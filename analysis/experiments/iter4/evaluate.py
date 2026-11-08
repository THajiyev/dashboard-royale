"""Iteration 4 evaluation: same two protocols as iteration 3.

  fixed   : forecast all of May-Jun from Apr 30; CV = the 7 harness origins inside Jan-Apr. Base = EL.
  refresh : refit weekly, forecast the next 7 days; CV origins Jan 31 + 7k .. Apr 23. Base = EL2 + 28-day anchor
            (the iteration 3 recommendation).

`python evaluate.py cv`               -> cv_results.csv (touches Jan-Apr only)
`python evaluate.py holdout NAME ...` -> holdout_results.csv; every look is appended to holdout_log.jsonl.
NAME is "fixed:<model>" or "refresh:<model>".
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent.parent)); sys.path.insert(0, str(HERE))
import harness  # noqa: E402
from common import TRAIN_END  # noqa: E402
from iter2.models import EL  # noqa: E402
from iter3.models import make_el2  # noqa: E402
from hol_hist import with_holidays, with_holiday_gbm, with_history  # noqa: E402

EL2A = make_el2(1.0, 28, 0.5)
HOL_KINDS = ["day", "longwknd", "longwknd+day", "near1", "near2", "near3", "kernel1", "kernel2", "kernel4", "bins"]
LAMS = [2, 5, 20]


def family(base):
    m = {"base": base}
    m.update({f"hol {k} lam={l}": with_holidays(base, k, l) for k in HOL_KINDS for l in LAMS})
    m["hol GBM"] = with_holiday_gbm(base)
    m.update({f"hist {s} beta={b}": with_history(base, s, b) for s in ("seasonal", "season_yoy") for b in (0.5, 1.0)})
    return m


FIXED, REFRESH = family(EL), family(EL2A)
TARGETS = ["theo_usd", "coin_in_usd"]
CV_REFRESH = pd.date_range("2025-01-31", "2025-04-23", freq="7D")
HO_REFRESH = pd.date_range("2025-04-30", "2025-06-25", freq="7D")


def _pred(f, df, origin, end, t):
    tr, fut, full = harness._split(df, origin, end)
    return harness._run(f, tr, fut, t), full[t].to_numpy(), full.gaming_date.to_numpy()


def refresh_series(f, df, origins, end, t):
    out = [_pred(f, df, o, min(o + pd.Timedelta(days=7), end), t) for o in origins if o < end]
    return tuple(np.concatenate(x) for x in zip(*out))


def cv():
    df = harness.frame(); df = df[df.gaming_date <= TRAIN_END]
    rows = []
    for t in TARGETS:
        for name, f in FIXED.items():
            ps = [_pred(f, df, o, TRAIN_END, t) for o in harness.CV_ORIGINS]
            rows.append({"protocol": "fixed", "target": t, "model": name,
                         "mae": np.mean([np.mean(np.abs(p - y)) for p, y, _ in ps]),
                         "bias": np.mean([np.mean(p - y) for p, y, _ in ps])})
        for name, f in REFRESH.items():
            p, y, _ = refresh_series(f, df, CV_REFRESH, TRAIN_END, t)
            rows.append({"protocol": "refresh", "target": t, "model": name, "mae": np.mean(np.abs(p - y)),
                         "bias": np.mean(p - y)})
    r = pd.DataFrame(rows)
    base = r[r.model == "base"].set_index(["protocol", "target"]).mae
    r["skill_vs_base"] = 1 - r.mae / r.set_index(["protocol", "target"]).index.map(base)
    return r


LOCALS = (pd.Timestamp("2025-06-09"), pd.Timestamp("2025-06-15"))
HOLIDAY_WINDOWS = [(pd.Timestamp("2025-05-23"), pd.Timestamp("2025-05-26")),   # Memorial Day weekend
                   (pd.Timestamp("2025-05-10"), pd.Timestamp("2025-05-12")),   # Mother's Day +-1
                   (pd.Timestamp("2025-06-18"), pd.Timestamp("2025-06-20"))]   # Juneteenth +-1


def holdout(names):
    df = harness.frame(); end = pd.Timestamp("2025-06-30")
    rows = []
    for name in names:
        proto, model = name.split(":", 1)
        reg = FIXED if proto == "fixed" else REFRESH
        for t in TARGETS:
            run = (lambda f: _pred(f, df, TRAIN_END, end, t)) if proto == "fixed" else \
                  (lambda f: refresh_series(f, df, HO_REFRESH, end, t))
            p, y, d = run(reg[model]); pb, _, _ = run(reg["base"])
            d = pd.to_datetime(d)
            loc = (d >= LOCALS[0]) & (d <= LOCALS[1])
            hol = np.zeros(len(d), bool)
            for a, b in HOLIDAY_WINDOWS:
                hol |= (d >= a) & (d <= b)
            e, eb = p - y, pb - y
            rows.append({"protocol": proto, "target": t, "model": model, "mae": np.mean(np.abs(e)),
                         "mae_base": np.mean(np.abs(eb)), "skill_vs_base": 1 - np.mean(np.abs(e)) / np.mean(np.abs(eb)),
                         "bias": e.mean(), "mae_ex_locals": np.mean(np.abs(e[~loc])),
                         "mae_holiday_days": np.mean(np.abs(e[hol])), "mae_holiday_days_base": np.mean(np.abs(eb[hol])),
                         "bias_may": e[d.month == 5].mean(), "bias_jun": e[d.month == 6].mean(),
                         "dm_p_vs_base": harness.dm_test(e, eb) if model != "base" else np.nan})
    with (HERE / "holdout_log.jsonl").open("a") as fh:
        fh.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "models": names}) + "\n")
    return pd.DataFrame(rows)


if __name__ == "__main__":
    pd.set_option("display.width", 240); pd.set_option("display.max_rows", 500)
    if sys.argv[1] == "cv":
        r = cv(); r.to_csv(HERE / "cv_results.csv", index=False)
        print(r.sort_values(["protocol", "target", "mae"]).to_string(index=False, float_format=lambda x: f"{x:,.3f}" if abs(x) < 1 else f"{x:,.0f}"))
    else:
        r = holdout(sys.argv[2:]); f = HERE / "holdout_results.csv"
        (pd.concat([pd.read_csv(f), r]) if f.exists() else r).to_csv(f, index=False)
        print(r.to_string(index=False, float_format=lambda x: f"{x:,.3f}" if abs(x) < 1 else f"{x:,.0f}"))
