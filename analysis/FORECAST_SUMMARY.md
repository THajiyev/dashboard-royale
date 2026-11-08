# Daily theo forecast: model summary

**Task.** Forecast the casino's daily theo (expected slot revenue). Models learn from Jan 1 – Apr 30, 2025 and are scored on May 1 – Jun 30 (61 days) they never saw.

**Baseline.** B1 is the average theo for each day of the week in Jan–Apr. It uses no event, holiday or outside data.

**Result.** The **EL event-type lift** model is the headline. It was picked before the test period, and it cuts the daily error by about a third compared with B1:

| | B1 baseline | EL |
|---|---:|---:|
| Average daily miss (MAE) | $6,699 | **$4,290** |
| Miss as a share of theo | 5.2% | **3.4%** |
| RMSE change vs B1 (95% CI) | — | **−34%** (−44% to −24%) |

## How the models work

| Model | Approach |
|---|---|
| **B0 constant mean** | One number for every day: the Jan–Apr daily average. |
| **B1 weekday mean** *(baseline)* | The Jan–Apr average for each day of the week. |
| **B2 event-aware weekday** | Weekday averages from non-event days, times one shared lift (about +10%) on known event days. |
| **EL event-type lift** *(iteration 1)* | Like B2, but each event type gets its own lift. Sports and festivals add about +17–20%, conventions about +3%. Types with few examples borrow strength from similar types. Forecast made once on Apr 30. |
| **EL2 + 28-day anchor (EL2A)** *(iteration 3)* | EL refit every week to forecast the next 7 days. The level is reset to the last 28 non-event days, and each event counts as one piece of evidence, so a 3-day event isn't counted as three. |
| **EL + extras** *(iterations 2 and 4)* | EL with one addition: a CatBoost correction on its errors; holiday flags (long weekend, near a holiday, closeness to a holiday); a payday term; the 2023–24 Las Vegas seasonal pattern; or the latest published city visitor trend. |
| **Segments** *(iteration 5)* | Separate weekly forecasts for local players and visitors, then combined. A locals-only promotion lifts only the locals forecast. The city visitor trend is applied to visitors only. |

**Protocol:** *fixed* means one forecast made on Apr 30 for all 61 days. *Refresh* means refit every 7 days and forecast the next week.

## Rankings (May–Jun 2025, daily theo)

- **Sorting:** by RMSE, which is like MAE but penalises big misses more. MAE is the average daily miss in dollars.
- **Δ vs B1:** the change in RMSE, with its 95% block-bootstrap CI. ✓ means the CI excludes zero, so the model is significantly better.
- **Picked in advance:** the model was chosen on Jan–Apr results before May–Jun was seen. Only these count as honest wins.
- **Event days:** EDC (May 16–18) and Locals Week (Jun 9–15).

