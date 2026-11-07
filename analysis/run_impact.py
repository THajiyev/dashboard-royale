"""Score every change in Jan–Jun 2025 with the change-impact model (impact.py).

Writes outputs/model_change_impacts.csv (one row per part: direct, spillover, NET) and
outputs/model_outage_recapture.csv. Validation is in impact_validate.py. Run that first if impact.py changes.
"""
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

import impact
from common import OUT, load

rng = np.random.default_rng(3)
v = impact.daily_view()
loc = load("2_machine_decision/floor_locations.parquet").set_index("location_id")
bank_of_loc = {l: p for l, p in zip(loc.index, loc.parent_location_id)}
zone_of_bank = loc[loc.node_type == "bank"].zone_id.to_dict()
NEW = sorted(set(v[v.gaming_date >= "2025-03-24"].machine_id) - set(v[v.gaming_date < "2025-03-24"].machine_id))
NEW_PIT = [m for m in NEW if v[v.machine_id == m].bank_id.iloc[0] == "B-51"]
CLO = (pd.Timestamp("2025-03-03"), pd.Timestamp("2025-04-06"))
END = pd.Timestamp("2025-06-30")
THEO, CI = "theo_usd", "coin_in_usd"

# pivots: machine-day and location-day (a slot keeps its series across a replacement)
MP = {m: v.pivot_table(index="gaming_date", columns="machine_id", values=m, aggfunc="sum").fillna(0) for m in (THEO, CI)}
LP = {m: v.pivot_table(index="gaming_date", columns="location_id", values=m, aggfunc="sum") for m in (THEO, CI)}
bank_machines = v.groupby("bank_id").machine_id.unique().to_dict()
machine_bank = v.sort_values("gaming_date").groupby("machine_id").bank_id.last().to_dict()
rows = []


def S(machines, metric=THEO):
    return MP[metric][list(machines)].sum(axis=1)


def zones(*z, metric=THEO):
    return S(v[v.zone_id.isin(z)].machine_id.unique(), metric)


def bank_placebos(exclude_banks, k_banks, metric, n=80):
    """Random groups of k whole banks (not involved) as pseudo-treated; control = all other uninvolved machines."""
    pool = [b for b in bank_machines if b not in exclude_banks and b != "B-51"]
    allm = [m for b in pool for m in bank_machines[b] if m not in NEW]
    tot = S(allm, metric)
    out = {}
    for i in range(n):
        g = rng.choice(pool, size=k_banks, replace=False)
        gm = [m for b in g for m in bank_machines[b] if m not in NEW]
        out[i] = (S(gm, metric), tot - S(gm, metric))
    return out


def machine_placebos(exclude_machines, metric, n=60):
    pool = [m for m in MP[metric].columns if m not in exclude_machines and m not in NEW]
    tot = S(pool, metric)
    pick = rng.choice(pool, size=n, replace=False)
    return {m: (MP[metric][m], tot - MP[metric][m]) for m in pick}, tot


# ============================================================== 1. walkway closure (temporary)
def closure(cannib_beta):
    name = "Walkway W-ENT-B40 closed (Mar 3 – Apr 6)"
    b40 = zones("Z-B40")
    rest5 = zones("Z-BAR", "Z-ENT", "Z-GAR", "Z-HL", "Z-HTL")
    pit_old = S([m for m in v[v.zone_id == "Z-PIT"].machine_id.unique() if m not in NEW_PIT])
    pit_old = pit_old.where(pit_old.index < "2025-03-24", pit_old / np.exp(cannib_beta))  # undo cannibalization
    parts = []
    for part, s, note in [("Direct: Back Forty", b40, ""),
                          ("Spillover: 5 other zones", rest5, ""),
                          ("Spillover: Pit (existing machines)", pit_old,
                           "post-Mar 24 values corrected for the new bank's cannibalization (section 2)")]:
        e = impact.on_off(s, *CLO, baseline_days=28)
        parts.append(impact.row(name, part, e, "on_off", note))
    rows.extend(parts)
    rows.append(impact.net_row(name, parts, 35, "sum of parts"))
    e = impact.on_off(b40 + rest5 + pit_old, *CLO, baseline_days=28)
    r = impact.row(name, "NET, measured directly (whole floor excl. new bank)", e, "on_off")
    r["theo_usd_total"] = r["theo_usd_per_day"] * 35
    rows.append(r)


