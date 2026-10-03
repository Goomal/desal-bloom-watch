"""Backfill: regional requests, resumability, adaptive split, no row for missing days. All offline."""
import re
import urllib.parse
from datetime import date, timedelta

import pytest

from dbw import climatology as clim
from dbw import store
from dbw.providers.base import FetchError
from dbw.registry import Box

SRC = "noaacwN20VIIRSchlaDaily"
SST = "noaacrwsstDaily"
LAT = [31.59375, 31.63125, 31.66875]
LON = [34.44375, 34.48125]


# one fixed 31-day chunk (chunk_days=31 boundaries are calendar multiples of 31)
C0 = date.fromordinal((date(2026, 8, 1).toordinal() // 31 + 1) * 31)
C1 = C0 + timedelta(days=30)


def box(i, lat0, lat1, lon0, lon1, sea="mediterranean"):
    return Box(i, "plant", ((lat0, lon0), (lat0, lon1), (lat1, lon1), (lat1, lon0), (lat0, lon0)), sea)


A = box("a", 31.60, 31.66, 34.44, 34.495)
B = box("b", 31.60, 31.66, 34.44, 34.495)  # same cells as a
C = box("c", 31.80, 31.86, 34.60, 34.66)
G = box("g", 29.48, 29.53, 34.94, 34.98, "red_sea")


class FakeErddap:
    """Answers a range URL with one row per day per pixel (value = day of month), skipping `missing`
    days; raises 502 for ranges longer than `max_days`; and records every URL it saw."""
    def __init__(self, max_days=999, missing=(), last=date(2026, 9, 29)):
        self.urls, self.max_days, self.missing, self.last = [], max_days, set(missing), last

    def __call__(self, url):
        self.urls.append(url)
        q = urllib.parse.unquote(url)
        t0, t1 = re.search(r"\((\d{4}-\d\d-\d\d)T12:00:00Z\):1:(\(last\)|\((\d{4}-\d\d-\d\d)T)", q).group(1, 3)
        a = date.fromisoformat(t0)
        b = date.fromisoformat(t1) if t1 else self.last
        if (b - a).days + 1 > self.max_days:
            raise FetchError("HTTP 502", reachable=False)
        lines = ["time,altitude,latitude,longitude,chlor_a", "UTC,m,degrees_north,degrees_east,mg m^-3"]
        d = a
        while d <= min(b, self.last):
            if d not in self.missing:
                lines += [f"{d}T12:00:00Z,0.0,{la},{lo},{d.day}.0" for la in LAT for lo in LON]
            d += timedelta(days=1)
        return "\n".join(lines) + "\n"


def run(conn, boxes, get, start=C0, end=C1, **kw):
    kw.setdefault("chunk_days", 31)
    kw.setdefault("sleep", lambda s: None)
    kw.setdefault("today", C1 + timedelta(days=60))
    kw.setdefault("log", lambda m: None)
    return clim.backfill(conn, boxes, [SRC], start, end, get=get, **kw)[SRC]


def n_rows(conn, box_id="a"):
    return conn.execute("SELECT COUNT(DISTINCT date) FROM obs WHERE source=? AND box=? AND stat='median'",
                        (SRC, box_id)).fetchone()[0]


def test_one_regional_request_per_chunk_serves_all_boxes_of_a_sea(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    fake = FakeErddap()
    rep = run(conn, [A, B], fake)
    assert rep.requests == 1 == len(fake.urls)  # one chunk, one sea, two boxes
    assert n_rows(conn, "a") == n_rows(conn, "b") == 31


def test_two_seas_two_requests_per_chunk(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    fake = FakeErddap()
    assert run(conn, [A, G], fake).requests == 2


def test_rerun_is_resumable_no_requests_and_no_duplicates(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    run(conn, [A], FakeErddap(missing=[C0 + timedelta(days=9)]))
    before = conn.execute("SELECT COUNT(*) FROM obs").fetchone()[0]
    fake = FakeErddap()
    rep = run(conn, [A], fake)
    assert fake.urls == [] and rep.skipped_chunks > 0 and rep.requests == 0
    assert conn.execute("SELECT COUNT(*) FROM obs").fetchone()[0] == before


def test_missing_day_gets_no_row_and_is_not_refetched(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    run(conn, [A], FakeErddap(missing=[C0 + timedelta(days=9)]))
    assert n_rows(conn) == 30
    assert C0 + timedelta(days=9) not in {d for d, _ in store.load_series(conn, SRC, "a", "median")}


def test_existing_row_is_not_overwritten_without_force_but_is_with_force(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    from dbw.providers.base import BoxStats
    d = C0 + timedelta(days=4)
    store.write_result(conn, d, SRC, "a", BoxStats(1, 1, 99.0, 99.0, 99.0, 99.0, 99.0, "x"))
    run(conn, [A], FakeErddap())
    assert dict(store.load_series(conn, SRC, "a", "median"))[d] == 99.0
    run(conn, [A], FakeErddap(), force=True)
    assert dict(store.load_series(conn, SRC, "a", "median"))[d] == float(d.day)


def test_502_halves_the_range_until_it_answers(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    fake = FakeErddap(max_days=8)
    rep = run(conn, [A], fake)
    assert rep.failed == [] and n_rows(conn) == 31
    assert rep.requests > 4  # 31 -> 15+16 -> 7/8 ... splits happened


def test_unanswerable_day_is_reported_and_not_marked_covered(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")

    def get(url):
        raise FetchError("HTTP 502", reachable=False)

    with pytest.raises(RuntimeError, match="in a row"):
        run(conn, [A], get)
    assert not store.is_covered(conn, SRC, "a", C0, C1)


def test_start_is_clamped_to_dataset_first_date(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    fake = FakeErddap()
    run(conn, [A], fake, start=date(2020, 1, 1), end=date(2021, 8, 31), chunk_days=31)
    first = urllib.parse.unquote(fake.urls[0])
    assert "(2021-08-26T12:00:00Z)" in first  # N20 begins 2021-08-26; earlier start is an ERDDAP 404


def test_recent_chunk_asks_for_last_and_is_never_marked_covered(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    fake = FakeErddap(last=C0 + timedelta(days=27))
    run(conn, [A], fake, today=C1)  # chunk ends within 3 days of today: open-ended request
    assert "(last)" in urllib.parse.unquote(fake.urls[0])
    assert n_rows(conn) == 28  # C0 .. the dataset's last slice
    fake2 = FakeErddap(last=C0 + timedelta(days=28))
    run(conn, [A], fake2, today=C1)
    assert len(fake2.urls) == 1 and n_rows(conn) == 29  # re-asked, picked up the new day


def test_cells_signature_identical_for_boxes_with_same_pixels(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    run(conn, [A, B, G], FakeErddap())
    sig = dict(conn.execute("SELECT box, signature FROM cells WHERE source=?", (SRC,)).fetchall())
    assert sig["a"] == sig["b"]


def test_chunks_are_aligned_to_fixed_boundaries():
    c1 = clim.chunk_ranges(date(2026, 8, 1), date(2026, 9, 30), 30)
    c2 = clim.chunk_ranges(date(2026, 8, 20), date(2026, 9, 30), 30)
    assert c1[0][0] == date(2026, 8, 1) and c1[-1][1] == date(2026, 9, 30)
    assert set(c2[1:]) <= set(c1)  # later chunks coincide whatever --from is
    assert all(b >= a for a, b in c1) and sum((b - a).days + 1 for a, b in c1) == 61


def test_percentiles_are_stored_and_reloaded(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    run(conn, [A], FakeErddap())
    clim.build_percentiles(conn, SRC, "a", min_n=5)
    pc = clim.load_percentiles(conn, SRC, "a")
    assert pc[clim.doy365(C0 + timedelta(days=15))].n == 31
    assert pc[clim.doy365(date(2026, 2, 15))] is None


def test_tie_box_is_queried_on_its_own_not_cut_from_the_region(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    # bbox edges 31.6 / 31.66 / 34.44 / 34.495 sit exactly midway between these pixel centres
    global LAT, LON
    saved = LAT, LON
    LAT, LON = [31.575, 31.625, 31.675], [34.425, 34.475, 34.525]
    try:
        fake = FakeErddap()
        rep = run(conn, [A, C, G], fake)
    finally:
        LAT, LON = saved
    assert rep.requests == 3  # Med region (holds tie box a and c), a on its own, red-sea region
    assert any("(31.6):1:(31.66)" in urllib.parse.unquote(u) for u in fake.urls)
