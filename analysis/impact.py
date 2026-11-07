"""Change-impact model: how much did a change (closure, new machines, title swap, promotion, outage) move play?

This is retrospective. It uses all six months of data, because an impact estimate is measured after the
fact; it is not a forecast. For each change it reports:
- direct effect on the treated units: % and theo $/day vs a counterfactual;
- spillover on neighbouring units, e.g. the rest of the floor or bank-mates;
- net $/day = direct + spillover, the number that matters for the P&L;
- a 90% interval, a z-score and a verdict: Positive / Negative / Inconclusive (interval spans 0).

Two estimators, chosen by the kind of change:
- on_off: for TEMPORARY changes. The window is compared with equal-length baselines immediately before and
  after, on log daily theo with weekday effects and a linear trend, so slow drifts cancel. Event days are dropped.
- did: for PERMANENT changes. Log(treated) − log(control) gap, weekday-adjusted, pre vs post.
Intervals come from placebos (the same estimator on fake changes), not from a standard-error formula:
HAC errors under-covered badly in validation (40% coverage for a nominal 90%). `impact_validate.py` checks the
placebo intervals on fake changes and on injected effects.

Outages, i.e. slots closing temporarily, use a panel instead (`outage_recapture`): bank-days where machines are
down vs the bank's expected play, which gives the share of a down machine's play that its bank-mates pick up.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import statsmodels.api as sm

from common import OUT, load

Z90 = 1.645  # used only by outage_recapture (cluster-robust panel SE)
EVENT_DAYS: set | None = None


# ----------------------------------------------------------------------------- data
_V = None


def daily_view() -> pd.DataFrame:
    global _V
    if _V is None:
        v = load("1_prepared_views/prepared_daily_view.parquet")
        v = v[v.active].copy()
        md = load("2_machine_decision/machine_day.parquet")[["machine_id", "gaming_date", "scheduled_seconds",
                                                             "available_seconds"]]
        v = v.merge(md, on=["machine_id", "gaming_date"], how="left")
        v["gaming_date"] = pd.to_datetime(v.gaming_date)
        v["down_h"] = (v.scheduled_seconds - v.available_seconds) / 3600
        _V = v
    return _V


def event_days() -> set:
    global EVENT_DAYS
    if EVENT_DAYS is None:
        ev = load("4_context/events.parquet")
        EVENT_DAYS = set()
        for s, e in zip(pd.to_datetime(ev.start_date), pd.to_datetime(ev.end_date)):
            EVENT_DAYS |= set(pd.date_range(s, e))
    return EVENT_DAYS


def series(mask: pd.Series, metric: str = "theo_usd") -> pd.Series:
    v = daily_view()
    return v[mask].groupby("gaming_date")[metric].sum()


# ----------------------------------------------------------------------------- estimators
@dataclass
class Est:
    beta: float           # log effect
    lo: float             # 90% interval on the log scale (placebo-based)
    hi: float
    p: float              # placebo p-value (two-sided)
    n_placebo: int
    n_window: int
    level_usd: float      # actual mean $/day of the unit in the window
    extra: dict = field(default_factory=dict)

    @property
    def pct(self):
        return np.expm1(self.beta)

    @property
    def usd_day(self):  # actual − counterfactual, $/day
        return self.level_usd * (1 - np.exp(-self.beta))


def _dow(idx):
    d = pd.get_dummies(pd.DatetimeIndex(idx).dayofweek, prefix="d", drop_first=True).astype(float)
    d.index = idx
    for k in range(1, 7):
        d[f"d_{k}"] = d.get(f"d_{k}", 0.0)
    return d[[f"d_{k}" for k in range(1, 7)]]


def _mask(idx, ranges):
    m = np.zeros(len(idx), bool)
    for a, z in ranges:
        m |= (idx >= pd.Timestamp(a)) & (idx <= pd.Timestamp(z))
    return m


def on_off_beta(s: pd.Series, start, end, b: int, drop_events=True, exclude=(), window_is_event=False):
    """Log effect of window [start, end] vs `b` usable baseline days on each side (excluded days skipped).
    Event days are dropped everywhere, except inside the window when the change itself is an event."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    inw = (s.index >= start) & (s.index <= end)
    ev = s.index.isin(list(event_days()))
    usable = ~_mask(s.index, exclude)
    if drop_events:
        usable &= ~(ev & ~inw) if window_is_event else ~ev
    before = s.index[usable & (s.index < start)][-b:]
    after = s.index[usable & (s.index > end)][:b]
    if len(before) + len(after) < b or min(len(before), len(after)) < 5:
        return None
    x = s[s.index.isin(before.union(after)) | (inw & usable)]
    w = ((x.index >= start) & (x.index <= end)).astype(float)
    X = sm.add_constant(_dow(x.index).assign(t=(x.index - start).days / 30.0, w=w), has_constant="add")
    r = np.linalg.lstsq(X.to_numpy(), np.log(x.to_numpy()), rcond=None)[0]
    return float(r[-1]), float(x[w == 1].mean())


