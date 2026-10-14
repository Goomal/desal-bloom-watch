"""A daily report the PC missed (off, or restarting for a Windows update, at the scheduled hour): the scheduled run
never sends one day twice and never overlaps another run, and the bot starts the run once today's time has passed
and the report has not gone out. Offline: ERDDAP and Telegram are fakes."""
from datetime import datetime, timedelta, timezone

import pytest

from dbw import bot as botmod, cli, config, registry, store, subscribers as subs
from test_run_daily import Erddap, TODAY, env  # noqa: F401  (env is a fixture)
from test_telegram import TOKEN, http  # noqa: F401  (http is a fixture)


def scheduled_run(env):
    log = env.tmp / "data" / "dbw-run.log"
    return cli.main(["run", "--config", env.cfg, "--log", str(log)]), log


def last_result(log):
    return log.read_text(encoding="utf-8").rstrip().splitlines()[-1].split("RESULT ", 1)[1]


# --- the scheduled run ----------------------------------------------------------------------------------------------

def test_a_second_scheduled_run_the_same_day_sends_nothing_and_fetches_nothing(env, http, monkeypatch):
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    config.add_telegram_chat(env.cfg, 111)
    erddap = Erddap(last=TODAY)
    env.use(erddap)
    assert scheduled_run(env)[0] == 0
    sent, fetched = len(http.calls), len(erddap.urls)
    rc, log = scheduled_run(env)
    assert rc == 0 and last_result(log) == "skipped: already sent today"
    assert len(http.calls) == sent and len(erddap.urls) == fetched


def test_a_failed_send_leaves_the_day_due_so_the_next_run_tries_again(env, http, monkeypatch):
    config.add_telegram_chat(env.cfg, 111)  # no token: the send fails
    env.use(Erddap(last=TODAY))
    assert last_result(scheduled_run(env)[1]) == "partial: telegram failed"
    assert cli.due_today(env.db(), config.load(env.cfg), TODAY)
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    assert last_result(scheduled_run(env)[1]) == "ok" and [c.method for c in http.calls] == ["sendMessage", "sendDocument"]
    assert not cli.due_today(env.db(), config.load(env.cfg), TODAY)


def test_a_run_for_a_subscriber_only_does_not_send_the_configured_chats_again(env, http, monkeypatch):
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    config.add_telegram_chat(env.cfg, 111)
    env.use(Erddap(last=TODAY))
    assert scheduled_run(env)[0] == 0
    subs.add(env.db(), "Dana", "telegram", "555", ["ashkelon"], "en", "admin")  # signs up after the morning run
    http.calls.clear()
    assert scheduled_run(env)[0] == 0
    chats = {c.body.split(b'"chat_id": "', 1)[1].split(b'"', 1)[0] for c in http.calls if b'"chat_id": "' in c.body}
    assert http.calls and b"111" not in chats


def test_a_scheduled_run_stops_while_another_run_holds_the_lock(env, http):
    held = botmod.acquire_lock(cli.run_lock_path())
    try:
        rc, log = scheduled_run(env)
    finally:
        held.close()
    assert rc == 0 and last_result(log) == "skipped: another run was going"


def test_a_run_by_hand_is_never_skipped(env, http):
    env.use(Erddap(last=TODAY))
    assert cli.main(["run", "--config", env.cfg]) == 0
    (env.reports / f"dbw-report-{TODAY}.txt").unlink()
    assert cli.main(["run", "--config", env.cfg]) == 0
    assert (env.reports / f"dbw-report-{TODAY}.txt").exists()


# --- the bot's check ------------------------------------------------------------------------------------------------

IL = timezone(timedelta(hours=3))


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    return store.connect()


def checker(clock, cfg=None):
    started, logged = [], []
    cfg = {"plants": ["ashkelon"], "schedule": {"time": "07:00"}} if cfg is None else cfg
    return cli.missed_run_check(cfg, "config.yaml", logged.append, now=lambda: clock[0], start=started.append), started, logged


def test_the_bot_waits_for_the_scheduled_time(conn):
    clock = [datetime(2026, 10, 14, 6, 59, tzinfo=IL)]
    check, started, _ = checker(clock)
    check(conn)
    assert started == []


def test_the_bot_starts_a_missed_run_once_then_retries_after_an_hour(conn):
    clock = [datetime(2026, 10, 14, 8, 5, tzinfo=IL)]
    check, started, logged = checker(clock)
    check(conn)
    assert started == ["config.yaml"] and "2026-10-14" in logged[0]
    clock[0] += timedelta(minutes=59)
    check(conn)
    assert len(started) == 1
    clock[0] += timedelta(minutes=1)
    check(conn)
    assert len(started) == 2


def test_the_bot_starts_nothing_once_the_report_went_out(conn):
    subs.set_state(conn, cli.SENT_KEY, "2026-10-14")
    clock = [datetime(2026, 10, 14, 8, 5, tzinfo=IL)]
    check, started, _ = checker(clock)
    check(conn)
    assert started == []
    clock[0] = datetime(2026, 10, 15, 7, 0, tzinfo=IL)  # the next morning is due again
    check(conn)
    assert started == ["config.yaml"]


def test_the_bot_starts_nothing_while_a_run_is_going(conn):
    held = botmod.acquire_lock(cli.run_lock_path())
    try:
        check, started, _ = checker([datetime(2026, 10, 14, 8, 5, tzinfo=IL)])
        check(conn)
    finally:
        held.close()
    assert started == []


def test_without_a_schedule_the_bot_never_starts_a_run(conn):
    check, started, _ = checker([datetime(2026, 10, 14, 12, 0, tzinfo=IL)], cfg={"plants": ["ashkelon"]})
    check(conn)
    assert started == []


def test_the_bot_loop_runs_the_check_and_survives_its_errors(conn, http):
    seen, logged = [], []

    def check(c):
        seen.append(c)
        raise RuntimeError("disk full")
    b = botmod.Bot(conn, TOKEN, admin_ids=[], log=logged.append)
    botmod.run(b, logged.append, stop=lambda: len(seen) >= 2, sleep=lambda s: None, check=check)
    assert seen == [conn, conn] and "missed-run check: disk full" in logged


def test_bot_run_passes_the_check(tmp_path, monkeypatch):
    p = tmp_path / "config.yaml"
    config.write(p, ["ashkelon"], tmp_path / "reports", registry.load(), formats=["md"])
    config.set_schedule(p, "schtasks", "07:00")
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    seen = {}
    monkeypatch.setattr(botmod, "run", lambda b, log, check=None, **kw: seen.update(check=check))
    assert cli.main(["bot", "--config", str(p)]) == 0
    assert callable(seen["check"])
