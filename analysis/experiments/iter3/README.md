# Iteration 3: keeping one-off disruptions out of the forecast

**Recommendation: refresh the forecast every week, with the level anchored to the last 28 days, and count event evidence per event (not per day).** On ordinary days it is the most accurate and least biased model we have. Its one weak spot is an event format it has never seen; see below.

Files:

| File | What it does |
|---|---|
| `models.py` | ZS (zone-structural), the anchored EL, EL2 (event-level shrinkage), EL3 (ongoing-event update; rejected) |
| `evaluate.py` | runs both protocols. `cv` touches Jan–Apr only; `holdout` logs each look to `holdout_log.jsonl` (2 looks) |
| `final_table.py` | builds `final_table.csv` from every model that had a holdout look |

## What we found in the data first

The weekday-adjusted level by zone, on non-event days (Jan–Feb = 1.00):

| | Back Forty | Pit | Other 5 zones |
|---|---:|---:|---:|
| Mar (closure) | 0.71 | 1.08 | 1.01–1.07 (absorbed Back Forty's players) |
| Apr | 0.95 | 1.14 (72 → 80 machines) | 0.97–1.02 |
| May | 0.91 | 1.12 | 0.94–0.99 |
| Jun | 0.89 | 1.08 | 0.88–0.96 |

The two "crises" show up clearly in the zone data. The closure moved play between zones rather than just removing it, and the 8 new machines went into the Pit. Underneath both, there is a slow decline that starts in April. At property level, the Pit expansion and Back Forty's recovery hid it.

## Two protocols

- **Fixed (as before):** forecast all 61 days of May–Jun from Apr 30.
- **Weekly refresh:** every 7 days, refit on all data up to that date and forecast the next 7 days. The holdout origins (Apr 30, May 7, …, Jun 25) cover the same 61 days. The CV origins are weekly from Jan 31 to Apr 23. This is how a dashboard forecast would actually be run.

## Models

| Model | What it does |
|---|---|
| **ZS** (zone-structural) | Per zone, models theo *per active machine*, so the Pit's extra machines count as capacity, not demand. Excludes the closure window from every zone's base. Forecasts with each zone's current machine count. Option: a pooled trend from clean days, damped. |
| **Anchor w% (L days)** | Rescales the weekday profile toward the level of the last L non-event days, with weight w |
| **EL2** | EL, but a 3-day event counts as **one** piece of evidence instead of three, with a pseudo-count of 0.5 *events*. Days within one event share one shock. |
| EL3 | EL2 plus updating a running event's lift from its observed days. **Rejected by CV:** slightly worse at every pseudo-count, because lift builds up from Friday to Sunday. |

## Results (theo, May 1 – Jun 30; full table in `final_table.csv`)

"Ex-Locals" leaves out Jun 9–15, the Locals Appreciation Week; see below.

| Protocol | Model | CV MAE | Holdout MAE | Bias/day | **MAE ex-Locals** | Bias ex-Locals | Bias, last 2 weeks |
|---|---|---:|---:|---:|---:|---:|---:|
| fixed | B2 | $5,443 | $4,460 | +1,979 | $4,441 | +2,724 | +5,786 |
| fixed | **EL (previous best)** | $4,027 | **$4,290** | +2,501 | $4,249 | +3,315 | +5,786 |
| fixed | ZS | $3,982 | $5,950 | +5,231 | $6,233 | +6,056 | +8,427 |
| fixed | ZS + damped trend | $4,022 | $4,760 | +3,451 | $4,800 | +4,288 | +6,472 |
| refresh | B2 | $5,641 | $4,332 | +1,620 | $4,278 | +2,397 | +5,242 |
| refresh | EL | $4,170 | $5,267 | +4,273 | $4,044 | +2,921 | +5,028 |
| refresh | EL + anchor 100% (28 d) | $4,052 | $4,850 | +3,593 | $3,659 | +2,240 | +2,296 |
| refresh | ZS + anchor 100% (28 d) | $4,350 | $4,998 | +3,771 | $3,734 | +2,348 | +2,304 |
| refresh | EL2 + anchor 50% (28 d) | $3,876 | $5,021 | +3,991 | $3,829 | +2,665 | +3,662 |
| refresh | **EL2 + anchor 100% (28 d)** ← CV choice | **$3,852** | $4,849 | +3,651 | **$3,677** | **+2,324** | **+2,296** |

Coin-in follows the same pattern.

### How to read it

1. **On ordinary days, weekly refresh with an anchor is the clear winner.**
   - Error falls from $4,249 to $3,677 (−13% vs fixed EL; DM p = 0.09), and to −14% vs refreshed B2.
   - The over-forecast in the last two weeks of June falls from +$5.8K to +$2.3K a day, because the model follows the decline within weeks.
   - Jan–Apr refresh CV picked it independently, both the 100% anchor weight and the 28-day window.
2. **Correcting the disruptions properly makes the fixed forecast worse.** ZS removes the closure's drag and counts the Pit machines, which is the "right" level on Apr 30. It is 2% above EL and loses on the holdout ($5,950). So EL's fixed-horizon win was partly luck: the closure dragged its average down, which happened to offset the decline that came later. A damped trend fitted on clean zones does detect the decline ($4,760), but too weakly to catch up.
3. **The remaining failure is the Locals Appreciation Week.**
   - It was announced May 26, so only the refreshed models know about it. They give it the leisure/promotion lift of about +18% learned from the Winter Slot Tournament. It actually lifted play about +3–8%.
   - That one week adds about +$14K a day of error, which is why every refreshed EL model is behind fixed EL over the full 61 days.
   - Nothing in Jan–Apr can predict it: every leisure event so far was a Friday–Sunday tourist draw.
   - We tested "events lift weekends more" as an alternative explanation and the training data refutes it: conventions lift weekdays 1.04 and weekends 0.99.
   - B2 refreshed ($4,332) does well over the full 61 days only because its single pooled lift happens to be less wrong for that week.
4. **Event-level shrinkage (EL2)** helps in Jan–Apr refresh CV: $4,052 → $3,852, and the worst week $9.2K → $6.1K. It barely changes the fixed protocol. *Disclosure:* we started looking at event evidence after seeing the Locals error. It was adopted because Jan–Apr CV supports it, and it doesn't fix the Locals week.

## For the dashboard

- Use **EL2 + 100% anchor (28 d), refreshed weekly** as the forecast and the "no action" yardstick.
- For any event of a **type or format the data hasn't seen**, show the forecast with and without the lift. For the Locals week that is roughly +0% to +18%. Don't present a single number.
- Report bias next to MAE. After refreshing, bias on ordinary days is about +$2.3K a day (1.8%), down from +$3.3K.

## Holdout accounting

Iteration 3 made 2 logged looks at May–Jun (`holdout_log.jsonl`), covering 13 models in total. Each set was chosen from Jan–Apr CV before the look. `final_table.py` recomputes those same models and adds no new ones. EL3 was rejected on CV and never scored on the holdout.