# Placebo quantiles under-cover a little (overlapping placebo windows, few long windows): 83–86% for a nominal
# 90% on 150 fake changes (seed 7). One factor for both estimators, confirmed on a fresh batch (seed 11).
CALIBRATION = 1.25
USE_CALIBRATION = True


def _summarise(beta, null, n_window, level, extra):
    null = np.asarray([n for n in null if n is not None and np.isfinite(n)])  # zero-play weeks give log(0)
    h = float(np.quantile(np.abs(null), 0.90)) if len(null) >= 10 else np.nan
    h *= CALIBRATION if USE_CALIBRATION else 1.0
    p = float((1 + np.sum(np.abs(null) >= abs(beta))) / (1 + len(null))) if len(null) else np.nan
    return Est(beta, beta - h, beta + h, p, len(null), n_window, level, extra)


def on_off(s: pd.Series, start, end, baseline_days: int | None = None, drop_events: bool = True,
           exclude: list[tuple] = (), step: int = 2, window_is_event: bool = False) -> Est:
    """Temporary change. Interval from in-time placebos: the same estimator on fake windows of the same length
    on the same series, never overlapping the real window or `exclude` (other known changes)."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    L = (end - start).days + 1
    b = baseline_days or int(np.clip(L, 14, 28))
    beta, level = on_off_beta(s, start, end, b, drop_events, exclude, window_is_event)
    avoid = list(exclude) + [(start, end)]
    null = []
    for fs in pd.date_range(s.index.min() + pd.Timedelta(days=5), s.index.max() - pd.Timedelta(days=L + 4), freq=f"{step}D"):
        fe = fs + pd.Timedelta(days=L - 1)
        if _mask(pd.date_range(fs, fe), avoid).any():
            continue
        if window_is_event and len(set(pd.date_range(fs, fe)) & event_days()):
            continue  # placebos for an event window are non-event windows of the same length
        o = on_off_beta(s, fs, fe, b, drop_events, avoid, window_is_event)
        null.append(None if o is None else o[0])
    return _summarise(beta, null, L, level, {"baseline_days": b})


def _weekly_gap(t: pd.Series, c: pd.Series, start, end, pre_days, drop_events, exclude):
    """log(sum T / sum C) over 7-day blocks anchored at `start` (full blocks only; event/excluded days dropped)."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    idx = t.index.intersection(c.index)
    idx = idx[(idx >= start - pd.Timedelta(days=pre_days)) & (idx <= end)]
    keep = ~_mask(idx, exclude)
    if drop_events:
        keep &= ~idx.isin(list(event_days()))
    idx = idx[keep]
    blk = np.floor((idx - start).days / 7).astype(int)
    g = pd.DataFrame({"t": t.reindex(idx).to_numpy(), "c": c.reindex(idx).to_numpy(), "b": blk})
    g = g.groupby("b").filter(lambda x: len(x) >= 4).groupby("b").sum()
    gap = np.log(g.t / g.c)
    return gap[gap.index < 0], gap[gap.index >= 0]


def did(treated: pd.Series, control: pd.Series, start, end=None, pre_days: int = 56, drop_events: bool = True,
        exclude: list[tuple] = (), placebo_units: dict | None = None) -> Est:
    """Permanent change: weekly log gap treated − control, post mean − pre mean.
    Interval from in-space placebos: `placebo_units` = {name: (pseudo_treated_series, its_control_series)},
    run with the same dates. Without placebos, falls back to in-time placebos on the gap."""
    end = pd.Timestamp(end) if end is not None else treated.index.max()
    pre, post = _weekly_gap(treated, control, start, end, pre_days, drop_events, exclude)
    beta = float(post.mean() - pre.mean())
    level = float(treated[(treated.index >= pd.Timestamp(start)) & (treated.index <= end)].mean())
    null = []
    for _, (pt, pc) in (placebo_units or {}).items():
        a, z = _weekly_gap(pt, pc, start, end, pre_days, drop_events, exclude)
        if len(a) and len(z):
            null.append(float(z.mean() - a.mean()))
    return _summarise(beta, null, int((end - pd.Timestamp(start)).days + 1), level,
                      {"pre_weeks": len(pre), "post_weeks": len(post)})


# ----------------------------------------------------------------------------- reporting
def row(change: str, part: str, est: Est, method: str, note: str = "") -> dict:
    lvl = est.level_usd
    usd = lambda b: lvl * (1 - np.exp(-b))
    verdict = ("Positive" if est.lo > 0 else "Negative" if est.hi < 0 else "Inconclusive") if np.isfinite(est.lo) else "n/a"
    return {"change": change, "part": part, "method": method, "effect_pct": est.pct, "lo90_pct": np.expm1(est.lo),
            "hi90_pct": np.expm1(est.hi), "theo_usd_per_day": est.usd_day, "lo90_usd_day": usd(est.lo),
            "hi90_usd_day": usd(est.hi), "placebo_p": est.p, "n_placebo": est.n_placebo, "verdict": verdict,
            "days": est.n_window, "note": note}


