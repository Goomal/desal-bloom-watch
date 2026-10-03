"""score.py: pure deterministic levels + reasons. No I/O, no network, no database."""
from datetime import date, timedelta

import pytest

from dbw.climatology import Pctl
from dbw.score import DayStat, Level, Sentinel, Sst, score_box

DAY = date(2026, 8, 20)
P = Pctl(n=100, p50=1.0, p75=1.5, p90=2.0, p97=2.5)  # P97 < 3 x P50 so orange and red are distinct


def ds(offset, median, valid=10, total=10, p90=None):
    """A day's box stats, `offset` days before DAY."""
    return DayStat(DAY - timedelta(days=offset), valid, total, median, p90 if p90 is not None else median)


def flat(value, days=4):
    return [ds(k, value) for k in range(days)]


def reasons(score):
    return " | ".join(score.reasons)


# --- grey, never green -------------------------------------------------------------------------
def test_no_data_is_grey_not_green():
    s = score_box(DAY, [], P)
    assert s.level is Level.GREY
    assert "no data" in reasons(s).lower()


def test_stale_data_is_grey_not_green():
    s = score_box(DAY, [ds(6, 0.5)], P)  # newest valid observation is 6 days old
    assert s.level is Level.GREY and "stale" in reasons(s).lower()


def test_too_few_valid_pixels_is_grey_not_green():
    s = score_box(DAY, [ds(0, 0.5, valid=1, total=20)], P)  # 5 % of the box is clear
    assert s.level is Level.GREY and "coverage" in reasons(s).lower()


def test_no_percentile_for_the_season_is_grey_not_green():
    s = score_box(DAY, flat(0.5), None)
    assert s.level is Level.GREY and "history" in reasons(s).lower()


def test_all_nan_day_does_not_count_as_data():
    s = score_box(DAY, [DayStat(DAY, 0, 20, None, None)], P)
    assert s.level is Level.GREY


def test_clean_low_day_is_green_control():
    s = score_box(DAY, flat(0.5), P)
    assert s.level is Level.GREEN


# --- sentinel upgrade: yellow + upstream sentinel >= its P90 -> orange --------------------------
HIGH = Sentinel("port_said", value=9.0, p90=5.0, data_date=DAY)
CALM = Sentinel("port_said", value=2.0, p90=5.0, data_date=DAY)


def test_yellow_plus_high_sentinel_is_orange():
    s = score_box(DAY, flat(2.2), P, sentinels=[HIGH])  # >= P90, < P97
    assert s.level is Level.ORANGE
    assert "port_said" in reasons(s)


def test_yellow_with_calm_sentinel_stays_yellow():
    s = score_box(DAY, flat(2.2), P, sentinels=[CALM])
    assert s.level is Level.YELLOW


def test_high_sentinel_alone_does_not_upgrade_a_green_plant():
    s = score_box(DAY, flat(0.5), P, sentinels=[HIGH])
    assert s.level is Level.GREEN
    assert "port_said" in reasons(s)  # still reported as context


# --- level ladder (PLAN section 4 draft) ----------------------------------------------------------
def test_between_p75_and_p90_not_rising_is_green_with_above_normal_reason():
    s = score_box(DAY, flat(1.7), P)
    assert s.level is Level.GREEN and ">=P75" in reasons(s)


def test_at_or_above_p90_is_yellow():
    assert score_box(DAY, flat(2.0), P).level is Level.YELLOW


def test_at_or_above_p97_is_orange():
    assert score_box(DAY, flat(2.5), P).level is Level.ORANGE


def test_rising_three_days_above_p75_is_yellow():
    series = [ds(2, 1.55), ds(1, 1.7), ds(0, 1.85)]  # all >= P75, < P90, climbing
    s = score_box(DAY, series, P)
    assert s.level is Level.YELLOW and "rising" in reasons(s)


def test_flat_above_p75_is_not_rising():
    assert score_box(DAY, [ds(2, 1.7), ds(1, 1.7), ds(0, 1.7)], P).level is Level.GREEN


def test_falling_above_p75_is_not_rising():
    assert score_box(DAY, [ds(2, 1.9), ds(1, 1.7), ds(0, 1.55)], P).level is Level.GREEN


def test_trend_needs_every_day_in_window_above_p75():
    assert score_box(DAY, [ds(2, 1.0), ds(1, 1.6), ds(0, 1.9)], P).level is Level.GREEN


