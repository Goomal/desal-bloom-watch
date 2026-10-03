"""Telegram in config.yaml, `dbw telegram chat-id`, `dbw send-test telegram`, the scheduled run and `dbw setup`.
Offline: the Telegram HTTP layer and the NOAA fetch are fakes; the fake token is built at run time."""
import json

import pytest
import yaml

from dbw import cli, climatology, config, registry, schedule
from dbw.channels import telegram
from test_run_daily import Erddap, TODAY, down, env  # noqa: F401  (env is a fixture)
from test_setup import Recorder
from test_telegram import TOKEN, UPDATES, Http, fail, http  # noqa: F401  (http is a fixture)

PRIVATE = {"update_id": 1, "message": {"date": 1790000000, "chat": {"id": 111, "type": "private", "first_name": "Shay"}}}
GROUP = {"update_id": 2, "message": {"date": 1790001000, "chat": {"id": -100222, "type": "supergroup", "title": "Plant ops"}}}


def updates(*u):
    return (200, {"ok": True, "result": list(u)})


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    p = tmp_path / "config.yaml"
    config.write(p, ["ashkelon"], tmp_path / "reports", registry.load(), formats=["md", "txt"])
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    return p


def chats_in(path):
    return config.load(path)["channels"]["telegram"]["chat_ids"]


# --- config ---------------------------------------------------------------------------------------------------

def check(channels):
    return config.check({"plants": ["hadera"], "channels": channels})


def test_a_valid_telegram_block_loads():
    check({"telegram": {"enabled": True, "chat_ids": [111, "-100222"]}})
    check({"telegram": {"enabled": False}})  # off: no ids needed
    check({"email": {"anything": 1}})  # channels that are not built yet are ignored


@pytest.mark.parametrize("channels, why", [
    (["telegram"], "channels"),
    ({"telegram": "yes"}, "telegram"),
    ({"telegram": {"enabled": "yes", "chat_ids": [1]}}, "enabled"),
    ({"telegram": {"enabled": True}}, "chat_ids"),
    ({"telegram": {"enabled": True, "chat_ids": []}}, "chat_ids"),
    ({"telegram": {"enabled": True, "chat_ids": 111}}, "chat_ids"),
    ({"telegram": {"enabled": True, "chat_ids": ["abc"]}}, "abc"),
    ({"telegram": {"enabled": True, "chat_ids": [True]}}, "chat_ids"),
    ({"telegram": {"enabled": True, "chat_ids": [1.5]}}, "chat_ids"),
])
def test_a_bad_telegram_block_is_a_one_line_config_error(channels, why):
    with pytest.raises(config.ConfigError, match=why):
        check(channels)


def test_telegram_chat_ids_are_strings_and_empty_unless_enabled():
    assert config.telegram_chat_ids(check({"telegram": {"enabled": True, "chat_ids": [111, "-100222"]}})) == ["111", "-100222"]
    assert config.telegram_chat_ids(check({"telegram": {"enabled": False, "chat_ids": [1]}})) == []
    assert config.telegram_chat_ids({"plants": ["hadera"]}) == [] and config.telegram_chat_ids(None) == []


def test_add_telegram_chat_enables_it_keeps_the_rest_and_does_not_repeat_an_id(cfg):
    before = config.load(cfg)
    config.add_telegram_chat(cfg, 111)
    config.add_telegram_chat(cfg, -100222)
    config.add_telegram_chat(cfg, "111")
    after = config.load(cfg)
    assert after["channels"]["telegram"] == {"enabled": True, "chat_ids": [111, -100222]}
    assert {k: v for k, v in after.items() if k != "channels"} == before


# --- dbw telegram chat-id -----------------------------------------------------------------------------------------

def test_chat_id_lists_the_chats_and_changes_nothing_without_write(cfg, http, capsys):
    http.script = [updates(PRIVATE, GROUP)]
    assert cli.main(["telegram", "chat-id", "--config", str(cfg)]) == 0
    out = capsys.readouterr().out
    assert "111  private  Shay" in out and "-100222  supergroup  Plant ops" in out and TOKEN not in out
    assert "channels" not in config.load(cfg)


def test_chat_id_with_no_updates_says_to_message_the_bot_first(cfg, http, capsys):
    http.script = [updates()]
    assert cli.main(["telegram", "chat-id", "--config", str(cfg)]) == 1
    assert "send your bot a message first" in capsys.readouterr().out


def test_chat_id_write_with_one_chat_adds_it(cfg, http, capsys):
    http.script = [updates(PRIVATE)]
    assert cli.main(["telegram", "chat-id", "--write", "--config", str(cfg)]) == 0
    assert config.load(cfg)["channels"]["telegram"] == {"enabled": True, "chat_ids": [111]}
    assert "111" in capsys.readouterr().out


