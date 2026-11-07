"""Phases 1–4: train every model, validate, and turn the results into decisions.

Run from the repo root:  python analysis/run_models.py
Writes outputs/model_*.csv and friends; see analysis/models.md for the write-up.
"""
from __future__ import annotations

import sys
import time
import warnings

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

import causal  # noqa: E402
import downtime  # noqa: E402
import forecast  # noqa: E402
import machine_effects  # noqa: E402
from common import OUT, active_machine_days  # noqa: E402
from luck import bottom10_comparison, luck_engine, machine_luck  # noqa: E402

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 25)
JULY_MODEL = "OLS log (weekday+event+holiday)"  # best non-baseline on the holdout; has a holiday term for Jul 4


def iteration_scores() -> pd.DataFrame:
    """Approved iteration models vs B1/B2 on the holdout, with the harness's 7-origin CV and DM test."""
    sys.path.insert(0, str(OUT.parent / "analysis" / "experiments"))
    import harness
    from common import score, split_by_date
    tr, te = split_by_date(forecast.daily_frame())
    rows = []
    for name, f in forecast.ITERATIONS.items():
        for tgt in ["theo_usd", "coin_in_usd", "house_win_usd"]:
            p, b1, b2 = f(tr, te, tgt), forecast.m_b1(tr, te, tgt), forecast.m_b2(tr, te, tgt)
            y = te[tgt].to_numpy()
            s = score(y, p, ref_mae=np.mean(np.abs(b1 - y)))
            c = harness.cv(f, tgt)
            rows.append({"target": tgt, "model": name, "stack": "iteration", "phase": "iteration 1", **s,
                         "cv7_mae": c["cv_mae"], "cv7_mae_b2": c["cv_mae_b2"], "cv7_folds_won_vs_b2": c["folds_won"],
                         "skill_vs_B2": 1 - s["MAE"] / np.mean(np.abs(b2 - y)), "dm_p_vs_B2": harness.dm_test(p - y, b2 - y)})
    return pd.DataFrame(rows)


