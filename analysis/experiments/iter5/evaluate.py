"""Iteration 5 evaluation (PREREG.md).

`python evaluate.py cv`      -> cv_results.csv: Jan-Apr refresh-CV RMSE of the 6 segment candidates (+ EL2A), the pick,
                                and the pre-June check (select on Jan-Feb CV, score on Mar-Apr).  Touches Jan-Apr only.
`python evaluate.py holdout` -> final_table.csv: every listed model scored once on May-Jun (logged in holdout_log.jsonl).
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent.parent)); sys.path.insert(0, str(HERE))
import forecast  # noqa: E402
import harness  # noqa: E402
from common import TRAIN_END  # noqa: E402
from ds_alpha.models import _EV  # noqa: E402
from iter2.models import CANDIDATES as I2, VARIANTS as I2V, EL  # noqa: E402
from iter3.models import make_el2  # noqa: E402
from iter4.hol_hist import with_holidays, with_history  # noqa: E402
from models import CANDIDATES as I5  # noqa: E402

Y = "theo_usd"
EL2A = make_el2(1.0, 28, 0.5)
CV_REFRESH = pd.date_range("2025-01-31", "2025-04-23", freq="7D")
HO_REFRESH = pd.date_range("2025-04-30", "2025-06-25", freq="7D")
HO_END = pd.Timestamp("2025-06-30")
ALPHA = 0.10
N_BOOT, BLOCK = 2000, 7


# ----------------------------------------------------------------------------- protocols
def fixed_run(f, df, origin, end):
    tr, fut, full = harness._split(df, origin, end)
    return harness._run(f, tr, fut, Y), full[Y].to_numpy(), full.gaming_date.to_numpy()


def refresh_run(f, df, origins, end):
    out = [fixed_run(f, df, o, min(o + pd.Timedelta(days=7), end)) for o in origins if o < end]
    return tuple(np.concatenate(x) for x in zip(*out))


def cv_residuals(f, proto, df_cv):
    """log(y/p) on the model's own Jan-Apr CV forecasts (fixed: harness origins; refresh: weekly origins)."""
    if proto == "fixed":
        ps = [fixed_run(f, df_cv, o, TRAIN_END) for o in harness.CV_ORIGINS]
        p, y = np.concatenate([a for a, _, _ in ps]), np.concatenate([b for _, b, _ in ps])
    else:
        p, y, _ = refresh_run(f, df_cv, CV_REFRESH, TRAIN_END)
    return np.log(y / p), p, y


def rmse(e):
    return float(np.sqrt(np.mean(e ** 2)))


# ----------------------------------------------------------------------------- stage 1: CV (Jan-Apr only)
def cv():
    df = harness.frame(); df = df[df.gaming_date <= TRAIN_END]
    cands = {"EL2 + anchor": EL2A, **I5}
    rows = []
    for name, f in cands.items():
        p, y, _ = refresh_run(f, df, CV_REFRESH, TRAIN_END)
        pa, ya, _ = refresh_run(f, df, CV_REFRESH[CV_REFRESH < "2025-02-28"], pd.Timestamp("2025-02-28"))
        pb, yb, _ = refresh_run(f, df, CV_REFRESH[CV_REFRESH >= "2025-02-28"], TRAIN_END)
        rows.append({"model": name, "cv_rmse_janapr": rmse(p - y), "cv_mae_janapr": float(np.mean(np.abs(p - y))),
                     "cv_rmse_janfeb": rmse(pa - ya), "test_rmse_marapr": rmse(pb - yb),
                     "_e_marapr": pb - yb})
    r = pd.DataFrame(rows)
    seg = r[r.model != "EL2 + anchor"]
    pick = seg.loc[seg.cv_rmse_janapr.idxmin(), "model"]
    pick_jf = seg.loc[seg.cv_rmse_janfeb.idxmin(), "model"]
    r["cv_pick"] = r.model == pick
    r["janfeb_pick"] = r.model == pick_jf
    # pre-June check: Jan-Feb pick vs EL2A on Mar-Apr, block-bootstrap CI on the RMSE difference
    eA = r.set_index("model").loc[pick_jf, "_e_marapr"]; eB = r.set_index("model").loc["EL2 + anchor", "_e_marapr"]
    lo, hi = boot_ci(lambda i: rmse(eA[i]) / rmse(eB[i]) - 1, len(eA))
    r = r.drop(columns="_e_marapr")
    r.to_csv(HERE / "cv_results.csv", index=False)
    check = {"janfeb_pick": pick_jf, "marapr_rmse_pick": rmse(eA), "marapr_rmse_el2a": rmse(eB),
             "delta_pct": rmse(eA) / rmse(eB) - 1, "ci95": (lo, hi), "janapr_pick": pick}
    (HERE / "prejune_check.json").write_text(json.dumps(check, indent=2, default=float))
    return r, check


def boot_idx(n, rng):
    """Moving-block bootstrap indices (blocks of BLOCK consecutive days, wrapped)."""
    k = int(np.ceil(n / BLOCK))
    starts = rng.integers(0, n, size=k)
    return np.concatenate([(s + np.arange(BLOCK)) % n for s in starts])[:n]


