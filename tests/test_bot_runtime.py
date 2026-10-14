"""dbw/bot.py runtime: the long-poll loop, the saved offset, the single-instance lock, the log, `dbw bot run`.
Offline: Telegram is the fake `_http`."""
import http.client as httpclient
import json
import sqlite3

import pytest

from dbw import bot as botmod, cli, config, registry, store, subscribers as subs
from dbw.i18n import Msg
from test_bot import msg
from test_telegram import TOKEN, Http, fail, http  # noqa: F401


def updates(*u):
    return 200, {"ok": True, "result": list(u)}


def numbered(n, update):
    return {**update, "update_id": n}


@pytest.fixture
def b(tmp_path, http):
    return botmod.Bot(store.connect(tmp_path / "t.sqlite"), TOKEN, admin_ids=[], log=lambda m: None)


def test_poll_once_handles_the_batch_and_saves_the_next_offset(b, http):
    http.script = [updates(numbered(5, msg("/start")), numbered(6, msg("hi", chat=222)))]
    assert b.poll_once() == 2
    assert json.loads(http.calls[0].body) == {"timeout": 25}
    assert subs.get_state(b.conn, botmod.OFFSET_KEY) == "7"
    http.script = [updates()]
    b.poll_once()
    assert json.loads(http.calls[-1].body) == {"timeout": 25, "offset": 7}


def test_the_offset_is_saved_so_a_restart_does_not_replay(tmp_path, http):
    path = tmp_path / "t.sqlite"
    http.script = [updates(numbered(5, msg("/start")))]
    botmod.Bot(store.connect(path), TOKEN, admin_ids=[], log=lambda m: None).poll_once()
    again = botmod.Bot(store.connect(path), TOKEN, admin_ids=[], log=lambda m: None)
    http.script = [updates()]
    again.poll_once()
    assert json.loads(http.calls[-1].body)["offset"] == 6


def test_one_bad_update_is_logged_and_skipped(tmp_path, http, monkeypatch):
    logged = []
    b = botmod.Bot(store.connect(tmp_path / "t.sqlite"), TOKEN, admin_ids=[], log=logged.append)
    real = b.handle
    monkeypatch.setattr(b, "handle", lambda u: (_ for _ in ()).throw(KeyError("boom")) if u["update_id"] == 5 else real(u))
    http.script = [updates(numbered(5, msg("x")), numbered(6, msg("/start")))]
    assert b.poll_once() == 2
    assert subs.get_state(b.conn, botmod.OFFSET_KEY) == "7" and any("update 5" in l and "boom" in l for l in logged)


def test_a_busy_database_keeps_the_update_for_the_next_poll(tmp_path, http):
    path, logged = tmp_path / "t.sqlite", []
    conn = store.connect(path)
    conn.execute("PRAGMA busy_timeout = 0")  # fail at once instead of waiting
    b = botmod.Bot(conn, TOKEN, admin_ids=[], log=logged.append)
    other = sqlite3.connect(path)  # stands in for `dbw run` in the middle of a write
    other.execute("BEGIN IMMEDIATE")
    http.script = [updates(numbered(5, msg("/start")))]
    assert b.poll_once() == 0
    assert subs.get_state(conn, botmod.OFFSET_KEY) is None and any("database busy" in l for l in logged)
    other.rollback()
    http.script = [updates(numbered(5, msg("/start")))]  # Telegram sends it again: the offset was not moved
    assert b.poll_once() == 1 and subs.get_state(conn, botmod.OFFSET_KEY) == "6"


def test_a_database_error_that_is_not_busy_skips_the_update(tmp_path, http, monkeypatch):
    logged = []
    b = botmod.Bot(store.connect(tmp_path / "t.sqlite"), TOKEN, admin_ids=[], log=logged.append)
    monkeypatch.setattr(b, "handle", lambda u: (_ for _ in ()).throw(sqlite3.OperationalError("no such table: x")))
    http.script = [updates(numbered(5, msg("x")))]
    assert b.poll_once() == 1 and subs.get_state(b.conn, botmod.OFFSET_KEY) == "6"


def test_the_loop_waits_after_a_telegram_error_and_goes_on(b, http, monkeypatch):
    monkeypatch.setattr(b, "register_commands", lambda: None)  # the script is for getUpdates
    http.script = [fail(409, "Conflict: terminated by other getUpdates request"), updates(numbered(1, msg("/start")))]
    slept, logged, polls = [], [], iter([False, False, True])
    botmod.run(b, logged.append, stop=lambda: next(polls), sleep=slept.append)
    assert slept == [botmod.ERROR_WAIT] and subs.get_state(b.conn, botmod.OFFSET_KEY) == "2"
    assert any("409" in l for l in logged)


def test_the_loop_survives_an_error_that_is_not_telegrams(b, monkeypatch):
    answers = iter([httpclient.IncompleteRead(b""), []])

    def get_updates(token, offset=None, timeout=0):
        a = next(answers)
        if isinstance(a, Exception):
            raise a
        return a
    monkeypatch.setattr(botmod.telegram, "get_updates", get_updates)
    slept, logged, polls = [], [], iter([False, False, True])
    botmod.run(b, logged.append, stop=lambda: next(polls), sleep=slept.append)
    assert slept == [botmod.ERROR_WAIT] and any("IncompleteRead" in l for l in logged)


# --- the "/" menu -----------------------------------------------------------------------------------------------

