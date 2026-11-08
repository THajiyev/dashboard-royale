"""Recompute every headline claim on the dashboard from the raw tables, and check it against the site.

    python scripts/reproduce_claims.py          # prints each claim, PASS/FAIL, writes docs/data/claims.js
    python scripts/reproduce_claims.py --check  # same, but exits 1 if any claim fails (for CI)

Needs only pandas + pyarrow and the data/ folder. Each claim is computed here from data/ directly, with short,
readable code, NOT from outputs/ — so anyone can check a number without running the modelling pipeline.
The EL forecast, detectable effect, and adjusted fault ratio depend on saved model outputs; each says so in
`source` or `method`.

Every claim carries the fields the GUIDE asks for in the Claims & Evidence appendix:
    table/query -> result -> alternative explanation tested -> limitation
"""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA, OUT = ROOT / "data", ROOT / "outputs"
CLOSED = ("2025-03-03", "2025-04-06")          # walkway W-ENT-B40 closed (events / operations notes)


def rd(path: str, cols=None) -> pd.DataFrame:
    d = pd.read_parquet(DATA / f"{path}.parquet", columns=cols)
    for c in d.columns:          # money columns are stored as exact decimals; floats are fine for these checks
        if d[c].dtype == object and len(d) and type(d[c].dropna().iloc[0]).__name__ == "Decimal":
            d[c] = d[c].astype(float)
    return d


# ----------------------------------------------------------------------------- shared inputs
md = rd("2_machine_decision/machine_day")
md = md[md.active].copy()
md["gaming_date"] = pd.to_datetime(md.gaming_date)
v = rd("1_prepared_views/prepared_daily_view")
v = v[v.active & v.location_id.notna()].copy()
v["gaming_date"] = pd.to_datetime(v.gaming_date)
pdays = rd("1_prepared_views/property_day")
pdays["gaming_date"] = pd.to_datetime(pdays.gaming_date)
ev = rd("4_context/events")
on_event = pdays.gaming_date.apply(lambda d: bool(((ev.start_date.astype(str) <= d.strftime("%Y-%m-%d")) &
                                                   (ev.end_date.astype(str) >= d.strftime("%Y-%m-%d"))).any()))
pdays["event"] = on_event.to_numpy()

claims: list[dict] = []


class ClaimReferenceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        self.ids.update(value for key, value in attrs if key == "data-claim" and value)


def claim(cid, q, text, value, expected, tol, fmt, source, method, alternative, limitation, page, original=False):
    ok = abs(value - expected) <= tol
    claims.append({"id": cid, "q": q, "text": text, "value": float(value), "expected": float(expected), "tol": tol,
                   "fmt": fmt, "pass": bool(ok), "source": source, "method": method, "alternative": alternative,
                   "limitation": limitation, "page": page, "original": original})


# ============================================================================= Q1 machines
# C1: the GM's bottom 10 (GUIDE query: lowest total house win on active days) and where they sit
hw = md.groupby("machine_id").house_win_cents.sum().sort_values()
b10 = hw.head(10).index
zone = v.groupby(["machine_id", "zone_name"]).size().reset_index(name="n").sort_values("n").drop_duplicates("machine_id", keep="last") \
    .set_index("machine_id").zone_name
n_b40 = int((zone.reindex(b10) == "Back Forty").sum())
claim("C1", 1, "Nine of the GM's bottom 10 sit in Back Forty, the zone furthest from the entrances.", n_b40, 9, 0, "int",
      "machine_day (house_win_cents, active days) → bottom 10; prepared_daily_view.zone_name (zone on most days)",
      "SUM(house_win_cents) per machine, lowest 10; count those whose usual zone is Back Forty.",
      "That Back Forty simply holds weaker machines: the same machines' play fell 31% when the zone's walkway closed "
      "and recovered when it reopened (C3), so access, not the machines, sets their level.",
      "Zone is the one a machine spent most active days in; three machines moved during the period.", "machines.html#b10-h")

