"""Luck metrics.

Exact variance: house win = sum over spins of bet × (1 − payout multiple), so
Var(house win) = Σ bet² × Var(payout multiple) = sum_bet_squared × payout_multiplier_variance.
Luck z = (house win − theo) / sqrt(Var). Under fair play z ≈ N(0, 1).
Hit-rate z: payout-positive spins vs Binomial(paid spins, hit_probability) — a payout-configuration check.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def machine_luck(v: pd.DataFrame) -> pd.DataFrame:
    """Per-machine luck table over the rows given (all active machine-days of the window)."""
    v = v.sort_values("gaming_date")
    g = v.groupby("machine_id").agg(
        zone_name=("zone_name", "last"), theme=("theme", "last"), config_id=("config_id", "last"),
        manufacturer=("manufacturer", "first"), volatility_class=("volatility_class", "last"),
        zones=("zone_name", "nunique"), days=("gaming_date", "nunique"), coin_in_usd=("coin_in_usd", "sum"), house_win_usd=("house_win_usd", "sum"),
        theo_usd=("theo_usd", "sum"), var_c2=("win_var_cents2", "sum"), spins=("paid_spins", "sum"),
        pos=("payout_positive_spins", "sum"), hit_prob=("hit_prob", "first"),
        avail_h=("available_hours", "sum"), down_h=("downtime_hours", "sum")).reset_index()
    g["luck_usd"] = g.house_win_usd - g.theo_usd
    g["luck_sd_usd"] = np.sqrt(g.var_c2) / 100
    g["luck_z"] = g.luck_usd / g.luck_sd_usd
    g["luck_p_two_sided"] = 2 * stats.norm.sf(np.abs(g.luck_z))
    g["luck_percentile"] = stats.norm.cdf(g.luck_z)  # 0.02 = unluckier than 98% of fair outcomes
    g["observed_hold"] = g.house_win_usd / g.coin_in_usd
    g["theo_hold"] = g.theo_usd / g.coin_in_usd
    half = 1.96 * g.luck_sd_usd / g.coin_in_usd
    g["hold_ci95_lo"], g["hold_ci95_hi"] = g.theo_hold - half, g.theo_hold + half  # where a fair machine's hold lands
    n, p = g.spins, g.hit_prob
    g["hit_rate"] = g.pos / n
    g["hit_z"] = (g.pos - n * p) / np.sqrt(n * p * (1 - p))
    g["theo_per_avail_hr"] = g.theo_usd / g.avail_h
    g["rank_by_win"] = g.house_win_usd.rank(method="first").astype(int)  # 1 = lowest earner
    g["rank_by_theo"] = g.theo_usd.rank(method="first").astype(int)  # total theo: still penalises short exposure
    # luck-free AND exposure-free ranking (GUIDE §5): expected revenue per available hour
    g["rank_by_theo_per_hr"] = g.theo_per_avail_hr.rank(method="first").astype(int)
    return g.drop(columns=["var_c2", "pos"]).sort_values("house_win_usd")


def bottom10_comparison(luck: pd.DataFrame, short_days: int = 150) -> pd.DataFrame:
    """GM's bottom 10 by house win, with every reason that applies (they are not exclusive).

    Low earners are judged on theo per available hour, so a machine that was on the floor for
    49 days is not excused as "short exposure" if it also earns little per hour it was there.
    """
    b = luck.nsmallest(10, "house_win_usd").copy()
    b["in_bottom10_by_theo_per_hr"] = b.rank_by_theo_per_hr <= 10
    b["theo_per_day"] = b.theo_usd / b.days
    flags = {
        "payout mismatch (hit-rate test) → inspect": b.hit_z.abs() > 5,
        "low expected revenue per hour (bottom 10 theo/hr)": b.rank_by_theo_per_hr <= 10,
        f"short exposure (on floor < {short_days} of 181 days)": b.days < short_days,
        "unlucky (luck z < −2)": b.luck_z < -2,
    }
    b["basic_read"] = [" + ".join(k for k, m in flags.items() if m.loc[i]) or "mixed: modest bad luck + low theo"
                       for i in b.index]
    return b[["machine_id", "zone_name", "zones", "theme", "days", "house_win_usd", "theo_per_day", "theo_per_avail_hr", "theo_usd",
              "luck_usd", "luck_z", "luck_p_two_sided", "hit_z", "rank_by_win", "rank_by_theo", "rank_by_theo_per_hr",
              "in_bottom10_by_theo_per_hr", "basic_read"]]


# ----------------------------------------------------------------------------- Phase 1 luck engine
def bh_qvalues(p: np.ndarray) -> np.ndarray:
    """Benjamini–Hochberg adjusted p-values (q-values)."""
    p = np.asarray(p, float)
    n = len(p)
    order = np.argsort(p)
    q = p[order] * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(q, 1)
    return out


def cusum(z: np.ndarray, k: float = 0.5, h: float = 4.0) -> tuple[float, int]:
    """Two-sided tabular CUSUM on standardised values. Returns (max statistic, first alarm index or -1)."""
    sp = sn = 0.0
    best, alarm = 0.0, -1
    for i, x in enumerate(z):
        sp, sn = max(0.0, sp + x - k), max(0.0, sn - x - k)
        best = max(best, sp, sn)
        if alarm < 0 and max(sp, sn) > h:
            alarm = i
    return best, alarm


def monthly_z(v: pd.DataFrame) -> pd.DataFrame:
    """Per machine-month luck z and hit-rate z (independent across months under fair play)."""
    g = v.groupby(["machine_id", "month"]).agg(win=("house_win_usd", "sum"), theo=("theo_usd", "sum"),
                                               var=("win_var_cents2", "sum"), n=("paid_spins", "sum"),
                                               pos=("payout_positive_spins", "sum"), p=("hit_prob", "first")).reset_index()
    g["luck_z"] = (g.win - g.theo) / (np.sqrt(g["var"]) / 100)
    g["hit_z"] = (g.pos - g.n * g.p) / np.sqrt(g.n * g.p * (1 - g.p))
    return g.replace([np.inf, -np.inf], np.nan).dropna(subset=["luck_z", "hit_z"])


def luck_engine(v: pd.DataFrame, luck: pd.DataFrame, fdr: float = 0.05, n_sim: int = 2000) -> tuple[pd.DataFrame, dict]:
    """Extends machine_luck: 99% hold band, BH q-values, volatility index, monthly CUSUM, jackpot share."""
    L = luck.copy().set_index("machine_id")
    half99 = 2.576 * L.luck_sd_usd / L.coin_in_usd
    L["hold_ci99_lo"], L["hold_ci99_hi"] = L.theo_hold - half99, L.theo_hold + half99
    L["hit_p_two_sided"] = 2 * stats.norm.sf(L.hit_z.abs())
    L["luck_q_bh"], L["hit_q_bh"] = bh_qvalues(L.luck_p_two_sided), bh_qvalues(L.hit_p_two_sided)
    pv = v.groupby("machine_id").payout_var.first()
    L["volatility_index"] = 1.645 * np.sqrt(pv)  # industry VI: 90% one-sided spread of payout per unit bet

    # jackpot share: how much of a luck deficit came from the single worst day
    d = v.assign(day_luck=v.house_win_usd - v.theo_usd)
    L["worst_day_luck_usd"] = d.groupby("machine_id").day_luck.min().reindex(L.index)
    share = (L.worst_day_luck_usd / L.luck_usd).clip(upper=1.0)  # 1.0 = one day explains the whole deficit
    L["jackpot_share_of_deficit"] = share.where(L.luck_usd < 0)

    mz = monthly_z(v)
    cs = {}
    for m, g in mz.sort_values("month").groupby("machine_id"):
        lz, la = cusum(g.luck_z.to_numpy())
        hz, ha = cusum(g.hit_z.to_numpy())
        cs[m] = {"cusum_luck_max": lz, "cusum_luck_alarm_month": g.month.iloc[la] if la >= 0 else None,
                 "cusum_hit_max": hz, "cusum_hit_alarm_month": g.month.iloc[ha] if ha >= 0 else None,
                 "hit_z_months_above_3": int((g.hit_z > 3).sum()), "months": len(g)}
    L = L.join(pd.DataFrame.from_dict(cs, orient="index"))

    # null calibration of the CUSUM alarm count: same machines × months, z ~ N(0,1)
    rng = np.random.default_rng(0)
    months = L.months.fillna(0).astype(int).to_numpy()
    sims = [sum(cusum(rng.standard_normal(k))[1] >= 0 for k in months if k) for _ in range(n_sim // 10)]
    info = {
        "luck_flags_bh": int((L.luck_q_bh < fdr).sum()), "hit_flags_bh": int((L.hit_q_bh < fdr).sum()),
        "luck_flags_raw_p05": int((L.luck_p_two_sided < 0.05).sum()),
        "expected_false_luck_flags_raw": 0.05 * len(L),
        "cusum_luck_alarms": int(L.cusum_luck_alarm_month.notna().sum()),
        "cusum_hit_alarms": int(L.cusum_hit_alarm_month.notna().sum()),
        "cusum_alarms_expected_null": float(np.mean(sims)),
        "monthly_luck_z_sd": float(mz.luck_z.std()), "monthly_hit_z_sd_ex_top": float(mz[mz.hit_z.abs() < 10].hit_z.std()),
    }
    return L.reset_index(), info
