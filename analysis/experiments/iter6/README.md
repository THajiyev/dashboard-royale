# Iteration 6: does a recent-demand adjustment improve EL?

**Answer: no, not for EL as it is used now.**
- When EL is forecast once on Apr 30 (the headline setup), every one of the 128 recent-demand variants made May–Jun
  worse, most of them significantly.
- When EL is refit every week, an adjustment helps on ordinary days, by about 12% compared with refreshed EL. But
  that is the same 28-day anchor that iteration 3 already built into EL2A, and the gain on the full 61 days isn't
  significant.

**Recommendation:** don't integrate an adjustment into EL. EL is unchanged (`ds_alpha/models.py`).

The design, including the selection rule, was fixed in `PREREG.md` before anything was scored. An amendment was added
after Jan–Apr CV and before the May–Jun look.

## Files

| File | What it does |
|---|---|
| `PREREG.md` | the grid, the selection rule and the pre-look amendment |
| `models.py` | `EL × m`, where m = 1 + w·(R − 1). EL is imported unchanged. |
| `evaluate.py` | `check`: leakage and equivalence tests. `cv`: Jan–Apr only. `holdout`: one logged look (`holdout_log.jsonl`); refuses a second run. |
| `cv_results.csv`, `cv_folds.csv`, `cv_pick.json` | stage 1: every variant, both protocols, Jan–Apr only |
| `holdout_table.csv`, `holdout_weeks.csv`, `holdout_daily.csv` | stage 2: every variant scored on May–Jun |

## What was tried

| Choice | Values | Total |
|---|---|---:|
| Recent statistic | 7-, 14- or 28-day mean; EMA with half-life 7, 14 or 28 days; weekday-specific mean over 28 or 56 days, shrunk toward the all-day level | 8 |
| Event handling | `excl` drops event days. `excl_clo` also drops the walkway closure. `delift` keeps event days but measures them against EL's lifted fit. `raw` measures event days against the weekday base, so spikes leak in. | 4 |
| Strength w | 25%, 50%, 75%, 100% | 4 |
| Protocol | fixed (one forecast on Apr 30) or weekly refresh | 2 |

How the adjustment works:
- **What R measures:** the recent level of actual ÷ EL's own in-sample fit. It is a multiplicative adjustment on
  EL's prediction; EL's historical weekday base is kept, not replaced.
- **Leakage controls:**
  - Every input is dated on or before the origin, and events count only once announced.
  - `evaluate.py check` proves the forecasts don't change when every value after the origin is tripled.
  - The same check shows w = 0 gives back EL exactly, and that the 28-day, 100% variant reproduces iteration 3's
    CV figure ($4,052).

## Comparison table (May 1 – Jun 30, daily theo; average theo is $128K a day)

- **Picked in advance:** the two reference models and each protocol's CV picks only.
- **Δ vs EL:** compared with EL under the same protocol, with a 7-day block-bootstrap 95% CI.

| Protocol | Model | Role | RMSE | MAE | Δ RMSE vs EL (95% CI) | Δ RMSE vs B1 | Ordinary-day MAE | Event-day MAE | May MAE | Jun MAE | Weeks beating EL |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| fixed | B1 weekday mean | baseline | 8,299 | 6,699 | +51% | — | 6,328 | 8,591 | 6,051 | 7,369 | 0/9 |
| fixed | **EL (original)** | reference | **5,503** | **4,290** | — | **−34%** | 4,217 | 4,660 | 3,491 | 5,115 | — |
| fixed | EL × mean14d [excl] 100% | clean CV pick | 6,623 | 5,292 | **+20% (+12 to +28)** | −20% | 5,386 | 4,812 | 4,243 | 6,375 | 0/9 |
| fixed | EL × ema hl28d [raw] 50% | rule CV pick | 6,422 | 5,087 | **+17% (+10 to +23)** | −23% | 5,151 | 4,765 | 4,033 | 6,177 | 0/9 |
| fixed | *best of 128, post hoc:* ema hl28d [delift] 25% | — | 5,630 | 4,394 | +2.3% (+1.0 to +3.4) | −32% | — | — | — | — | 1/9 |
| refresh | EL refreshed weekly | reference | 7,198 | 5,267 | — | −13% | 3,996 | 11,752 | 3,582 | 7,009 | — |
| refresh | **EL × mean28d [delift] 100%** | clean CV pick | 6,647 | 4,730 | −7.7% (−18 to +4.5) | −20% | **3,514** | 10,929 | 3,968 | 5,517 | 6/9 |
| refresh | EL × mean28d [raw] 50% | rule CV pick | 7,682 | 5,612 | +6.7% (+0.2 to +9.5) | −7% | 4,237 | 12,623 | 3,846 | 7,437 | 4/9 |
| refresh | *best of 128, post hoc:* mean7d [delift] 100% | — | 5,930 | 4,658 | −18% (−33 to +11) | −29% | — | — | — | — | 5/9 |

