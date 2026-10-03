"""Multi-day (time-range) ERDDAP responses: grouping by UTC date, per-box windowing, URLs."""
from datetime import date
from pathlib import Path

import pytest

from dbw.providers import noaa_erddap as erddap
from dbw.providers.base import BoxStats, NoData
from dbw.registry import Box

FIX = Path(__file__).parent / "fixtures"
REGION = (FIX / "erddap_n20_range_region_ashkelon_2026-09-01_04.csv").read_text(encoding="utf-8")
BOXRESP = (FIX / "erddap_n20_range_box_ashkelon_2026-09-01_04.csv").read_text(encoding="utf-8")

ASHKELON = Box("ashkelon", "plant", ((31.60, 34.44), (31.60, 34.495), (31.66, 34.495),
                                     (31.66, 34.44), (31.60, 34.44)), "mediterranean")
D1, D2, D3, D4 = (date(2026, 9, d) for d in (1, 2, 3, 4))
SEP1 = [3.26032, 9.675145, 7.90579, 18.065632, 13.845899, 40.463455]  # hand-copied from the fixture


def test_parse_range_groups_pixels_by_utc_date():
    grid = erddap.parse_range_csv(BOXRESP)
    assert sorted(grid) == [D1, D2, D3, D4]
    assert all(len(px) == 6 for px in grid.values())
    assert grid[D1][(31.66875, 34.44374999999998)] == pytest.approx(3.26032)


def test_range_stats_reuse_phase1_semantics():
    stats, cells = erddap.range_stats(erddap.parse_range_csv(BOXRESP), ASHKELON)
    s = stats[D1]
    assert isinstance(s, BoxStats)
    assert (s.valid_count, s.total_count) == (6, 6)
    assert s.mean == pytest.approx(sum(SEP1) / 6)
    assert s.max == pytest.approx(40.463455) and s.min == pytest.approx(3.26032)
    assert s.data_time == "2026-09-01T12:00:00Z"
    assert len(cells) == 6


def test_all_nan_day_is_nodata_not_zero_and_not_dropped():
    stats, _ = erddap.range_stats(erddap.parse_range_csv(BOXRESP), ASHKELON)
    assert isinstance(stats[D4], NoData)
    assert stats[D4].total_count == 6 and "all_nan" in stats[D4].reason


def test_day_missing_from_response_gets_no_entry_never_a_neighbour():
    text = "\n".join(l for l in BOXRESP.splitlines() if not l.startswith("2026-09-02"))
    stats, _ = erddap.range_stats(erddap.parse_range_csv(text), ASHKELON)
    assert sorted(stats) == [D1, D3, D4]


def test_regional_window_equals_per_box_query():
    """A box cut out of a bigger regional grid must select exactly the pixels griddap returns
    for the box's own query (nearest-grid-index rule), so backfill == daily `dbw run`."""
    region, rcells = erddap.range_stats(erddap.parse_range_csv(REGION), ASHKELON)
    direct, dcells = erddap.range_stats(erddap.parse_range_csv(BOXRESP), ASHKELON)
    assert rcells == dcells and len(rcells) == 6
    for d in (D1, D2, D3):
        assert region[d] == direct[d]


def test_box_outside_the_grid_is_absent():
    far = Box("far", "plant", ((10.0, 10.0), (10.0, 10.1), (10.1, 10.1), (10.1, 10.0), (10.0, 10.0)))
    stats, cells = erddap.range_stats(erddap.parse_range_csv(REGION), far)
    assert stats == {} and cells == ()


def test_two_boxes_with_same_bbox_share_cells():
    twin = Box("twin", "plant", ASHKELON.polygon)
    _, a = erddap.range_stats(erddap.parse_range_csv(REGION), ASHKELON)
    _, b = erddap.range_stats(erddap.parse_range_csv(REGION), twin)
    assert a == b


def test_range_url_is_one_request_with_a_time_range():
    url = erddap.build_range_url("noaacwN20VIIRSchlaDaily", (31.55, 31.72, 34.38, 34.56),
                                 date(2026, 9, 1), date(2026, 9, 30))
    assert "[" not in url and "]" not in url
    assert "(2026-09-01T12:00:00Z):1:(2026-09-30T12:00:00Z)" in url.replace("%3A", ":")
    assert "(0.0)" in url and "(31.55):1:(31.72)" in url and "(34.38):1:(34.56)" in url