def menus(http):
    """{(scope, language_code): [commands]} of every setMyCommands call."""
    out = {}
    for c in http.calls:
        if c.method == "setMyCommands":
            body = json.loads(c.body)
            scope = body["scope"].get("chat_id", body["scope"]["type"])
            out[(scope, body.get("language_code"))] = [x["command"] for x in body["commands"]]
    return out


def test_the_menu_is_set_for_everyone_groups_and_each_admin(tmp_path, http):
    b = botmod.Bot(store.connect(tmp_path / "t.sqlite"), TOKEN, admin_ids=[999, 888], log=lambda m: None)
    b.register_commands()
    m = menus(http)
    for code in (None, "he", "ar"):
        assert m[("all_private_chats", code)] == ["start", "edit", "stop", "help"]
        assert m[("all_group_chats", code)] == ["help"]
    assert m[(999, None)] == m[(888, None)] == ["start", "edit", "stop", "help", "add", "remove", "list"]


def test_the_menu_speaks_each_language(b, http):
    b.register_commands()
    bodies = {json.loads(c.body).get("language_code"): json.loads(c.body) for c in http.calls
              if c.method == "setMyCommands" and json.loads(c.body)["scope"]["type"] == "all_private_chats"}
    for lang in ("en", "he", "ar"):
        body = bodies[None if lang == "en" else lang]
        assert body["commands"][0]["description"] == Msg("bot.cmd_start").render(lang)


def test_an_admin_menu_is_in_the_admins_language(tmp_path, http):
    b = botmod.Bot(store.connect(tmp_path / "t.sqlite"), TOKEN, admin_ids=[999], admin_lang="he", log=lambda m: None)
    b.register_commands()
    (body,) = [json.loads(c.body) for c in http.calls if c.method == "setMyCommands"
               and json.loads(c.body)["scope"].get("chat_id") == 999]
    assert body["commands"][-1]["description"] == Msg("bot.cmd_list").render("he")


def test_a_former_admin_loses_the_admin_menu(tmp_path, http):
    path = tmp_path / "t.sqlite"
    botmod.Bot(store.connect(path), TOKEN, admin_ids=[999, 888], log=lambda m: None).register_commands()
    http.calls.clear()
    botmod.Bot(store.connect(path), TOKEN, admin_ids=[999], log=lambda m: None).register_commands()
    assert [json.loads(c.body) for c in http.calls if c.method == "deleteMyCommands"] ==         [{"scope": {"type": "chat", "chat_id": 888}}]
    http.calls.clear()
    botmod.Bot(store.connect(path), TOKEN, admin_ids=[999], log=lambda m: None).register_commands()
    assert not [c for c in http.calls if c.method == "deleteMyCommands"]


def test_a_menu_telegram_refuses_is_logged_and_the_rest_still_set(tmp_path, http):
    logged = []
    b = botmod.Bot(store.connect(tmp_path / "t.sqlite"), TOKEN, admin_ids=[999], log=logged.append)
    http.script = [fail(400, "Bad Request: something")]
    b.register_commands()
    assert any("not set" in l and "400" in l for l in logged)
    assert (999, None) in menus(http)


def test_the_loop_sets_the_menu_before_polling(b, http):
    b.admins = {999}
    botmod.run(b, lambda m: None, stop=iter([False, True]).__next__)
    methods = [c.method for c in http.calls]
    assert "setMyCommands" in methods and methods.index("setMyCommands") < methods.index("getUpdates")


def test_only_one_bot_at_a_time(tmp_path):
    p = tmp_path / "dbw-bot.lock"
    first = botmod.acquire_lock(p)
    try:
        assert botmod.lock_held(p)
        with pytest.raises(botmod.BotError, match="already running"):
            botmod.acquire_lock(p)
    finally:
        first.close()
    assert not botmod.lock_held(p)


def test_the_log_is_stamped_and_never_holds_the_token(tmp_path):
    log = botmod.file_log(tmp_path / "bot.log", TOKEN)
    log(f"failed https://api.telegram.org/bot{TOKEN}/getUpdates")
    text = (tmp_path / "bot.log").read_text(encoding="utf-8")
    assert TOKEN not in text and text.startswith("[") and text.endswith("\n")


# --- `dbw bot run` ----------------------------------------------------------------------------------------------

@pytest.fixture
def cfg(tmp_path, monkeypatch):
    p = tmp_path / "config.yaml"
    config.write(p, ["ashkelon"], tmp_path / "reports", registry.load(), formats=["md"])
    config.add_telegram_admin(p, 999)
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    return p


def test_bot_run_starts_the_loop_with_the_admins_and_releases_the_lock(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    seen = {}
    monkeypatch.setattr(botmod, "run", lambda b, log, **kw: seen.update(admins=b.admins, lang=b.admin_lang))
    assert cli.main(["bot", "--config", str(cfg)]) == 0
    assert seen == {"admins": {999}, "lang": "en"}
    assert not botmod.lock_held(botmod.lock_path())


def test_bot_run_refuses_a_second_copy(cfg, monkeypatch):
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    held = botmod.acquire_lock(botmod.lock_path())
    try:
        with pytest.raises(SystemExit, match="already running"):
            cli.main(["bot", "run", "--config", str(cfg)])
    finally:
        held.close()


def test_bot_run_without_a_token_is_one_line(cfg):
    with pytest.raises(SystemExit, match="no Telegram bot token"):
        cli.main(["bot", "run", "--config", str(cfg)])