def net_row(change: str, parts: list[dict], days: int, note: str = "") -> dict:
    """Net = sum of parts in $/day. Interval: parts treated as independent (half-widths added in quadrature)."""
    usd = sum(p["theo_usd_per_day"] for p in parts)
    hw = np.sqrt(sum(((p["hi90_usd_day"] - p["lo90_usd_day"]) / 2) ** 2 for p in parts))
    lo, hi = usd - hw, usd + hw
    verdict = "Positive" if lo > 0 else "Negative" if hi < 0 else "Inconclusive"
    return {"change": change, "part": "NET (direct + spillover)", "method": "sum of parts", "theo_usd_per_day": usd,
            "lo90_usd_day": lo, "hi90_usd_day": hi, "verdict": verdict, "days": days,
            "theo_usd_total": usd * days, "lo90_usd_total": lo * days, "hi90_usd_total": hi * days, "note": note}


# ----------------------------------------------------------------------------- slots closing: outages
def outage_recapture() -> dict:
    """Share of a down machine's expected play that its bank-mates pick up.

    Bank-day panel. Expected play uses HOURLY data. Faults happen while machines are being played, so busy
    hours are over-represented, and a daily-average rate would understate what was lost.
    - Floor hour profile: share of a machine's daily coin-in in each local hour, by weekday/weekend.
    - Machine rate: coin-in per available hour on fully-up days, by weekday.
    - expected_full(m, day) = rate x 24; expected_lost(m, day) = rate x 24 x sum over hours of down share x profile.
    - y = bank actual / (bank expected_full x zone level from OTHER banks) − 1; x = lost / expected_full (bank).
    - y = a + b x, cluster-robust by bank. Recapture = 1 + b (b = −1: nothing recaptured; b = 0: all of it).
    """
    mh = load("5_optional/machine_hour.parquet")[["machine_id", "gaming_date", "local_hour", "active",
                                                 "available_seconds", "coin_in_cents"]]
    mh = mh[mh.active].copy()
    mh["gaming_date"] = pd.to_datetime(mh.gaming_date)
    mh["wknd"] = mh.gaming_date.dt.dayofweek >= 4
    up = mh[mh.available_seconds == 3600]
    prof = up.groupby(["wknd", "local_hour"]).coin_in_cents.sum()
    prof = prof / prof.groupby(level=0).transform("sum")  # hour share of the day, by weekday/weekend
    mh["hshare"] = prof.reindex(pd.MultiIndex.from_arrays([mh.wknd, mh.local_hour])).to_numpy()
    mh["down_frac"] = (1 - mh.available_seconds / 3600).clip(0, 1)
    lost_share = (mh.down_frac * mh.hshare).groupby([mh.machine_id, mh.gaming_date]).sum().rename("lost_share")

    v = daily_view().copy()
    v["dow"] = v.gaming_date.dt.dayofweek
    upd = v[v.down_h < 0.25]
    r = upd.groupby(["machine_id", "dow"]).apply(lambda g: g.coin_in_usd.sum() / g.available_hours.sum())
    v["typ_rate"] = r.reindex(pd.MultiIndex.from_arrays([v.machine_id, v.dow])).to_numpy()
    v = v.merge(lost_share.reset_index(), on=["machine_id", "gaming_date"], how="left")
    v["exp_full"] = v.typ_rate * 24.0
    v["exp_lost"] = v.exp_full * v.lost_share.fillna(0)
    b = v.groupby(["bank_id", "zone_id", "gaming_date"]).agg(act=("coin_in_usd", "sum"), exp=("exp_full", "sum"),
                                                              lost=("exp_lost", "sum"), n=("machine_id", "size")).reset_index()
    z = b.groupby(["zone_id", "gaming_date"])[["act", "exp"]].transform("sum")
    b["zone_lvl_other"] = (z.act - b.act) / (z.exp - b.exp)
    b = b[(b.n >= 3) & np.isfinite(b.zone_lvl_other) & np.isfinite(b.exp) & ~b.gaming_date.isin(list(event_days()))]
    b["y"] = b.act / (b.exp * b.zone_lvl_other) - 1
    b["x"] = b.lost / b.exp
    out = {}
    for label, d in [("all outage bank-days", b), ("outages >= 5% of bank play", b[(b.x == 0) | (b.x >= 0.05)])]:
        fit = sm.OLS(d.y, sm.add_constant(d[["x"]])).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d.bank_id)[0]})
        sl, se = fit.params["x"], fit.bse["x"]
        out[label] = {"recapture_share": 1 + sl, "lo90": 1 + sl - Z90 * se, "hi90": 1 + sl + Z90 * se,
                      "bank_days": len(d), "bank_days_with_outage": int((d.x > 0.005).sum()),
                      "mean_lost_share_when_down": float(d.x[d.x > 0.005].mean())}
    return out
