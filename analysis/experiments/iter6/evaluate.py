"""Iteration 6 evaluation (PREREG.md).

`python evaluate.py cv`      -> cv_results.csv, cv_folds.csv, cv_pick.json. Touches Jan-Apr only.
`python evaluate.py holdout` -> holdout_daily.csv, holdout_table.csv, holdout_weeks.csv. Scores May-Jun once and logs
                                the look to holdout_log.jsonl; refuses to run a second time.
`python evaluate.py check`   -> leakage / equivalence checks (Jan-Apr only).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent), str(HERE.parent.parent)]
import forecast  # noqa: E402
import harness  # noqa: E402
from common import TRAIN_END  # noqa: E402
from ds_alpha.models import _EV  # noqa: E402
from models import EL, GRID, Spec, make, recent_factor  # noqa: E402

Y = "theo_usd"
HO_END = pd.Timestamp("2025-06-30")
CV_FIXED = harness.CV_ORIGINS                                   # Feb 28 ... Apr 11
CV_REFRESH = pd.date_range("2025-01-31", "2025-04-25", freq="7D")  # 13 weeks
HO_REFRESH = pd.date_range("2025-04-30", "2025-06-25", freq="7D")  # 9 weeks
EARLY_CUT = pd.Timestamp("2025-03-21")
CLO_SCORE = (pd.Timestamp("2025-03-03"), pd.Timestamp("2025-04-13"))  # closure + 1 week, dropped in check (c)
N_BOOT, BLOCK = 2000, 7
REFS = ["B1 weekday mean", "EL"]


def windows(proto, split):
    """List of (origin, end) forecast windows."""
    if proto == "fixed":
        return [(o, TRAIN_END) for o in CV_FIXED] if split == "cv" else [(TRAIN_END, HO_END)]
    origins, end = (CV_REFRESH, TRAIN_END) if split == "cv" else (HO_REFRESH, HO_END)
    return [(o, min(o + pd.Timedelta(days=7), end)) for o in origins if o < end]


def run_all(proto, split):
    """Long frame: one row per (window, target day) with actual and every model's forecast."""
    df = harness.frame()
    if split == "cv":
        df = df[df.gaming_date <= TRAIN_END]
    out = []
    for i, (o, e) in enumerate(windows(proto, split)):
        tr, fut, full = harness._split(df, o, e)
        assert tr.gaming_date.max() == o and fut.gaming_date.min() > o  # leakage guard
        el_fut = harness._run(EL, tr, fut, Y)
        el_fit = EL(tr, tr[harness.FUTURE_COLS], Y)  # in-sample EL fit, from rows <= origin only
        rec = {"fold": i, "origin": o, "gaming_date": full.gaming_date.to_numpy(), "actual": full[Y].to_numpy(),
               "B1 weekday mean": harness._run(forecast.m_b1, tr, fut, Y), "EL": el_fut}
        for s in GRID:
            p = el_fut * recent_factor(tr, fut, Y, s, el_fit)
            assert np.all(np.isfinite(p)) and np.all(p > 0)
            rec[s.name] = p
        out.append(pd.DataFrame(rec))
    return pd.concat(out, ignore_index=True)


rmse = lambda e: float(np.sqrt(np.mean(np.square(e))))
mae = lambda e: float(np.mean(np.abs(e)))
MODELS = REFS + [s.name for s in GRID]


# ----------------------------------------------------------------------------- stage 1: CV
def cv_summary(d, models=MODELS):
    y = d.actual.to_numpy()
    clo = d.gaming_date.between(*CLO_SCORE).to_numpy()
    early = (d.origin <= EARLY_CUT).to_numpy()
    fr = {m: d.groupby("fold").apply(lambda g: rmse(g[m] - g.actual), include_groups=False) for m in models}
    rows = []
    for m in models:
        e = d[m].to_numpy() - y
        rows.append({"model": m, "cv_rmse": rmse(e), "cv_mae": mae(e), "cv_bias": float(e.mean()),
                     "folds_won_vs_EL": int((fr[m] < fr["EL"]).sum()), "folds": len(fr[m]),
                     "worst_fold_rmse": float(fr[m].max()),
                     "cv_rmse_ex_closure": rmse(e[~clo]), "cv_rmse_early": rmse(e[early]), "cv_rmse_late": rmse(e[~early])})
    return pd.DataFrame(rows)


CLEAN_MODES = ("excl", "excl_clo", "delift")  # amendment (PREREG.md): event days kept out of the level


