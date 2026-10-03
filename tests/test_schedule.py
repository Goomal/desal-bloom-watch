"""`dbw schedule`: the launchd plist, the crontab editor and the schtasks command and XML builders as pure functions,
plus install / status / remove through a fake process runner. Nothing here touches the real launchd, crontab or
Task Scheduler, and nothing needs the network."""
import plistlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from dbw import schedule

ROOT = Path("/Users/someone/desal bloom watch")  # a space on purpose: every runner must quote it


def job(time="01:15", platform="darwin"):
    return schedule.make_job(ROOT, time, platform=platform)


class FakeRun:
    """Stands in for subprocess.run: records every call, answers from `answers[(program, first arg)]`."""

    def __init__(self, answers=None):
        self.calls, self.answers, self.inputs = [], answers or {}, []

    def __call__(self, args, input=None):
        self.calls.append(list(args))
        self.inputs.append(input)
        rc, out, err = self.answers.get((args[0], args[1] if len(args) > 1 else None), (0, "", ""))
        return SimpleNamespace(returncode=rc, stdout=out, stderr=err)


# --- runner and time ----------------------------------------------------------------------------

def test_default_runner_per_platform():
    assert schedule.default_runner("darwin") == "launchd"
    assert schedule.default_runner("linux") == "cron"
    assert schedule.default_runner("win32") == "schtasks"


def test_unknown_runner_names_the_three_options():
    with pytest.raises(schedule.ScheduleError, match="launchd.*cron.*schtasks"):
        schedule.check_runner("systemd")


@pytest.mark.parametrize("hours,expected", [(3, "01:15"), (2, "00:15"), (0, "22:15"), (-5, "17:15"), (5.5, "03:45")])
def test_arrival_time_is_the_measured_utc_time_on_the_local_clock(hours, expected):
    now = datetime(2026, 10, 2, 12, 0, tzinfo=timezone(timedelta(hours=hours)))
    assert schedule.ARRIVAL_UTC_TIME == "22:15"
    assert schedule.arrival_time(now) == expected


def test_default_time_is_seven_in_the_morning_local():
    assert schedule.default_time() == "07:00" == schedule.DEFAULT_TIME


@pytest.mark.parametrize("bad", ["25:00", "7", "07:60", "noon", "", "7:5:1"])
def test_parse_time_rejects_junk(bad):
    with pytest.raises(schedule.ScheduleError, match="HH:MM"):
        schedule.parse_time(bad)


def test_parse_time_accepts_one_digit_hours():
    assert schedule.parse_time("7:05") == (7, 5) and schedule.normalize_time("7:05") == "07:05"


def test_next_run_is_today_if_still_ahead_else_tomorrow():
    now = datetime(2026, 10, 2, 9, 0)
    assert schedule.next_run("10:30", now) == datetime(2026, 10, 2, 10, 30)
    assert schedule.next_run("08:00", now) == datetime(2026, 10, 3, 8, 0)
    assert schedule.next_run("09:00", now) == datetime(2026, 10, 3, 9, 0)


# --- the job: absolute paths, repo root as working directory, no date argument --------------------

def test_job_uses_the_repos_own_venv_and_a_log_inside_the_gitignored_data_folder():
    j = job()
    assert j.exe == ROOT / ".venv" / "bin" / "dbw" and j.log == ROOT / "data" / "dbw-run.log"
    assert j.args == ["run", "--log", str(j.log)] and "--date" not in j.args
    w = schedule.make_job(Path("C:/repo"), "01:15", platform="win32")
    assert w.exe == Path("C:/repo") / ".venv" / "Scripts" / "dbw.exe"


# --- launchd plist ----------------------------------------------------------------------------------

