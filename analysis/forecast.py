"""Phase 2: daily property forecasts (theo, coin-in) vs the Phase 0 baselines.

Protocol (GUIDE §5, §7):
- Every model sees Jan–Apr only. Model choice is made on rolling-origin CV *inside* Jan–Apr,
  then the chosen model is scored once on May–Jun. The holdout never drives a choice.
- Inputs are known on Apr 30: weekday, federal holiday, events announced by Apr 30, a time index.
  No lagged actuals, so the 61-day forecast is a true multi-horizon forecast with no holdout leakage.
- Models work on log(y), so weekday and event effects are multiplicative.
- 90% intervals: split-conformal on the CV residuals (model-agnostic), plus the native Bayesian
  posterior for BayesianRidge.
"""
from __future__ import annotations

import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from sklearn.linear_model import BayesianRidge
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.statespace.structural import UnobservedComponents

from baselines import known_event_days
from common import TRAIN_END, WEEK, load, score, split_by_date

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", module="statsmodels")

T0 = pd.Timestamp("2025-01-01")
CV_ORIGINS = [pd.Timestamp("2025-02-28"), pd.Timestamp("2025-03-31")]  # train ≤ origin, test ≤ Apr 30
JULY_HOLIDAYS = {pd.Timestamp("2025-07-04"): "Independence Day"}


# ----------------------------------------------------------------------------- data
def daily_frame(as_of: pd.Timestamp = TRAIN_END) -> pd.DataFrame:
    """property_day + calendar inputs that are known on `as_of`."""
    p = load("1_prepared_views/property_day.parquet").sort_values("gaming_date").reset_index(drop=True)
    cal = load("2_machine_decision/calendar_day.parquet")[["gaming_date", "federal_holiday"]]
    p = p.merge(cal, on="gaming_date", how="left", validate="1:1")
    return add_calendar(p, as_of)


def add_calendar(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    df = df.copy()
    d = pd.to_datetime(df.gaming_date)
    df["dow"] = d.dt.dayofweek
    df["weekday"] = df.dow.map(dict(enumerate(WEEK)))
    df["event"] = known_event_days(d, as_of).astype(float)
    df["holiday"] = df.federal_holiday.notna().astype(float)
    df["t"] = (d - T0).dt.days.astype(float)
    return df


def design(df: pd.DataFrame, trend: bool = True) -> pd.DataFrame:
    X = pd.get_dummies(df.dow, prefix="dow", drop_first=True).astype(float)
    for d in range(1, 7):  # stable columns even when a fold lacks a weekday
        X[f"dow_{d}"] = X.get(f"dow_{d}", 0.0)
    X = X[[f"dow_{d}" for d in range(1, 7)]]
    X["event"], X["holiday"] = df.event.to_numpy(), df.holiday.to_numpy()
    if trend:
        X["t"] = df.t.to_numpy() / 100
    return sm.add_constant(X, has_constant="add")


# ----------------------------------------------------------------------------- models
# each: f(train, test, target) -> np.ndarray of point forecasts (dollars)
def m_b1(tr, te, y):
    return te.dow.map(tr.groupby("dow")[y].mean()).to_numpy()


def m_b2(tr, te, y):
    base = tr[tr.event == 0].groupby("dow")[y].mean()
    ev = tr[tr.event == 1]
    lift = (ev[y] / ev.dow.map(base)).mean() if len(ev) else 1.0
    return te.dow.map(base).to_numpy() * np.where(te.event == 1, lift, 1.0)


def _ols(trend):
    def f(tr, te, y):
        r = sm.OLS(np.log(tr[y]), design(tr, trend)).fit()
        return np.exp(r.predict(design(te, trend)) + r.mse_resid / 2)  # log-normal mean correction
    return f


def m_ets(tr, te, y):
    r = ExponentialSmoothing(tr[y].to_numpy(), seasonal="mul", seasonal_periods=7, trend=None,
                             initialization_method="estimated").fit()
    return r.forecast(len(te))


def m_ets_event(tr, te, y):
    """ETS fitted on event-adjusted series, event lift re-applied (lift from OLS on train)."""
    lift = np.exp(sm.OLS(np.log(tr[y]), design(tr, False)).fit().params["event"])
    adj = tr[y].to_numpy() / np.where(tr.event == 1, lift, 1.0)
    r = ExponentialSmoothing(adj, seasonal="mul", seasonal_periods=7, initialization_method="estimated").fit()
    return r.forecast(len(te)) * np.where(te.event == 1, lift, 1.0)


def _exog(df):
    return design(df, trend=False).drop(columns="const")


def m_sarimax(tr, te, y):
    """Regression with AR(1) errors: log y ~ weekday + event + holiday, errors AR(1)."""
    r = SARIMAX(np.log(tr[y].to_numpy()), exog=_exog(tr), order=(1, 0, 0), trend="c").fit(disp=False)
    return np.exp(r.forecast(len(te), exog=_exog(te)) + np.asarray(r.params)[-1] / 2)  # + sigma2/2


def m_ucm(tr, te, y):
    """Structural time series: local level + weekday regressors + event/holiday."""
    r = UnobservedComponents(np.log(tr[y].to_numpy()), level="local level", exog=_exog(tr)).fit(disp=False)
    return np.exp(r.forecast(len(te), exog=_exog(te)))


def m_lgbm(tr, te, y):
    cols = ["dow", "event", "holiday", "t"]
    mdl = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=7, min_child_samples=5,
                            subsample=0.8, subsample_freq=1, random_state=42, verbose=-1)
    mdl.fit(tr[cols], np.log(tr[y]))
    return np.exp(mdl.predict(te[cols]))