def select(t, proto, modes=None):
    t = t.set_index("model")
    el = t.loc["EL"]
    grid = t.loc[[s.name for s in GRID if modes is None or s.mode in modes]]
    pick = grid.cv_rmse.idxmin()
    p = grid.loc[pick]
    early_pick = grid.cv_rmse_early.idxmin()
    need = {"fixed": 5, "refresh": 9}[proto]
    checks = {
        "a_size_ge_3pct": bool(p.cv_rmse <= 0.97 * el.cv_rmse),
        "b_folds_won": bool(p.folds_won_vs_EL >= need),
        "c_ex_closure_beats_EL": bool(p.cv_rmse_ex_closure < el.cv_rmse_ex_closure),
        "d_early_pick_beats_EL_late": bool(grid.loc[early_pick].cv_rmse_late < el.cv_rmse_late),
    }
    return {"protocol": proto, "pick": pick, "cv_rmse": p.cv_rmse, "cv_rmse_EL": el.cv_rmse,
            "cv_gain_vs_EL": 1 - p.cv_rmse / el.cv_rmse, "folds_won": int(p.folds_won_vs_EL), "folds": int(p.folds),
            "early_pick": early_pick, "early_pick_late_rmse": grid.loc[early_pick].cv_rmse_late,
            "EL_late_rmse": el.cv_rmse_late, "checks": checks, "adopt_in_principle": all(checks.values())}


def stage_cv():
    res, folds, picks = [], [], {}
    for proto in ["fixed", "refresh"]:
        d = run_all(proto, "cv")
        t = cv_summary(d).assign(protocol=proto)
        res.append(t)
        picks[proto] = select(t, proto)
        picks[proto + "_clean"] = select(t, proto, CLEAN_MODES)
        fr = d.groupby(["fold", "origin"]).apply(
            lambda g: pd.Series({m: rmse(g[m] - g.actual) for m in MODELS}), include_groups=False).reset_index()
        folds.append(fr.assign(protocol=proto))
    pd.concat(res).to_csv(HERE / "cv_results.csv", index=False)
    pd.concat(folds).to_csv(HERE / "cv_folds.csv", index=False)
    (HERE / "cv_pick.json").write_text(json.dumps(picks, indent=2, default=float))
    print(json.dumps(picks, indent=2, default=float))


# ----------------------------------------------------------------------------- stage 2: one May-Jun look
def boot_idx(n, rng):
    k = int(np.ceil(n / BLOCK))
    return np.concatenate([(s + np.arange(BLOCK)) % n for s in rng.integers(0, n, size=k)])[:n]