def test_plist_content():
    p = plistlib.loads(schedule.plist_bytes(job("01:15")))
    assert p["Label"] == schedule.LABEL == "com.desalbloomwatch.dbw"
    assert p["ProgramArguments"] == [str(job().exe), "run", "--log", str(job().log)]
    assert p["WorkingDirectory"] == str(ROOT)
    assert p["StartCalendarInterval"] == {"Hour": 1, "Minute": 15}
    assert p["StandardOutPath"] == p["StandardErrorPath"] and p["StandardOutPath"].startswith(str(ROOT / "data"))
    assert "RunAtLoad" not in p or p["RunAtLoad"] is False
    assert p["EnvironmentVariables"]["PYTHONUTF8"] == "1"


def test_plist_midnight_and_late_times():
    assert plistlib.loads(schedule.plist_bytes(job("00:05")))["StartCalendarInterval"] == {"Hour": 0, "Minute": 5}
    assert plistlib.loads(schedule.plist_bytes(job("23:59")))["StartCalendarInterval"] == {"Hour": 23, "Minute": 59}


def test_launchd_install_boots_out_the_old_job_then_bootstraps_the_new(tmp_path):
    run = FakeRun()
    lines = schedule.install("launchd", job(), run=run, home=tmp_path, uid=501)
    plist = tmp_path / "Library" / "LaunchAgents" / "com.desalbloomwatch.dbw.plist"
    assert plistlib.loads(plist.read_bytes())["StartCalendarInterval"] == {"Hour": 1, "Minute": 15}
    assert run.calls == [["launchctl", "bootout", "gui/501/com.desalbloomwatch.dbw"],
                         ["launchctl", "bootstrap", "gui/501", str(plist)]]
    assert any("01:15" in l for l in lines)


def test_launchd_install_twice_replaces_and_never_makes_two_jobs(tmp_path):
    run = FakeRun()
    schedule.install("launchd", job("01:15"), run=run, home=tmp_path, uid=501)
    schedule.install("launchd", job("03:30"), run=run, home=tmp_path, uid=501)
    agents = list((tmp_path / "Library" / "LaunchAgents").iterdir())
    assert [a.name for a in agents] == ["com.desalbloomwatch.dbw.plist"]
    assert plistlib.loads(agents[0].read_bytes())["StartCalendarInterval"] == {"Hour": 3, "Minute": 30}
    boots = [c for c in run.calls if c[1] == "bootstrap"]
    outs = [c for c in run.calls if c[1] == "bootout"]
    assert len(boots) == 2 and len(outs) == 2  # each install first removes what the last one loaded


def test_launchd_bootstrap_failure_is_an_error_with_launchctls_words(tmp_path):
    run = FakeRun({("launchctl", "bootstrap"): (5, "", "Bootstrap failed: 5: Input/output error")})
    with pytest.raises(schedule.ScheduleError, match="Input/output error"):
        schedule.install("launchd", job(), run=run, home=tmp_path, uid=501)


def test_launchd_dry_run_prints_the_plist_and_touches_nothing(tmp_path):
    run = FakeRun()
    lines = schedule.install("launchd", job(), run=run, home=tmp_path, uid=501, dry_run=True)
    assert run.calls == [] and not (tmp_path / "Library").exists()
    text = "\n".join(lines)
    assert "com.desalbloomwatch.dbw.plist" in text and "<key>StartCalendarInterval</key>" in text


def test_launchd_remove_boots_out_and_deletes_only_the_plist(tmp_path):
    run = FakeRun()
    schedule.install("launchd", job(), run=run, home=tmp_path, uid=501)
    other = tmp_path / "Library" / "LaunchAgents" / "com.someone.else.plist"
    other.write_bytes(b"x")
    run.calls.clear()
    lines = schedule.remove("launchd", run=run, home=tmp_path, uid=501)
    assert run.calls == [["launchctl", "bootout", "gui/501/com.desalbloomwatch.dbw"]]
    assert [p.name for p in (tmp_path / "Library" / "LaunchAgents").iterdir()] == ["com.someone.else.plist"]
    assert any("removed" in l for l in lines)


