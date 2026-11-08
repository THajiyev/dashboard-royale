# Iteration 5: locals vs non-locals segment forecast

**Status: confirmatory, not a clean holdout.** The Locals Week outcome was already known when this was designed.
The design was pre-registered in `PREREG.md` (commit `624ad20`) before any model was fitted.

**Result: the segment model is not promoted.**
- The pre-registered pick (bottom-up, LVCVA trend β = 0.5 on non-locals) cuts May–Jun RMSE by 12.3% compared with EL2 + anchor, and ordinary-day RMSE is no worse.
- But the 95% block-bootstrap CI on the difference is **−20.4% to +1.0%**, which includes zero, so it fails the win rule.
- In the pre-June check, choosing on Jan–Feb only gave a different variant, and that variant was 4.6% *worse* on Mar–Apr (CI −3.6% to +13.9%).

| File | What it does |
|---|---|
| `PREREG.md` | the design, written and committed before running anything |
| `segments.py` | daily theo for locals (carded, home region Local) and non-locals (everything else, including uncarded play); the two add up to the floor exactly |
| `checks.py` | Locals Week DiD, displacement check, walkway closure 95% bound |
| `models.py` | `make_seg(combo, beta)`: the 6 pre-registered candidates |
| `evaluate.py` | `cv`: Jan–Apr selection and the pre-June check (`cv_results.csv`, `prejune_check.json`); `holdout`: one look at May–Jun (`final_table.csv`, `holdout_daily.csv`) |
| `table_vs_b1.py` | the output table, every model vs B1 (`table_vs_b1.md`, `table_vs_b1.csv`) |

## 1. Checks before modelling

**Locals Week DiD (Jun 9–15).**
- Method: the `impact.on_off` estimator, with 14 baseline days on each side, weekday effects, a linear trend, and 45 in-time placebos. Intervals are 90%.

| Series | Effect | 90% interval |
|---|---:|---|
| Floor total | +7.0% | +2.5% to +11.6% |
| Locals | **+14.4%** | +9.0% to +20.1% |
| Non-locals (incl. uncarded) | +2.1% | −3.7% to +8.3% |
| Carded non-locals | −5.4% | −12.9% to +2.9% |
| **DiD: locals vs non-locals** | **+12.0%** | +4.2% to +20.4% |

The event effect on locals survives netting out the tourism trend. The promotion worked on its audience.

**Displacement: none found.**
- The first version grouped machines by the locals' share *in the event week* and found a strong "displacement" slope.
- That slope is mechanical: wherever non-locals left a machine, the locals' share rose automatically.
- Grouping by the locals' share in the 14 days *before* the event removes it. Carded non-local play fell 1–10% in every tercile, and the slope is +0.26 ± 0.23, not significant.
- So non-locals dipped evenly across the floor rather than being pushed off locals' machines.

| Tercile (pre-event locals share) | Machines | Locals | Carded non-locals | Uncarded |
|---|---:|---:|---:|---:|
| Low (31%) | 103 | +16.0% | −9.7% | +4.0% |
| Mid (39%) | 102 | +14.5% | −0.7% | +8.0% |
| High (49%) | 103 | +11.7% | −6.2% | +13.6% |

## 2. Selection on Jan–Apr

Refresh-protocol CV, RMSE on daily theo:

| Model | Jan–Apr CV RMSE | Jan–Feb CV RMSE | Mar–Apr test RMSE |
|---|---:|---:|---:|
| EL2 + anchor (reference) | 5,600 | 6,893 | 4,825 |
| bottom-up β 0 | 5,573 | 6,883 | 4,785 |
| **bottom-up β 0.5 (Jan–Apr pick)** | **5,519** | 6,647 | 4,858 |
| bottom-up β 1 | 5,592 | 6,620 | 5,000 |
| top-down β 0 | 5,591 | 6,893 | 4,810 |
| top-down β 0.5 | 5,542 | 6,652 | 4,893 |
| top-down β 1 (Jan–Feb pick) | 5,620 | **6,619** | 5,047 |

- The way segments are combined barely matters.
- β, the weight on the LVCVA visitor trend, is what moves the result, and it isn't stable. More weight helped in Jan–Feb and hurt in Mar–Apr.

## 3. May–Jun, all models (one logged look)

**Baseline: B1, the weekday mean.** It averages all Jan–Apr days by day of week, with no events, holidays or outside data. B0 (constant mean) is shown for reference. B2 is ranked as an ordinary model.

