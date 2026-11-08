"""Player outcomes for the dashboard (docs/data/players.js and players_all.js).

Carded play only (sessions reconcile exactly with player_period). For each player:
  expected payout  = coin-in − theo           (what the games' configured RTP pays back)
  actual payout    = payout
  luck             = actual − expected payout  (player's view: + means luckier than expected)
  Var(luck)        = Σ sum_bet_squared × payout_multiplier_variance   (exact, per spin)
  z                = luck / sd  (descriptive: in standard deviations)
  peer percentile  = rank of z among players whose play was mostly on the same game with a similar
                     number of spins (spin-count fifths within the game). Slot payouts are heavily skewed
                     (rare large jackpots), so for short play the normal curve badly understates how often
                     big wins happen; z-based p-values flag thousands of fair players. Peers are the
                     calibrated yardstick instead.
  win-rate z       = payout-positive spins vs Binomial(spins, hit_probability). Spin outcomes are
                     win/no-win, so this test is well calibrated; Benjamini–Hochberg q over all players.
Fair play: P(player ends ahead) ≈ Φ(−theo / sd), summed for "expected winners" (approximate for short play).
Every summary is precomputed for each From–To month range and each guest group.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BINS = np.arange(-5, 5.0001, 0.25)
PBINS = np.linspace(0, 1, 21)
TIER_ORDER = {"Base": 0, "Gold": 1, "Platinum": 2}


def bh(p: np.ndarray) -> np.ndarray:
    n = len(p)
    o = np.argsort(p)
    q = p[o] * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out = np.empty(n)
    out[o] = np.minimum(q, 1)
    return out


def win_rate_p(g: pd.DataFrame) -> np.ndarray:
    """Exact two-sided binomial p for payout-positive spins, at the player's spin-weighted hit probability.

    A player's spins can span games with different odds (a Poisson-binomial); the pooled binomial is
    a close, slightly conservative stand-in. Exact rather than normal so short, low-hit-rate play
    (e.g. Comet Cash at 4.6%) isn't over-flagged.
    """
    n = g.n.to_numpy().astype(int)
    k = g.pos.to_numpy().astype(int)
    pbar = np.divide(g.epos.to_numpy(), n, out=np.zeros(len(g)), where=n > 0)
    hi = stats.binom.sf(k - 1, n, pbar)
    lo = stats.binom.cdf(k, n, pbar)
    return np.where(n > 0, np.minimum(1.0, 2 * np.minimum(hi, lo)), 1.0)


def lorenz(v: np.ndarray, k: int = 50) -> list:
    """Cumulative share of the total, players sorted largest first, at k+1 evenly spaced player shares."""
    v = np.sort(v)[::-1]
    tot = v.sum()
    if len(v) == 0 or tot == 0:
        return [0] * (k + 1)
    c = np.concatenate([[0], np.cumsum(v)]) / tot
    idx = np.round(np.linspace(0, len(v), k + 1)).astype(int)
    return [round(float(x), 4) for x in c[idx]]


def top_share(v: np.ndarray, frac: float) -> float:
    v = np.sort(v)[::-1]
    n = max(1, int(round(len(v) * frac)))
    return float(v[:n].sum() / v.sum()) if v.sum() else 0.0


def players(dump, r, MONTHS):
    gm = pd.read_parquet(DATA / "2_machine_decision/game_math.parquet").set_index("config_id")
    s = pd.read_parquet(DATA / "3_guests/sessions.parquet",
                        columns=["player_id", "gaming_date", "machine_id", "config_id", "coin_in_cents", "payout_cents",
                                 "theo_cents", "sum_bet_squared", "paid_spins", "payout_positive_spins", "logical_session_id"])
    s["m"] = s.gaming_date.astype(str).str[:7].map({m: i for i, m in enumerate(MONTHS)})
    s["theo"] = s.theo_cents.astype(float) / 100
    s["ci"] = s.coin_in_cents / 100
    s["po"] = s.payout_cents / 100
    s["var"] = s.sum_bet_squared * s.config_id.map(gm.payout_multiplier_variance).astype(float) / 1e4  # usd^2
    hp = s.config_id.map(gm.hit_probability).astype(float)
    s["epos"] = s.paid_spins * hp
    s["vpos"] = s.paid_spins * hp * (1 - hp)

    pm = s.groupby(["player_id", "m"]).agg(ci=("ci", "sum"), po=("po", "sum"), theo=("theo", "sum"), var=("var", "sum"),
                                            n=("paid_spins", "sum"), pos=("payout_positive_spins", "sum"),
                                            epos=("epos", "sum"), vpos=("vpos", "sum"),
                                            ses=("logical_session_id", "nunique")).reset_index()
    pmm = s.groupby(["player_id", "m", "machine_id"]).ci.sum().reset_index()
    pmc = s.groupby(["player_id", "m", "config_id"]).ci.sum().reset_index()
    cfg_theme = gm.theme.to_dict()

    def peer_pct(g: pd.DataFrame, a: int, b: int):
        """Dominant game per player, the percentile of z among peers (same game, similar spin count),
        and the empirical two-sided p-value: twice the share of peers at least as extreme on the same side."""
        c = pmc[(pmc.m >= a) & (pmc.m <= b)].groupby(["player_id", "config_id"]).ci.sum().reset_index()
        dom = c.sort_values("ci", ascending=False).drop_duplicates("player_id").set_index("player_id").config_id
        h = g[["z", "n"]].join(dom.rename("cfg"))
        h["bucket"] = h.groupby("cfg").n.transform(lambda x: pd.qcut(x.rank(method="first"), 5, labels=False))
        grp = h.groupby(["cfg", "bucket"]).z
        rk, N = grp.rank(method="max"), grp.transform("size")
        rk_lo = grp.rank(method="min")
        pct = rk / N
        p_lo, p_up = rk / N, (N - rk_lo + 1) / N
        mp = np.minimum(1.0, 2 * np.minimum(p_lo, p_up))
        return h.cfg, pct, mp

    # guest groups: home region and age band from players; tier = tier at the end of the player's last month
    pl = pd.read_parquet(DATA / "3_guests/players.parquet", columns=["player_id", "home_region", "age_band"]).set_index("player_id")
    pl["age_band"] = pl.age_band.fillna("Unknown")
    pp = pd.read_parquet(DATA / "1_prepared_views/player_period.parquet", columns=["player_id", "period_month", "tier_end"])
    pp["m"] = pp.period_month.astype(str).str[:7].map({m: i for i, m in enumerate(MONTHS)})
    tier = pp.sort_values("m").groupby("player_id").tier_end.last()

    groups = {"region": ["Local", "Regional", "Domestic", "International"],
              "age": ["21-34", "35-49", "50-64", "65+", "Unknown"],
              "tier": ["Base", "Gold", "Platinum"]}
    attr = pd.DataFrame({"region": pl.home_region, "age": pl.age_band}).join(tier.rename("tier"))

    ranges, anomalies = {}, {}
    for a in range(6):
        for b in range(a, 6):
            key = f"{a}-{b}"
            g = pm[(pm.m >= a) & (pm.m <= b)].groupby("player_id")[["ci", "po", "theo", "var", "n", "pos", "epos", "vpos", "ses"]].sum()
            g = g.join(attr, how="left")
            sd = np.sqrt(g["var"].to_numpy())
            exp_po = (g.ci - g.theo).to_numpy()
            luck = g.po.to_numpy() - exp_po
            z = np.divide(luck, sd, out=np.zeros_like(luck), where=sd > 0)
            hz = np.divide((g.pos - g.epos).to_numpy(), np.sqrt(g.vpos.to_numpy()), out=np.zeros(len(g)), where=g.vpos.to_numpy() > 0)
            hp = win_rate_p(g)
            hq = bh(hp)
            net = (g.po - g.ci).to_numpy()
            g = g.assign(sd=sd, exp_po=exp_po, luck=luck, z=z, hz=hz, hp=hp, hq=hq, net=net)
            cfg, pct, mp = peer_pct(g, a, b)
            g = g.assign(cfg=cfg, pct=pct, mp=mp)
            g["mq"] = bh(g.mp.fillna(1).to_numpy())

            segs = {"all": np.ones(len(g), bool)}
            for dim, vals in groups.items():
                for v in vals:
                    segs[f"{dim}:{v}"] = (g[dim] == v).to_numpy()
            out = {}
            for sk, mask in segs.items():
                h = g[mask]
                if not len(h):
                    continue
                loss = -h.net.to_numpy()
                losers = loss[loss > 0]
                zc = np.clip(h.z.to_numpy(), -4.9999, 4.9999)
                out[sk] = {
                    "players": int(len(h)), "sessions": int(h.ses.sum()),
                    "ci": r(h.ci.sum(), 0), "po": r(h.po.sum(), 0), "theo": r(h.theo.sum(), 0), "luck": r(h.luck.sum(), 0),
                    "sd": r(np.sqrt(h["var"].sum()), 0),
                    "ahead": int((h.net > 0).sum()),
                    "zHi": int((h.z > 1.96).sum()), "zLo": int((h.z < -1.96).sum()),
                    "hitOut": int((np.abs(h.hz) > 1.96).sum()), "hitFlag": int((h.hq < 0.05).sum()),
                    "hitHist": np.histogram(np.clip(h.hz.to_numpy(), -4.9999, 4.9999), BINS)[0].tolist(),
                    "hitP": np.histogram(h.hp.to_numpy(), PBINS)[0].tolist(), "monP": np.histogram(h.mp.fillna(1).to_numpy(), PBINS)[0].tolist(),
                    "hitP05": int((h.hp < 0.05).sum()), "monP05": int((h.mp < 0.05).sum()), "monFlag": int((h.mq < 0.05).sum()),
                    "expNet": r(-h.theo.sum(), 0),
                    "winnings": r(h.net[h.net > 0].sum(), 0), "losses": r(losers.sum(), 0),
                    "top1": round(top_share(losers, 0.01), 4) if len(losers) else 0,
                    "top10": round(top_share(losers, 0.10), 4) if len(losers) else 0,
                    "top1Theo": round(top_share(h.theo.to_numpy(), 0.01), 4), "top10Theo": round(top_share(h.theo.to_numpy(), 0.10), 4),
                    "lorLoss": lorenz(np.clip(loss, 0, None)), "lorTheo": lorenz(h.theo.to_numpy()),
                    "hist": np.histogram(zc, BINS)[0].tolist(),
                }
            ranges[key] = out

            # two lists: win rate off the game's odds (flagged + largest |win-rate z|),
            # and the largest money results against expectation, both directions
            hit = g[g.hq < 0.05]
            hit = pd.concat([hit, g[~g.index.isin(hit.index)].assign(a=np.abs(g.hz)).sort_values("a", ascending=False).head(40)])
            money = pd.concat([g.sort_values("luck", ascending=False).head(100), g.sort_values("luck").head(50)])
            pick = pd.concat([hit.assign(list="hit"), money.assign(list="money")])
            mm = pmm[(pmm.m >= a) & (pmm.m <= b) & pmm.player_id.isin(pick.index)].groupby(["player_id", "machine_id"]).ci.sum().reset_index()
            top = mm.sort_values("ci", ascending=False).drop_duplicates("player_id").set_index("player_id")
            anomalies[key] = [{
                "list": x.list, "id": pid, "region": x.region, "age": x.age, "tier": x.tier, "ses": int(x.ses), "n": int(x.n),
                "ci": r(x.ci, 0), "exp": r(x.exp_po, 0), "po": r(x.po, 0), "sd": r(x.sd, 0), "z": r(x.z, 2),
                "pct": r(x.pct, 5), "game": cfg_theme.get(x.cfg), "hz": r(x.hz, 2), "hq": float(f"{x.hq:.3g}"),
                "hp": float(f"{x.hp:.3g}"), "mp": float(f"{x.mp:.3g}"), "mq": float(f"{x.mq:.3g}"),
                "pos": int(x.pos), "epos": r(x.epos, 1),
                "mach": top.machine_id.get(pid), "machShare": r(top.ci.get(pid, 0) / x.ci if x.ci else 0, 2),
            } for pid, x in pick.iterrows()]
            print(f"players {key}: {len(g)} players, win p<.05 {int((g.hp < 0.05).sum())} flagged {int((g.hq < 0.05).sum())}; "
                  f"money p<.05 {int((g.mp < 0.05).sum())} flagged {int((g.mq < 0.05).sum())}")

    # machines where win-rate-flagged players did most of their play, per period (small file the floor and machine pages read)
    pf = {k: {} for k in anomalies}
    for k, rows in anomalies.items():
        for x in rows:
            if x["list"] == "hit" and x["hq"] < 0.05 and x["mach"] and (x["machShare"] or 0) >= 0.5:
                pf[k][x["mach"]] = pf[k].get(x["mach"], 0) + 1
    dump("player_flags", pf)

    dump("players", {"bins": [round(float(x), 2) for x in BINS], "pbins": [round(float(x), 2) for x in PBINS],
                     "groups": groups, "ranges": ranges, "anomalies": anomalies})

    # every player, Jan–Jun, columnar to keep the file small
    g = pm.groupby("player_id")[["ci", "po", "theo", "var", "n", "pos", "epos", "vpos", "ses"]].sum().join(attr, how="left")
    hz = (g.pos - g.epos) / np.sqrt(g.vpos)
    sd = np.sqrt(g["var"])
    g["z"] = np.where(sd > 0, (g.po - (g.ci - g.theo)) / sd.where(sd > 0, 1), 0)
    cfg, pct, mp = peer_pct(g, 0, 5)
    hp = win_rate_p(g)
    hq = bh(hp)
    mp = mp.reindex(g.index).fillna(1)
    mq = bh(mp.to_numpy())
    games = list(gm.theme)
    code = {d: {v: i for i, v in enumerate(vals)} for d, vals in groups.items()}
    dump("players_all", {
        "id": g.index.tolist(),
        "region": g.region.map(code["region"]).fillna(-1).astype(int).tolist(),
        "age": g.age.map(code["age"]).fillna(-1).astype(int).tolist(),
        "tier": g.tier.map(code["tier"]).fillna(-1).astype(int).tolist(),
        "ses": g.ses.astype(int).tolist(),
        "ci": np.round(g.ci).astype(int).tolist(), "po": np.round(g.po).astype(int).tolist(),
        "theo": np.round(g.theo, 1).tolist(), "sd": np.round(np.sqrt(g["var"]), 1).tolist(),
        "hz": np.round(hz.fillna(0), 2).tolist(), "hq": [float(f"{x:.2g}") for x in hq],
        "hp": [float(f"{x:.2g}") for x in hp], "mp": [float(f"{x:.2g}") for x in mp], "mq": [float(f"{x:.2g}") for x in mq],
        "n": g.n.astype(int).tolist(), "pos": g.pos.astype(int).tolist(), "epos": np.round(g.epos, 1).tolist(),
        "pct": np.round(pct.reindex(g.index).fillna(0.5), 4).tolist(),
        "games": games, "game": cfg.reindex(g.index).map({c: games.index(t) for c, t in cfg_theme.items()}).fillna(-1).astype(int).tolist(),
    })


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_site_data as b
    players(b.dump, b.r, b.MONTHS)
