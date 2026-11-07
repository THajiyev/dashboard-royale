"""Phase 3: location-adjusted machine model — is a machine bad, or is its spot (or its game) bad?

Target: coin-in per available hour on a machine-day (demand), modelled with a log link and an
offset of log(available hours), so ratios come from sums and downtime is not counted as zero demand.
Decomposition (Lucas & Dunn "performance potential"):
    E[coin-in] = hours × exp(location (bank) + game (theme) + calendar + closure) × machine effect
A machine effect is what is left after location and game: the only part a machine swap would fix
*if the replacement plays the same game*; the game term says what a different title would add.

Three stacks, all fit on Jan–Apr only:
1. Lightweight: quasi-Poisson GLM with bank + theme fixed effects; machine effect = log(Σactual/Σpred),
   empirical-Bayes shrunk (James–Stein style) with a 90% interval and P(effect < 0).
2. ML: LightGBM (Poisson, offset) on location / game / calendar features without machine identity
   (slot coordinates excluded, since they would identify the machine); SHAP via pred_contrib.
3. Partial pooling: linear mixed model on machine-week log rates with a random machine intercept.
Validation: machine effects must persist into May–Jun (Spearman), and May–Jun coin-in/hr predictions
are scored against the Phase 0 baselines Z0 (zone rate) and M0 (machine's own rate).
"""
from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

from baselines import known_event_days
from common import load, score, split_by_date

CLOSURE = (pd.Timestamp("2025-03-03"), pd.Timestamp("2025-04-06"))  # W-ENT-B40 closed, gaming dates
LOC_COLS = ["zone_id", "bank_id", "bank_dist_entrance_m"]
GAME_COLS = ["theme", "volatility_class", "edge", "min_bet_usd", "manufacturer"]
CAL_COLS = ["dow", "event", "holiday", "b40_closed"]


# ----------------------------------------------------------------------------- data
def machine_day_frame(v: pd.DataFrame) -> pd.DataFrame:
    """Active machine-days with location, game and calendar features known on the day."""
    v = v[v.available_hours > 0].copy()
    fl = load("2_machine_decision/floor_locations.parquet")
    banks = fl[fl.node_type == "bank"].set_index("bank_id")[["x_m", "y_m"]]
    ent = fl[fl.node_type == "entrance"][["x_m", "y_m"]].to_numpy()
    d = np.sqrt(((banks.to_numpy()[:, None, :] - ent[None, :, :]) ** 2).sum(-1)).min(1)
    v["bank_dist_entrance_m"] = v.bank_id.map(pd.Series(d, index=banks.index))
    gm = load("2_machine_decision/game_math.parquet").set_index("config_id")
    v["edge"] = 1 - v.configured_rtp.astype(float)
    v["min_bet_usd"] = v.config_id.map(gm.min_bet_cents).astype(float) / 100
    v["dow"] = v.gaming_date.dt.dayofweek
    v["event"] = known_event_days(v.gaming_date).astype(float)
    v["holiday"] = v.federal_holiday.notna().astype(float)
    v["b40_closed"] = ((v.zone_id == "Z-B40") & v.gaming_date.between(*CLOSURE)).astype(float)
    v["log_hours"] = np.log(v.available_hours)
    return v


# ----------------------------------------------------------------------------- 1. GLM + empirical Bayes
GLM_FORMULA = "coin_in_usd ~ C(bank_id) + C(theme) + C(dow) + event + holiday + b40_closed"


def fit_glm(train: pd.DataFrame):
    return smf.glm(GLM_FORMULA, data=train, family=sm.families.Poisson(), offset=train.log_hours).fit(scale="X2")


def machine_effects(df: pd.DataFrame, pred: np.ndarray) -> pd.DataFrame:
    """Raw log(Σactual/Σpred) per machine with a ratio-estimator standard error."""
    t = df.assign(pred=pred, r=df.coin_in_usd / pred)
    g = t.groupby("machine_id").agg(actual=("coin_in_usd", "sum"), pred=("pred", "sum"), n=("r", "size"),
                                    r_mean=("r", "mean"), r_sd=("r", "std"))
    g["raw"] = np.log(g.actual / g.pred)
    g["se"] = g.r_sd / (np.sqrt(g.n) * g.r_mean)
    return g[["actual", "pred", "n", "raw", "se"]]