def test_launchd_remove_when_nothing_is_installed_says_so_and_does_not_fail(tmp_path):
    run = FakeRun({("launchctl", "bootout"): (113, "", "Could not find service")})
    assert "not installed" in " ".join(schedule.remove("launchd", run=run, home=tmp_path, uid=501))


def test_launchd_status_reads_the_plist_and_launchctl(tmp_path):
    run = FakeRun()
    schedule.install("launchd", job("01:15"), run=run, home=tmp_path, uid=501)
    st = schedule.status("launchd", run=run, home=tmp_path, uid=501, now=datetime(2026, 10, 2, 9, 0))
    assert st.installed and st.runner == "launchd" and st.time == "01:15"
    assert st.next_run == datetime(2026, 10, 3, 1, 15)
    assert run.calls[-1] == ["launchctl", "print", "gui/501/com.desalbloomwatch.dbw"]


def test_launchd_status_not_loaded_even_if_the_plist_is_left_behind(tmp_path):
    run = FakeRun()
    schedule.install("launchd", job(), run=run, home=tmp_path, uid=501)
    run = FakeRun({("launchctl", "print"): (113, "", "Could not find service")})
    st = schedule.status("launchd", run=run, home=tmp_path, uid=501, now=datetime(2026, 10, 2, 9, 0))
    assert not st.installed and st.next_run is None


# --- the crontab editor -----------------------------------------------------------------------------

ORIGINAL = "MAILTO=me@example.com\n0 5 * * 1 /usr/bin/backup --weekly\n# my own note\n"


def test_cron_line_quotes_paths_and_runs_from_the_repo_root():
    line = schedule.cron_line(job("01:15", "linux"))
    assert line.startswith("15 1 * * * cd '/Users/someone/desal bloom watch' && ")
    assert "'/Users/someone/desal bloom watch/.venv/bin/dbw' run --log '/Users/someone/desal bloom watch/data/dbw-run.log'" in line
    assert "--date" not in line


def test_edit_crontab_keeps_existing_lines_and_adds_one_marked_block():
    new = schedule.edit_crontab(ORIGINAL, job("01:15", "linux"))
    assert new.startswith(ORIGINAL)
    block = new[len(ORIGINAL):].splitlines()
    assert block[0] == schedule.CRON_BEGIN and block[-1] == schedule.CRON_END and len(block) == 3
    assert block[1] == schedule.cron_line(job("01:15", "linux"))


def test_reinstall_replaces_the_block_and_never_duplicates_it():
    once = schedule.edit_crontab(ORIGINAL, job("01:15", "linux"))
    twice = schedule.edit_crontab(once, job("03:30", "linux"))
    assert twice.count(schedule.CRON_BEGIN) == 1 and twice.count("dbw' run") == 1
    assert "30 3 * * *" in twice and "15 1 * * *" not in twice
    assert twice.startswith(ORIGINAL)


def test_remove_restores_the_original_exactly():
    once = schedule.edit_crontab(ORIGINAL, job("01:15", "linux"))
    assert schedule.edit_crontab(once, None) == ORIGINAL
    assert schedule.edit_crontab(ORIGINAL, None) == ORIGINAL


def test_lines_outside_the_markers_are_never_touched_even_between_two_installs():
    once = schedule.edit_crontab(ORIGINAL, job("01:15", "linux"))
    edited = once + "30 6 * * * /usr/bin/other\n"
    after = schedule.edit_crontab(edited, job("02:00", "linux"))
    assert "30 6 * * * /usr/bin/other\n" in after and after.startswith(ORIGINAL)
    assert schedule.edit_crontab(after, None) == ORIGINAL + "30 6 * * * /usr/bin/other\n"


def test_empty_crontab_roundtrip_and_a_missing_final_newline():
    assert schedule.edit_crontab(schedule.edit_crontab("", job("01:15", "linux")), None) == ""
    assert schedule.edit_crontab("0 5 * * * x", None) == "0 5 * * * x\n"  # cron needs the final newline