def stage_holdout():
    log = HERE / "holdout_log.jsonl"
    if log.exists() and "--force" not in sys.argv:
        raise SystemExit("May-Jun has already been scored once for iteration 6 (holdout_log.jsonl).")
    picks = json.loads((HERE / "cv_pick.json").read_text())
    ev_days = set()
    for r in _EV.itertuples():
        ev_days |= set(pd.date_range(r.start_date, r.end_date))
    locals_wk = pd.date_range("2025-06-09", "2025-06-15")
    rng = np.random.default_rng(0)
    I = [boot_idx(61, rng) for _ in range(N_BOOT)]

    daily, rows, weeks = [], [], []
    for proto in ["fixed", "refresh"]:
        d = run_all(proto, "holdout").sort_values("gaming_date").reset_index(drop=True)
        assert len(d) == 61 and d.gaming_date.is_unique
        daily.append(d.assign(protocol=proto))
        y = d.actual.to_numpy()
        ev = d.gaming_date.isin(ev_days).to_numpy()
        lw = d.gaming_date.isin(locals_wk).to_numpy()
        mon = d.gaming_date.dt.month.to_numpy()
        wk = ((d.gaming_date - pd.Timestamp("2025-05-01")).dt.days // 7).to_numpy()
        eEL = d["EL"].to_numpy() - y
        eB1f = None
        for m in MODELS:
            e = d[m].to_numpy() - y
            gain = np.abs(eEL) - np.abs(e)          # per-day MAE gain vs EL
            top5 = np.argsort(-gain)[:5]
            keep = np.ones(61, bool); keep[top5] = False
            rr = np.array([rmse(e[i]) / rmse(eEL[i]) for i in I]) if m != "EL" else None
            wk_rmse = pd.Series(e).groupby(wk).apply(rmse)
            wk_el = pd.Series(eEL).groupby(wk).apply(rmse)
            spec = next((s for s in GRID if s.name == m), None)
            rows.append({
                "protocol": proto, "model": m,
                "picked_in_advance": m in REFS or m in (picks[proto]["pick"], picks[proto + "_clean"]["pick"]),
                "pick_role": ("rule pick" if m == picks[proto]["pick"] else
                              "clean pick" if m == picks[proto + "_clean"]["pick"] else "reference" if m in REFS else ""),
                "stat": spec and spec.stat, "span": spec and spec.span, "mode": spec and spec.mode, "w": spec and spec.w,
                "RMSE": rmse(e), "MAE": mae(e), "bias": float(e.mean()),
                "ordinary_RMSE": rmse(e[~ev]), "event_RMSE": rmse(e[ev]),
                "ordinary_MAE": mae(e[~ev]), "event_MAE": mae(e[ev]),
                "May_MAE": mae(e[mon == 5]), "Jun_MAE": mae(e[mon == 6]),
                "May_RMSE": rmse(e[mon == 5]), "Jun_RMSE": rmse(e[mon == 6]),
                "RMSE_ex_locals_wk": rmse(e[~lw]), "MAE_ex_locals_wk": mae(e[~lw]),
                "MAE_ex_top5_gain_days": mae(e[keep]), "EL_MAE_ex_same5": mae(eEL[keep]),
                "weeks_won_vs_EL": int((wk_rmse < wk_el).sum()), "weeks": len(wk_rmse),
                "dRMSE_vs_EL": rmse(e) / rmse(eEL) - 1,
                "dRMSE_vs_EL_lo": rr is not None and float(np.quantile(rr, .025)) - 1 or np.nan,
                "dRMSE_vs_EL_hi": rr is not None and float(np.quantile(rr, .975)) - 1 or np.nan,
                "dm_p_vs_EL": harness.dm_test(e, eEL) if m != "EL" else np.nan,
            })
            weeks.append(pd.DataFrame({"protocol": proto, "model": m, "week": wk_rmse.index, "RMSE": wk_rmse.values}))
    t = pd.DataFrame(rows)
    # Delta vs the headline baseline: B1 fixed
    df_fixed = daily[0]
    eB1 = (df_fixed["B1 weekday mean"] - df_fixed.actual).to_numpy()
    for proto, d in zip(["fixed", "refresh"], daily):
        y = d.actual.to_numpy()
        for m in MODELS:
            e = d[m].to_numpy() - y
            r = np.array([rmse(e[i]) / rmse(eB1[i]) for i in I])
            sel = (t.protocol == proto) & (t.model == m)
            t.loc[sel, ["dRMSE_vs_B1fixed", "dRMSE_vs_B1_lo", "dRMSE_vs_B1_hi"]] = \
                [rmse(e) / rmse(eB1) - 1, np.quantile(r, .025) - 1, np.quantile(r, .975) - 1]
    t.to_csv(HERE / "holdout_table.csv", index=False)
    pd.concat(weeks).to_csv(HERE / "holdout_weeks.csv", index=False)
    keep_cols = ["protocol", "gaming_date", "origin", "actual", *MODELS]
    pd.concat(daily)[keep_cols].to_csv(HERE / "holdout_daily.csv", index=False)
    with log.open("a") as fh:
        fh.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "n_models": len(MODELS),
                             "protocols": ["fixed", "refresh"], "picks": {k: v["pick"] for k, v in picks.items()}}) + "\n")
    show = t[t.picked_in_advance].round(4)
    print(show[["protocol", "model", "RMSE", "MAE", "ordinary_RMSE", "event_RMSE", "dRMSE_vs_EL",
                "dRMSE_vs_EL_lo", "dRMSE_vs_EL_hi"]].to_string())


# ----------------------------------------------------------------------------- checks (Jan-Apr only)
def stage_check():
    df = harness.frame(); df = df[df.gaming_date <= TRAIN_END]
    o = pd.Timestamp("2025-03-28")
    tr, fut, full = harness._split(df, o, TRAIN_END)
    # 1. the cached path equals the model function
    for s in [GRID[0], GRID[37], GRID[-1]]:
        assert np.allclose(make(s)(tr, fut, Y), EL(tr, fut, Y) * recent_factor(tr, fut, Y, s))
    # 2. w=0 is EL exactly
    assert np.allclose(make(Spec("mean", 28, "excl", 0.0))(tr, fut, Y), EL(tr, fut, Y))
    # 3. no look-ahead: perturbing every row after the origin leaves the forecast unchanged
    df2 = df.copy(); df2.loc[df2.gaming_date > o, Y] *= 3.0
    tr2, fut2, _ = harness._split(df2, o, TRAIN_END)
    for s in GRID[::9]:
        assert np.allclose(make(s)(tr, fut, Y), make(s)(tr2, fut2, Y))
    # 4. reproduces iteration 3's "EL + anchor 100% (28d)" on Jan-Apr refresh CV (CV MAE $4,052 there)
    d = run_all("refresh", "cv")
    d12 = d[d.origin <= pd.Timestamp("2025-04-18")]  # iteration 3's 12 origins
    print("EL x mean28d [excl] w=100% refresh CV MAE (iter3 origins):",
          round(mae(d12["EL x mean28d [excl] w=100%"] - d12.actual)), "| EL:", round(mae(d12["EL"] - d12.actual)))
    print("checks passed")


if __name__ == "__main__":
    {"cv": stage_cv, "holdout": stage_holdout, "check": stage_check}[sys.argv[1]]()