# C2: M-1158's payouts don't match its configuration
gm = rd("2_machine_decision/game_math").set_index("config_id")
m = md[md.machine_id == "M-1158"]
hold = m.house_win_cents.sum() / m.coin_in_cents.sum()
theo_hold = m.theo_cents.sum() / m.coin_in_cents.sum()
p = m.config_id.map(gm.hit_probability).astype(float)
hit_z = (m.payout_positive_spins.sum() - (m.paid_spins * p).sum()) / np.sqrt((m.paid_spins * p * (1 - p)).sum())
claim("C2", 1, "M-1158 held 3.0% of play against the 10% its configuration predicts, the only machine whose payouts "
      "don't match its settings.", hold * 100, 3.0, 0.1, "pct1",
      "machine_day (house_win, coin_in, theo, paid_spins, payout_positive_spins) + game_math.hit_probability",
      f"Observed hold = SUM(house_win)/SUM(coin_in); configured hold = SUM(theo)/SUM(coin_in) = {theo_hold:.1%}. "
      f"Win-rate z = (wins − Σ spins·p) / √Σ spins·p(1−p) = {hit_z:+.0f}.",
      "Luck: a fair high-volatility game can hold 3% for a while, but luck moves the size of wins, not how often a spin "
      f"pays. A win-rate z of {hit_z:+.0f} is not luck, and it survives Benjamini–Hochberg correction across 310 machines.",
      "An inspection lead, not proof of wrongdoing: a paytable, meter or configuration-record error would all look like this.",
      "machines.html#M-1158")

# C3: the walkway closure natural experiment (headline original finding)
zd = v.groupby(["gaming_date", "zone_id"]).agg(ci=("coin_in_usd", "sum"), hrs=("available_hours", "sum")).reset_index()
zd["lr"] = np.log(zd.ci / zd.hrs)
w = zd.pivot(index="gaming_date", columns="zone_id", values="lr")


def closure_effect(treated: str) -> float:
    controls = [z for z in w.columns if z not in ("Z-B40", "Z-HL", treated)]
    gap = w[treated] - w[controls].mean(axis=1)
    closed = (gap.index >= CLOSED[0]) & (gap.index <= CLOSED[1])
    reopened = gap.index > CLOSED[1]
    X = np.column_stack([np.ones(len(gap)), closed, reopened] +
                        [(gap.index.dayofweek == k) for k in range(1, 7)]).astype(float)
    beta = np.linalg.lstsq(X, gap.to_numpy(), rcond=None)[0]
    return float(np.expm1(beta[1]))


eff = closure_effect("Z-B40")
placebo = [closure_effect(z) for z in w.columns if z not in ("Z-B40", "Z-HL")]
claim("C3", 1, "Closing Back Forty's walkway from the main entrance (Mar 3 – Apr 6) cut its coin-in per available hour "
      "by 31% against the other zones, and it recovered on reopening.", eff * 100, -30.9, 0.5, "pct1",
      "prepared_daily_view (coin_in_usd, available_hours, zone_id) by gaming day",
      "Daily log(coin-in per available hour), Back Forty minus the mean of five control zones (High-Limit Room excluded), "
      "regressed on closed + reopened + weekday dummies (ordinary least squares, numpy).",
      f"That the whole floor slowed in March: running the same test with each control zone as the fake treated zone gives "
      f"{min(placebo):+.0%} to {max(placebo):+.0%}, nowhere near −31%.",
      "One closure, one zone. A mild pre-trend (−1.8% per 30 days, p = 0.08) is disclosed in the model write-up.",
      "context.html#cl-h", original=True)
claim("C4", 1, "Placebo check: the same closure test on zones that were not closed moves by only a few percent.",
      max(abs(x) for x in placebo) * 100, 3.3, 0.6, "pct1",
      "prepared_daily_view, as C3",
      "C3's regression with each control zone in turn as the treated zone; the largest absolute effect is reported.",
      "This is the competing-explanation test for C3.", "Five placebo zones is a small reference set.", "context.html#cl-h")