- **Sorting and ranks:** sorted by RMSE, with ranks on both RMSE and MAE.
- **Δ vs B1:** error ratio minus 1, so negative means better. The 95% moving-block bootstrap CI is in brackets, and **bold** means it excludes zero.
- **Event days:** the 10 days inside an event (EDC and Locals Week).
- **90% bands:** split-conformal from each model's own Jan–Apr CV residuals.
- **Interval score:** Winkler at α = 0.1; lower is better.
- **Source:** built by `table_vs_b1.py` from the saved predictions, with no refitting (`table_vs_b1.csv`). The CI against EL2 + anchor, which the win rule uses, is in `final_table.csv`.

| Rank (RMSE) | Rank (MAE) | Model | Iter | Protocol | Picked in advance? | RMSE | Δ RMSE vs B1 (95% CI) | MAE | Δ MAE vs B1 (95% CI) | WAPE | Bias | Ordinary RMSE | Event RMSE | 90% cover | Interval score |
|---:|---:|---|---|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | 1 | EL x CatBoost residual (best post hoc) | Iter 2 | fixed | no | 5,381 | **−35.2% (−46.4% to −25.3%)** | 4,151 | **−38.0% (−49.4% to −28.2%)** | 3.24% | +2,365 | 5,250 | 6,004 | 82% | 30,793 |
| 2 | 2 | EL + hol near1 lam=5 | Iter 4 | fixed | no | 5,468 | **−34.1% (−44.8% to −24.7%)** | 4,239 | **−36.7% (−46.0% to −28.3%)** | 3.31% | +2,339 | 5,279 | 6,343 | 75% | 30,864 |
| 3 | 4 | EL + hol longwknd+day lam=2 | Iter 4 | fixed | no | 5,469 | **−34.1% (−44.5% to −24.8%)** | 4,261 | **−36.4% (−45.5% to −28.1%)** | 3.33% | +2,510 | 5,297 | 6,274 | 75% | 31,027 |
| 4 | 5 | EL + hol kernel1 lam=20 | Iter 4 | fixed | no | 5,500 | **−33.7% (−44.2% to −24.3%)** | 4,286 | **−36.0% (−45.3% to −27.8%)** | 3.35% | +2,490 | 5,334 | 6,282 | 75% | 31,530 |
| 5 | 6 | EL event-type lift | Iter 1 | fixed | yes | 5,503 | **−33.7% (−44.1% to −24.3%)** | 4,290 | **−36.0% (−45.3% to −27.8%)** | 3.35% | +2,501 | 5,338 | 6,274 | 75% | 31,563 |
| 6 | 3 | EL + hist season_yoy beta=0.5 | Iter 4 | fixed | no | 5,529 | **−33.4% (−43.9% to −23.3%)** | 4,247 | **−36.6% (−46.2% to −27.6%)** | 3.32% | +2,627 | 5,312 | 6,521 | 87% | 23,891 |
| 7 | 13 | B2 event-aware weekday | Phase 0 | fixed | yes | 5,595 | **−32.6% (−40.3% to −24.9%)** | 4,460 | **−33.4% (−39.2% to −27.0%)** | 3.48% | +1,979 | 5,338 | 6,752 | 97% | 25,485 |
| 8 | 8 | EL2A segments: bottom_up beta=0.5 | Iter 5 | refresh | yes | 6,003 | **−27.7% (−50.0% to −2.5%)** | 4,410 | **−34.2% (−54.3% to −8.3%)** | 3.44% | +3,168 | 4,768 | 10,193 | 79% | 29,882 |
| 9 | 7 | EL2A segments: bottom_up beta=1.0 | Iter 5 | refresh | no | 6,003 | **−27.7% (−49.7% to −2.9%)** | 4,399 | **−34.3% (−54.8% to −8.8%)** | 3.43% | +3,125 | 4,745 | 10,249 | 80% | 30,111 |
| 10 | 12 | EL2A segments: bottom_up beta=0.0 | Iter 5 | refresh | no | 6,009 | **−27.6% (−49.7% to −2.3%)** | 4,422 | **−34.0% (−54.5% to −7.9%)** | 3.45% | +3,210 | 4,798 | 10,141 | 75% | 33,703 |
| 11 | 10 | EL2A segments: top_down beta=0.0 | Iter 5 | refresh | no | 6,018 | **−27.5% (−49.9% to −2.0%)** | 4,413 | **−34.1% (−54.5% to −8.2%)** | 3.45% | +3,215 | 4,793 | 10,185 | 75% | 33,797 |
| 12 | 9 | EL2A segments: top_down beta=0.5 | Iter 5 | refresh | no | 6,026 | **−27.4% (−49.7% to −2.3%)** | 4,413 | **−34.1% (−54.4% to −8.2%)** | 3.45% | +3,182 | 4,776 | 10,255 | 82% | 29,802 |
| 13 | 11 | EL2A segments: top_down beta=1.0 | Iter 5 | refresh | no | 6,039 | **−27.2% (−49.3% to −2.6%)** | 4,416 | **−34.1% (−54.4% to −8.5%)** | 3.45% | +3,148 | 4,765 | 10,328 | 80% | 30,686 |
| 14 | 15 | EL + hist seasonal beta=0.5 | Iter 4 | fixed | yes | 6,126 | **−26.2% (−38.2% to −16.3%)** | 4,808 | **−28.2% (−40.9% to −19.8%)** | 3.75% | +3,660 | 6,155 | 5,972 | 85% | 24,315 |
| 15 | 14 | EL2A + hist seasonal beta=0.5 | Iter 4 | refresh | no | 6,665 | −19.7% (−49.1% to +14.4%) | 4,759 | −29.0% (−54.3% to +6.5%) | 3.72% | +3,587 | 4,810 | 12,367 | 77% | 33,912 |
| 16 | 17 | EL2A + hol longwknd+day lam=2 | Iter 4 | refresh | yes | 6,823 | −17.8% (−48.8% to +18.5%) | 4,843 | −27.7% (−53.8% to +9.3%) | 3.78% | +3,660 | 4,761 | 12,975 | 74% | 41,564 |
| 17 | 20 | EL2A + hol near1 lam=5 | Iter 4 | refresh | no | 6,839 | −17.6% (−48.4% to +18.7%) | 4,853 | −27.6% (−53.5% to +9.4%) | 3.79% | +3,597 | 4,794 | 12,966 | 72% | 41,708 |
| 18 | 19 | EL2 + 28d anchor (main) | Iter 3 | refresh | yes | 6,842 | −17.6% (−48.4% to +18.8%) | 4,849 | −27.6% (−53.6% to +9.5%) | 3.79% | +3,651 | 4,793 | 12,975 | 72% | 41,747 |
| 19 | 18 | EL2A + hol kernel1 lam=20 | Iter 4 | refresh | no | 6,842 | −17.5% (−48.4% to +18.7%) | 4,848 | −27.6% (−53.7% to +9.4%) | 3.79% | +3,652 | 4,793 | 12,978 | 72% | 41,781 |
| 20 | 16 | EL2A + hist season_yoy beta=0.5 | Iter 4 | refresh | no | 6,864 | −17.3% (−48.3% to +18.6%) | 4,838 | −27.8% (−54.1% to +9.4%) | 3.78% | +3,592 | 4,750 | 13,126 | 77% | 36,275 |
| 21 | 21 | EL + recent-level (28d) + payday | Iter 2 | fixed | yes | 6,908 | **−16.8% (−29.1% to −6.0%)** | 5,497 | **−18.0% (−30.0% to −8.5%)** | 4.29% | +4,691 | 6,977 | 6,547 | 70% | 39,392 |
| 22 | 22 | B1 weekday mean **(baseline)** | Phase 0 | fixed | yes | 8,299 | — | 6,699 | — | 5.23% | +4,029 | 7,737 | 10,714 | 77% | 45,312 |
| 23 | 23 | B0 constant mean | Phase 0 | fixed | yes | 23,950 | +188.6% (+148.2% to +239.9%) | 20,853 | +211.3% (+165.5% to +268.9%) | 16.28% | +3,041 | 22,659 | 29,675 | 82% | 90,225 |

