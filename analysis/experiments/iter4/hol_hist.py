"""Iteration 4: holiday-proximity features and prior-year (historical) patterns.

Two families, each a *wrapper* around an existing base forecast (EL for the fixed protocol, EL2 + 28-day
anchor for the weekly refresh), so any gain is attributable to the new inputs only.

Holiday proximity (`with_holidays`)
    Holiday dates are fixed calendar facts, known years ahead, so they are legal inputs at any origin.
    Features per day, from the signed distance d = date - nearest holiday:
      day      : on a federal holiday
      longwknd : Fri-Mon of a Monday federal holiday (MLK, Presidents, Memorial)
      near_k   : |d| <= k to any major holiday (boolean)
      kernel_t : exp(-|d|/t), separate before/after coefficients (a "how close" metric)
      bins     : before (-3..-1), on (0), after (+1..+3) dummies
    Coefficients are ridge-regressed on training log residuals of the base (non-event days, local level
    removed with a centred 15-day rolling median), with ridge `lam` in pseudo-days, i.e. shrunk to "no effect".
    `with_holiday_gbm` fits LightGBM on the same residuals with all the features instead.

Historical patterns (`with_history`)
    The casino's own data starts 2025-01-01, so history comes from LVCVA Las Vegas visitor volume:
      2023 and 2024 by month (lvcva_history.csv, from the LVCVA monthly Executive Summaries, public before 2025),
      2025 by month (in-repo city_visitation_monthly), used only once published (month end + 30 days).
    City level per day L(date) (piecewise-linear between mid-months):
      seasonal       : average of the 2023 and 2024 per-day visitor shapes (each year normalised to its Jan-Jun mean)
      season_yoy     : 2024 per-day visitors x (1 + latest published 2025 YoY), for months not yet published;
                       published 2025 months use their actual value. This carries the city's year-over-year
                       momentum into the forecast.
    The base is fitted to y / L^beta (training) and its forecast multiplied by L^beta (future); beta is the
    property's elasticity to the city level, chosen by CV.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent.parent))
from common import load  # noqa: E402
from ds_alpha.models import event_labels  # noqa: E402

# ----------------------------------------------------------------------------- holiday calendar
FEDERAL = pd.to_datetime(["2025-01-01", "2025-01-20", "2025-02-17", "2025-05-26", "2025-06-19", "2025-07-04"])
MONDAY_FEDERAL = pd.to_datetime(["2025-01-20", "2025-02-17", "2025-05-26"])
OTHER_MAJOR = pd.to_datetime(["2025-02-14",   # Valentine's Day
                              "2025-04-20",   # Easter
                              "2025-05-11",   # Mother's Day
                              "2025-06-15"])  # Father's Day
MAJOR = FEDERAL.union(OTHER_MAJOR)


def _signed_dist(dates, hols):
    d = pd.to_datetime(pd.Series(dates)).to_numpy().astype("datetime64[D]").astype(int)
    h = hols.to_numpy().astype("datetime64[D]").astype(int)
    diff = d[:, None] - h[None, :]
    return diff[np.arange(len(d)), np.abs(diff).argmin(1)]


def holiday_features(dates, kind: str) -> np.ndarray:
    dates = pd.to_datetime(pd.Series(dates)).reset_index(drop=True)
    dist = _signed_dist(dates, MAJOR)
    if kind == "day":
        return dates.isin(FEDERAL).to_numpy(float)[:, None]
    if kind == "longwknd":
        dm = _signed_dist(dates, MONDAY_FEDERAL)
        return ((dm >= -3) & (dm <= 0)).astype(float)[:, None]
    if kind.startswith("near"):
        k = int(kind[4:])
        return (np.abs(dist) <= k).astype(float)[:, None]
    if kind.startswith("kernel"):
        t = float(kind[6:])
        k = np.exp(-np.abs(dist) / t)
        return np.c_[np.where(dist < 0, k, 0), np.where(dist == 0, 1.0, 0), np.where(dist > 0, k, 0)]
    if kind == "bins":
        return np.c_[(dist >= -3) & (dist <= -1), dist == 0, (dist >= 1) & (dist <= 3)].astype(float)
    if kind == "longwknd+day":
        return np.c_[holiday_features(dates, "longwknd"), holiday_features(dates, "day")]
    raise ValueError(kind)


def _residuals(tr, y, origin):
    """log(actual / weekday profile) on non-event training days, local level removed."""
    lab = event_labels(tr.gaming_date, origin)
    ev = lab.event_id.notna().to_numpy()
    prof = tr[~ev].groupby("dow")[y].mean()
    r = pd.Series(np.log(tr[y].to_numpy() / tr.dow.map(prof).to_numpy()), index=tr.index)
    lvl = r.where(~ev).rolling(15, center=True, min_periods=5).median()
    return (r - lvl).to_numpy(), ~ev & lvl.notna().to_numpy()


def with_holidays(base, kind: str, lam: float = 5.0):
    def f(tr, fut, y):
        origin = tr.gaming_date.max()
        r, ok = _residuals(tr, y, origin)
        X = holiday_features(tr.gaming_date, kind)[ok]
        beta = np.linalg.solve(X.T @ X + lam * np.eye(X.shape[1]), X.T @ r[ok])
        return base(tr, fut, y) * np.exp(holiday_features(fut.gaming_date, kind) @ beta)
    return f


def _gbm_X(dates):
    dates = pd.to_datetime(pd.Series(dates)).reset_index(drop=True)
    dist = _signed_dist(dates, MAJOR)
    return np.c_[np.clip(dist, -7, 7), np.abs(np.clip(dist, -7, 7)), dates.dt.dayofweek,
                 holiday_features(dates, "day"), holiday_features(dates, "longwknd")]


def with_holiday_gbm(base):
    import lightgbm as lgb

    def f(tr, fut, y):
        r, ok = _residuals(tr, y, tr.gaming_date.max())
        m = lgb.LGBMRegressor(n_estimators=150, learning_rate=0.03, num_leaves=4, min_child_samples=8,
                              reg_lambda=5.0, random_state=0, verbose=-1)
        m.fit(_gbm_X(tr.gaming_date)[ok], r[ok])
        return base(tr, fut, y) * np.exp(m.predict(_gbm_X(fut.gaming_date)))
    return f


# ----------------------------------------------------------------------------- historical city level
def _hist():
    h = pd.read_csv(HERE / "lvcva_history.csv")
    h["pd"] = h.visitor_volume / h.days
    return h.pivot(index="month", columns="year", values="pd")  # per-day visitors, months 1..6


def _v2025():
    c = load("4_context/real_sources/city_visitation_monthly.parquet")
    c["m"] = pd.to_datetime(c.month).dt.month
    return c.set_index("m").mean_visitors_per_calendar_day.astype(float)


def _published(origin):
    """2025 months whose LVCVA figures were public at `origin` (month end + 30 days)."""
    out = []
    for m in range(1, 13):
        end = pd.Timestamp(2025, m, 1) + pd.offsets.MonthEnd(0)
        if end + pd.Timedelta(days=30) <= origin:
            out.append(m)
    return out


def city_monthly(origin, source: str) -> pd.Series:
    h = _hist()
    if source == "seasonal":
        idx = (h[2023] / h[2023].mean() + h[2024] / h[2024].mean()) / 2
        return idx
    if source == "season_yoy":
        v25, pub = _v2025(), _published(origin)
        if not pub:
            return h[2024] / h[2024].mean()
        yoy = v25.loc[pub[-1]] / h[2024].loc[pub[-1]]  # latest published per-day YoY
        L = h[2024] * yoy
        for m in pub:
            L.loc[m] = v25.loc[m]
        return L / h[2024].mean()
    raise ValueError(source)


def city_daily(dates, origin, source):
    """Piecewise-linear interpolation between mid-month points (flat beyond the ends)."""
    L = city_monthly(origin, source)
    mids = np.array([(pd.Timestamp(2025, m, 15) - pd.Timestamp("2025-01-01")).days for m in L.index], float)
    t = (pd.to_datetime(pd.Series(dates)) - pd.Timestamp("2025-01-01")).dt.days.to_numpy(float)
    return np.interp(t, mids, L.to_numpy())


def with_history(base, source: str, beta: float = 1.0):
    def f(tr, fut, y):
        origin = tr.gaming_date.max()
        s_tr = city_daily(tr.gaming_date, origin, source) ** beta
        s_fu = city_daily(fut.gaming_date, origin, source) ** beta
        tr2 = tr.copy()
        tr2[y] = tr[y].to_numpy() / s_tr
        return base(tr2, fut, y) * s_fu
    return f