closure_rows = pd.read_csv(OUT / "model_change_impacts.csv")
closure_rows = closure_rows[
    (closure_rows.change == "Walkway W-ENT-B40 closed (Mar 3 – Apr 6)") &
    (closure_rows.part == "NET, measured directly (whole floor excl. new bank)")
]
if len(closure_rows) != 1:
    raise ValueError("Expected one whole-floor walkway-closure row in outputs/model_change_impacts.csv")
closure_row = closure_rows.iloc[0]
closure_source = "Model output: outputs/model_change_impacts.csv (whole-floor closure row)"
closure_method = ("Direct whole-floor on/off estimate over the closure, with placebo-based 90% interval; "
                  "see analysis/run_impact.py.")
closure_alternative = ("Back Forty’s lost play may have shifted to other zones, but this estimate does not establish "
                       "that players walked elsewhere.")
closure_limitation = "One 35-day closure; the 90% interval spans zero, so the floor-wide change is inconclusive."
claim("C23", 1, "The estimated whole-floor change during the walkway closure was +1.6%.",
      closure_row.effect_pct * 100, 1.6, 0.05, "pct1", closure_source, closure_method,
      closure_alternative, closure_limitation, "context.html#cl-h")
claim("C24", 1, "The 90% interval's lower bound for the whole-floor closure estimate was −0.2%.",
      closure_row.lo90_pct * 100, -0.2, 0.05, "pct1", closure_source, closure_method,
      closure_alternative, closure_limitation, "context.html#cl-h")
claim("C25", 1, "The 90% interval's upper bound for the whole-floor closure estimate was +3.4%.",
      closure_row.hi90_pct * 100, 3.4, 0.05, "pct1", closure_source, closure_method,
      closure_alternative, closure_limitation, "context.html#cl-h")

# ============================================================================= Q2 demand
wk = pdays[pdays.gaming_date <= "2025-04-30"].groupby(pdays.gaming_date.dt.dayofweek).theo_usd.mean()
ho = pdays[pdays.gaming_date >= "2025-05-01"].copy()
ho["B1"] = ho.gaming_date.dt.dayofweek.map(wk)
b1_mae = (ho.B1 - ho.theo_usd).abs().mean()
claim("C5", 2, "The weekday baseline B1 (Jan–Apr average theo per weekday) misses May–Jun daily theo by $6,699 a day.",
      b1_mae, 6699, 2, "usd",
      "property_day.theo_usd",
      "Mean of Jan 1 – Apr 30 theo for each weekday, applied to every May 1 – Jun 30 day; MAE = mean |B1 − actual|.",
      "A constant Jan–Apr mean (B0) is the cruder baseline: it misses by about $20.9K a day.",
      "One 61-day test window with one unusual event week.", "models.html#tab-h")
el = pd.read_csv(ROOT / "analysis/experiments/iter5/holdout_daily.csv", parse_dates=["gaming_date"])
el_mae = (el["EL event-type lift"] - el.actual).abs().mean()
claim("C6", 2, "The event-type lift forecast (EL), picked before May, cuts the daily miss to $4,290, about a third less than B1.",
      el_mae, 4290, 2, "usd",
      "Model output: analysis/experiments/iter5/holdout_daily.csv (EL frozen on Apr 30); actuals from property_day",
      "MAE of the frozen EL forecast over the same 61 days. The model is refit by analysis/experiments/ds_alpha/.",
      "Model shopping: EL was recorded as the pick before May was opened; four models scored after the fact beat it by "
      "0–2%, within noise, and are not claimed.",
      "Its 90% bands caught 75% of days, so they are too narrow.", "models.html#forest-h")
