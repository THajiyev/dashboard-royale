"""Shared loading, time split and scoring for the modelling work.

Ground rules (GUIDE.md §5, §7):
- train on gaming dates Jan 1 – Apr 30 2025, test on May 1 – Jun 30 2025;
- active machine-days only; ratios from sums;
- only inputs known on the forecast date.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(ROOT / "scripts"))
from build_reports import load  # noqa: E402  (Decimal -> float, date -> datetime64)

TRAIN_END = pd.Timestamp("2025-04-30")
TEST_START = pd.Timestamp("2025-05-01")
WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def split_by_date(df: pd.DataFrame, col: str = "gaming_date") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Time-based split; asserts that no test-period row leaks into training."""
    d = pd.to_datetime(df[col])
    train, test = df[d <= TRAIN_END], df[d >= TEST_START]
    assert pd.to_datetime(train[col]).max() < TEST_START, "leakage: test rows in training set"
    assert len(train) + len(test) == len(df), "rows fall outside the train/test window"
    return train, test


def property_day() -> pd.DataFrame:
    return load("1_prepared_views/property_day.parquet").sort_values("gaming_date").reset_index(drop=True)


def active_machine_days() -> pd.DataFrame:
    """prepared_daily_view (active rows) + raw meter columns and game math needed for luck variance."""
    v = load("1_prepared_views/prepared_daily_view.parquet")
    v = v[v.active].copy()
    md = load("2_machine_decision/machine_day.parquet")[
        ["machine_id", "gaming_date", "scheduled_seconds", "available_seconds", "payout_positive_spins",
         "sum_bet_squared", "house_win_cents", "theo_cents"]]
    v = v.merge(md, on=["machine_id", "gaming_date"], how="left", validate="1:1")
    gm = load("2_machine_decision/game_math.parquet").set_index("config_id")
    v["payout_var"] = v.config_id.map(gm.payout_multiplier_variance).astype(float)
    v["hit_prob"] = v.config_id.map(gm.hit_probability).astype(float)
    # Var(house win) in cents^2 = sum over spins of bet^2 * Var(payout/bet)
    v["win_var_cents2"] = v.sum_bet_squared * v.payout_var
    v["downtime_hours"] = (v.scheduled_seconds - v.available_seconds) / 3600
    return v


def score(y, yhat, lo=None, hi=None, ref_mae: float | None = None) -> dict:
    y, yhat = np.asarray(y, float), np.asarray(yhat, float)
    err = yhat - y
    out = {
        "MAE": np.mean(np.abs(err)),
        "RMSE": np.sqrt(np.mean(err ** 2)),
        "MAPE": np.mean(np.abs(err) / np.abs(y)) if np.all(y != 0) else np.nan,
        "bias": np.mean(err),
        "n": len(y),
    }
    if ref_mae:
        out["skill_vs_ref"] = 1 - out["MAE"] / ref_mae
    if lo is not None and hi is not None:
        out["coverage"] = np.mean((y >= np.asarray(lo)) & (y <= np.asarray(hi)))
    return out
