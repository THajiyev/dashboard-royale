"""Export the weekly-pattern and correlation results for the static site (docs/data/weekly.js, docs/data/corr.js).

    python scripts/build_site_patterns.py

Descriptive statistics on Jan 1 - Jun 30 2025. Nothing is fitted for forecasting here, so using all six months is
fine. "Ordinary days" are days with no event from the events table (the same definition the forecast pages use).
"""
from __future__ import annotations

import sys
from math import comb
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import signal, stats
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.stats.multicomp import pairwise_tukeyhsd
from statsmodels.stats.multitest import multipletests

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "analysis"), str(ROOT / "analysis" / "experiments"),
                str(ROOT / "analysis" / "experiments" / "iter5"), str(ROOT / "scripts")]
from common import active_machine_days, load  # noqa: E402
from ds_alpha.models import _EV  # noqa: E402
from segments import segment_day  # noqa: E402
from build_site_data import MONTHS, dump, r  # noqa: E402

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CLOSURE = (pd.Timestamp("2025-03-03"), pd.Timestamp("2025-04-06"))
SPLIT = pd.Timestamp("2025-05-01")


def event_map():
    m = {}
    for e in _EV.itertuples():
        for d in pd.date_range(e.start_date, e.end_date):
            m[d] = e.event_id
    return m


EV = event_map()
EV_NAME = {"EV-CES25": "CES", "EV-SB59": "Super Bowl", "EV-MM25": "March Madness", "EV-CC25": "CinemaCon",
           "EV-NAB25": "NAB Show", "EV-EDC25": "EDC", "EV-P-TOURN": "Slot tournament", "EV-P-LOCALS": "Locals Week"}


def pfmt(p):
    return None if p is None or not np.isfinite(p) else float(f"{p:.3g}")


# ============================================================================= weekly
def fisher_g(I):
    """Fisher's exact test for the largest periodogram ordinate (white-noise null)."""
    m = len(I); g = I.max() / I.sum()
    p = sum((-1) ** (k - 1) * comb(m, k) * (1 - k * g) ** (m - 1) for k in range(1, int(1 / g) + 1))
    return float(g), float(min(max(p, 0.0), 1.0))


