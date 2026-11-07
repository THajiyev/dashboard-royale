"""Iteration 3: structural zone model ("ZS") and weekly-refresh forecasting.

ZS builds the property base bottom-up so one-off disruptions don't leak into the level:
- per zone, theo (or coin-in) per active machine, so the Pit's 72 -> 80 machines (Mar 24) is a capacity change,
  not a demand change; the future uses each zone's machine count on the origin date;
- the walkway closure window (Mar 3 - Apr 6) is excluded from every zone's base, because it pushed play
  out of Back Forty into the other zones; if the origin falls inside the closure, future closure days get each
  zone's measured closure ratio;
- the event lift is EL's hierarchy (pooled -> business/leisure -> type), measured against the ZS base;
- optional pooled log-linear trend across zones, fitted on clean days only, damped (phi per day).

Everything uses only rows dated <= origin and events announced by the origin.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))
from common import load  # noqa: E402
from ds_alpha.models import EVENT_CLASS, event_labels  # noqa: E402

CLOSURE = (pd.Timestamp("2025-03-03"), pd.Timestamp("2025-04-06"))
_Z = None


def zone_day() -> pd.DataFrame:
    global _Z
    if _Z is None:
        v = load("1_prepared_views/prepared_daily_view.parquet")
        v = v[v.active]
        z = v.groupby(["gaming_date", "zone_id"]).agg(theo_usd=("theo_usd", "sum"), coin_in_usd=("coin_in_usd", "sum"),
                                                       n=("machine_id", "nunique")).reset_index()
        z["gaming_date"] = pd.to_datetime(z.gaming_date)
        z["dow"] = z.gaming_date.dt.dayofweek
        z["t"] = (z.gaming_date - pd.Timestamp("2025-01-01")).dt.days.astype(float)
        _Z = z
    return _Z


def _shrunk(x, prior, k):
    x = pd.Series(x)
    return (len(x) * x.mean() + k * prior) / (len(x) + k) if len(x) else prior


def hier_lift(ratio, typ, cls, f_typ, f_cls, k=3.0):
    """EL's hierarchy: pooled -> class -> type, pseudo-count k at each level."""
    r = pd.Series(ratio)
    pooled = r.mean() if len(r) else 1.0
    cl = {c: _shrunk(x, pooled, k) for c, x in r.groupby(np.asarray(cls))}
    ty = {t: _shrunk(x, cl[EVENT_CLASS.get(t, "leisure")], k) for t, x in r.groupby(np.asarray(typ))}
    return np.array([1.0 if t is None else ty.get(t, cl.get(c, pooled)) for t, c in zip(f_typ, f_cls)])


def in_closure(d):
    d = pd.to_datetime(pd.Series(d)).to_numpy()
    return (d >= CLOSURE[0].to_datetime64()) & (d <= CLOSURE[1].to_datetime64())


