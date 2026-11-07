"""Iteration 2: a wider model search against the current best (Iteration 1, event-type lift "EL").

Every model is f(train, future, target) -> np.ndarray (harness contract). Inputs are only what is
known on the origin = train.gaming_date.max(): the calendar, events announced by the origin, the
walkway renovation schedule (floor_walkways), and other tables filtered to dates <= origin.

Families
- EL refinements: holiday term, structural level shifts (walkway closure, 300 -> 308 machines),
  recency-weighted / recent-level base, robust base, day-of-month (payday) term.
- Classical TS on the event-adjusted series (statsforecast AutoETS / AutoARIMA / AutoTheta / MSTL),
  event lift re-applied: "adjust, forecast, re-apply" (classical decomposition forecasting).
- Prophet (flat and linear growth) on the event-adjusted series.
- Gradient boosting (CatBoost, XGBoost) fitted to EL's log residuals (boosted residual correction).
- Bottom-up: EL per zone, summed; and theo = coin-in forecast x recent theo-hold.
- Forecast combinations (equal-weight geometric means).
"""
from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))
from common import load  # noqa: E402
from ds_alpha.models import EVENT_CLASS, event_labels  # noqa: E402

warnings.filterwarnings("ignore")
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)

CLOSURE = (pd.Timestamp("2025-03-03"), pd.Timestamp("2025-04-06"))  # W-ENT-B40 renovation (floor_walkways)


# ----------------------------------------------------------------------------- EL core
def _shrunk(x: pd.Series, prior: float, k: float) -> float:
    return (len(x) * x.mean() + k * prior) / (len(x) + k) if len(x) else prior


def el_lifts(tr, fut, y, base_fn=None, k=3.0):
    """EL's hierarchical event lift. Returns (lift_train, lift_future, is_event_train, base_series_fn)."""
    origin = tr.gaming_date.max()
    lt, lf = event_labels(tr.gaming_date, origin), event_labels(fut.gaming_date, origin)
    is_ev = lt.event_id.notna().to_numpy()
    base_tr = (base_fn or base_mean)(tr, ~is_ev, y)            # per-row base for train rows
    r = pd.Series(tr[y].to_numpy()[is_ev] / base_tr[is_ev])
    typ, cls = lt.event_type[is_ev].to_numpy(), lt.eclass[is_ev].to_numpy()
    pooled = r.mean() if len(r) else 1.0
    cl = {c: _shrunk(x, pooled, k) for c, x in r.groupby(cls)}
    ty = {t: _shrunk(x, cl[EVENT_CLASS.get(t, "leisure")], k) for t, x in r.groupby(typ)}

    def lift_of(labels):
        return np.array([1.0 if t is None else ty.get(t, cl.get(c, pooled))
                         for t, c in zip(labels.event_type, labels.eclass)])
    return lift_of(lt), lift_of(lf), is_ev


def _base_mean(tr, mask, y, w=None):
    """Per-row non-event weekday mean (optionally weighted). Returns array aligned with tr."""
    d = tr.dow.to_numpy()
    v = tr[y].to_numpy()
    w = np.ones(len(tr)) if w is None else w
    m = {k: np.sum((v * w)[mask & (d == k)]) / np.sum(w[mask & (d == k)]) for k in range(7)}
    return np.array([m[k] for k in d]), m


def base_mean(tr, mask, y):
    return _base_mean(tr, mask, y)[0]


def make_el(base="mean", half_life=None, holiday_k=None, structural=False, dom_k=None, level_days=None, k=3.0):
    """EL with optional refinements. base in {"mean", "median"}."""
    def f(tr, fut, y):
        origin = tr.gaming_date.max()
        trd, fud = tr.gaming_date, fut.gaming_date
        lt, lf, is_ev = el_lifts(tr, fut, y, k=k)
        v = tr[y].to_numpy().astype(float)
        mult_tr, mult_fu = np.ones(len(tr)), np.ones(len(fut))

        # structural level shifts known at origin: closure window and the Mar 24 machine add
        if structural:
            for name, (s, e) in {"closure": CLOSURE,
                                 "cap308": (pd.Timestamp("2025-03-24"), pd.Timestamp("2099-01-01"))}.items():
                in_tr = ((trd >= s) & (trd <= e)).to_numpy()
                in_fu = ((fud >= s) & (fud <= e)).to_numpy()
                ok = in_tr & ~is_ev
                if ok.sum() >= 7 and (~in_tr & ~is_ev).sum() >= 14:
                    cur = v / mult_tr  # sequential: the machine add is measured on closure-adjusted data
                    b_out, _ = _base_mean(tr.assign(**{y: cur}), ~in_tr & ~is_ev, y)
                    ratio = np.mean(cur[ok] / b_out[ok])
                    mult_tr[in_tr] *= ratio
                    mult_fu[in_fu] *= ratio

        hol_tr = tr.holiday.to_numpy() == 1
        mask = ~is_ev & (~hol_tr if holiday_k is not None else True)
        w = None
        if half_life:
            age = (origin - trd).dt.days.to_numpy()
            w = 0.5 ** (age / half_life)
        vadj = v / mult_tr
        trx = tr.assign(**{y: vadj})
        if base == "median":
            d = tr.dow.to_numpy()
            m = {kk: np.median(vadj[mask & (d == kk)]) for kk in range(7)}
            btr = np.array([m[kk] for kk in d])
        else:
            btr, m = _base_mean(trx, mask, y, w)
        bfu = fut.dow.map(m).to_numpy().astype(float)

        if level_days:  # rescale the weekday profile to the last `level_days` non-event days' level
            rec = mask & ((origin - trd).dt.days.to_numpy() < level_days)
            bfu = bfu * np.mean(vadj[rec] / btr[rec])

        extra = np.ones(len(fut))
        if holiday_k is not None:
            ok = hol_tr & ~is_ev
            hr = pd.Series(vadj[ok] / btr[ok])
            extra *= np.where(fut.holiday.to_numpy() == 1, _shrunk(hr, 1.0, holiday_k), 1.0)
        if dom_k is not None:  # payday buckets: 1-3, 4-14, 15-17, 18-end
            def bucket(s):
                dd = s.dt.day.to_numpy()
                return np.select([dd <= 3, dd <= 14, dd <= 17], [0, 1, 2], 3)
            bt, bf = bucket(trd), bucket(fud)
            rr = vadj / btr
            for b in range(4):
                sel = mask & (bt == b)
                extra[bf == b] *= _shrunk(pd.Series(rr[sel]), 1.0, dom_k) / _shrunk(pd.Series(rr[mask]), 1.0, dom_k)
        return bfu * mult_fu * lf * extra
    return f


