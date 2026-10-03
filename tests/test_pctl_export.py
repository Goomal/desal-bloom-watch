"""Percentile export: a committed, recomputable file of per-box seasonal percentiles so `dbw setup`
only fetches recent days. Offline, synthetic database."""
import json
from datetime import date, timedelta

import pytest

from dbw import cli, climatology as clim, config, pctl_export, registry, store
from dbw.providers.base import BoxStats

SRC = "noaacwNPPN20VIIRSDINEOFDaily"


def bs(v):
    return BoxStats(10, 10, v, v, v, v, v)


@pytest.fixture
def full(tmp_path):
    c = store.connect(tmp_path / "full.sqlite")
    for box in ("hadera", "eilat"):
        rows = {date(y, 8, 25) + timedelta(days=k): bs(1.0 + 0.01 * ((k * 7 + y) % 20))
                for y in range(2021, 2026) for k in range(-40, 41)}
        store.write_days(c, SRC, box, rows)
    store.put_cells(c, SRC, "hadera", [(32.5, 34.8)])
    return c


def test_export_header_says_where_the_numbers_came_from(full):
    data = pctl_export.build(full, ["hadera", "eilat"])
    h = data["header"]
    assert h["history"] == {"first": "2021-07-16", "last": "2025-10-04"}
    assert SRC in h["datasets"] and "coastwatch.noaa.gov/erddap" in h["datasets"][SRC]
    assert "median" in h["method"] and "P97" in h["method"]
    assert set(data["pctl"][SRC]) == {"hadera", "eilat"}


def test_installing_the_export_gives_the_same_percentiles_as_the_full_history(full, tmp_path):
    data = json.loads(json.dumps(pctl_export.build(full, ["hadera", "eilat"])))  # through JSON, like the file
    fresh = store.connect(tmp_path / "fresh.sqlite")
    assert pctl_export.install(fresh, data, ["hadera"]) == 1
    want = clim.seasonal_percentiles(store.load_series(full, SRC, "hadera"))
    got = clim.load_percentiles(fresh, SRC, "hadera")
    assert got.keys() == want.keys()
    for d, w in want.items():
        assert (got[d] is None) == (w is None)
        if w:
            assert got[d].n == w.n and all(abs(getattr(got[d], f) - getattr(w, f)) < 1e-4 for f in ("p50", "p75", "p90", "p97"))
    assert clim.load_percentiles(fresh, SRC, "eilat") == {}  # only the chosen boxes
    assert store.get_cells(fresh, SRC)["hadera"][0] == 1


def test_install_never_overwrites_percentiles_the_user_built_themselves(full, tmp_path):
    data = pctl_export.build(full, ["hadera"])
    own = store.connect(tmp_path / "own.sqlite")
    store.write_days(own, SRC, "hadera", {date(2024, 8, d): bs(5.0) for d in range(1, 29)})
    clim.build_percentiles(own, SRC, "hadera", min_n=1)
    before = store.get_pctl(own, SRC, "hadera", "median")
    assert pctl_export.install(own, data, ["hadera"]) == 0
    assert store.get_pctl(own, SRC, "hadera", "median") == before


def test_bundled_export_is_small_and_covers_every_registry_box():
    data = pctl_export.load()
    ids = {b.id for b in registry.load()}
    for src in clim.BACKFILL_SOURCES:
        assert set(data["pctl"][src]) == ids
    assert pctl_export.BUNDLED.stat().st_size < 600_000


# --- setup: the default fetches recent days only; --full-history keeps the long backfill -------------

class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, conn, boxes, sources, start, end, **kw):
        self.calls.append((sorted(b.id for b in boxes), start, end))
        return {}


def _setup(tmp_path, monkeypatch, *extra):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    rec = Recorder()
    monkeypatch.setattr(clim, "backfill", rec)
    rc = cli.main(["setup", "--plants", "hadera", "--out", str(tmp_path / "r"), "--config", str(tmp_path / "c.yaml"),
                   "--yes", *extra])
    assert rc == 0
    return rec, store.connect(tmp_path / "t.sqlite")


def test_setup_default_loads_the_export_and_fetches_only_recent_days(tmp_path, monkeypatch):
    rec, conn = _setup(tmp_path, monkeypatch)
    ids, start, end = rec.calls[0]
    assert "hadera" in ids and "eilat" not in ids
    assert (end - start).days == cli.RECENT_DAYS
    assert clim.load_percentiles(conn, SRC, "hadera")  # came from the export, no history fetched


def test_setup_full_history_keeps_the_long_backfill(tmp_path, monkeypatch):
    rec, _ = _setup(tmp_path, monkeypatch, "--full-history")
    assert rec.calls[0][1] == clim.FIRST_BACKFILL