**Across the whole grid, post hoc** (`holdout_table.csv`):
- Fixed: 0 of 128 variants beat EL.
- Refresh: 92 of 128 beat refreshed EL, but none beats fixed EL's $5,503 RMSE. Locals Week (Jun 9–15) is the reason.

## Which approach works best, and why

1. **Event days have to be kept out of the level.** `delift` and `excl` are the best modes, and `raw` is the worst
   mode on May–Jun under 56 of the 64 settings. It ties on the other 8 (fixed 7- and 14-day means), where no event
   fell inside the window.
   - `raw` won Jan–Apr CV, but only through two errors cancelling (see the `PREREG.md` amendment).
   - Event spikes put its R 2–3.6% high. In Jan–Apr that happened to offset EL's 1–2% under-forecast while the
     level was rising.
   - `delift`, which keeps event days but measures them against EL's lifted fit, is marginally better than dropping
     them, because it uses more days.
   - Dropping the closure too (`excl_clo`) made no useful difference.
2. **Plain rolling means work as well as anything more elaborate.**
   - EMA was no better than a plain mean of the same length.
   - Weekday-specific recent levels were consistently worse than one shared factor. Four Mondays are too few to
     separate a weekday shift from noise.
3. **Under a fixed horizon, a recent-demand factor can only add bias.** Errors this spring are mostly bias.
   - On Apr 30 the recent factor pointed *up*, by 1–2%, because April was strong.
   - May–Jun then fell, and EL was already over-forecasting by $2.5K a day.
   - A 1.4% up-shift adds about $1.8K a day of bias, which is why the clean pick is 20% worse.
   - The Jan–Apr CV said the opposite (5.8% better, 7/7 folds), because the level rose through March–April. Iteration
     2 found the same reversal.
   - Jan–Apr CV can't tell whether the level is about to keep going or reverse, so it can't be used to choose a
     recent-level factor for a 61-day horizon.
4. **Under weekly refresh, the factor helps, because it can follow a downturn within a few weeks.**
   - The factor slid from 1.016 (Apr 30) to 0.965 (Jun 25).
   - The gains are in the weeks of May 29, Jun 19 and Jun 26.
   - It loses in early May, when the factor was still carrying April's strength.
   - Shorter windows (7 days) look even better on May–Jun but were worse in Jan–Apr CV. That is hindsight, not a
     choice that could have been made in advance.

## Is the improvement meaningful?

| Question | Fixed (clean pick) | Refresh (clean pick) |
|---|---|---|
| Better than EL on May–Jun? | No: significantly worse (+20%) | Yes, but the CI includes 0 (−7.7%; −18% to +4.5%). DM p = 0.05 on MAE. |
| Better in both months? | No | No: worse in May (+11% MAE), better in June (−21%) |
| Consistent across weeks? | 0/9 weeks | 6/9 weeks, with the gain concentrated in 3 weeks |
| Survives dropping its 5 best days? | — | Yes: MAE $4,851 vs EL's $5,041 on the remaining days |
| Size in practice | — | Ordinary days: −$480 a day vs refreshed EL (≈0.4% of theo), and −$700 vs fixed EL |
| Pre-registered verdict | Fails | Fails: it doesn't meet the CI or both-months conditions |
| New evidence? | Yes | Little: the same model as iteration 3's 28-day anchor, already seen on May–Jun |

## Recommendation

- **Don't add a recent-demand adjustment to EL.**
  - For the headline fixed-horizon forecast, it made the result reliably worse.
  - Jan–Apr gives no way to know in advance which direction the level will go.
- **For weekly refresh, it is already in place.**
  - EL2A, iteration 3's main model, is EL with event-level shrinkage and a 100% 28-day non-event anchor.
  - The best clean refresh variant here is that same mechanism, so there is nothing new to integrate.
  - One small finding: de-lifting event days rather than dropping them gave 0.1 points more CV gain. That is too
    small to justify a change.
- **The next real test is July,** which the existing `iter5/JULY_PLAN.md` already covers (EL2A vs segments). July
  could also score fixed EL with and without a recent factor. That would be the first clean out-of-sample test of
  this question, since May–Jun has now been seen 9 times.

## Caveats

- **One test window,** 61 days, with one unusual month: June's drop in visitor play.
- A different spring, where the level kept rising, could reverse the fixed-protocol verdict. That is exactly why it
  shouldn't be adopted: its sign depends on something the model can't see.
- **The holdout was not clean** (see `PREREG.md`). Results here are confirmatory.
- **Every variant was scored on May–Jun.** Only the CV picks count as picked in advance; the grid view is for
  explanation only.