def make_zs(trend_phi: float | None = None, anchor_w: float = 0.0, anchor_days: int = 14,
            exclude_closure: bool = True, per_machine: bool = True, k: float = 3.0):
    """Zone-structural forecast. anchor_w blends in the recent level (last `anchor_days` clean days)."""
    def f(tr, fut, y):
        origin = tr.gaming_date.max()
        z = zone_day()
        z = z[z.gaming_date <= origin].copy()
        lab = event_labels(z.gaming_date, origin)
        z["ev"] = lab.event_id.notna().to_numpy()
        z["clo"] = in_closure(z.gaming_date)
        z["u"] = z[y] / z.n if per_machine else z[y]
        clean = ~z.ev & (~z.clo if exclude_closure else True)

        fd = pd.to_datetime(fut.gaming_date).reset_index(drop=True)
        fdow, fclo = fd.dt.dayofweek.to_numpy(), in_closure(fd)
        h = (fd - origin).dt.days.to_numpy().astype(float)

        # pooled log-linear trend on clean days, zone x dow intercepts
        slope = 0.0
        if trend_phi is not None:
            c = z[clean].copy()
            c["lu"] = np.log(c.u)
            c["dm"] = c.lu - c.groupby(["zone_id", "dow"]).lu.transform("mean")
            c["tm"] = c.t - c.groupby(["zone_id", "dow"]).t.transform("mean")
            slope = float((c.dm * c.tm).sum() / (c.tm ** 2).sum())
            damp = np.array([np.sum(trend_phi ** np.arange(1, int(hh) + 1)) for hh in h])

        base_f = np.zeros(len(fut))
        base_in = pd.Series(0.0, index=z.index)
        for zid, g in z.groupby("zone_id"):
            gc = g[clean.loc[g.index]]
            if trend_phi is not None:  # profile at the origin's trend level
                lvl = gc.u * np.exp(-slope * (gc.t - (origin - pd.Timestamp("2025-01-01")).days))
                prof = lvl.groupby(gc.dow).mean()
            else:
                prof = gc.u.groupby(gc.dow).mean()
            # closure ratio for this zone (applied to future closure days only, if measurable)
            gcl = g[g.clo & ~g.ev]
            cr = float(np.mean(gcl.u / gcl.dow.map(prof))) if len(gcl) >= 5 else 1.0
            # recent-level anchor on clean days
            rec = gc[gc.gaming_date > origin - pd.Timedelta(days=anchor_days)]
            ar = float(np.mean(rec.u / rec.dow.map(prof))) if (anchor_w and len(rec) >= 5) else 1.0
            level = (1 - anchor_w) + anchor_w * ar
            n_now = g[g.gaming_date == origin].n.iloc[0] if per_machine and (g.gaming_date == origin).any() else 1.0
            mult = np.where(fclo, cr, 1.0) * level
            if trend_phi is not None:
                mult = mult * np.exp(slope * damp)
            base_f += pd.Series(fdow).map(prof).to_numpy() * n_now * mult
            # in-sample base for the same zone (to measure event ratios at property level)
            ins = g.dow.map(prof).to_numpy() * (g.n.to_numpy() if per_machine else 1.0) * np.where(g.clo, cr, 1.0)
            if trend_phi is not None:
                ins = ins * np.exp(slope * (g.t.to_numpy() - (origin - pd.Timestamp("2025-01-01")).days))
            base_in.loc[g.index] = ins

        p = z.assign(b=base_in).groupby("gaming_date").agg(y=(y, "sum"), b=("b", "sum")).reset_index()
        pl = event_labels(p.gaming_date, origin)
        ev = pl.event_id.notna().to_numpy()
        fl = event_labels(fd, origin)
        lift = hier_lift((p.y / p.b).to_numpy()[ev], pl.event_type[ev].to_numpy(), pl.eclass[ev].to_numpy(),
                         fl.event_type, fl.eclass, k)
        return base_f * lift
    return f


def make_el_anchor(anchor_w: float, anchor_days: int = 14):
    """Property-level EL with its base blended toward the recent clean level (for weekly refresh)."""
    sys.path.insert(0, str(HERE.parent / "iter2"))
    from iter2.models import el_lifts  # noqa

    def f(tr, fut, y):
        origin = tr.gaming_date.max()
        lt, lf, is_ev = el_lifts(tr, fut, y)
        ok = ~is_ev
        prof = tr[ok].groupby("dow")[y].mean()
        rec = tr[ok & (tr.gaming_date > origin - pd.Timedelta(days=anchor_days)).to_numpy()]
        ar = float(np.mean(rec[y] / rec.dow.map(prof))) if len(rec) >= 5 else 1.0
        return fut.dow.map(prof).to_numpy() * ((1 - anchor_w) + anchor_w * ar) * lf
    return f


