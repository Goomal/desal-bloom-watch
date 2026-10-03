import json
import statistics
from datetime import date
from pathlib import Path

import pytest

from dbw.providers import openmeteo
from dbw.providers.base import BoxStats, FetchError, NoData
from dbw.registry import Box

FIX = Path(__file__).parent / "fixtures"
WIND = json.loads((FIX / "openmeteo_wind_ashkelon.json").read_text(encoding="utf-8"))
AIR = json.loads((FIX / "openmeteo_air_ashkelon.json").read_text(encoding="utf-8"))
BOX = Box("ashkelon", "plant", ((31.60, 34.44), (31.60, 34.50), (31.66, 34.50), (31.66, 34.44),
                                (31.60, 34.44)), "mediterranean")
D = date(2026, 9, 27)


def getter(url):
    if "air-quality" in url:
        return json.dumps(AIR)
    return json.dumps(WIND)


def test_wind_speed_daily_stats_from_fixture():
    r = openmeteo.OpenMeteoProvider("openmeteo_wind_speed", http_get=getter).fetch(BOX, D)
    vals = WIND["hourly"]["wind_speed_10m"]
    assert isinstance(r, BoxStats) and (r.valid_count, r.total_count) == (24, 24)
    assert r.mean == pytest.approx(statistics.mean(vals))
    assert r.max == max(vals) and r.min == min(vals)


def test_dust_and_aod_come_from_air_quality_api():
    dust = openmeteo.OpenMeteoProvider("openmeteo_dust", http_get=getter).fetch(BOX, D)
    aod = openmeteo.OpenMeteoProvider("openmeteo_aod", http_get=getter).fetch(BOX, D)
    assert dust.mean == pytest.approx(statistics.mean(AIR["hourly"]["dust"]))
    assert aod.mean == pytest.approx(statistics.mean(AIR["hourly"]["aerosol_optical_depth"]))


def test_wind_direction_is_circular_mean_without_other_stats():
    r = openmeteo.OpenMeteoProvider("openmeteo_wind_dir", http_get=getter).fetch(BOX, D)
    assert 0 <= r.mean < 360
    assert r.median is None and r.p90 is None and r.min is None and r.max is None
    assert openmeteo.circular_mean_deg([350, 10]) == pytest.approx(0, abs=1e-6) or \
        openmeteo.circular_mean_deg([350, 10]) == pytest.approx(360, abs=1e-6)
    assert openmeteo.circular_mean_deg([90, 90]) == pytest.approx(90)


def test_url_uses_box_centroid_no_key_and_local_day():
    url = openmeteo.build_url("openmeteo_wind_speed", BOX, D)
    assert url.startswith("https://api.open-meteo.com/v1/forecast?")
    assert "latitude=31.63" in url and "longitude=34.47" in url
    assert "start_date=2026-09-27" in url and "end_date=2026-09-27" in url
    assert "apikey" not in url and "Asia%2FJerusalem" in url
    assert openmeteo.build_url("openmeteo_dust", BOX, D).startswith(
        "https://air-quality-api.open-meteo.com/v1/air-quality?")


def test_null_hours_are_not_counted_valid():
    air = json.loads(json.dumps(AIR))
    air["hourly"]["dust"][:20] = [None] * 20
    r = openmeteo.OpenMeteoProvider("openmeteo_dust", http_get=lambda u: json.dumps(air)).fetch(BOX, D)
    assert (r.valid_count, r.total_count) == (4, 24)


def test_all_null_is_nodata():
    air = json.loads(json.dumps(AIR))
    air["hourly"]["dust"] = [None] * 24
    r = openmeteo.OpenMeteoProvider("openmeteo_dust", http_get=lambda u: json.dumps(air)).fetch(BOX, D)
    assert isinstance(r, NoData) and r.total_count == 24


def test_http_error_and_bad_json_are_nodata():
    def boom(url):
        raise FetchError("HTTP 400", reachable=True)

    assert isinstance(openmeteo.OpenMeteoProvider("openmeteo_dust", http_get=boom).fetch(BOX, D), NoData)
    bad = openmeteo.OpenMeteoProvider("openmeteo_dust", http_get=lambda u: "not json").fetch(BOX, D)
    assert isinstance(bad, NoData) and "json" in bad.reason.lower()


def test_shared_cache_makes_one_request_for_speed_and_direction():
    calls = []
    cache = {}

    def counting(url):
        calls.append(url)
        return json.dumps(WIND)

    for s in ("openmeteo_wind_speed", "openmeteo_wind_dir"):
        openmeteo.OpenMeteoProvider(s, http_get=counting, cache=cache).fetch(BOX, D)
    assert len(calls) == 1
    assert "non-commercial" in openmeteo.ATTRIBUTION and "CC BY 4.0" in openmeteo.ATTRIBUTION