jun = ho[(ho.gaming_date.dt.month == 6) & ~ho.event]
b1_jun_bias = jun.B1.sum() / jun.theo_usd.sum() - 1
claim("C7", 2, "On June's ordinary days B1 over-forecast by 6.5%: demand fell, mostly among out-of-town visitors.",
      b1_jun_bias * 100, 6.5, 0.1, "pct1",
      "property_day.theo_usd, events (to drop event days)",
      "Σ B1 / Σ actual − 1 over June days with no event.",
      "Weather: ordinary heat has no measurable effect, and days of 40°C+ explain about 1 point of the shortfall at most "
      "(analysis/WEATHER_NOTE.md). Las Vegas visitation also ran below 2024 in June (LVCVA).",
      "The locals/visitors split relies on home_region, which covers carded play only.", "forecast.html#seg-h")
mde = pd.read_csv(OUT / "model_measurement_plan.csv").mde.iloc[0]
claim("C22", 2, "A floor-wide 30-day test can detect a change of about 4.7%.", mde * 100, 4.7, 0.1, "pct1",
      "Model output: outputs/model_measurement_plan.csv",
      "The 80%-power, 5%-significance minimum detectable effect for daily property theo over 30 days.",
      "The weekday baseline's June drift is larger than this threshold (C8).",
      "Assumes July's daily residual variability resembles May–Jun.", "forecast.html#meas-h")
claim("C8", 2, "That 6.5% gap is larger than the 4.7% floor-wide effect a 30-day test can detect, so judging July "
      "against weekday norms would make a no-action month look like a failed plan.", (b1_jun_bias - mde) * 100, 1.9, 0.15, "pp",
      "C7, and model output outputs/model_measurement_plan.csv (detectable effect at 80% power, α = 0.05)",
      "Gap minus detectable effect, in percentage points. Positive = B1's drift alone would register as an effect.",
      "That the drift is a one-off: the June-anchored July forecast (×0.959) is the yardstick used instead, and "
      "zone-level actions are judged against control zones, which share any floor-wide drift.",
      "The detectable effect assumes July's day-to-day noise matches May–Jun.", "forecast.html#dec-h", original=True)
edc = ho[(ho.gaming_date >= "2025-05-16") & (ho.gaming_date <= "2025-05-18")]
claim("C9", 2, "B1 under-forecast EDC festival weekend by 9%; an event-aware forecast would have planned for it.",
      (edc.B1.sum() / edc.theo_usd.sum() - 1) * 100, -9.5, 0.2, "pct1",
      "property_day.theo_usd, events (EV-EDC25, announced May 2024)",
      "Σ B1 / Σ actual − 1 over May 16–18.",
      "That EDC weekend was just a strong weekend: EL's lift for festivals and sports (+17–20%) was learned from Jan–Apr "
      "events, and it landed within 2% of actual.", "One festival weekend in the test.", "forecast.html#dec-h")

# ============================================================================= Q3 downtime
down_h = (md.scheduled_seconds - md.available_seconds).sum() / 3600
claim("C10", 3, "Machines were down 5,021 hours in six months, 0.4% of scheduled time; 98% of it was fault repairs.",
      down_h, 5021, 1, "int",
      "machine_day (scheduled_seconds − available_seconds, active days); operations.event_type",
      "Sum of scheduled minus available seconds over active machine-days, in hours.",
      "That downtime explains the bottom 10: Back Forty had the fewest fault hours of the main zones (downtime page).",
      "Down hours from meters; a machine that is up but unattractive is not counted.", "downtime.html")
op = rd("2_machine_decision/operations")
f = op[op.event_type == "fault_repair"].copy()
f["wait"] = (f.work_started_at_utc - f.opened_at_utc).dt.total_seconds() / 3600
f["fix"] = (f.available_at_utc - f.work_started_at_utc).dt.total_seconds() / 3600
claim("C11", 3, "A fault takes 2.9 hours to fix but only 1.1 hours to reach, so another technician can't recover much.",
      f.fix.mean() / f.wait.mean(), 2.58, 0.05, "x",
      "operations (fault_repair: opened_at, work_started_at, available_at)",
      "Mean fix time ÷ mean wait time over 1,207 faults.",
      "That waits are long on some shifts: they are (grave 2.0 h vs about 0.9 h), and the repair-queue replay that adds "
      "a technician to each shift still saves only $1.8–2.8K of theo per 30 days against $11,520.",
      "The replay assumes fix times don't change with staffing.", "downtime.html")
