"""Phase 4b: faults, repair queues and what downtime actions are worth.

1. Fault-rate model: negative-binomial GLM of faults per machine-day
   ~ manufacturer + volatility + machine age + log(occupied hours), offset log(available+down hours).
   Fit Jan–Apr, scored on May–Jun machine totals against a fleet-rate and a manufacturer-rate baseline.
2. Repair-queue replay simulation (new): replays every actual fault (arrival time, actual fix time)
   through the actual slot-tech roster, FIFO, one tech per job. Calibrated against the observed waits,
   then re-run with +1 technician on each shift to get the downtime that A-TECH-SHIFT would remove.
   This is mechanistic, so it does not need observational variation in headcount (grave never varies).
3. Value of a down hour = machine theo per available hour × zone busy-ness index for that local hour
   (the Phase 0 hour-aware rate). Savings are compared with action_catalog prices.
4. Preventive-maintenance break-even: the fault reduction a sweep needs to pay for itself in 30 days.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from common import TRAIN_END, load, split_by_date

ROOT = Path(__file__).resolve().parents[1]


# ----------------------------------------------------------------------------- inputs
def faults() -> pd.DataFrame:
    op = load("2_machine_decision/operations.parquet")
    f = op[op.event_type == "fault_repair"].copy()
    for c in ["opened_at_utc", "work_started_at_utc", "available_at_utc", "opened_at_local"]:
        f[c] = pd.to_datetime(f[c])
    f["wait_h"] = (f.work_started_at_utc - f.opened_at_utc).dt.total_seconds() / 3600
    f["fix_h"] = (f.available_at_utc - f.work_started_at_utc).dt.total_seconds() / 3600
    f["local_hour"] = f.opened_at_local.dt.hour
    f["repair_cost_usd"] = f.direct_cost_cents / 100
    return f.sort_values("opened_at_utc").reset_index(drop=True)


def roster() -> pd.DataFrame:
    r = load("5_optional/shift_roster.parquet")
    r = r[r.role == "slot_tech"].copy()
    r["start_utc"], r["end_utc"] = pd.to_datetime(r.start_utc), pd.to_datetime(r.end_utc)
    return r[["gaming_date", "shift", "start_utc", "end_utc", "actual_headcount"]]


def hour_value(v: pd.DataFrame) -> pd.DataFrame:
    """Theo per down hour by (machine, local hour, Fri–Sun): machine rate × zone hour index."""
    mh = pd.read_parquet(ROOT / "data/5_optional/machine_hour.parquet",
                         columns=["machine_id", "gaming_date", "local_hour", "active", "available_seconds", "coin_in_cents"])
    mh = mh[mh.active].copy()
    mh["gaming_date"] = pd.to_datetime(mh.gaming_date)
    mh = mh.merge(v[["machine_id", "gaming_date", "zone_id"]], on=["machine_id", "gaming_date"], how="left")
    mh["fri_sun"] = mh.gaming_date.dt.dayofweek >= 4
    cell = mh.groupby(["zone_id", "fri_sun", "local_hour"])[["coin_in_cents", "available_seconds"]].sum()
    zone = mh.groupby("zone_id")[["coin_in_cents", "available_seconds"]].sum()
    idx = (cell.coin_in_cents / cell.available_seconds) / (zone.coin_in_cents / zone.available_seconds).reindex(
        cell.index.get_level_values("zone_id")).to_numpy()
    return idx.rename("hour_index").reset_index()


def value_faults(f: pd.DataFrame, v: pd.DataFrame) -> pd.DataFrame:
    rate = v.groupby("machine_id").theo_usd.sum() / v.groupby("machine_id").available_hours.sum()
    md = v[["machine_id", "gaming_date", "zone_id", "manufacturer"]]
    f = f.merge(md, left_on=["machine_id", f.opened_at_local.dt.normalize() - pd.to_timedelta((f.local_hour < 6).astype(int), "D")],
                right_on=["machine_id", "gaming_date"], how="left")
    f["fri_sun"] = f.gaming_date.dt.dayofweek >= 4
    f = f.merge(hour_value(v), on=["zone_id", "fri_sun", "local_hour"], how="left")
    f["theo_per_down_h"] = f.machine_id.map(rate) * f.hour_index.fillna(1.0)
    return f


# ----------------------------------------------------------------------------- 1. fault-rate GLM
def fault_rate_model(v: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    m = load("2_machine_decision/machines.parquet")[["machine_id", "install_date"]]
    d = v.merge(m, on="machine_id", how="left")
    d["age_years"] = (d.gaming_date - pd.to_datetime(d.install_date)).dt.days / 365.25
    d["exposure_h"] = d.available_hours + d.downtime_hours
    d["log_occ"] = np.log1p(d.occupied_hours)
    d = d[d.exposure_h > 0]
    tr, te = split_by_date(d)
    form = "faults_opened ~ C(manufacturer) + C(volatility_class) + age_years + log_occ"
    nb = smf.glm(form, tr, family=sm.families.NegativeBinomial(alpha=1.0), offset=np.log(tr.exposure_h)).fit()
    # estimate the NB dispersion by profile (statsmodels' discrete NB for alpha, then refit GLM)
    alpha = smf.negativebinomial(form, tr, offset=np.log(tr.exposure_h)).fit(disp=False).params["alpha"]
    nb = smf.glm(form, tr, family=sm.families.NegativeBinomial(alpha=alpha), offset=np.log(tr.exposure_h)).fit()
    te = te.assign(pred_nb=nb.predict(te, offset=np.log(te.exposure_h)))
    fleet = tr.faults_opened.sum() / tr.exposure_h.sum()
    mfr = tr.groupby("manufacturer").faults_opened.sum() / tr.groupby("manufacturer").exposure_h.sum()
    te["pred_fleet"] = te.exposure_h * fleet
    te["pred_mfr"] = te.exposure_h * te.manufacturer.map(mfr)
    agg = te.groupby("machine_id")[["faults_opened", "pred_nb", "pred_fleet", "pred_mfr"]].sum()
    scores = pd.DataFrame([{"target": "Faults per machine, May–Jun", "model": name,
                            "MAE": np.mean(np.abs(agg[c] - agg.faults_opened)),
                            "RMSE": np.sqrt(np.mean((agg[c] - agg.faults_opened) ** 2)),
                            "bias": np.mean(agg[c] - agg.faults_opened), "n": len(agg)}
                           for name, c in [("Fleet rate (baseline)", "pred_fleet"), ("Manufacturer rate", "pred_mfr"),
                                           ("NB GLM", "pred_nb")]])
    irr = pd.DataFrame({"rate_ratio": np.exp(nb.params), "lo95": np.exp(nb.conf_int()[0]),
                        "hi95": np.exp(nb.conf_int()[1]), "p": nb.pvalues})
    irr.attrs["alpha"] = alpha
    return scores, irr


# ----------------------------------------------------------------------------- 2. queue replay
def replay(f: pd.DataFrame, r: pd.DataFrame, extra: dict[str, int] | None = None) -> np.ndarray:
    """FIFO replay of faults through tech shifts. Returns simulated wait hours per fault.

    Each roster row contributes `actual_headcount` (+ extra[shift]) techs, available from shift start
    to shift end; a tech who starts a job before shift end finishes it. Fix times are the actual ones.
    """
    extra = extra or {}
    techs = []  # [start, end, free_at] in hours since epoch
    t0 = pd.Timestamp("2024-12-31")
    for row in r.itertuples():
        s, e = (row.start_utc - t0) / pd.Timedelta(hours=1), (row.end_utc - t0) / pd.Timedelta(hours=1)
        for _ in range(int(row.actual_headcount) + extra.get(row.shift, 0)):
            techs.append([s, e, s])
    T = np.array(techs)
    arr = ((f.opened_at_utc - t0) / pd.Timedelta(hours=1)).to_numpy()
    fix = f.fix_h.to_numpy()
    waits = np.empty(len(f))
    for i, (a, d) in enumerate(zip(arr, fix)):
        start = np.maximum(np.maximum(T[:, 2], T[:, 0]), a)
        ok = start < T[:, 1]
        j = np.flatnonzero(ok)[np.argmin(start[ok])]
        waits[i] = start[j] - a
        T[j, 2] = start[j] + d
    return waits


def tech_scenarios(f: pd.DataFrame, r: pd.DataFrame, days_in_window: int) -> tuple[pd.DataFrame, dict]:
    base = replay(f, r)
    shift_of = pd.cut(f.local_hour, bins=[-1, 5, 13, 21, 23], labels=["grave", "day", "swing", "grave2"]).astype(str)
    shift_of = shift_of.replace({"grave2": "grave"})
    calib = pd.DataFrame({"actual_wait_h": f.wait_h, "sim_wait_h": base, "shift": shift_of}).groupby("shift").mean()
    cost = load("2_machine_decision/action_catalog.parquet").set_index("action_type_id").loc["A-TECH-SHIFT"]
    rows = []
    for sh in ["day", "swing", "grave"]:
        w = replay(f, r, {sh: 1})
        saved_h = base - w
        theo = saved_h * f.theo_per_down_h.to_numpy()
        rows.append({"scenario": f"+1 tech on {sh} shift", "down_hours_saved_6mo": saved_h.sum(),
                     "theo_saved_6mo": np.nansum(theo), "theo_saved_30d": np.nansum(theo) * 30 / days_in_window,
                     "cost_30d": cost.unit_cost_cents / 100,
                     "net_30d": np.nansum(theo) * 30 / days_in_window - cost.unit_cost_cents / 100})
    info = {"sim_mean_wait_h": base.mean(), "actual_mean_wait_h": f.wait_h.mean(),
            "sim_vs_actual_corr": np.corrcoef(base, f.wait_h)[0, 1], "calibration_by_shift": calib}
    return pd.DataFrame(rows), info


# ----------------------------------------------------------------------------- 4. preventive break-even
def preventive_breakeven(f: pd.DataFrame, v: pd.DataFrame, days_in_window: int) -> pd.DataFrame:
    a = load("2_machine_decision/action_catalog.parquet").set_index("action_type_id").loc["A-PREVENTIVE"]
    f = f.assign(down_h=f.wait_h + f.fix_h, lost_theo=lambda x: x.down_h * x.theo_per_down_h)
    g = f.groupby("manufacturer").agg(faults=("operation_id", "size"), lost_theo=("lost_theo", "sum"),
                                      repair_cost=("repair_cost_usd", "sum"), down_h=("down_h", "sum"))
    n_mach = v.groupby("manufacturer").machine_id.nunique()
    quiet_rate = v.groupby("manufacturer").theo_usd.sum() / v.groupby("manufacturer").available_hours.sum() * 0.3
    g["machines"] = n_mach
    g["theo_plus_repair_per_30d"] = (g.lost_theo + g.repair_cost) * 30 / days_in_window
    g["sweep_cost"] = a.unit_cost_cents / 100 + g.machines * a.downtime_minutes / 60 * quiet_rate  # + own downtime (quiet hours ≈ 0.3× avg)
    g["breakeven_fault_reduction"] = g.sweep_cost / g.theo_plus_repair_per_30d
    g["faults_per_machine_month"] = g.faults / g.machines / (days_in_window / 30)
    return g.reset_index()


def run(v: pd.DataFrame):
    f = value_faults(faults(), v)
    r = roster()
    days = v.gaming_date.nunique()
    fr_scores, irr = fault_rate_model(v)
    scen, qinfo = tech_scenarios(f, r, days)
    prev = preventive_breakeven(f, v, days)
    wait_by_hour = f.groupby("local_hour").agg(faults=("operation_id", "size"), mean_wait_h=("wait_h", "mean"),
                                                mean_fix_h=("fix_h", "mean")).reset_index()
    return {"fault_scores": fr_scores, "fault_irr": irr, "tech_scenarios": scen, "queue_info": qinfo,
            "preventive": prev, "wait_by_hour": wait_by_hour, "faults": f}
