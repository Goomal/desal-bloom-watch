"""report.language: validated in config.yaml, chosen at `dbw setup`, overridden per render by `dbw report --language`."""
import builtins
import sqlite3

import pytest

from dbw import cli, climatology, config, registry
from test_report import conn  # noqa: F401  (calm-history database; `conn` is module-scoped there)


def test_default_language_is_english_and_is_written(tmp_path):
    path = tmp_path / "config.yaml"
    config.write(path, ["hadera"], tmp_path / "r", registry.load())
    assert config.load(path)["report"]["language"] == "en"
    assert config.report_language(config.load(path)) == "en" and config.report_language(None) == "en"


@pytest.mark.parametrize("lang", ["he", "ar"])
def test_language_roundtrips(tmp_path, lang):
    path = tmp_path / "config.yaml"
    config.write(path, ["hadera"], tmp_path / "r", registry.load(), language=lang)
    assert config.report_language(config.load(path)) == lang


def test_unknown_language_is_refused_when_writing_and_loading(tmp_path):
    with pytest.raises(config.ConfigError, match="language"):
        config.write(tmp_path / "c.yaml", ["hadera"], "r", registry.load(), language="fr")
    p = tmp_path / "c.yaml"
    p.write_text("plants: [hadera]\nreport: {out: r, language: fr}\n", encoding="utf-8")
    with pytest.raises(config.ConfigError, match="language"):
        config.load(p)


def test_a_config_without_language_still_loads_as_english(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("plants: [hadera]\nreport: {out: r}\n", encoding="utf-8")
    assert config.report_language(config.load(p)) == "en"


def test_txt_is_in_the_default_formats(tmp_path):
    assert "txt" in config.FORMATS
    cfg = config.write(tmp_path / "c.yaml", ["hadera"], "r", registry.load())
    assert cfg["report"]["formats"] == list(config.FORMATS)


def test_prompt_language_defaults_to_english_and_reasks_on_junk():
    assert config.prompt_language(input_fn=lambda _: "", say=lambda *_: None) == "en"
    answers = iter(["klingon", " HE "])
    assert config.prompt_language(input_fn=lambda _: next(answers), say=lambda *_: None) == "he"


def _db(monkeypatch, conn):  # noqa: F811
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    monkeypatch.setenv("DBW_DB", path)


def test_report_language_flag_overrides_the_config(tmp_path, monkeypatch, conn):  # noqa: F811
    _db(monkeypatch, conn)
    cfgp = tmp_path / "c.yaml"
    config.write(cfgp, ["hadera", "ashkelon"], tmp_path / "from-config", registry.load(), language="he")
    common = ["report", "--date", "2026-08-25", "--mode", "dineof", "--format", "html,txt", "--config", str(cfgp)]
    assert cli.main(common) == 0
    assert 'lang="he"' in (tmp_path / "from-config" / "dbw-report-2026-08-25.html").read_text(encoding="utf-8")
    assert cli.main(common + ["--language", "ar", "--out", str(tmp_path / "ar")]) == 0
    assert 'lang="ar"' in (tmp_path / "ar" / "dbw-report-2026-08-25.html").read_text(encoding="utf-8")
    assert cli.main(common + ["--language", "en", "--out", str(tmp_path / "en")]) == 0
    assert (tmp_path / "en" / "dbw-report-2026-08-25.html").read_text(encoding="utf-8").startswith("<!doctype html>\n<html lang=\"en\" dir=\"ltr\">")
    assert (tmp_path / "en" / "dbw-report-2026-08-25.txt").read_text(encoding="utf-8").startswith("Desal Bloom Watch 2026-08-25")


def test_report_rejects_an_unknown_language_flag(tmp_path, monkeypatch, conn):  # noqa: F811
    _db(monkeypatch, conn)
    with pytest.raises(SystemExit):
        cli.main(["report", "--date", "2026-08-25", "--language", "fr", "--out", str(tmp_path)])


class Recorder:
    def __call__(self, conn, boxes, sources, start, end, **kw):
        return {}


def test_setup_language_flag_writes_config_and_the_first_report(tmp_path, monkeypatch):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    monkeypatch.setattr(climatology, "backfill", Recorder())
    cfgp, out = tmp_path / "config.yaml", tmp_path / "reports"
    assert cli.main(["setup", "--plants", "hadera", "--out", str(out), "--config", str(cfgp), "--language", "he",
                     "--yes"]) == 0
    assert config.report_language(config.load(cfgp)) == "he"
    assert 'lang="he"' in next(out.glob("*.html")).read_text(encoding="utf-8")
    assert next(out.glob("*.txt")).read_text(encoding="utf-8").lstrip("\u200f").startswith("Desal Bloom Watch")


def test_setup_without_the_flag_stays_english_when_not_interactive(tmp_path, monkeypatch):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    monkeypatch.setattr(climatology, "backfill", Recorder())
    cfgp = tmp_path / "config.yaml"
    cli.main(["setup", "--plants", "hadera", "--out", str(tmp_path / "r"), "--config", str(cfgp), "--yes"])
    assert config.report_language(config.load(cfgp)) == "en"


def test_interactive_setup_asks_the_language_after_the_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    monkeypatch.setattr(climatology, "backfill", Recorder())
    asked = []
    answers = iter([str(tmp_path / "r"), "ar"])

    def fake_input(prompt=""):
        asked.append(prompt)
        return next(answers)

    monkeypatch.setattr(builtins, "input", fake_input)
    cfgp = tmp_path / "config.yaml"
    assert cli.main(["setup", "--plants", "hadera", "--config", str(cfgp), "--no-schedule", "--no-telegram"]) == 0
    assert [("folder" in q.lower(), "language" in q.lower()) for q in asked] == [(True, False), (False, True)]
    assert config.report_language(config.load(cfgp)) == "ar"