def empirical_bayes(g: pd.DataFrame, level: float = 0.90) -> pd.DataFrame:
    """Normal–normal shrinkage toward the precision-weighted mean (method-of-moments τ²)."""
    g = g.copy()
    mu = np.average(g.raw, weights=1 / g.se ** 2)
    tau2 = max(0.0, np.var(g.raw, ddof=1) - np.mean(g.se ** 2))
    g["shrink_w"] = tau2 / (tau2 + g.se ** 2)
    g["effect"] = mu + g.shrink_w * (g.raw - mu)
    g["effect_sd"] = np.sqrt(g.shrink_w) * g.se
    z = stats.norm.ppf(0.5 + level / 2)
    g["effect_lo"], g["effect_hi"] = g.effect - z * g.effect_sd, g.effect + z * g.effect_sd
    g["p_effect_below_0"] = stats.norm.cdf(-g.effect / g.effect_sd)
    g.attrs["tau"], g.attrs["mu"] = np.sqrt(tau2), mu
    return g


# ----------------------------------------------------------------------------- 2. LightGBM + SHAP
def _lgb_X(df):
    X = df[LOC_COLS + GAME_COLS + CAL_COLS].copy()
    for c in ["zone_id", "bank_id", "theme", "volatility_class", "manufacturer"]:
        X[c] = X[c].astype("category")
    return X


def fit_lgbm(train: pd.DataFrame):
    X = _lgb_X(train)
    m = lgb.LGBMRegressor(objective="poisson", n_estimators=400, learning_rate=0.05, num_leaves=31,
                          min_child_samples=300, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                          random_state=42, verbose=-1)
    m.fit(X, train.coin_in_usd, init_score=train.log_hours.to_numpy())
    cats = {c: X[c].cat.categories for c in X.select_dtypes("category")}
    return m, cats


def predict_lgbm(model, cats, df):
    X = _lgb_X(df)
    for c, levels in cats.items():
        X[c] = pd.Categorical(X[c], categories=levels)
    return np.exp(model.predict(X, raw_score=True) + df.log_hours.to_numpy()), X


def shap_shares(model, cats, df) -> pd.Series:
    """Share of mean |SHAP| (log scale) by driver group: location vs game vs calendar."""
    _, X = predict_lgbm(model, cats, df)
    contrib = pd.DataFrame(model.predict(X, pred_contrib=True)[:, :-1], columns=X.columns)
    a = contrib.abs().mean()
    groups = {"location": LOC_COLS, "game": GAME_COLS, "calendar": ["dow", "event", "holiday"], "B40 closure": ["b40_closed"]}
    s = pd.Series({k: a[c].sum() for k, c in groups.items()})
    return (s / s.sum()).rename("share_of_mean_abs_shap")


# ----------------------------------------------------------------------------- 3. mixed model
def fit_mixed(train: pd.DataFrame) -> pd.DataFrame:
    """Random machine intercept on machine-week log(coin-in / hour); BLUPs with conditional SD."""
    w = train.assign(week=train.gaming_date.dt.isocalendar().week.astype(int))
    w = w.groupby(["machine_id", "week", "zone_id", "theme"], as_index=False).agg(
        ci=("coin_in_usd", "sum"), hrs=("available_hours", "sum"), closed=("b40_closed", "mean"))
    w["y"] = np.log(w.ci / w.hrs)
    r = smf.mixedlm("y ~ C(zone_id) + C(theme) + C(week) + closed", w, groups=w.machine_id).fit(reml=True)
    re = pd.Series({k: v.iloc[0] for k, v in r.random_effects.items()}, name="mixed_effect")
    # conditional SD of each BLUP: sqrt(σ_u² σ_e² / (n σ_u² + σ_e²))
    su2, se2 = float(r.cov_re.iloc[0, 0]), r.scale
    n = w.groupby("machine_id").size()
    sd = np.sqrt(su2 * se2 / (n * su2 + se2)).rename("mixed_sd")
    out = pd.concat([re, sd], axis=1)
    out["mixed_p_below_0"] = stats.norm.cdf(-out.mixed_effect / out.mixed_sd)
    out.attrs["sigma_machine"], out.attrs["sigma_week"] = np.sqrt(su2), np.sqrt(se2)
    return out


