"""Comp program for the dashboard (docs/data/comps.js).

Points are awarded on carded play and redeemed for F&B comps (loyalty_ledger). For each redemption,
points per $1 of comp face value is the price of a comp in points. Comp reinvestment = redeemed comp
economic cost ÷ tracked theo (reference/DATASET.md). Gaming date = local time − 6 h.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TIERS = ["Base", "Gold", "Platinum"]


def comps(dump, r, MONTHS):
    l = pd.read_parquet(DATA / "3_guests/loyalty_ledger.parquet")
    # gaming date: UTC −8/−7 local, then −6 h; use the fixed Pacific offset via tz conversion
    t = pd.to_datetime(l.event_at_utc).dt.tz_localize("UTC").dt.tz_convert("America/Los_Angeles").dt.tz_localize(None)
    l["d"] = (t - pd.Timedelta(hours=6)).dt.strftime("%Y-%m-%d")
    l["m"] = l.d.str[:7]
    l = l[l.m.isin(MONTHS)]
    red = l[l.event_type == "redeem"].copy()
    red["face"] = red.face_value_cents / 100
    red["cost"] = red.economic_cost_cents / 100
    red["pts"] = -red.points_delta
    red["ppd"] = red.pts / red.face
    aw = l[l.event_type == "award"]

    # daily price of a $1 comp, by tier
    daily = red.groupby(["d", "tier_before"]).ppd.median().unstack().reindex(columns=TIERS)
    dcount = red.groupby("d").agg(n=("face", "size"), face=("face", "sum"), cost=("cost", "sum"))

    # monthly program summary
    pp = pd.read_parquet(DATA / "1_prepared_views/player_period.parquet",
                         columns=["player_id", "period_month", "tier_end", "theo_usd", "comp_cost_usd", "comp_face_value_usd",
                                  "points_earned", "points_redeemed", "tracked_coin_in_usd"])
    for c in ["theo_usd", "comp_cost_usd", "comp_face_value_usd", "tracked_coin_in_usd"]:
        pp[c] = pp[c].astype(float)
    pp["m"] = pp.period_month.astype(str).str[:7]
    mon = []
    for i, m in enumerate(MONTHS):
        R, A, P = red[red.m == m], aw[aw.m == m], pp[pp.m == m]
        tiers = P.groupby("tier_end").player_id.nunique().reindex(TIERS).fillna(0)
        by_tier = {tr: {"members": int(tiers[tr]), "theo": r(P[P.tier_end == tr].theo_usd.sum(), 0),
                        "cost": r(P[P.tier_end == tr].comp_cost_usd.sum(), 0),
                        "ppd": r(R[R.tier_before == tr].ppd.median(), 2), "redemptions": int((R.tier_before == tr).sum())}
                   for tr in TIERS}
        mon.append({"m": i, "redemptions": int(len(R)), "redeemers": int(R.player_id.nunique()),
                    "face": r(R.face.sum(), 0), "cost": r(R.cost.sum(), 0), "ptsRedeemed": int(R.pts.sum()),
                    "ptsEarned": int(A.points_delta.sum()), "theo": r(P.theo_usd.sum(), 0), "ci": r(P.tracked_coin_in_usd.sum(), 0),
                    "active": int(P.player_id.nunique()), "ppCost": r(P.comp_cost_usd.sum(), 0), "tiers": by_tier})

    # what comps bought, before vs after May 1
    red["after"] = red.d >= "2025-05-01"
    items = red.groupby(["benefit_id", "after"]).face.sum().unstack(fill_value=0)
    items = (items / items.sum()).round(4)
    item_rows = [{"item": k.replace("COMP-", "").title(), "before": float(v[False]), "after": float(v[True])} for k, v in items.iterrows()]

    # points per redemption and face per redemption, before vs after
    ba = red.groupby("after").agg(n=("face", "size"), face=("face", "mean"), pts=("pts", "mean"), cost=("cost", "mean"))
    days = {False: 120, True: 61}
    ba_rows = {("after" if k else "before"): {"perDay": r(v.n / days[k], 1), "face": r(v.face, 2), "pts": r(v.pts, 0), "cost": r(v.cost, 2)}
               for k, v in ba.iterrows()}

    # ---- May 1 investigation
    # 1. the pricing rule: points = ceil(face × base rate × tier multiplier); which rule does each redemption match?
    mult = red.tier_before.map({"Base": 1.0, "Gold": 0.8, "Platinum": 0.6})
    old = np.ceil(red.face * 15 * mult - 1e-9) == red.pts
    new = np.ceil(red.face * 7 * mult - 1e-9) == red.pts
    ts = pd.to_datetime(red.event_at_utc).dt.tz_localize("UTC").dt.tz_convert("America/Los_Angeles").dt.tz_localize(None)
    rule = {"n": int(len(red)), "old": int(old.sum()), "new": int((new & ~old).sum()), "neither": int((~old & ~new).sum()),
            "lastOld": ts[old].max().strftime("%Y-%m-%d %H:%M"), "firstNew": ts[new & ~old].min().strftime("%Y-%m-%d %H:%M"),
            "menuChanged": bool(red.groupby(["benefit_id", "after"]).face.nunique().gt(1).any()
                                or red.groupby("benefit_id").face.nunique().gt(1).any())}
    # earning: points awarded per dollar of tracked coin-in, before vs after
    earn = {k: r(aw[aw.d.ge("2025-05-01") == k].points_delta.sum() / pp[(pp.m >= "2025-05") == k].tracked_coin_in_usd.sum(), 3)
            for k in (False, True)}
    # 2. did comp users play more? locals who redeemed in Jan–Apr vs active locals who never did; theo indexed to Mar–Apr
    pp2 = pd.read_parquet(DATA / "1_prepared_views/player_period.parquet",
                          columns=["player_id", "period_month", "home_region", "theo_usd", "observed_visits", "comps_redeemed"])
    pp2["m"] = pp2.period_month.astype(str).str[:7]
    pp2["theo"] = pp2.theo_usd.astype(float)
    redeemers = set(pp2[pp2.m.isin(MONTHS[:4]) & (pp2.comps_redeemed > 0)].player_id)
    active = set(pp2[pp2.m.isin(MONTHS[2:4])].player_id)
    loc = pp2[pp2.home_region == "Local"].copy()
    loc["cohort"] = np.where(loc.player_id.isin(redeemers), "redeemer", np.where(loc.player_id.isin(active), "other", None))
    loc = loc[loc.cohort.notna()]
    cohorts = {}
    for co, d in loc.groupby("cohort"):
        th = d.groupby("m").theo.sum().reindex(MONTHS).fillna(0)
        vi = d.groupby("m").observed_visits.sum().reindex(MONTHS).fillna(0)
        cohorts[co] = {"players": int(d.player_id.nunique()), "theo": [r(v, 4) for v in th / th[MONTHS[2:4]].mean()],
                       "visits": [r(v, 4) for v in vi / vi[MONTHS[2:4]].mean()]}
    visitors_return = r(pp2[pp2.home_region != "Local"].groupby("player_id").m.nunique().gt(1).mean(), 4)
    # 3. F&B: did comps replace cash purchases by card holders?
    f = pd.read_parquet(DATA / "3_guests/fnb_transactions.parquet", columns=["event_at_local", "player_id", "comp_id", "cash_receipt_cents"])
    f["m"] = (pd.to_datetime(f.event_at_local) - pd.Timedelta(hours=6)).dt.strftime("%Y-%m")
    f = f[f.m.isin(MONTHS)]
    carded = f.player_id.notna()
    fnb = [{"m": i, "cardedPaidTx": int((carded & f.comp_id.isna() & (f.m == m)).sum()),
            "cardedCash": r(f[carded & (f.m == m)].cash_receipt_cents.sum() / 100, 0),
            "uncardedCash": r(f[~carded & (f.m == m)].cash_receipt_cents.sum() / 100, 0),
            "compTx": int((f.comp_id.notna() & (f.m == m)).sum())} for i, m in enumerate(MONTHS)]
    may1 = {"rule": rule, "earnPerDollar": {"before": earn[False], "after": earn[True]}, "cohorts": cohorts,
            "visitorsReturn": visitors_return, "fnb": fnb}

    out = {
        "may1": may1,
        "tiers": TIERS,
        "daily": [{"d": d, **{tr: (None if pd.isna(row[tr]) else round(float(row[tr]), 2)) for tr in TIERS},
                   "n": int(dcount.n.get(d, 0)), "face": r(dcount.face.get(d, 0), 0), "cost": r(dcount.cost.get(d, 0), 0)}
                  for d, row in daily.iterrows()],
        "months": mon, "items": item_rows, "beforeAfter": ba_rows,
        "costRatio": r(red.cost.sum() / red.face.sum(), 4),
    }
    dump("comps", out)
    print("comps: redemptions", len(red), "change day prices", daily.loc["2025-04-30"].to_dict(), daily.loc["2025-05-01"].to_dict())