def weekly():
    p = load("1_prepared_views/property_day.parquet")
    p["d"] = pd.to_datetime(p.gaming_date)
    p = p.set_index("d").sort_index()
    seg = segment_day()
    df = pd.DataFrame({"theo": p.theo_usd.astype(float)}).join(seg[["locals", "nonlocals"]])
    df["dow"] = df.index.dayofweek
    df["month"] = df.index.month
    df["ev"] = [EV.get(d) for d in df.index]
    df["clo"] = (df.index >= CLOSURE[0]) & (df.index <= CLOSURE[1])
    df["half"] = np.where(df.index < SPLIT, "JanApr", "MayJun")
    df["lth"] = np.log(df.theo)
    od = df[df.ev.isna()].copy()  # ordinary days

    # ---- how much of day-to-day variation is the weekday? (ordinary days, log theo)
    m_dow = smf.ols("lth ~ C(dow)", od).fit()
    m_mon = smf.ols("lth ~ C(month)", od).fit()
    m_both = smf.ols("lth ~ C(dow) + C(month)", od).fit()
    kw = stats.kruskal(*[g.lth for _, g in od.groupby("dow")])
    partial = (m_mon.ssr - m_both.ssr) / m_mon.ssr  # share of what's left after month that weekday explains
    anova = {"F": r(m_dow.fvalue, 1), "p": pfmt(m_dow.f_pvalue), "df1": int(m_dow.df_model), "df2": int(m_dow.df_resid),
             "R2": r(m_dow.rsquared, 3), "R2_month": r(m_mon.rsquared, 3), "partialR2": r(partial, 3),
             "kw_H": r(kw[0], 1), "kw_p": pfmt(kw[1]), "n": len(od)}

    # ---- is the shape the same in Jan-Apr and May-Jun? (interaction F-test, month level absorbed)
    full = smf.ols("lth ~ C(dow)*C(half) + C(month)", od).fit()
    red = smf.ols("lth ~ C(dow) + C(half) + C(month)", od).fit()
    ft = full.compare_f_test(red)
    stable = {"F": r(ft[0], 2), "p": pfmt(ft[1]), "df": int(ft[2])}

    # ---- weekday table: level-adjusted index (day / its month's ordinary-day mean), by half
    od["idx"] = od.theo / od.groupby("month").theo.transform("mean")
    wd = []
    raw_p = []
    for k in range(7):
        g = od[od.dow == k]
        a, b = g[g.half == "JanApr"].idx, g[g.half == "MayJun"].idx
        t = stats.ttest_ind(np.log(a), np.log(b), equal_var=False)
        raw_p.append(t.pvalue)
        ci = stats.t.interval(0.95, len(g) - 1, loc=g.theo.mean(), scale=stats.sem(g.theo))
        wd.append({"dow": DAYS[k], "n": len(g), "mean": r(g.theo.mean(), 0), "lo": r(ci[0], 0), "hi": r(ci[1], 0),
                   "sd": r(g.theo.std(), 0), "idx": r(g.idx.mean(), 4),
                   "idxA": r(a.mean(), 4), "idxA_lo": r(a.mean() - 1.96 * stats.sem(a), 4), "idxA_hi": r(a.mean() + 1.96 * stats.sem(a), 4),
                   "idxB": r(b.mean(), 4), "idxB_lo": r(b.mean() - 1.96 * stats.sem(b), 4), "idxB_hi": r(b.mean() + 1.96 * stats.sem(b), 4),
                   "nA": len(a), "nB": len(b), "p": pfmt(t.pvalue)})
    q = multipletests(raw_p, method="fdr_bh")[1]
    for w, qq in zip(wd, q):
        w["q"] = pfmt(qq)

    # ---- pairwise weekdays (Tukey HSD on level-adjusted log theo)
    od["la"] = od.lth - od.groupby("month").lth.transform("mean")
    th = pairwise_tukeyhsd(od.la, od.dow.map(dict(enumerate(DAYS))))
    # unrounded p-values (the printed summary rounds them); statsmodels floors Tukey p at 0.001
    gu = list(th.groupsunique)
    P = np.full((7, 7), np.nan); Dm = np.full((7, 7), np.nan)
    for a, b, md, pv in zip(*th._multicomp.pairindices, th.meandiffs, th.pvalues):
        i, j = DAYS.index(gu[a]), DAYS.index(gu[b])
        P[i, j] = P[j, i] = float(pv)
        Dm[j, i] = np.expm1(float(md)); Dm[i, j] = np.expm1(-float(md))  # Dm[a,b] = day a vs day b
    tukey = {"vars": DAYS, "p": [[pfmt(v) for v in row] for row in P], "diff": [[r(v, 4) for v in row] for row in Dm],
             "n_sig": int(np.nansum(P < 0.05) // 2), "n_pairs": 21}

    # ---- autocorrelation (all days, log theo) before and after removing the weekday means
    x = df.lth - df.lth.mean()
    resid = df.lth - df.groupby("dow").lth.transform("mean")
    lags = 28
    acf_raw = sm.tsa.acf(x, nlags=lags, fft=False)
    acf_res = sm.tsa.acf(resid - resid.mean(), nlags=lags, fft=False)
    lb_raw = acorr_ljungbox(x, lags=[7, 14], return_df=True)
    lb_res = acorr_ljungbox(resid, lags=[7, 14], return_df=True)
    acf = {"band": r(1.96 / np.sqrt(len(df)), 4), "n": len(df),
           "raw": [r(v, 4) for v in acf_raw[1:]], "resid": [r(v, 4) for v in acf_res[1:]],
           "lb": {"raw7": pfmt(lb_raw.lb_pvalue.iloc[0]), "raw14": pfmt(lb_raw.lb_pvalue.iloc[1]),
                  "Q7": r(lb_raw.lb_stat.iloc[0], 1), "res7": pfmt(lb_res.lb_pvalue.iloc[0]),
                  "res14": pfmt(lb_res.lb_pvalue.iloc[1]), "Qres7": r(lb_res.lb_stat.iloc[0], 1)}}
    # weekly lag of the weekday-removed series: is there a leftover weekly echo?
    wk_lags = [6, 13, 20, 27]
    acf["weekly_raw"] = [r(acf_raw[k + 1], 3) for k in wk_lags]
    acf["weekly_res"] = [r(acf_res[k + 1], 3) for k in wk_lags]

    # ---- periodogram (linear trend removed)
    f, I = signal.periodogram(signal.detrend(df.lth.to_numpy()), fs=1.0, detrend=False, scaling="spectrum")
    f, I = f[1:], I[1:]
    g, gp = fisher_g(I)
    top = np.argsort(-I)[:3]
    spec = {"f": [r(v, 5) for v in f], "I": [r(v, 7) for v in I], "fisher_g": r(g, 3), "fisher_p": pfmt(gp),
            "share7": r(I[np.argmin(np.abs(f - 1 / 7))] / I.sum(), 3),
            "share_weekly": r(sum(I[np.argmin(np.abs(f - h / 7))] for h in (1, 2, 3)) / I.sum(), 3),
            "top": [{"period": r(1 / f[i], 2), "share": r(I[i] / I.sum(), 3)} for i in top]}

    # ---- every week (Mon-Sun, complete) and its profile
    days = [{"d": d.strftime("%Y-%m-%d"), "dow": int(rw.dow), "theo": r(rw.theo, 0),
             "ev": EV_NAME.get(rw.ev) if rw.ev else None, "clo": bool(rw.clo)} for d, rw in df.iterrows()]
    df["wk"] = (df.index - pd.to_timedelta(df.dow.to_numpy(), unit="D")).strftime("%Y-%m-%d")
    avg = od.groupby("dow").idx.mean().to_numpy()
    weeks = []
    for wk, g in df.groupby("wk"):
        if len(g) < 7:
            continue
        v = g.theo.to_numpy(); prof = v / v.mean()
        weeks.append({"wk": wk, "total": r(v.sum(), 0), "prof": [r(x, 4) for x in prof],
                      "ev": sorted({EV_NAME[e] for e in g.ev.dropna()}), "clo": bool(g.clo.any()),
                      "r": r(np.corrcoef(prof, avg)[0, 1], 3)})
    rs = np.array([w["r"] for w in weeks]); rs_ord = np.array([w["r"] for w in weeks if not w["ev"]])

    # ---- week totals: trend within each half, ordinary weeks only (HAC, 2 lags)
    wt = pd.DataFrame([{"wk": pd.Timestamp(w["wk"]), "tot": w["total"], "ev": bool(w["ev"])} for w in weeks])
    trend = {}
    for name, lo, hi in [("JanApr", "2025-01-01", "2025-04-30"), ("MayJun", "2025-04-28", "2025-06-30"), ("all", "2025-01-01", "2025-06-30")]:
        s = wt[(wt.wk >= lo) & (wt.wk <= hi) & ~wt.ev].copy()
        s["t"] = np.arange(len(s)); s["t"] = (s.wk - s.wk.min()).dt.days / 7
        fit = sm.OLS(np.log(s.tot), sm.add_constant(s.t)).fit(cov_type="HAC", cov_kwds={"maxlags": 2})
        kt = stats.kendalltau(s.t, s.tot)
        trend[name] = {"slope": r(np.expm1(fit.params.iloc[1]), 5), "lo": r(np.expm1(fit.conf_int().iloc[1, 0]), 5),
                       "hi": r(np.expm1(fit.conf_int().iloc[1, 1]), 5), "p": pfmt(fit.pvalues.iloc[1]),
                       "kendall_tau": r(kt[0], 3), "kendall_p": pfmt(kt[1]), "n": len(s),
                       "a": r(fit.params.iloc[0], 6), "b": r(fit.params.iloc[1], 6), "start": s.wk.min().strftime("%Y-%m-%d"),
                       "end": s.wk.max().strftime("%Y-%m-%d")}

    # ---- monthly profiles and their correlation (does the shape repeat month to month?)
    mp = od.groupby(["month", "dow"]).idx.mean().unstack()
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    R = np.corrcoef(mp.to_numpy())
    Pm = np.ones_like(R)
    for i in range(6):
        for j in range(6):
            if i != j:
                Pm[i, j] = stats.pearsonr(mp.iloc[i], mp.iloc[j])[1]
    mprof = {"vars": months, "r": [[r(v, 3) for v in row] for row in R], "p": [[pfmt(v) for v in row] for row in Pm],
             "n": 7, "prof": [[r(v, 4) for v in row] for row in mp.to_numpy()]}

    # ---- locals vs visitors: does each group repeat the same week?
    seg_out = {}
    long = []
    for col, lab in [("locals", "Locals"), ("nonlocals", "Visitors and uncarded")]:
        s = od[[col, "dow", "month"]].rename(columns={col: "v"}).copy()
        s["idx"] = s.v / s.groupby("month").v.transform("mean")
        s["lv"] = np.log(s.v); s["seg"] = col
        long.append(s)
        prof = s.groupby("dow").idx.agg(["mean", "sem"])
        mfit = smf.ols("lv ~ C(dow) + C(month)", s).fit()
        mm = smf.ols("lv ~ C(month)", s).fit()
        wkend = s[s.dow.isin([4, 5])].idx.mean() / s[s.dow.isin([0, 1, 2, 3])].idx.mean() - 1
        seg_out[col] = {"label": lab, "idx": [r(v, 4) for v in prof["mean"]],
                        "lo": [r(m - 1.96 * e, 4) for m, e in prof.to_numpy()], "hi": [r(m + 1.96 * e, 4) for m, e in prof.to_numpy()],
                        "partialR2": r((mm.ssr - mfit.ssr) / mm.ssr, 3), "weekend_uplift": r(wkend, 3),
                        "share": r(od[col].sum() / od.theo.sum(), 3)}
    L = pd.concat(long)
    f1 = smf.ols("lv ~ C(seg)*C(dow) + C(seg):C(month)", L).fit()
    f0 = smf.ols("lv ~ C(seg) + C(dow) + C(seg):C(month)", L).fit()
    sf = f1.compare_f_test(f0)
    seg_out["test"] = {"F": r(sf[0], 1), "p": pfmt(sf[1]), "df": int(sf[2])}

    dump("weekly", {"days": days, "weeks": weeks, "anova": anova, "stable": stable, "weekday": wd, "tukey": tukey,
                    "acf": acf, "spec": spec, "trend": trend, "monthProfiles": mprof, "segments": seg_out,
                    "weekCorr": {"median": r(np.median(rs), 3), "median_ord": r(np.median(rs_ord), 3),
                                 "share90": r(np.mean(rs >= 0.9), 3), "min": r(rs.min(), 3), "n": len(rs),
                                 "n_ord": len(rs_ord)}})
    return anova, stable, acf, spec, trend, mprof, seg_out


# ============================================================================= correlations
def corr_block(X: pd.DataFrame, method="pearson"):
    cols = list(X.columns); k = len(cols)
    R = np.eye(k); P = np.zeros((k, k)); N = np.zeros((k, k), int)
    f = stats.pearsonr if method == "pearson" else stats.spearmanr
    for i in range(k):
        for j in range(i + 1, k):
            s = X[[cols[i], cols[j]]].dropna()
            if len(s) < 8 or s.iloc[:, 0].std() == 0 or s.iloc[:, 1].std() == 0:
                rv, pv = np.nan, np.nan
            else:
                res = f(s.iloc[:, 0], s.iloc[:, 1]); rv, pv = float(res[0]), float(res[1])
            R[i, j] = R[j, i] = rv; P[i, j] = P[j, i] = pv; N[i, j] = N[j, i] = len(s)
    iu = np.triu_indices(k, 1)
    pv = P[iu]; ok = np.isfinite(pv)
    Q = np.full((k, k), np.nan)
    qv = np.full(len(pv), np.nan); qv[ok] = multipletests(pv[ok], method="fdr_bh")[1]
    Q[iu] = qv; Q[(iu[1], iu[0])] = qv
    return {"r": [[r(v, 3) for v in row] for row in R], "p": [[pfmt(v) for v in row] for row in P],
            "q": [[pfmt(v) for v in row] for row in Q], "n": [[int(v) for v in row] for row in N], "method": method}


def daily_matrix():
    p = load("1_prepared_views/property_day.parquet")
    p["d"] = pd.to_datetime(p.gaming_date); p = p.set_index("d").sort_index()
    w = load("4_context/real_sources/weather_daily.parquet")
    w["d"] = pd.to_datetime(w.source_date); w = w.set_index("d")[["tmax_c", "prcp_mm"]].astype(float)
    seg = segment_day()
    X = pd.DataFrame({
        "Theo": p.theo_usd, "Coin-in": p.coin_in_usd, "Occupied hours": p.occupied_machine_hours,
        "Visitors' theo": seg.nonlocals, "Locals' theo": seg.locals,
        "Zone entries": p.total_zone_entries_observed / p.counter_coverage_share.replace(0, np.nan),
        "F&B cash": p.pos_cash_usd, "Comps given": p.comp_face_value_usd, "Carded share": p.carded_coin_in_share,
        "Available hours": p.available_machine_hours, "Faults": p.faults_opened, "Incidents": p.incidents_reported,
        "House win": p.house_win_usd, "Hold": p.observed_hold, "High temp": w.tmax_c, "Rain": w.prcp_mm,
    }).astype(float)
    raw = corr_block(X)
    # residual: weekday and slow level removed, ordinary days only (same recipe as WEATHER_NOTE.md)
    od = X[[d not in EV for d in X.index]].copy()
    logc = ["Theo", "Coin-in", "Occupied hours", "Visitors' theo", "Locals' theo", "Zone entries", "F&B cash",
            "Comps given", "Available hours", "House win"]
    Z = pd.DataFrame(index=od.index)
    dow = od.index.dayofweek
    for c in od.columns:
        v = od[c]
        if c in logc:
            v = np.log(v.where(v > 0))
        elif c in ("Faults", "Incidents"):
            v = np.log1p(v)
        if c in ("High temp",):
            Z[c] = v - v.rolling(15, center=True, min_periods=5).mean()
            continue
        if c == "Rain":
            Z[c] = v; continue
        a = v - v.groupby(dow).transform("mean")
        Z[c] = a - a.rolling(15, center=True, min_periods=5).median()
    res = corr_block(Z)
    return {"id": "daily", "vars": list(X.columns), "modes": {"raw": raw, "resid": res},
            "n_days": int(len(X)), "n_resid": int(Z.dropna().shape[0])}


def machine_matrix():
    v = active_machine_days()
    v["half"] = np.where(v.gaming_date < SPLIT, "A", "B")
    gm = load("2_machine_decision/game_math.parquet").set_index("config_id")
    g = v.groupby(["machine_id", "half"]).agg(
        theo=("theo_usd", "sum"), days=("gaming_date", "nunique"), occ=("occupied_hours", "sum"),
        avail=("available_hours", "sum"), down=("downtime_hours", "sum"), ci=("coin_in_usd", "sum"),
        spins=("paid_spins", "sum"), luck=("luck_residual_usd", "sum"), var=("win_var_cents2", "sum"),
        faults=("faults_opened", "sum"), cfg=("config_id", "last"), loc=("location_id", "last"),
        pos=("payout_positive_spins", "sum"), hp=("hit_prob", "mean"), vol=("volatility_class", "last")).unstack("half")
    keep = (g["days"]["A"] >= 30) & (g["days"]["B"] >= 20)
    g = g[keep]
    sdA, sdB = np.sqrt(g["var"]["A"] / 1e4), np.sqrt(g["var"]["B"] / 1e4)
    # luck carry-over checks: without machines whose payout rate is off configuration (hit-rate z, BH q < 0.05),
    # and by volatility class
    zA, zB = g["luck"]["A"] / sdA, g["luck"]["B"] / sdB
    N, Pp, hp = g["spins"]["A"] + g["spins"]["B"], g["pos"]["A"] + g["pos"]["B"], (g["hp"]["A"] + g["hp"]["B"]) / 2
    hz = (Pp - N * hp) / np.sqrt(N * hp * (1 - hp))
    ok = multipletests(2 * stats.norm.sf(np.abs(hz)), method="fdr_bh")[1] >= 0.05
    sp = lambda a, b: {"r": r(stats.spearmanr(a, b)[0], 3), "p": pfmt(stats.spearmanr(a, b)[1]), "n": int(len(a))}
    luck_check = {"excl_payout_off": {**sp(zA[ok], zB[ok]), "excluded": int((~ok).sum())},
                  "by_vol": {v: sp(zA[ok & (g["vol"]["B"] == v)], zB[ok & (g["vol"]["B"] == v)])
                             for v in ["low", "medium", "high", "very_high"]}}
    allh = lambda c: g[c]["A"] + g[c]["B"]
    X = pd.DataFrame({
        "Theo/day, Jan–Apr": g["theo"]["A"] / g["days"]["A"], "Theo/day, May–Jun": g["theo"]["B"] / g["days"]["B"],
        "Occupancy, Jan–Apr": g["occ"]["A"] / g["avail"]["A"], "Occupancy, May–Jun": g["occ"]["B"] / g["avail"]["B"],
        "Average bet": allh("ci") / allh("spins"),
        "House edge (config)": 1 - g["cfg"]["B"].map(gm.configured_rtp).astype(float),
        "Availability": allh("avail") / (allh("avail") + allh("down")),
        "Faults / 1,000 h": 1000 * allh("faults") / allh("avail"),
        "Luck z, Jan–Apr": g["luck"]["A"] / sdA, "Luck z, May–Jun": g["luck"]["B"] / sdB,
    }).astype(float)
    out = corr_block(X, "spearman")
    return {"id": "machines", "vars": list(X.columns), "modes": {"all": out}, "n": int(len(X)), "luckCheck": luck_check}


def player_matrix():
    pp = load("1_prepared_views/player_period.parquet")
    pp["h"] = np.where(pp.period_month.astype(str) < "2025-04", "A", "B")
    g = pp.groupby(["player_id", "h"]).agg(vis=("observed_visits", "sum"), theo=("theo_usd", "sum"),
                                           luck=("luck_residual_usd", "sum"), ci=("tracked_coin_in_usd", "sum"),
                                           pay=("tracked_payout_usd", "sum"), comps=("comp_face_value_usd", "sum"),
                                           hrs=("carded_play_hours", "sum"), fb=("linked_pos_cash_usd", "sum")).unstack("h").fillna(0)
    g = g[(g["vis"]["A"] > 0) & (g["vis"]["B"] > 0)]
    tot = lambda c: g[c]["A"] + g[c]["B"]
    X = pd.DataFrame({
        "Visits, Jan–Mar": g["vis"]["A"], "Visits, Apr–Jun": g["vis"]["B"],
        "Theo, Jan–Mar": g["theo"]["A"], "Theo, Apr–Jun": g["theo"]["B"],
        "Theo per visit": tot("theo") / tot("vis"), "Play hours": tot("hrs"),
        "Comps": tot("comps"), "Comps ÷ theo": tot("comps") / tot("theo").where(tot("theo") > 0),
        "F&B cash": tot("fb"),
        "Luck ÷ theo, Jan–Mar": g["luck"]["A"] / g["theo"]["A"].where(g["theo"]["A"] > 0),
        "Luck ÷ theo, Apr–Jun": g["luck"]["B"] / g["theo"]["B"].where(g["theo"]["B"] > 0),
    }).astype(float)
    out = corr_block(X, "spearman")
    # does Jan-Mar luck bring players back, once their Jan-Mar visits and theo are held fixed? (partial rank corr.)
    s = X[["Luck ÷ theo, Jan–Mar", "Visits, Apr–Jun", "Visits, Jan–Mar", "Theo, Jan–Mar"]].dropna().rank()
    Z = sm.add_constant(s[["Visits, Jan–Mar", "Theo, Jan–Mar"]])
    ra = sm.OLS(s["Luck ÷ theo, Jan–Mar"], Z).fit().resid
    rb = sm.OLS(s["Visits, Apr–Jun"], Z).fit().resid
    pr = stats.pearsonr(ra, rb)
    partial = {"r": r(pr[0], 3), "p": pfmt(pr[1]), "n": int(len(s))}
    return {"id": "players", "vars": list(X.columns), "modes": {"all": out}, "n": int(len(X)),
            "luckReturn": partial, "age": age_correlations()}


def age_correlations():
    bands = ["21-34", "35-49", "50-64", "65+"]
    sessions = pd.read_parquet(
        ROOT / "data/3_guests/sessions.parquet",
        columns=["player_id", "gaming_date", "logical_session_id", "coin_in_cents", "payout_cents", "theo_cents"],
    )
    sessions["month"] = sessions.gaming_date.astype(str).str[:7]
    sessions = sessions[sessions.month.isin(MONTHS)].copy()
    sessions["coin_in"] = sessions.coin_in_cents / 100
    sessions["payout"] = sessions.payout_cents / 100
    sessions["theo"] = sessions.theo_cents / 100
    g = sessions.groupby("player_id").agg(
        sessions=("logical_session_id", "nunique"),
        coin_in=("coin_in", "sum"),
        payout=("payout", "sum"),
        theo=("theo", "sum"),
    )
    guests = pd.read_parquet(ROOT / "data/3_guests/players.parquet", columns=["player_id", "age_band"]).set_index("player_id")
    g = g.join(guests.age_band, how="left")
    unknown = int((~g.age_band.isin(bands)).sum())
    g = g[g.age_band.isin(bands) & (g.coin_in > 0)].copy()
    age = g.age_band.map({band: i for i, band in enumerate(bands)})
    metrics = {
        "Sessions, Jan–Jun": g.sessions,
        "Coin-in, Jan–Jun": g.coin_in,
        "Theo per session": g.theo / g.sessions,
        "Net result ÷ coin-in": (g.payout - g.coin_in) / g.coin_in,
    }

    results = []
    for metric, values in metrics.items():
        valid = pd.DataFrame({"age": age, "value": values}).replace([np.inf, -np.inf], np.nan).dropna()
        corr = stats.spearmanr(valid.age.to_numpy(), valid.value.to_numpy())
        results.append({"metric": metric, "r": float(corr[0]), "p": float(corr[1]), "n": len(valid)})
    q = multipletests([x["p"] for x in results], method="fdr_bh")[1]
    for row, value in zip(results, q):
        row["r"] = r(row["r"], 3)
        row["p"] = pfmt(row["p"])
        row["q"] = pfmt(value)
    return {"n": int(len(g)), "unknown": unknown, "bands": bands, "rows": results}


def error_matrix():
    import forecast  # noqa
    import harness  # noqa
    from common import TRAIN_END  # noqa
    d = pd.read_csv(ROOT / "analysis/experiments/iter5/holdout_daily.csv", parse_dates=["gaming_date"]).set_index("gaming_date")
    d6 = pd.read_csv(ROOT / "analysis/experiments/iter6/holdout_daily.csv", parse_dates=["gaming_date"])
    df = harness.frame()
    tr, fut, full = harness._split(df, TRAIN_END, pd.Timestamp("2025-06-30"))
    b1 = pd.Series(forecast.m_b1(tr, fut, "theo_usd"), index=pd.to_datetime(full.gaming_date.to_numpy()))
    cols = {"B1 weekday mean": b1, "B2 event-aware": d["B2 event-aware weekday"], "EL (headline)": d["EL event-type lift"],
            "EL × CatBoost": d["EL x CatBoost residual (best post hoc)"], "EL + 2023–24 season": d["EL + hist seasonal beta=0.5"],
            "EL + recent level": d["EL + recent-level (28d) + payday"],
            "EL × 14-day level (iter 6)": d6[d6.protocol == "fixed"].set_index("gaming_date")["EL x mean14d [excl] w=100%"],
            "EL2A, weekly refit": d["EL2 + 28d anchor"],
            "Segments, weekly refit": d["EL2A segments: bottom_up beta=0.5"]}
    y = d.actual
    E = pd.DataFrame({k: v.reindex(y.index) - y for k, v in cols.items()})
    out = corr_block(E)
    bias = {k: r(E[k].mean(), 0) for k in E}
    rmse = {k: r(np.sqrt((E[k] ** 2).mean()), 0) for k in E}
    # how much of each model's squared error is the shared component (first principal component)?
    Ec = E - E.mean()
    ev = np.linalg.eigvalsh(np.corrcoef(Ec.T.to_numpy()))
    return {"id": "errors", "vars": list(E.columns), "modes": {"all": out}, "n": int(len(E)),
            "bias": bias, "rmse": rmse, "pc1_share": r(ev[-1] / ev.sum(), 3)}


def strongest(M, mode, k=8):
    m = M["modes"][mode]; v = M["vars"]; rows = []
    for i in range(len(v)):
        for j in range(i + 1, len(v)):
            if m["r"][i][j] is not None and m["q"][i][j] is not None:
                rows.append((abs(m["r"][i][j]), v[i], v[j], m["r"][i][j], m["q"][i][j]))
    return sorted(rows, reverse=True)[:k]


def main():
    out = weekly()
    C = [daily_matrix(), machine_matrix(), player_matrix(), error_matrix()]
    dump("corr", {m["id"]: m for m in C})
    if "-v" in sys.argv:
        import json
        print(json.dumps(out, indent=1, default=str)[:6000])
        for M in C:
            for mode in M["modes"]:
                print(M["id"], mode, [(a, b, rr, qq) for _, a, b, rr, qq in strongest(M, mode)])
        e = C[-1]; print("errors pc1", e["pc1_share"], e["bias"])


if __name__ == "__main__":
    main()
