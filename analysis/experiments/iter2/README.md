# Iteration 2: a wider model search against the event-type lift

**Result: no model beats Iteration 1 (EL, theo holdout MAE $4,290) in a way we can trust.** The three
models chosen in advance by CV all lost badly on May–Jun. A few models came out slightly ahead when we
scored everything afterwards, but none of those would have been picked by CV, and the gaps are within noise.

Extra libraries: `statsforecast`, `prophet`, `catboost`, `xgboost` (on top of `requirements-analysis.txt`).

| File | What it does |
|---|---|
| `models.py` | 30 candidate models, all built on the harness contract `f(train, future, target)` |
| `run_cv.py` | 7-fold rolling-origin CV inside Jan–Apr → `cv_results*.csv`, `cv_folds*.csv` |
| `submit.py` | the 3 holdout submissions chosen in advance → `../leaderboard_iter2.jsonl` (3 of 3 used) |
| `posthoc_holdout.py` | scores every model on May–Jun after the submissions → `posthoc_holdout.csv` (a diagnostic, not used to choose) |

## What was tried

| Family | Models | Idea |
|---|---|---|
| EL refinements | holiday term; level shifts for the walkway closure and the move from 300 to 308 machines; recency-weighted base (half-life 28/56 d); weekday profile rescaled to the level of the last 14–56 days; median base; payday (day-of-month) term | Fix specific sources of base-level bias in EL |
| Classical TS | statsforecast AutoETS, AutoARIMA, AutoTheta, MSTL | Divide out EL's event lift, forecast the adjusted series, multiply the lift back in |
| Prophet | flat and linear growth, weekly seasonality | Same adjust → forecast → re-apply approach |
| Boosting | CatBoost / XGBoost fitted directly on calendar features plus the lift; CatBoost / XGBoost fitted to EL's log residuals | Use ML to pick up calendar effects EL misses |
| Bottom-up | EL per zone, summed; theo = EL(coin-in) × theo-hold of the last 28 days | Let each zone have its own profile and lift; let theo follow the current game mix |
| Combinations | equal-weight geometric means of 2–3 models | Forecast combination |

## Holdout submissions (chosen by CV before any holdout number was seen)

| Submission | Why it was chosen | CV MAE | Holdout theo MAE | vs EL | Bias/day |
|---|---|---:|---:|---:|---:|
| EL + recent level (28 d) + payday | best single model in CV | $3,617 | $5,497 | −28% | +$4,691 |
| Combo: EL-level28 + AutoTheta + Prophet-linear | best combination in CV | $3,647 | $5,810 | −35% | +$5,207 |
| AutoTheta on event-adjusted | best classical model in CV | $3,764 | $5,704 | −33% | +$5,119 |
| *EL (reference)* | | $4,027 | **$4,290** | — | +$2,501 |

**Why they lost.** The underlying level rose through Jan–Apr: the closure ended on Apr 6, 8 machines were
added on Mar 24, and April ran high. Models that follow the recent level (recency weights, level rescaling,
ETS/Theta/ARIMA, linear Prophet) therefore win CV inside Jan–Apr. In May–Jun the level fell about 2%, so
the same models over-forecast even more than EL does (bias rises from +$2.5K to +$4.4–5.9K a day).
Across all 30 models, **CV rank is negatively correlated with holdout rank (Spearman −0.42 on theo,
p = 0.02; −0.49 on coin-in).** That means Jan–Apr CV is not a reliable way to choose between level
assumptions on this data.

## Post-hoc holdout scores for every model (diagnostic only)

Theo, May–Jun. The DM p column is the one-sided Diebold–Mariano test against EL; low values favour the model.

