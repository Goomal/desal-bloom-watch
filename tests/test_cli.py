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
    assert cli.main(["doctor", "--config", str(tmp_path / "none.yaml")]) == 1
    out = capsys.readouterr().out
    assert "src_up" in out and "src_down" in out and "FAIL" in out


def test_doctor_ok_when_all_reachable(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))

    class UpNoData:
        source = "src_up"

        def fetch(self, box, day):
            return NoData("all_nan: 0/20 valid", total_count=20)

    monkeypatch.setattr(cli, "build_providers", lambda names=None: {"src_up": UpNoData()})
    assert cli.main(["doctor", "--config", str(tmp_path / "none.yaml")]) == 0


def _doctor_env(tmp_path, monkeypatch):
    from dbw import config, registry
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))

    class Up:
        source = "src_up"

        def fetch(self, box, day):
            return NoData("all_nan: 0/20 valid", total_count=20)
    monkeypatch.setattr(cli, "build_providers", lambda names=None: {"src_up": Up()})
    p = tmp_path / "config.yaml"
    config.write(p, ["ashkelon"], tmp_path / "reports", registry.load(), formats=["md"])
    return p


def test_doctor_is_silent_about_the_bot_when_subscriptions_are_not_used(tmp_path, monkeypatch, capsys):
    p = _doctor_env(tmp_path, monkeypatch)
    assert cli.main(["doctor", "--config", str(p)]) == 0
    out = capsys.readouterr().out
    assert "admin_ids" not in out and "bot:" not in out


def test_doctor_checks_admin_ids_and_the_bot_once_subscriptions_are_used(tmp_path, monkeypatch, capsys):
    from dbw import bot, config, store, subscribers
    p = _doctor_env(tmp_path, monkeypatch)
    subscribers.add(store.connect(), "Dana", "telegram", "111", ["hadera"], "he", "self")
    assert cli.main(["doctor", "--config", str(p)]) == 1
    out = capsys.readouterr().out
    assert "FAIL telegram admin_ids: not set" in out and "FAIL bot: not running" in out
    config.add_telegram_admin(p, 999)
    held = bot.acquire_lock(bot.lock_path())
    try:
        assert cli.main(["doctor", "--config", str(p)]) == 0
    finally:
        held.close()
    out = capsys.readouterr().out
    assert "OK   telegram admin_ids: 1 set" in out and "OK   bot: running" in out