# ============================================================== 2. new bank B-51 in the Pit (permanent)
def pit_expansion():
    name = "8 new machines, bank B-51 (Pit, Mar 24)"
    start = pd.Timestamp("2025-04-07")  # after the closure, so it can't confound
    pit_old_m = [m for m in v[v.zone_id == "Z-PIT"].machine_id.unique() if m not in NEW_PIT]
    ctrl_z = ["Z-BAR", "Z-ENT", "Z-GAR", "Z-HL", "Z-HTL"]
    out = {}
    for metric in (THEO, CI):
        gross = S(NEW_PIT, metric)[start:END]
        e = impact.did(S(pit_old_m, metric), zones(*ctrl_z, metric=metric), start, END, pre_days=96,
                       exclude=[CLO], placebo_units=bank_placebos(
                           [b for b in bank_machines if zone_of_bank.get(b) in ("Z-PIT", "Z-B40")], 6, metric))
        out[metric] = (gross.mean(), e)
    g, e = out[THEO]
    lvl = g  # gross is measured, not estimated: no interval
    rows.append({"change": name, "part": "Direct: new machines' own theo", "method": "measured",
                 "theo_usd_per_day": g, "lo90_usd_day": g, "hi90_usd_day": g, "verdict": "Positive", "days": 85})
    r = impact.row(name, "Spillover: existing Pit machines (cannibalization)", e, "did",
                   f"coin-in effect {out[CI][1].pct:+.1%}")
    rows.append(r)
    net = g + r["theo_usd_per_day"]
    hw = (r["hi90_usd_day"] - r["lo90_usd_day"]) / 2
    rows.append({"change": name, "part": "NET (direct + spillover)", "method": "sum of parts", "theo_usd_per_day": net,
                 "lo90_usd_day": net - hw, "hi90_usd_day": net + hw,
                 "verdict": "Positive" if net - hw > 0 else "Negative" if net + hw < 0 else "Inconclusive",
                 "days": 85, "theo_usd_total": net * 85, "lo90_usd_total": (net - hw) * 85, "hi90_usd_total": (net + hw) * 85,
                 "note": f"cannibalization = {-r['theo_usd_per_day'] / g:.0%} of the new machines' theo"})
    return e.beta


# ============================================================== 3. machine moves (same game, to an empty slot)
MOVES = [("M-1152", "2025-02-04", "L-33-4", "L-03-7"), ("M-1113", "2025-02-18", "L-12-1", "L-09-7"),
         ("M-1126", "2025-05-06", "L-40-6", "L-21-7"), ("M-1299", "2025-06-10", "L-07-3", "L-44-7")]


def moves():
    for m, d, a, b in MOVES:
        ob, nb = bank_of_loc[a], bank_of_loc[b]
        name = f"Move {m}: {a} ({zone_of_bank[ob]}) → {b} ({zone_of_bank[nb]}), {d}"
        start = pd.Timestamp(d)
        end = min(start + pd.Timedelta(days=55 + (35 if start < CLO[0] else 0)), END)  # 8 post weeks net of closure
        involved = set(bank_machines[ob]) | set(bank_machines[nb]) | {m}
        parts = []
        for metric in (THEO, CI):
            plac, tot = machine_placebos(involved, metric)
            e = impact.did(MP[metric][m], tot, start, end, pre_days=56, placebo_units=plac, exclude=[CLO])
            if metric == CI:
                ci_note = f"coin-in effect {e.pct:+.1%} [{np.expm1(e.lo):+.0%}, {np.expm1(e.hi):+.0%}]"
            else:
                e_theo = e
        parts.append(impact.row(name, "Direct: the moved machine", e_theo, "did", ci_note))
        bp = bank_placebos({ob, nb}, 1, THEO)
        ctrl = S([x for x in MP[THEO].columns if x not in involved and x not in NEW])
        for part, bk in [("Spillover: old bank-mates", ob), ("Spillover: new bank-mates", nb)]:
            mates = [x for x in bank_machines[bk] if x != m]
            e = impact.did(S(mates), ctrl, start, end, pre_days=56, placebo_units=bp, exclude=[CLO])
            parts.append(impact.row(name, part, e, "did"))
        rows.extend(parts)
        rows.append(impact.net_row(name, parts, (end - start).days + 1))


