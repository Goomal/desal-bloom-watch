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
