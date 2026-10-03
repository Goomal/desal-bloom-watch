from datetime import date

from dbw import store
from dbw.providers.base import BoxStats, NoData

D = date(2026, 9, 27)
STATS = BoxStats(valid_count=12, total_count=20, mean=0.137, median=0.14, p90=0.15,
                 min=0.056, max=0.323, data_time="2026-09-27T12:00:00Z")


def rows(conn):
    return conn.execute("SELECT date, source, box, stat, value, note FROM obs ORDER BY 1,2,3,4").fetchall()


def test_rerun_same_date_does_not_duplicate(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    store.write_result(conn, D, "src", "eilat", STATS)
    first = rows(conn)
    store.write_result(conn, D, "src", "eilat", STATS)
    assert rows(conn) == first
    assert store.count(conn) == 7


def test_rerun_replaces_value(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    store.write_result(conn, D, "src", "eilat", STATS)
    newer = BoxStats(10, 20, 0.2, 0.2, 0.3, 0.1, 0.4, "2026-09-27T12:00:00Z")
    store.write_result(conn, D, "src", "eilat", newer)
    got = {r[3]: r[4] for r in rows(conn)}
    assert got["mean"] == 0.2 and got["valid_count"] == 10
    assert store.count(conn) == 7


def test_nodata_writes_zero_valid_count_with_reason(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    store.write_result(conn, D, "src", "eilat", NoData("all_nan: 0/20 valid", total_count=20))
    got = rows(conn)
    stats = {r[3]: r for r in got}
    assert stats["valid_count"][4] == 0
    assert stats["valid_count"][5] == "all_nan: 0/20 valid"
    assert stats["total_count"][4] == 20
    assert "mean" not in stats  # never zero-fill


def test_nodata_after_data_drops_stale_stats(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    store.write_result(conn, D, "src", "eilat", STATS)
    store.write_result(conn, D, "src", "eilat", NoData("http_500"))
    got = {r[3] for r in rows(conn)}
    assert got == {"valid_count"}


def test_default_path_honours_dbw_db(monkeypatch, tmp_path):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "x.sqlite"))
    assert store.default_path() == tmp_path / "x.sqlite"
    monkeypatch.delenv("DBW_DB")
    assert store.default_path().name == "dbw.sqlite"
