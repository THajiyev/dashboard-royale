"""Export the "is anyone due?" results for the static site (docs/data/streaks.js).

    python scripts/build_site_streaks.py [-v]

Carded play, Jan 1 - Jun 30 2025, one row per observed visit. Per visit, as on the Players page:
  luck = actual payout - expected payout (coin-in - theo); Var(luck) = sum_bet_squared x payout_multiplier_variance
  z    = luck / sd;  ended ahead = payout > coin-in (the player left with more than they put in)

Tests of "due" (losses now make wins more likely later):
  1. Streaks: share of next visits that end ahead, by the streak a player is on going in. Compared with the same
     visits shuffled into random order within each player (keeps who plays and how much; removes only order).
  2. Half against half: players' luck z in Jan-Mar, in tenths, against their luck z in Apr-Jun.
  3. Behind in dollars: cumulative luck going into a visit, in fifths, against the next visit.
What can be predicted: swing size (Jan-Mar sd against Apr-Jun |luck|), and the house edge over volume.
What losing does change: the share of visits followed by another visit within 30 days, by how the visit went.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
sys.path[:0] = [str(ROOT / "scripts")]
from build_site_data import dump, r  # noqa: E402

N_SHUF = 40
SEED = 20250701
SPLIT = pd.Timestamp("2025-04-01")
END = pd.Timestamp("2025-07-01 13:00:00")
L_BINS = [1, 2, 3, 4, 5, 6]   # losing streak going in (6 = 6 or more)
W_BINS = [1, 2, 3]            # winning streak going in (3 = 3 or more)


def visits() -> pd.DataFrame:
    gm = pd.read_parquet(DATA / "2_machine_decision/game_math.parquet").set_index("config_id")
    s = pd.read_parquet(DATA / "3_guests/sessions.parquet",
                        columns=["player_id", "observed_visit_id", "config_id", "start_utc", "end_utc", "coin_in_cents",
                                 "payout_cents", "theo_cents", "sum_bet_squared", "paid_spins"])
    s = s.dropna(subset=["player_id"])
    s["ci"] = s.coin_in_cents / 100
    s["po"] = s.payout_cents / 100
    s["theo"] = s.theo_cents.astype(float) / 100
    s["var"] = s.sum_bet_squared * s.config_id.map(gm.payout_multiplier_variance).astype(float) / 1e4
    v = s.groupby(["player_id", "observed_visit_id"]).agg(
        t0=("start_utc", "min"), t1=("end_utc", "max"), ci=("ci", "sum"), po=("po", "sum"),
        theo=("theo", "sum"), var=("var", "sum"), spins=("paid_spins", "sum")).reset_index()
    v = v[(v.ci > 0) & (v["var"] > 0)].copy()
    v["t0"], v["t1"] = pd.to_datetime(v.t0), pd.to_datetime(v.t1)
    v["luck"] = v.po - (v.ci - v.theo)
    v["sd"] = np.sqrt(v["var"])
    v["z"] = v.luck / v.sd
    v["ahead"] = v.po > v.ci
    v = v.sort_values(["player_id", "t0"]).reset_index(drop=True)
    return v


def streak_in(pid: np.ndarray, ahead: np.ndarray) -> np.ndarray:
    """Signed streak going into each visit: -k after k losing visits in a row, +k after k winning; 0 = first visit."""
    out = np.zeros(len(pid), dtype=int)
    for i in range(1, len(pid)):
        if pid[i] != pid[i - 1]:
            continue
        prev = out[i - 1]
        if ahead[i - 1]:
            out[i] = prev + 1 if prev > 0 else 1
        else:
            out[i] = prev - 1 if prev < 0 else -1
    return out


def streak_table(pid, ahead, z):
    st = streak_in(pid, ahead)
    keys = [-k for k in L_BINS[::-1]] + W_BINS
    b = np.clip(st, -L_BINS[-1], W_BINS[-1])
    rows = {}
    for k in keys:
        m = b == k
        rows[k] = (int(m.sum()), float(ahead[m].mean()) if m.any() else np.nan, float(z[m].mean()) if m.any() else np.nan)
    return rows


def wilson(p, n, zc=1.96):
    if n == 0:
        return (None, None)
    d = 1 + zc ** 2 / n
    c = (p + zc ** 2 / (2 * n)) / d
    h = zc * np.sqrt(p * (1 - p) / n + zc ** 2 / (4 * n * n)) / d
    return (c - h, c + h)


def streaks(v: pd.DataFrame):
    pid = v.player_id.to_numpy()
    ahead = v.ahead.to_numpy()
    z = v.z.to_numpy()
    obs = streak_table(pid, ahead, z)
    rng = np.random.default_rng(SEED)
    shuf = {k: [] for k in obs}
    for _ in range(N_SHUF):
        key = rng.random(len(v))
        o = np.lexsort((key, pid))  # random order within each player
        t = streak_table(pid[o], ahead[o], z[o])
        for k in t:
            shuf[k].append(t[k][1])
    out = []
    for k, (n, p, mz) in obs.items():
        lo, hi = wilson(p, n)
        sh = np.array(shuf[k])
        out.append({"streak": k, "n": n, "ahead": r(p, 4), "lo": r(lo, 4), "hi": r(hi, 4), "mean_z": r(mz, 3),
                    "shuf": r(sh.mean(), 4), "shuf_lo": r(np.quantile(sh, 0.025), 4), "shuf_hi": r(np.quantile(sh, 0.975), 4)})
    # one number: does a losing visit change the chance the next visit ends ahead, beyond player mix?
    prev = np.r_[False, pid[1:] == pid[:-1]]
    nxt_ahead = ahead[prev]
    prev_ahead = np.r_[False, ahead[:-1]][prev]
    diff_obs = nxt_ahead[~prev_ahead].mean() - nxt_ahead[prev_ahead].mean()
    diffs = []
    for _ in range(N_SHUF):
        o = np.lexsort((rng.random(len(v)), pid))
        a2 = ahead[o]
        pa = np.r_[False, a2[:-1]][prev]
        na = a2[prev]
        diffs.append(na[~pa].mean() - na[pa].mean())
    diffs = np.array(diffs)
    return out, {"after_loss_minus_after_win": r(diff_obs, 4), "shuf_mean": r(diffs.mean(), 4),
                 "shuf_lo": r(np.quantile(diffs, 0.025), 4), "shuf_hi": r(np.quantile(diffs, 0.975), 4),
                 "pairs": int(prev.sum()), "after_loss": r(nxt_ahead[~prev_ahead].mean(), 4),
                 "after_win": r(nxt_ahead[prev_ahead].mean(), 4)}


def halves(v: pd.DataFrame):
    v = v.assign(h=np.where(v.t0 < SPLIT, 0, 1))
    g = v.groupby(["player_id", "h"]).agg(luck=("luck", "sum"), var=("var", "sum"), ci=("ci", "sum"),
                                          theo=("theo", "sum"), po=("po", "sum"), n=("spins", "sum")).unstack()
    g = g.dropna()
    z1 = g["luck"][0] / np.sqrt(g["var"][0])
    z2 = g["luck"][1] / np.sqrt(g["var"][1])
    rho, p_rho = stats.spearmanr(z1, z2)
    fit = stats.linregress(z1, z2)
    dec = pd.qcut(z1.rank(method="first"), 10, labels=False)
    rows = []
    for d in range(10):
        m = dec == d
        a, b = z1[m], z2[m]
        se = b.std(ddof=1) / np.sqrt(len(b))
        ahead2 = (g["po"][1][m] > g["ci"][1][m]).mean()
        rows.append({"decile": d + 1, "n": int(m.sum()), "z1": r(a.mean(), 3), "z2": r(b.mean(), 3),
                     "z2_lo": r(b.mean() - 1.96 * se, 3), "z2_hi": r(b.mean() + 1.96 * se, 3),
                     "z2_median": r(b.median(), 3), "ahead2": r(ahead2, 4)})
    # swing size: Jan-Mar sd (how hard they play) against Apr-Jun realised |luck|, and the share who end ahead
    sd1 = np.sqrt(g["var"][0])
    sd2 = np.sqrt(g["var"][1])
    abs2 = g["luck"][1].abs()
    rho_sw, _ = stats.spearmanr(sd1, abs2)
    rho_dir, p_dir = stats.spearmanr(sd1, g["luck"][1])
    q = pd.qcut(sd1.rank(method="first"), 10, labels=False)
    sw = []
    for d in range(10):
        m = q == d
        net2 = g["po"][1][m] - g["ci"][1][m]
        sw.append({"decile": d + 1, "n": int(m.sum()), "sd1": r(sd1[m].median(), 0),
                   "abs_luck2_med": r(abs2[m].median(), 0), "abs_luck2_p90": r(abs2[m].quantile(0.9), 0),
                   "net2_med": r(net2.median(), 0), "ahead2": r((net2 > 0).mean(), 4),
                   "luck_z2": r(z2[m].mean(), 3)})
    return ({"players": int(len(g)), "rho": r(rho, 4), "p": r(p_rho, 4), "slope": r(fit.slope, 4),
             "slope_lo": r(fit.slope - 1.96 * fit.stderr, 4), "slope_hi": r(fit.slope + 1.96 * fit.stderr, 4),
             "deciles": rows},
            {"players": int(len(g)), "rho_size": r(rho_sw, 3), "rho_sd2": r(stats.spearmanr(sd1, sd2)[0], 3),
             "rho_direction": r(rho_dir, 4), "p_direction": r(p_dir, 4), "deciles": sw})


def behind(v: pd.DataFrame):
    """Cumulative luck (dollars) going into a visit, players with 3+ earlier visits, in fifths."""
    v = v.copy()
    g = v.groupby("player_id")
    v["k"] = g.cumcount()
    v["cum"] = g.luck.cumsum() - v.luck
    v["cumz"] = v.cum / np.sqrt(g["var"].cumsum() - v["var"]).replace(0, np.nan)
    w = v[v.k >= 3].dropna(subset=["cumz"])
    q = pd.qcut(w.cumz.rank(method="first"), 5, labels=False)
    names = ["Furthest behind", "Behind", "About even", "Ahead", "Furthest ahead"]
    rows = []
    for i in range(5):
        m = q == i
        x = w[m]
        p = x.ahead.mean()
        lo, hi = wilson(p, len(x))
        rows.append({"band": names[i], "n": int(len(x)), "cum_med": r(x.cum.median(), 0), "cumz_med": r(x.cumz.median(), 2),
                     "ahead": r(p, 4), "lo": r(lo, 4), "hi": r(hi, 4), "mean_z": r(x.z.mean(), 3),
                     "mean_z_lo": r(x.z.mean() - 1.96 * x.z.std() / np.sqrt(len(x)), 3),
                     "mean_z_hi": r(x.z.mean() + 1.96 * x.z.std() / np.sqrt(len(x)), 3)})
    rho, p = stats.spearmanr(w.cumz, w.z)
    return {"visits": int(len(w)), "players": int(w.player_id.nunique()), "rho": r(rho, 4), "p": r(p, 4), "bands": rows}


def comeback(v: pd.DataFrame):
    """Share of visits followed by another visit within 30 days, by how that visit went (luck z, fifths).
    Only visits ending 30+ days before the data ends."""
    v = v.copy()
    v["next_t0"] = v.groupby("player_id").t0.shift(-1)
    w = v[v.t1 <= END - pd.Timedelta(days=30)].copy()
    w["back"] = (w.next_t0 - w.t1) <= pd.Timedelta(days=30)
    q = pd.qcut(w.z.rank(method="first"), 5, labels=False)
    names = ["Worst fifth", "Second", "Middle", "Fourth", "Best fifth"]
    rows = []
    for i in range(5):
        x = w[q == i]
        p = x.back.mean()
        lo, hi = wilson(p, len(x))
        rows.append({"band": names[i], "n": int(len(x)), "z_med": r(x.z.median(), 2), "net_med": r((x.po - x.ci).median(), 0),
                     "back": r(p, 4), "lo": r(lo, 4), "hi": r(hi, 4)})
    # same comparison within spend: does the luck effect survive holding coin-in fixed?
    w["ci_q"] = pd.qcut(w.ci.rank(method="first"), 5, labels=False)
    w["z_q"] = q
    within = w.groupby("ci_q").apply(lambda x: x[x.z_q == 0].back.mean() - x[x.z_q == 4].back.mean(), include_groups=False)
    return {"visits": int(len(w)), "bands": rows, "gap_within_spend": [r(x, 4) for x in within]}


def main():
    v = visits()
    st, st1 = streaks(v)
    hv, sw = halves(v)
    out = {"visits": int(len(v)), "players": int(v.player_id.nunique()),
           "repeat_players": int((v.groupby("player_id").size() > 1).sum()),
           "ahead_rate": r(v.ahead.mean(), 4), "mean_z": r(v.z.mean(), 4), "n_shuffles": N_SHUF,
           "streaks": st, "next": st1, "halves": hv, "swing": sw, "behind": behind(v), "comeback": comeback(v)}
    dump("streaks", out)
    if "-v" in sys.argv:
        import json
        print(json.dumps(out, indent=1)[:9000])


if __name__ == "__main__":
    main()
