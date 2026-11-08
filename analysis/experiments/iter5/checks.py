"""Pre-modelling checks (PREREG.md, bias control 3), plus the walkway minimum-detectable-loss statement.

1. Locals Week DiD: log(locals) - log(non-locals), event week vs 14 baseline days each side, in-time placebos.
2. Displacement: change in non-local theo per machine, by tercile of the locals' share of that machine's play.
3. Walkway closure: the 95% version of the existing placebo interval on the whole-floor net.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent)); sys.path.insert(0, str(HERE))
import impact  # noqa: E402
from segments import segment_day, machine_segment  # noqa: E402

LW = (pd.Timestamp("2025-06-09"), pd.Timestamp("2025-06-15"))


def did():
    s = segment_day()
    rows = []
    for name, x in [("floor total", s.total), ("locals", s.locals), ("non-locals (incl. uncarded)", s.nonlocals),
                    ("carded non-locals", s.carded_nonlocals),
                    ("DiD: locals / non-locals", s.locals / s.nonlocals),
                    ("DiD: locals / carded non-locals", s.locals / s.carded_nonlocals)]:
        e = impact.on_off(x, *LW, baseline_days=14, window_is_event=True)
        rows.append({"series": name, "effect": e.pct, "lo90": np.expm1(e.lo), "hi90": np.expm1(e.hi),
                     "placebo_p": e.p, "n_placebo": e.n_placebo})
    return pd.DataFrame(rows)


def displacement():
    wk = machine_segment(*LW)
    pre = machine_segment(LW[0] - pd.Timedelta(days=14), LW[0] - pd.Timedelta(days=1))
    post = machine_segment(LW[1] + pd.Timedelta(days=1), LW[1] + pd.Timedelta(days=14))
    base = (pre + post) / 2
    d = wk.join(base, rsuffix="_base").fillna(0.0)
    d = d[d.total_base > 0]
    d["local_share_wk"] = d.locals / d.total.where(d.total > 0)
    # terciles on the locals' share in the 14 days BEFORE the event: same-week share is mechanically
    # higher wherever non-locals left, which would manufacture a displacement slope
    d["local_share_pre"] = (pre.locals / pre.total.where(pre.total > 0)).reindex(d.index)
    d = d[d.local_share_pre.notna()]
    d["tercile"] = pd.qcut(d.local_share_pre.rank(method="first"), 3, labels=["low", "mid", "high"])
    g = d.groupby("tercile", observed=True)
    out = pd.DataFrame({
        "machines": g.size(),
        "locals_share_pre": g.local_share_pre.mean(), "locals_share_wk": g.local_share_wk.mean(),
        "locals_chg": g.locals.sum() / g.locals_base.sum() - 1,
        "carded_nonlocal_chg": g.carded_nonlocals.sum() / g.carded_nonlocals_base.sum() - 1,
        "uncarded_chg": g.uncarded.sum() / g.uncarded_base.sum() - 1,
        "total_chg": g.total.sum() / g.total_base.sum() - 1})
    # machine-level slope: carded non-local log change vs locals' pre-event share
    ok = (d.carded_nonlocals > 0) & (d.carded_nonlocals_base > 0)
    y = np.log(d.carded_nonlocals[ok] / d.carded_nonlocals_base[ok])
    x = d.local_share_pre[ok]
    X = np.c_[np.ones(len(x)), x]
    b, res, *_ = np.linalg.lstsq(X, y, rcond=None)
    se = np.sqrt(res[0] / (len(x) - 2) * np.linalg.inv(X.T @ X)[1, 1])
    return out, {"slope_per_unit_share": b[1], "se": se, "n": int(ok.sum())}


def walkway95():
    """Same estimator and placebos as run_impact.closure (directly measured whole-floor net), 95% quantile."""
    import run_impact as ri  # builds the series it needs at import
    b40 = ri.zones("Z-B40")
    rest5 = ri.zones("Z-BAR", "Z-ENT", "Z-GAR", "Z-HL", "Z-HTL")
    # cannibalization beta from the pit section, as run_impact.main does
    cb = ri.pit_expansion() if hasattr(ri, "pit_expansion") else 0.0
    pit_old = ri.S([m for m in ri.v[ri.v.zone_id == "Z-PIT"].machine_id.unique() if m not in ri.NEW_PIT])
    pit_old = pit_old.where(pit_old.index < "2025-03-24", pit_old / np.exp(cb))
    s = b40 + rest5 + pit_old
    start, end = ri.CLO
    L = (end - start).days + 1
    beta, level = impact.on_off_beta(s, start, end, 28)
    null = []
    for fs in pd.date_range(s.index.min() + pd.Timedelta(days=5), s.index.max() - pd.Timedelta(days=L + 4), freq="2D"):
        fe = fs + pd.Timedelta(days=L - 1)
        if impact._mask(pd.date_range(fs, fe), [(start, end)]).any():
            continue
        o = impact.on_off_beta(s, fs, fe, 28, True, [(start, end)])
        if o is not None and np.isfinite(o[0]):
            null.append(o[0])
    null = np.asarray(null)
    out = {"beta": beta, "level": level, "n_placebo": len(null)}
    for q in (0.90, 0.95):
        h = np.quantile(np.abs(null), q) * impact.CALIBRATION
        lo = beta - h
        out[f"lo{int(q*100)}_usd_day"] = level * (1 - np.exp(-lo))
        out[f"hi{int(q*100)}_usd_day"] = level * (1 - np.exp(-(beta + h)))
        out[f"lo{int(q*100)}_pct"] = np.expm1(lo)
    out["est_usd_day"] = level * (1 - np.exp(-beta))
    return out


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    print(did().to_string(index=False, float_format=lambda x: f"{x:+.3f}"))
    t, sl = displacement()
    print(t.to_string(float_format=lambda x: f"{x:+.3f}")); print(sl)
    print(walkway95())
