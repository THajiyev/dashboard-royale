# Iteration 5 pre-registration: segment forecast (locals vs non-locals)

Written and committed on 2026-11-07, before any iteration 5 model was fitted or scored.

**Status of the May–Jun result: confirmatory, not a clean holdout.** The Locals Appreciation Week outcome
(Jun 9–15) has already been seen in iterations 3 and 4, and in a quick split by home region (locals +14%,
Domestic and Regional −7 to −8% that week). The design choices below were made knowing that. July data
is the first clean test (see `JULY_PLAN.md`).

## Segments

| Segment | Definition |
|---|---|
| Locals | carded theo of players with `home_region == "Local"` (sessions joined to players) |
| Non-locals | floor theo (`property_day.theo_usd`) minus locals: carded Regional, Domestic and International play, plus all uncarded play |

- Carded sessions cover about 66% of floor theo. Uncarded play can't be attributed to a segment, so it goes in the non-local group. This way the two segments add up exactly to the floor.
- Regional and International are not forecast separately, because they are too small to forecast day by day.
- Only data dated on or before each origin is used.

## Base and protocol

- **Protocol:** weekly refresh, the same as iteration 3. Refit every 7 days and forecast the next 7.
  - CV origins: Jan 31 + 7k through Apr 23.
  - Scoring origins: Apr 30 + 7k through Jun 25.
- **Base for each series:** the EL2 + 28-day anchor base, meaning the non-event weekday mean rescaled to the last 28 non-event days.
- **Reference model:** EL2 + anchor (k_ev = 0.5) on the floor total.

## How segments combine (chosen on Jan–Apr CV)

- **(a) Bottom-up:** forecast locals and non-locals separately (base × the segment's own lift), then add them up.
- **(b) Top-down:** forecast the floor total with the EL2 + anchor base. The event lift is the share-weighted mix of the segment lifts:
  - lift = s_L · lift_L + (1 − s_L) · lift_N
  - s_L is the locals share of base theo over the last 28 non-event days.

## Event lifts

- For event e and segment g, log lift_g(e) = log L_type(e) + δ_g(type).
  - L_type is the floor-level EL2 type lift: the event-level hierarchy with k_ev = 0.5.
  - δ_g is the segment adjustment. Each past event of that type counts as one observation: log(r_g / r_total), where r is the event-day mean ratio to that series' base.
  - δ_g is shrunk toward a prior δ0_g with pseudo-count k_ev = 0.5 events.
- **The prior is set in advance, not learned:**
  - Ordinary events (conventions, sports, festivals, and promotions not aimed at locals): δ0_L = δ0_N = 0, meaning the lift is the same for both segments.
  - Locals-targeted events: **the full type lift goes to locals, and non-locals get none.** In terms of the prior, δ0_L = 0 and δ0_N = −log L_type. The reasoning is that a locals promotion does not draw tourists.
  - An event is tagged locals-targeted if its name contains "Locals". This is known when the event is announced. At present only EV-P-LOCALS qualifies.

## Visitor trend (LVCVA)

- The iteration 4 `season_yoy` city index, using only published months (month end + 30 days), is applied to the **non-local segment only**.
- For (a), it applies to the non-local series directly. For (b), the floor multiplier is s_L + (1 − s_L) · idx^β.
- β ∈ {0, 0.5, 1} is chosen on Jan–Apr CV.

## Selection

- **Candidate grid:** 2 ways of combining × 3 values of β = 6 models.
- **Selection rule:** lowest Jan–Apr refresh-CV RMSE on daily theo.
- **Only the CV pick is eligible to become the challenger.** The other 5 are reported for context.

## Main metric and win rule

- **Main metric:** RMSE on daily theo, over all 61 days of May–Jun.
  - Forecasts get added up into budget totals, and large event-day misses cost more than small ones.
- **Win rule:** the iteration 5 CV pick becomes the **challenger** only if all three of these hold:
  1. Its RMSE is lower than EL2 + anchor's.
  2. The 95% CI on the RMSE difference excludes zero. The CI comes from a moving-block bootstrap: 7-day blocks, 2,000 resamples, seed 0.
  3. Its ordinary-day RMSE is no worse than EL2 + anchor's (point estimate).
- **Event days:** any day inside an event in `events.parquet`. **Ordinary days:** all other days.

## Bias controls

1. All choices are made on Jan–Apr only. May–Jun is scored once, with no tuning afterward. The look is logged in `holdout_log.jsonl`.
2. **Pre-June check:** the selection is repeated using Jan–Feb CV only (origins Jan 31 – Feb 21), then scored on Mar–Apr (refresh origins Feb 28 – Apr 23) against EL2 + anchor.
3. **Before modelling:**
   - A DiD of log(locals) − log(non-locals) over the Locals Week against equal baseline weeks on either side, with in-time placebo intervals (`impact.on_off`). This keeps the tourism trend from being mistaken for an event effect.
   - A displacement check: did non-local play fall most on the machines that locals played heavily that week?

## Output table

- One row per model, all scored on May–Jun: B2, EL1, EL2 + anchor, the best of iteration 2, the iteration 4 variants, and the iteration 5 candidates.
- Columns: RMSE, MAE, WAPE, bias, ordinary-day RMSE, event-day RMSE, Δ RMSE vs B2 with a block-bootstrap 95% CI, 90% band coverage, interval score, and whether the model was picked in advance.
- **90% bands:** split-conformal on each model's own Jan–Apr CV log-residuals (5th and 95th percentiles).
- **Interval score:** Winkler score at α = 0.1.
- Earlier models are re-scored with the new metrics only. Nothing is re-selected.
