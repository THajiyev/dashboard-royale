# Casino Manager

## The bottom 10

Casino Manager found that the 10 lowest earners shouldn't be replaced. Most of the performance is explained by the poor location in Back Forty. M-1158 was the only machine flagged for inspection, but it was not confirmed as faulty.

## Demand

Demand follows the day of the week and events such as sports, festivals, conventions and new banks. The walkway closure and a visitor-driven June slowdown also cut demand.

## Downtime

Downtime cost around 5021 hours and $102K in theo (expected house win). Downtime happened every month, but it was the worst in May.

## Players

Tracked players wagered $163.8M and got back $148.2M (a net loss of $15.6M). The top 10% of losers are responsible for 53% of losses.

## Comps

Comp cost was ≈$191K in total. On May 1st, points per comp halved without providing extra play, and raised cost by 9%.

## Model

For the ML section, I used a Poisson GLM to predict each machine's play per hour. I trained on January to April and tested on May to June. I improved the MAE by 28% compared to the baseline of zone averages ($53.1 vs $38.2). This model helps decide if moving a machine is worth it.

## July plan

When planning out the month of July, I would spend $48.3K out of the $100K and keep $51.7K.

- **Promotions ($30K).** I would spend $30K on 2 promotion weekends. Past promotions added $8.4K and $26.1K of theo a day. The uncertainty comes from the small sample size of two events, but the outcome is easily measured by comparing to the July forecast (see appendix).
- **Machine moves ($10.8K).** I would move 6 machines for $10.8K. Both our ML model and past record of a move adding $342 a day support this idea. Uncertainty comes from our ML model's coefficient range. The outcome is easily measured by comparing the moved and unmoved machines' usage rates.
- **Back Forty signs ($7.5K).** Lastly, I would purchase new signs for Back Forty for $7.5K. Closing the walkway to the area cut its play by around 31%, so improving access should help. It is uncertain since this is mostly an assumption based on a logical connection. The outcome is measured by comparing this area to others.

---

# Appendix

## AI Statement

I utilized GitHub Copilot and Claude Code for planning, coding, and editing my documentation. I used ChatGPT to generate the website logo. Claude proofread and edited my writing. For the Claims & Evidence table, Claude drafted the claims, table/query and result columns from my writing, code and outputs, which I checked.I wrote the alternative explanations and limitations myself.

## Another ML model (Optional Read)

I also used time-series to forecast theo for the day. My baseline was the average for each day of the week using data from January to April. The model used weekday averages and lifts for different event types. Tested on May to June, it cut the MAE by 36% ($6699 to $4290). This gave the July forecast that the plan's results are measured against.

## Claims & Evidence

Every table is in `data/`; scripts and model outputs are in the repository. The dashboard's Evidence page recomputes the headline claims from raw data (`python scripts/reproduce_claims.py`).

