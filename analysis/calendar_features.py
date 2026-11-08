"""Deterministic calendar features, derived from a date column only.

No external data, APIs or event lookups: every feature is a fixed function of the date, so it is known years
in advance and cannot leak the target. Moving holidays (MLK, Presidents, Memorial, Labor, Columbus,
Thanksgiving) are computed per year from their weekday rules.

    from calendar_features import add_calendar_features
    df = add_calendar_features(df, date_col="gaming_date")

Existing columns are never modified or reordered, and the row count and index are unchanged. If a feature name
already exists with identical values it is left alone; if it exists with different values (e.g.
calendar_day.month is "2025-01"), the new feature is written as "<name>_cal" instead.

Definitions (all windows inclusive)
  season               meteorological: Winter Dec-Feb, Spring Mar-May, Summer Jun-Aug, Fall Sep-Nov
  is_holiday_season    Thanksgiving (4th Thu of Nov) through Jan 1
  is_christmas_week    Dec 20-26
  is_new_year_period   Dec 27 - Jan 2 (crosses the year boundary)
  is_thanksgiving_period  Mon-Sun of Thanksgiving week (Thanksgiving -3 .. +3 days)
  is_spring_break_period  fixed approximation: Mar 8-28 (the 2nd-4th weeks of March, when most US college
                       spring breaks fall)
  is_memorial_day_period  Fri-Mon ending on Memorial Day (last Mon of May)
  is_labor_day_period  Fri-Mon ending on Labor Day (1st Mon of Sep)
  is_july_4th_period   Jul 3-5, plus the Fri-Mon or Thu-Sun long weekend when the observed holiday is a Mon or Fri
  is_long_weekend      around US federal holidays (observed date: Sat -> Fri, Sun -> Mon):
                       observed Monday -> Fri-Mon; observed Friday -> Thu-Sun; Thanksgiving -> Thu-Sun.
                       Tue/Wed/Thu holidays (other than Thanksgiving) do not make a long weekend.
  is_payday_period     twice-monthly and month-end pay dates (1st, 15th, last day of month), each moved to the
                       previous weekday if it falls on a weekend, plus the 2 days after (play follows pay).
                       Biweekly cycles have no fixed phase across employers; their Friday pattern is already
                       carried by day_of_week, so no separate biweekly flag is added.
  is_month_start       day 1-3
  is_month_end         last 3 days of the month (leap-year aware)
  day_of_week          0 = Monday ... 6 = Sunday
  is_weekend           Saturday or Sunday (matches the dataset's existing is_weekend)
  day_of_month, month, quarter
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

SEASONS = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
           6: "Summer", 7: "Summer", 8: "Summer", 9: "Fall", 10: "Fall", 11: "Fall"}
SPRING_BREAK = ((3, 8), (3, 28))
PAYDAY_TAIL_DAYS = 2
EDGE_DAYS = 3

FEATURES = ["season", "is_winter", "is_spring", "is_summer", "is_fall", "is_holiday_season", "is_christmas_week",
            "is_new_year_period", "is_thanksgiving_period", "is_spring_break_period", "is_memorial_day_period",
            "is_labor_day_period", "is_july_4th_period", "is_long_weekend", "is_payday_period", "is_month_start",
            "is_month_end", "day_of_week", "is_weekend", "day_of_month", "month", "quarter"]


# ----------------------------------------------------------------------------- holiday rules
def nth_weekday(year: int, month: int, weekday: int, n: int) -> pd.Timestamp:
    """n-th `weekday` (0 = Mon) of the month; n = -1 for the last one."""
    if n > 0:
        first = pd.Timestamp(year, month, 1)
        return first + pd.Timedelta(days=(weekday - first.dayofweek) % 7 + 7 * (n - 1))
    last = pd.Timestamp(year, month, 1) + pd.offsets.MonthEnd(0)
    return last - pd.Timedelta(days=(last.dayofweek - weekday) % 7)


def thanksgiving(year: int) -> pd.Timestamp:
    return nth_weekday(year, 11, 3, 4)


def memorial_day(year: int) -> pd.Timestamp:
    return nth_weekday(year, 5, 0, -1)


def labor_day(year: int) -> pd.Timestamp:
    return nth_weekday(year, 9, 0, 1)


def observed(d: pd.Timestamp) -> pd.Timestamp:
    """Federal observance: Saturday -> Friday, Sunday -> Monday."""
    return d - pd.Timedelta(days=1) if d.dayofweek == 5 else d + pd.Timedelta(days=1) if d.dayofweek == 6 else d


@lru_cache(maxsize=None)
def federal_holidays(year: int) -> dict[str, pd.Timestamp]:
    """US federal holidays (actual dates, not observed). Juneteenth from 2021."""
    h = {"New Year's Day": pd.Timestamp(year, 1, 1),
         "Martin Luther King Jr. Day": nth_weekday(year, 1, 0, 3),
         "Washington's Birthday": nth_weekday(year, 2, 0, 3),
         "Memorial Day": memorial_day(year),
         "Independence Day": pd.Timestamp(year, 7, 4),
         "Labor Day": labor_day(year),
         "Columbus Day": nth_weekday(year, 10, 0, 2),
         "Veterans Day": pd.Timestamp(year, 11, 11),
         "Thanksgiving Day": thanksgiving(year),
         "Christmas Day": pd.Timestamp(year, 12, 25)}
    if year >= 2021:
        h["Juneteenth"] = pd.Timestamp(year, 6, 19)
    return h


def _long_weekend_days(name: str, d: pd.Timestamp) -> list[pd.Timestamp]:
    o = observed(d)
    if name == "Thanksgiving Day":
        return list(pd.date_range(o, o + pd.Timedelta(days=3)))          # Thu-Sun
    if o.dayofweek == 0:
        return list(pd.date_range(o - pd.Timedelta(days=3), o))          # Fri-Mon
    if o.dayofweek == 4:
        return list(pd.date_range(o - pd.Timedelta(days=1), o + pd.Timedelta(days=2)))  # Thu-Sun
    return []


@lru_cache(maxsize=None)
def long_weekend_dates(year: int) -> frozenset:
    """Long-weekend days for holidays of `year`, plus the next year's New Year (observed can fall on Dec 31)."""
    out = set()
    for y in (year, year + 1):
        for name, d in federal_holidays(y).items():
            out.update(_long_weekend_days(name, d))
    return frozenset(x for x in out if x.year == year)


