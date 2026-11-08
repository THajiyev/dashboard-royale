"""Iteration 6: EL x recent-demand factor (PREREG.md). EL itself (ds_alpha.models.make_typed(3, 3)) is untouched.

A variant is EL(tr, fut) * m, with m = 1 + w * (R - 1), where R is a recent level of r_t = y_t / EL_fit_t over
"eligible" training days. EL_fit_t is EL's own in-sample fit (weekday base x event lift for that day), obtained by
calling EL with the training rows as the "future" - so no EL internals are reimplemented.

Leakage: everything is computed from `tr`, which holds rows dated <= origin; event labels use announced_date <= origin.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent.parent)]
import harness  # noqa: E402
from ds_alpha.models import event_labels, make_typed  # noqa: E402

EL = make_typed(3, 3)
CLOSURE = (pd.Timestamp("2025-03-03"), pd.Timestamp("2025-04-06"))  # walkway closure (same as iter3)
MIN_DAYS, MIN_DOW_DAYS, DOW_K = 4, 2, 2.0


@dataclass(frozen=True)
class Spec:
    stat: str      # "mean" | "ema" | "dow"
    span: int      # window length L (mean, dow) or half-life h (ema), in days
    mode: str      # "excl" | "excl_clo" | "delift" | "raw"
    w: float       # strength

    @property
    def name(self):
        s = {"mean": f"mean{self.span}d", "ema": f"ema hl{self.span}d", "dow": f"weekday{self.span}d"}[self.stat]
        return f"EL x {s} [{self.mode}] w={int(self.w * 100)}%"


def ratios(tr: pd.DataFrame, y: str, mode: str, el_fit: np.ndarray | None = None):
    """(r_t, eligible mask) for training days under an event-handling mode."""
    origin = tr.gaming_date.max()
    fit = EL(tr, tr[harness.FUTURE_COLS], y) if el_fit is None else el_fit
    is_ev = event_labels(tr.gaming_date, origin).event_id.notna().to_numpy()
    v = tr[y].to_numpy(float)
    if mode == "raw":  # measure against the weekday base only: event spikes leak into the level
        r, ok = v / tr.dow.map(tr[~is_ev].groupby("dow")[y].mean()).to_numpy(), np.ones(len(tr), bool)
    else:
        r = v / fit
        ok = ~is_ev if mode in ("excl", "excl_clo") else np.ones(len(tr), bool)
        if mode == "excl_clo":
            d = tr.gaming_date.to_numpy()
            ok &= ~((d >= CLOSURE[0].to_datetime64()) & (d <= CLOSURE[1].to_datetime64()))
    return r, ok


def recent_factor(tr, fut, y, spec: Spec, el_fit=None) -> np.ndarray:
    """Per-future-row multiplier m (all 1 when there is too little recent evidence)."""
    origin = tr.gaming_date.max()
    r, ok = ratios(tr, y, spec.mode, el_fit)
    age = (origin - tr.gaming_date).dt.days.to_numpy()
    one = np.ones(len(fut))
    if spec.stat == "ema":
        if ok.sum() < MIN_DAYS:
            return one
        wt = 0.5 ** (age[ok] / spec.span)
        R = np.full(len(fut), np.sum(wt * r[ok]) / wt.sum())
    else:
        sel = ok & (age < spec.span)
        if sel.sum() < MIN_DAYS:
            return one
        R_all = r[sel].mean()
        if spec.stat == "mean":
            R = np.full(len(fut), R_all)
        else:  # weekday-specific, shrunk toward the window's all-day level
            dow = tr.dow.to_numpy()
            Rd = {}
            for k in range(7):
                x = r[sel & (dow == k)]
                Rd[k] = (x.sum() + DOW_K * R_all) / (len(x) + DOW_K) if len(x) >= MIN_DOW_DAYS else R_all
            R = fut.dow.map(Rd).to_numpy(float)
    return 1 + spec.w * (R - 1)


def make(spec: Spec):
    def f(tr, fut, y):
        return EL(tr, fut, y) * recent_factor(tr, fut, y, spec)
    f.spec = spec
    return f


STATS = [("mean", 7), ("mean", 14), ("mean", 28), ("ema", 7), ("ema", 14), ("ema", 28), ("dow", 28), ("dow", 56)]
MODES = ["excl", "excl_clo", "delift", "raw"]
WEIGHTS = [0.25, 0.5, 0.75, 1.0]
GRID = [Spec(s, L, m, w) for s, L in STATS for m in MODES for w in WEIGHTS]
assert len(GRID) == 128
