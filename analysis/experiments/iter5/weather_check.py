"""Does weather explain play? (competing-explanation check for the June decline; not a forecast input)

Source: data/4_context/real_sources/weather_daily.parquet (NOAA, Las Vegas airport, Jan 1 - Jun 30 2025).
Ordinary (non-event) days only. For each day:
  play residual = log(theo) - weekday mean of log(theo) - centred 15-day rolling median   (weekday + slow level removed)
  temperature   = daily high minus its centred 15-day rolling mean                          ("hotter than recent days")
  rain day      = precipitation > 1 mm
OLS of the residual on both, HAC (Newey-West, 7 lags) standard errors; for floor total, locals and non-locals.
Writes weather_check.csv (regression) and weather_monthly.csv (monthly averages).
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

w = load("4_context/real_sources/weather_daily.parquet")
w["d"] = pd.to_datetime(w.source_date)
w = w.set_index("d")[["tmax_c", "tmin_c", "prcp_mm"]].astype(float)
s = segment_day().join(w)
ev = set()
for r in _EV.itertuples():
    ev |= set(pd.date_range(r.start_date, r.end_date))
s = s[~s.index.isin(ev)].copy()
s["dow"] = s.index.dayofweek
s["rain"] = (s.prcp_mm > 1).astype(float)

rows = []
for col, label in [("total", "Floor total"), ("locals", "Locals"), ("nonlocals", "Visitors (non-locals)")]:
    ly = np.log(s[col])
    r = ly - ly.groupby(s.dow).transform("mean")
    r = r - r.rolling(15, center=True, min_periods=5).median()
    t = s.tmax_c - s.tmax_c.rolling(15, center=True, min_periods=5).mean()
    X = sm.add_constant(pd.DataFrame({"temp_dev_10C": t / 10, "rain": s.rain}))
    ok = r.notna() & X.notna().all(axis=1)
    m = sm.OLS(r[ok], X[ok]).fit(cov_type="HAC", cov_kwds={"maxlags": 7})
    ci_t, ci_r = m.conf_int().loc["temp_dev_10C"], m.conf_int().loc["rain"]
    rows.append({"series": label, "n_days": int(ok.sum()), "rain_days": int(s.rain[ok].sum()),
                 "effect_plus10C": np.expm1(m.params.temp_dev_10C), "lo95_plus10C": np.expm1(ci_t[0]),
                 "hi95_plus10C": np.expm1(ci_t[1]), "p_temp": m.pvalues.temp_dev_10C,
                 "effect_rain": np.expm1(m.params.rain), "lo95_rain": np.expm1(ci_r[0]), "hi95_rain": np.expm1(ci_r[1]),
                 "p_rain": m.pvalues.rain})
reg = pd.DataFrame(rows)
monthly = s.groupby(s.index.to_period("M")).agg(avg_high_c=("tmax_c", "mean"), rain_days=("rain", "sum"),
                                                locals_usd_day=("locals", "mean"), visitors_usd_day=("nonlocals", "mean"),
                                                total_usd_day=("total", "mean"))
reg.to_csv(HERE / "weather_check.csv", index=False)
monthly.to_csv(HERE / "weather_monthly.csv")

if __name__ == "__main__":
    pd.set_option("display.width", 200)
    print(reg.to_string(index=False, float_format=lambda x: f"{x:+.3f}"))
    print(monthly.round(1).to_string())
    print("rain dates:", list(s.index[s.rain == 1].date))
    print("corr(monthly high, locals)", np.corrcoef(monthly.avg_high_c, monthly.locals_usd_day)[0, 1].round(2),
          " corr(monthly high, visitors)", np.corrcoef(monthly.avg_high_c, monthly.visitors_usd_day)[0, 1].round(2))
