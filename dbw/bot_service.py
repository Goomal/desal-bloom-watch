"""Start `dbw bot` at login and keep it running: a launchd agent (macOS), a cron @reboot line (Linux) or a Task
Scheduler task with a logon trigger (Windows). Shaped like dbw/schedule.py: pure builders, and every system call
goes through a `run` callable so tests never touch the real service manager. The bot answers only while this
computer is on."""
import plistlib
import shlex
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from dbw import schedule

LABEL = "com.desalbloomwatch.bot"
TASK_NAME = "DesalBloomWatchBot"
CRON_BEGIN = "# BEGIN desal-bloom-watch-bot (managed by `dbw bot`; do not edit)"
CRON_END = "# END desal-bloom-watch-bot"


@dataclass(frozen=True)
class BotJob:
    root: Path
    exe: Path
    log: Path
    args: list = field(default_factory=list)


def make_job(root, platform=None):
    """The venv's `dbw bot run --log data/dbw-bot.log`; on Windows `pythonw.exe -m dbw.cli ...`, which opens no
    console window (an always-on dbw.exe would keep one open all day)."""
    root, platform = Path(root), platform or sys.platform
    log = root / "data" / "dbw-bot.log"
    if platform.startswith("win"):
        return BotJob(root, root / ".venv" / "Scripts" / "pythonw.exe", log, ["-m", "dbw.cli", "bot", "run", "--log", str(log)])
    return BotJob(root, root / ".venv" / "bin" / "dbw", log, ["bot", "run", "--log", str(log)])


# --- builders ---------------------------------------------------------------------------------------------------

def plist_bytes(job):
    out = job.root / "data" / "dbw-bot-launchd.log"  # only what escapes `--log`, such as an import crash
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [str(job.exe), *job.args],
        "WorkingDirectory": str(job.root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 60,  # a bot that keeps failing (no token) is restarted at most once a minute
        "StandardOutPath": str(out),
        "StandardErrorPath": str(out),
        "EnvironmentVariables": {"PYTHONUTF8": "1"},
    })


def cron_line(job):
    cmd = f"cd {shlex.quote(str(job.root))} && {shlex.quote(str(job.exe))} " + " ".join(shlex.quote(a) for a in job.args)
    return "@reboot " + cmd.replace("%", "\\%")


def edit_crontab(text, job):
    """crontab text with this bot's block replaced by one for `job`, or removed when `job` is None. Every other line,
    the daily run's block included, is kept. (dbw/schedule.py has the same editor for its own markers.)"""
    keep, inside = [], False
    for line in text.splitlines():
        if line == CRON_BEGIN:
            inside = True
        elif inside and line == CRON_END:
            inside = False
        elif not inside:
            keep.append(line)
    if job is not None:
        keep += [CRON_BEGIN, cron_line(job), CRON_END]
    return "".join(l + "\n" for l in keep)


