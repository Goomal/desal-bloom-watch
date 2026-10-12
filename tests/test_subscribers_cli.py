"""Subscriptions on the computer: admin_ids in config.yaml, `dbw subscribers ...`, `dbw telegram admin-id`.
Offline; the fake token is built at run time."""
import pytest
import yaml

from dbw import config, registry


def check(tg):
    return config.check({"plants": ["hadera"], "channels": {"telegram": tg}})


def test_admin_ids_load_as_ints_whatever_their_yaml_type():
    assert config.telegram_admin_ids(check({"admin_ids": [111, "222"]})) == [111, 222]


def test_no_admin_ids_is_an_empty_list():
    assert config.telegram_admin_ids(None) == []
    assert config.telegram_admin_ids({"plants": ["hadera"]}) == []
    assert config.telegram_admin_ids(check({"enabled": False})) == []


def test_admin_ids_alone_do_not_turn_on_the_admin_report():
    assert config.telegram_chat_ids(check({"admin_ids": [111]})) == []


@pytest.mark.parametrize("bad", [111, ["abc"], [True], [1.5], "111"])
def test_bad_admin_ids_are_a_one_line_config_error(bad):
    with pytest.raises(config.ConfigError, match="admin_ids"):
        check({"admin_ids": bad})


def test_add_telegram_admin_adds_once_and_keeps_every_other_key(tmp_path):
    p = tmp_path / "config.yaml"
    config.write(p, ["ashkelon"], tmp_path / "reports", registry.load(), formats=["md"], language="he")
    config.add_telegram_admin(p, "111")
    config.add_telegram_admin(p, 111)
    cfg = config.load(p)
    assert cfg["channels"]["telegram"]["admin_ids"] == [111]
    assert cfg["plants"] == ["ashkelon"] and cfg["report"]["language"] == "he"
    assert cfg["channels"]["telegram"].get("enabled") is not True
    assert yaml.safe_load(p.read_text(encoding="utf-8"))["channels"]["telegram"]["admin_ids"] == [111]


import json

from dbw import cli, store, subscribers as subs
from test_telegram import TOKEN, Http, fail, http  # noqa: F401  (http is a fixture)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    return store.connect(tmp_path / "t.sqlite")


@pytest.fixture
def cfgp(tmp_path, monkeypatch):
    p = tmp_path / "config.yaml"
    config.write(p, ["ashkelon"], tmp_path / "reports", registry.load(), formats=["md"])
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    return p


def answers(monkeypatch, *replies):
    it = iter(replies)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it))


def test_list_empty_then_one_line_per_subscriber(db, capsys):
    assert cli.main(["subscribers", "list"]) == 0
    assert "no subscribers yet" in capsys.readouterr().out
    subs.add(db, "Dana", "telegram", "111", ["hadera"], "he", "self")
    cli.main(["subscribers", "list"])
    out = capsys.readouterr().out
    assert "Dana" in out and "telegram 111" in out and "hadera" in out and "he" in out


def test_add_picks_a_contact_then_asks_name_plants_language(db, monkeypatch, capsys):
    subs.touch_contact(db, "telegram", "111", "Dana", "private", 100)
    subs.touch_contact(db, "telegram", "-100222", "Plant ops", "supergroup", 200)
    answers(monkeypatch, "2", "", "hadera,eilat", "he")  # 2 = Dana (newest first: Plant ops is 1); Enter keeps her name
    assert cli.main(["subscribers", "add"]) == 0
    (s,) = subs.active(db)
    assert (s.address, s.name, s.plants, s.language, s.added_by) == ("111", "Dana", ("hadera", "eilat"), "he", "admin")


def test_add_with_nobody_known_says_how_to_get_someone(db):
    with pytest.raises(SystemExit, match="message the bot"):
        cli.main(["subscribers", "add"])


def test_remove_by_id(db, capsys):
    s = subs.add(db, "Dana", "telegram", "111", ["hadera"], "he", "self")
    assert cli.main(["subscribers", "remove", str(s.id)]) == 0
    assert subs.active(db) == [] and "removed" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="no active subscriber"):
        cli.main(["subscribers", "remove", str(s.id)])


def test_export_writes_every_row_as_json(db, tmp_path):
    subs.add(db, "Dana", "telegram", "111", ["hadera"], "he", "self")
    out = tmp_path / "backup.json"
    assert cli.main(["subscribers", "export", "--out", str(out)]) == 0
    assert [r["name"] for r in json.loads(out.read_text(encoding="utf-8"))] == ["Dana"]


def test_admin_id_writes_a_private_chat_only(db, cfgp, http):
    subs.touch_contact(db, "telegram", "-100222", "Plant ops", "supergroup", 200)
    subs.touch_contact(db, "telegram", "111", "Dana", "private", 100)
    http.script = [(200, {"ok": True, "result": []})]
    assert cli.main(["telegram", "admin-id", "--write", "--config", str(cfgp)]) == 0
    assert config.telegram_admin_ids(config.load(cfgp)) == [111]


def test_chat_id_also_lists_contacts_the_bot_recorded(db, cfgp, http, capsys):
    subs.touch_contact(db, "telegram", "111", "Dana", "private", 1790000000)
    http.script = [fail(409, "Conflict: terminated by other getUpdates request")]  # the bot is polling
    assert cli.main(["telegram", "chat-id", "--config", str(cfgp)]) == 0
    assert "111  private  Dana" in capsys.readouterr().out
