# Iteration 6 pre-registration: a recent-demand adjustment on top of EL

Written before any iteration 6 variant was fitted or scored.

**Question.** Does multiplying EL's forecast by a factor that tracks recent demand improve daily theo forecasts?

**EL itself is not changed.** The model is `ds_alpha.models.make_typed(3, 3)`: the non-event weekday mean of all
training days, times the hierarchical event-type lift. Every variant here is `EL forecast × m`, where m is a single
factor (or one factor per weekday) computed from data dated on or before the origin.

## Status of the May–Jun result: confirmatory, not a clean holdout

- May–Jun has already been scored 8 times across earlier iterations (`leaderboard_*.jsonl`, `*/holdout_log.jsonl`).
- Close relatives of these variants have already been seen on it:
  - Iteration 2 tried a fixed-horizon rescale to the last 14, 28, 42 and 56 days at 100% strength. It won Jan–Apr CV
    and lost on May–Jun.
  - Iteration 3 tried weekly-refresh anchors (25–100%, over 7, 14 and 28 days). The 28-day, 100% anchor became EL2A.
- So the grid below was designed knowing roughly what a 28-day anchor does in May–Jun. To limit the damage:
  - the selection rule is fixed here and uses Jan–Apr only;
  - May–Jun is scored once, and that look is logged;
  - only the CV pick counts as "picked in advance".
- No clean test exists in this data (it ends Jun 30). July is the first one.

## The adjustment

For training day t, let e_t be EL's own in-sample fit (weekday base × the event lift for that day), and let
r_t = y_t / e_t be the ratio of actual theo to that fit.

**Recent statistic R:**

| Family | Values tried | Definition |
|---|---|---|
| `mean` | 7, 14, 28 days | mean of r_t over eligible days in the last L calendar days up to the origin |
| `ema` | half-life 7, 14, 28 days | weighted mean of r_t over every eligible day up to the origin, weight 0.5^(age/h) |
| `dow` | 28, 56 days | one R per weekday: mean r_t of eligible same-weekday days in the last L days, shrunk toward that window's all-day R with a pseudo-count of 2 days |

**Which days count ("event handling"):**

| Mode | Event days | Walkway closure (Mar 3 – Apr 6) |
|---|---|---|
| `excl` | dropped | kept |
| `excl_clo` | dropped | dropped. This is a known, planned operational disruption, not demand. |
| `delift` | kept, with r_t measured against base × lift | kept |
| `raw` | kept, with r_t measured against the base only (the lift is ignored) | kept. This is the naive version, shown to measure how much event spikes distort it. |

**Strength:** m = 1 + w·(R − 1), with w ∈ {0.25, 0.5, 0.75, 1.0}. The factor applies to every future day, event
days included.

**Fallback:** if fewer than 4 eligible days fall in the window (fewer than 2 per weekday for `dow`), R = 1, so there
is no adjustment.

The grid is 8 statistics × 4 modes × 4 strengths = **128 variants**, under each of two protocols.

## Protocols (same as iterations 3–5)

- **Fixed:** one forecast per origin for every day up to the end of the window.
  - CV origins: the 7 harness origins (Feb 28, Mar 7, 14, 21, 28, Apr 4, 11), each forecasting to Apr 30.
  - Holdout: Apr 30 → May 1 – Jun 30.
- **Refresh:** every 7 days, refit and forecast the next 7 days.
  - CV origins: Jan 31 + 7k through Apr 25 (13 weeks). The last week is Apr 26–30 (5 days). Iteration 5 stopped at
    Apr 18; this extends it by one week so all of Feb–Apr is scored.
  - Holdout origins: Apr 30 + 7k through Jun 25 (the same 61 days).

The references are refitted under each protocol: EL, and B1 (weekday mean of all training days).

## Selection rule (Jan–Apr only)

For each protocol separately:

