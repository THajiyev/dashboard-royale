# Phase 0 baselines

The simplest benchmarks every model must beat. Fit on **Jan 1 – Apr 30 2025**, scored on **May 1 – Jun 30 2025**.
Run with `python analysis/run_phase0.py`; results are written to `outputs/phase0_*.csv`.

## How each baseline is calculated

| Baseline | Calculation | Plain English |
|---|---|---|
| **B0: constant mean** | Average daily value from Jan–Apr, used for every May–Jun day | "Every day will look like an average day" |
| **B1: weekday mean** | Average daily value per weekday from Jan–Apr, used for the same weekday in May–Jun | "Every Saturday will look like an average Saturday" |
| **B2: event-aware weekday** | Weekday mean from Jan–Apr *non-event* days × one pooled event lift (≈1.10, from the 26 Jan–Apr event days) on days with an event announced by Apr 30 | "An ordinary Saturday looks like an ordinary Saturday; a known event day is ~10% busier" |
| **Z0: zone rate** | Σ coin-in ÷ Σ available hours for the machine's zone in Jan–Apr | "A machine earns what its area of the floor earns per hour" |
| **M0: machine rate** | Σ coin-in ÷ Σ available hours for that machine in Jan–Apr (zone rate for machines installed later) | "A machine keeps earning what it earned before" |
| **Downtime lost play** | Hours down × the machine's own (Σ theo ÷ Σ available hours); hour-aware version also × the zone's busy-ness index for that local hour and day type (`machine_hour`) | "Each broken hour cost what that hour usually earns" |
| **Luck $** | Σ house win − Σ theo | "Actual win minus what the game math expected" |
| **Luck z** | Luck $ ÷ √(Σ bet² × payout variance) | "How unusual the result is; beyond ±2 is rare for a fair machine" |
| **Hit z** | (winning spins − spins × hit probability) ÷ √(spins × p × (1−p)) | "Is it paying out as often as it's configured to? A huge value points to a payout mismatch" |

Forecasts are scored with **MAE**: the mean absolute gap between forecast and actual, in dollars (lower is better). The luck metrics need no training; they come straight from the game math.

## Results

### Daily property forecasts (May–Jun holdout, 61 days)

| Target | B0 constant mean | B1 weekday mean | B2 event-aware weekday | B2 vs B1 |
|---|---:|---:|---:|---:|
| Expected revenue (theo) | MAE $20.9K (16.6%) | MAE $6.7K (5.2%) | **MAE $4.5K (3.6%)** | −33% |
| Coin-in | MAE $218K (16.4%) | MAE $69K (5.0%) | **MAE $47K (3.6%)** | −32% |
| House win | MAE $22.1K (17.9%) | MAE $10.2K (8.3%) | **MAE $8.9K (7.4%)** | −13% |

- Weekday is the dominant pattern. **B1 is the frozen benchmark** (GUIDE §7); B2 was added after a review of B1's residuals, so it is a stronger baseline, not an untouched holdout result.
- B1's over-forecast is mostly an **event artefact, not a trend**: 26 of the 120 training days had events (lift 1.01–1.22), inflating every weekday mean. B1 over-forecasts ordinary May–Jun days by ~$60K coin-in/day yet under-forecasts the EDC weekend by ~$179K/day. Removing event days and adding one event lift cuts the bias from $39K to $18K/day.
- **Leakage trap:** the Locals Appreciation Week (Jun 9–15) was announced on May 26, after the Apr 30 forecast date, so B2 treats it as an ordinary week. Check `announced_date` before using any event as an input.
- What's left is a real June softening (B2 over-forecasts June by ~2.3% vs ~0.4% in May). It shows up in every zone's coin-in per hour, so it's floor-wide demand, not individual machines. Nothing in Jan–Apr predicts it.
- House win gains least because luck can't be forecast. That's why the model target is theo.

### Machine coin-in per available hour (May–Jun machine-days)

| Baseline | MAE |
|---|---:|
| Z0 zone rate | $53.1 / hour |
| **M0 machine rate** | **$46.7 / hour** |

Both over-forecast by $8–10/hour: the same floor-wide June softening. Unweighted and hours-weighted MAE are identical (95% of machine-days have 24 available hours), so averaging daily ratios does no harm here.

### Luck

- Daily luck z over all machine-days: mean −0.01, SD 1.04, **but skew −2.5 and median +0.20**. On most days the house wins a bit more than theo; occasional jackpots pull it far below. So mean and SD match the theory, but the shape isn't normal: **don't read a single day's z against ±2**. Machine-level z, summed over months of spins, is close enough to normal to use.
- 20 of 310 machines have |luck z| > 2; about 14 are expected by chance (binomial p = 0.08), so most "unlucky" flags are noise.
- Hit-rate z has SD 1.006 across the other 309 machines, so the test is well calibrated, and M-1158's +124 is not a modelling artefact.

### The GM's bottom 10 (lowest house win)

| Read | Machines |
|---|---|
Machines are judged on **theo per available hour** (free of both luck and exposure). Reasons can overlap, so each machine gets every one that applies.

| Read | Machines |
|---|---|
| Payout mismatch → inspect | M-1158 (hit z +124, luck z −4.6; theo/hr rank 46 of 310, so the game itself is fine) |
| Short exposure only (earns well per hour) | M-1118 (55 days, theo/hr rank 176, High-Limit Room) |
| Low theo/hr **and** short exposure | M-5076 (49 days, rank 2), M-1120 (132 days, rank 1) |
| Low theo/hr + unlucky | M-1181 (rank 6, luck z −2.4) |
| Low theo/hr | M-1238, M-1035, M-1179, M-1017, M-1265 |

8 of the GM's 10 are in the bottom 10 by theo per hour; the luck-free bottom 10 swaps in M-1048 and M-1162 for M-1158 and M-1118.
9 of the 10 sit in **Back Forty**, the lowest-traffic zone, and the low-theo machines are mostly the lowest-edge games (Royal Draw, Comet Cash).

*Correction:* the earlier version ranked on total theo, which still penalises short exposure. That marked M-1118 as "bottom 10 by theo" (rank 3) even though it ranks 176 per hour, and it hid that M-5076 and M-1120 are low earners per hour, not just new.

### Downtime

Lost expected revenue ≈ **$102K** over six months (≈ $1.10M coin-in) once each down hour is valued at that hour's usual busy-ness: Ridgeline $56K, Northwind $26K, Halcyon $20K.
The flat-rate figure ($90K) understated it by ~13%, because down hours cluster in the evening (9 pm–2 am, 5 of 24 hours, holds ~29% of all down hours).
Treat $102K as an **upper bound**: on a floor that isn't full, some displaced players move to a nearby machine, and that play isn't lost.
