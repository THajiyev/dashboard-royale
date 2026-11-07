"""Phase 0 baselines: the simplest defensible benchmarks every later model must be compared with."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from common import TRAIN_END, WEEK, load, score, split_by_date

TARGETS = {"theo_usd": "Expected revenue (theo)", "coin_in_usd": "Coin-in", "house_win_usd": "House win"}


def known_event_days(dates: pd.Series, as_of: pd.Timestamp = TRAIN_END) -> np.ndarray:
    """True on dates covered by an event that had been announced by the forecast date.

    Events announced after `as_of` (e.g. the Locals Appreciation Week, announced 2025-05-26)
    could not have been in a forecast frozen on Apr 30, so they are ignored.
    """
    ev = load("4_context/events.parquet")
    ev = ev[pd.to_datetime(ev.announced_date) <= as_of]
    d = pd.to_datetime(dates).to_numpy()
    hit = np.zeros(len(d), bool)
    for s, e in zip(pd.to_datetime(ev.start_date), pd.to_datetime(ev.end_date)):
        hit |= (d >= s.to_datetime64()) & (d <= e.to_datetime64())
    return hit


def b0_constant_mean(train: pd.DataFrame, test: pd.DataFrame, target: str) -> np.ndarray:
    """B0: training-period mean daily value, flat over the holdout."""
    return np.full(len(test), train[target].mean())


def b1_weekday_mean(train: pd.DataFrame, test: pd.DataFrame, target: str) -> np.ndarray:
    """B1: training-period mean by weekday (GUIDE §7 beginner route)."""
    m = train.groupby("local_weekday")[target].mean()
    return test.local_weekday.map(m).to_numpy()


def b2_event_aware_weekday(train: pd.DataFrame, test: pd.DataFrame, target: str) -> tuple[np.ndarray, float]:
    """B2: weekday mean from non-event training days × one pooled event lift on pre-announced event days.

    B1's weekday means include 26 Jan–Apr event days (lift 1.01–1.22), which inflates every
    ordinary holdout day and still under-forecasts the EDC weekend. Both inputs are known on Apr 30.
    Returns (predictions, lift).
    """
    base = train[~train.known_event].groupby("local_weekday")[target].mean()
    ev = train[train.known_event]
    lift = float((ev[target] / ev.local_weekday.map(base)).mean())
    return test.local_weekday.map(base).to_numpy() * np.where(test.known_event, lift, 1.0), lift


def property_forecast_baselines(pdays: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score B0, B1 (frozen benchmarks) and B2 (event-aware, added after review) on May–Jun."""
    pdays = pdays.assign(known_event=known_event_days(pdays.gaming_date))
    train, test = split_by_date(pdays)
    rows, preds = [], test[["gaming_date", "local_weekday", "known_event"]].copy()
    for t, label in TARGETS.items():
        p0, p1 = b0_constant_mean(train, test, t), b1_weekday_mean(train, test, t)
        p2, lift = b2_event_aware_weekday(train, test, t)
        s0, s1, s2 = score(test[t], p0), score(test[t], p1), score(test[t], p2)
        rows.append({"target": label, "model": "B0 constant mean", **s0, "skill_vs_B0": 0.0})
        rows.append({"target": label, "model": "B1 weekday mean", **s1, "skill_vs_B0": 1 - s1["MAE"] / s0["MAE"]})
        rows.append({"target": label, "model": f"B2 event-aware weekday (lift {lift:.3f})", **s2,
                     "skill_vs_B0": 1 - s2["MAE"] / s0["MAE"], "skill_vs_B1": 1 - s2["MAE"] / s1["MAE"]})
        preds[f"{t}_actual"], preds[f"{t}_B0"], preds[f"{t}_B1"], preds[f"{t}_B2"] = test[t].to_numpy(), p0, p1, p2
    return pd.DataFrame(rows), preds


