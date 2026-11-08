"""Export the analysis results the static dashboard site reads (docs/data/*.js).

Each file sets window.__DATA[name] = {...}, so the site works from file:// with no server.
Run from the repository root after analysis/run_phase0.py, run_models.py and run_impact.py:
    python scripts/build_site_data.py
Only reads data/ and outputs/ (plus one refit of the Phase 3 location GLM for bank-effect
covariances). Nothing here is fitted on May–Jun data except where the source table already was.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "analysis"), str(ROOT / "analysis" / "experiments"),
                str(ROOT / "analysis" / "experiments" / "iter5")]
from common import active_machine_days, load, split_by_date  # noqa: E402
import machine_effects as mfx  # noqa: E402

OUT = ROOT / "outputs"
IT5 = ROOT / "analysis" / "experiments" / "iter5"
DEST = ROOT / "docs" / "data"
MONTHS = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06"]


def r(x, n=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), n)


def dump(name, obj):
    DEST.mkdir(exist_ok=True)
    body = json.dumps(obj, separators=(",", ":"), default=str)
    path = DEST / f"{name}.js"
    path.write_text(f"(window.__DATA = window.__DATA || {{}})[{json.dumps(name)}] = {body};\n", encoding="utf-8")
    print(f"{path.name}  {path.stat().st_size / 1024:.0f} KB")


def records(df, cols=None, n=4):
    df = df if cols is None else df[cols]
    out = []
    for row in df.itertuples(index=False):
        rec = {}
        for k, v in zip(df.columns, row):
            if isinstance(v, (float, np.floating)):
                rec[k] = r(v, n)
            elif isinstance(v, (np.integer,)):
                rec[k] = int(v)
            elif isinstance(v, (np.bool_, bool)):
                rec[k] = bool(v)
            elif isinstance(v, pd.Timestamp):
                rec[k] = v.strftime("%Y-%m-%d")
            elif v is None or (isinstance(v, float) and np.isnan(v)):
                rec[k] = None
            else:
                rec[k] = v
        out.append(rec)
    return out


# ----------------------------------------------------------------------------- floor + machines
def floor_and_machines():
    fl = load("2_machine_decision/floor_locations.parquet")
    zones = fl[fl.node_type == "zone"]
    banks = fl[fl.node_type == "bank"]
    slots = fl[fl.node_type == "slot"]
    v = active_machine_days()
    v["month"] = v.gaming_date.dt.strftime("%Y-%m")
    zname = v.drop_duplicates("zone_id").set_index("zone_id").zone_name.to_dict()

    # GLM bank effects with covariance (same fit as Phase 3, Jan–Apr only)
    df = mfx.machine_day_frame(v)
    train, _ = split_by_date(df)
    glm = mfx.fit_glm(train)
    keys = [k for k in glm.params.index if k.startswith("C(bank_id)")]
    bank_ids = [k.split("[T.")[1][:-1] for k in keys]
    ref = sorted(set(train.bank_id) - set(bank_ids))
    fx = {b: float(glm.params[k]) for b, k in zip(bank_ids, keys)}
    for b in ref:
        fx[b] = 0.0
    cov = glm.cov_params().loc[keys, keys].to_numpy()
    order = ref + bank_ids  # reference bank(s) have zero variance
    covfull = np.zeros((len(order), len(order)))
    covfull[len(ref):, len(ref):] = cov
    # centre on the slot-weighted mean so "0" reads as an average spot
    cap = banks.set_index("bank_id").capacity.astype(float)
    mean_fx = sum(fx[b] * cap.get(b, 0) for b in fx) / sum(cap.get(b, 0) for b in fx)

    walk = load("2_machine_decision/floor_walkways.parquet")
    ent = fl[fl.node_type == "entrance"]
    outl = fl[fl.node_type == "outlet"]

    # zone traffic: entries per counted hour, by month (ok counters only)
    t = load("4_context/zone_traffic_hourly.parquet")
    t = t[t.counter_status == "ok"].copy()
    t["gd"] = (pd.to_datetime(t.hour_start_local) - pd.Timedelta(hours=6)).dt.strftime("%Y-%m")
    tr = t.groupby(["zone_id", "gd"]).agg(e=("entries_count", "sum"), h=("coverage_minutes", "sum")).reset_index()
    tr["per_h"] = tr.e / (tr.h / 60)
    traffic = {z: [r(tr[(tr.zone_id == z) & (tr.gd == m)].per_h.sum(), 1) for m in MONTHS] for z in zones.zone_id}

    floor = {
        "months": MONTHS,
        "zones": [{"id": z.zone_id, "name": zname.get(z.zone_id, z.zone_id), "x": r(z.x_m, 1), "y": r(z.y_m, 1)}
                  for z in zones.itertuples()],
        "banks": [{"id": b.bank_id, "zone": b.zone_id, "x": r(b.x_m, 1), "y": r(b.y_m, 1),
                   "fx": r(fx.get(b.bank_id, np.nan) - mean_fx, 4) if b.bank_id in fx else None}
                  for b in banks.itertuples()],
        "slots": [{"id": s.location_id, "bank": s.bank_id, "zone": s.zone_id, "x": r(s.x_m, 1), "y": r(s.y_m, 1)}
                  for s in slots.itertuples()],
        "entrances": [{"id": e.location_id, "zone": e.zone_id, "x": r(e.x_m, 1), "y": r(e.y_m, 1)} for e in ent.itertuples()],
        "outlets": [{"id": o.location_id, "zone": o.zone_id, "x": r(o.x_m, 1), "y": r(o.y_m, 1)} for o in outl.itertuples()],
        "walkways": [{"id": w.walkway_id, "a": w.zone_a, "b": w.zone_b, "len": r(w.length_m, 0),
                      "closed": None if pd.isna(w.closed_from_utc) else ["2025-03-03", "2025-04-06"]}
                     for w in walk.itertuples()],
        "traffic": traffic,
        "bankCov": {"order": order, "cov": [[r(c, 7) for c in row] for row in covfull]},
    }
    dump("floor", floor)

    # ---- machines: static facts + monthly meters
    mach = load("2_machine_decision/machines.parquet")
    luck = pd.read_csv(OUT / "model_luck_engine.csv").set_index("machine_id")
    eff = pd.read_csv(OUT / "model_machine_effects.csv").set_index("machine_id")
    b10 = pd.read_csv(OUT / "model_bottom10_classification.csv").set_index("machine_id")
    down = pd.read_csv(OUT / "phase0_downtime_lost_play.csv").groupby("machine_id")[["lost_theo_usd"]].sum()
    gm = load("2_machine_decision/game_math.parquet").set_index("config_id")

    mon = v.groupby(["machine_id", "month"]).agg(
        ci=("coin_in_usd", "sum"), theo=("theo_usd", "sum"), win=("house_win_usd", "sum"),
        ah=("available_hours", "sum"), dh=("downtime_hours", "sum"), var=("win_var_cents2", "sum"),
        n=("paid_spins", "sum"), pos=("payout_positive_spins", "sum"), days=("gaming_date", "nunique"),
        loc=("location_id", "last")).reset_index()
    mon["var"] = mon["var"] / 1e4  # usd^2
    last = v.sort_values("gaming_date").groupby("machine_id").last()

    out = []
    for mid, g in mon.groupby("machine_id"):
        g = g.set_index("month").reindex(MONTHS)
        L = luck.loc[mid] if mid in luck.index else None
        E = eff.loc[mid] if mid in eff.index else None
        cfg = last.loc[mid].config_id
        m = {
            "id": mid, "theme": last.loc[mid].theme, "mfr": last.loc[mid].manufacturer,
            "vol": last.loc[mid].volatility_class, "rtp": r(float(gm.loc[cfg].configured_rtp), 3),
            "hitp": r(float(gm.loc[cfg].hit_probability), 6), "zone": last.loc[mid].zone_id,
            "loc": [None if pd.isna(x) else x for x in g["loc"]],
            "ci": [r(x, 0) if pd.notna(x) else 0 for x in g.ci], "theo": [r(x, 1) if pd.notna(x) else 0 for x in g.theo],
            "win": [r(x, 1) if pd.notna(x) else 0 for x in g.win], "ah": [r(x, 1) if pd.notna(x) else 0 for x in g.ah],
            "dh": [r(x, 1) if pd.notna(x) else 0 for x in g.dh], "var": [r(x, 0) if pd.notna(x) else 0 for x in g["var"]],
            "n": [int(x) if pd.notna(x) else 0 for x in g.n], "pos": [int(x) if pd.notna(x) else 0 for x in g.pos],
            "days": [int(x) if pd.notna(x) else 0 for x in g.days],
            "lostTheo": r(down.lost_theo_usd.get(mid, 0), 0),
        }
        if E is not None:
            m["effect"] = [r(np.expm1(E.effect), 4), r(np.expm1(E.effect_lo), 4), r(np.expm1(E.effect_hi), 4)]
        if L is not None:
            m["cusum"] = [None if pd.isna(L.cusum_luck_alarm_month) else L.cusum_luck_alarm_month,
                          None if pd.isna(L.cusum_hit_alarm_month) else L.cusum_hit_alarm_month]
            m["jackpotShare"] = r(L.jackpot_share_of_deficit, 3)
        if mid in b10.index:
            B = b10.loc[mid]
            m["b10"] = {"rank": int(L.rank_by_win) if L is not None else None, "verdict": B.verdict,
                        "action": B.recommended_action, "evidence": B.evidence,
                        "uplift": r(B.location_uplift_theo_per_day, 1)}
        out.append(m)
    inst = mach.set_index("machine_id")
    for m in out:
        row = inst.loc[m["id"]]
        m["installed"] = str(row.install_date)[:10]; m["retired"] = None if pd.isna(row.retire_date) else str(row.retire_date)[:10]
    dump("machines", out)


# ----------------------------------------------------------------------------- forecast
def forecast():
    import forecast as fc  # noqa: F401  (needed by evaluate)
    import harness
    from evaluate import ALPHA, cv_residuals
    from iter2.models import EL
    from common import TRAIN_END
    pdy = load("1_prepared_views/property_day.parquet").sort_values("gaming_date")
    hd = pd.read_csv(IT5 / "holdout_daily.csv", parse_dates=["gaming_date"])
    hd2 = pd.read_csv(OUT / "model_forecast_holdout_predictions.csv", parse_dates=["gaming_date"])
    hd2 = hd2[hd2.target == "theo_usd"].set_index("gaming_date")
    hd = hd.set_index("gaming_date")
    df = harness.frame()
    df_cv = df[df.gaming_date <= TRAIN_END]
    bands = {}
    for name, f in [("EL", EL), ("B1", fc.m_b1)]:
        lr, _, _ = cv_residuals(f, "fixed", df_cv)
        bands[name] = [float(x) for x in np.quantile(lr, [ALPHA / 2, 1 - ALPHA / 2])]

    ev = load("4_context/events.parquet")
    jul = pd.read_csv(OUT / "model_july_theo_counterfactual.csv")
    wm = pd.read_csv(IT5 / "weather_monthly.csv")
    # B1 as built: the Jan–Apr mean theo per weekday
    tr = pdy[pdy.gaming_date <= TRAIN_END]
    b1 = tr.groupby(tr.gaming_date.dt.dayofweek).theo_usd.mean()

    out = {
        "daily": [{"d": d.strftime("%Y-%m-%d"), "theo": r(t, 0), "ci": r(c, 0)}
                  for d, t, c in zip(pdy.gaming_date, pdy.theo_usd, pdy.coin_in_usd)],
        "holdout": [{"d": d.strftime("%Y-%m-%d"), "actual": r(hd.loc[d, "actual"], 0),
                     "EL": r(hd.loc[d, "EL event-type lift"], 0), "B1": r(hd2.loc[d, "B1 weekday mean"], 0),
                     "B2": r(hd.loc[d, "B2 event-aware weekday"], 0), "EL2A": r(hd.loc[d, "EL2 + 28d anchor"], 0),
                     "SEG": r(hd.loc[d, "EL2A segments: bottom_up beta=0.5"], 0)} for d in hd.index],
        "bands": bands,
        "b1Weekday": [r(b1.get(i), 0) for i in range(7)],
        "events": records(ev),
        "july": records(jul, ["gaming_date", "weekday", "forecast", "lo90", "hi90", "forecast_level_adj"], 0),
        "julyLevelAdj": r(jul.level_adj.iloc[0], 4),
        "segments": records(wm, None, 1),
    }
    dump("forecast", out)


# ----------------------------------------------------------------------------- models + context
def models_and_context():
    t = pd.read_csv(IT5 / "table_vs_b1.csv")
    p2 = pd.read_csv(OUT / "model_comparison.csv")
    nf = pd.read_csv(IT5 / "noise_floor.csv")
    lb = pd.read_csv(OUT / "model_leaderboard_forecast.csv")
    mp = pd.read_csv(OUT / "model_measurement_plan.csv")
    sc = pd.read_csv(OUT / "model_change_scorecard.csv")
    tech = pd.read_csv(OUT / "model_tech_scenarios.csv")
    prev = pd.read_csv(OUT / "model_preventive_breakeven.csv")
    frr = pd.read_csv(OUT / "model_fault_rate_ratios.csv").rename(columns={"Unnamed: 0": "term"})
    cat = load("2_machine_decision/action_catalog.parquet")
    dump("models", {"catalog": records(cat), "vsB1": records(t), "phase2": records(p2), "noiseFloor": records(nf, None, 0),
                    "leaderboard": records(lb), "measurement": records(mp), "scorecard": records(sc),
                    "tech": records(tech, None, 1), "preventive": records(prev), "faultRates": records(frr)})

    wc = pd.read_csv(IT5 / "weather_check.csv")
    wr = pd.read_csv(IT5 / "weather_robustness.csv")
    w = load("4_context/real_sources/weather_daily.parquet")
    es = pd.read_csv(OUT / "model_closure_event_study.csv")
    cf = pd.read_csv(OUT / "model_closure_counterfactual_daily.csv")
    lv = pd.read_csv(ROOT / "analysis" / "experiments" / "iter4" / "lvcva_history.csv")
    try:
        city = load("4_context/real_sources/city_visitation_monthly.parquet")
        city = records(city, ["month", "visitor_volume", "visitor_yoy_ratio", "convention_attendance",
                              "hotel_occupancy_ratio"])
    except Exception:  # noqa: BLE001
        city = []
    dump("context", {"weatherCheck": records(wc), "weatherRobust": records(wr),
                     "weather": records(w, ["source_date", "tmax_c", "tmin_c", "prcp_mm"], 1), "closureStudy": records(es), "closureDaily": records(cf, None, 1),
                     "lvcva": records(lv), "city": city})


if __name__ == "__main__":
    import sys as _s
    only = set(_s.argv[1:])
    if not only or "core" in only:
        floor_and_machines()
        forecast()
        models_and_context()
    if not only or "comps" in only:
        from build_site_comps import comps
        comps(dump, r, MONTHS)
    if not only or "players" in only:
        from build_site_players import players
        players(dump, r, MONTHS)
