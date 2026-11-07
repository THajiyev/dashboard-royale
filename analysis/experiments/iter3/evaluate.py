"""Iteration 3 evaluation.

Protocol A (fixed): the harness setup — forecast all of May–Jun from Apr 30. CV = 7 harness origins in Jan–Apr.
Protocol B (weekly refresh): every 7 days, refit on all data to that origin and forecast the next 7 days.
  CV origins: Jan 31 + 7k through Apr 23 (windows truncated at Apr 30).
  Holdout origins: Apr 30 + 7k through Jun 25 -> exactly the same 61 days as protocol A.

`python evaluate.py cv` runs CV only. `python evaluate.py holdout NAME...` scores named models on May–Jun
and appends every look to holdout_log.jsonl (so the number of looks is on record).
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE))
import harness, forecast  # noqa
from common import TRAIN_END  # noqa
from models import make_zs, make_el_anchor, make_el2, make_el3  # noqa
from iter2.models import EL, make_el  # noqa

FIXED = {
    "B2": forecast.m_b2,
    "EL (current best)": EL,
    "ZS": make_zs(),
    "ZS, no per-machine": make_zs(per_machine=False),
    "ZS, closure kept in base": make_zs(exclude_closure=False),
    "ZS + damped trend (phi .98)": make_zs(trend_phi=0.98),
    "ZS + damped trend (phi .95)": make_zs(trend_phi=0.95),
    "ZS + anchor 50% (28d)": make_zs(anchor_w=0.5, anchor_days=28),
}
REFRESH = {
    "B2": forecast.m_b2,
    "EL": EL,
    "EL + recency (hl 28d)": make_el(half_life=28),
    **{f"EL + anchor {int(w*100)}% ({d}d)": make_el_anchor(w, d) for w in (0.25, 0.5, 0.75, 1.0) for d in (7, 14, 28)},
    "ZS": make_zs(),
    **{f"ZS + anchor {int(w*100)}% ({d}d)": make_zs(anchor_w=w, anchor_days=d) for w in (0.25, 0.5, 0.75, 1.0) for d in (14, 28)},
    "ZS + damped trend (phi .98)": make_zs(trend_phi=0.98),
    **{f"EL2 k_ev={k} + anchor {int(w*100)}% (28d)": make_el2(w, 28, k) for k in (0.5, 1, 2) for w in (0, 0.5, 1.0)},
}
REFRESH.update({f"EL3 ongoing k={k}": make_el3(1.0, 28, 0.5, k) for k in (1, 3, 7)})
FIXED.update({f"EL2 k_ev={k}": make_el2(0, 28, k) for k in (0.5, 1, 2)})
TARGETS = ["theo_usd", "coin_in_usd"]


def _pred(f, df, origin, end, target):
    tr, fut, full = harness._split(df, origin, end)
    return harness._run(f, tr, fut, target), full[target].to_numpy(), full.gaming_date.to_numpy()


def fixed_cv(models):
    df = harness.frame(); df = df[df.gaming_date <= TRAIN_END]
    rows = []
    for t in TARGETS:
        for name, f in models.items():
            maes, bias = [], []
            for o in harness.CV_ORIGINS:
                p, y, _ = _pred(f, df, o, TRAIN_END, t)
                maes.append(np.mean(np.abs(p - y))); bias.append(np.mean(p - y))
            rows.append({"protocol": "fixed", "split": "cv", "target": t, "model": name,
                         "mae": np.mean(maes), "bias": np.mean(bias), "worst_fold": np.max(maes)})
    return rows


def refresh_series(f, df, origins, end, target):
    P, Y, D = [], [], []
    for o in origins:
        e = min(o + pd.Timedelta(days=7), end)
        if e <= o:
            continue
        p, y, d = _pred(f, df, o, e, target)
        P.append(p); Y.append(y); D.append(d)
    return np.concatenate(P), np.concatenate(Y), np.concatenate(D)


CV_REFRESH = pd.date_range("2025-01-31", "2025-04-23", freq="7D")
HO_REFRESH = pd.date_range("2025-04-30", "2025-06-25", freq="7D")


def refresh_cv(models):
    df = harness.frame(); df = df[df.gaming_date <= TRAIN_END]
    rows = []
    for t in TARGETS:
        for name, f in models.items():
            p, y, _ = refresh_series(f, df, CV_REFRESH, TRAIN_END, t)
            e = p - y
            rows.append({"protocol": "refresh", "split": "cv", "target": t, "model": name, "mae": np.mean(np.abs(e)),
                         "bias": np.mean(e), "worst_fold": np.max(np.abs(pd.Series(e).rolling(7).mean()))})
    return rows


def holdout(names):
    df = harness.frame(); end = pd.Timestamp("2025-06-30")
    rows = []
    for name in names:
        proto, model = name.split(":", 1)
        for t in TARGETS:
            if proto == "fixed":
                p, y, d = _pred(FIXED[model], df, TRAIN_END, end, t)
                pel, _, _ = _pred(EL, df, TRAIN_END, end, t)
            else:
                p, y, d = refresh_series(REFRESH[model], df, HO_REFRESH, end, t)
                pel, _, _ = refresh_series(EL, df, HO_REFRESH, end, t)
            e = p - y
            m = pd.Series(e, index=pd.to_datetime(d)).groupby(lambda x: x.month).mean()
            rows.append({"protocol": proto, "split": "holdout", "target": t, "model": model, "mae": np.mean(np.abs(e)),
                         "bias": np.mean(e), "bias_may": m.get(5), "bias_jun": m.get(6),
                         "dm_p_vs_el_same_protocol": harness.dm_test(e, pel - y) if model != "EL" and "EL (current" not in model else np.nan})
    with (HERE / "holdout_log.jsonl").open("a") as fh:
        fh.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "models": names}) + "\n")
    return rows


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    fmt = lambda x: f"{x:,.0f}" if abs(x) >= 10 else f"{x:.3f}"
    if sys.argv[1] == "cv":
        only = sys.argv[2:]
        pick = lambda d: {k: v for k, v in d.items() if not only or any(o in k for o in only)}
        r = pd.DataFrame(fixed_cv(pick(FIXED)) + refresh_cv(pick(REFRESH)))
        r.to_csv(HERE / ("cv_results.csv" if not only else "cv_results_round2.csv"), index=False)
        print(r.sort_values(["protocol", "target", "mae"]).to_string(index=False, float_format=fmt))
    else:
        r = pd.DataFrame(holdout(sys.argv[2:]))
        f = HERE / "holdout_results.csv"
        r = pd.concat([pd.read_csv(f), r]) if f.exists() else r
        r.to_csv(f, index=False)
        print(r.to_string(index=False, float_format=fmt))