def test_chat_id_write_never_picks_silently_between_several_chats(cfg, http):
    http.script = [updates(PRIVATE, GROUP)]
    with pytest.raises(SystemExit, match="--pick"):
        cli.main(["telegram", "chat-id", "--write", "--config", str(cfg)])
    assert "channels" not in config.load(cfg)


def test_chat_id_write_pick_adds_the_chosen_group_next_to_the_private_chat(cfg, http):
    config.add_telegram_chat(cfg, 111)
    http.script = [updates(PRIVATE, GROUP)]
    assert cli.main(["telegram", "chat-id", "--write", "--pick", "-100222", "--config", str(cfg)]) == 0
    assert chats_in(cfg) == [111, -100222]


def test_chat_id_pick_must_be_one_of_the_chats(cfg, http):
    http.script = [updates(PRIVATE)]
    with pytest.raises(SystemExit, match="999"):
        cli.main(["telegram", "chat-id", "--write", "--pick", "999", "--config", str(cfg)])


def test_chat_id_pick_without_write_is_refused(cfg, http):
    with pytest.raises(SystemExit, match="--write"):
        cli.main(["telegram", "chat-id", "--pick", "111", "--config", str(cfg)])


def test_chat_id_write_needs_a_config(tmp_path, monkeypatch, http):
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    http.script = [updates(PRIVATE)]
    with pytest.raises(SystemExit, match="dbw setup"):
        cli.main(["telegram", "chat-id", "--write", "--config", str(tmp_path / "none.yaml")])


def test_chat_id_without_a_token_is_one_line_naming_the_variable(cfg, monkeypatch):
    monkeypatch.delenv("DBW_TELEGRAM_TOKEN")
    with pytest.raises(SystemExit) as e:
        cli.main(["telegram", "chat-id", "--config", str(cfg)])
    assert "DBW_TELEGRAM_TOKEN" in str(e.value) and "\n" not in str(e.value)


def test_the_token_is_read_from_the_dotenv_next_to_the_config(cfg, monkeypatch, http, capsys):
    monkeypatch.delenv("DBW_TELEGRAM_TOKEN")
    (cfg.parent / ".env").write_text(f"DBW_TELEGRAM_TOKEN={TOKEN}\n", encoding="utf-8")
    http.script = [updates(PRIVATE)]
    assert cli.main(["telegram", "chat-id", "--config", str(cfg)]) == 0
    assert http.calls[0].url == f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    assert TOKEN not in capsys.readouterr().out


def test_a_telegram_error_is_one_redacted_line(cfg, http):
    http.script = [fail(401, f"Unauthorized bot{TOKEN}")]
    with pytest.raises(SystemExit) as e:
        cli.main(["telegram", "chat-id", "--config", str(cfg)])
    assert str(e.value) == "getUpdates: HTTP 401: Unauthorized bot<redacted>"


# --- dbw send-test telegram ---------------------------------------------------------------------------------------

def test_send_test_sends_one_message_to_each_chat(cfg, http, capsys):
    config.add_telegram_chat(cfg, 111)
    config.add_telegram_chat(cfg, -100222)
    assert cli.main(["send-test", "telegram", "--config", str(cfg)]) == 0
    sent = [json.loads(c.body) for c in http.calls]
    assert sent == [{"chat_id": "111", "text": cli.TELEGRAM_TEST_TEXT}, {"chat_id": "-100222", "text": cli.TELEGRAM_TEST_TEXT}]
    assert cli.TELEGRAM_TEST_TEXT == "Desal Bloom Watch test: the bot can reach this chat."
    out = capsys.readouterr().out
    assert "chat 111: ok" in out and "chat -100222: ok" in out and TOKEN not in out


def test_send_test_reports_each_failure_and_exits_non_zero(cfg, http, capsys):
    config.add_telegram_chat(cfg, 111)
    config.add_telegram_chat(cfg, 222)
    http.script = [fail(403, "Forbidden: bot was blocked by the user")]
    assert cli.main(["send-test", "telegram", "--config", str(cfg)]) == 1
    out = capsys.readouterr().out
    assert "chat 111: sendMessage: HTTP 403: Forbidden: bot was blocked by the user" in out and "chat 222: ok" in out


def test_send_test_when_telegram_is_not_enabled_says_how(cfg):
    with pytest.raises(SystemExit, match="chat-id --write"):
        cli.main(["send-test", "telegram", "--config", str(cfg)])


def write_report_files(cfg, stem="dbw-report-2026-10-02", html=True):
    out = config.report_settings(config.load(cfg))[0]
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{stem}.txt").write_text("Desal Bloom Watch 2026-10-02: ORANGE (eilat)\n\nEilat: orange.\n", encoding="utf-8")
    if html:
        (out / f"{stem}.html").write_text("<html>report</html>", encoding="utf-8")
    return out