def classify(b10: pd.DataFrame, L: pd.DataFrame, fx: pd.DataFrame, f: pd.DataFrame, v: pd.DataFrame) -> pd.DataFrame:
    """Luck / Location / Leak / Downtime / Game / Exposure verdict for each of the GM's bottom 10."""
    L = L.set_index("machine_id")
    fx = fx.set_index("machine_id")
    days_total = v.gaming_date.nunique()
    fleet_down_share = v.downtime_hours.sum() / (v.available_hours.sum() + v.downtime_hours.sum())
    mach_down = v.groupby("machine_id").agg(down=("downtime_hours", "sum"), avail=("available_hours", "sum"))
    mach_down["down_share"] = mach_down.down / (mach_down.down + mach_down.avail)
    lost = (f.assign(lost=(f.wait_h + f.fix_h) * f.theo_per_down_h).groupby("machine_id").lost.sum())
    centre = (fx.bank_effect_log * 1).mean()  # average machine's location
    q25_bank = fx.bank_effect_log.quantile(0.25)
    edge = v.groupby("machine_id").theo_hold.first()
    fleet_edge = v.theo_usd.sum() / v.coin_in_usd.sum()
    rows = []
    for m in b10.machine_id:
        e = L.loc[m]
        x = fx.loc[m] if m in fx.index else None
        theo_day = e.theo_usd / e.days
        bank = x.bank_effect_log if x is not None else np.nan
        loc_uplift_day = theo_day * (np.exp(centre - bank) - 1) if x is not None else np.nan
        tags, evidence = [], []
        if e.hit_q_bh < 0.05:
            tags.append("Leak")
            evidence.append(f"hit-rate z {e.hit_z:+.0f} (BH q {e.hit_q_bh:.1g}); hold {e.observed_hold:.1%} vs theo {e.theo_hold:.0%}, "
                            f"outside 99% band; deficit spread over many days (worst day {e.jackpot_share_of_deficit:.0%})")
        # location vs game is only identified if this title also plays in other zones
        # (Platinum Reels is high-limit only, so its bank effect and game effect are the same thing)
        separable = v[v.theme == e.theme].zone_name.nunique() > 1
        if x is not None and bank <= q25_bank and separable:
            tags.append("Location")
            evidence.append(f"bank effect {np.expm1(bank - centre):+.0%} vs average spot (≈ +${loc_uplift_day:,.0f} theo/day at an average spot)")
        if edge[m] < fleet_edge - 0.02:
            tags.append("Low-edge game")
            evidence.append(f"configured hold {edge[m]:.0%} vs fleet {fleet_edge:.1%}")
        if e.days < 150:
            tags.append("Short exposure")
            evidence.append(f"on floor {e.days} of {days_total} days")
        if "Leak" not in tags and (e.luck_z < -2 or (e.luck_z < -1 and e.jackpot_share_of_deficit > 0.8)):
            tags.append("Luck")
            evidence.append(f"luck ${e.luck_usd:,.0f} (z {e.luck_z:.1f}, BH q {e.luck_q_bh:.2f}); worst day = "
                            f"{e.jackpot_share_of_deficit:.0%} of deficit")
        if mach_down.loc[m, "down_share"] > 2 * fleet_down_share:
            tags.append("Downtime")
            evidence.append(f"down {mach_down.loc[m, 'down_share']:.1%} of hours vs fleet {fleet_down_share:.1%}; lost theo ${lost.get(m, 0):,.0f}")
        machine_bad = x is not None and bool(x.credibly_negative)
        evidence.append("machine effect " + (f"{x.effect_pct:+.1%} (90% {np.expm1(x.effect_lo):+.1%} to {np.expm1(x.effect_hi):+.1%})"
                                             if x is not None and pd.notna(x.effect) else "n/a (installed after Apr 30)"))
        if "Leak" in tags:
            action = "A-INSPECT (paytable verification) before any replacement"
        elif tags and tags[0] == "Short exposure" and len(tags) == 1:
            action = "Keep: earns well per hour; low total is time on floor"
        elif machine_bad:
            action = "Replacement candidate (credibly weak machine)"
        else:
            action = "Don't replace like-for-like: the spot and the game explain it (see swap/move options)"
        rows.append({"machine_id": m, "zone": e.zone_name, "theme": e.theme, "days": e.days, "house_win_usd": e.house_win_usd,
                     "theo_usd": e.theo_usd, "theo_per_day": theo_day, "theo_per_avail_hr": e.theo_per_avail_hr,
                     "luck_usd": e.luck_usd, "luck_z": e.luck_z, "hit_z": e.hit_z,
                     "machine_effect_pct": x.effect_pct if x is not None else np.nan,
                     "machine_effect_credibly_negative": machine_bad,
                     "location_uplift_theo_per_day": loc_uplift_day, "lost_theo_downtime": lost.get(m, 0.0),
                     "verdict": " + ".join(tags) if tags else "Mixed", "recommended_action": action,
                     "evidence": " | ".join(evidence)})
    return pd.DataFrame(rows)