| Model | CV7 MAE | Holdout MAE | vs EL | Bias/day | DM p |
|---|---:|---:|---:|---:|---:|
| EL × CatBoost residual (calendar) | $4,215 | $4,151 | +3.2% | +2,365 | 0.19 |
| EL coin-in × recent theo-hold | $3,999 | $4,163 | +2.9% | +2,188 | 0.02 |
| EL, median base | $4,096 | $4,216 | +1.7% | +2,511 | 0.29 |
| EL + holiday term | $4,022 | $4,253 | +0.9% | +2,524 | 0.19 |
| Prophet (flat) on event-adjusted | $4,084 | $4,262 | +0.6% | +2,471 | 0.31 |
| **EL (iteration 1, current best)** | $4,027 | **$4,290** | — | +2,501 | |
| EL × XGBoost residual (calendar) | $4,060 | $4,299 | −0.2% | +2,583 | 0.52 |
| EL bottom-up by zone | $4,022 | $4,306 | −0.4% | +2,501 | 0.86 |
| EL + payday (day-of-month) term | $3,908 | $4,358 | −1.6% | +2,592 | 0.76 |
| Combo: EL + bottom-up + structural | $4,036 | $4,565 | −6.4% | +3,145 | 1.00 |
| EL + recency-weighted base (hl 56d) | $3,974 | $4,606 | −7.4% | +3,144 | 1.00 |
| EL + recency-weighted base (hl 28d) | $3,944 | $4,965 | −15.7% | +3,717 | 1.00 |
| MSTL on event-adjusted | $4,178 | $5,045 | −17.6% | +4,072 | 1.00 |
| Combo: EL + AutoETS-adj | $4,018 | $5,088 | −18.6% | +4,114 | 1.00 |
| EL + recent-level rescale (56d) | $3,858 | $5,166 | −20.4% | +4,204 | 1.00 |
| CatBoost direct (calendar + lift) | $4,769 | $5,242 | −22.2% | +3,327 | 1.00 |
| EL + holiday + structural | $4,125 | $5,261 | −22.6% | +4,454 | 1.00 |
| Combo: EL + AutoTheta-adj + AutoETS-adj | $3,831 | $5,282 | −23.1% | +4,448 | 1.00 |
| EL + recent-level rescale (14d) | $3,683 | $5,292 | −23.4% | +4,385 | 1.00 |
| EL + structural shifts (closure, 308 machines) | $4,119 | $5,309 | −23.8% | +4,444 | 1.00 |
| EL + recent-level rescale (28d) | $3,674 | $5,439 | −26.8% | +4,599 | 1.00 |
| EL + recent-level (28d) + payday | $3,617 | $5,497 | −28.1% | +4,691 | 1.00 |
| AutoARIMA on event-adjusted | $3,928 | $5,529 | −28.9% | +4,718 | 1.00 |
| EL + recent-level rescale (42d) | $3,816 | $5,530 | −28.9% | +4,728 | 1.00 |
| Combo: EL-level28 + AutoTheta-adj | $3,661 | $5,564 | −29.7% | +4,858 | 1.00 |
| AutoTheta on event-adjusted | $3,764 | $5,704 | −33.0% | +5,119 | 1.00 |
| Combo: EL-level28 + AutoTheta-adj + Prophet-lin-adj | $3,647 | $5,810 | −35.4% | +5,207 | 1.00 |
| AutoETS on event-adjusted | $4,044 | $6,172 | −43.9% | +5,748 | 1.00 |
| Prophet (linear) on event-adjusted | $3,728 | $6,380 | −48.7% | +5,908 | 1.00 |
| XGBoost direct (calendar + lift) | $5,660 | $7,727 | −80.1% | +5,532 | 1.00 |

Coin-in tells the same story (`posthoc_holdout.csv`).

**Reading the post-hoc winners.** None of them should replace EL yet:

- **CatBoost residual** lost CV by 5% and won no CV folds against EL. Its holdout gain is not significant (p = 0.19).
- **Coin-in × recent theo-hold** is the most defensible. It wins 6 of 7 CV folds (+0.7%), and its holdout gain is significant (p = 0.02). In practice, though, it only scales theo by the hold of the last 28 days relative to the Jan–Apr hold (9.44% vs 9.47%, ×0.997). It cuts the June over-forecast slightly; it is not a better model of demand.
- **Median base and holiday term** are +1–2% on the holdout and have mixed CV results.

These need a fresh test window (for example July 2025) before any of them is adopted. The `iter2` holdout
budget is used up, and submitting under a new agent name would get around the cap.

## Takeaways

1. **EL stays the current best forecast.** We tested 30 models from five families. None beats it by a margin that CV would have predicted.
2. **The level assumption matters more than the model class.** Holdout errors are driven by bias: every model over-forecasts June. Flexible models (ETS, ARIMA, Theta, Prophet, GBM) mostly change the level assumption, and with only Jan–Apr to learn from, they choose a worse one.
3. **ML is not competitive at n = 120 days.** XGBoost and CatBoost fitted directly come last. Boosting EL's residuals adds roughly nothing.
4. **Small, principled corrections are roughly neutral.** Holiday term, median base and bottom-up by zone each move MAE by ±2%.
5. **Fixing the June bias needs information we don't have on Apr 30.** Nothing observable by then signals it (see Iteration 1). The useful next step is a July test of EL, EL × theo-hold and EL + holiday, not more model search.
