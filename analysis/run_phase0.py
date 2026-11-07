"""Phase 0: most-basic baselines. Run from the repo root:  python analysis/run_phase0.py"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from scipy import stats

from baselines import downtime_baseline, downtime_hourly, location_baseline, property_forecast_baselines
from common import OUT, active_machine_days, property_day
from luck import bottom10_comparison, machine_luck

sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252 and crash on ⇒ / −
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)


def main():
    OUT.mkdir(exist_ok=True)
    pdays = property_day()
    v = active_machine_days()

    # sanity: machine-level totals reconcile with property_day; luck z is ~N(0,1) per machine-day
    assert abs(v.theo_usd.sum() - pdays.theo_usd.sum()) < 1, "theo does not reconcile"
    assert abs(v.house_win_usd.sum() - pdays.house_win_usd.sum()) < 1, "house win does not reconcile"
    played = v[v.paid_spins > 0]
    z = (played.house_win_cents - played.theo_cents.astype(float)) / np.sqrt(played.win_var_cents2)
    print(f"machine-day luck z: mean {z.mean():.3f}, sd {z.std():.3f}, skew {stats.skew(z):.2f}, median {z.median():.2f}"
          "  (mean/sd ≈ 0/1, but strongly skewed: don't read daily z against normal tails)")

    fc_scores, fc_preds = property_forecast_baselines(pdays)
    loc_scores, loc_table = location_baseline(v)
    scores = pd.concat([fc_scores, loc_scores], ignore_index=True)
    scores.to_csv(OUT / "phase0_baseline_scores.csv", index=False)
    fc_preds.to_csv(OUT / "phase0_property_predictions.csv", index=False)

    luck = machine_luck(v)
    luck.to_csv(OUT / "phase0_machine_luck.csv", index=False)
    b10 = bottom10_comparison(luck)
    b10.to_csv(OUT / "phase0_bottom10.csv", index=False)
    loc_table.to_csv(OUT / "phase0_location_ratio.csv", index=False)
    down = downtime_hourly(v, downtime_baseline(v))
    down.to_csv(OUT / "phase0_downtime_lost_play.csv", index=False)

    print("\nHoldout scores (May–Jun), lower MAE is better:")
    print(scores[["target", "model", "MAE", "RMSE", "MAPE", "bias", "skill_vs_B0", "skill_vs_B1"]].round(3).to_string(index=False))
    n_out, n = (luck.luck_z.abs() > 2).sum(), len(luck)
    print(f"\nMachines with |luck z| > 2: {n_out} of {n} (≈{0.0455 * n:.0f} expected by chance; "
          f"binomial p = {stats.binom.sf(n_out - 1, n, 0.0455):.2f})")
    print("\nGM's bottom 10 by house win:")
    print(b10[["machine_id", "zone_name", "theme", "days", "house_win_usd", "theo_per_avail_hr", "luck_z", "hit_z",
               "rank_by_theo_per_hr", "basic_read"]].round(2).to_string(index=False))
    print(f"\nLost play from downtime: flat-rate theo {down.lost_theo_usd.sum():,.0f} USD, "
          f"hour-aware theo {down.lost_theo_hourly_usd.sum():,.0f} USD "
          f"(coin-in {down.lost_coin_in_usd.sum():,.0f} → {down.lost_coin_in_hourly_usd.sum():,.0f})")
    print(down.groupby("manufacturer")[["down_h", "lost_theo_usd", "lost_theo_hourly_usd"]].sum().round(0))


if __name__ == "__main__":
    main()
