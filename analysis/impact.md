# Change-impact model: did a change help or hurt, and by how much?

Run `python analysis/run_impact.py` (about 10 s). Validation is in `python analysis/impact_validate.py 7` and `... 11 --calibrated` (about 1.5 min each).

Code is `analysis/impact.py`. Outputs:

| File | Contents |
|---|---|
| `outputs/model_change_scorecard.csv` | one headline row per change |
| `outputs/model_change_impacts.csv` | every part: direct, spillover, net |
| `outputs/model_outage_recapture.csv` | the outage (slot closing) result |
| `outputs/model_impact_validation_*.csv` | validation runs |

## What it reports

For any change (which units, which dates) it returns:

- **Direct effect** on the changed units: % and theo $/day against a counterfactual.
- **Spillover** on the units most likely to absorb or lose play: other zones for a closure, existing Pit machines for the new bank, old and new bank-mates for a moved machine.
- **NET $/day = direct + spillover.** This is what the P&L sees. A closure that just moves players to the next zone has a large direct effect and a net effect near zero.
- A **90% interval**, a **verdict** (Positive / Negative / Inconclusive when the interval spans 0), and an **impact score**: net ÷ (half-width / 1.645), read like a z-score. |score| > 1.645 means the 90% interval excludes zero.

## How it works

| Kind of change | Estimator | Counterfactual | Interval from |
|---|---|---|---|
| Temporary: closure, promotion, event | **on–off** | Equal-length baselines just before and after, with weekday effects and a linear trend, so slow drifts like the spring decline cancel. Event days are dropped unless the change *is* the event. | **In-time placebos:** the same estimator on fake windows of the same length on the same series |
| Permanent: new machines, move, replacement | **difference-in-differences** on weekly blocks | log(treated) − log(control), pre vs post | **In-space placebos:** the same dates on 60–80 random untouched machines or banks |
| Slots closing for hours (outages) | **bank-day panel** | Bank play vs its expected play if all machines were up, scaled by the zone's level that day from other banks. Expected loss uses an hourly play profile. | Cluster-robust by bank |

Data periods overlapping another known change are excluded: the closure window is removed from the February move and replacement comparisons, and the new bank from the closure's Pit series.

## Validation (before any real result was used)

We ran 150 fake changes per estimator at random units and dates where nothing happened, then the same draws with an effect of −15% or +10% injected.

| Estimator | Intervals | Coverage of the truth (target 90%) | False flags on fake changes (target ≤10%) | Mean estimate when the truth is −15% / 0 / +10% | Detects −15% / +10% |
|---|---|---:|---:|---|---|
| on–off (zone) | raw placebo | 83–86% | 14% | −14.5% / +0.1% / +9.8% | — |
| on–off (zone) | **calibrated ×1.25**, fresh batch | **97%** | **3%** | −15.0% / 0.0% / +10.0% | 99% / 83% |
| DiD (machine) | raw placebo | 85% | 15% | −14.2% / +1.0% / +11.0% | — |
| DiD (machine) | **calibrated ×1.25**, fresh batch | **95%** | **5%** | −14.4% / +0.7% / +10.7% | 66% / 33% |

The checks fixed three things along the way:
1. A standard-error formula (Newey–West) covered only 40%, so placebos replaced it.
2. Event days inside a window biased estimates by +2%, so event handling was fixed.
3. Placebo spreads are slightly too narrow, so they are multiplied by one ×1.25 factor. It was fit on seed 7 and confirmed on seed 11.

**Limits:**
- A single machine's change has to be big to show: +10% is caught only a third of the time.
- Zone-level changes of 10% or more are caught reliably.
- Spillover to bank groups uses the same machinery but was not validated separately.
- The NET interval adds the parts' half-widths in quadrature, which ignores correlation between them. For the closure we therefore quote the directly measured net.

## Results (theo; `model_change_scorecard.csv`)