def test_send_test_latest_adds_the_newest_short_message_and_html(cfg, http, capsys):
    config.add_telegram_chat(cfg, 111)
    out = write_report_files(cfg, "dbw-report-2026-10-01")
    write_report_files(cfg, "dbw-report-2026-10-02")
    (out / "dbw-report-2026-10-01.txt").write_text("OLD", encoding="utf-8")
    assert cli.main(["send-test", "telegram", "--latest", "--config", str(cfg)]) == 0
    assert [c.method for c in http.calls] == ["sendMessage", "sendMessage", "sendDocument"]
    assert json.loads(http.calls[1].body)["text"].startswith("Desal Bloom Watch 2026-10-02: ORANGE")
    assert b"<html>report</html>" in http.calls[2].body and b"Desal Bloom Watch 2026-10-02: ORANGE (eilat)" in http.calls[2].body


def test_send_test_latest_without_a_report_still_sends_the_test_and_says_so(cfg, http, capsys):
    config.add_telegram_chat(cfg, 111)
    assert cli.main(["send-test", "telegram", "--latest", "--config", str(cfg)]) == 0
    assert [c.method for c in http.calls] == ["sendMessage"]
    assert "no report" in capsys.readouterr().out


# --- the scheduled run --------------------------------------------------------------------------------------------

def run_with_telegram(env, http, monkeypatch, *chats, script=()):
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    for c in chats:
        config.add_telegram_chat(env.cfg, c)
    http.script = list(script)
    env.use(Erddap(last=TODAY))
    log = env.tmp / "data" / "dbw-run.log"
    return cli.main(["run", "--config", env.cfg, "--log", str(log)]), log


def test_the_run_sends_the_short_message_then_the_html_to_each_chat(env, http, monkeypatch):
    rc, log = run_with_telegram(env, http, monkeypatch, 111, -100222)
    assert rc == 0 and log.read_text(encoding="utf-8").rstrip().endswith("RESULT ok")
    assert [c.method for c in http.calls] == ["sendMessage", "sendDocument"] * 2
    txt = (env.reports / f"dbw-report-{TODAY}.txt").read_text(encoding="utf-8")
    html = (env.reports / f"dbw-report-{TODAY}.html").read_bytes()  # formats were md+txt: html is made because telegram needs it
    assert json.loads(http.calls[0].body) == {"chat_id": "111", "text": txt}
    assert html in http.calls[1].body and txt.splitlines()[0].encode("utf-8") in http.calls[1].body
    assert json.loads(http.calls[2].body)["chat_id"] == "-100222"
    assert "telegram: sent to 111" in log.read_text(encoding="utf-8") and TOKEN not in log.read_text(encoding="utf-8")


def test_the_run_writes_only_the_configured_files_when_telegram_is_off(env, http):
    env.use(Erddap(last=TODAY))
    assert cli.main(["run", "--config", env.cfg]) == 0
    assert not (env.reports / f"dbw-report-{TODAY}.html").exists() and http.calls == []


def test_a_failed_send_never_stops_the_report_and_makes_the_run_partial(env, http, monkeypatch, capsys):
    rc, log = run_with_telegram(env, http, monkeypatch, 111, 222, script=[fail(403, "Forbidden: bot was blocked by the user")])
    text = log.read_text(encoding="utf-8")
    assert rc == 0 and text.rstrip().endswith("RESULT partial: telegram failed")
    assert "telegram: failed for 111: sendMessage: HTTP 403: Forbidden: bot was blocked by the user" in text
    assert "telegram: sent to 222" in text  # the next chat is still tried
    assert (env.reports / f"dbw-report-{TODAY}.txt").exists() and (env.reports / f"dbw-report-{TODAY}.md").exists()
    monkeypatch.setattr(cli, "_root", lambda: env.tmp)
    from test_schedule import FakeRun
    monkeypatch.setattr(schedule, "_call", FakeRun({("crontab", "-l"): (1, "", "no crontab")}))
    cli.main(["schedule", "status", "--runner", "cron", "--config", env.cfg])
    assert "partial: telegram failed" in capsys.readouterr().out


def test_a_missing_token_is_a_telegram_failure_not_a_crash(env, http, monkeypatch):
    config.add_telegram_chat(env.cfg, 111)
    env.use(Erddap(last=TODAY))
    log = env.tmp / "run.log"
    assert cli.main(["run", "--config", env.cfg, "--log", str(log)]) == 0
    text = log.read_text(encoding="utf-8")
    assert "telegram: failed: no Telegram bot token" in text and text.rstrip().endswith("RESULT partial: telegram failed")
    assert http.calls == [] and (env.reports / f"dbw-report-{TODAY}.txt").exists()