def location_baseline(v: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Coin-in per available hour vs the zone average.

    Forecast use: predict each May–Jun machine-day's coin-in per available hour with the
    machine's zone mean from Jan–Apr (Z0) or the machine's own Jan–Apr mean (M0).
    Descriptive use: machine / zone ratio over the whole window.
    """
    v = v[v.available_hours > 0].copy()
    v["ci_per_hr"] = v.coin_in_usd / v.available_hours
    train, test = split_by_date(v)
    zone_rate = train.groupby("zone_id").coin_in_usd.sum() / train.groupby("zone_id").available_hours.sum()
    mach_rate = train.groupby("machine_id").coin_in_usd.sum() / train.groupby("machine_id").available_hours.sum()
    pz = test.zone_id.map(zone_rate)
    pm = test.machine_id.map(mach_rate).fillna(pz)  # machines new in May–Jun fall back to zone rate
    sz, sm = score(test.ci_per_hr, pz), score(test.ci_per_hr, pm)
    scores = pd.DataFrame([{"target": "Machine-day coin-in per available hour", "model": "Z0 zone mean (Jan–Apr)", **sz},
                           {"target": "Machine-day coin-in per available hour", "model": "M0 own machine mean (Jan–Apr)", **sm}])
    g = v.groupby(["machine_id", "zone_name"]).agg(ci=("coin_in_usd", "sum"), hrs=("available_hours", "sum")).reset_index()
    g["ci_per_hr"] = g.ci / g.hrs
    zr = v.groupby("zone_name").coin_in_usd.sum() / v.groupby("zone_name").available_hours.sum()
    g["zone_ci_per_hr"] = g.zone_name.map(zr)
    g["vs_zone"] = g.ci_per_hr / g.zone_ci_per_hr - 1
    return scores, g[["machine_id", "zone_name", "ci_per_hr", "zone_ci_per_hr", "vs_zone"]]


def downtime_baseline(v: pd.DataFrame) -> pd.DataFrame:
    """Lost play ≈ downtime hours × the machine's own coin-in (and theo) per available hour."""
    g = v.groupby(["machine_id", "zone_name", "manufacturer"]).agg(
        down_h=("downtime_hours", "sum"), avail_h=("available_hours", "sum"),
        ci=("coin_in_usd", "sum"), theo=("theo_usd", "sum")).reset_index()
    g["lost_coin_in_usd"] = g.down_h * g.ci / g.avail_h
    g["lost_theo_usd"] = g.down_h * g.theo / g.avail_h
    return g.sort_values("lost_theo_usd", ascending=False)


def downtime_hourly(v: pd.DataFrame, down: pd.DataFrame) -> pd.DataFrame:
    """Hour-aware lost play: weight each down hour by how busy that hour is.

    Faults cluster in the evening, so valuing every down hour at the machine's 24-hour average
    understates the loss. Rate for a down hour = machine's own coin-in per available hour ×
    its zone's index for that local hour and day type (Fri–Sun vs Mon–Thu); index = 1 on average.
    Still an upper bound if displaced players simply move to a neighbouring machine.
    """
    mh = pd.read_parquet(Path(__file__).resolve().parents[1] / "data/5_optional/machine_hour.parquet",
                         columns=["machine_id", "gaming_date", "local_hour", "active", "available_seconds", "coin_in_cents"])
    mh = mh[mh.active].copy()
    mh["gaming_date"] = pd.to_datetime(mh.gaming_date)
    mh = mh.merge(v[["machine_id", "gaming_date", "zone_id", "zone_name"]], on=["machine_id", "gaming_date"], how="left", validate="m:1")
    mh["fri_sun"] = mh.gaming_date.dt.dayofweek >= 4
    mh["down_h"] = (3600 - mh.available_seconds) / 3600
    cell = mh.groupby(["zone_id", "fri_sun", "local_hour"])[["coin_in_cents", "available_seconds"]].sum()
    zone = mh.groupby("zone_id")[["coin_in_cents", "available_seconds"]].sum()
    idx = (cell.coin_in_cents / cell.available_seconds) / (zone.coin_in_cents / zone.available_seconds).reindex(
        cell.index.get_level_values("zone_id")).to_numpy()
    d = mh[mh.down_h > 0].join(idx.rename("hour_index"), on=["zone_id", "fri_sun", "local_hour"])
    # key on machine AND zone: 3 machines moved zones and have one row per zone in `down`
    d = (d.down_h * d.hour_index).groupby([d.machine_id, d.zone_name]).sum().rename("busy_weighted_down_h")
    out = down.set_index(["machine_id", "zone_name"]).join(d).fillna({"busy_weighted_down_h": 0.0})
    assert abs(out.down_h.sum() - mh.down_h.sum()) < 1e-6, "down hours do not reconcile with machine_hour"
    out["lost_coin_in_hourly_usd"] = out.busy_weighted_down_h * out.ci / out.avail_h
    out["lost_theo_hourly_usd"] = out.busy_weighted_down_h * out.theo / out.avail_h
    return out.reset_index().sort_values("lost_theo_hourly_usd", ascending=False)
