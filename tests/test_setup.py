"""config.yaml writer and the non-interactive `dbw setup`. Offline: the backfill is replaced by a recorder."""
from datetime import date

import pytest
import yaml

from dbw import cli, climatology, config, registry


def test_write_config_roundtrips(tmp_path):
    path = tmp_path / "config.yaml"
    cfg = config.write(path, ["hadera", "eilat"], tmp_path / "reports", registry.load())
    assert cfg["plants"] == ["hadera", "eilat"]
    back = config.load(path)
    assert back["plants"] == ["hadera", "eilat"]
    assert back["report"]["out"] == str(tmp_path / "reports")
    assert back["report"]["formats"] == ["html", "md", "png", "txt"] and back["report"]["basemap"] == "none"
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == back


def test_write_config_rejects_unknown_and_sentinel_ids(tmp_path):
    with pytest.raises(config.ConfigError, match="nope"):
        config.write(tmp_path / "c.yaml", ["nope"], "r", registry.load())
    with pytest.raises(config.ConfigError, match="port_said"):
        config.write(tmp_path / "c.yaml", ["port_said"], "r", registry.load())
    assert not (tmp_path / "c.yaml").exists()


def test_write_config_needs_at_least_one_plant(tmp_path):
    with pytest.raises(config.ConfigError):
        config.write(tmp_path / "c.yaml", [], "r", registry.load())


def test_load_missing_config_is_none(tmp_path):
    assert config.load(tmp_path / "nope.yaml") is None


def test_load_rejects_a_bad_basemap(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("plants: [hadera]\nreport: {out: r, basemap: osm}\n", encoding="utf-8")
    with pytest.raises(config.ConfigError, match="basemap"):
        config.load(p)


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, conn, boxes, sources, start, end, **kw):
        self.calls.append((sorted(b.id for b in boxes), list(sources), start, end))
        return {}


def test_setup_yes_writes_config_backfills_scoped_boxes_and_writes_a_report(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    rec = Recorder()
    monkeypatch.setattr(climatology, "backfill", rec)
    cfgp, out = tmp_path / "config.yaml", tmp_path / "reports"
    rc = cli.main(["setup", "--plants", "hadera,eilat", "--out", str(out), "--config", str(cfgp), "--yes"])
    assert rc == 0
    assert config.load(cfgp)["plants"] == ["hadera", "eilat"]
    ids, sources, start, end = rec.calls[0]
    assert ids == sorted({"hadera", "eilat", "port_said", "el_arish", "rafah", "tiran", "gulf_mid"})
    assert (end - start).days == cli.RECENT_DAYS and sources == list(climatology.BACKFILL_SOURCES)
    assert sorted(p.suffix for p in out.iterdir()) == [".html", ".md", ".png", ".txt"]
    assert "DINEOF" in next(out.glob("*.md")).read_text(encoding="utf-8")


def test_setup_yes_without_plants_is_an_error(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["setup", "--out", str(tmp_path), "--config", str(tmp_path / "c.yaml"), "--yes"])


def test_setup_refuses_to_overwrite_without_yes(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("plants: [hadera]\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(["setup", "--plants", "eilat", "--out", str(tmp_path), "--config", str(p), "--no-input"])
    assert config.load(p)["plants"] == ["hadera"]


def test_prompt_plants_accepts_numbers_and_ids():
    boxes = registry.load()
    answers = iter(["2, eilat"])
    got = config.prompt_plants(boxes, input_fn=lambda _: next(answers), say=lambda *_: None)
    assert got == [[b.id for b in boxes if b.kind == "plant"][1], "eilat"]


def test_prompt_plants_reasks_on_junk():
    boxes = registry.load()
    answers = iter(["zzz", "hadera"])
    assert config.prompt_plants(boxes, input_fn=lambda _: next(answers), say=lambda *_: None) == ["hadera"]
