"""Noise floor: how far is our out-of-sample ordinary-day RMSE from the in-sample error of a model fit on Jan-Jun?

In-sample fits on all of Jan 1 - Jun 30 (181 days), scored on ordinary (non-event) days:
  EL in-sample          EL (iter 1) fit on Jan-Jun and evaluated on the same days: one weekday profile, no drift.
  local level (L days)  the EL2 + anchor structure in hindsight: non-event weekday profile x a CENTRED L-day
                        rolling level (mean of y / profile over non-event days). It sees the level on both sides
                        of every day, so it is an optimistic floor (a lower bound on irreducible day-to-day noise).
Out-of-sample: ordinary-day RMSE on May-Jun from holdout_daily.csv (no refit).
Stop rule (user): if iteration 5 does not win and the best out-of-sample ordinary RMSE is within ~15% of the floor,
stop modelling.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent.parent), str(HERE)]
import harness  # noqa: E402
from evaluate import _EV  # noqa: E402
from iter2.models import EL  # noqa: E402

Y = "theo_usd"
df = harness.frame()
df = df[df.gaming_date <= "2025-06-30"].reset_index(drop=True)
ev_days = set()
for r in _EV.itertuples():
    ev_days |= set(pd.date_range(r.start_date, r.end_date))
ev = df.gaming_date.isin(ev_days).to_numpy()
mayjun = (df.gaming_date >= "2025-05-01").to_numpy()
y = df[Y].to_numpy()
rmse = lambda e: float(np.sqrt(np.mean(e ** 2)))

fits = {"EL in-sample (Jan-Jun fit)": EL(df.copy(), df[harness.FUTURE_COLS].copy(), Y)}
prof = df[~ev].groupby("dow")[Y].mean()
b = df.dow.map(prof).to_numpy()
for L in (28, 14):
    ratio = pd.Series(np.where(ev, np.nan, y / b))
    lvl = ratio.rolling(L, center=True, min_periods=L // 2).mean().bfill().ffill().to_numpy()
    fits[f"local level, centred {L}d (hindsight)"] = b * lvl

rows = [{"fit": k, "ordinary_RMSE_janjun": rmse((p - y)[~ev]), "ordinary_RMSE_mayjun": rmse((p - y)[~ev & mayjun])}
        for k, p in fits.items()]
floor = pd.DataFrame(rows)

t = pd.read_csv(HERE / "table_vs_b1.csv").set_index("model")
oos = {"EL2A segments: bottom_up beta=1.0": "best ordinary-day model (not picked in advance)",
       "EL2A segments: bottom_up beta=0.5": "iteration 5 pick",
       "EL2 + 28d anchor": "current main",
       "EL event-type lift": "best overall model picked in advance",
       "B1 weekday mean": "baseline"}
ref = floor.set_index("fit").ordinary_RMSE_mayjun
F28 = ref["local level, centred 28d (hindsight)"]
cmp = pd.DataFrame([{"model": m, "role": role, "oos_ordinary_RMSE": t.loc[m, "ordinary_RMSE"],
                     "gap_vs_floor_28d": t.loc[m, "ordinary_RMSE"] / F28 - 1,
                     "gap_vs_floor_14d": t.loc[m, "ordinary_RMSE"] / ref["local level, centred 14d (hindsight)"] - 1,
                     "gap_vs_EL_insample": t.loc[m, "ordinary_RMSE"] / ref["EL in-sample (Jan-Jun fit)"] - 1}
                    for m, role in oos.items()])
floor.to_csv(HERE / "noise_floor.csv", index=False)
cmp.to_csv(HERE / "noise_floor_gap.csv", index=False)

if __name__ == "__main__":
    pd.set_option("display.width", 220)
    print(floor.to_string(index=False, float_format=lambda x: f"{x:,.0f}"))
    print()
    print(cmp.to_string(index=False, float_format=lambda x: f"{x:+.1%}" if abs(x) < 5 else f"{x:,.0f}"))
    print("\nordinary days: Jan-Jun", int((~ev).sum()), " May-Jun", int((~ev & mayjun).sum()))