def boot_ci(stat, n, seed=0):
    rng = np.random.default_rng(seed)
    v = [stat(boot_idx(n, rng)) for _ in range(N_BOOT)]
    return float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))


# ----------------------------------------------------------------------------- stage 2: holdout (once)
def registry(pick5):
    I4F = lambda base: {"hist seasonal beta=0.5": with_history(base, "seasonal", 0.5),
                        "hist season_yoy beta=0.5": with_history(base, "season_yoy", 0.5),
                        "hol longwknd+day lam=2": with_holidays(base, "longwknd+day", 2),
                        "hol near1 lam=5": with_holidays(base, "near1", 5),
                        "hol kernel1 lam=20": with_holidays(base, "kernel1", 20)}
    m = [("B2 event-aware weekday", "Phase 0", "fixed", forecast.m_b2, True),
         ("EL event-type lift", "Iter 1", "fixed", EL, True),
         ("EL + recent-level (28d) + payday", "Iter 2", "fixed", I2V["EL + recent-level (28d) + payday"], True),
         ("EL x CatBoost residual (best post hoc)", "Iter 2", "fixed", I2["EL x CatBoost residual (calendar)"], False),
         ("EL2 + 28d anchor", "Iter 3", "refresh", EL2A, True)]
    for proto, base, bname, cvpick in [("fixed", EL, "EL", "hist seasonal beta=0.5"),
                                       ("refresh", EL2A, "EL2A", "hol longwknd+day lam=2")]:
        for k, f in I4F(base).items():
            m.append((f"{bname} + {k}", "Iter 4", proto, f, k == cvpick))
    for k, f in I5.items():
        m.append((k.replace("seg ", "EL2A segments: "), "Iter 5", "refresh", f, k == pick5))
    return m


def holdout():
    pick5 = pd.read_csv(HERE / "cv_results.csv").query("cv_pick").model.iloc[0]
    df = harness.frame(); df_cv = df[df.gaming_date <= TRAIN_END]
    ev_days = set()
    for r in _EV.itertuples():
        ev_days |= set(pd.date_range(r.start_date, r.end_date))
    preds = {}
    for name, it, proto, f, adv in registry(pick5):
        lr, _, _ = cv_residuals(f, proto, df_cv)
        q_lo, q_hi = np.quantile(lr, [ALPHA / 2, 1 - ALPHA / 2])
        p, y, d = fixed_run(f, df, TRAIN_END, HO_END) if proto == "fixed" else refresh_run(f, df, HO_REFRESH, HO_END)
        preds[name] = dict(it=it, proto=proto, adv=adv, p=p, y=y, d=pd.to_datetime(d), lo=p * np.exp(q_lo),
                           hi=p * np.exp(q_hi))
        print("scored", name, flush=True)
    y = preds["B2 event-aware weekday"]["y"]; d = preds["B2 event-aware weekday"]["d"]
    ev = np.asarray(pd.DatetimeIndex(d).isin(list(ev_days)))
    eB2 = preds["B2 event-aware weekday"]["p"] - y
    eA = preds["EL2 + 28d anchor"]["p"] - y
    rows = []
    for name, r in preds.items():
        assert np.allclose(r["y"], y)
        e = r["p"] - y
        lo_, hi_ = r["lo"], r["hi"]
        winkler = (hi_ - lo_) + (2 / ALPHA) * (lo_ - y) * (y < lo_) + (2 / ALPHA) * (y - hi_) * (y > hi_)
        rows.append({"model": name, "iteration": r["it"], "protocol": r["proto"], "RMSE": rmse(e),
                     "MAE": float(np.mean(np.abs(e))), "WAPE": float(np.sum(np.abs(e)) / np.sum(y)),
                     "bias": float(e.mean()), "ordinary_RMSE": rmse(e[~ev]), "event_RMSE": rmse(e[ev]),
                     "dRMSE_vs_B2": rmse(e) / rmse(eB2) - 1,
                     "ci95_vs_B2": boot_ci(lambda i: rmse(e[i]) / rmse(eB2[i]) - 1, len(e)),
                     "dRMSE_vs_EL2A": rmse(e) / rmse(eA) - 1,
                     "ci95_vs_EL2A": boot_ci(lambda i: rmse(e[i]) / rmse(eA[i]) - 1, len(e)),
                     "cover90": float(np.mean((y >= lo_) & (y <= hi_))), "interval_score": float(winkler.mean()),
                     "picked_in_advance": r["adv"]})
    t = pd.DataFrame(rows).sort_values("RMSE").reset_index(drop=True)
    t["n_event_days"] = int(ev.sum())
    t.to_csv(HERE / "final_table.csv", index=False)
    pd.DataFrame({"gaming_date": d, "actual": y, **{k: v["p"] for k, v in preds.items()}}).to_csv(
        HERE / "holdout_daily.csv", index=False)
    with (HERE / "holdout_log.jsonl").open("a") as fh:
        fh.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "iter5_pick": pick5,
                             "models": list(preds)}) + "\n")
    return t


if __name__ == "__main__":
    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 30)
    if sys.argv[1] == "cv":
        r, c = cv(); print(r.to_string(index=False)); print(json.dumps(c, indent=2, default=float))
    else:
        print(holdout().to_string(index=False))