def test_noaa_down_and_telegram_down_are_both_named(env, http, monkeypatch):
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    config.add_telegram_chat(env.cfg, 111)
    http.script = [fail(500, "Internal Server Error")]
    env.use(down("HTTP 502"))
    log = env.tmp / "run.log"
    assert cli.main(["run", "--config", env.cfg, "--log", str(log)]) == 0
    assert log.read_text(encoding="utf-8").rstrip().endswith("RESULT partial: upstream unreachable, telegram failed")


def test_a_run_without_report_sends_nothing(env, http, monkeypatch):
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    config.add_telegram_chat(env.cfg, 111)
    env.use(Erddap(last=TODAY))
    assert cli.main(["run", "--config", env.cfg, "--no-report"]) == 0
    assert http.calls == []


# --- dbw setup ----------------------------------------------------------------------------------------------------

@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    monkeypatch.setattr(climatology, "backfill", Recorder())
    return ["setup", "--plants", "hadera", "--out", str(tmp_path / "reports"), "--config", str(tmp_path / "config.yaml")]


def test_setup_yes_does_not_set_up_telegram(setup_env, tmp_path):
    assert cli.main(setup_env + ["--yes"]) == 0  # the blocked http would fail the test if telegram were touched
    assert "channels" not in config.load(tmp_path / "config.yaml")


def test_setup_telegram_flag_explains_the_steps_and_writes_the_chat_id(setup_env, tmp_path, monkeypatch, http, capsys):
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    http.script = [updates(PRIVATE)]
    assert cli.main(setup_env + ["--yes", "--telegram"]) == 0
    out = capsys.readouterr().out
    assert "@BotFather" in out and "DBW_TELEGRAM_TOKEN" in out and TOKEN not in out
    assert chats_in(tmp_path / "config.yaml") == [111]


def test_setup_telegram_with_several_chats_refuses_without_a_pick(setup_env, tmp_path, monkeypatch, http, capsys):
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    http.script = [updates(PRIVATE, GROUP)]
    assert cli.main(setup_env + ["--yes", "--telegram"]) == 1
    assert "--pick" in capsys.readouterr().err and "channels" not in config.load(tmp_path / "config.yaml")


def test_setup_telegram_flags_exclude_each_other(setup_env):
    with pytest.raises(SystemExit):
        cli.main(setup_env + ["--yes", "--telegram", "--no-telegram"])


def test_setup_telegram_token_missing_is_one_line_and_setup_still_finishes_its_report(setup_env, tmp_path, capsys):
    assert cli.main(setup_env + ["--yes", "--telegram"]) == 1
    err = capsys.readouterr().err
    assert "DBW_TELEGRAM_TOKEN" in err and "chat-id --write" in err
    assert (tmp_path / "reports").exists()


def test_setup_asks_about_telegram_after_the_daily_run_question(setup_env, tmp_path, monkeypatch, http, capsys):
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    http.script = [updates(PRIVATE)]
    asked, answers = [], iter(["n", "y", "", ])  # daily run: no; telegram: yes; Enter after the three steps
    monkeypatch.setattr("builtins.input", lambda prompt="": asked.append(prompt) or next(answers))
    assert cli.main(setup_env + ["--language", "en"]) == 0
    assert "Run this every day" in asked[0] and asked[1] == "Send the daily report to Telegram? [y/N] "
    assert len(asked) == 3 and "Enter" in asked[2]
    assert chats_in(tmp_path / "config.yaml") == [111]


def test_setup_telegram_question_defaults_to_no(setup_env, tmp_path, monkeypatch):
    answers = iter(["n", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert cli.main(setup_env + ["--language", "en"]) == 0
    assert "channels" not in config.load(tmp_path / "config.yaml")


def test_setup_no_telegram_flag_asks_nothing(setup_env, monkeypatch):
    answers = iter(["n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))  # only the daily-run question
    assert cli.main(setup_env + ["--language", "en", "--no-telegram"]) == 0


def test_any_exception_in_the_send_is_a_logged_redacted_failure_not_a_crash(env, monkeypatch):
    def boom(url, body, ctype):
        raise RuntimeError(f"surprise at {url}")
    monkeypatch.setattr(telegram, "_http", boom)
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    config.add_telegram_chat(env.cfg, 111)
    env.use(Erddap(last=TODAY))
    log = env.tmp / "run.log"
    assert cli.main(["run", "--config", env.cfg, "--log", str(log)]) == 0
    text = log.read_text(encoding="utf-8")
    assert "telegram: failed for 111: surprise at https://api.telegram.org/bot<redacted>/sendMessage" in text
    assert TOKEN not in text and text.rstrip().endswith("RESULT partial: telegram failed")
    assert (env.reports / f"dbw-report-{TODAY}.txt").exists()