mach = rd("2_machine_decision/machines").set_index("machine_id")
days = md.groupby(md.machine_id.map(mach.manufacturer)).size()
fa = f.groupby(f.machine_id.map(mach.manufacturer)).size()
raw_ratio = (fa["Ridgeline"] / days["Ridgeline"]) / (fa["Halcyon"] / days["Halcyon"])
claim("C12", 3, "Ridgeline machines fault about four times as often as Halcyon's.", raw_ratio, 3.64, 0.1, "x",
      "operations (fault_repair) + machines.manufacturer + machine_day (active days)",
      "Faults per active machine-day, Ridgeline ÷ Halcyon. The model-adjusted ratio (negative binomial, for age, "
      "volatility and occupancy) is 4.2× (95% CI 3.5–5.1).",
      "That Ridgeline machines are just older or busier: the adjusted model controls for both and the ratio grows.",
      "No record of what a maintenance sweep does, so the 40% cut used on the Actions page is an assumption.",
      "downtime.html")

# ============================================================================= Q4 players
claim("C13", 4, "Loyalty-card play is two thirds of all coin-in.",
      md.carded_coin_in_cents.sum() / md.coin_in_cents.sum() * 100, 66, 0.6, "pct0",
      "machine_day (carded_coin_in_cents, coin_in_cents)",
      "SUM(carded coin-in) / SUM(coin-in), Jan–Jun.",
      "That player tables are broken because they don't match machine totals: they only see carded play, by design.",
      "Everything on the Players page describes this two thirds, not all guests.", "players.html")
pp = rd("1_prepared_views/player_period")
net = pp.groupby("player_id").apply(lambda g: g.tracked_payout_usd.sum() - g.tracked_coin_in_usd.sum(), include_groups=False)
loss = np.sort(-net[net < 0].to_numpy())[::-1]
top10 = loss[: max(1, int(round(len(loss) * 0.10)))].sum() / loss.sum()
claim("C14", 4, "Losses are concentrated: the 10% of losing players who lost most account for about half of all losses.",
      top10 * 100, 53, 1, "pct0",
      "player_period (tracked_payout_usd − tracked_coin_in_usd per player, Jan–Jun)",
      "Players who finished down, sorted by loss; share of total losses held by the top 10%.",
      "That a few players were just unlucky: expected losses (theo) are even more concentrated, so it is volume of play, "
      "not luck, that concentrates results (Players page).",
      "Shown to describe outcomes, not to target anyone; carded play only.", "players.html#lor-h")

# ============================================================================= Q5 comps
led = rd("3_guests/loyalty_ledger", ["event_type", "event_at_utc", "points_delta", "face_value_cents", "tier_before"])
red = led[(led.event_type == "redeem") & (led.tier_before == "Base")].copy()
red["ppd"] = -red.points_delta / (red.face_value_cents / 100)
after = pd.to_datetime(red.event_at_utc) >= pd.Timestamp("2025-05-01 13:00")      # 6 a.m. Pacific = 13:00 UTC
cut = red[after].ppd.median() / red[~after].ppd.median() - 1
claim("C15", 5, "On May 1 every comp started costing about half as many points (−53%), at every tier.", cut * 100, -53, 1.5, "pct0",
      "loyalty_ledger (redeem events: points_delta, face_value_cents, tier_before)",
      "Median points per $1 of comp face value, Base tier, before vs after the May 1 gaming day.",
      "A menu change: the same items kept the same face values; only the points price moved (15 → 7 per $1 × tier).",
      "Applies to every card holder at once, so there is no untouched group; C17 and C18 read its effect from cost and "
      "from comp users against all locals.", "comps.html#may-h")
