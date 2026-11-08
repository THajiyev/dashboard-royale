"""Iteration 5: locals / non-locals segment forecast (as pre-registered in PREREG.md).

make_seg(combo, beta) -> f(train, future, "theo_usd") for the harness (theo only; segments are theo-defined).

  combo = "bottom_up": EL2 + 28-day anchor base for each segment, times each segment's own event lift, summed.
  combo = "top_down" : EL2 + 28-day anchor base on the floor total, times the share-weighted segment lift.
  beta              : LVCVA season_yoy city index ** beta, applied to the non-local segment only.

Segment lift for event e, segment g:  lift_g = L_type(e) * exp(delta_g),
  L_type  = floor-level EL2 event-type lift (event-level hierarchy, k_ev = 0.5),
  delta_g = mean over past events of that type of log(r_g / r_total), shrunk toward a fixed prior delta0_g with
            pseudo-count k_ev events; delta0 = 0, except for locals-targeted events (name contains "Locals"),
            where delta0_L = 0 and delta0_N = -log L_type (the type lift goes to locals only).
Only rows dated <= origin and events announced by the origin are used.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent.parent)); sys.path.insert(0, str(HERE))
from ds_alpha.models import _EV, event_labels  # noqa: E402
from iter3.models import hier_lift_events  # noqa: E402
from iter4.hol_hist import city_daily  # noqa: E402
from segments import segment_day  # noqa: E402

K_EV = 0.5
ANCHOR_DAYS = 28
LOCALS_TARGETED = set(_EV[_EV.name.str.contains("Locals", case=False)].event_id)


def _base(v, dow, is_ev, dates, origin, fdow):
    """EL2 base: non-event weekday mean (for event ratios) and the anchored future base."""
    prof = pd.Series(v[~is_ev]).groupby(dow[~is_ev]).mean()
    b = pd.Series(dow).map(prof).to_numpy()
    rec = ~is_ev & (dates > origin - pd.Timedelta(days=ANCHOR_DAYS))
    ar = float(np.mean(v[rec] / b[rec])) if rec.sum() >= 5 else 1.0
    return b, pd.Series(fdow).map(prof).to_numpy() * ar, rec


def _event_ratio(v, b, ev_id, is_ev):
    return pd.Series(v[is_ev] / b[is_ev]).groupby(ev_id[is_ev]).mean()


def make_seg(combo: str = "bottom_up", beta: float = 0.0, k_ev: float = K_EV):
    def f(tr, fut, y):
        assert y == "theo_usd", "segments are defined on theo only"
        origin = tr.gaming_date.max()
        dates = pd.to_datetime(tr.gaming_date).to_numpy()
        fd = pd.to_datetime(fut.gaming_date).reset_index(drop=True)
        seg = segment_day().reindex(pd.DatetimeIndex(dates))
        lt, lf = event_labels(tr.gaming_date, origin), event_labels(fd, origin)
        is_ev = lt.event_id.notna().to_numpy()
        ev_id = lt.event_id.to_numpy()
        dow, fdow = tr.dow.to_numpy(), fd.dt.dayofweek.to_numpy()

        # city index on non-locals only
        c_tr = city_daily(tr.gaming_date, origin, "season_yoy") ** beta if beta else np.ones(len(tr))
        c_fu = city_daily(fd, origin, "season_yoy") ** beta if beta else np.ones(len(fd))
        vL = seg.locals.to_numpy()
        vN = seg.nonlocals.to_numpy() / c_tr
        vT = vL + vN

        bT, fT, rec = _base(vT, dow, is_ev, dates, origin, fdow)
        bL, fL, _ = _base(vL, dow, is_ev, dates, origin, fdow)
        bN, fN, _ = _base(vN, dow, is_ev, dates, origin, fdow)

        # floor-level type lift for each future row (EL2)
        L_type = hier_lift_events(vT[is_ev] / bT[is_ev], ev_id[is_ev], lt.event_type[is_ev].to_numpy(),
                                  lt.eclass[is_ev].to_numpy(), lf.event_type, lf.eclass, k_ev)

        # segment adjustments per past event: log(r_g / r_total)
        rT = _event_ratio(vT, bT, ev_id, is_ev)
        obs = {"L": np.log(_event_ratio(vL, bL, ev_id, is_ev) / rT),
               "N": np.log(_event_ratio(vN, bN, ev_id, is_ev) / rT)}
        typ_of = dict(zip(ev_id[is_ev], lt.event_type[is_ev]))

        lift = {"L": np.ones(len(fd)), "N": np.ones(len(fd))}
        for i, (e, t) in enumerate(zip(lf.event_id, lf.event_type)):
            if e is None:
                continue
            past = [x for x, tt in typ_of.items() if tt == t and x != e]
            for g in ("L", "N"):
                d0 = -np.log(L_type[i]) if (g == "N" and e in LOCALS_TARGETED) else 0.0
                o = obs[g].reindex(past).dropna()
                delta = (o.sum() + k_ev * d0) / (len(o) + k_ev)
                lift[g][i] = L_type[i] * np.exp(delta)

        if combo == "bottom_up":
            return fL * lift["L"] + fN * c_fu * lift["N"]
        if combo == "top_down":
            sL = vL[rec].sum() / vT[rec].sum()
            mult = sL * lift["L"] + (1 - sL) * c_fu * lift["N"]
            # base is on the city-adjusted total; non-local share gets the city index back
            return fT * mult
        raise ValueError(combo)
    return f


CANDIDATES = {f"seg {c} beta={b}": make_seg(c, b) for c in ("bottom_up", "top_down") for b in (0.0, 0.5, 1.0)}