1. **Pick** the variant with the lowest Jan–Apr CV RMSE on daily theo.
2. **Adopt in principle** only if the pick passes every one of these checks:
   - **(a) Size:** its CV RMSE is at least 3% below EL's under the same protocol.
   - **(b) Consistency:** it beats EL on most folds: at least 5 of 7 origins (fixed) or 9 of 13 weeks (refresh), judged by each fold's
     RMSE. Ties count as losses.
   - **(c) Not driven by the closure:** it still beats EL in CV when days from Mar 3 to Apr 13 (the closure plus one
     week) are left out of the scoring.
   - **(d) The selection procedure itself generalises inside Jan–Apr.**
     - Re-run step 1 on the early folds only (fixed: the 4 origins up to Mar 21; refresh: the 8 weeks with origins
       up to Mar 21).
     - That pick must then beat EL on the later folds, by RMSE pooled over them (fixed: the Mar 28, Apr 4 and
       Apr 11 origins; refresh: the 5 weeks with origins Mar 28 – Apr 25).
     - For the fixed protocol this check is weaker, because early and late origins forecast some of the same April
       days.
3. **Integrate into EL** only if the pick passes step 2 *and* the single May–Jun look confirms it. Confirming means
   both of these:
   - lower RMSE than EL under the same protocol, with the 95% block-bootstrap CI of the RMSE ratio below 1 (7-day
     blocks, 2,000 draws);
   - lower error than EL in both May and June.

If step 2 fails, the recommendation is not to integrate, whatever May–Jun shows.

## What is reported on May–Jun

- Every variant, all labelled post hoc except the two CV picks: MAE, RMSE, bias, and ordinary-day vs event-day
  error. Event days are the days of any event in the events table (EDC May 16–18; Locals Week Jun 9–15).
- Error by month and by week, and the number of weeks each variant beats EL.
- Error with the 5 worst days left out, and with Locals Week left out.
- The change in RMSE vs EL and vs B1, with block-bootstrap 95% CIs, plus a DM p-value vs EL.

## Amendment, written after stage 1 (Jan–Apr CV) and before the May–Jun look

**What the rule picked.** Under both protocols, the step-1 pick is a `raw` variant:

| Protocol | Rule pick | Gain vs EL in CV | Checks |
|---|---|---:|---|
| fixed | `ema hl28d [raw] w=50%` | 8.2% | passes (a)–(d) |
| refresh | `mean28d [raw] w=50%` | 3.6% | fails (d) |

**Why `raw` wins in Jan–Apr.** The diagnosis uses Jan–Apr only; the figures are from `cv_results.csv` and a per-origin
check of R.
- `raw`'s R is 1.02–1.04 at every fixed origin. The clean modes give 0.995–1.009. The difference is event spikes
  (Super Bowl, the tournament, March Madness, two conventions) leaking into the level.
- EL under-forecast Jan–Apr by 1.2–2.3%, because the level rose with the Mar 24 machine add and a strong April.
  Half of the leaked event share happens to cancel that.
- The gain also isn't monotone in strength. At 25–50% it helps by 5–8%; at 100% it is 8–36% worse than EL.
- So this is two errors cancelling, not a demand signal. There is no reason to expect it to work in May–Jun, where EL
  already over-forecasts.

**Amendment.**
- The rule pick stays on record and is reported exactly as pre-registered.
- A second pick is added, chosen the same way but only among variants that keep event days out of the level
  (`excl`, `excl_clo`, `delift`). Both picks count as picked in advance.
- **The recommendation will be based on the clean pick.** A `raw` variant will not be recommended whatever May–Jun
  shows, because its mechanism is known to be event leakage.

| Protocol | Clean pick | Gain vs EL in CV | Folds won | Checks |
|---|---|---:|---:|---|
| fixed | `mean14d [excl] w=100%` | 5.8% | 7/7 | passes (a)–(d) |
| refresh | `mean28d [delift] w=100%` | 3.4% | 10/13 | passes (a)–(d) |

**Caveats on the clean picks.**
- *Refresh pick.* This is essentially iteration 3's "EL + anchor 100% (28 d)", which has already been scored on
  May–Jun (MAE $4,850). Its result here is not new evidence.
- *Fixed pick.* Its `excl_clo` twin gains only 1.2% in CV. So part of its CV gain comes from closure days in the
  window, which pull the level down and then rebound. It still passes (c), which scores CV without closure-period
  days.
- *Fixed CV generally.* The level rose during Jan–Apr, so CV rewards anything that follows the recent level.
  Iteration 2 found the same and saw it reverse on May–Jun.
