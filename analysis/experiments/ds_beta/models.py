"""ds-beta candidate forecasts: robust / recency / loss-aligned / combination variants of B2.

Every model is f(train, future, target) -> np.ndarray. All cutoffs are derived from train.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))
import harness  # noqa: E402
import forecast  # noqa: E402


# ---------------------------------------------------------------- building blocks
def _wavg(x, w):
    return float(np.sum(x * w) / np.sum(w))


def _wmedian(x, w):
    o = np.argsort(x)
    x, w = np.asarray(x)[o], np.asarray(w)[o]
    c = np.cumsum(w) / w.sum()
    return float(x[np.searchsorted(c, 0.5)])


def _huber(x, c=1.345):
    x = np.asarray(x, float)
    mu = np.median(x)
    s = stats.median_abs_deviation(x, scale="normal") or 1.0
    for _ in range(50):
        r = (x - mu) / s
        w = np.minimum(1, c / np.maximum(np.abs(r), 1e-12))
        mu = np.sum(w * x) / np.sum(w)
    return float(mu)


def _weights(tr, half_life):
    if half_life is None:
        return np.ones(len(tr))
    age = (tr.gaming_date.max() - tr.gaming_date).dt.days.to_numpy()
    return 0.5 ** (age / half_life)


def b2_family(loc="mean", half_life=None, lift="mean", lift_shrink=1.0, trim=0.2, scale=1.0):
    """Weekday base from non-event days (location estimator `loc`, optional recency weights)
    x pooled event lift (`lift` estimator, shrunk toward 1 by `lift_shrink`)."""
    def f(tr, fut, y):
        w = _weights(tr, half_life)
        ne = tr.event.to_numpy() == 0
        base = {}
        for d in range(7):
            m = ne & (tr.dow.to_numpy() == d)
            x, ww = tr[y].to_numpy()[m], w[m]
            if loc == "mean":
                base[d] = _wavg(x, ww)
            elif loc == "median":
                base[d] = _wmedian(x, ww)
            elif loc == "trim":
                base[d] = stats.trim_mean(x, trim)
            elif loc == "huber":
                base[d] = _huber(x)
        ev = tr[tr.event == 1]
        if len(ev):
            r = (ev[y] / ev.dow.map(base)).to_numpy()
            L = {"mean": np.mean, "median": np.median, "ratio": None}[lift]
            L = r.mean() if lift == "mean" else (np.median(r) if lift == "median"
                                                  else ev[y].sum() / ev.dow.map(base).sum())
        else:
            L = 1.0
        L = 1 + lift_shrink * (L - 1)
        return fut.dow.map(base).to_numpy() * np.where(fut.event == 1, L, 1.0) * scale
    return f


def lad(trend=False, log=True, q=0.5):
    """Quantile (LAD) regression: y ~ weekday + event + holiday [+ t]."""
    def f(tr, fut, y):
        X, Xf = forecast.design(tr, trend), forecast.design(fut, trend)
        yy = np.log(tr[y]) if log else tr[y]
        r = sm.QuantReg(yy, X).fit(q=q, max_iter=5000)
        p = r.predict(Xf)
        return np.exp(p) if log else np.asarray(p)
    return f


def combo(fs, ws):
    def f(tr, fut, y):
        return sum(w * np.asarray(g(tr, fut, y)) for g, w in zip(fs, ws))
    return f


B2 = forecast.m_b2


def run(name, f, target="theo_usd"):
    r = harness.cv(f, target)
    print(f"{name:45s} cv={r['cv_mae']:9.1f} b2={r['cv_mae_b2']:9.1f} skill={r['cv_skill_vs_b2']:+.3f} won={r['folds_won']}/{r['folds']}")
    return r
