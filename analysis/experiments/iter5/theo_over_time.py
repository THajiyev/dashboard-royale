"""Daily theo (the forecast target) over the full data window, Jan 1 - Jun 30 2025 -> outputs/theo_over_time.png"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent.parent)]
from common import OUT, TRAIN_END, property_day  # noqa: E402
from ds_alpha.models import _EV  # noqa: E402

BLUE, BLUE_LIGHT, INK, INK2, GRID, SURF, SHADE = "#2a78d6", "#9ec5f4", "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb", "#f0efec"
d = property_day()
d["gaming_date"] = pd.to_datetime(d.gaming_date)
s = d.set_index("gaming_date").theo_usd.astype(float) / 1e3
r7 = s.rolling(7, center=True, min_periods=4).mean()
monthly = s.resample("MS").mean()

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False})
fig, ax = plt.subplots(figsize=(13, 5.6), facecolor=SURF)
ax.set_facecolor(SURF)
ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)

top = s.max() * 1.12
short = {"EV-CES25": "CES", "EV-SB59": "Super Bowl", "EV-MM25": "March\nMadness", "EV-CC25": "CinemaCon",
         "EV-NAB25": "NAB", "EV-EDC25": "EDC", "EV-P-TOURN": "Slot\ntournament", "EV-P-LOCALS": "Locals\nWeek"}
for r in _EV.itertuples():
    a, b = pd.Timestamp(r.start_date) - pd.Timedelta(hours=12), pd.Timestamp(r.end_date) + pd.Timedelta(hours=12)
    ax.axvspan(a, b, color=SHADE, zorder=0)
    y = top - (9 if r.event_id == "EV-NAB25" else 0)  # NAB starts 2 days after CinemaCon ends
    ax.text(a + (b - a) / 2, y, short[r.event_id], ha="center", va="top", fontsize=8, color=INK2)

ax.plot(s.index, s.values, color=BLUE_LIGHT, lw=1.2, zorder=2, label="Daily theo")
ax.plot(r7.index, r7.values, color=BLUE, lw=2.4, zorder=3, label="7-day average")
for m, v in monthly.items():
    e = m + pd.offsets.MonthEnd(0)
    ax.plot([m, e], [v, v], color=INK, lw=1.4, ls=(0, (4, 3)), zorder=4)
    ax.text(m + (e - m) / 2, v - 3.5, f"{m:%b} avg ${v:,.0f}K", ha="center", va="top", fontsize=8.5, color=INK)

ax.axvline(TRAIN_END + pd.Timedelta(hours=12), color=INK2, lw=1.2, zorder=4)
ax.text(TRAIN_END - pd.Timedelta(days=1), s.min() * 0.93, "Training (Jan–Apr)  ◀", ha="right", fontsize=9, color=INK2)
ax.text(TRAIN_END + pd.Timedelta(days=2), s.min() * 0.93, "▶  Test (May–Jun)", ha="left", fontsize=9, color=INK2)

ax.set_ylim(s.min() * 0.88, top * 1.01)
ax.set_xlim(s.index.min() - pd.Timedelta(days=2), s.index.max() + pd.Timedelta(days=2))
ax.set_ylabel("Daily theo ($K)")
ax.xaxis.set_major_locator(mdates.MonthLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
ax.set_title("Daily theo (expected casino revenue), Jan 1 – Jun 30 2025", loc="left", color=INK, fontsize=13,
             fontweight="bold", pad=22)
ax.legend(loc="lower right", bbox_to_anchor=(1, 1.0), frameon=False, ncol=2)
fig.text(0.01, 0.01, "Shaded: events. Dashed: monthly average. The data covers Jan–Jun 2025 only.",
         color=INK2, fontsize=8.5)
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig(OUT / "theo_over_time.png", dpi=150, facecolor=SURF)
print(monthly.round(1).to_string())
