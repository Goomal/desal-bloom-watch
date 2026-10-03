"""Seasonal percentile window: +-15 days, circular over the year end, min sample count."""
from datetime import date

import pytest

from dbw import climatology as clim


def test_doy365_ignores_leap_day():
    assert clim.doy365(date(2025, 3, 1)) == 60
    assert clim.doy365(date(2024, 3, 1)) == 60  # leap year: Mar 1 is still 60
    assert clim.doy365(date(2024, 2, 29)) == clim.doy365(date(2024, 2, 28)) == 59
    assert clim.doy365(date(2024, 12, 31)) == 365


def test_window_is_plus_minus_15_inclusive():
    # one sample per offset around 10 Apr in 2021..: offsets -16..+16 days
    from datetime import timedelta
    centre = date(2022, 4, 10)
    series = [(centre + timedelta(days=k), float(abs(k))) for k in range(-16, 17)]
    pc = clim.seasonal_percentiles(series, min_n=1)
    n = pc[clim.doy365(centre)].n
    assert n == 31  # offsets -15..+15 inclusive, -16 and +16 excluded
    assert pc[clim.doy365(centre)].p97 <= 15.0


def test_window_wraps_over_the_year_end():
    series = [(date(2021, 12, 25), 5.0), (date(2022, 1, 8), 7.0), (date(2022, 1, 20), 99.0)]
    pc = clim.seasonal_percentiles(series, min_n=1)
    jan3 = pc[clim.doy365(date(2022, 1, 3))]
    assert jan3.n == 2  # Dec 25 (9 days before, across the year end) and Jan 8; Jan 20 is 17 away
    assert jan3.p50 == pytest.approx(6.0)
    dec28 = pc[clim.doy365(date(2021, 12, 28))]
    assert dec28.n == 2  # Dec 25 and Jan 8 (11 days after, across the year end)


def test_percentile_values_linear_interpolation_across_years():
    series = [(date(2000 + k, 4, 10), float(k + 1)) for k in range(100)]  # 1..100 on one doy
    p = clim.seasonal_percentiles(series, min_n=10)[clim.doy365(date(2050, 4, 10))]
    assert p.n == 100
    assert p.p50 == pytest.approx(50.5)
    assert p.p75 == pytest.approx(75.25)
    assert p.p90 == pytest.approx(90.1)
    assert p.p97 == pytest.approx(97.03)


def test_below_min_sample_count_gives_no_percentile():
    series = [(date(2021 + k, 4, 10), 1.0 + k) for k in range(5)]
    pc = clim.seasonal_percentiles(series, min_n=30)
    assert pc[clim.doy365(date(2022, 4, 10))] is None
    assert clim.seasonal_percentiles(series, min_n=3)[clim.doy365(date(2022, 4, 10))] is not None


def test_exclude_year_leaves_that_year_out():
    series = [(date(2021, 4, 10), 1.0), (date(2022, 4, 10), 2.0), (date(2023, 4, 10), 100.0)]
    full = clim.seasonal_percentiles(series, min_n=1)[clim.doy365(date(2022, 4, 10))]
    loo = clim.seasonal_percentiles(series, min_n=1, exclude_year=2023)[clim.doy365(date(2022, 4, 10))]
    assert full.n == 3 and loo.n == 2 and loo.p97 < 3.0


def test_nan_and_none_values_are_skipped():
    series = [(date(2021, 4, 10), float("nan")), (date(2022, 4, 10), None), (date(2023, 4, 10), 2.0)]
    p = clim.seasonal_percentiles(series, min_n=1)[clim.doy365(date(2022, 4, 10))]
    assert p.n == 1 and p.p50 == 2.0