def test_cron_time_from_a_crontab():
    assert schedule.cron_time(schedule.edit_crontab(ORIGINAL, job("07:05", "linux"))) == "07:05"
    assert schedule.cron_time(ORIGINAL) is None


def test_cron_install_goes_through_crontab_dash_l_and_dash(tmp_path):
    run = FakeRun({("crontab", "-l"): (0, ORIGINAL, "")})
    schedule.install("cron", job("01:15", "linux"), run=run)
    assert run.calls == [["crontab", "-l"], ["crontab", "-"]]
    assert run.inputs[1] == schedule.edit_crontab(ORIGINAL, job("01:15", "linux"))


def test_cron_install_with_no_crontab_yet(tmp_path):
    run = FakeRun({("crontab", "-l"): (1, "", "no crontab for shay")})
    schedule.install("cron", job("01:15", "linux"), run=run)
    assert run.inputs[1].startswith(schedule.CRON_BEGIN)


def test_cron_dry_run_writes_nothing():
    run = FakeRun({("crontab", "-l"): (0, ORIGINAL, "")})
    lines = schedule.install("cron", job("01:15", "linux"), run=run, dry_run=True)
    assert ["crontab", "-"] not in run.calls and any("15 1 * * *" in l for l in lines)


def test_cron_remove_restores_and_removes_the_crontab_when_it_ends_up_empty():
    mine = schedule.edit_crontab("", job("01:15", "linux"))
    run = FakeRun({("crontab", "-l"): (0, mine, "")})
    schedule.remove("cron", run=run)
    assert ["crontab", "-r"] in run.calls
    mixed = schedule.edit_crontab(ORIGINAL, job("01:15", "linux"))
    run = FakeRun({("crontab", "-l"): (0, mixed, "")})
    schedule.remove("cron", run=run)
    assert run.calls[-1] == ["crontab", "-"] and run.inputs[-1] == ORIGINAL


def test_cron_status():
    mixed = schedule.edit_crontab(ORIGINAL, job("01:15", "linux"))
    st = schedule.status("cron", run=FakeRun({("crontab", "-l"): (0, mixed, "")}), now=datetime(2026, 10, 2, 9, 0))
    assert st.installed and st.time == "01:15" and st.next_run == datetime(2026, 10, 3, 1, 15)
    st = schedule.status("cron", run=FakeRun({("crontab", "-l"): (0, ORIGINAL, "")}), now=datetime(2026, 10, 2, 9, 0))
    assert not st.installed


# --- Windows Task Scheduler: command and XML builders -------------------------------------------------

def test_schtasks_xml_is_well_formed_daily_per_user_and_runs_missed_starts():
    j = schedule.make_job(Path("C:/Users/dana/desal & bloom"), "01:15", platform="win32")
    xml = schedule.schtasks_xml(j)
    root = ET.fromstring(xml.split("?>", 1)[1])
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    assert root.find(".//t:CalendarTrigger/t:StartBoundary", ns).text.endswith("T01:15:00")
    assert root.find(".//t:CalendarTrigger/t:ScheduleByDay/t:DaysInterval", ns).text == "1"
    assert root.find(".//t:Settings/t:StartWhenAvailable", ns).text == "true"
    assert root.find(".//t:Settings/t:DisallowStartIfOnBatteries", ns).text == "false"
    assert root.find(".//t:Principals/t:Principal/t:LogonType", ns).text == "InteractiveToken"
    assert root.find(".//t:Principals/t:Principal/t:RunLevel", ns).text == "LeastPrivilege"
    assert root.find(".//t:Principals/t:Principal/t:Password", ns) is None  # no stored password
    ex = root.find(".//t:Actions/t:Exec", ns)
    assert ex.find("t:Command", ns).text.endswith(".venv/Scripts/dbw.exe") or ex.find("t:Command", ns).text.endswith(".venv\\Scripts\\dbw.exe")
    assert ex.find("t:Arguments", ns).text.startswith('run --log "') and "--date" not in ex.find("t:Arguments", ns).text
    assert ex.find("t:WorkingDirectory", ns).text.replace("\\", "/") == "C:/Users/dana/desal & bloom"


