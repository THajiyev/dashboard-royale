# Phases 1–4: models, validation and what they decide

Run with `python analysis/run_models.py` (about 20 s; needs the Phase 0 outputs, so run `run_phase0.py` first).
All models fit on **Jan 1 – Apr 30 2025** and are scored once on **May 1 – Jun 30**. Inputs are only what was known on Apr 30.
Outputs are `outputs/model_*.csv`; the master table is `outputs/model_comparison.csv`.

Libraries: numpy, pandas, scipy, statsmodels, scikit-learn, lightgbm (`requirements-analysis.txt`).
The plan's PyMC, Prophet, MAPIE, SHAP and CausalImpact packages weren't installed, so each is replaced by an equivalent from those libraries:

| Planned | Used instead |
|---|---|
| PyMC / Bambi | Empirical-Bayes shrinkage, statsmodels mixed model, BayesianRidge |
| MAPIE | Split-conformal intervals from rolling-origin CV residuals |
| SHAP | LightGBM `pred_contrib`, which gives TreeSHAP values |
| CausalImpact | statsmodels structural time series with control-zone regressors, simulated counterfactual paths |

## Headline answers

| Question | Answer | Evidence |
|---|---|---|
| Is anything in the GM's bottom 10 a bad *machine*? | **No.** Once location and game are accounted for, machines differ by only τ ≈ 1.7%. None of the 10 has a credibly negative machine effect. | Phase 3 |
| What makes them low? | **Location** (9 of 10 in Back Forty; their banks sit 22–38% below an average spot) and **low-edge games** (Royal Draw holds 5% vs the fleet's 9.5%) | Phase 3, SHAP: location 60%, game 21% of explained variation |
| Does location really cause it? | **Yes.** Closing the walkway from the main entrance cut Back Forty's coin-in per hour by **31%** (90% CI 29–32%) and it recovered on reopening. That cost ≈ **$136K** of expected revenue in 35 days (90% CI $114K–$159K). Placebo zones moved by −2% to +3%. | Phase 4a |
| Leak? | **M-1158 only.** Payout-rate z = +124, the only machine flagged after Benjamini–Hochberg correction. Hold was 3.0% vs a 10% configuration, outside the 99% band, and the deficit is spread evenly across days. | Phase 1 |
| Luck? | Mostly noise. 24 machines have raw p < 0.05 against about 16 expected by chance; BH flags only M-1158. CUSUM alarms (6 on luck, 4 on payout rate) sit near the ≈ 3.9 expected under fair play. M-5076's whole deficit is one jackpot day. | Phase 1 |
| Downtime? | It's real (≈ $102K theo over 6 months) but **not** why these 10 are low. An extra technician recovers only $1.8–2.8K of theo per 30 days against an $11.5K cost. | Phase 4b |

## Phase 1 — Luck engine (`luck.luck_engine`, `outputs/model_luck_engine.csv`)

Per machine, adding to Phase 0:
- a 99% hold band;
- BH q-values for both luck and payout rate;
- volatility index (1.645·√payout variance);
- jackpot share: the worst day's luck as a share of the total deficit;
- two-sided monthly CUSUM (k = 0.5, h = 4) on luck z and payout-rate z.

**Calibration:**
- Monthly luck z has SD 1.003 and monthly payout-rate z has SD 1.012 (excluding M-1158).
- The CUSUM false-alarm rate comes from 200 simulated fair floors.

M-1158's CUSUM alarms in January, its first month, so the mismatch predates the data.

## Phase 2 — Daily forecast (`forecast.py`)

The CV-chosen model is the best non-baseline on rolling-origin CV inside Jan–Apr. Skill is improvement over B1.

| Model | Stack | CV MAE (Jan–Apr) | **Holdout MAE** | Bias/day | Skill vs B1 | 90% coverage |
|---|---|---:|---:|---:|---:|---:|
| **B2 event-aware weekday** | baseline | $5.5K | **$4.46K** | +$2.0K | **+33%** | 93% |
| OLS log (weekday + event + holiday) | lightweight | $5.4K | $4.78K | +$2.2K | +29% | 90% |
| Regression with AR(1) errors | lightweight | $6.2K | $4.79K | +$2.4K | +29% | 90% |
| Structural (local level + regressors) | lightweight | $7.7K | $5.12K | +$3.3K | +24% | 98% |
| ETS weekly, event-adjusted | lightweight | $7.8K | $5.23K | +$3.3K | +22% | 98% |
| Ensemble (top 3 by CV) | ensemble | — | $5.35K | +$2.9K | +20% | 90% |
| LightGBM (calendar) ← CV choice | ML | $5.1K | $5.83K | +$4.0K | +13% | 87% |
| ETS weekly (multiplicative) | lightweight | $5.7K | $5.92K | +$2.5K | +12% | 92% |
| Bayesian ridge (log, trend) | Bayesian | $6.8K | $6.25K | +$5.0K | +7% | 95% |
| B1 weekday mean (frozen benchmark) | baseline | $4.8K | $6.70K | +$4.0K | 0% | 84% |
| B0 constant mean | baseline | $20.0K | $20.9K | +$3.0K | −211% | 84% |

Coin-in tells the same story (`model_comparison.csv`).

- **The honest result is that no model beats the simple event-aware baseline.** The pre-registered CV choice (LightGBM) came 7th on the holdout. Two CV folds of 30–61 days are too noisy to pick between models whose errors differ by about $500/day.
- Every model over-forecasts June by 2–4%. Phase 0 and the zone panel both show a floor-wide June softening that no Jan–Apr input predicts.
- Intervals: split-conformal 90% bands cover 87–98% of holdout days, so they are honest or slightly wide.
- **Decision use:** `model_july_theo_counterfactual.csv` is the "no action" yardstick for July. It uses OLS-log refit on Jan–Jun: the best model on the holdout after B2, with a holiday term for Jul 4. It predicts $3.78M of theo over 30 days, or **$3.63M anchored to June's level (×0.959)**. Use the anchored version.

## Iteration 1 — event-type lift (current best forecast)

`forecast.event_type_lift()`, found by the multi-agent search in `analysis/experiments/`.

**How it works.** It keeps B2's non-event weekday base, but replaces the single pooled event lift with a hierarchy:

| Level | Lift (Jan–Apr) |
|---|---|
| Pooled | 1.10 |
| Business events (conventions) | 1.03 |
| Leisure events: sports viewing | 1.20 |
| Leisure events: property promotion | 1.17 |

The classes were fixed in advance by visitor purpose. Each level is shrunk toward the one above with a pseudo-count of 3 days. An event type never seen in training gets its class lift; on the holdout that is EDC, a festival, which gets the leisure lift of ≈ 1.17.

**Results.** The skill column is the improvement over B2.

| Target | Holdout MAE | B2 | Skill vs B2 | DM p vs B2 | 7-fold CV MAE (B2) | CV folds won |
|---|---:|---:|---:|---:|---:|---:|
| Theo | **$4,290** | $4,460 | +3.8% | 0.23 | $4,027 ($5,443) | 6 of 7 |
| Coin-in | **$44,912** | $46,671 | +3.8% | 0.23 | $44,888 ($59,613) | 6 of 7 |
| House win | $9,254 | $8,865 | −4.4% | 0.87 | $8,604 ($9,642) | 6 of 7 |

**How to read it:**
- **Leakage.** None found. The model uses training actuals and events announced by each origin only, and the coordinator audited and reproduced it.
- **What the win rests on.** The 3 EDC days (May 16–18) are the only holdout days where it differs from B2. It beats B2 for any EDC lift between ≈ 1.11 and 1.19. That is why the gain is not statistically significant on 61 days.
- **Independent support.** Jan–Apr CV supports the business/leisure split without touching May–Jun.
- **Disclosed contamination.** The search brief mentioned B2's EDC under-forecast, which is holdout knowledge, so the search was pointed at event days.
- **House win** is worse because luck dominates it; the forecast target is theo.
- **Holdout budget.** This was 1 of 6 allowed submissions (`analysis/experiments/leaderboard_ds-alpha.jsonl`). ds-beta's robust, recency and median-loss variants lost to B2 in CV and were not submitted (`analysis/experiments/ds_beta/`).
- **Still open.** The June over-forecast (+$2.5K/day) remains. Nothing observable by Apr 30 (trips, enrollments, entrance counts, carded share) signals it.

**Decision use.** Leisure events lift play ≈ 6× more than conventions (+17–20% vs +3%). That is the evidence base for valuing A-PROMO (property promotion weekend, ≈ 1.17 lift in training). It also argues against timing actions around conventions.

## Phase 3 — Location-adjusted machine model (`machine_effects.py`)

Target: coin-in per available hour, with log link and an offset of log(hours).

| Model (May–Jun coin-in per available hour) | MAE | Persistence ρ |
|---|---:|---:|
| Z0 zone mean (Phase 0) | $53.1 | — |
| M0 machine's own mean (Phase 0) | $46.7 | — |
| **GLM: bank + theme + calendar + closure** | **$38.2** | — |
| GLM + shrunk machine effect | $38.2 | 0.27 |
| LightGBM (location, game, calendar; no machine identity) | $39.7 | — |
| LightGBM + shrunk machine effect | $39.6 | 0.15 |

- **Location plus game beats each machine's own history by 18%.** A machine's past is a worse guide than where it sits and what it plays.
- Machine effects are small (τ = 1.7%) and only weakly persistent (Spearman 0.27). The mixed model's machine variance sits near zero (a boundary warning). Five machines are credibly negative, at −2% to −3%, and none is in the bottom 10.
- **Swap simulator (new, `model_swap_simulation.csv`):** keeps the slot and changes only the title. The large "gains" (+$170–245 theo/day by switching to Jackpot Summit) come almost entirely from a 12% vs 5% hold. That is *more player loss*, not more play. Treat them with caution:
  - the intervals cover parameter uncertainty only;
  - the theme effects are cross-sectional, not causal;
  - the GUIDE asks us not to design ideas that push losers to gamble more.
  
  Present this as a tradeoff, not a recommendation.

## Phase 4a — Walkway closure (`causal.py`)

- **DiD:** gap between Back Forty and 5 control zones, with weekday controls and HAC SE. The High-Limit Room is excluded as a different clientele.
  - Closed: **−30.9%** (90% CI −32.3% to −29.4%).
  - After reopening: −2.8%.
  - Pre-trend: −1.8% per 30 days (p = 0.08). A mild drift worth disclosing; it also shows in weeks +9 to +17 (`model_closure_event_study.csv`).
- **Structural counterfactual:** −28.2% (90% CI −31% to −25%), ≈ $136K theo lost.
- **Placebo:** using each control zone as the fake treated zone gives −1.8% to +3.3%. Back Forty's −31% is far outside that range.
- **What it means:** access, not the machines, drives Back Forty. That is the evidence base for A-WAYFINDING and A-MOVE.

## Phase 4b — Faults and repair capacity (`downtime.py`)

- **Fault rate, NB GLM:**

  | Factor | Fault rate ratio (95% CI) |
  |---|---|
  | Ridgeline vs Halcyon | **4.2×** (3.5–5.1) |
  | Northwind vs Halcyon | 1.6× (1.3–2.0) |
  | Each year of machine age | +5.5% |
  | Low/medium volatility vs high | +40% |

  May–Jun MAE per machine: NB 0.94, manufacturer rate 0.95, fleet rate 1.05.
- **Repair-queue replay (new):** replays all 1,207 faults through the actual technician roster.
  - It reproduces the observed waits exactly (mean 1.14 h; grave shift 1.96 h vs about 0.9 h on day and swing), so the mechanism is validated.
  - +1 technician saves 515–674 down hours over 6 months. That is only **$1.8–2.8K of theo per 30 days vs $11.5K cost**, because most downtime is fix time (2.9 h), not waiting (1.1 h).
- **Preventive break-even:** a Ridgeline sweep (≈ $9.7K including its own downtime) pays back in 30 days if it cuts Ridgeline faults by **≥ 32%**. Halcyon would need 99%, and Northwind 70%.

## Measurement plan (`model_measurement_plan.csv`; 80% power, α = 0.05, 30 days)

| Action | Metric | Detectable effect | Break-even |
|---|---|---:|---:|
| Any floor-wide action | daily theo vs the July counterfactual | 4.7% | — |
| A-WAYFINDING, Back Forty | Back Forty vs control-zone gap | **3.6%** | 1.9% |
| A-PREVENTIVE, Ridgeline | Ridgeline fault rate vs Jan–Jun | 25% reduction | 32% |

Wayfinding can pay for itself below the detectable effect, so it needs the zone-gap design (not a floor-wide before/after) to be measurable. A Ridgeline sweep that pays back would also be detectable.

## Bottom-10 verdicts (`model_bottom10_classification.csv`)

| Machine | Verdict | Action |
|---|---|---|
| M-1158 | **Leak** + location | **A-INSPECT** before anything else |
| M-1118 | Short exposure (rank 176 of 310 per hour) | Keep |
| M-5076 | Location + low-edge game + short exposure + one-jackpot luck | Don't replace like-for-like |
| M-1120, M-1238, M-1035, M-1017 | Location + low-edge game (Royal Draw) | Don't replace like-for-like |
| M-1181 | Location + luck (z −2.4, not significant after BH) | Don't replace like-for-like |
| M-1179, M-1265 | Location | Don't replace like-for-like |

"At an average spot" uplifts (+$53–109 theo/day each) are per machine. A move into an occupied slot displaces another machine, so the net gain is smaller unless the slot is empty.

## Limitations

- **Small samples.** The event lift and the CV each rest on only 26 event days and two folds.
- **Theme effects** in the GLM are cross-sectional. High-Limit is excluded from the location verdict because its game exists only there.
- **Fault-rate inference.** Manufacturer and age are observational. The replay is mechanistic but assumes one tech per job and no travel time.
- **The data is synthetic.** The queue replay matching exactly suggests the simulator and the data generator share the same queue logic; real data would be noisier.

## Iteration 2 — wider model search (no new winner)

Full write-up: `analysis/experiments/iter2/README.md`. We tested 30 models against EL with the same harness:

- **Classical TS:** AutoETS, AutoARIMA, AutoTheta and MSTL on the event-adjusted series.
- **Prophet:** flat and linear growth.
- **Boosting:** CatBoost and XGBoost, fitted directly and on EL's residuals.
- **EL refinements:** holiday term, level shifts for the closure and the 308 machines, recency weighting, recent-level rescaling, median base, payday term.
- **Bottom-up:** by zone, and coin-in × theo-hold.
- **Combinations** of the above.

**Holdout submissions (3 of 3, chosen in advance by CV):**

| Submission | Holdout theo MAE |
|---|---:|
| EL + recent level + payday | $5,497 |
| 3-way combo (EL-level28, AutoTheta, Prophet-linear) | $5,810 |
| AutoTheta | $5,704 |
| *EL (reference)* | *$4,290* |

All three lost. Each tracks the level that rose through Jan–Apr, and that rise reversed in May–Jun. Across the 30 models, **CV rank and holdout rank are negatively correlated (Spearman −0.42, p = 0.02)**, so Jan–Apr CV can't choose between level assumptions here.

Scoring every model afterwards (a diagnostic only), a few beat EL by 1–3%:

| Model | vs EL | DM p | Caveat |
|---|---:|---:|---|
| EL × CatBoost residual | +3.2% | 0.19 | lost CV |
| EL coin-in × recent theo-hold | +2.9% | 0.02 | in effect ×0.997 on theo |
| EL, median base | +1.7% | — | |
| EL + holiday term | +0.9% | — | |

None is adopted without a fresh test window. **EL remains the current best.**

## Iteration 3 — weekly refresh and zone-structural model (new recommendation)

Full write-up: `analysis/experiments/iter3/README.md`.

**Recommendation: refresh the forecast weekly, anchor the level to the last 28 non-event days, and count event evidence per event (EL2).** The 28-day window, the anchor weight and the shrinkage were all chosen on Jan–Apr refresh CV.

| Theo, May–Jun | MAE, all 61 days | MAE, ordinary days (excl. Locals week) | Bias ex-Locals | Bias, last 2 weeks |
|---|---:|---:|---:|---:|
| Fixed EL (previous best) | **$4,290** | $4,249 | +$3,315 | +$5,786 |
| Weekly-refresh EL2 + anchor | $4,849 | **$3,677 (−13%)** | **+$2,324** | **+$2,296** |

**Ordinary days.** The refreshed model is more accurate and follows the April–June decline within weeks.

**Over all 61 days it loses**, because of the Locals Appreciation Week (Jun 9–15). The promotion was announced May 26, so only the refreshed model knows about it. It gets the +18% lift learned from the Winter Slot Tournament, but its actual lift was about +3–8%. No Jan–Apr evidence predicts this; a weekend-vs-weekday explanation was tested on the training data and refuted. Show novel event formats as a range, not as one lift.

**Zone-structural model (ZS).** It models theo per machine per zone, so the 8 new Pit machines count as capacity, and it excludes the closure window. That gives the correct Apr 30 level, 2% above EL, and it does worse on the holdout ($5,950). EL's fixed-horizon lead is partly offsetting errors: the closure dragged its average down just before demand declined.