| Rank | Model | Iter | Protocol | Picked in advance | RMSE | MAE | Δ RMSE vs B1 (95% CI) | Ordinary-day RMSE | Event-day RMSE | 90% range coverage |
|---:|---|:-:|---|:-:|---:|---:|---|---:|---:|---:|
| 1 | EL × CatBoost residual | 2 | fixed | no | 5,381 | 4,151 | −35% (−46% to −25%) ✓ | 5,250 | 6,004 | 82% |
| 2 | EL + within-1-day-of-holiday flag | 4 | fixed | no | 5,468 | 4,239 | −34% (−45% to −25%) ✓ | 5,279 | 6,343 | 75% |
| 3 | EL + long-weekend & holiday flags | 4 | fixed | no | 5,469 | 4,261 | −34% (−45% to −25%) ✓ | 5,297 | 6,274 | 75% |
| 4 | EL + holiday closeness kernel | 4 | fixed | no | 5,500 | 4,286 | −34% (−44% to −24%) ✓ | 5,334 | 6,282 | 75% |
| 5 | **EL event-type lift** | 1 | fixed | **yes** | **5,503** | **4,290** | **−34% (−44% to −24%) ✓** | 5,338 | 6,274 | 75% |
| 6 | EL + city visitor trend (YoY) | 4 | fixed | no | 5,529 | 4,247 | −33% (−44% to −23%) ✓ | 5,312 | 6,521 | 87% |
| 7 | B2 event-aware weekday | 0 | fixed | yes | 5,595 | 4,460 | −33% (−40% to −25%) ✓ | 5,338 | 6,752 | 97% |
| 8 | Segments: locals + visitors (iteration 5 pick) | 5 | refresh | yes | 6,003 | 4,410 | −28% (−50% to −3%) ✓ | 4,768 | 10,193 | 79% |
| 9 | Segments, bottom-up, full visitor trend | 5 | refresh | no | 6,003 | 4,399 | −28% (−50% to −3%) ✓ | 4,745 | 10,249 | 80% |
| 10 | Segments, bottom-up, no visitor trend | 5 | refresh | no | 6,009 | 4,422 | −28% (−50% to −2%) ✓ | 4,798 | 10,141 | 75% |
| 11 | Segments, top-down, no visitor trend | 5 | refresh | no | 6,018 | 4,413 | −27% (−50% to −2%) ✓ | 4,793 | 10,185 | 75% |
| 12 | Segments, top-down, half visitor trend | 5 | refresh | no | 6,026 | 4,413 | −27% (−50% to −2%) ✓ | 4,776 | 10,255 | 82% |
| 13 | Segments, top-down, full visitor trend | 5 | refresh | no | 6,039 | 4,416 | −27% (−49% to −3%) ✓ | 4,765 | 10,328 | 80% |
| 14 | EL + 2023–24 seasonal pattern | 4 | fixed | yes | 6,126 | 4,808 | −26% (−38% to −16%) ✓ | 6,155 | 5,972 | 85% |
| 15 | EL2A + 2023–24 seasonal pattern | 4 | refresh | no | 6,665 | 4,759 | −20% (−49% to +14%) | 4,810 | 12,367 | 77% |
| 16 | EL2A + long-weekend & holiday flags | 4 | refresh | yes | 6,823 | 4,843 | −18% (−49% to +19%) | 4,761 | 12,975 | 74% |
| 17 | EL2A + within-1-day-of-holiday flag | 4 | refresh | no | 6,839 | 4,853 | −18% (−48% to +19%) | 4,794 | 12,966 | 72% |
| 18 | EL2 + 28-day anchor (EL2A) | 3 | refresh | yes | 6,842 | 4,849 | −18% (−48% to +19%) | 4,793 | 12,975 | 72% |
| 19 | EL2A + holiday closeness kernel | 4 | refresh | no | 6,842 | 4,848 | −18% (−48% to +19%) | 4,793 | 12,978 | 72% |
| 20 | EL2A + city visitor trend (YoY) | 4 | refresh | no | 6,864 | 4,838 | −17% (−48% to +19%) | 4,750 | 13,126 | 77% |
| 21 | EL + recent level + payday | 2 | fixed | yes | 6,908 | 5,497 | −17% (−29% to −6%) ✓ | 6,977 | 6,547 | 70% |
| 22 | **B1 weekday mean (baseline)** | 0 | fixed | yes | 8,299 | 6,699 | — | 7,737 | 10,714 | 77% |
| 23 | B0 constant mean | 0 | fixed | yes | 23,950 | 20,853 | +189% (+148% to +240%) | 22,659 | 29,675 | 82% |

## What the rankings say

- **EL is the best model picked in advance.** The four models above it were chosen after seeing May–Jun, and they beat it by 0–2%, which is within noise.
- **The weekly-refresh models are best on ordinary days but worst on events.** Their ordinary-day RMSE is about $4,750–4,810, against $5,338 for EL. But they over-forecast Locals Week by about 10%, because they applied a promotion lift to an event that mostly drew locals.
  - EL looks better that week by luck. The event was announced after its Apr 30 forecast, so EL treated it as an ordinary week.
  - The segment models (ranks 8–13) remove part of that overshoot.
- **Adding outside or calendar information didn't help.**
  - Holiday flags move error by ±2%.
  - The 2023–24 seasonal pattern made the forecast worse, because 2025's June decline was a one-off tourism slowdown that earlier years didn't show.
- **Every model over-forecasts** (by $2–5K a day), because demand fell in June. Locals' play stayed flat; out-of-town visitors' play fell 6–11%.
- **Weather doesn't explain the decline.**
  - Ordinary heat has no effect on play. Days of 40°C or more had about 3.5% less play, but that accounts for about 1 point of June's ~5% shortfall at most.
  - Rain lowers locals' play by about 18%, which explains EL's worst ordinary-day misses (May 5–6).
  - Even a perfect weather forecast would cut EL's error by only about 5%.
  - Details in `WEATHER_NOTE.md`.

## Other models tried

These were scored on MAE only, all in `outputs/model_leaderboard_forecast.csv`:
- **Phase 2:** OLS, ETS, SARIMAX, structural, LightGBM, Bayesian ridge, ensemble.
- **Iteration 2:** about 30 variants, including AutoARIMA, AutoETS, Theta, MSTL, Prophet, XGBoost and CatBoost (direct), bottom-up by zone, and combinations.

None beat EL in a way we could trust. Averaging EL with EL2A was also checked: it lost in Jan–Apr validation.

## Caveats

- **One test window.** 61 days, with one unusual event week and one unusual month. Treat differences of a few percent as ties.
- **Ranges are too narrow.** EL's 90% ranges caught 75% of days.
- **Near the limit for this data.** The models' ordinary-day error is within 15% of what EL achieves when it is allowed to see all of Jan–Jun. Further gains would need new information, such as hotel bookings, not more modelling.
- **Next test.** Planned for July: EL2A (main) vs the segment model (challenger), with the decision rule written down in advance (`experiments/iter5/JULY_PLAN.md`).

**Details:**
- `models.md`: the full write-up. Iteration 1 is covered there; its code is in `experiments/ds_alpha/`.
- `experiments/iter2`–`iter5/README.md`: one per iteration.
- `experiments/iter5/table_vs_b1.csv`: the table above.