def test_schtasks_commands():
    assert schedule.schtasks_create_args("t.xml") == ["schtasks", "/Create", "/TN", "DesalBloomWatch", "/XML", "t.xml", "/F"]
    assert schedule.schtasks_query_args() == ["schtasks", "/Query", "/TN", "DesalBloomWatch", "/V", "/FO", "LIST"]
    assert schedule.schtasks_delete_args() == ["schtasks", "/Delete", "/TN", "DesalBloomWatch", "/F"]


def test_schtasks_install_writes_utf16_xml_and_creates_with_force(tmp_path):
    run = FakeRun()
    j = schedule.make_job(Path("C:/repo"), "01:15", platform="win32")
    schedule.install("schtasks", j, run=run, tmp=tmp_path)
    (call,) = run.calls
    assert call[:5] == ["schtasks", "/Create", "/TN", "DesalBloomWatch", "/XML"] and call[-1] == "/F"
    raw = Path(call[5]).read_bytes()
    assert raw[:2] == b"\xff\xfe" and raw.decode("utf-16").lstrip().startswith('<?xml version="1.0" encoding="UTF-16"?>')


def test_schtasks_reinstall_replaces_by_the_fixed_name(tmp_path):
    run = FakeRun()
    for t in ("01:15", "03:30"):
        schedule.install("schtasks", schedule.make_job(Path("C:/repo"), t, platform="win32"), run=run, tmp=tmp_path)
    assert [c[3] for c in run.calls] == ["DesalBloomWatch", "DesalBloomWatch"] and all("/F" in c for c in run.calls)


def test_schtasks_failure_is_an_error(tmp_path):
    run = FakeRun({("schtasks", "/Create"): (1, "", "ERROR: The task XML is malformed.")})
    with pytest.raises(schedule.ScheduleError, match="malformed"):
        schedule.install("schtasks", schedule.make_job(Path("C:/repo"), "01:15", platform="win32"), run=run, tmp=tmp_path)


def test_schtasks_dry_run_prints_xml_and_touches_nothing(tmp_path):
    run = FakeRun()
    lines = schedule.install("schtasks", schedule.make_job(Path("C:/repo"), "01:15", platform="win32"), run=run,
                             tmp=tmp_path, dry_run=True)
    assert run.calls == [] and list(tmp_path.iterdir()) == [] and "<StartWhenAvailable>true" in "\n".join(lines)


QUERY = """Folder: \\
HostName:                             DANA-PC
TaskName:                             \\DesalBloomWatch
Next Run Time:                        10/3/2026 1:15:00 AM
Status:                               Ready
Logon Mode:                           Interactive only
Last Run Time:                        10/2/2026 1:15:00 AM
Last Result:                          0
Scheduled Task State:                 Enabled
"""


def test_schtasks_status_and_remove():
    run = FakeRun({("schtasks", "/Query"): (0, QUERY, "")})
    st = schedule.status("schtasks", run=run, now=datetime(2026, 10, 2, 9, 0))
    assert st.installed and st.runner == "schtasks" and st.time == "01:15"
    assert st.next_run == datetime(2026, 10, 3, 1, 15) and "Last Result: 0" in " ".join(st.detail)
    run = FakeRun({("schtasks", "/Query"): (1, "", "ERROR: The system cannot find the file specified.")})
    assert not schedule.status("schtasks", run=run, now=datetime(2026, 10, 2, 9, 0)).installed
    run = FakeRun()
    schedule.remove("schtasks", run=run)
    assert run.calls == [schedule.schtasks_delete_args()]


# --- the run log and `status` ------------------------------------------------------------------------------

