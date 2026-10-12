"""The daily run and subscribers: their plants are fetched, one report per (plants, language) group, each person
gets it once a day, a failure or a 403 never stops the others. Offline: NOAA and Telegram are fakes."""
import json
from datetime import timedelta

import pytest

from dbw import cli, config, subscribers as subs
from dbw.i18n import Msg
from test_run_daily import Erddap, TODAY, env  # noqa: F401  (env is a fixture)
from test_telegram import TOKEN, fail, http  # noqa: F401  (http is a fixture)

ADMIN = 999


def add(env, address, plants, lang="en", name=None):
    return subs.add(env.db(), name or f"P{address}", "telegram", address, plants, lang, "self")


def run(env, monkeypatch, *extra):
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    env.use(Erddap(last=TODAY))
    log = env.tmp / "data" / "dbw-run.log"
    rc = cli.main(["run", "--config", env.cfg, "--log", str(log), *extra])
    return rc, log.read_text(encoding="utf-8")


def sent_to(http):
    return [json.loads(c.body)["chat_id"] for c in http.calls if c.method == "sendMessage"]


def docs_to(http):
    return [c for c in http.calls if c.method == "sendDocument"]


def test_subscriber_plants_are_fetched_too(env, http, monkeypatch):
    add(env, "1", ["hadera"])  # config.yaml has ashkelon only
    run(env, monkeypatch)
    n = env.db().execute("SELECT COUNT(*) FROM obs WHERE box='hadera'").fetchone()[0]
    assert n > 0


def test_one_report_per_group_and_each_person_gets_it(env, http, monkeypatch):
    add(env, "1", ["hadera"], "he")
    add(env, "2", ["hadera"], "he")
    add(env, "3", ["ashkelon"], "en")
    rc, log = run(env, monkeypatch)
    assert rc == 0 and log.rstrip().endswith("RESULT ok")
    groups = sorted(p.name for p in (env.reports / "subscribers" / str(TODAY)).iterdir())
    assert groups == ["en-ashkelon", "he-hadera"]
    he_html = (env.reports / "subscribers" / str(TODAY) / "he-hadera" / f"dbw-report-{TODAY}.html").read_bytes()
    assert sent_to(http) == ["1", "2", "3"] and len(docs_to(http)) == 3
    assert he_html in docs_to(http)[0].body and he_html in docs_to(http)[1].body
    he_txt = (env.reports / "subscribers" / str(TODAY) / "he-hadera" / f"dbw-report-{TODAY}.txt").read_text(encoding="utf-8")
    assert json.loads(http.calls[0].body)["text"] == he_txt and "חדרה" in he_txt
    assert "subscribers: sent 3 of 3" in log
    assert (env.reports / f"dbw-report-{TODAY}.md").exists()  # the admin's own report is still written


def test_one_failure_does_not_stop_the_others_and_makes_the_run_partial(env, http, monkeypatch):
    for a in ("1", "2", "3"):
        add(env, a, ["ashkelon"])
    http.script = [fail(500, "Internal Server Error")]  # the first sendMessage; a 500 is not retried
    rc, log = run(env, monkeypatch)
    assert rc == 0 and log.rstrip().endswith("RESULT partial: telegram failed for 1 of 3")
    assert sent_to(http) == ["1", "2", "3"]
    assert [s.last_sent for s in subs.active(env.db())] == [None, str(TODAY), str(TODAY)]


def test_a_403_removes_the_subscriber_and_tells_the_admin(env, http, monkeypatch):
    config.add_telegram_admin(env.cfg, ADMIN)
    add(env, "1", ["ashkelon"], name="Dana")
    add(env, "2", ["ashkelon"])
    http.script = [fail(403, "Forbidden: bot was blocked by the user")]
    rc, log = run(env, monkeypatch)
    assert rc == 0 and log.rstrip().endswith("RESULT ok")
    assert [s.address for s in subs.active(env.db())] == ["2"]
    admin_msgs = [json.loads(c.body)["text"] for c in http.calls
                  if c.method == "sendMessage" and json.loads(c.body)["chat_id"] == str(ADMIN)]
    assert admin_msgs == [Msg("bot.admin_blocked", name="Dana").render("en")]
    assert "1 removed" in log


def test_a_second_run_the_same_day_sends_nothing_new(env, http, monkeypatch):
    add(env, "1", ["ashkelon"])
    run(env, monkeypatch)
    n = len(http.calls)
    rc, log = run(env, monkeypatch)
    assert len(http.calls) == n and "subscribers: sent 0 of 0" in log


def test_a_dated_run_never_sends_to_subscribers(env, http, monkeypatch):
    add(env, "1", ["ashkelon"])
    monkeypatch.setenv("DBW_TELEGRAM_TOKEN", TOKEN)
    monkeypatch.setattr(cli, "build_providers", lambda names=None: {})  # a dated run fetches per day; nothing to fetch
    assert cli.main(["run", "--config", env.cfg, "--date", (TODAY - timedelta(days=3)).isoformat()]) == 0
    assert http.calls == [] and subs.active(env.db())[0].last_sent is None


def test_a_plant_gone_from_the_registry_is_skipped_not_fatal(env, http, monkeypatch):
    add(env, "1", ["ashkelon", "atlantis"])
    rc, log = run(env, monkeypatch)
    assert rc == 0 and sent_to(http) == ["1"]
    assert (env.reports / "subscribers" / str(TODAY) / "en-ashkelon-atlantis").is_dir()


def test_no_token_is_a_partial_run_naming_every_subscriber(env, http, monkeypatch):
    add(env, "1", ["ashkelon"])
    add(env, "2", ["ashkelon"])
    env.use(Erddap(last=TODAY))
    log = env.tmp / "run.log"
    assert cli.main(["run", "--config", env.cfg, "--log", str(log)]) == 0
    text = log.read_text(encoding="utf-8")
    assert text.rstrip().endswith("RESULT partial: telegram failed for 2 of 2") and http.calls == []


def test_no_subscribers_means_no_token_needed_and_no_line(env, http, monkeypatch):
    env.use(Erddap(last=TODAY))
    log = env.tmp / "run.log"
    assert cli.main(["run", "--config", env.cfg, "--log", str(log)]) == 0
    assert "subscribers:" not in log.read_text(encoding="utf-8") and log.read_text(encoding="utf-8").rstrip().endswith("RESULT ok")
