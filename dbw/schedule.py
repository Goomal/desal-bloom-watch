"""Daily runner: install, inspect and remove one scheduled `dbw run` on launchd, cron or Windows Task Scheduler.

The builders (plist, crontab editor, task XML, command lines) are pure functions; every system call goes through
a `run` callable so tests use a fake and never touch the real launchd, crontab or Task Scheduler. The job always
runs the repo's own venv `dbw run --log <file>` from the repo root, with no date argument."""
import contextlib
import plistlib
import re
import shlex
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass, field
from datetime import datetime, time as Time, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

RUNNERS = ("launchd", "cron", "schtasks")
LABEL = "com.desalbloomwatch.dbw"
TASK_NAME = "DesalBloomWatch"
CRON_BEGIN = "# BEGIN desal-bloom-watch (managed by `dbw schedule`; do not edit)"
CRON_END = "# END desal-bloom-watch"
# Measured arrival of the newest NOAA slices (docs/schedule.md): the latest of the three data sets lands by
# about 21:00 UTC, once a day, so any run after ARRIVAL_UTC_TIME (21:00 plus margin) sees the newest day.
ARRIVAL_UTC_TIME = "22:15"
DEFAULT_TIME = "07:00"  # local clock: the report is ready at the start of the workday; a missed run catches up on wake
OK = "ok"
UPSTREAM, TELEGRAM = "upstream unreachable", "telegram failed"  # the reasons a run can be partial


def partial(*reasons):
    return "partial: " + ", ".join(reasons)


PARTIAL = partial(UPSTREAM)


class ScheduleError(Exception):
    """A scheduling problem the user can act on; the CLI prints it as one plain line."""


# --- runner and time ------------------------------------------------------------------------------

def default_runner(platform=None):
    platform = platform or sys.platform
    return "launchd" if platform == "darwin" else "schtasks" if platform.startswith("win") else "cron"


def check_runner(runner):
    if runner not in RUNNERS:
        raise ScheduleError(f"unknown runner '{runner}': use one of launchd, cron, schtasks")
    return runner


def parse_time(text):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(text).strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ScheduleError(f"time must be HH:MM on a 24-hour clock, got '{text}'")
    return int(m.group(1)), int(m.group(2))


def normalize_time(text):
    h, m = parse_time(text)
    return f"{h:02d}:{m:02d}"


def default_time():
    return DEFAULT_TIME


def arrival_time(now=None):
    """ARRIVAL_UTC_TIME on the clock of `now` (an aware datetime; the local clock when omitted), as HH:MM:
    any run later than this, up to the next day's arrival, gets the newest day."""
    now = now or datetime.now().astimezone()
    h, m = parse_time(ARRIVAL_UTC_TIME)
    utc = datetime.combine(now.astimezone(timezone.utc).date(), Time(h, m), tzinfo=timezone.utc)
    return utc.astimezone(now.tzinfo).strftime("%H:%M")


def next_run(time_text, now):
    h, m = parse_time(time_text)
    at = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return at if at > now else at + timedelta(days=1)


# --- the job ----------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Job:
    root: Path
    time: str
    exe: Path
    log: Path
    args: list = field(default_factory=list)


def make_job(root, time_text, platform=None):
    root = Path(root)
    platform = platform or sys.platform
    exe = root / ".venv" / ("Scripts" if platform.startswith("win") else "bin") / ("dbw.exe" if platform.startswith("win") else "dbw")
    log = root / "data" / "dbw-run.log"
    return Job(root, normalize_time(time_text), exe, log, ["run", "--log", str(log)])


def _call(args, input=None):
    try:
        return subprocess.run(args, input=input, capture_output=True, text=True)
    except FileNotFoundError:
        raise ScheduleError(f"{args[0]} was not found on this machine; choose another runner with --runner") from None


def _why(r):
    return (r.stderr or r.stdout or f"exit {r.returncode}").strip()


# --- launchd -----------------------------------------------------------------------------------------

def plist_bytes(job):
    h, m = parse_time(job.time)
    out = job.root / "data" / "dbw-launchd.log"  # only what escapes `--log`, such as an import crash
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [str(job.exe), *job.args],
        "WorkingDirectory": str(job.root),
        "StartCalendarInterval": {"Hour": h, "Minute": m},
        "StandardOutPath": str(out),
        "StandardErrorPath": str(out),
        "EnvironmentVariables": {"PYTHONUTF8": "1"},
    })


def _plist_path(home):
    return Path(home) / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _domain(uid):
    return f"gui/{uid}"


# --- cron --------------------------------------------------------------------------------------------

def cron_line(job):
    h, m = parse_time(job.time)
    cmd = f"cd {shlex.quote(str(job.root))} && {shlex.quote(str(job.exe))} " + " ".join(shlex.quote(a) for a in job.args)
    return f"{m} {h} * * * " + cmd.replace("%", "\\%")  # an unescaped % in a crontab line means newline