EL = make_el()


# ----------------------------------------------------------------------------- adjust -> forecast -> re-apply
def _adjusted(tr, fut, y):
    lt, lf, _ = el_lifts(tr, fut, y)
    return tr[y].to_numpy() / lt, lf


def make_sf(kind: str):
    """statsforecast model on the event-adjusted series, lift re-applied."""
    def f(tr, fut, y):
        from statsforecast.models import MSTL, AutoARIMA, AutoETS, AutoTheta
        adj, lf = _adjusted(tr, fut, y)
        mdl = {"ets": lambda: AutoETS(season_length=7),
               "arima": lambda: AutoARIMA(season_length=7),
               "theta": lambda: AutoTheta(season_length=7),
               "mstl": lambda: MSTL(season_length=7, trend_forecaster=AutoETS(model="ZNN"))}[kind]()
        p = mdl.forecast(y=adj.astype(float), h=len(fut))["mean"]
        return np.asarray(p) * lf
    return f


def make_prophet(growth: str = "flat"):
    def f(tr, fut, y):
        from prophet import Prophet
        adj, lf = _adjusted(tr, fut, y)
        df = pd.DataFrame({"ds": tr.gaming_date.to_numpy(), "y": np.log(adj)})
        m = Prophet(growth=growth, weekly_seasonality=True, yearly_seasonality=False, daily_seasonality=False,
                    changepoint_prior_scale=0.01, seasonality_mode="additive")
        m.fit(df)
        p = m.predict(pd.DataFrame({"ds": fut.gaming_date.to_numpy()}))["yhat"].to_numpy()
        sigma2 = np.var(np.log(adj) - m.predict(df[["ds"]])["yhat"].to_numpy())
        return np.exp(p + sigma2 / 2) * lf
    return f


# ----------------------------------------------------------------------------- boosted residual correction
def _feats(df):
    d = df.gaming_date
    return pd.DataFrame({"dow": df.dow.to_numpy(), "dom": d.dt.day.to_numpy(), "holiday": df.holiday.to_numpy(),
                         "t": df.t.to_numpy(), "dim": d.dt.days_in_month.to_numpy() - d.dt.day.to_numpy()})


def make_gbm_resid(lib: str = "catboost", use_t: bool = False):
    """Fit a heavily regularised GBM to log(actual / EL in-sample) on calendar features."""
    def f(tr, fut, y):
        base = EL(tr, tr, y)  # in-sample EL fit (base + lifts from the same train)
        r = np.log(tr[y].to_numpy() / base)
        X, Xf = _feats(tr), _feats(fut)
        if not use_t:
            X, Xf = X.drop(columns="t"), Xf.drop(columns="t")
        if lib == "catboost":
            from catboost import CatBoostRegressor
            m = CatBoostRegressor(iterations=200, depth=2, learning_rate=0.03, l2_leaf_reg=10, verbose=0,
                                  random_seed=0, loss_function="MAE")
        else:
            from xgboost import XGBRegressor
            m = XGBRegressor(n_estimators=200, max_depth=2, learning_rate=0.03, reg_lambda=10, subsample=0.8,
                             random_state=0, objective="reg:absoluteerror")
        m.fit(X, r)
        return EL(tr, fut, y) * np.exp(m.predict(Xf))
    return f


