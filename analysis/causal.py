"""Phase 4a: what did the Mar 3 – Apr 6 closure of walkway W-ENT-B40 cost Back Forty?

The closure is a natural experiment in *access*: Back Forty's machines and games did not change,
only the walk from the main entrance. That makes it the cleanest evidence for "location" (and the
best prior for what wayfinding / signage could be worth).

Methods
1. Difference-in-differences on the daily gap d_t = log(B40 coin-in/hr) − mean log(control zone coin-in/hr),
   with weekday controls and Newey–West (HAC) errors; periods: pre / closed / reopened.
   Pre-trend check on the pre-period slope; weekly event-study coefficients.
2. Structural counterfactual (CausalImpact-style): local-level model of log B40 rate with the control
   zones as regressors, fitted on the pre-period, forecast through the closure with 90% intervals.
3. Placebo/permutation: run the same DiD with each control zone as the fake treated zone.
4. Measurement plan (new): minimum detectable lift for a 30-day zone action (e.g. A-WAYFINDING),
   from the residual SD and autocorrelation of d_t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.tsa.statespace.structural import UnobservedComponents

CLOSED = (pd.Timestamp("2025-03-03"), pd.Timestamp("2025-04-06"))
TREATED = "Z-B40"


def zone_day(v: pd.DataFrame) -> pd.DataFrame:
    g = v.groupby(["gaming_date", "zone_id"]).agg(ci=("coin_in_usd", "sum"), hrs=("available_hours", "sum"),
                                                  theo=("theo_usd", "sum")).reset_index()
    g["log_rate"] = np.log(g.ci / g.hrs)
    return g


def _gap(zd: pd.DataFrame, treated: str, controls: list[str]) -> pd.DataFrame:
    w = zd.pivot(index="gaming_date", columns="zone_id", values="log_rate")
    d = pd.DataFrame({"gap": w[treated] - w[controls].mean(axis=1)})
    d["dow"] = d.index.dayofweek
    d["closed"] = ((d.index >= CLOSED[0]) & (d.index <= CLOSED[1])).astype(float)
    d["reopened"] = (d.index > CLOSED[1]).astype(float)
    d["t"] = np.arange(len(d), dtype=float)
    return d


def did(zd: pd.DataFrame, treated: str = TREATED, controls: list[str] | None = None) -> dict:
    controls = controls or [z for z in zd.zone_id.unique() if z not in (treated, "Z-HL")]
    d = _gap(zd, treated, controls)
    r = smf.ols("gap ~ closed + reopened + C(dow)", d).fit(cov_type="HAC", cov_kwds={"maxlags": 7})
    pre = d[d.index < CLOSED[0]]
    pt = smf.ols("gap ~ t + C(dow)", pre).fit(cov_type="HAC", cov_kwds={"maxlags": 7})
    ci = r.conf_int(alpha=0.10)
    return {"treated": treated, "effect_closed_log": r.params["closed"], "effect_closed_pct": np.expm1(r.params["closed"]),
            "closed_lo90_pct": np.expm1(ci.loc["closed", 0]), "closed_hi90_pct": np.expm1(ci.loc["closed", 1]),
            "p_closed": r.pvalues["closed"], "effect_reopened_pct": np.expm1(r.params["reopened"]),
            "p_reopened": r.pvalues["reopened"], "pretrend_slope_per_30d_pct": np.expm1(30 * pt.params["t"]),
            "pretrend_p": pt.pvalues["t"], "resid": r.resid, "controls": controls}


def event_study(zd: pd.DataFrame, controls: list[str]) -> pd.DataFrame:
    """Weekly mean gap relative to the pre-period mean (weekday-adjusted), with HAC 90% CIs."""
    d = _gap(zd, TREATED, controls)
    d["rel_week"] = ((d.index - CLOSED[0]).days // 7).astype(int)
    d["wk"] = d.rel_week.clip(lower=-9).astype(str)
    r = smf.ols("gap ~ C(wk, Treatment(reference='-9')) + C(dow)", d).fit(cov_type="HAC", cov_kwds={"maxlags": 7})
    ci = r.conf_int(alpha=0.10)
    rows = []
    for k in r.params.index:
        if k.startswith("C(wk"):
            w = int(k.split("[T.")[1][:-1])
            rows.append({"rel_week": w, "effect_pct": np.expm1(r.params[k]),
                         "lo90_pct": np.expm1(ci.loc[k, 0]), "hi90_pct": np.expm1(ci.loc[k, 1])})
    return pd.DataFrame(rows).sort_values("rel_week")


def structural_counterfactual(zd: pd.DataFrame, controls: list[str]) -> tuple[dict, pd.DataFrame]:
    w = zd.pivot(index="gaming_date", columns="zone_id", values="log_rate")
    th = zd.pivot(index="gaming_date", columns="zone_id", values="theo")
    pre, during = w[w.index < CLOSED[0]], w[(w.index >= CLOSED[0]) & (w.index <= CLOSED[1])]
    X = lambda df: pd.concat([df[controls], pd.get_dummies(df.index.dayofweek, prefix="d", drop_first=True)
                              .set_index(df.index).astype(float)], axis=1)
    r = UnobservedComponents(pre[TREATED].to_numpy(), level="local level", exog=X(pre)).fit(disp=False)
    n = len(during)
    f = r.get_forecast(n, exog=X(during))
    mu, ci = np.asarray(f.predicted_mean), np.asarray(f.conf_int(alpha=0.10))
    out = pd.DataFrame({"actual_log": during[TREATED].to_numpy(), "cf_log": mu, "cf_lo": ci[:, 0], "cf_hi": ci[:, 1]},
                       index=during.index)
    out["effect_pct"] = np.expm1(out.actual_log - out.cf_log)
    theo = th.loc[during.index, TREATED].to_numpy()
    # interval for the *average* effect: simulate whole counterfactual paths (errors are correlated
    # across the horizon under a local level, so a per-day interval / sqrt(n) would be too narrow)
    sims = np.asarray(r.simulate(n, repetitions=2000, anchor="end", exog=X(during), random_state=0)).reshape(n, -1)
    avg_sims = (out.actual_log.to_numpy()[:, None] - sims).mean(axis=0)
    lost_sims = (theo[:, None] * (np.exp(sims - out.actual_log.to_numpy()[:, None]) - 1)).sum(axis=0)
    avg = (out.actual_log - out.cf_log).mean()
    summ = {"avg_effect_pct": np.expm1(avg), "avg_effect_lo90_pct": np.expm1(np.quantile(avg_sims, 0.05)),
            "avg_effect_hi90_pct": np.expm1(np.quantile(avg_sims, 0.95)),
            "lost_theo_usd_during_closure": float((theo * (np.exp(out.cf_log - out.actual_log) - 1)).sum()),
            "lost_theo_lo90": float(np.quantile(lost_sims, 0.05)), "lost_theo_hi90": float(np.quantile(lost_sims, 0.95)),
            "days": n}
    return summ, out.reset_index()


def placebo(zd: pd.DataFrame) -> pd.DataFrame:
    zones = [z for z in zd.zone_id.unique() if z != "Z-HL"]
    rows = []
    for z in zones:
        res = did(zd, z, [c for c in zones if c not in (z, TREATED)])
        rows.append({k: res[k] for k in ["treated", "effect_closed_pct", "p_closed", "pretrend_p"]})
    return pd.DataFrame(rows).sort_values("effect_closed_pct")


def zone_action_mde(resid: pd.Series, days: int = 30, alpha: float = 0.05, power: float = 0.8) -> dict:
    """Detectable lift in the B40-vs-controls gap from a 30-day zone action (e.g. wayfinding)."""
    e = resid.to_numpy()
    rho = np.corrcoef(e[:-1], e[1:])[0, 1]
    n_eff = days * (1 - rho) / (1 + rho)
    mde = (stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)) * e.std(ddof=1) * np.sqrt(1 / n_eff + 1 / len(e))
    return {"gap_resid_sd": e.std(ddof=1), "lag1_autocorr": rho, "n_eff_30d": n_eff, "mde_pct": np.expm1(mde)}


def run(v: pd.DataFrame):
    zd = zone_day(v)
    main = did(zd)
    es = event_study(zd, main["controls"])
    sc, sc_daily = structural_counterfactual(zd, main["controls"])
    pl = placebo(zd)
    mde = zone_action_mde(main["resid"])
    b40_theo_day = zd[(zd.zone_id == TREATED) & (zd.gaming_date > CLOSED[1])].theo.mean()
    return {"did": {k: v for k, v in main.items() if k not in ("resid",)}, "event_study": es,
            "structural": sc, "structural_daily": sc_daily, "placebo": pl, "mde": mde,
            "b40_theo_per_day_after": b40_theo_day}