# ----------------------------------------------------------------------------- event-level evidence (round 2)
def hier_lift_events(ratio, ev_id, typ, cls, f_typ, f_cls, k_ev=1.0):
    """Like hier_lift, but each *event* is one observation (its mean daily ratio), with pseudo-count k_ev events.
    Days inside one event share one shock, so a 3-day event is one piece of evidence, not three."""
    d = pd.DataFrame({"r": ratio, "e": ev_id, "t": typ, "c": cls}).groupby("e").agg(r=("r", "mean"), t=("t", "first"),
                                                                                  c=("c", "first"))
    pooled = d.r.mean() if len(d) else 1.0
    cl = {c: _shrunk(g.r, pooled, k_ev) for c, g in d.groupby("c")}
    ty = {t: _shrunk(g.r, cl[EVENT_CLASS.get(t, "leisure")], k_ev) for t, g in d.groupby("t")}
    return np.array([1.0 if t is None else ty.get(t, cl.get(c, pooled)) for t, c in zip(f_typ, f_cls)])


def make_el2(anchor_w: float = 0.0, anchor_days: int = 28, k_ev: float = 1.0, half_life=None):
    """Property-level EL with event-level shrinkage and optional recent-level anchor."""
    def f(tr, fut, y):
        origin = tr.gaming_date.max()
        lt, lf = event_labels(tr.gaming_date, origin), event_labels(fut.gaming_date, origin)
        is_ev = lt.event_id.notna().to_numpy()
        v = tr[y].to_numpy()
        prof = tr[~is_ev].groupby("dow")[y].mean()
        b = tr.dow.map(prof).to_numpy()
        lift = hier_lift_events(v[is_ev] / b[is_ev], lt.event_id[is_ev].to_numpy(), lt.event_type[is_ev].to_numpy(),
                                lt.eclass[is_ev].to_numpy(), lf.event_type, lf.eclass, k_ev)
        rec = ~is_ev & (tr.gaming_date > origin - pd.Timedelta(days=anchor_days)).to_numpy()
        ar = float(np.mean(v[rec] / b[rec])) if (anchor_w and rec.sum() >= 5) else 1.0
        return fut.dow.map(prof).to_numpy() * ((1 - anchor_w) + anchor_w * ar) * lift
    return f


# ----------------------------------------------------------------------------- ongoing-event update (round 3)
def make_el3(anchor_w: float = 1.0, anchor_days: int = 28, k_ev: float = 0.5, ongoing_k: float | None = 3.0):
    """EL2 + anchor, and for an event already under way at the origin, its own observed lift (vs the anchored
    base) is blended with the prior lift using a pseudo-count of `ongoing_k` days."""
    base_f = make_el2(anchor_w, anchor_days, k_ev)

    def f(tr, fut, y):
        p = base_f(tr, fut, y)
        if ongoing_k is None:
            return p
        origin = tr.gaming_date.max()
        lt, lf = event_labels(tr.gaming_date, origin), event_labels(fut.gaming_date, origin)
        is_ev = lt.event_id.notna().to_numpy()
        v = tr[y].to_numpy()
        prof = tr[~is_ev].groupby("dow")[y].mean()
        b = tr.dow.map(prof).to_numpy()
        rec = ~is_ev & (tr.gaming_date > origin - pd.Timedelta(days=anchor_days)).to_numpy()
        lvl = (1 - anchor_w) + anchor_w * (float(np.mean(v[rec] / b[rec])) if rec.sum() >= 5 else 1.0)
        fb = fut.dow.map(prof).to_numpy() * lvl
        prior = p / fb
        for e in set(lf.event_id.dropna()) & set(lt.event_id.dropna()):
            obs = (lt.event_id == e).to_numpy()
            n, m = obs.sum(), np.mean(v[obs] / (b[obs] * lvl))
            sel = (lf.event_id == e).to_numpy()
            prior[sel] = (n * m + ongoing_k * prior[sel]) / (n + ongoing_k)
        return fb * prior
    return f
