"""Validate the change-impact estimators before using them on real changes.

1. Null: fake changes where nothing happened (random unit and dates, away from known changes).
   Honest 90% intervals should flag about 10% of them as Positive/Negative.
2. Injection: the same draws with a known effect multiplied in (−15%, +10%). We check the bias of the
   estimate, the 90% coverage, and the detection rate.
Usage: python impact_validate.py SEED [--calibrated]. Seed 7 fits the calibration (raw run); seed 11 confirms it.
Writes outputs/model_impact_validation_*.csv.
"""
import warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import impact
from common import OUT

import sys
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 7
CALIBRATED = "--calibrated" in sys.argv
impact.USE_CALIBRATION = CALIBRATED
rng = np.random.default_rng(SEED)
v = impact.daily_view()
CHANGED = {"M-1113", "M-1126", "M-1152", "M-1299", "M-1532", "M-5076"}
NEW = set(v[v.gaming_date < "2025-03-24"].machine_id) ^ set(v.machine_id)
zp = v.pivot_table(index="gaming_date", columns="zone_id", values="theo_usd", aggfunc="sum")
mp = v[~v.machine_id.isin(CHANGED | NEW)].pivot_table(index="gaming_date", columns="machine_id",
                                                     values="theo_usd", aggfunc="sum").fillna(0)
zone_of = v.drop_duplicates("machine_id").set_index("machine_id").zone_id
CLO = ("2025-03-03", "2025-04-06")
N = 150

rows = []
for rep in range(N):  # ---- on_off on zones (temporary changes)
    z = rng.choice(zp.columns)
    L = int(rng.choice([3, 7, 14, 28]))
    while True:
        s = pd.Timestamp("2025-01-15") + pd.Timedelta(days=int(rng.integers(0, 150 - L)))
        e = s + pd.Timedelta(days=L - 1)
        if not impact._mask(pd.date_range(s, e), [CLO]).any():
            break
    excl = [CLO] + ([("2025-03-24", "2025-04-06")] if z == "Z-PIT" else [])
    for f in (1.0, 0.85, 1.10):
        x = zp[z].copy()
        x[(x.index >= s) & (x.index <= e)] *= f
        est = impact.on_off(x, s, e, exclude=excl, step=3)
        rows.append({"estimator": "on_off (zone, temporary)", "true_log": np.log(f), "beta": est.beta,
                     "lo": est.lo, "hi": est.hi, "len": L})
for rep in range(N):  # ---- did on machines (permanent changes)
    m = rng.choice(mp.columns)
    s = pd.Timestamp("2025-02-15") + pd.Timedelta(days=int(rng.integers(0, 100)))
    e = min(s + pd.Timedelta(days=27), pd.Timestamp("2025-06-30"))
    pool = [c for c in mp.columns if zone_of[c] == zone_of[m] and c != m]
    others = list(rng.choice(pool, size=min(30, len(pool)), replace=False))
    ctrl_total = mp[pool].sum(axis=1)
    plac = {p: (mp[p], ctrl_total - mp[p]) for p in others}
    for f in (1.0, 0.85, 1.10):
        x = mp[m].copy()
        x[x.index >= s] *= f
        est = impact.did(x, ctrl_total, s, e, pre_days=56, placebo_units=plac)
        rows.append({"estimator": "did (machine, permanent)", "true_log": np.log(f), "beta": est.beta,
                     "lo": est.lo, "hi": est.hi, "len": 28})
r = pd.DataFrame(rows).dropna()
out = []
for (est, t), h in r.groupby(["estimator", "true_log"]):
    out.append({"estimator": est, "true_effect_pct": np.expm1(t), "n": len(h),
                "mean_estimate_pct": np.expm1(h.beta.mean()), "coverage_90": np.mean((h.lo <= t) & (t <= h.hi)),
                "flagged_share": np.mean((h.lo > 0) | (h.hi < 0)),
                "median_halfwidth_pct": np.expm1(np.median((h.hi - h.lo) / 2))})
by_len = r[(r.true_log == 0) & r.estimator.str.startswith("on_off")].groupby("len").apply(
    lambda h: pd.Series({"n": len(h), "false_flag": np.mean((h.lo > 0) | (h.hi < 0)),
                         "median_halfwidth_pct": np.expm1(np.median((h.hi - h.lo) / 2))}))
o = pd.DataFrame(out)
o.assign(seed=SEED, calibrated=CALIBRATED).to_csv(OUT / f"model_impact_validation{'_calibrated' if CALIBRATED else '_raw'}_seed{SEED}.csv", index=False)
pd.set_option("display.width", 200)
print(o.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
print(by_len.round(3))