@lru_cache(maxsize=None)
def payday_dates(year: int) -> frozenset:
    out = set()
    for y, m in [(year - 1, 12)] + [(year, m) for m in range(1, 13)]:
        for d in (pd.Timestamp(y, m, 1), pd.Timestamp(y, m, 15), pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)):
            while d.dayofweek >= 5:  # weekend -> previous Friday
                d -= pd.Timedelta(days=1)
            out.update(pd.date_range(d, d + pd.Timedelta(days=PAYDAY_TAIL_DAYS)))
    return frozenset(x for x in out if x.year == year)


# ----------------------------------------------------------------------------- features
def calendar_features(dates) -> pd.DataFrame:
    """Feature frame for a sequence of dates (one row per input, same order). Accepts dates or timestamps."""
    d = pd.DatetimeIndex(pd.to_datetime(pd.Series(dates)).dt.normalize())
    if d.isna().any():
        raise ValueError("date column contains missing values")
    m, dom, dow = d.month.to_numpy(), d.day.to_numpy(), d.dayofweek.to_numpy()
    days_in_month = d.days_in_month.to_numpy()
    years = sorted(set(d.year))

    def in_set(fn):
        s = set().union(*(fn(y) for y in years)) if years else set()
        return np.asarray(d.isin(list(s)))

    tg = {y: thanksgiving(y) for y in years}
    tg_d = pd.DatetimeIndex([tg[y] for y in d.year])
    md_d = pd.DatetimeIndex([memorial_day(y) for y in d.year])
    ld_d = pd.DatetimeIndex([labor_day(y) for y in d.year])
    to_tg = (d - tg_d).days.to_numpy()
    to_md = (d - md_d).days.to_numpy()
    to_ld = (d - ld_d).days.to_numpy()
    md = m * 100 + dom  # month-day as an integer, e.g. 1225

    season = pd.Series(m).map(SEASONS).to_numpy()
    lw = in_set(long_weekend_dates)
    j4_window = (md >= 703) & (md <= 705)
    j4_long = np.zeros(len(d), bool)
    for y in years:
        days = _long_weekend_days("Independence Day", pd.Timestamp(y, 7, 4))
        j4_long |= np.asarray(d.isin(days))

    f = pd.DataFrame({
        "season": season,
        "is_winter": season == "Winter", "is_spring": season == "Spring",
        "is_summer": season == "Summer", "is_fall": season == "Fall",
        "is_holiday_season": (to_tg >= 0) & (m >= 11) | (md == 101),
        "is_christmas_week": (md >= 1220) & (md <= 1226),
        "is_new_year_period": (md >= 1227) | (md <= 102),
        "is_thanksgiving_period": (to_tg >= -3) & (to_tg <= 3),
        "is_spring_break_period": (md >= SPRING_BREAK[0][0] * 100 + SPRING_BREAK[0][1]) &
                                  (md <= SPRING_BREAK[1][0] * 100 + SPRING_BREAK[1][1]),
        "is_memorial_day_period": (to_md >= -3) & (to_md <= 0),
        "is_labor_day_period": (to_ld >= -3) & (to_ld <= 0),
        "is_july_4th_period": j4_window | j4_long,
        "is_long_weekend": lw,
        "is_payday_period": in_set(payday_dates),
        "is_month_start": dom <= EDGE_DAYS,
        "is_month_end": dom > days_in_month - EDGE_DAYS,
        "day_of_week": dow.astype("int8"),
        "is_weekend": dow >= 5,
        "day_of_month": dom.astype("int8"),
        "month": m.astype("int8"),
        "quarter": d.quarter.to_numpy().astype("int8"),
    })
    for c in f.columns:
        if c.startswith("is_"):
            f[c] = f[c].astype(bool)
    return f[FEATURES]


def add_calendar_features(df: pd.DataFrame, date_col: str = "gaming_date") -> pd.DataFrame:
    """Return a copy of `df` with the calendar features appended (existing columns untouched)."""
    f = calendar_features(df[date_col])
    f.index = df.index
    out = df.copy()
    for c in f.columns:
        if c in out.columns:
            if out[c].astype(str).equals(f[c].astype(str)):
                continue
            out[f"{c}_cal"] = f[c]
        else:
            out[c] = f[c]
    return out


if __name__ == "__main__":
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "analysis"))
    from common import property_day  # noqa: E402

    pdy = add_calendar_features(property_day())
    pdy.to_csv(root / "outputs" / "property_day_calendar.csv", index=False)
    full = calendar_features(pd.date_range("2025-01-01", "2026-12-31"))
    full.insert(0, "date", pd.date_range("2025-01-01", "2026-12-31").date)
    full.to_csv(root / "outputs" / "calendar_features_2025_2026.csv", index=False)
    print(f"property_day_calendar.csv: {pdy.shape}; calendar_features_2025_2026.csv: {full.shape}")
    print(pdy[FEATURES].sum(numeric_only=True).to_string())