# ----------------------------------------------------------------------------- swap simulator (new)
def swap_simulator(glm, df: pd.DataFrame, machines: list[str], replace_cost_30d: float) -> pd.DataFrame:
    """Expected theo/hr if a machine kept its slot but ran a different title (GLM theme effects).

    Uses the GLM's bank (location) term at the machine's current bank and swaps only the theme;
    theo = coin-in × edge of the new title. Interval from the theme-coefficient covariance.
    Themes only ever placed in one zone (Platinum Reels: high-limit only) are excluded as extrapolation.
    """
    cfg = df.drop_duplicates("theme").set_index("theme")[["edge"]]
    multi_zone = df.groupby("theme").zone_id.nunique()
    themes = [t for t in cfg.index if multi_zone[t] > 1]
    p, cov = glm.params, glm.cov_params()
    def coef(t):
        k = f"C(theme)[T.{t}]"
        return (p.get(k, 0.0), k if k in p.index else None)
    rows = []
    for m in machines:
        cur = df[df.machine_id == m].sort_values("gaming_date").iloc[-1]
        hrs_day = df[df.machine_id == m].available_hours.mean()
        b0, k0 = coef(cur.theme)
        base_theo_hr = df[df.machine_id == m].theo_usd.sum() / df[df.machine_id == m].available_hours.sum()
        # model's location+calendar-average rate for the current theme at this bank
        sub = df[df.machine_id == m]
        cur_ci_hr = glm.predict(sub, offset=sub.log_hours).sum() / sub.available_hours.sum()
        for t in themes:
            if t == cur.theme:
                continue
            b1, k1 = coef(t)
            d = b1 - b0
            var = sum(cov.loc[a, b] * sa * sb for a, sa in [(k1, 1), (k0, -1)] if a for b, sb in [(k1, 1), (k0, -1)] if b)
            ci_hr = cur_ci_hr * np.exp(d)
            theo_hr = ci_hr * cfg.edge[t]
            exp_cur_theo_hr = cur_ci_hr * cur.edge
            gain_day = (theo_hr - exp_cur_theo_hr) * hrs_day
            rows.append({"machine_id": m, "zone_id": cur.zone_id, "current_theme": cur.theme, "swap_to": t,
                         "actual_theo_per_hr": base_theo_hr, "model_theo_per_hr_now": exp_cur_theo_hr,
                         "model_theo_per_hr_swapped": theo_hr,
                         "theo_gain_per_day": gain_day,
                         "theo_gain_per_day_lo90": (cur_ci_hr * np.exp(d - 1.645 * np.sqrt(var)) * cfg.edge[t] - exp_cur_theo_hr) * hrs_day,
                         "theo_gain_per_day_hi90": (cur_ci_hr * np.exp(d + 1.645 * np.sqrt(var)) * cfg.edge[t] - exp_cur_theo_hr) * hrs_day,
                         "net_30d_after_lease": gain_day * 30 - replace_cost_30d})
    return pd.DataFrame(rows).sort_values(["machine_id", "theo_gain_per_day"], ascending=[True, False])


