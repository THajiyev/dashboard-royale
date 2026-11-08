# July 2025 test protocol (pre-registered)

The first clean out-of-sample test. This protocol was fixed before any July data was available, and nothing in it changes after July data arrives.

## Models

| Role | Model | Code |
|---|---|---|
| **Main** | EL2 + 28-day anchor, weekly refresh (k_ev = 0.5) | `iter3.models.make_el2(1.0, 28, 0.5)` |
| **Challenger** | Segments, bottom-up, β = 0.5, weekly refresh | `iter5.models.make_seg("bottom_up", 0.5)` |
| Reference only (cannot win) | EL, fixed forecast, and B2 | `iter2.models.EL`, `forecast.m_b2` |

The challenger is the iteration 5 pre-registered pick. It missed the win rule on May–Jun only on the CI criterion, so July decides.

## Forecasts

- **Origins:** weekly refresh at Jun 25, Jul 2, 9, 16 and 23, plus Jul 30 for the final day. Each origin forecasts the next 7 days and uses only data dated on or before the origin, and events announced by then.
- **Freezing:** each week's forecasts are saved by the dashboard at the origin (`outputs/july_forecasts/<origin>.csv`) before that week is played. Scoring reads only these saved files.
- **Settings:** the models and their settings are frozen at commit `624ad20` and its iteration 5 follow-up. No refit of any hyperparameter.

## Metrics

Scored on daily theo, Jul 1–31 (31 days).
- **Main metric: RMSE.**
- Also reported: MAE, WAPE, bias, ordinary-day and event-day RMSE, 90% band coverage, and interval score.
- **Event days:** days inside an event in `events.parquet` announced by the forecast origin.
- **Holiday window:** Jul 3–6 (Independence Day is a Friday). It is reported separately but is not an event unless listed.

## Decision rule (same as iteration 5)

**Switch to the challenger only if all three hold:**
1. Its July RMSE is lower than the main model's.
2. The 95% moving-block bootstrap CI on the RMSE ratio (7-day blocks, 2,000 resamples, seed 0) excludes zero.
3. Its ordinary-day RMSE is no worse.

**Otherwise, keep the main model.**

**Low power.** With 31 days, a 12% gap had a CI reaching +1% even over 61 days, so July alone will probably be inconclusive. If it is:
- Continue the same frozen forecasts through August.
- Apply the same rule to Jul 1 – Aug 31 (62 days), pooled.
- That is the final decision. There is no further extension.

## Dates

| What | When |
|---|---|
| Last July gaming day | 2025-07-31 |
| **Dashboard runs the July scoring** | **2025-08-01**, once the Jul 31 gaming day is loaded (data lands about 13 hours after the gaming day) |
| Pooled Jul–Aug decision, if needed | 2025-09-01 |

## Reported regardless of outcome

- The table above for both models, plus the two references.
- The CI.
- The decision.
- Any deviation from this protocol, such as late data or a missed origin.
