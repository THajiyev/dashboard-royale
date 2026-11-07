"""Shared evaluation harness for the "beat B2" search. Every agent uses this, unchanged.

Target to beat: B2 event-aware weekday, May–Jun holdout MAE on daily property theo = $4,460.28
(coin-in $46,671.25 reported as a secondary check).

Rules this harness enforces
- A model is f(train, future, target) -> np.ndarray of daily forecasts (dollars), one per `future` row.
- `future` holds ONLY inputs known on the forecast origin: FUTURE_COLS. No actuals, no events_active
  (it includes the Locals week, announced 2025-05-26, after the Apr 30 origin).
- `train` holds full property_day rows up to the origin. Other tables may be used only for dates
  <= origin (check this yourself; the coordinator audits every submission).
- Develop with cv() (rolling origins inside Jan–Apr). The holdout is touched only through submit(),
  which is capped at MAX_SUBMISSIONS per agent and logs every call, win or lose.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import forecast  # noqa: E402
from common import TRAIN_END  # noqa: E402

FUTURE_COLS = ["gaming_date", "local_weekday", "weekday", "dow", "event", "holiday", "federal_holiday", "t"]
B2_HOLDOUT = {"theo_usd": 4460.276, "coin_in_usd": 46671.254}
MAX_SUBMISSIONS = 3
CV_ORIGINS = pd.date_range("2025-02-28", "2025-04-16", freq="7D")  # 7 origins, horizons 14–61 days


def frame() -> pd.DataFrame:
    return forecast.daily_frame()


def _split(df, origin, end):
    tr = df[df.gaming_date <= origin].copy()
    fut = df[(df.gaming_date > origin) & (df.gaming_date <= end)]
    return tr, fut[FUTURE_COLS].copy(), fut


def _run(f, tr, fut, target):
    p = np.asarray(f(tr, fut, target), float)
    assert p.shape == (len(fut),), f"expected {len(fut)} forecasts, got {p.shape}"
    assert np.all(np.isfinite(p)) and np.all(p > 0), "forecasts must be finite and positive"
    return p


def cv(f, target: str = "theo_usd") -> dict:
    """Rolling-origin CV inside Jan–Apr. Returns mean MAE of f and of B2 on the same folds."""
    df = frame()
    df = df[df.gaming_date <= TRAIN_END]
    m, b = [], []
    for o in CV_ORIGINS:
        tr, fut, full = _split(df, o, TRAIN_END)
        y = full[target].to_numpy()
        m.append(np.mean(np.abs(_run(f, tr, fut, target) - y)))
        b.append(np.mean(np.abs(_run(forecast.m_b2, tr, fut, target) - y)))
    return {"cv_mae": float(np.mean(m)), "cv_mae_b2": float(np.mean(b)), "cv_skill_vs_b2": 1 - np.mean(m) / np.mean(b),
            "folds_won": int(np.sum(np.array(m) < np.array(b))), "folds": len(m)}


def dm_test(e1: np.ndarray, e2: np.ndarray, h: int = 1) -> float:
    """Diebold–Mariano p-value (one-sided: model 1 has lower absolute error), HAC variance."""
    d = np.abs(e1) - np.abs(e2)
    n = len(d)
    lags = max(1, int(np.floor(n ** (1 / 3))))
    g = [np.mean((d[k:] - d.mean()) * (d[:n - k] - d.mean())) for k in range(lags + 1)]
    var = (g[0] + 2 * sum((1 - k / (lags + 1)) * g[k] for k in range(1, lags + 1))) / n
    return float(stats.norm.cdf(d.mean() / np.sqrt(var)))


def submit(agent: str, name: str, f, description: str) -> dict:
    """Score on the May–Jun holdout (counts against the agent's budget). CV is computed first."""
    log = HERE / f"leaderboard_{agent}.jsonl"
    prior = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
    if len(prior) >= MAX_SUBMISSIONS:
        raise RuntimeError(f"{agent} has used all {MAX_SUBMISSIONS} holdout submissions")
    rec = {"agent": agent, "model": name, "description": description, "time": datetime.now().isoformat(timespec="seconds")}
    for target in ["theo_usd", "coin_in_usd"]:
        c = cv(f, target)
        df = frame()
        tr, fut, full = _split(df, TRAIN_END, pd.Timestamp("2025-06-30"))
        y = full[target].to_numpy()
        p = _run(f, tr, fut, target)
        pb2 = _run(forecast.m_b2, tr, fut, target)
        mae = float(np.mean(np.abs(p - y)))
        rec[target] = {**c, "holdout_mae": mae, "holdout_mae_b2": float(np.mean(np.abs(pb2 - y))),
                       "holdout_bias": float(np.mean(p - y)), "beats_b2": mae < B2_HOLDOUT[target],
                       "dm_p_vs_b2": dm_test(p - y, pb2 - y)}
    rec["WIN"] = bool(rec["theo_usd"]["beats_b2"])
    with log.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(json.dumps(rec, indent=2))
    return rec
