"""7-fold rolling-origin CV (harness origins, Jan–Apr only) for every iteration-2 candidate.
Writes cv_results.csv. Never touches May–Jun."""
import sys, time
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE))
import harness, forecast
from common import TRAIN_END
from models import CANDIDATES

df = harness.frame(); df = df[df.gaming_date <= TRAIN_END]
only = sys.argv[1:] or list(CANDIDATES)
rows = []
for target in ["theo_usd", "coin_in_usd"]:
    for o in harness.CV_ORIGINS:
        tr, fut, full = harness._split(df, o, TRAIN_END)
        y = full[target].to_numpy()
        ref = {"B2": harness._run(forecast.m_b2, tr, fut, target)}
        for name in only:
            t0 = time.time()
            p = harness._run(CANDIDATES[name], tr, fut, target)
            rows.append({"target": target, "origin": o.date(), "model": name, "mae": np.mean(np.abs(p - y)),
                         "mae_b2": np.mean(np.abs(ref["B2"] - y)), "sec": time.time() - t0})
r = pd.DataFrame(rows)
el = r[r.model == "EL (iteration 1, current best)"].set_index(["target", "origin"]).mae
r["mae_el"] = [el.get((t, o), np.nan) for t, o in zip(r.target, r.origin)]
r.to_csv(HERE / "cv_folds.csv", index=False)
s = r.groupby(["target", "model"]).apply(lambda g: pd.Series({
    "cv_mae": g.mae.mean(), "skill_vs_el": 1 - g.mae.mean() / g.mae_el.mean(),
    "skill_vs_b2": 1 - g.mae.mean() / g.mae_b2.mean(), "folds_won_vs_el": int((g.mae < g.mae_el - 1e-6).sum()),
    "sec_per_fit": g.sec.mean()})).reset_index()
s.to_csv(HERE / "cv_results.csv", index=False)
pd.set_option("display.width", 200)
print(s.sort_values(["target", "cv_mae"]).to_string(index=False, float_format=lambda x: f"{x:,.3f}"))
