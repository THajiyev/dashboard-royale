"""Robustness tests for the weather check (weather_check.py). Writes weather_robustness.csv.

Residual = log(theo) - weekday mean - centred 15-day rolling median, on ordinary (non-event) days, as in
weather_check.py. Tests:
  A. Rain placebo test: the observed rain effect vs the effect of 4 random "rain days" (10,000 draws), and vs
     random 3-consecutive-day + 1 single-day patterns (mimicking the real May 4-6 cluster + Feb 13).
  B. Rain leave-one-episode-out: Feb 13 alone; May 4-6 alone.
  C. Rain threshold: > 0 mm, > 1 mm, > 5 mm.
  D. Heat specifications: daily high vs recent days (baseline); overnight low; yesterday's high;
     extreme heat (high >= 40 C, and top-decile high); May-Jun only (the hot season).
  E. Value of a perfect weather forecast: fit the rain + temperature effects on Jan-Apr residuals only, apply them
     with ACTUAL May-Jun weather to EL's May-Jun forecast (an upper bound no real forecast could reach),
     and compare MAE / RMSE with plain EL.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent.parent), str(HERE)]
from common import load  # noqa: E402
from ds_alpha.models import _EV  # noqa: E402
from segments import segment_day  # noqa: E402

rng = np.random.default_rng(0)
w = load("4_context/real_sources/weather_daily.parquet")
w["d"] = pd.to_datetime(w.source_date)
w = w.set_index("d")[["tmax_c", "tmin_c", "prcp_mm"]].astype(float)
s_all = segment_day().join(w)
ev = set()
for r in _EV.itertuples():
    ev |= set(pd.date_range(r.start_date, r.end_date))
s = s_all[~s_all.index.isin(ev)].copy()
s["dow"] = s.index.dayofweek


def resid(col, frame=s):
    ly = np.log(frame[col])
    r = ly - ly.groupby(frame.dow).transform("mean")
    return r - r.rolling(15, center=True, min_periods=5).median()


def dev(x, frame=s):
    return x - x.rolling(15, center=True, min_periods=5).mean()


def fit(r, cols):
    X = sm.add_constant(pd.DataFrame(cols))
    ok = r.notna() & X.notna().all(axis=1)
    return sm.OLS(r[ok], X[ok]).fit(cov_type="HAC", cov_kwds={"maxlags": 7}), ok


R = {c: resid(c) for c in ("total", "locals", "nonlocals")}
rows = []


def add(test, variant, series, effect, lo=np.nan, hi=np.nan, p=np.nan, n=np.nan, note=""):
    rows.append({"test": test, "variant": variant, "series": series, "effect": effect, "lo95": lo, "hi95": hi,
                 "p": p, "n_days": n, "note": note})


rain = (s.prcp_mm > 1).astype(float)
tdev = dev(s.tmax_c) / 10

# A. placebo test for rain (difference in mean residual, rain vs non-rain days)
for col in ("total", "locals"):
    r = R[col].dropna()
    rd = rain.reindex(r.index)
    obs = r[rd == 1].mean() - r[rd == 0].mean()
    idx = np.arange(len(r))
    null4 = []
    for _ in range(10000):
        pick = rng.choice(idx, 4, replace=False)
        m = np.zeros(len(r), bool); m[pick] = True
        null4.append(r.values[m].mean() - r.values[~m].mean())
    nullc = []
    for _ in range(10000):
        a = rng.integers(0, len(r) - 3); b = rng.integers(0, len(r))
        m = np.zeros(len(r), bool); m[a:a + 3] = True; m[b] = True
        if m.sum() < 4:
            continue
        nullc.append(r.values[m].mean() - r.values[~m].mean())
    for name, null in [("4 random days", null4), ("3 consecutive + 1 random day", nullc)]:
        p = (1 + np.sum(np.asarray(null) <= obs)) / (1 + len(null))
        add("A rain placebo", name, col, np.expm1(obs), p=p, n=int(rd.sum()),
            note=f"placebo 2.5-97.5%: {np.expm1(np.quantile(null, 0.025)):+.1%} to {np.expm1(np.quantile(null, 0.975)):+.1%}")

# B. leave one rain episode out
for label, keep in [("Feb 13 only", ["2025-02-13"]), ("May 4-6 only", ["2025-05-04", "2025-05-05", "2025-05-06"])]:
    rr = pd.Series(0.0, index=s.index)
    rr[pd.to_datetime(keep)] = 1.0
    other = (rain == 1) & (rr == 0)
    for col in ("total", "locals"):
        m, ok = fit(R[col][~other], {"rain": rr[~other], "temp_dev_10C": tdev[~other]})
        ci = m.conf_int().loc["rain"]
        add("B rain leave-one-out", label, col, np.expm1(m.params.rain), np.expm1(ci[0]), np.expm1(ci[1]),
            m.pvalues.rain, int(rr[~other][ok].sum()))

# C. rain threshold
for thr in (0.0, 1.0, 5.0):
    rr = (s.prcp_mm > thr).astype(float)
    for col in ("total", "locals"):
        m, ok = fit(R[col], {"rain": rr, "temp_dev_10C": tdev})
        ci = m.conf_int().loc["rain"]
        add("C rain threshold", f"> {thr:g} mm", col, np.expm1(m.params.rain), np.expm1(ci[0]), np.expm1(ci[1]),
            m.pvalues.rain, int(rr[ok].sum()))

# D. heat specifications (each with rain as a control)
q90 = s.tmax_c.quantile(0.9)
specs = {
    "high vs recent days, per +10C (baseline)": tdev,
    "overnight low vs recent days, per +10C": dev(s.tmin_c) / 10,
    "yesterday's high vs recent days, per +10C": tdev.shift(1),
    "extreme heat day (high >= 40C)": (s.tmax_c >= 40).astype(float),
    f"top-decile high (>= {q90:.1f}C)": (s.tmax_c >= q90).astype(float),
}
for name, x in specs.items():
    for col in ("total", "locals", "nonlocals"):
        m, ok = fit(R[col], {"x": x, "rain": rain})
        ci = m.conf_int().loc["x"]
        n = int(x[ok].sum()) if x.dropna().isin([0, 1]).all() else int(ok.sum())
        add("D heat spec", name, col, np.expm1(m.params.x), np.expm1(ci[0]), np.expm1(ci[1]), m.pvalues.x, n)
hot = s.index.month >= 5
for col in ("total", "locals", "nonlocals"):
    m, ok = fit(R[col][hot], {"x": tdev[hot], "rain": rain[hot]})
    ci = m.conf_int().loc["x"]
    add("D heat spec", "May-Jun only, high vs recent days, per +10C", col, np.expm1(m.params.x),
        np.expm1(ci[0]), np.expm1(ci[1]), m.pvalues.x, int(ok.sum()))

# E. value of a PERFECT weather forecast for EL (upper bound)
d = pd.read_csv(HERE / "holdout_daily.csv", parse_dates=["gaming_date"]).set_index("gaming_date")
tr = s.index <= "2025-04-30"
m, _ = fit(R["total"][tr], {"rain": rain[tr], "temp_dev_10C": tdev[tr]})
wf = s_all.reindex(d.index)
tdev_all = (s_all.tmax_c - s_all.tmax_c.rolling(15, center=True, min_periods=5).mean()).reindex(d.index) / 10
adj = np.exp(m.params.rain * (wf.prcp_mm > 1).astype(float) + m.params.temp_dev_10C * tdev_all.fillna(0))
y, p0 = d.actual, d["EL event-type lift"]
p1 = p0 * adj
for name, p in [("EL", p0), ("EL x perfect-weather adjustment", p1)]:
    e = p - y
    add("E perfect weather forecast", name, "total", float(np.mean(np.abs(e))),
        note=f"RMSE {np.sqrt(np.mean(e ** 2)):,.0f}; fitted on Jan-Apr: rain {np.expm1(m.params.rain):+.1%} "
             f"(1 rain day), +10C {np.expm1(m.params.temp_dev_10C):+.1%}")
e0, e1 = (p0 - y).abs(), (p1 - y).abs()
add("E perfect weather forecast", "MAE change", "total", e1.mean() / e0.mean() - 1,
    note=f"May 4-6 MAE {e0['2025-05-04':'2025-05-06'].mean():,.0f} -> {e1['2025-05-04':'2025-05-06'].mean():,.0f}")

out = pd.DataFrame(rows)
out.to_csv(HERE / "weather_robustness.csv", index=False)

if __name__ == "__main__":
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 120)
    print(out.to_string(index=False, float_format=lambda x: f"{x:+.3f}" if abs(x) < 10 else f"{x:,.0f}"))