def edit_crontab(text, job):
    """crontab text with the managed block replaced by one for `job`, or removed when `job` is None.
    Lines outside the markers are returned untouched."""
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


def cron_time(text):
    lines = text.splitlines()
    if CRON_BEGIN not in lines:
        return None
    parts = lines[lines.index(CRON_BEGIN) + 1].split()
    return f"{int(parts[1]):02d}:{int(parts[0]):02d}" if len(parts) > 2 and parts[0].isdigit() and parts[1].isdigit() else None


def _crontab(run):
    r = run(["crontab", "-l"])
    return r.stdout if r.returncode == 0 else ""  # "no crontab for <user>" is an empty one


# --- Windows Task Scheduler --------------------------------------------------------------------------

_TASK_NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"


def schtasks_xml(job, user=None):
    """Task definition XML. A plain `schtasks /Create` flag set has no way to say 'run a missed start when the PC
    comes back' (StartWhenAvailable), so the task is imported from XML instead. Current user, interactive token,
    least privilege: no admin rights and no stored password."""
    h, m = parse_time(job.time)
    user_id = f"<UserId>{escape(user)}</UserId>" if user else ""
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="{_TASK_NS}">
  <RegistrationInfo><Description>Desal Bloom Watch daily run</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-01-01T{h:02d}:{m:02d}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">{user_id}<LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(str(job.exe))}</Command>
      <Arguments>{escape(f'run --log "{job.log}"')}</Arguments>
      <WorkingDirectory>{escape(str(job.root))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def schtasks_create_args(xml_path):
    return ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"]


def schtasks_query_args():
    return ["schtasks", "/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"]


def schtasks_delete_args():
    return ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]


def _task_user():
    import os
    name, domain = os.environ.get("USERNAME"), os.environ.get("USERDOMAIN")
    return f"{domain}\\{name}" if name and domain else name


# --- install / status / remove -----------------------------------------------------------------------

@dataclass
class Status:
    installed: bool
    runner: str
    time: str = None
    next_run: datetime = None
    detail: list = field(default_factory=list)


def install(runner, job, run=None, home=None, uid=None, tmp=None, dry_run=False):
    """Install (or replace) the one daily job. Returns the lines to print. `dry_run` changes nothing."""
    check_runner(runner)
    run = run or _call  # looked up here, not bound at import, so a test can swap the process runner
    if runner == "launchd":
        return _install_launchd(job, run, Path(home) if home else Path.home(), uid, dry_run)
    if runner == "cron":
        return _install_cron(job, run, dry_run)
    return _install_schtasks(job, run, Path(tmp) if tmp else Path(tempfile.gettempdir()), dry_run)


def _install_launchd(job, run, home, uid, dry_run):
    import os
    uid = os.getuid() if uid is None else uid
    plist = _plist_path(home)
    if dry_run:
        return [f"dry run: would write {plist} and load it with launchctl bootstrap {_domain(uid)}",
                plist_bytes(job).decode("utf-8")]
    run(["launchctl", "bootout", f"{_domain(uid)}/{LABEL}"])  # an older copy of this job, if any
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_bytes(plist_bytes(job))
    r = run(["launchctl", "bootstrap", _domain(uid), str(plist)])
    if r.returncode != 0:
        raise ScheduleError(f"launchctl bootstrap failed: {_why(r)}")
    return [f"installed: launchd job {LABEL}, every day at {job.time} local time", f"plist: {plist}"]


def _install_cron(job, run, dry_run):
    new = edit_crontab(_crontab(run), job)
    if dry_run:
        return ["dry run: would set this crontab block:", *new[new.index(CRON_BEGIN):].splitlines()]
    r = run(["crontab", "-"], input=new)
    if r.returncode != 0:
        raise ScheduleError(f"crontab failed: {_why(r)}")
    return [f"installed: cron line, every day at {job.time} local time"]


def _install_schtasks(job, run, tmp, dry_run):
    xml = schtasks_xml(job, _task_user())
    if dry_run:
        return [f"dry run: would import this task as {TASK_NAME}:", *xml.splitlines()]
    path = tmp / "dbw-task.xml"
    path.write_bytes(b"\xff\xfe" + xml.encode("utf-16-le"))
    r = run(schtasks_create_args(path))
    if r.returncode != 0:
        raise ScheduleError(f"schtasks failed: {_why(r)}")
    return [f"installed: Task Scheduler task {TASK_NAME}, every day at {job.time} local time"]


