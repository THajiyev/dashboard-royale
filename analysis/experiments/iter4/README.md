# Iteration 4: holiday proximity and prior-year patterns

**Result: neither idea improves the forecast enough to adopt.** Holiday features change error by ±1%. Prior-year
seasonality, the CV choice for the fixed forecast, is 12% *worse* on May–Jun. The one historical input that
points the right way is the city's year-over-year trend (+1.0% theo, +1.5% coin-in on the fixed forecast), and
that gain is not significant (DM p = 0.23). The iteration 3 recommendation stands.

| File | What it does |
|---|---|
| `hol_hist.py` | holiday calendar and features, holiday wrappers (ridge, GBM), historical city-level wrapper |
| `lvcva_history.csv` | Las Vegas visitors, occupancy and Strip gaming revenue for Jan–Jun 2023 and 2024, transcribed from the LVCVA monthly Executive Summaries (public before 2025) |
| `evaluate.py` | `cv` (Jan–Apr only) → `cv_results.csv`; `holdout` → `holdout_results.csv`, each look logged in `holdout_log.jsonl` (1 look) |

Both families wrap an existing base (EL for the fixed forecast, EL2 + 28-day anchor for the weekly refresh), so
any change is due to the new inputs alone.

## Holiday proximity

**Calendar.** Federal holidays (New Year, MLK, Presidents, Memorial, Juneteenth, July 4) plus Valentine's Day,
Easter, Mother's Day and Father's Day. These are fixed dates, so they are legal inputs at any origin.

**Features tried**, from the signed distance to the nearest holiday:

| Feature | Form |
|---|---|
| `day` | on a federal holiday (boolean) |
| `longwknd` | Fri–Mon of a Monday federal holiday (boolean) |
| `near1/2/3` | within 1, 2 or 3 days of a major holiday (boolean) |
| `kernel1/2/4` | closeness metric exp(−\|d\|/τ), separate before / on / after effects |
| `bins` | 1–3 days before, on the day, 1–3 days after |
| GBM | LightGBM on distance, \|distance\|, weekday and the flags |

Effects are ridge-regressed on the base model's training log residuals, shrunk toward zero (λ = 2, 5 or 20 pseudo-days).

**What the training data shows.** Holidays barely move play here. The fitted effects at Apr 30 are all within
±1.4% (long weekend +0.4 to +0.9%, holiday day −1.0 to −1.4%, within one day of a holiday −0.5 to −0.6%). Ordinary
day-to-day noise is ±3.2%. MLK weekend ran about +3% and Presidents Day weekend about 0%.

**Caveat on the evidence.** Jan–Apr has three federal holidays, and the fixed-protocol CV windows (Mar–Apr) contain
none, only Easter. Every holiday in the holdout (Memorial Day, Mother's Day, Juneteenth, Father's Day) is a
date with no training example.

## Prior-year patterns

The casino data starts on 2025-01-01, so "previous years" have to come from the city. The property's monthly
level tracks Las Vegas visitor volume closely (June: −3.7% at the property vs −5.0% city-wide, both against Jan–Apr).

| Visitors per day | Jan | Feb | Mar | Apr | May | Jun |
|---|---:|---:|---:|---:|---:|---:|
| 2023 | 105.7K | 110.1K | 117.9K | 112.9K | 112.8K | 114.3K |
| 2024 | 109.1K | 116.4K | 118.4K | 117.1K | 118.0K | 116.4K |
| 2025 | 107.8K | 106.2K | 109.3K | 111.2K | 110.3K | 103.2K |

Two ways to use it. Each divides the training series by a city index to the power β (the property's elasticity),
forecasts, then multiplies the index back in.
- **`seasonal`**: average 2023–24 monthly shape. It says May–Jun ≈ Mar–Apr, i.e. no summer dip.
- **`season_yoy`**: 2024 levels × the latest *published* 2025 YoY (month end + 30 days, so March's −7.8% on Apr 30).
  It carries the 2025 slowdown forward instead of a seasonal shape.

## Results

CV is Jan–Apr; skill is the change in MAE against the base of the same protocol (positive = better). Full CV grid in `cv_results.csv`.

| Protocol | Model | CV skill theo | Holdout theo MAE | Skill | Coin-in skill | DM p |
|---|---|---:|---:|---:|---:|---:|
| fixed | base (EL) | — | $4,290 | — | — | |
| fixed | **seasonal history, β 0.5 (CV pick)** | **+3.0%** | $4,808 | **−12.1%** | −10.9% | 1.00 |
| fixed | season + YoY trend, β 0.5 | +0.2% | $4,247 | +1.0% | +1.5% | 0.23 |
| fixed | long weekend + holiday day | 0.0% (no holidays in CV) | $4,261 | +0.7% | +0.4% | 0.18 |
| fixed | within 1 day of holiday | −3.0% | $4,239 | +1.2% | +0.1% | 0.14 |
| fixed | closeness kernel (τ 1) | −0.2% | $4,286 | +0.1% | +0.1% | 0.13 |
| refresh | base (EL2 + anchor) | — | $4,849 | — | — | |
| refresh | **long weekend + holiday day (CV pick)** | **+0.5%** | $4,843 | +0.1% | +0.1% | 0.42 |
| refresh | closeness kernel (τ 1) | −0.2% | $4,848 | 0.0% | 0.0% | 0.41 |
| refresh | season + YoY trend, β 0.5 | −4.5% | $4,838 | +0.2% | +0.3% | 0.42 |
| refresh | seasonal history, β 0.5 | −6.7% | $4,759 | +1.9% | +1.4% | 0.05 |

## How to read it

1. **Holidays are not where the forecast goes wrong.** On the holdout's holiday windows (Memorial Day weekend,
   Mother's Day, Juneteenth) the base already errs *less* than on an average day ($3,188 vs $4,290 a day, fixed).
   The holiday features shave about $175 a day off those windows, which is about 0.5% overall.
2. **Prior-year seasonality is the wrong history for 2025.** In 2023 and 2024 June was flat with April. 2025 ran
   6–11% below 2024 all spring, and June fell further. A seasonal prior raises May–Jun to the Mar–Apr level and
   makes the over-forecast worse. It won CV only because its Jan→Mar rise matches Jan–Apr, the same trap as iteration 2.
3. **The year-over-year trend is the useful history, but it is small.** Carrying the published YoY forward is the
   right direction (+1–1.5% on the fixed forecast), but the slump deepened after March (June YoY −11%), and that
   was not public until August.
4. **The refresh "seasonal" +1.9% (p = 0.05) is not adopted.** It lost Jan–Apr CV by 6.7%, so we would not have chosen it.

## For the dashboard

- Keep **EL2 + 28-day anchor, refreshed weekly** (iteration 3).
- Holiday flags can be shown for context, but don't adjust the forecast for them. No holiday in the data moved play by more than ~3%.
- The city's latest YoY visitor change is worth showing next to the forecast as an early-warning context line.
  It is the input that best explains the 2025 decline, but it arrives with a month's lag.
- A July test (Independence Day, a Friday) is the first chance to see a major holiday weekend out of sample.

## Holdout accounting

1 logged look (`holdout_log.jsonl`) at 12 models. They were chosen before the look: the CV pick per protocol and
family, plus the main alternatives. No model was added or tuned after the look.