**Win rule for the iteration 5 pick against EL2 + anchor:**
- RMSE: −12.3%. ✓
- 95% CI: −20.4% to +1.0%. ✗
- Ordinary-day RMSE: $4,768 vs $4,793. ✓
- **No challenger is promoted.**

## How to read it

1. **Switching to RMSE changes the leaderboard.** Every weekly-refresh model ranks below every fixed EL model.
   - The refresh models have the best ordinary-day RMSE ($4,745–4,810, vs $5,250–6,155 for the fixed models).
   - But their event-day RMSE is about twice as large ($10–13K vs about $6K).
   - Squaring the errors makes those 10 event days dominate.
2. **EL's good score on Locals Week is luck.** The fixed forecast was made on Apr 30. The Locals Week was announced on May 26, so EL forecast it as an ordinary week at a level that was too high, and came out −2.9% for the week.
   - The refresh models knew about the event and applied a promotion lift: EL2A was +10.5% for the week, the segment model +7.7%.
   - The segment prior removed about a quarter of EL2A's overshoot. It didn't remove more because the prior counts for only 0.5 events against one observed promotion (the slot tournament), whose adjustment is what drives the remaining lift.
3. **The CIs are wide because the gaps come from one week.** EL vs EL2 + anchor is −19.6% RMSE, with a 95% CI of −39.7% to +18.5%.
   - That gap is mostly Locals Week. Excluding that week, EL2A beats EL: RMSE $5,071 vs $5,510.
