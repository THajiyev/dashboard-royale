"""ds-alpha: structural forecasts for daily property theo / coin-in.

Every model is f(train, future, target) -> np.ndarray. Cutoffs are always derived from train.
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

# A priori taxonomy (fixed before looking at any holdout number): why the visitor is in town.
# Business travel (conventions) brings attendees with little gaming time; leisure events
# (sports viewing weekends, festivals, the property's own slot promotions) bring gamers.
EVENT_CLASS = {"convention": "business", "sports_viewing": "leisure", "festival": "leisure",
               "property_promotion": "leisure"}

_EV = load("4_context/events.parquet")
_EV["start_date"] = pd.to_datetime(_EV.start_date)
_EV["end_date"] = pd.to_datetime(_EV.end_date)
_EV["announced_date"] = pd.to_datetime(_EV.announced_date)


def event_labels(dates: pd.Series, origin: pd.Timestamp) -> pd.DataFrame:
    """Per date: event_id, event_type, class for events announced by `origin` (None if none)."""
    ev = _EV[_EV.announced_date <= origin]
    d = pd.to_datetime(pd.Series(dates).reset_index(drop=True))
    out = pd.DataFrame({"event_id": [None] * len(d), "event_type": [None] * len(d), "eclass": [None] * len(d)})
    for _, r in ev.iterrows():
        m = ((d >= r.start_date) & (d <= r.end_date)).to_numpy()
        out.loc[m, "event_id"] = r.event_id
        out.loc[m, "event_type"] = r.event_type
        out.loc[m, "eclass"] = EVENT_CLASS.get(r.event_type, "leisure")
    return out


def _shrink(ratios: pd.Series, groups: pd.Series, prior: float, k: float) -> dict:
    """Empirical-Bayes style: group mean shrunk toward prior with pseudo-count k (in days)."""
    out = {}
    for g, r in ratios.groupby(groups.to_numpy()):
        n = len(r)
        out[g] = (n * r.mean() + k * prior) / (n + k)
    return out


def make_typed(k_class: float = 3.0, k_type: float = 3.0, k_event: float | None = None):
    """B2 base (non-event weekday mean) x hierarchical event lift: pooled -> class -> type (-> event)."""
    def f(tr, fut, y):
        origin = tr.gaming_date.max()
        lt, lf = event_labels(tr.gaming_date, origin), event_labels(fut.gaming_date, origin)
        is_ev = lt.event_id.notna().to_numpy()
        base = tr[~is_ev].groupby("dow")[y].mean()
        r = pd.Series(tr[y].to_numpy()[is_ev] / tr.dow.map(base).to_numpy()[is_ev])
        cls, typ = lt.eclass[is_ev].reset_index(drop=True), lt.event_type[is_ev].reset_index(drop=True)
        pooled = r.mean() if len(r) else 1.0
        cl = _shrink(r, cls, pooled, k_class)
        ty = {t: (len(rr) * rr.mean() + k_type * cl[c]) / (len(rr) + k_type)
              for (t, c), rr in r.groupby([typ.to_numpy(), cls.to_numpy()])}
        lift = np.ones(len(fut))
        for i, (t, c) in enumerate(zip(lf.event_type, lf.eclass)):
            if t is None:
                continue
            lift[i] = ty.get(t, cl.get(c, pooled))
        return fut.dow.map(base).to_numpy() * lift
    return f


def m_b2_lab(tr, fut, y):
    """B2 reproduced via event_labels (sanity check)."""
    origin = tr.gaming_date.max()
    lt, lf = event_labels(tr.gaming_date, origin), event_labels(fut.gaming_date, origin)
    is_ev = lt.event_id.notna().to_numpy()
    base = tr[~is_ev].groupby("dow")[y].mean()
    r = tr[y].to_numpy()[is_ev] / tr.dow.map(base).to_numpy()[is_ev]
    return fut.dow.map(base).to_numpy() * np.where(lf.event_id.notna(), r.mean(), 1.0)
