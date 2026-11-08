"""Tests for analysis/calendar_features.py.

Run:  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest analysis/tests -q
(the env var skips broken third-party pytest plugins installed in this Python, e.g. dash's.)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calendar_features import (FEATURES, add_calendar_features, calendar_features, federal_holidays,  # noqa: E402
                               labor_day, memorial_day, observed, thanksgiving)


def feat(date):
    return calendar_features([date]).iloc[0]


def flags(dates, col):
    return calendar_features(pd.to_datetime(dates))[col].tolist()


# ----------------------------------------------------------------------------- moving holidays
@pytest.mark.parametrize("year, tg, md, ld", [
    (2023, "2023-11-23", "2023-05-29", "2023-09-04"),
    (2024, "2024-11-28", "2024-05-27", "2024-09-02"),
    (2025, "2025-11-27", "2025-05-26", "2025-09-01"),
    (2026, "2026-11-26", "2026-05-25", "2026-09-07"),
    (2028, "2028-11-23", "2028-05-29", "2028-09-04"),
])
def test_moving_holidays(year, tg, md, ld):
    assert thanksgiving(year) == pd.Timestamp(tg)
    assert memorial_day(year) == pd.Timestamp(md)
    assert labor_day(year) == pd.Timestamp(ld)


def test_federal_holidays_match_dataset_calendar():
    """The dataset's own calendar_day.federal_holiday (Jan-Jun 2025) must agree with the computed rules."""
    root = Path(__file__).resolve().parents[2]
    c = pd.read_parquet(root / "data" / "2_machine_decision" / "calendar_day.parquet")
    given = {pd.Timestamp(d): n for d, n in zip(c.gaming_date, c.federal_holiday) if n}
    ours = {d: n for n, d in federal_holidays(2025).items() if d <= pd.Timestamp("2025-06-30")}
    assert given == ours


def test_observed_rule():
    assert observed(pd.Timestamp("2026-07-04")) == pd.Timestamp("2026-07-03")   # Sat -> Fri
    assert observed(pd.Timestamp("2027-07-04")) == pd.Timestamp("2027-07-05")   # Sun -> Mon
    assert observed(pd.Timestamp("2025-07-04")) == pd.Timestamp("2025-07-04")


# ----------------------------------------------------------------------------- windows and boundaries
def test_memorial_and_labor_day_weekends():
    assert flags(["2025-05-22", "2025-05-23", "2025-05-26", "2025-05-27"], "is_memorial_day_period") == \
        [False, True, True, False]
    assert flags(["2025-08-28", "2025-08-29", "2025-09-01", "2025-09-02"], "is_labor_day_period") == \
        [False, True, True, False]


def test_thanksgiving_week_and_holiday_season():
    assert flags(["2025-11-23", "2025-11-24", "2025-11-30", "2025-12-01"], "is_thanksgiving_period") == \
        [False, True, True, False]
    assert flags(["2025-11-26", "2025-11-27", "2025-12-31", "2026-01-01", "2026-01-02"], "is_holiday_season") == \
        [False, True, True, True, False]


def test_christmas_and_new_year_boundaries():
    assert flags(["2025-12-19", "2025-12-20", "2025-12-26", "2025-12-27"], "is_christmas_week") == \
        [False, True, True, False]
    assert flags(["2025-12-26", "2025-12-27", "2025-12-31", "2026-01-01", "2026-01-02", "2026-01-03"],
                 "is_new_year_period") == [False, True, True, True, True, False]


def test_spring_break_and_july_4th():
    assert flags(["2025-03-07", "2025-03-08", "2025-03-28", "2025-03-29"], "is_spring_break_period") == \
        [False, True, True, False]
    # 2025: Jul 4 is a Friday -> Thu-Sun long weekend, plus the Jul 3-5 window
    assert flags(["2025-07-02", "2025-07-03", "2025-07-06", "2025-07-07"], "is_july_4th_period") == \
        [False, True, True, False]
    # 2026: Jul 4 is a Saturday, observed Fri Jul 3 -> Thu Jul 2 - Sun Jul 5
    assert flags(["2026-07-01", "2026-07-02", "2026-07-05", "2026-07-06"], "is_july_4th_period") == \
        [False, True, True, False]


def test_long_weekends():
    # MLK 2025 = Mon Jan 20 -> Fri Jan 17 .. Mon Jan 20
    assert flags(["2025-01-16", "2025-01-17", "2025-01-20", "2025-01-21"], "is_long_weekend") == \
        [False, True, True, False]
    # Juneteenth 2025 is a Thursday: no long weekend
    assert flags(["2025-06-19", "2025-06-20"], "is_long_weekend") == [False, False]
    # Thanksgiving Thu-Sun
    assert flags(["2025-11-26", "2025-11-27", "2025-11-30", "2025-12-01"], "is_long_weekend") == \
        [False, True, True, False]