# ============================================================== 4. replacements (slot keeps its series)
REPL = [("L-27-3", "2025-02-25", "M-1118 (G-HL90) → M-1532 (G-CLS93), new game"),
        ("L-38-5", "2025-05-13", "M-1120 → M-5076, like-for-like (G-VID95)")]


def replacements():
    for l, d, what in REPL:
        name = f"Replace at {l}: {what}, {d}"
        start = pd.Timestamp(d)
        end = min(start + pd.Timedelta(days=55 + (35 if start < CLO[0] else 0)), END)
        bk = bank_of_loc[l]
        locs_pool = [x for x in LP[THEO].columns if bank_of_loc.get(x) != bk and LP[THEO][x].notna().all()]
        for metric, label in ((THEO, "theo"), (CI, "coin-in (play)")):
            tot = LP[metric][locs_pool].sum(axis=1)
            pick = rng.choice(locs_pool, size=60, replace=False)
            plac = {x: (LP[metric][x], tot - LP[metric][x]) for x in pick}
            e = impact.did(LP[metric][l].fillna(0), tot, start, end, pre_days=56, placebo_units=plac, exclude=[CLO])
            rows.append(impact.row(name, f"Direct: the slot ({label})", e, "did"))


# ============================================================== 5. events and promotions (property level)
def events():
    ev = load("4_context/events.parquet")
    prop = S([m for m in MP[THEO].columns if m not in NEW])  # excl. new bank, so the Mar 24 step can't leak in
    for _, r in ev.sort_values("start_date").iterrows():
        s, e = pd.Timestamp(r.start_date), pd.Timestamp(r.end_date)
        est = impact.on_off(prop, s, e, baseline_days=14, window_is_event=True, step=1)
        kind = "Property promotion" if r.local_scope == "property" else "Citywide event"
        rows.append(impact.row(f"{kind}: {r['name']} ({s:%b %d}–{e:%b %d})", "Direct: whole floor", est, "on_off",
                               "inside the closure window" if (s <= CLO[1] and e >= CLO[0]) else ""))
        rows[-1]["theo_usd_total"] = rows[-1]["theo_usd_per_day"] * est.n_window


if __name__ == "__main__":
    cb = pit_expansion()
    closure(cb)
    moves()
    replacements()
    events()
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "model_change_impacts.csv", index=False)
    # scorecard: one headline row per change (NET where spillover was measured; whole floor for events;
    # for replacements, theo; for the closure, the directly measured net — summing parts double-counts shared noise)
    pick = []
    for ch, g in out.groupby("change", sort=False):
        pref = ["NET, measured directly (whole floor excl. new bank)", "NET (direct + spillover)", "Direct: whole floor",
                "Direct: the slot (theo)"]
        r = next(g[g.part == p].iloc[0] for p in pref if (g.part == p).any())
        pick.append(r)
    sc = pd.DataFrame(pick)[["change", "part", "theo_usd_per_day", "lo90_usd_day", "hi90_usd_day", "verdict", "days"]]
    sc["theo_usd_total"] = sc.theo_usd_per_day * sc.days
    sc["impact_score"] = sc.theo_usd_per_day / ((sc.hi90_usd_day - sc.lo90_usd_day) / 2) * 1.645  # z-like
    sc.to_csv(OUT / "model_change_scorecard.csv", index=False)
    rec = impact.outage_recapture()
    pd.DataFrame(rec).T.rename_axis("sample").to_csv(OUT / "model_outage_recapture.csv")
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 70)
    cols = ["change", "part", "effect_pct", "lo90_pct", "hi90_pct", "theo_usd_per_day", "lo90_usd_day",
            "hi90_usd_day", "verdict", "note"]
    print(out[cols].to_string(index=False, float_format=lambda x: f"{x:,.3f}" if abs(x) < 5 else f"{x:,.0f}"))
    print(rec)
    print(sc.to_string(index=False, float_format=lambda x: f"{x:,.1f}" if abs(x) < 10 else f"{x:,.0f}"))
