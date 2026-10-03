from datetime import date

import pytest

from dbw import cli, registry, store
from dbw.providers.base import BoxStats, NoData

D = date(2026, 9, 27)


class Fake:
    def __init__(self, source, results):
        self.source, self._results = source, results

    def fetch(self, box, day):
        return self._results[box.id]


def providers():
    ok = BoxStats(12, 20, 0.137, 0.14, 0.15, 0.056, 0.323, "2026-09-27T12:00:00Z")
    nd = NoData("all_nan: 0/20 valid", total_count=20)
    return {
        "src_a": Fake("src_a", {b.id: (ok if i % 2 else nd) for i, b in enumerate(registry.load())}),
        "src_b": Fake("src_b", {b.id: ok for b in registry.load()}),
    }


def test_run_twice_writes_same_row_count(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    boxes = registry.load()
    cli.run_day(conn, boxes, providers(), D)
    first = store.count(conn)
    cli.run_day(conn, boxes, providers(), D)
    assert store.count(conn) == first
    # 13 boxes x 2 sources: half of src_a is NoData (2 rows), the rest 7 rows
    n = len(boxes)
    nodata = sum(1 for i in range(n) if not i % 2)
    assert first == nodata * 2 + (n - nodata) * 7 + n * 7


def test_run_returns_one_summary_line_per_box(tmp_path):
    conn = store.connect(tmp_path / "t.sqlite")
    boxes = registry.load()
    lines = cli.run_day(conn, boxes, providers(), D)
    assert len(lines) == len(boxes)
    assert lines[0].startswith("hadera") and "no data" in lines[0]


def test_plants_filter_keeps_plant_and_its_sentinels():
    boxes = registry.load()
    got = cli.select_boxes(boxes, ["ashkelon"])
    ids = {b.id for b in got}
    assert "ashkelon" in ids and "hadera" not in ids
    assert ids - {"ashkelon"} <= {b.id for b in boxes if b.kind == "sentinel"}
    with pytest.raises(SystemExit):
        cli.select_boxes(boxes, ["nope"])


def test_main_run_end_to_end_with_fakes(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    monkeypatch.setattr(cli, "build_providers", lambda names=None: providers())
    assert cli.main(["run", "--date", "2026-09-27", "--plants", "eilat"]) == 0
    out = capsys.readouterr().out
    assert "eilat" in out and "hadera" not in out
    conn = store.connect(tmp_path / "t.sqlite")
    assert store.count(conn) > 0


def test_unknown_source_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    with pytest.raises(SystemExit):
        cli.main(["run", "--date", "2026-09-27", "--sources", "bogus"])


def test_doctor_reports_unreachable_source(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))

    class Down:
        source = "src_down"

        def fetch(self, box, day):
            return NoData("network: boom", reachable=False)

    class UpNoData:
        source = "src_up"

        def fetch(self, box, day):
            return NoData("all_nan: 0/20 valid", total_count=20)

    monkeypatch.setattr(cli, "build_providers",
                        lambda names=None: {"src_down": Down(), "src_up": UpNoData()})
    assert cli.main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert "src_up" in out and "src_down" in out and "FAIL" in out


def test_doctor_ok_when_all_reachable(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))

    class UpNoData:
        source = "src_up"

        def fetch(self, box, day):
            return NoData("all_nan: 0/20 valid", total_count=20)

    monkeypatch.setattr(cli, "build_providers", lambda names=None: {"src_up": UpNoData()})
    assert cli.main(["doctor"]) == 0
