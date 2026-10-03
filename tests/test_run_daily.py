"""The scheduled `dbw run` (no date): catch-up fetch, an unreachable NOAA as a partial run and not a crash,
the run log, and utf-8 output whatever the console charset. Offline: ERDDAP is a fake `get`."""
import functools
import io
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from dbw import cli, climatology, config, registry, schedule, store
from dbw.providers.base import FetchError, NoData
from test_schedule import FakeRun

TODAY = datetime.now(timezone.utc).date()
DINEOF = "noaacwNPPN20VIIRSDINEOFDaily"
REAL_BACKFILL = climatology.backfill


class Erddap:
    """A griddap holding every UTC day up to `last`; pixels sit on the requested bbox edges and midpoint."""

    def __init__(self, last):
        self.last, self.urls = last, []

    def __call__(self, url):
        self.urls.append(url)
        q = urllib.parse.unquote(url)
        t0 = date_of(re.search(r"\((\d{4}-\d\d-\d\d)T12:00:00Z\):1:", q).group(1))
        la0, la1, lo0, lo1 = (float(x) for x in re.search(
            r"\[\(([\d.-]+)\):1:\(([\d.-]+)\)\]\[\(([\d.-]+)\):1:\(([\d.-]+)\)\]$", q).groups())
        rows = ["time,latitude,longitude,chlor_a", "UTC,degrees_north,degrees_east,mg m^-3"]
        d = t0
        while d <= self.last:
            rows += [f"{d}T12:00:00Z,{la},{lo},{d.day}.0" for la in (la0, (la0 + la1) / 2, la1)
                     for lo in (lo0, (lo0 + lo1) / 2, lo1)]
            d += timedelta(days=1)
        return "\n".join(rows) + "\n"