def m_bayes_ridge(tr, te, y, return_std=False):
    X, Xt = design(tr, True).drop(columns="const"), design(te, True).drop(columns="const")
    r = BayesianRidge().fit(X, np.log(tr[y]))
    mu, sd = r.predict(Xt, return_std=True)
    return (np.exp(mu), sd) if return_std else np.exp(mu + sd ** 2 / 2)


MODELS = {
    "B0 constant mean": lambda tr, te, y: np.full(len(te), tr[y].mean()),
    "B1 weekday mean": m_b1,
    "B2 event-aware weekday": m_b2,
    "OLS log (weekday+event+holiday)": _ols(False),
    "OLS log + linear trend": _ols(True),
    "ETS weekly (mult.)": m_ets,
    "ETS weekly, event-adjusted": m_ets_event,
    "Regression + AR(1) errors": m_sarimax,
    "Structural (local level + regressors)": m_ucm,
    "LightGBM (calendar)": m_lgbm,
    "Bayesian ridge (log, trend)": m_bayes_ridge,
}
STACK = {"B0 constant mean": "baseline", "B1 weekday mean": "baseline", "B2 event-aware weekday": "baseline",
         "OLS log (weekday+event+holiday)": "lightweight", "OLS log + linear trend": "lightweight",
         "ETS weekly (mult.)": "lightweight", "ETS weekly, event-adjusted": "lightweight",
         "Regression + AR(1) errors": "lightweight", "Structural (local level + regressors)": "lightweight",
         "LightGBM (calendar)": "ML", "Bayesian ridge (log, trend)": "Bayesian"}


# ----------------------------------------------------------------------------- evaluation
def rolling_cv(df: pd.DataFrame, target: str) -> tuple[pd.DataFrame, dict]:
    """Rolling-origin CV inside Jan–Apr. Returns (CV MAE per model, log residuals per model)."""
    train_all = df[df.gaming_date <= TRAIN_END]
    rows, resid = [], {m: [] for m in MODELS}
    for origin in CV_ORIGINS:
        tr, te = train_all[train_all.gaming_date <= origin], train_all[train_all.gaming_date > origin]
        for name, f in MODELS.items():
            p = f(tr, te, target)
            resid[name].append(np.log(te[target].to_numpy() / p))
            rows.append({"model": name, "origin": origin.date(), "cv_mae": np.mean(np.abs(p - te[target]))})
    cv = pd.DataFrame(rows).groupby("model", sort=False).cv_mae.mean()
    ens = cv.drop([m for m in cv.index if STACK[m] == "baseline"]).nsmallest(3).index.tolist()
    return cv, {k: np.concatenate(v) for k, v in resid.items()}, ens