def test_long_weekend_across_year_boundary():
    # New Year's Day 2022 was a Saturday, observed Fri Dec 31 2021 -> Thu Dec 30 .. Sun Jan 2
    assert flags(["2021-12-29", "2021-12-30", "2021-12-31", "2022-01-01", "2022-01-02", "2022-01-03"],
                 "is_long_weekend") == [False, True, True, True, True, False]


def test_payday_period():
    # 2025-03-01 is a Saturday -> paid Fri Feb 28 (also month-end) -> Feb 28, Mar 1, Mar 2
    assert flags(["2025-02-27", "2025-02-28", "2025-03-02", "2025-03-03"], "is_payday_period") == \
        [False, True, True, False]
    # 2025-01-15 is a Wednesday -> Jan 15-17
    assert flags(["2025-01-14", "2025-01-15", "2025-01-17", "2025-01-18"], "is_payday_period") == \
        [False, True, True, False]
    # previous year's Dec 31 carries into Jan 1-2 (Dec 31 2024 was a Tuesday)
    assert flags(["2025-01-02"], "is_payday_period") == [True]


# ----------------------------------------------------------------------------- leap years and month edges
@pytest.mark.parametrize("date, end", [("2024-02-27", True), ("2024-02-26", False), ("2024-02-29", True),
                                       ("2025-02-26", True), ("2025-02-25", False), ("1900-02-26", True),
                                       ("2000-02-27", True), ("2000-02-26", False)])
def test_month_end_leap_years(date, end):
    assert feat(date).is_month_end == end


def test_leap_day_features():
    f = feat("2024-02-29")
    assert (f.month, f.day_of_month, f.quarter, f.season, f.day_of_week) == (2, 29, 1, "Winter", 3)
    assert f.is_month_end and not f.is_month_start


def test_month_start():
    assert flags(["2025-04-01", "2025-04-03", "2025-04-04"], "is_month_start") == [True, True, False]


def test_seasons_and_quarters_at_boundaries():
    f = calendar_features(pd.to_datetime(["2024-11-30", "2024-12-01", "2025-02-28", "2025-03-01",
                                          "2025-05-31", "2025-06-01", "2025-08-31", "2025-09-01"]))
    assert f.season.tolist() == ["Fall", "Winter", "Winter", "Spring", "Spring", "Summer", "Summer", "Fall"]
    assert f.quarter.tolist() == [4, 4, 1, 1, 2, 2, 3, 3]
    one_hot = f[["is_winter", "is_spring", "is_summer", "is_fall"]].sum(axis=1)
    assert (one_hot == 1).all()


def test_weekend_matches_dataset_definition():
    assert flags(["2025-01-03", "2025-01-04", "2025-01-05", "2025-01-06"], "is_weekend") == \
        [False, True, True, False]


# ----------------------------------------------------------------------------- structure and determinism
def test_preserves_structure_and_handles_conflicts():
    df = pd.DataFrame({"gaming_date": pd.to_datetime(["2025-01-01", "2025-07-04"]),
                       "theo_usd": [1.0, 2.0], "month": ["2025-01", "2025-07"], "is_weekend": [False, False]},
                      index=[10, 20])
    out = add_calendar_features(df)
    assert list(out.columns[:4]) == list(df.columns)
    pd.testing.assert_frame_equal(out[df.columns], df)          # existing columns untouched
    assert list(out.index) == [10, 20]
    assert "month_cal" in out and out.month_cal.tolist() == [1, 7]  # conflicting name -> suffix
    assert "is_weekend_cal" not in out                          # identical values -> left as is
    assert df.shape == (2, 4)                                   # input not mutated


def test_output_is_deterministic_and_order_independent():
    dates = pd.date_range("2023-12-15", "2025-01-15")
    a = calendar_features(dates)
    b = calendar_features(dates[::-1]).iloc[::-1].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)
    assert list(a.columns) == FEATURES
    assert not a.isna().any().any()


def test_features_depend_only_on_the_date():
    """Same date in different frames gives the same row (no look-ahead across rows)."""
    full = calendar_features(pd.date_range("2025-01-01", "2025-12-31"))
    one = calendar_features(pd.to_datetime(["2025-11-28"]))
    pd.testing.assert_frame_equal(full.iloc[[331]].reset_index(drop=True), one)


def test_accepts_strings_and_date_objects_and_rejects_missing():
    a = calendar_features(["2025-05-26"])
    b = calendar_features([pd.Timestamp("2025-05-26 14:00").date()])
    pd.testing.assert_frame_equal(a, b)
    with pytest.raises(ValueError):
        calendar_features([None])