pp["m"] = pp.period_month.astype(str).str[:7]
late = pp[pp.m >= "2025-05"]
early = pp[pp.m < "2025-05"]
claim("C16", 5, "Since the May 1 price cut, comps cost the casino about $33K a month, 1.3% of tracked theo "
      "(Jan–Apr: $30.8K, 1.2%).", late.comp_cost_usd.sum() / 2, 33709, 50, "usd",
      "player_period.comp_cost_usd (economic cost, not menu price), theo_usd",
      f"SUM(comp_cost_usd) / 2 months for May–Jun; share of SUM(theo_usd) = {late.comp_cost_usd.sum() / late.theo_usd.sum():.1%}. "
      f"Jan–Apr: ${early.comp_cost_usd.sum() / 4:,.0f} a month, {early.comp_cost_usd.sum() / early.theo_usd.sum():.1%}.",
      "That comp cost rose because guests played more: theo fell in May–Jun while comp cost rose, so cost per dollar of "
      "play went up. Counting menu price instead of cost would overstate it about fourfold.",
      "Carded guests only; two months after the change.", "comps.html#ba-h")
claim("C17", 5, "That is 9% more than before the cut, about $2,900 a month.",
      (late.comp_cost_usd.sum() / 2) / (early.comp_cost_usd.sum() / 4) * 100 - 100, 9.4, 0.2, "pct1",
      "player_period.comp_cost_usd", "May–Jun monthly comp cost ÷ Jan–Apr monthly comp cost − 1.",
      "That more guests simply came: the share of locals who redeem stayed at 68–69%, and play fell.",
      "Two months; the seasonal comparison is Jan–Apr.", "comps.html#ba-h")
loc = pp[pp.home_region == "Local"]
redeemers = set(pp[(pp.m < "2025-05") & (pp.comps_redeemed > 0)].player_id)


def change(d):
    return d[d.m >= "2025-05"].theo_usd.sum() / d[d.m.isin(["2025-03", "2025-04"])].theo_usd.sum() - 1


chg_r, chg_l = change(loc[loc.player_id.isin(redeemers)]), change(loc)
claim("C18", 5, "The cut didn't bring in play: locals who already used comps played 2.5% less in May–Jun than in Mar–Apr, "
      "while locals overall played 1.2% less.", chg_r * 100, -2.5, 0.1, "pct1",
      "player_period (theo_usd, home_region, comps_redeemed)",
      f"Theo May–Jun ÷ theo Mar–Apr − 1 for locals who redeemed in Jan–Apr ({chg_r:+.1%}) and for all locals ({chg_l:+.1%}).",
      "A comparison with locals who had never redeemed showed a −19% gap, but it failed its placebo test (−13% before May) "
      "because that group was picked for being active in Mar–Apr, so it isn't used.",
      "Locals only, where comp use is common; visitors rarely come back within the window.", "comps.html")

# ============================================================================= Q6 actions
cat = rd("2_machine_decision/action_catalog").set_index("action_type_id")
plan = {"A-PROMO": 2, "A-MOVE-MACHINE": 6, "A-WAYFINDING": 1}
cost = sum(n * (cat.loc[a, "unit_cost_cents"] + cat.loc[a, "recurring_cost_cents_per_day"] * max(0, 30 - cat.loc[a, "lead_days"])) / 100
           for a, n in plan.items())
claim("C19", 6, "The plan funds two promotion weekends, 6 machine moves and new signs for Back Forty for $48,300, and keeps $51,700.",
      cost, 48300, 0, "usd",
      "action_catalog (unit_cost_cents, recurring_cost_cents_per_day, lead_days)",
      "GUIDE formula: quantity × (unit cost + daily cost × max(0, 30 − lead days)) / 100, summed. The plan is the best of every "
      "plan the catalogue allows at central assumptions (assets/benefits.js); the 6 moves are the location model's best (assets/moves.js).",
      "Replacing the bottom 10 instead: the one like-for-like replacement in the data moved theo by +$4 a day (−$17 to +$23). "
      "The one real move in the data matched its projection (+$303 predicted, +$342 a day measured).",
      "Moves leave out bank B-51, whose effect belongs to its new machines. Beyond $48,300 no plan returns more in July.", "actions.html")