def evaluate(target: str = "theo_usd", alpha: float = 0.10):
    """Fit every model on Jan–Apr, score on May–Jun; conformal intervals from CV residuals."""
    df = daily_frame()
    cv, resid, ens = rolling_cv(df, target)
    tr, te = split_by_date(df)
    preds = {name: f(tr, te, target) for name, f in MODELS.items()}
    preds["Ensemble (top-3 by CV)"] = np.exp(np.mean([np.log(preds[m]) for m in ens], axis=0))
    resid["Ensemble (top-3 by CV)"] = np.mean([resid[m] for m in ens], axis=0)
    STACK["Ensemble (top-3 by CV)"] = "ensemble"
    cv["Ensemble (top-3 by CV)"] = np.nan
    b1_mae = np.mean(np.abs(preds["B1 weekday mean"] - te[target]))
    rows, out = [], te[["gaming_date", "weekday", "event", "holiday"]].copy()
    out["actual"] = te[target].to_numpy()
    for name, p in preds.items():
        q = np.quantile(np.abs(resid[name]), 1 - alpha)  # split-conformal half-width on log scale
        lo, hi = p * np.exp(-q), p * np.exp(q)
        s = score(te[target], p, lo, hi, ref_mae=b1_mae)
        rows.append({"target": target, "model": name, "stack": STACK[name], "cv_mae_janapr": cv.get(name, np.nan),
                     **s, "interval_halfwidth_pct": np.expm1(q)})
        out[name] = p
    mu, sd = m_bayes_ridge(tr, te, target, return_std=True)
    z = stats.norm.ppf(1 - alpha / 2)
    bayes_cov = np.mean((te[target] >= mu * np.exp(-z * sd)) & (te[target] <= mu * np.exp(z * sd)))
    res = pd.DataFrame(rows).sort_values("MAE")
    res.loc[res.model == "Bayesian ridge (log, trend)", "native_posterior_coverage"] = bayes_cov
    chosen = cv.drop([m for m in cv.index if STACK.get(m) == "baseline"]).dropna().idxmin()
    return res, out, chosen, ens


# ----------------------------------------------------------------------------- July yardstick
def july_counterfactual(model_name: str, target: str = "theo_usd", alpha: float = 0.10) -> pd.DataFrame:
    """Refit the CV-chosen model on Jan–Jun and forecast Jul 1–30: the 'no action' yardstick."""
    df = daily_frame(as_of=pd.Timestamp("2025-06-30"))
    jul = pd.DataFrame({"gaming_date": pd.date_range("2025-07-01", "2025-07-30")})
    jul["federal_holiday"] = jul.gaming_date.map(JULY_HOLIDAYS)
    jul = add_calendar(jul, pd.Timestamp("2025-06-30"))
    p = MODELS[model_name](df, jul, target)
    # interval from the model's May–Jun holdout errors (out-of-sample, 61 days)
    tr, te = split_by_date(daily_frame())
    r = np.log(te[target].to_numpy() / MODELS[model_name](tr, te, target))
    q = np.quantile(np.abs(r - r.mean()), 1 - alpha)
    jul["forecast"], jul["lo90"], jul["hi90"] = p, p * np.exp(-q), p * np.exp(q)
    # level anchor: June ran below the model; scale by the last 28 days' actual / in-sample fit
    last = df[df.gaming_date > df.gaming_date.max() - pd.Timedelta(days=28)]
    jul["level_adj"] = last[target].sum() / MODELS[model_name](df, last, target).sum()
    jul["forecast_level_adj"] = jul.forecast * jul.level_adj
    return jul[["gaming_date", "weekday", "holiday", "forecast", "lo90", "hi90", "level_adj", "forecast_level_adj"]]


def detectable_lift(model_name: str, target: str = "theo_usd", days: int = 30, share_of_floor: float = 1.0,
                    alpha: float = 0.05, power: float = 0.8) -> dict:
    """Minimum detectable effect for a July action measured as actual vs forecast (new).

    Uses the model's May–Jun log residuals: SD and lag-1 autocorrelation (effective n).
    An action touching `share_of_floor` of theo must move that slice by MDE / share to show up.
    """
    tr, te = split_by_date(daily_frame())
    r = np.log(te[target].to_numpy() / MODELS[model_name](tr, te, target))
    r = r - r.mean()  # assume the level bias is re-estimated on June before July
    rho = np.corrcoef(r[:-1], r[1:])[0, 1]
    n_eff = days * (1 - rho) / (1 + rho)
    mde = (stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)) * r.std(ddof=1) / np.sqrt(n_eff)
    return {"target": target, "model": model_name, "daily_resid_sd": r.std(ddof=1), "lag1_autocorr": rho,
            "n_eff": n_eff, "mde_property_pct": np.expm1(mde), "share_of_floor": share_of_floor,
            "mde_on_affected_slice_pct": np.expm1(mde) / share_of_floor}