def date_of(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def down(reason):
    def get(url):
        raise FetchError(reason, reachable=False)
    return get


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    cfg = tmp_path / "config.yaml"
    config.write(cfg, ["ashkelon"], tmp_path / "reports", registry.load(), formats=["md", "txt"])

    def use(get):
        monkeypatch.setattr(climatology, "backfill", functools.partial(REAL_BACKFILL, get=get, sleep=lambda s: None))
    return SimpleNamespace(tmp=tmp_path, cfg=str(cfg), use=use, db=lambda: store.connect(tmp_path / "t.sqlite"),
                           reports=tmp_path / "reports")


def newest(conn, source=DINEOF, box="ashkelon"):
    return conn.execute("SELECT MAX(date) FROM obs WHERE source=? AND box=? AND stat='median'", (source, box)).fetchone()[0]


# --- catch-up ---------------------------------------------------------------------------------------

def test_run_without_a_date_fetches_what_has_arrived_and_reports_for_today(env):
    env.use(Erddap(last=TODAY - timedelta(days=2)))
    assert cli.main(["run", "--config", env.cfg]) == 0
    conn = env.db()
    assert newest(conn) == (TODAY - timedelta(days=2)).isoformat()
    assert conn.execute("SELECT COUNT(*) FROM obs WHERE date=? AND stat='valid_count' AND value=0",
                        (TODAY.isoformat(),)).fetchone()[0] == 0  # no "no data" row for a slice that has not landed yet
    assert (env.reports / f"dbw-report-{TODAY}.txt").exists() and (env.reports / f"dbw-report-{TODAY}.md").exists()


def test_run_catch_up_fills_days_missed_while_the_machine_was_off(env):
    env.use(Erddap(last=TODAY - timedelta(days=7)))
    cli.main(["run", "--config", env.cfg])
    env.use(Erddap(last=TODAY - timedelta(days=2)))
    cli.main(["run", "--config", env.cfg])
    days = {r[0] for r in env.db().execute("SELECT DISTINCT date FROM obs WHERE source=? AND box='ashkelon'", (DINEOF,))}
    assert {(TODAY - timedelta(days=n)).isoformat() for n in range(2, 8)} <= days


def test_run_catch_up_replaces_a_stale_nodata_row(env):
    conn = env.db()
    day = TODAY - timedelta(days=2)
    store.write_result(conn, day, DINEOF, "ashkelon", NoData("no slice for today", reachable=True))
    env.use(Erddap(last=day))
    cli.main(["run", "--config", env.cfg])
    assert newest(env.db()) == day.isoformat()


def test_run_twice_changes_nothing(env):
    env.use(Erddap(last=TODAY - timedelta(days=2)))
    cli.main(["run", "--config", env.cfg])
    n = store.count(env.db())
    cli.main(["run", "--config", env.cfg])
    assert store.count(env.db()) == n


# --- NOAA unreachable ----------------------------------------------------------------------------------

@pytest.mark.parametrize("reason", ["HTTP 502", "network: timed out"])
def test_noaa_down_still_scores_from_the_database_and_says_so(env, reason, capsys):
    last = TODAY - timedelta(days=3)
    env.use(Erddap(last=last))
    cli.main(["run", "--config", env.cfg])
    before = store.count(env.db())
    env.use(down(reason))
    assert cli.main(["run", "--config", env.cfg]) == 0
    note = f"NOAA data could not be fetched today ({reason}); values are from {last}"
    for fmt in ("txt", "md"):
        assert note in (env.reports / f"dbw-report-{TODAY}.{fmt}").read_text(encoding="utf-8")
    assert store.count(env.db()) == before  # nothing was overwritten with "no data"
    assert "partial" in capsys.readouterr().out


def test_the_run_writes_the_note_in_the_configured_language(env):
    config.write(env.tmp / "he.yaml", ["ashkelon"], env.tmp / "he-reports", registry.load(), formats=["txt"],
                       language="he")
    last = TODAY - timedelta(days=3)
    env.use(Erddap(last=last))
    cli.main(["run", "--config", str(env.tmp / "he.yaml")])
    env.use(down("HTTP 502"))
    assert cli.main(["run", "--config", str(env.tmp / "he.yaml")]) == 0
    text = (env.tmp / "he-reports" / f"dbw-report-{TODAY}.txt").read_text(encoding="utf-8")
    assert "NOAA" in text and "HTTP 502" in text and str(last) in text and "לא ניתן" in text


def test_a_run_with_an_explicit_date_and_a_down_provider_stores_nothing_and_is_partial(env, monkeypatch, capsys):
    class Down:
        source = "src_down"

        def fetch(self, box, day):
            return NoData("HTTP 502", reachable=False)

    monkeypatch.setattr(cli, "build_providers", lambda names=None: {"src_down": Down()})
    assert cli.main(["run", "--date", "2026-09-27", "--config", env.cfg]) == 0
    assert store.count(env.db()) == 0
    assert "could not be fetched" in capsys.readouterr().out


def test_every_fetching_command_prints_one_plain_line_when_noaa_is_down(env, capsys):
    env.use(down("HTTP 502"))
    cases = [["backfill", "--from", "2026-09-01", "--to", "2026-09-10"],
             ["setup", "--plants", "hadera", "--out", str(env.tmp / "r"), "--config", str(env.tmp / "new.yaml"), "--yes"]]
    for argv in cases:
        capsys.readouterr()
        assert cli.main(argv) == 1  # a plain exit code, not a traceback
        err = capsys.readouterr().err.strip().splitlines()
        assert len(err) == 1 and err[0].startswith("NOAA data could not be fetched"), (argv, err)


# --- the run log -----------------------------------------------------------------------------------------

def test_run_log_gets_the_output_and_a_result_line_and_status_reads_it(env, monkeypatch, capsys):
    env.use(Erddap(last=TODAY - timedelta(days=3)))
    cli.main(["run", "--config", env.cfg])
    log = env.tmp / "data" / "dbw-run.log"
    env.use(down("HTTP 502"))
    assert cli.main(["run", "--config", env.cfg, "--log", str(log)]) == 0
    text = log.read_text(encoding="utf-8")
    assert "dbw run start" in text and text.rstrip().endswith("RESULT partial: upstream unreachable")
    assert "NOAA data could not be fetched today" in text
    monkeypatch.setattr(cli, "_root", lambda: env.tmp)
    monkeypatch.setattr(schedule, "_call", FakeRun({("crontab", "-l"): (1, "", "no crontab")}))
    capsys.readouterr()
    assert cli.main(["schedule", "status", "--runner", "cron", "--config", env.cfg]) == 0
    assert "partial: upstream unreachable" in capsys.readouterr().out


def test_a_failed_run_leaves_the_reason_in_the_log_and_exits_non_zero(env):
    log = env.tmp / "run.log"
    assert cli.main(["run", "--config", env.cfg, "--plants", "nope", "--log", str(log)]) == 1
    assert "RESULT failed: unknown plant id(s): nope" in log.read_text(encoding="utf-8")


def test_a_run_with_no_config_logs_a_failure_and_exits_non_zero(env):
    log = env.tmp / "run.log"
    assert cli.main(["run", "--config", str(env.tmp / "none.yaml"), "--log", str(log)]) == 1
    assert "RESULT failed: no" in log.read_text(encoding="utf-8")


# --- utf-8 on the console ---------------------------------------------------------------------------------

def test_main_makes_a_cp1252_console_print_hebrew_and_emoji(monkeypatch):
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252", write_through=True))
    monkeypatch.setattr(cli, "cmd_doctor", lambda a: (print("🟢 שלום מ⁨ים⁩ ✓"), 0)[1])
    assert cli.main(["doctor"]) == 0
    assert "🟢 שלום" in raw.getvalue().decode("utf-8")


def test_main_never_crashes_on_a_stream_it_cannot_reconfigure(monkeypatch):
    class Bare:  # no .reconfigure, like some redirected streams
        def __init__(self):
            self.text = []

        def write(self, s):
            self.text.append(s)

        def flush(self):
            pass

    bare = Bare()
    monkeypatch.setattr(sys, "stdout", bare)
    monkeypatch.setattr(cli, "cmd_doctor", lambda a: (print("ok"), 0)[1])
    assert cli.main(["doctor"]) == 0 and "ok" in "".join(bare.text)


# --- the machine just woke up: wait for the network before fetching ------------------------------------

class Dns:
    """getaddrinfo that fails `fails` times (no network yet), then answers."""

    def __init__(self, fails):
        self.fails, self.calls = fails, 0

    def __call__(self, host, port):
        self.calls += 1
        if self.calls <= self.fails:
            raise OSError(8, "nodename nor servname provided, or not known")
        return [()]


def test_scheduled_run_waits_for_the_network_after_wake_up(env, monkeypatch, capsys):
    dns, slept = Dns(fails=3), []
    monkeypatch.setattr(cli, "_resolve", dns)
    monkeypatch.setattr(cli, "_sleep", slept.append)
    env.use(Erddap(last=TODAY - timedelta(days=2)))
    log = env.tmp / "data" / "dbw-run.log"
    assert cli.main(["run", "--config", env.cfg, "--log", str(log)]) == 0
    assert dns.calls == 4 and sum(slept) == 3 * cli.NETWORK_POLL
    text = log.read_text(encoding="utf-8")
    assert "network: up after" in text and text.rstrip().endswith("RESULT ok")


def test_scheduled_run_gives_up_waiting_and_runs_partial(env, monkeypatch):
    slept = []
    monkeypatch.setattr(cli, "_resolve", Dns(fails=10 ** 6))
    monkeypatch.setattr(cli, "_sleep", slept.append)
    env.use(down("network: nodename nor servname provided"))
    log = env.tmp / "data" / "dbw-run.log"
    assert cli.main(["run", "--config", env.cfg, "--log", str(log)]) == 0
    assert sum(slept) >= cli.NETWORK_WAIT
    text = log.read_text(encoding="utf-8")
    assert "network: still down after" in text and "RESULT partial" in text


def test_a_run_by_hand_does_not_wait(env, monkeypatch):
    dns = Dns(fails=10 ** 6)
    monkeypatch.setattr(cli, "_resolve", dns)
    env.use(Erddap(last=TODAY - timedelta(days=2)))
    assert cli.main(["run", "--config", env.cfg]) == 0
    assert dns.calls == 0
