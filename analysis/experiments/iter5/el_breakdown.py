"""Error breakdown of the headline model (EL, iteration 1; fixed forecast made Apr 30 for May-Jun).

Writes outputs/el_error_over_time.png and outputs/el_error_breakdown.csv (daily rows). No refit beyond EL itself.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent.parent), str(HERE)]
import forecast  # noqa: E402
import harness  # noqa: E402
from common import OUT, TRAIN_END  # noqa: E402
from evaluate import ALPHA, _EV, cv_residuals, fixed_run  # noqa: E402
from iter2.models import EL  # noqa: E402

END = pd.Timestamp("2025-06-30")
df = harness.frame()
p, y, d = fixed_run(EL, df, TRAIN_END, END)
pb1, _, _ = fixed_run(forecast.m_b1, df, TRAIN_END, END)
lr, _, _ = cv_residuals(EL, "fixed", df[df.gaming_date <= TRAIN_END])
qlo, qhi = np.quantile(lr, [ALPHA / 2, 1 - ALPHA / 2])
d = pd.DatetimeIndex(d)

ev_name = pd.Series("", index=d)
for r in _EV.itertuples():
    ev_name[(d >= r.start_date) & (d <= r.end_date)] = r.name
known = {r.event_id for r in _EV.itertuples() if r.announced_date <= TRAIN_END}
ev_known = pd.Series(False, index=d)
for r in _EV.itertuples():
    if r.event_id in known:
        ev_known[(d >= r.start_date) & (d <= r.end_date)] = True

t = pd.DataFrame({"gaming_date": d, "actual": y, "forecast": p, "lo90": p * np.exp(qlo), "hi90": p * np.exp(qhi),
                  "b1": pb1, "event": ev_name.to_numpy(), "event_known_at_forecast": ev_known.to_numpy()})
t["error"] = t.forecast - t.actual
t["error_pct"] = t.error / t.actual
t["inside90"] = (t.actual >= t.lo90) & (t.actual <= t.hi90)
t["weekday"] = d.day_name().str[:3]
t.to_csv(OUT / "el_error_breakdown.csv", index=False)

# ----------------------------------------------------------------------------- numbers
rm = lambda e: float(np.sqrt(np.mean(np.square(e))))
print(f"RMSE {rm(t.error):,.0f}  MAE {t.error.abs().mean():,.0f}  bias {t.error.mean():+,.0f}  "
      f"MAPE {t.error_pct.abs().mean():.2%}  90% cover {t.inside90.mean():.0%}")
print(f"lag-1 autocorrelation of daily error: {t.error.autocorr(1):.2f}")
t["period"] = np.where(t.gaming_date.dt.month == 5, "May", "Jun")
print(t.groupby("period", sort=False).agg(MAE=("error", lambda e: e.abs().mean()), bias=("error", "mean"),
                                          bias_pct=("error_pct", "mean")).round(3).to_string())
print(t.groupby("weekday").agg(MAE=("error", lambda e: e.abs().mean()), bias=("error", "mean"),
                               bias_pct=("error_pct", "mean")).reindex(
    ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]).round(3).to_string())
g = t.assign(event=t.event.replace("", "(ordinary day)")).groupby("event")
print(g.agg(days=("error", "size"), MAE=("error", lambda e: e.abs().mean()), bias_pct=("error_pct", "mean"),
            known=("event_known_at_forecast", "first")).round(3).to_string())
print(t.reindex(t.error.abs().sort_values(ascending=False).index).head(6)[
    ["gaming_date", "weekday", "actual", "forecast", "error_pct", "event"]].to_string(index=False))
w = t.set_index("gaming_date").error_pct.resample("W-SUN").mean()
print("weekly mean error %:", (w * 100).round(1).to_dict())

# ----------------------------------------------------------------------------- chart
BLUE, ORANGE, INK, INK2, GRID, SURF, BAND = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#cde2fb"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False})
fig, (a1, a2) = plt.subplots(2, 1, figsize=(12, 7.6), sharex=True, gridspec_kw={"height_ratios": [1.15, 1]},
                             facecolor=SURF)
for a in (a1, a2):
    a.set_facecolor(SURF)
    a.grid(axis="y", color=GRID, lw=0.8)
    a.set_axisbelow(True)
    for name, s, e in [("EDC (known)", "2025-05-16", "2025-05-18"),
                       ("Locals Week (announced May 26, after the forecast)", "2025-06-09", "2025-06-15"),
                       ("Memorial Day wknd", "2025-05-23", "2025-05-26")]:
        a.axvspan(pd.Timestamp(s) - pd.Timedelta(hours=12), pd.Timestamp(e) + pd.Timedelta(hours=12),
                  color="#f0efec", zorder=0)

k = 1e3
a1.fill_between(t.gaming_date, t.lo90 / k, t.hi90 / k, color=BAND, lw=0, label="90% band", zorder=1)
a1.plot(t.gaming_date, t.actual / k, color=BLUE, lw=2, marker="o", ms=3.5, label="Actual", zorder=3)
a1.plot(t.gaming_date, t.forecast / k, color=ORANGE, lw=2, label="EL forecast (made Apr 30)", zorder=2)
a1.set_ylabel("Daily theo ($K)")
a1.set_title("EL forecast vs actual, May–Jun 2025", loc="left", color=INK, fontsize=12, fontweight="bold")
a1.legend(loc="lower right", bbox_to_anchor=(1, 1.0), frameon=False, ncol=3)
for name, x in [("EDC", "2025-05-17"), ("Memorial\nDay wknd", "2025-05-24"), ("Locals Week\n(unknown at forecast)", "2025-06-12")]:
    a1.annotate(name, (pd.Timestamp(x), a1.get_ylim()[1]), xytext=(0, -4), textcoords="offset points",
                ha="center", va="top", fontsize=8.5, color=INK2)

cols = np.where(t.event != "", ORANGE, BLUE)
a2.bar(t.gaming_date, t.error_pct * 100, color=cols, width=0.75, zorder=2)
roll = t.set_index("gaming_date").error_pct.rolling(7, center=True, min_periods=4).mean() * 100
a2.plot(roll.index, roll.values, color=INK, lw=2, zorder=3, label="7-day average error")
a2.axhline(0, color=INK2, lw=1, zorder=2)
a2.set_ylabel("Forecast error (% of actual)\n+ = over-forecast")
a2.set_title("Daily error", loc="left", color=INK, fontsize=12, fontweight="bold")
from matplotlib.patches import Patch  # noqa: E402
a2.legend(handles=[Patch(color=BLUE, label="Ordinary day"), Patch(color=ORANGE, label="Event day"),
                   plt.Line2D([], [], color=INK, lw=2, label="7-day average error")],
          loc="lower left", frameon=False, ncol=3)
a2.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
a2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
fig.text(0.01, 0.005, "Error = forecast − actual. Shaded: EDC, Memorial Day weekend, Locals Week. "
         "90% band: split-conformal from Jan–Apr CV.", color=INK2, fontsize=8.5)
fig.tight_layout(rect=(0, 0.02, 1, 1))
fig.savefig(OUT / "el_error_over_time.png", dpi=150, facecolor=SURF)
print("wrote", OUT / "el_error_over_time.png")
