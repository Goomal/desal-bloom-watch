import re
import statistics
from datetime import date
from pathlib import Path

import pytest

from dbw.providers import noaa_erddap as erddap
from dbw.providers.base import BoxStats, FetchError, NoData
from dbw.registry import Box

FIX = Path(__file__).parent / "fixtures" / "erddap_n20_chl_eilat_2026-09-27.csv"
# The 12 non-NaN values in the fixture (one Eilat box, 2026-09-27, 20 pixels).
VALID = [0.14445019, 0.10341703, 0.32258037, 0.15162346, 0.14043872, 0.15008335,
         0.14888778, 0.13621071, 0.06924424, 0.12285184, 0.095229805, 0.05555072]

EILAT = Box("eilat", "plant", ((29.40, 34.90), (29.40, 35.00), (29.55, 35.00), (29.55, 34.90),
                               (29.40, 34.90)), "red_sea")


def test_parse_real_fixture():
    r = erddap.parse_csv(FIX.read_text(encoding="utf-8"))
    assert isinstance(r, BoxStats)
    assert (r.valid_count, r.total_count) == (12, 20)
    assert r.mean == pytest.approx(statistics.mean(VALID))
    assert r.median == pytest.approx(statistics.median(VALID))
    assert r.min == pytest.approx(min(VALID)) and r.max == pytest.approx(max(VALID))
    s = sorted(VALID)
    assert r.p90 == pytest.approx(s[9] + 0.9 * (s[10] - s[9]))  # linear interpolation at rank 9.9
    assert r.data_time == "2026-09-27T12:00:00Z"


def test_polygon_mask_triangle():
    # Hand-checked: 4 pixel centres fall inside; 2 of them are NaN.
    tri = ((29.40, 34.89), (29.40, 35.02), (29.47, 35.02), (29.40, 34.89))
    r = erddap.parse_csv(FIX.read_text(encoding="utf-8"), polygon=tri)
    assert (r.valid_count, r.total_count) == (2, 4)
    assert r.mean == pytest.approx((0.095229805 + 0.05555072) / 2)


def test_polygon_with_no_pixel_inside_is_nodata():
    far = ((10.0, 10.0), (10.0, 10.1), (10.1, 10.1), (10.0, 10.0))
    r = erddap.parse_csv(FIX.read_text(encoding="utf-8"), polygon=far)
    assert isinstance(r, NoData) and "polygon" in r.reason


def test_all_nan_grid_is_nodata_not_zero():
    text = re.sub(r",[0-9.]+\n", ",NaN\n", FIX.read_text(encoding="utf-8"))
    r = erddap.parse_csv(text)
    assert isinstance(r, NoData)
    assert r.total_count == 20 and "all_nan" in r.reason


def test_header_only_is_nodata():
    r = erddap.parse_csv("time,altitude,latitude,longitude,chlor_a\nUTC,m,degrees_north,degrees_east,mg m^-3\n")
    assert isinstance(r, NoData) and "empty" in r.reason


def test_url_encodes_brackets_and_snaps_to_noon():
    url = erddap.build_url("noaacwN20VIIRSchlaDaily", EILAT, date(2026, 9, 27))
    assert "[" not in url and "]" not in url
    assert "%5B" in url and "%5D" in url
    assert "(2026-09-27T12:00:00Z)" in url
    assert "(0.0)" in url  # VIIRS altitude axis
    assert "(29.4):1:(29.55)" in url and "(34.9):1:(35.0)" in url


def test_sst_has_no_altitude_axis():
    url = erddap.build_url("noaacrwsstDaily", EILAT, date(2026, 9, 27))
    assert "analysed_sst" in url and "(0.0)" not in url


def test_five_sources_with_attribution():
    assert set(erddap.SOURCES) == {
        "noaacwN20VIIRSchlaDaily", "noaacwNPPN20VIIRSDINEOFDaily", "noaacwNPPVIIRSchlaDaily",
        "noaacwN20VIIRSchlanomratDaily", "noaacrwsstDaily"}
    assert "CoastWatch" in erddap.ATTRIBUTION


def test_provider_fetch_uses_getter_and_rectangle_is_unmasked():
    seen = []

    def getter(url):
        seen.append(url)
        return FIX.read_text(encoding="utf-8")

    r = erddap.ErddapProvider("noaacwN20VIIRSchlaDaily", http_get=getter).fetch(EILAT, date(2026, 9, 27))
    assert (r.valid_count, r.total_count) == (12, 20)
    assert len(seen) == 1


def test_http_error_becomes_nodata_with_reachability():
    def boom404(url):
        raise FetchError("HTTP 404", reachable=True)

    def boom_net(url):
        raise FetchError("timeout", reachable=False)

    p404 = erddap.ErddapProvider("noaacwN20VIIRSchlaDaily", http_get=boom404).fetch(EILAT, date(2026, 9, 27))
    pnet = erddap.ErddapProvider("noaacwN20VIIRSchlaDaily", http_get=boom_net).fetch(EILAT, date(2026, 9, 27))
    assert isinstance(p404, NoData) and p404.reachable and "404" in p404.reason
    assert isinstance(pnet, NoData) and not pnet.reachable


def test_snapped_to_other_day_is_nodata():
    # ERDDAP snaps a missing time to the nearest slice; a different day must not be stored as ours.
    text = FIX.read_text(encoding="utf-8").replace("2026-09-27T12:00:00Z", "2026-09-26T12:00:00Z")
    assert isinstance(erddap.parse_csv(text, day=date(2026, 9, 26)), BoxStats)
    r = erddap.parse_csv(text, day=date(2026, 9, 27))
    assert isinstance(r, NoData) and r.reachable
    assert "no slice for 2026-09-27" in r.reason and "2026-09-26T12:00:00Z" in r.reason


def test_provider_rejects_snapped_slice():
    text = FIX.read_text(encoding="utf-8").replace("2026-09-27T12:00:00Z", "2026-09-25T12:00:00Z")
    r = erddap.ErddapProvider("noaacwN20VIIRSchlaDaily", http_get=lambda u: text).fetch(EILAT, date(2026, 9, 27))
    assert isinstance(r, NoData) and "no slice" in r.reason
