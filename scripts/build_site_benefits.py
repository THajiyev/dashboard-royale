"""Export what each catalogue action could bring in July (docs/data/benefits.js).

    python scripts/build_site_benefits.py

Needs the analysis outputs (outputs/model_*.csv from analysis/run_models.py) and data/.
Every number here is either measured in Jan-Jun or a model output; the page (assets/benefits.js) turns them into
July value curves with a low / central / high case. Where nothing in the data says what an action does, the input
is an explicit assumption, and the page says so.

Inputs, per action type:
  A-MOVE-MACHINE  location model, computed in the browser (assets/moves.js); downtime valued here
  A-MOVE-BANK     bank-swap values from the same location model (bank effects + bank covariance), computed here
  A-REPLACE-*     the like-for-like replacement measured at L-38-5 (theo per day, 90% CI)
  A-TECH-SHIFT    repair-queue replay: theo saved per 30 days for one more technician on each shift
  A-PREVENTIVE    per manufacturer: lost theo + repair cost per 30 days, and the sweep's own downtime
  A-INSPECT       M-1158's daily payout gap (theo - house win); no other machine is flagged
  A-WAYFINDING    Back Forty's theo per day (May-Jun); the next zone's for a second unit
  A-COMP-PILOT    half of the extra comp cost since May 1, saved while the pilot runs
  A-COMP-CHANGE   all of it, if the old rate is restored; comp users' theo for the downside case
  A-PROMO         the two property promotions measured in Jan-Jun (theo per day, 90% CI)
  A-SURVEY        no revenue effect
Downtime: each unit's catalogue downtime_minutes x the floor's theo per available machine-hour (May-Jun).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA, OUT = ROOT / "data", ROOT / "outputs"
sys.path[:0] = [str(ROOT / "scripts")]
from build_site_data import dump, r  # noqa: E402


def num(d: pd.DataFrame) -> pd.DataFrame:
    for c in d.columns:
        if d[c].dtype == object and len(d) and type(d[c].dropna().iloc[0]).__name__ == "Decimal":
            d[c] = d[c].astype(float)
    return d


def main() -> None:
    v = num(pd.read_parquet(DATA / "1_prepared_views/prepared_daily_view.parquet",
                            columns=["machine_id", "gaming_date", "zone_id", "zone_name", "theo_usd", "house_win_usd",
                                     "available_hours", "active", "location_id"]))
    v = v[v.active & v.location_id.notna()].copy()
    v["gaming_date"] = pd.to_datetime(v.gaming_date)
    mj = v[v.gaming_date >= "2025-05-01"]
    hour_theo = mj.theo_usd.sum() / mj.available_hours.sum()
    zone_day = (mj.groupby(["zone_id", "zone_name"]).theo_usd.sum() / mj.gaming_date.nunique()).reset_index(name="theo_day")

    sc = pd.read_csv(OUT / "model_change_scorecard.csv")
    promos = sc[sc.change.str.startswith("Property promotion")]
    like = sc[sc.change.str.contains("like-for-like")].iloc[0]
    newgame = sc[sc.change.str.contains("new game")].iloc[0]
    tech = pd.read_csv(OUT / "model_tech_scenarios.csv")
    prev = pd.read_csv(OUT / "model_preventive_breakeven.csv")

    m1158 = v[v.machine_id == "M-1158"]
    gap_day = (m1158.theo_usd.sum() - m1158.house_win_usd.sum()) / m1158.gaming_date.nunique()

    pp = num(pd.read_parquet(DATA / "1_prepared_views/player_period.parquet",
                             columns=["player_id", "period_month", "home_region", "theo_usd", "comp_cost_usd", "comps_redeemed"]))
    pp["m"] = pp.period_month.astype(str).str[:7]
    cost_m = pp.groupby("m").comp_cost_usd.sum()
    extra = cost_m[cost_m.index >= "2025-05"].mean() - cost_m[cost_m.index < "2025-05"].mean()
    redeemers = set(pp[(pp.m < "2025-05") & (pp.comps_redeemed > 0)].player_id)
    users_theo_m = pp[pp.player_id.isin(redeemers) & (pp.m >= "2025-05")].theo_usd.sum() / 2

    dump("benefits", {
        "hourTheo": r(hour_theo, 3),
        "zones": [{"id": z.zone_id, "name": z.zone_name, "theoDay": r(z.theo_day, 0)} for z in zone_day.itertuples()],
        "promos": [{"name": p.change.split(": ", 1)[1], "day": r(p.theo_usd_per_day, 0), "lo": r(p.lo90_usd_day, 0),
                    "hi": r(p.hi90_usd_day, 0), "days": int(p.days)} for p in promos.itertuples()],
        "replace": {"like": [r(like.lo90_usd_day, 2), r(like.theo_usd_per_day, 2), r(like.hi90_usd_day, 2)],
                    "newGame": [r(newgame.lo90_usd_day, 2), r(newgame.theo_usd_per_day, 2), r(newgame.hi90_usd_day, 2)]},
        "tech": [{"shift": t.scenario.split(" on ")[1].replace(" shift", ""), "saved30": r(t.theo_saved_30d, 0)}
                 for t in tech.sort_values("theo_saved_30d", ascending=False).itertuples()],
        "preventive": [{"maker": p.manufacturer, "machines": int(p.machines), "per30": r(p.theo_plus_repair_per_30d, 0),
                        "downtime": r(p.sweep_cost - 9000, 0)}
                       for p in prev.sort_values("theo_plus_repair_per_30d", ascending=False).itertuples()],
        "m1158GapDay": r(gap_day, 2),
        "comps": {"extraPerMonth": r(extra, 0), "usersTheoPerMonth": r(users_theo_m, 0)},
    })


if __name__ == "__main__":
    main()