sc = pd.read_csv(ROOT / "outputs/model_change_scorecard.csv")
promo = sc[sc.change.str.startswith("Property promotion")].set_index("days")
claim("C21", 6, "The two promotions in the data lifted floor theo by $8.4K a day (Locals Week) and $26.1K a day (Winter Slot Tournament).",
      promo.loc[3, "theo_usd_per_day"], 26146, 1, "usd",
      "Model output: outputs/model_change_scorecard.csv (analysis/impact.py, calibrated on 150 planted fake changes)",
      "Whole-floor theo on promotion days against the floor's expected level, with 90% intervals: tournament "
      f"${promo.loc[3, 'lo90_usd_day']:,.0f}–${promo.loc[3, 'hi90_usd_day']:,.0f} a day, Locals Week "
      f"${promo.loc[7, 'lo90_usd_day']:,.0f}–${promo.loc[7, 'hi90_usd_day']:,.0f}.",
      "That busy weekends lift anyway: the estimator controls for weekday, and its intervals were checked on planted fake changes.",
      "Two promotions only; the Actions page carries their full range into the plan's pessimistic and optimistic cases.", "actions.html#ben-h")
b40 = v[(v.zone_id == "Z-B40") & (v.gaming_date >= "2025-05-01")]
b40_day = b40.theo_usd.sum() / b40.gaming_date.nunique()
be = cat.loc["A-WAYFINDING", "unit_cost_cents"] / 100 / (b40_day * (30 - cat.loc["A-WAYFINDING", "lead_days"]))
claim("C20", 6, "New signs for Back Forty pay for themselves if they lift its play by about 2.8% over July's last 20 days.",
      be * 100, 2.8, 0.1, "pct1",
      "prepared_daily_view (Back Forty theo, May–Jun) + action_catalog (A-WAYFINDING: $7,500, 10-day lead)",
      "Break-even lift = $7,500 / (Back Forty theo per day × 20 days left after the lead).",
      "That access can't be improved by signs: the closure (C3) shows access matters; how much signs restore is the "
      "assumption, so the page shows the result at 0%, 5% and 10%.",
      "A 3.6% gap is the smallest a 30-day zone-vs-control test can detect, above break-even.", "actions.html#sens-h")


# ----------------------------------------------------------------------------- report
def show(c):
    x = c["value"]
    return {"int": f"{x:,.0f}", "usd": f"${x:,.0f}", "pct0": f"{x:.0f}%", "pct1": f"{x:.1f}%", "pp": f"{x:+.1f} pp",
            "x": f"{x:.2f}×"}[c["fmt"]]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    fails = 0
    for c in claims:
        fails += not c["pass"]
        print(f"{'PASS' if c['pass'] else 'FAIL'}  {c['id']:<4} Q{c['q']}  {show(c):>10}  (site: {c['expected']:g})  {c['text'][:80]}")
    for c in claims:
        c["shown"] = show(c)
    parser = ClaimReferenceParser()
    for path in (ROOT / "docs").rglob("*.html"):
        parser.feed(path.read_text(encoding="utf-8"))
    for path in (ROOT / "docs" / "assets").glob("*.js"):
        parser.ids.update(re.findall(r'data-claim="(C\d+)"', path.read_text(encoding="utf-8")))
    known = {c["id"] for c in claims}
    missing = sorted(parser.ids - known)
    for cid in missing:
        fails += 1
        print(f"FAIL  site reference {cid} is missing from the generated claim registry")
    dest = ROOT / "docs/data/claims.js"
    dest.write_text("(window.__DATA = window.__DATA || {})[\"claims\"] = " +
                    json.dumps({"claims": claims, "generated": pd.Timestamp.now().strftime("%Y-%m-%d")},
                               separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"\n{len(claims) - fails} of {len(claims)} claims reproduce; wrote {dest.relative_to(ROOT)}")
    return 1 if fails and "--check" in sys.argv else 0


if __name__ == "__main__":
    sys.exit(main())