def remove(runner, run=None, home=None, uid=None):
    """Remove the job and nothing else. Returns the lines to print."""
    import os
    check_runner(runner)
    run = run or _call
    if runner == "launchd":
        uid = os.getuid() if uid is None else uid
        plist = _plist_path(Path(home) if home else Path.home())
        r = run(["launchctl", "bootout", f"{_domain(uid)}/{LABEL}"])
        had = plist.exists()
        plist.unlink(missing_ok=True)
        return ["removed: launchd job" if had or r.returncode == 0 else "not installed: nothing to remove"]
    if runner == "cron":
        text = _crontab(run)
        if CRON_BEGIN not in text.splitlines():
            return ["not installed: nothing to remove"]
        new = edit_crontab(text, None)
        r = run(["crontab", "-r"]) if not new.strip() else run(["crontab", "-"], input=new)
        if r.returncode != 0:
            raise ScheduleError(f"crontab failed: {_why(r)}")
        return ["removed: cron line"]
    r = run(schtasks_delete_args())
    if r.returncode == 0:
        return ["removed: Task Scheduler task"]
    if "cannot find" in _why(r).lower():
        return ["not installed: nothing to remove"]
    raise ScheduleError(f"schtasks failed: {_why(r)}")


def status(runner, run=None, home=None, uid=None, now=None):
    import os
    check_runner(runner)
    run = run or _call
    now = now or datetime.now()
    if runner == "launchd":
        uid = os.getuid() if uid is None else uid
        plist = _plist_path(Path(home) if home else Path.home())
        if not plist.exists() or run(["launchctl", "print", f"{_domain(uid)}/{LABEL}"]).returncode != 0:
            return Status(False, runner)
        cal = plistlib.loads(plist.read_bytes())["StartCalendarInterval"]
        t = f"{cal['Hour']:02d}:{cal['Minute']:02d}"
        return Status(True, runner, t, next_run(t, now))
    if runner == "cron":
        t = cron_time(_crontab(run))
        return Status(False, runner) if t is None else Status(True, runner, t, next_run(t, now))
    r = run(schtasks_query_args())
    if r.returncode != 0:
        return Status(False, runner)
    fields = {k.strip(): v.strip() for k, _, v in (l.partition(":") for l in r.stdout.splitlines()) if v.strip()}
    # The date format follows the Windows locale, so only the clock is read; the next date is worked out from it.
    m = re.search(r"(\d{1,2}):(\d{2})(?::\d{2})?\s*(AM|PM)?", r.stdout.split("Next Run Time:", 1)[-1].splitlines()[0]) \
        if "Next Run Time:" in r.stdout else None
    t = None
    if m:
        h = int(m.group(1)) % 12 + (12 if (m.group(3) or "").upper() == "PM" else 0) if m.group(3) else int(m.group(1))
        t = f"{h:02d}:{m.group(2)}"
    detail = [f"{k}: {fields[k]}" for k in ("Status", "Last Run Time", "Last Result", "Scheduled Task State") if k in fields]
    return Status(True, runner, t, next_run(t, now) if t else None, detail)


# --- the run log -------------------------------------------------------------------------------------

@dataclass
class LastRun:
    when: str
    result: str = None  # None: it started and never wrote a result line


_LOG_LINE = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d)[^\]]*\] (dbw run start|RESULT (.*))$")


def last_run(text):
    found = None
    for line in text.splitlines():
        m = _LOG_LINE.match(line)
        if m:
            found = LastRun(m.group(1), m.group(3)) if m.group(3) is not None else LastRun(m.group(1))
    return found


def _stamp():
    return datetime.now().astimezone().isoformat(sep=" ", timespec="seconds")


def run_logged(log, fn):
    """Run `fn` with all its output appended to `log` (utf-8), bracketed by a start line and a RESULT line.
    `fn` returns OK or PARTIAL; anything it raises is a failure whose reason lands in the log. Returns the exit code:
    0 for ok and partial, 1 for a failure."""
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"[{_stamp()}] dbw run start\n")
        f.flush()
        try:
            with contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
                res = fn()
            if res in (None, 0):
                res = OK
            elif not isinstance(res, str):
                res = f"failed: exit {res}"
        except SystemExit as e:
            res = f"failed: {e.code}" if isinstance(e.code, str) else f"failed: exit {e.code}"
        except Exception as e:
            f.write(traceback.format_exc())
            res = f"failed: {e}"
        f.write(f"[{_stamp()}] RESULT {res}\n")
    return 1 if res.startswith("failed") else 0


def render_status(st, log_text, log_path):
    lines = [f"installed: {'yes' if st.installed else 'no'}", f"runner: {st.runner}"]
    if st.installed and st.time:
        lines.append(f"time: {st.time}")
    if st.next_run:
        lines.append(f"next run: {st.next_run:%Y-%m-%d %H:%M}")
    last = last_run(log_text or "")
    if last is None:
        lines.append("last run: never")
    elif last.result is None:
        lines.append(f"last run: {last.when} - started, no result (still running, or interrupted)")
    else:
        lines.append(f"last run: {last.when} - {last.result}")
    lines += st.detail
    lines.append(f"log: {log_path}")
    return lines