def make_gbm_direct(lib: str = "catboost"):
    """GBM on log y with calendar features + EL event lift as a numeric feature."""
    def f(tr, fut, y):
        lt, lf, _ = el_lifts(tr, fut, y)
        X, Xf = _feats(tr).assign(lift=lt), _feats(fut).assign(lift=lf)
        if lib == "catboost":
            from catboost import CatBoostRegressor
            m = CatBoostRegressor(iterations=400, depth=3, learning_rate=0.05, verbose=0, random_seed=0)
        else:
            from xgboost import XGBRegressor
            m = XGBRegressor(n_estimators=400, max_depth=3, learning_rate=0.05, random_state=0)
        m.fit(X, np.log(tr[y]))
        return np.exp(m.predict(Xf))
    return f


# ----------------------------------------------------------------------------- bottom-up / decompositions
_ZONE = None


def _zone_day():
    global _ZONE
    if _ZONE is None:
        v = load("1_prepared_views/prepared_daily_view.parquet")
        v = v[v.active]
        _ZONE = v.groupby(["gaming_date", "zone_id"])[["theo_usd", "coin_in_usd"]].sum().reset_index()
        _ZONE["gaming_date"] = pd.to_datetime(_ZONE.gaming_date)
    return _ZONE


def el_bottom_up(tr, fut, y):
    """EL fitted per zone (zone-specific weekday profile and event lifts), summed."""
    z = _zone_day()
    z = z[z.gaming_date <= tr.gaming_date.max()]
    cols = ["gaming_date", "dow", "event", "holiday", "t"]
    total = np.zeros(len(fut))
    for zid, g in z.groupby("zone_id"):
        trz = tr[cols].merge(g[["gaming_date", y]], on="gaming_date", how="inner")
        total += EL(trz, fut, y)
    return total


def theo_via_coin_in(hold_days: int = 28):
    """theo = EL(coin-in) x theo-hold of the last `hold_days` days (theo target only)."""
    def f(tr, fut, y):
        if y != "theo_usd":
            return EL(tr, fut, y)
        last = tr[tr.gaming_date > tr.gaming_date.max() - pd.Timedelta(days=hold_days)]
        return EL(tr, fut, "coin_in_usd") * last.theo_usd.sum() / last.coin_in_usd.sum()
    return f


# ----------------------------------------------------------------------------- combinations
def combo(*fs):
    def f(tr, fut, y):
        return np.exp(np.mean([np.log(g(tr, fut, y)) for g in fs], axis=0))
    return f


CANDIDATES = {
    # reference
    "EL (iteration 1, current best)": EL,
    # EL refinements
    "EL + holiday term": make_el(holiday_k=3),
    "EL + structural shifts (closure, 308 machines)": make_el(structural=True),
    "EL + recency-weighted base (hl 28d)": make_el(half_life=28),
    "EL + recency-weighted base (hl 56d)": make_el(half_life=56),
    "EL + recent-level rescale (28d)": make_el(level_days=28),
    "EL, median base": make_el(base="median"),
    "EL + payday (day-of-month) term": make_el(dom_k=10),
    "EL + holiday + structural": make_el(holiday_k=3, structural=True),
    # classical TS on event-adjusted series
    "AutoETS on event-adjusted": make_sf("ets"),
    "AutoARIMA on event-adjusted": make_sf("arima"),
    "AutoTheta on event-adjusted": make_sf("theta"),
    "MSTL on event-adjusted": make_sf("mstl"),
    "Prophet (flat) on event-adjusted": make_prophet("flat"),
    "Prophet (linear) on event-adjusted": make_prophet("linear"),
    # boosting
    "EL x CatBoost residual (calendar)": make_gbm_resid("catboost"),
    "EL x XGBoost residual (calendar)": make_gbm_resid("xgboost"),
    "CatBoost direct (calendar + lift)": make_gbm_direct("catboost"),
    "XGBoost direct (calendar + lift)": make_gbm_direct("xgboost"),
    # bottom-up / decomposition
    "EL bottom-up by zone": el_bottom_up,
    "EL coin-in x recent theo-hold": theo_via_coin_in(28),
    # combinations
    "Combo: EL + AutoETS-adj": combo(EL, make_sf("ets")),
    "Combo: EL + AutoTheta-adj + AutoETS-adj": combo(EL, make_sf("theta"), make_sf("ets")),
    "Combo: EL + bottom-up + structural": combo(EL, el_bottom_up, make_el(structural=True)),
}


# ----------------------------------------------------------------------------- sensitivity variants (round 2)
VARIANTS = {
    "EL + recent-level rescale (14d)": make_el(level_days=14),
    "EL + recent-level rescale (42d)": make_el(level_days=42),
    "EL + recent-level rescale (56d)": make_el(level_days=56),
    "EL + recent-level (28d) + payday": make_el(level_days=28, dom_k=10),
    "Combo: EL-level28 + AutoTheta-adj": combo(make_el(level_days=28), make_sf("theta")),
    "Combo: EL-level28 + AutoTheta-adj + Prophet-lin-adj": combo(make_el(level_days=28), make_sf("theta"),
                                                                 make_prophet("linear")),
}
CANDIDATES.update(VARIANTS)