def schtasks_xml(job, user=None):
    """Start at logon of the current user, no time limit, restart every minute after a failure. Same principal as the
    daily task: interactive token, least privilege, no stored password."""
    user_id = f"<UserId>{escape(user)}</UserId>" if user else ""
    args = " ".join(f'"{a}"' if a == str(job.log) or " " in a else a for a in job.args)
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="{schedule._TASK_NS}">
  <RegistrationInfo><Description>Desal Bloom Watch sign-up bot</Description></RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled>{user_id}</LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">{user_id}<LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(str(job.exe))}</Command>
      <Arguments>{escape(args)}</Arguments>
      <WorkingDirectory>{escape(str(job.root))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


# --- install / uninstall / installed ----------------------------------------------------------------------------

def _plist_path(home):
    return Path(home) / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def install(runner, job, run=None, home=None, uid=None, tmp=None, dry_run=False):
    """Install (or replace) the bot and start it now where the runner can. -> lines to print."""
    import os
    schedule.check_runner(runner)
    run = run or schedule._call
    if runner == "launchd":
        uid = os.getuid() if uid is None else uid
        plist = _plist_path(Path(home) if home else Path.home())
        if dry_run:
            return [f"dry run: would write {plist} and load it with launchctl bootstrap {schedule._domain(uid)}",
                    plist_bytes(job).decode("utf-8")]
        run(["launchctl", "bootout", f"{schedule._domain(uid)}/{LABEL}"])
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_bytes(plist_bytes(job))
        r = run(["launchctl", "bootstrap", schedule._domain(uid), str(plist)])
        if r.returncode != 0:
            raise schedule.ScheduleError(f"launchctl bootstrap failed: {schedule._why(r)}")
        return [f"installed: launchd agent {LABEL}; it starts now and at every login", f"plist: {plist}"]
    if runner == "cron":
        new = edit_crontab(schedule._crontab(run), job)
        if dry_run:
            return ["dry run: would set this crontab block:", *new[new.index(CRON_BEGIN):].splitlines()]
        r = run(["crontab", "-"], input=new)
        if r.returncode != 0:
            raise schedule.ScheduleError(f"crontab failed: {schedule._why(r)}")
        return ["installed: cron @reboot line; the bot starts at the next reboot",
                f"to start it now: cd {shlex.quote(str(job.root))} && nohup {shlex.quote(str(job.exe))} "
                + " ".join(shlex.quote(a) for a in job.args) + " >/dev/null 2>&1 &"]
    xml = schtasks_xml(job, schedule._task_user())
    if dry_run:
        return [f"dry run: would import this task as {TASK_NAME} and start it:", *xml.splitlines()]
    path = Path(tmp or tempfile.gettempdir()) / "dbw-bot-task.xml"
    path.write_bytes(b"\xff\xfe" + xml.encode("utf-16-le"))
    for args in (["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(path), "/F"], ["schtasks", "/Run", "/TN", TASK_NAME]):
        r = run(args)
        if r.returncode != 0:
            raise schedule.ScheduleError(f"schtasks failed: {schedule._why(r)}")
    return [f"installed: Task Scheduler task {TASK_NAME}; it starts now and at every logon"]


def uninstall(runner, run=None, home=None, uid=None):
    """Stop and remove the bot's job, and nothing else. -> lines to print."""
    import os
    schedule.check_runner(runner)
    run = run or schedule._call
    if runner == "launchd":
        uid = os.getuid() if uid is None else uid
        plist = _plist_path(Path(home) if home else Path.home())
        r = run(["launchctl", "bootout", f"{schedule._domain(uid)}/{LABEL}"])
        had = plist.exists()
        plist.unlink(missing_ok=True)
        return ["removed: launchd bot agent" if had or r.returncode == 0 else "not installed: nothing to remove"]
    if runner == "cron":
        text = schedule._crontab(run)
        if CRON_BEGIN not in text.splitlines():
            return ["not installed: nothing to remove"]
        new = edit_crontab(text, None)
        r = run(["crontab", "-r"]) if not new.strip() else run(["crontab", "-"], input=new)
        if r.returncode != 0:
            raise schedule.ScheduleError(f"crontab failed: {schedule._why(r)}")
        return ["removed: cron @reboot line (a bot started by hand keeps running until you stop it)"]
    run(["schtasks", "/End", "/TN", TASK_NAME])
    r = run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
    if r.returncode == 0:
        return ["removed: Task Scheduler task"]
    if "cannot find" in schedule._why(r).lower():
        return ["not installed: nothing to remove"]
    raise schedule.ScheduleError(f"schtasks failed: {schedule._why(r)}")


def installed(runner, run=None, home=None, uid=None):
    import os
    schedule.check_runner(runner)
    run = run or schedule._call
    if runner == "launchd":
        uid = os.getuid() if uid is None else uid
        return _plist_path(Path(home) if home else Path.home()).exists() and \
            run(["launchctl", "print", f"{schedule._domain(uid)}/{LABEL}"]).returncode == 0
    if runner == "cron":
        return CRON_BEGIN in schedule._crontab(run).splitlines()
    return run(["schtasks", "/Query", "/TN", TASK_NAME]).returncode == 0