# ----------------------------------------------------------------------------- run
def run(v: pd.DataFrame, bottom10: list[str]):
    df = machine_day_frame(v)
    train, test = split_by_date(df)

    glm = fit_glm(train)
    eb = empirical_bayes(machine_effects(train, glm.predict(train, offset=train.log_hours)))
    lgbm, cats = fit_lgbm(train)
    lgb_tr, _ = predict_lgbm(lgbm, cats, train)
    eb_l = empirical_bayes(machine_effects(train, lgb_tr))
    mixed = fit_mixed(train)

    # --- validation on May–Jun
    glm_te = glm.predict(test, offset=test.log_hours).to_numpy()
    lgb_te, _ = predict_lgbm(lgbm, cats, test)
    held = machine_effects(test, glm_te)  # out-of-sample machine effects (GLM fitted on Jan–Apr)
    held_l = machine_effects(test, lgb_te)
    both = eb.join(held.raw.rename("raw_mayjun"), how="inner")
    both_l = eb_l.join(held_l.raw.rename("raw_mayjun"), how="inner")
    persistence = {
        "GLM+EB": stats.spearmanr(both.effect, both.raw_mayjun).correlation,
        "LightGBM+EB": stats.spearmanr(both_l.effect, both_l.raw_mayjun).correlation,
        "Mixed model": stats.spearmanr(mixed.mixed_effect.reindex(both.index), both.raw_mayjun).correlation,
    }
    hrs, y = test.available_hours.to_numpy(), (test.coin_in_usd / test.available_hours).to_numpy()
    mult_glm = test.machine_id.map(np.exp(eb.effect)).fillna(1.0).to_numpy()
    mult_lgb = test.machine_id.map(np.exp(eb_l.effect)).fillna(1.0).to_numpy()
    preds = {"GLM location+game (no machine effect)": glm_te / hrs,
             "GLM + shrunk machine effect": glm_te * mult_glm / hrs,
             "LightGBM location+game (no machine effect)": lgb_te / hrs,
             "LightGBM + shrunk machine effect": lgb_te * mult_lgb / hrs}
    scores = pd.DataFrame([{"target": "Machine-day coin-in per available hour", "model": k, **score(y, p)}
                           for k, p in preds.items()])
    scores.loc[:, "persistence_spearman"] = scores.model.map({
        "GLM + shrunk machine effect": persistence["GLM+EB"], "LightGBM + shrunk machine effect": persistence["LightGBM+EB"]})

    # --- per-machine table (Jan–Jun descriptive context + Jan–Apr effects)
    first = df.sort_values("gaming_date").groupby("machine_id").last()[["zone_id", "zone_name", "bank_id", "theme", "manufacturer"]]
    tab = first.join(eb[["raw", "se", "shrink_w", "effect", "effect_lo", "effect_hi", "p_effect_below_0"]])
    tab = tab.join(eb_l[["effect", "p_effect_below_0"]].add_prefix("lgbm_")).join(mixed).join(held.raw.rename("raw_effect_mayjun"))
    tab["effect_pct"] = np.expm1(tab.effect)
    tab["credibly_negative"] = tab.effect_hi < 0
    bank_fx = pd.Series({k.split("[T.")[1][:-1]: v for k, v in glm.params.items() if k.startswith("C(bank_id)")})
    theme_fx = pd.Series({k.split("[T.")[1][:-1]: v for k, v in glm.params.items() if k.startswith("C(theme)")})
    tab["bank_effect_log"] = tab.bank_id.map(bank_fx).fillna(0.0)
    tab["theme_effect_log"] = tab.theme.map(theme_fx).fillna(0.0)

    lease = load("2_machine_decision/action_catalog.parquet").set_index("action_type_id").loc["A-REPLACE-LEASE"]
    lease_30d = (lease.unit_cost_cents + 30 * lease.recurring_cost_cents_per_day) / 100
    swaps = swap_simulator(glm, df, bottom10, lease_30d)

    info = {"tau_machine_glm": eb.attrs["tau"], "tau_machine_lgbm": eb_l.attrs["tau"],
            "sigma_machine_mixed": mixed.attrs["sigma_machine"], "persistence": persistence,
            "shap_shares": shap_shares(lgbm, cats, test.sample(min(20000, len(test)), random_state=0)),
            "lease_cost_30d": lease_30d, "glm_deviance_ratio": glm.deviance / glm.null_deviance,
            "theme_effects": theme_fx.sort_values(), "n_credibly_negative": int(tab.credibly_negative.sum())}
    return tab.reset_index(), scores, swaps, info
