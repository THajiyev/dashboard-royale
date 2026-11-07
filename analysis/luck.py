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