def main():
    t0 = time.time()
    OUT.mkdir(exist_ok=True)
    v = active_machine_days()

    # ---------------- Phase 1: luck engine
    luck = machine_luck(v)
    L, linfo = luck_engine(v, luck)
    L.to_csv(OUT / "model_luck_engine.csv", index=False)
    b10 = bottom10_comparison(luck)
    print(f"[1] luck: BH flags luck={linfo['luck_flags_bh']} hit={linfo['hit_flags_bh']} | raw p<.05 {linfo['luck_flags_raw_p05']} "
          f"(≈{linfo['expected_false_luck_flags_raw']:.0f} by chance) | CUSUM alarms luck {linfo['cusum_luck_alarms']}, "
          f"hit {linfo['cusum_hit_alarms']} vs ≈{linfo['cusum_alarms_expected_null']:.1f} under fair play")

    # ---------------- Phase 2: forecasts
    comp, preds = [], []
    for tgt in ["theo_usd", "coin_in_usd", "house_win_usd"]:
        res, out, chosen, ens = forecast.evaluate(tgt)
        res["cv_choice"] = res.model == chosen
        comp.append(res)
        preds.append(out.assign(target=tgt))
        print(f"[2] {tgt}: CV picks '{chosen}' (holdout MAE {res.loc[res.model == chosen, 'MAE'].iat[0]:,.0f}); "
              f"best holdout '{res.iloc[0].model}' {res.iloc[0].MAE:,.0f}; B1 {res.loc[res.model == 'B1 weekday mean', 'MAE'].iat[0]:,.0f}")
    fc = pd.concat(comp, ignore_index=True)
    pd.concat(preds, ignore_index=True).to_csv(OUT / "model_forecast_holdout_predictions.csv", index=False)
    jul = forecast.july_counterfactual(JULY_MODEL)
    jul.to_csv(OUT / "model_july_theo_counterfactual.csv", index=False)
    mde_prop = forecast.detectable_lift(JULY_MODEL)

    # ---------------- Phase 3: machine effects
    tab, mscores, swaps, minfo = machine_effects.run(v, b10.machine_id.tolist())
    tab.to_csv(OUT / "model_machine_effects.csv", index=False)
    swaps.to_csv(OUT / "model_swap_simulation.csv", index=False)
    print(f"[3] machine model: τ(machine) {minfo['tau_machine_glm']:.1%}; persistence ρ {minfo['persistence']['GLM+EB']:.2f}; "
          f"credibly negative machines {minfo['n_credibly_negative']}; SHAP {minfo['shap_shares'].round(2).to_dict()}")

    # ---------------- Phase 4: causal + downtime
    cz = causal.run(v)
    cz["event_study"].to_csv(OUT / "model_closure_event_study.csv", index=False)
    cz["structural_daily"].to_csv(OUT / "model_closure_counterfactual_daily.csv", index=False)
    cz["placebo"].to_csv(OUT / "model_closure_placebo.csv", index=False)
    d = cz["did"]
    print(f"[4a] closure: DiD {d['effect_closed_pct']:+.1%} (90% {d['closed_lo90_pct']:+.1%}..{d['closed_hi90_pct']:+.1%}); "
          f"structural {cz['structural']['avg_effect_pct']:+.1%}; lost theo ${cz['structural']['lost_theo_usd_during_closure']:,.0f}; "
          f"after reopening {d['effect_reopened_pct']:+.1%}; pre-trend p {d['pretrend_p']:.2f}")
    dt = downtime.run(v)
    dt["tech_scenarios"].to_csv(OUT / "model_tech_scenarios.csv", index=False)
    dt["preventive"].to_csv(OUT / "model_preventive_breakeven.csv", index=False)
    dt["fault_irr"].to_csv(OUT / "model_fault_rate_ratios.csv")
    dt["wait_by_hour"].to_csv(OUT / "model_fault_wait_by_hour.csv", index=False)
    print(f"[4b] faults: Ridgeline ×{dt['fault_irr'].loc['C(manufacturer)[T.Ridgeline]', 'rate_ratio']:.1f} vs Halcyon; "
          f"queue replay mean wait {dt['queue_info']['sim_mean_wait_h']:.2f} h vs actual {dt['queue_info']['actual_mean_wait_h']:.2f} h")

    # ---------------- model comparison table
    mc = pd.concat([fc.assign(phase="2 forecast"),
                    mscores.assign(phase="3 machine", stack=["lightweight", "lightweight", "ML", "ML"]),
                    dt["fault_scores"].assign(phase="4 faults", stack=["baseline", "baseline", "lightweight"])], ignore_index=True)
    p0 = pd.read_csv(OUT / "phase0_baseline_scores.csv") if (OUT / "phase0_baseline_scores.csv").exists() else None
    if p0 is not None:
        mc = pd.concat([mc, p0[p0.target.str.startswith("Machine-day")].assign(phase="3 machine", stack="baseline")], ignore_index=True)
    mc = pd.concat([mc, iteration_scores()], ignore_index=True)
    mc.to_csv(OUT / "model_comparison.csv", index=False)

    # ---------------- decisions
    cls = classify(b10, L, tab, dt["faults"], v)
    cls.to_csv(OUT / "model_bottom10_classification.csv", index=False)

    ridge_faults_30d = dt["preventive"].set_index("manufacturer").loc["Ridgeline", "faults_per_machine_month"] * \
        dt["preventive"].set_index("manufacturer").loc["Ridgeline", "machines"]
    ridge_hist = dt["preventive"].set_index("manufacturer").loc["Ridgeline", "faults"]
    se = np.sqrt(1 / ridge_faults_30d + 1 / ridge_hist)
    mp = pd.DataFrame([
        {"action": "Any floor-wide action", "metric": "daily property theo vs July counterfactual", "window_days": 30,
         "mde": mde_prop["mde_property_pct"], "note": f"resid SD {mde_prop['daily_resid_sd']:.1%}, lag-1 ρ {mde_prop['lag1_autocorr']:.2f}"},
        {"action": "A-WAYFINDING (Back Forty)", "metric": "B40 vs control-zone log coin-in/hr gap", "window_days": 30,
         "mde": cz["mde"]["mde_pct"], "note": f"break-even lift {7500 / (cz['b40_theo_per_day_after'] * 30):.1%} of B40 theo"},
        {"action": "A-PREVENTIVE (Ridgeline)", "metric": "Ridgeline fault rate vs Jan–Jun rate (Poisson)", "window_days": 30,
         "mde": -(1 - np.exp(-2.8 * se)), "note": f"break-even reduction {dt['preventive'].set_index('manufacturer').loc['Ridgeline', 'breakeven_fault_reduction']:.0%}"},
    ])
    mp.to_csv(OUT / "model_measurement_plan.csv", index=False)

    print("\nModel comparison — daily theo forecast (May–Jun holdout):")
    print(fc[fc.target == "theo_usd"][["model", "stack", "cv_mae_janapr", "MAE", "bias", "skill_vs_ref", "coverage"]].round(3).to_string(index=False))
    print("\nMachine coin-in per available hour (May–Jun):")
    print(mc[mc.phase == "3 machine"][["model", "MAE", "bias", "persistence_spearman"]].round(3).to_string(index=False))
    print("\nBottom-10 verdicts:")
    print(cls[["machine_id", "zone", "theme", "days", "theo_per_avail_hr", "machine_effect_pct", "location_uplift_theo_per_day",
               "verdict", "recommended_action"]].round(3).to_string(index=False))
    print("\nTech scenarios:\n", dt["tech_scenarios"].round(0).to_string(index=False))
    print("\nPreventive break-even:\n", dt["preventive"][["manufacturer", "faults_per_machine_month", "theo_plus_repair_per_30d",
                                                         "sweep_cost", "breakeven_fault_reduction"]].round(2).to_string(index=False))
    best_swap = swaps.sort_values("net_30d_after_lease", ascending=False).groupby("machine_id").head(1)
    print("\nBest title swap per machine (theo, parameter uncertainty only):\n",
          best_swap[["machine_id", "current_theme", "swap_to", "theo_gain_per_day", "net_30d_after_lease"]].round(0).to_string(index=False))
    print("\nMeasurement plan (MDE at 80% power, α=0.05):\n", mp.round(3).to_string(index=False))
    print(f"\nJuly theo counterfactual ({JULY_MODEL}): ${jul.forecast.sum():,.0f} over 30 days "
          f"(90% daily band ±{(jul.hi90 / jul.forecast - 1).mean():.1%}); June-anchored ${jul.forecast_level_adj.sum():,.0f} "
          f"(level ×{jul.level_adj.iat[0]:.3f})")
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
