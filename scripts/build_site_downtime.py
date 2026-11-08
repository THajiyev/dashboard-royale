"""Export the downtime answer (GUIDE question 3) for the static site (docs/data/downtime.js).

    python scripts/build_site_downtime.py

How much play was lost to downtime, and when?
  * Down hours per machine-day = scheduled_seconds - available_seconds (machine_day), active days only.
  * Each fault (operations, event_type = fault_repair) is valued at the machine's Jan-Jun theo per available
    hour x its zone's busy-ness index for the local hour and day type it opened in (analysis/downtime.py).
  * Two cruder valuations are kept for the range: every down hour at the machine's flat 24-hour rate, and the
    meter-based hour weighting from Phase 0 (outputs/phase0_downtime_lost_play.csv).
  * "When" = by month, by local hour of opening, by weekday, and by shift (wait vs fix time).
  * What could be done about it = the repair-queue replay (+1 tech per shift) and the preventive break-even.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "analysis")]
from build_site_data import dump, r  # noqa: E402
import downtime  # noqa: E402
from common import active_machine_days  # noqa: E402

OUT = ROOT / "outputs"
SHIFT = {**{h: "grave" for h in list(range(0, 6)) + [22, 23]}, **{h: "day" for h in range(6, 14)},
         **{h: "swing" for h in range(14, 22)}}


def main() -> None:
    v = active_machine_days()
    res = downtime.run(v)
    f = res["faults"].copy()
    f["down_h"] = f.wait_h + f.fix_h
    f["lost_theo"] = f.down_h * f.theo_per_down_h
    f["month"] = f.gaming_date.dt.month - 1
    f["dow"] = f.gaming_date.dt.dayofweek
    f["shift"] = f.local_hour.map(SHIFT)

    # all downtime from the meters (faults + installs, moves, maintenance)
    v = v.assign(month=v.gaming_date.dt.month - 1)
    rate = v.groupby("machine_id").theo_usd.sum() / v.groupby("machine_id").available_hours.sum()
    v["flat_lost_theo"] = v.downtime_hours * v.machine_id.map(rate)
    meter_month = v.groupby("month").agg(down_h=("downtime_hours", "sum"), avail_h=("available_hours", "sum"),
                                         flat=("flat_lost_theo", "sum"), theo=("theo_usd", "sum"))
    p0 = pd.read_csv(OUT / "phase0_downtime_lost_play.csv")

    by_month = f.groupby("month").agg(faults=("operation_id", "size"), down_h=("down_h", "sum"),
                                      wait_h=("wait_h", "sum"), fix_h=("fix_h", "sum"), lost=("lost_theo", "sum"))
    months = [{"m": int(m), "faults": int(row.faults), "downH": r(row.down_h, 1), "waitH": r(row.wait_h, 1),
               "fixH": r(row.fix_h, 1), "lost": r(row.lost, 0),
               "meterDownH": r(meter_month.loc[m, "down_h"], 1),
               "availability": r(meter_month.loc[m, "avail_h"] / (meter_month.loc[m, "avail_h"] + meter_month.loc[m, "down_h"]), 5),
               "theo": r(meter_month.loc[m, "theo"], 0)} for m, row in by_month.iterrows()]

    hours = [{"h": int(h), "faults": int(g.shape[0]), "wait": r(g.wait_h.mean(), 3), "fix": r(g.fix_h.mean(), 3),
              "lost": r(g.lost_theo.sum(), 0)} for h, g in f.groupby("local_hour")]
    dows = [{"dow": int(d), "faults": int(g.shape[0]), "lost": r(g.lost_theo.sum(), 0)} for d, g in f.groupby("dow")]
    shifts = [{"shift": s, "faults": int(g.shape[0]), "wait": r(g.wait_h.mean(), 3), "fix": r(g.fix_h.mean(), 3),
               "lost": r(g.lost_theo.sum(), 0)} for s, g in f.groupby("shift")]

    zone_name = v.drop_duplicates("zone_id").set_index("zone_id").zone_name
    zones = [{"zone": zone_name.get(z, z), "id": z, "faults": int(g.shape[0]), "downH": r(g.down_h.sum(), 1),
              "lost": r(g.lost_theo.sum(), 0)} for z, g in f.groupby("zone_id")]
    makers = res["preventive"].rename(columns=str)
    mk = [{"maker": row.manufacturer, "machines": int(row.machines), "faults": int(row.faults),
           "perMachineMonth": r(row.faults_per_machine_month, 3), "downH": r(row.down_h, 1), "lost": r(row.lost_theo, 0),
           "repair": r(row.repair_cost, 0), "per30": r(row.theo_plus_repair_per_30d, 0), "sweep": r(row.sweep_cost, 0),
           "breakeven": r(row.breakeven_fault_reduction, 4)} for row in makers.itertuples()]
    irr = pd.read_csv(OUT / "model_fault_rate_ratios.csv", index_col=0)
    tech = [{"scenario": row.scenario, "hoursSaved": r(row.down_hours_saved_6mo, 0), "saved30": r(row.theo_saved_30d, 0),
             "cost30": r(row.cost_30d, 0), "net30": r(row.net_30d, 0)} for row in res["tech_scenarios"].itertuples()]
    rec = pd.read_csv(OUT / "model_outage_recapture.csv").iloc[0]
    top = (f.groupby(["machine_id"]).agg(faults=("operation_id", "size"), down_h=("down_h", "sum"), lost=("lost_theo", "sum"))
           .join(v.drop_duplicates("machine_id", keep="last").set_index("machine_id")[["zone_name", "manufacturer"]])
           .sort_values("lost", ascending=False).head(10).reset_index())

    dump("downtime", {
        "totals": {
            "faults": int(f.shape[0]), "faultDownH": r(f.down_h.sum(), 1), "waitH": r(f.wait_h.sum(), 1), "fixH": r(f.fix_h.sum(), 1),
            "meterDownH": r(v.downtime_hours.sum(), 1), "availability": r(v.available_hours.sum() / (v.available_hours.sum() + v.downtime_hours.sum()), 5),
            "lostFault": r(f.lost_theo.sum(), 0), "lostFlat": r(v.flat_lost_theo.sum(), 0),
            "lostMeterHourly": r(p0.lost_theo_hourly_usd.sum(), 0), "lostCoinInMeterHourly": r(p0.lost_coin_in_hourly_usd.sum(), 0),
            "repairCost": r(f.repair_cost_usd.sum(), 0), "theo": r(v.theo_usd.sum(), 0),
            "meanWait": r(f.wait_h.mean(), 3), "meanFix": r(f.fix_h.mean(), 3),
        },
        "months": months, "hours": hours, "dows": dows, "shifts": shifts, "zones": zones, "makers": mk,
        "irr": {"Ridgeline": [r(irr.loc["C(manufacturer)[T.Ridgeline]", c], 3) for c in ["rate_ratio", "lo95", "hi95"]],
                "Northwind": [r(irr.loc["C(manufacturer)[T.Northwind]", c], 3) for c in ["rate_ratio", "lo95", "hi95"]]},
        "tech": tech,
        "recapture": {"share": r(rec.recapture_share, 4), "lo": r(rec.lo90, 4), "hi": r(rec.hi90, 4)},
        "top": [{"id": row.machine_id, "zone": row.zone_name, "maker": row.manufacturer, "faults": int(row.faults),
                 "downH": r(row.down_h, 1), "lost": r(row.lost, 0)} for row in top.itertuples()],
    })


if __name__ == "__main__":
    main()