| # | Claim | Table / query | Result | Alternative explanation | Limitation |
|---|---|---|---|---|---|
| 1 | Most of the bottom 10 are low because of location | `machine_day`: `SUM(house_win_cents)` per machine on active days, lowest 10; zone from `prepared_daily_view.zone_name` (zone on most days) | 9 of the 10 sit in Back Forty | | |
| 2 | M-1158 is the only machine flagged for inspection | `machine_day` (`house_win`, `coin_in`, `theo`, `paid_spins`, `payout_positive_spins`) + `game_math.hit_probability`: observed vs configured hold; win-rate z per machine, Benjamini–Hochberg across 310 machines | Hold 3.0% vs 10% configured; win-rate z = +124; only machine flagged after correction | | |
| 3 | Demand follows the day of the week and events | `property_day.theo_usd` + `events.event_type`, Jan–Apr: event-day theo ÷ the normal level for that weekday, averaged by event type | Sports and festivals +17–20%; conventions +3% | | |
| 4 | New banks raised demand | `outputs/model_change_impacts.csv`, bank B-51 rows (`analysis/impact.py`): new machines' theo minus cannibalisation of existing Pit machines | +$5.3K theo a day (90% CI $4.6K–$6.0K) | | |
| 5 | The walkway closure cut demand in Back Forty | `prepared_daily_view` (`coin_in_usd`, `available_hours`, `zone_id`): daily log(coin-in per available hour), Back Forty minus 5 control zones, OLS on closed + reopened + weekday | −30.9% while closed (Mar 3 – Apr 6), recovered after; whole floor +1.6% (90% CI −0.2% to +3.4%) | | |
| 6 | A visitor-driven June slowdown cut demand | `property_day.theo_usd`, `events` (event days dropped): Σ weekday-baseline forecast ÷ Σ actual − 1 on ordinary June days; locals vs visitors split on the Demand page | June 6.5% below weekday norms, mostly visitors | | |
| 7 | Downtime cost about 5021 hours | `machine_day`: Σ (`scheduled_seconds` − `available_seconds`) over active machine-days | 5,021 hours, 0.4% of scheduled time; 98% fault repairs | | |
| 8 | Downtime cost $102K in theo | `outputs/phase0_downtime_lost_play.csv` (`analysis/run_phase0.py`): down hours × the machine's theo per hour | ≈ $102K theo, Jan–Jun | | |
| 9 | Downtime was worst in May | `prepared_daily_view.downtime_hours` by month | May 1,017 h (highest); June 631 h (lowest) | | |
| 10 | Tracked players wagered $163.8M, got back $148.2M | `sessions` (carded play), Jan–Jun: Σ coin-in, Σ payout | $163.8M wagered, $148.2M paid back, net loss $15.6M | | |
| 11 | The top 10% of losers account for 53% of losses | `player_period`: `tracked_payout_usd − tracked_coin_in_usd` per player; losers sorted by loss, share held by the top 10% | 53% | | |
| 12 | Comps cost about $191K | `player_period.comp_cost_usd`, Σ Jan–Jun | ≈ $191K ($30.8K a month Jan–Apr, $33.7K May–Jun) | | |
| 13 | On May 1 points per comp halved | `loyalty_ledger` redeem events: median points per $1 of comp value, before vs after May 1 | −53% (15 → 7 points per $1), every tier | | |
| 14 | Comp cost rose 9% | `player_period.comp_cost_usd`: May–Jun monthly ÷ Jan–Apr monthly − 1 | +9.4% (≈ $2,900 a month) | | |
| 15 | The cut brought no extra play | `player_period` (`theo_usd`, `home_region`, `comps_redeemed`): theo May–Jun ÷ Mar–Apr − 1 | Locals who used comps −2.5%; all locals −1.2% | | |
| 16 | The Poisson GLM beats zone averages by 28% | `prepared_daily_view` coin-in per available hour (`analysis/machine_effects.py`): GLM on bank + theme + weekday + events + closure, trained Jan–Apr, tested May–Jun | MAE $38.2 vs $53.1 | | |
| 17 | The time-series forecast cuts error by 36% | `property_day.theo_usd`: weekday-mean baseline vs event-type lift model frozen on Apr 30, scored May 1 – Jun 30 (`analysis/experiments/iter5/holdout_daily.csv`) | MAE $6,699 → $4,290 | | |
| 18 | The plan costs $48.3K | `action_catalog` (`unit_cost_cents`, `recurring_cost_cents_per_day`, `lead_days`), GUIDE budget formula | $48,300 spent, $51,700 kept | | |
| 19 | Past promotions added $8.4K and $26.1K of theo a day | `outputs/model_change_scorecard.csv` (`analysis/impact.py`): floor theo on promotion days vs expected level | Locals Week +$8.4K a day (90% CI $3.4K–$13.3K); Winter Slot Tournament +$26.1K ($17.2K–$34.6K) | | |
| 20 | A past move added $342 a day | `outputs/model_change_impacts.csv`, "Move M-1152 … NET" row: direct effect + spillover on bank-mates | +$342 a day (90% CI $188–$497) | | |