4. **Calibration.**
   - The refresh models' 90% bands cover only 72–80% of days. Their CV residuals have little event-day error, so the bands are too narrow on events.
   - B1's bands cover 77%, and B2's cover 97%, so B2's are honest but wide.
   - The fixed EL with LVCVA season × YoY has the best interval score (23,891).

## Pre-registered verdict

| Rule (PREREG.md) | Iteration 5 pick vs EL2 + anchor | Pass? |
|---|---|---|
| Lower May–Jun RMSE | 6,003 vs 6,842 (−12.3%) | yes |
| 95% block-bootstrap CI on the RMSE difference excludes zero | −20.4% to +1.0% | **no** |
| Ordinary-day RMSE no worse | 4,768 vs 4,793 | yes |

**Verdict: the pick does not become the challenger.** EL2 + anchor stays the main model.

**Deviation from the pre-registration, recorded here:**
- After the look, the output table's reference column changed from B2 to B1, because B1 is the official simple baseline.
- This does not affect the win rule, which compares against EL2 + anchor.

## Noise floor

`noise_floor.py` fits models on all of Jan–Jun and compares their in-sample error on ordinary (non-event) days with our out-of-sample error on May–Jun ordinary days (51 days).

| In-sample fit, Jan–Jun | Ordinary-day RMSE on May–Jun days |
|---|---:|
| EL, the best model picked in advance | 4,649 |
| Weekday profile × centred 28-day level (in hindsight) | 3,674 |
| Weekday profile × centred 14-day level (in hindsight) | 3,372 |

| Out-of-sample model | Ordinary-day RMSE | Gap to EL in-sample | Gap to 28-day hindsight floor |
|---|---:|---:|---:|
| Iteration 5 pick | 4,768 | +2.5% | +29.8% |
| EL2 + anchor (main) | 4,793 | +3.1% | +30.5% |
| EL | 5,338 | +14.8% | +45.3% |
| B1 baseline | 7,737 | +66.4% | +110.6% |

**How to read the gaps:**
- **Against EL's own in-sample fit,** every model picked in advance is within 15%. The refresh models are within about 3%.
- **The hindsight floors are lower** because they know the level on both sides of each day. That is information a forecast never has.
- **The ~30% gap to the hindsight floor is the cost of not knowing next week's demand level.** Closing it would need leading information that this dataset doesn't contain, such as hotel bookings.
- **Iterations 2–5 all tried to model the level** (trends, recency weights, LVCVA history, segments), and none closed the gap.

## Walkway closure, 95% bound

- Same estimator and placebos as `run_impact.closure`: the whole floor excluding the new bank, measured directly, with 34 placebos and the 1.25 calibration factor.
- Point estimate: +$1,975/day.
- **No loss larger than $811/day (−0.6%) at 95%.** That is at most about $28K over the 35 days. The 90% bound is −$303/day.
- Caveat: the 1.25 calibration factor was validated at 90%. Applying it at 95% is an assumption.

## Holdout accounting

1 completed look at May–Jun (`holdout_log.jsonl`), covering all 21 models. The candidate set and the pick were fixed by `cv_results.csv` beforehand.

Before that look, two runs crashed partway through:
- The first ran out after three models' predictions, because `catboost` was not installed.
- The second crashed while building the event-day mask, after all predictions were made.

Neither printed or saved any metric, and nothing was changed between runs except the install and the mask fix.
