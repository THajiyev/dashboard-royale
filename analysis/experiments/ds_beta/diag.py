"""Forecast-only diagnostics at the Apr 30 origin: ratio of candidate forecasts to B2 (no holdout actuals read)."""
from models import *
from common import TRAIN_END
df = harness.frame()
tr = df[df.gaming_date <= TRAIN_END].copy()
fut = df[(df.gaming_date > TRAIN_END) & (df.gaming_date <= "2025-06-30")][harness.FUTURE_COLS].copy()
def ratio(f, y="theo_usd"):
    p, b = f(tr, fut, y), B2(tr, fut, y)
    return p.mean() / b.mean()
if __name__ == "__main__":
    for n, f in [("trim", b2_family(loc="trim")), ("huber", b2_family(loc="huber")), ("median", b2_family(loc="median")),
                 ("EW28", b2_family(half_life=28)), ("EW56", b2_family(half_life=56)), ("LAD log", lad())]:
        print(n, round(ratio(f), 4))
    print(tr[tr.holiday == 1][["gaming_date", "weekday", "theo_usd", "federal_holiday", "event"]])
    print(fut[(fut.holiday == 1) | (fut.event == 1)])
    base = tr[tr.event == 0]
    print(base.groupby("dow").theo_usd.agg(["count", "mean", "median", "std", "skew"]).round(0))