LOG = """[2026-10-01 01:15:02+03:00] dbw run start
done: 9 boxes, 4000 rows
[2026-10-01 01:15:40+03:00] RESULT ok
[2026-10-02 01:15:03+03:00] dbw run start
note: NOAA data could not be fetched today (noaacwN20VIIRSchlaDaily HTTP 502)
[2026-10-02 01:16:10+03:00] RESULT partial: upstream unreachable
"""


def test_last_run_is_read_from_the_log():
    last = schedule.last_run(LOG)
    assert last.when == "2026-10-02 01:16" and last.result == "partial: upstream unreachable"
    assert schedule.last_run(LOG.replace("partial: upstream unreachable", "failed: boom (exit 1)")).result == "failed: boom (exit 1)"


def test_a_run_that_started_and_never_finished_is_reported_as_such():
    last = schedule.last_run(LOG + "[2026-10-03 01:15:03+03:00] dbw run start\n")
    assert last.when == "2026-10-03 01:15" and last.result is None


def test_no_log_no_last_run():
    assert schedule.last_run("") is None


def test_render_status_lines(tmp_path):
    run = FakeRun()
    schedule.install("launchd", job("01:15"), run=run, home=tmp_path, uid=501)
    st = schedule.status("launchd", run=run, home=tmp_path, uid=501, now=datetime(2026, 10, 2, 9, 0))
    text = "\n".join(schedule.render_status(st, LOG, job().log))
    for needle in ("installed: yes", "runner: launchd", "time: 01:15", "next run: 2026-10-03 01:15",
                   "last run: 2026-10-02 01:16 - partial: upstream unreachable", f"log: {job().log}"):
        assert needle in text, needle
    gone = schedule.status("launchd", run=FakeRun({("launchctl", "print"): (113, "", "")}), home=tmp_path / "x",
                           uid=501, now=datetime(2026, 10, 2, 9, 0))
    t2 = "\n".join(schedule.render_status(gone, "", job().log))
    assert "installed: no" in t2 and "last run: never" in t2


def test_run_logged_writes_start_output_and_the_result_line(tmp_path, capsys):
    log = tmp_path / "logs" / "run.log"
    rc = schedule.run_logged(log, lambda: (print("hello"), schedule.OK)[1])
    assert rc == 0 and capsys.readouterr().out == ""  # the output went to the file, not the console
    text = log.read_text(encoding="utf-8")
    assert "dbw run start" in text and "hello" in text and text.rstrip().endswith("RESULT ok")


def test_run_logged_appends_across_runs(tmp_path):
    log = tmp_path / "run.log"
    for _ in range(2):
        schedule.run_logged(log, lambda: schedule.OK)
    assert log.read_text(encoding="utf-8").count("dbw run start") == 2


def test_run_logged_leaves_the_reason_and_exits_non_zero_on_failure(tmp_path):
    log = tmp_path / "run.log"

    def boom():
        raise RuntimeError("disk on fire")

    assert schedule.run_logged(log, boom) == 1
    assert "RESULT failed: disk on fire" in log.read_text(encoding="utf-8")
    assert schedule.run_logged(log, lambda: (_ for _ in ()).throw(SystemExit("no config.yaml"))) == 1
    assert "RESULT failed: no config.yaml" in log.read_text(encoding="utf-8")


def test_run_logged_partial_result_exits_zero(tmp_path):
    log = tmp_path / "run.log"
    assert schedule.run_logged(log, lambda: schedule.PARTIAL) == 0
    assert log.read_text(encoding="utf-8").rstrip().endswith("RESULT partial: upstream unreachable")


def test_run_logged_writes_hebrew_and_the_emoji_to_a_file_whatever_the_console_charset(tmp_path):
    log = tmp_path / "run.log"
    schedule.run_logged(log, lambda: (print("🟢 שלום מ\u2068ים\u2069"), schedule.OK)[1])
    assert "🟢 שלום" in log.read_text(encoding="utf-8")