def test_range_url_open_end_uses_last():
    url = erddap.build_range_url("noaacrwsstDaily", (31.55, 31.72, 34.38, 34.56), date(2026, 9, 1), None)
    assert "(last)" in url and "(0.0)" not in url


# --- edge-of-union-bbox equivalence (console condition): Ashkelon sits at the SW corner of the
# union bbox of Ashkelon + Ashdod, Ashdod at the NE corner. Fixtures are real ERDDAP responses.
UNION = (FIX / "erddap_n20_range_region_union_ashkelon_ashdod_2026-09-01_04.csv").read_text(encoding="utf-8")
ASHDOD_RESP = (FIX / "erddap_n20_range_box_ashdod_2026-09-01_04.csv").read_text(encoding="utf-8")
ASHDOD = Box("ashdod", "plant", ((31.84, 34.632), (31.84, 34.656), (31.86, 34.656),
                                 (31.86, 34.632), (31.84, 34.632)), "mediterranean")


@pytest.mark.parametrize("box,direct", [(ASHKELON, BOXRESP), (ASHDOD, ASHDOD_RESP)])
def test_union_bbox_edge_box_equals_its_own_query(box, direct):
    region, rcells = erddap.range_stats(erddap.parse_range_csv(UNION), box)
    own, ocells = erddap.range_stats(erddap.parse_range_csv(direct), box)
    assert rcells == ocells and len(rcells) > 0
    assert region == own
    assert sorted(region) == [D1, D2, D3, D4]


def test_region_split_matches_phase1_single_day_parser():
    """Per-day cross-check against the Phase 1 per-box parser (parse_csv) on the same box."""
    region, _ = erddap.range_stats(erddap.parse_range_csv(UNION), ASHKELON)
    for d in (D1, D2, D3):
        one_day = "\n".join(l for i, l in enumerate(BOXRESP.splitlines())
                            if i < 2 or l.startswith(d.isoformat()))
        assert region[d] == erddap.parse_csv(one_day, day=d)


def test_non_rectangular_box_gets_polygon_mask_like_phase1():
    tri = Box("tri", "plant", ((31.60, 34.44), (31.60, 34.495), (31.66, 34.495), (31.60, 34.44)))
    assert not tri.is_rectangle
    region, rcells = erddap.range_stats(erddap.parse_range_csv(UNION), tri)
    assert 0 < len(rcells) < 6
    for d in (D1, D2):
        one_day = "\n".join(l for i, l in enumerate(BOXRESP.splitlines())
                            if i < 2 or l.startswith(d.isoformat()))
        assert region[d] == erddap.parse_csv(one_day, polygon=tri.polygon, day=d)


# --- ties: a box edge exactly midway between two pixel centres. ERDDAP resolves such a tie its own
# way (live: CoralTemp, 0.05 deg grid, el_arish/tiran/gulf_mid/palmachim edges at x.x0 sit exactly
# midway), which a regional split cannot reproduce, so those boxes are flagged and queried alone.
def _grid(lats, lons):
    rows = ["time,latitude,longitude,analysed_sst", "UTC,degrees_north,degrees_east,degree_C"]
    rows += [f"2026-09-01T12:00:00Z,{la},{lo},28.0" for la in lats for lo in lons]
    return erddap.parse_range_csv("\n".join(rows) + "\n")


SST_LATS = [31.175, 31.225, 31.275, 31.325, 31.375]
SST_LONS = [33.725, 33.775, 33.825, 33.875, 33.925, 33.975]


def test_edge_midway_between_pixels_is_flagged_as_tie():
    el_arish = Box("el_arish", "sentinel", ((31.2, 33.75), (31.2, 33.9), (31.3, 33.9), (31.3, 33.75), (31.2, 33.75)))
    assert erddap.has_tie(_grid(SST_LATS, SST_LONS), el_arish)


def test_edge_clearly_nearer_one_pixel_is_not_a_tie():
    near = Box("near", "plant", ((31.23, 33.78), (31.23, 33.88), (31.27, 33.88), (31.27, 33.78), (31.23, 33.78)))
    assert not erddap.has_tie(_grid(SST_LATS, SST_LONS), near)


def test_real_viirs_boxes_in_the_fixture_have_no_tie():
    grid = erddap.parse_range_csv(UNION)
    assert not erddap.has_tie(grid, ASHKELON) and not erddap.has_tie(grid, ASHDOD)