def test_three_times_seasonal_median_is_red():
    s = score_box(DAY, flat(3.2), P)  # 3.2 >= 3 x P50 (1.0)
    assert s.level is Level.RED and "3.2x" in reasons(s)


def test_red_multiple_also_needs_p90():
    q = Pctl(n=100, p50=0.2, p75=0.5, p90=1.0, p97=1.5)  # 3 x P50 = 0.6 < P90
    assert score_box(DAY, flat(0.7), q).level is Level.GREEN


def test_orange_two_days_running_is_red():
    s = score_box(DAY, flat(2.7), P, prev_level=Level.ORANGE)
    assert s.level is Level.RED and "two days" in reasons(s)


def test_orange_after_a_green_day_stays_orange():
    assert score_box(DAY, flat(2.7), P, prev_level=Level.GREEN).level is Level.ORANGE


# --- extent, sst, overlap, confidence --------------------------------------------------------------
def test_extent_widespread_when_median_above_p90():
    assert score_box(DAY, flat(2.5), P).extent == "widespread"


def test_extent_patchy_when_only_the_day_p90_is_above():
    s = score_box(DAY, [ds(0, 1.0, p90=2.5)], P)
    assert s.extent == "patchy" and s.level is Level.GREEN


def test_extent_local_otherwise():
    assert score_box(DAY, [ds(0, 1.0, p90=1.2)], P).extent == "local"


def test_warm_anomalous_sst_is_reason_not_level():
    s = score_box(DAY, flat(0.5), P, sst=Sst(value=28.5, normal=27.0))
    assert s.level is Level.GREEN and "warm water" in reasons(s)


def test_warm_sst_without_anomaly_has_no_warm_water_line():
    s = score_box(DAY, flat(0.5), P, sst=Sst(value=27.2, normal=27.0))
    assert "warm water" not in reasons(s) and "27.2" in reasons(s)


def test_cool_sst_has_no_warm_water_line():
    assert "warm water" not in reasons(score_box(DAY, flat(0.5), P, sst=Sst(value=22.0, normal=19.0)))


def test_shared_pixels_are_flagged_not_merged():
    s = score_box(DAY, flat(2.2), P, shared_with=["sorek_b", "palmachim"])
    assert s.level is Level.YELLOW  # level unchanged
    assert "shares the same satellite pixels with sorek_b, palmachim; not independent" in reasons(s)


def test_data_confidence_line_reports_valid_pixels_and_age():
    s = score_box(DAY, [ds(2, 0.5, valid=6, total=8)], P)
    assert s.level is Level.GREEN and "6/8" in reasons(s) and "2 days old" in reasons(s)


def test_newest_valid_wins_when_today_is_all_nan():
    s = score_box(DAY, [ds(1, 2.7), DayStat(DAY, 0, 10, None, None)], P)
    assert s.level is Level.ORANGE and s.as_of == DAY - timedelta(days=1)


def test_days_after_the_scored_day_are_ignored():
    assert score_box(DAY, [ds(0, 0.5), ds(-1, 9.0)], P).level is Level.GREEN


def test_unsorted_series_is_fine():
    assert score_box(DAY, [ds(0, 2.7), ds(3, 0.5), ds(1, 2.7)], P).level is Level.ORANGE


# --- tuning for false alarms (docs/scoring.md, anti-overfit) -----------------------------------------
def test_single_spike_is_judged_by_the_lower_neighbour():
    s = score_box(DAY, [ds(1, 1.0), ds(0, 9.0)], P)  # one-day spike after a calm day
    assert s.level is Level.GREEN


def test_spike_two_days_running_counts():
    assert score_box(DAY, [ds(1, 9.0), ds(0, 9.0)], P).level is Level.RED


def test_previous_day_more_than_three_days_back_does_not_pull_the_value_down():
    assert score_box(DAY, [ds(4, 1.0), ds(0, 9.0)], P).level is Level.RED


def test_sentinel_slightly_above_its_p90_is_not_high_enough():
    mild = Sentinel("port_said", value=5.5, p90=5.0, data_date=DAY)  # 1.1 x P90, under 1.5 x
    assert score_box(DAY, flat(2.2), P, sentinels=[mild]).level is Level.YELLOW
