"""POST-HOC diagnostic: every candidate scored on May–Jun. Not a selection step — run after the 3
pre-registered submissions were logged. Writes posthoc_holdout.csv."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE))
import harness, forecast
from common import TRAIN_END
from models import CANDIDATES

df = harness.frame()
tr, fut, full = harness._split(df, TRAIN_END, pd.Timestamp("2025-06-30"))
cv = pd.read_csv(HERE / "cv_results_round1.csv")
cv = pd.concat([cv, pd.read_csv(HERE / "cv_results.csv")]).drop_duplicates(["target", "model"], keep="last")
rows = []
for target in ["theo_usd", "coin_in_usd"]:
    y = full[target].to_numpy()
    pel = harness._run(CANDIDATES["EL (iteration 1, current best)"], tr, fut, target)
    for name, f in CANDIDATES.items():
        p = harness._run(f, tr, fut, target)
        c = cv[(cv.target == target) & (cv.model == name)]
        rows.append({"target": target, "model": name, "cv7_mae": c.cv_mae.iloc[0] if len(c) else np.nan,
                     "holdout_mae": np.mean(np.abs(p - y)), "holdout_bias": np.mean(p - y),
                     "skill_vs_el": 1 - np.mean(np.abs(p - y)) / np.mean(np.abs(pel - y)),
                     "skill_vs_b2": 1 - np.mean(np.abs(p - y)) / harness.B2_HOLDOUT[target],
                     "dm_p_vs_el": harness.dm_test(p - y, pel - y) if name != "EL (iteration 1, current best)" else np.nan})
r = pd.DataFrame(rows)
r.to_csv(HERE / "posthoc_holdout.csv", index=False)
pd.set_option("display.width", 220)
print(r.sort_values(["target", "holdout_mae"]).to_string(index=False, float_format=lambda x: f"{x:,.3f}"))
