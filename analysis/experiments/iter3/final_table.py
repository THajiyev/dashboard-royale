"""Final comparison of every model that had a logged holdout look: full 61 days, and excluding the Locals
Appreciation Week (Jun 9–15, a novel event format announced May 26). Writes final_table.csv."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE))
import harness
from common import TRAIN_END
from evaluate import FIXED, REFRESH, HO_REFRESH, refresh_series, _pred

LOOKED = [("fixed", "B2"), ("fixed", "EL (current best)"), ("fixed", "EL2 k_ev=0.5"), ("fixed", "ZS"),
          ("fixed", "ZS + damped trend (phi .98)"), ("refresh", "B2"), ("refresh", "EL"),
          ("refresh", "EL + anchor 100% (28d)"), ("refresh", "ZS"), ("refresh", "ZS + anchor 100% (28d)"),
          ("refresh", "EL2 k_ev=0.5 + anchor 0% (28d)"), ("refresh", "EL2 k_ev=0.5 + anchor 50% (28d)"),
          ("refresh", "EL2 k_ev=0.5 + anchor 100% (28d)")]
cv = pd.read_csv(HERE / "cv_results.csv")
cv = pd.concat([cv, pd.read_csv(HERE / "cv_results_round2.csv")]).drop_duplicates(["protocol", "target", "model"], keep="last")
df = harness.frame(); end = pd.Timestamp("2025-06-30")
rows = []
for t in ["theo_usd", "coin_in_usd"]:
    for proto, name in LOOKED:
        f = FIXED[name] if proto == "fixed" else REFRESH[name]
        p, y, d = _pred(f, df, TRAIN_END, end, t) if proto == "fixed" else refresh_series(f, df, HO_REFRESH, end, t)
        e = pd.Series(p - y, index=pd.to_datetime(d))
        lw = (e.index >= "2025-06-09") & (e.index <= "2025-06-15")
        c = cv[(cv.protocol == proto) & (cv.target == t) & (cv.model == name)]
        rows.append({"target": t, "protocol": proto, "model": name, "cv_mae": c.mae.iloc[0] if len(c) else np.nan,
                     "holdout_mae": e.abs().mean(), "holdout_bias": e.mean(), "mae_ex_locals": e[~lw].abs().mean(),
                     "bias_ex_locals": e[~lw].mean(), "bias_last_2wk": e[e.index >= "2025-06-17"].mean(),
                     "locals_week_bias": e[lw].mean()})
r = pd.DataFrame(rows); r.to_csv(HERE / "final_table.csv", index=False)
pd.set_option("display.width", 250)
print(r[r.target == "theo_usd"].to_string(index=False, float_format=lambda x: f"{x:,.0f}"))
