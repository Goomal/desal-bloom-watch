"""dbw/bot_service.py: start the bot at login on launchd, cron or Task Scheduler. Every system call is a fake."""
import plistlib
import sys
from pathlib import Path

import pytest

from dbw import bot as botmod, bot_service as svc, cli, schedule
from test_schedule import FakeRun

ROOT = Path("/opt/dbw")


def test_the_job_runs_the_venv_dbw_on_mac_and_linux():
    job = svc.make_job(ROOT, "darwin")
    assert job.exe == ROOT / ".venv" / "bin" / "dbw"
    assert job.args == ["bot", "run", "--log", str(ROOT / "data" / "dbw-bot.log")]


def test_on_windows_it_runs_pythonw_so_no_console_window_stays_open():
    job = svc.make_job(ROOT, "win32")
    assert job.exe == ROOT / ".venv" / "Scripts" / "pythonw.exe"
    assert job.args[:4] == ["-m", "dbw.cli", "bot", "run"]


def test_the_launchd_agent_starts_at_login_and_is_kept_alive():
    p = plistlib.loads(svc.plist_bytes(svc.make_job(ROOT, "darwin")))
    assert p["Label"] == svc.LABEL and p["RunAtLoad"] is True and p["KeepAlive"] is True
    assert p["ProgramArguments"] == [str(ROOT / ".venv/bin/dbw"), "bot", "run", "--log", str(ROOT / "data/dbw-bot.log")]
    assert p["WorkingDirectory"] == str(ROOT) and p["EnvironmentVariables"] == {"PYTHONUTF8": "1"}


@pytest.mark.skipif(sys.platform == "win32", reason="cron is not on Windows; the POSIX test paths render with backslashes")
def test_the_cron_block_is_an_at_reboot_line_and_leaves_the_daily_block_alone():
    daily = schedule.edit_crontab("MAILTO=x\n", schedule.make_job(ROOT, "07:00", "linux"))
    text = svc.edit_crontab(daily, svc.make_job(ROOT, "linux"))
    assert schedule.CRON_BEGIN in text and svc.CRON_BEGIN in text and text.startswith("MAILTO=x\n")
    (line,) = [l for l in text.splitlines() if l.startswith("@reboot")]
    assert line.startswith("@reboot cd ") and " bot run --log " in line and line.rstrip().endswith("dbw-bot.log")
    assert svc.edit_crontab(text, None) == daily


def test_the_task_xml_starts_at_logon_never_times_out_and_restarts_on_failure():
    xml = svc.schtasks_xml(svc.make_job(ROOT, "win32"), "PC\\user")
    for part in ("<LogonTrigger>", "<UserId>PC\\user</UserId>", "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>",
                 "<RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>",
                 "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>", "pythonw.exe</Command>",
                 '<Arguments>-m dbw.cli bot run --log "'):
        assert part in xml, part


def test_install_on_launchd_writes_the_plist_and_bootstraps_it(tmp_path):
    run = FakeRun()
    lines = svc.install("launchd", svc.make_job(ROOT, "darwin"), run=run, home=tmp_path, uid=501)
    plist = tmp_path / "Library/LaunchAgents/com.desalbloomwatch.bot.plist"
    assert plist.exists() and ["launchctl", "bootstrap", "gui/501", str(plist)] in run.calls
    assert "installed" in lines[0]


def test_install_on_schtasks_imports_the_xml_then_starts_it_now(tmp_path):
    run = FakeRun()
    svc.install("schtasks", svc.make_job(ROOT, "win32"), run=run, tmp=tmp_path)
    assert run.calls[0][:4] == ["schtasks", "/Create", "/TN", svc.TASK_NAME]
    assert run.calls[1] == ["schtasks", "/Run", "/TN", svc.TASK_NAME]
    assert (tmp_path / "dbw-bot-task.xml").read_bytes().startswith(b"\xff\xfe")


def test_install_on_cron_adds_the_block_and_says_how_to_start_now():
    run = FakeRun({("crontab", "-l"): (0, "MAILTO=x\n", "")})
    lines = svc.install("cron", svc.make_job(ROOT, "linux"), run=run)
    assert svc.CRON_BEGIN in run.inputs[-1] and any("nohup" in l for l in lines)


def test_dry_run_changes_nothing(tmp_path):
    run = FakeRun()
    svc.install("launchd", svc.make_job(ROOT, "darwin"), run=run, home=tmp_path, uid=501, dry_run=True)
    assert run.calls == [] and not (tmp_path / "Library").exists()


def test_uninstall_and_installed_on_each_runner(tmp_path):
    run = FakeRun()
    job = svc.make_job(ROOT, "darwin")
    svc.install("launchd", job, run=run, home=tmp_path, uid=501)
    assert svc.installed("launchd", run=run, home=tmp_path, uid=501)
    assert svc.uninstall("launchd", run=run, home=tmp_path, uid=501) == ["removed: launchd bot agent"]
    assert not svc.installed("launchd", run=run, home=tmp_path, uid=501)
    gone = FakeRun({("schtasks", "/Query"): (1, "", "ERROR: The system cannot find the file specified.")})
    assert not svc.installed("schtasks", run=gone)
    assert svc.uninstall("schtasks", run=FakeRun({("schtasks", "/Delete"): (1, "", "ERROR: cannot find")})) == \
        ["not installed: nothing to remove"]


def test_cli_status_says_installed_and_running(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(svc, "installed", lambda runner, **kw: True)
    monkeypatch.setattr(botmod, "lock_held", lambda path: False)
    monkeypatch.setattr(cli, "_root", lambda: tmp_path)
    assert cli.main(["bot", "status", "--runner", "cron", "--config", str(tmp_path / "none.yaml")]) == 0
    out = capsys.readouterr().out
    assert "installed: yes" in out and "running: no" in out and "dbw-bot.log" in out


def test_cli_install_refuses_a_missing_config(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_root", lambda: tmp_path)
    with pytest.raises(SystemExit, match="dbw setup"):
        cli.main(["bot", "install", "--runner", "cron", "--config", str(tmp_path / "none.yaml")])


def test_cli_install_dry_run_prints_the_job(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_root", lambda: tmp_path)
    monkeypatch.setattr(schedule, "_call", FakeRun())
    assert cli.main(["bot", "install", "--runner", "cron", "--dry-run", "--config", str(tmp_path / "none.yaml")]) == 0
    out = capsys.readouterr().out
    assert "@reboot" in out and "--config" in out and "none.yaml" in out
