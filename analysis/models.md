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