| Change | NET theo $/day (90% CI) | Total | Verdict | Score |
|---|---:|---:|---|---:|
| **8 new machines, bank B-51, Pit (Mar 24)** | **+$5,298** (+4,551 to +6,045) | +$450K over 85 d | Positive | 12.0 |
| Walkway closure (Mar 3 – Apr 6) | +$1,975 (−303 to +4,213) | +$69K over 35 d | Inconclusive | 1.4 |
| **Move M-1152, Back Forty → Entrance (Feb 4)** | **+$342** (+188 to +497) | +$31K over 91 d | Positive | 3.6 |
| Move M-1113, within the Pit (Feb 18) | +$102 (−104 to +309) | | Inconclusive | 0.8 |
| Move M-1126, Hotel → Bar (May 6) | +$32 (−174 to +238) | | Inconclusive | 0.3 |
| Move M-1299, Pit → Hotel (Jun 10, 3 weeks of data) | −$106 (−304 to +92) | | Inconclusive | −0.9 |
| Replace M-1118 → M-1532, new game (high-limit room) | −$30 (−83 to +17) | | Inconclusive | −1.0 |
| **Replace M-1120 → M-5076, like-for-like (Back Forty)** | +$4 (−17 to +23) | | Inconclusive | 0.4 |
| Super Bowl weekend | +$35,710/day | +$107K | Positive | 6.8 |
| College basketball opening rounds | +$28,741/day | +$115K | Positive | 6.7 |
| Winter Slot Tournament (property promotion) | +$26,146/day | +$78K | Positive | 4.9 |
| EDC festival | +$23,451/day | +$70K | Positive | 4.7 |
| Locals Appreciation Week (property promotion) | +$8,444/day | +$59K | Positive | 2.8 |
| CES / NAB / CinemaCon (conventions) | −$1.1K to +$4.3K/day | | Inconclusive | −0.3 to 1.2 |

**Slots closing (outages).** Bank-mates recapture **−2% (90% CI −15% to +12%)** of a down machine's expected play. That is from 903 bank-days with an outage; for outages of at least 5% of bank play it is −7% (−23% to +9%). So a down machine's play is essentially **lost to its bank**. We can't rule out that some players walk further across the floor.

## What it means for the decisions

1. **The walkway closure barely cost the floor anything.** Back Forty lost 26% (−$3.7K/day, ≈ $129K over 35 days, in line with Phase 4a). The other zones gained +5% (+$5.5K/day) because players walked elsewhere. Measured directly, the whole floor was +1.6% (−0.2% to +3.4%), so there is no evidence of a net loss. *This revises the Phase 4a headline*: the ≈ $136K is Back Forty's loss, not the property's. Access matters for *where* people play more than for *whether* they play.
2. **Replacing like-for-like doesn't help.** The one like-for-like replacement, at a bottom-10 slot, moved theo by +$4/day (−$17 to +$23). A leased replacement costs $2,500 plus $55/day, so it can't pay back. This is direct evidence against the GM's plan.
3. **Location does.** Moving M-1152 from Back Forty to the Entrance doubled its play (+101% coin-in, +74% to +132%) with no detectable loss to its old or new bank-mates: net +$342/day. A move costs $1,800, so it pays back in about a week. The moves between busy zones did not change much.
4. **New capacity in the Pit was almost fully incremental.** Cannibalization of the existing Pit machines was −0.3% (−2.5% to +1.9%), so the 8 machines added about $5.3K/day net.
5. **Leisure events and promotions lift the floor 7–24%; conventions do nothing measurable.** The tournament earned about $78K of theo in 3 days and Locals week about $59K in 7. Promotion costs aren't in the data, so these are gross figures.
6. **Outages are pure loss at bank level.** That supports valuing downtime at the machine's full expected play, as Phase 4b does.

## Using it for a new change

```python
import impact
s = impact.series(impact.daily_view().zone_id == "Z-B40")           # any group's daily theo
e = impact.on_off(s, "2025-07-07", "2025-07-20")                     # temporary change
e = impact.did(treated, control, "2025-07-07", placebo_units=...)    # permanent change; see run_impact.py
print(e.pct, e.usd_day, impact.row("my change", "Direct", e, "on_off"))
```

Measure the spillover groups too, otherwise you only see the direct effect. `run_impact.py` has a worked pattern for each kind of change.
