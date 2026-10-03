"""`dbw schedule install|status|remove`, the config record of runner and time, and the schedule offer in `dbw setup`.
launchctl, crontab and schtasks are a fake; the real ones are never called."""
import plistlib
import sys
from types import SimpleNamespace

import pytest
import yaml

from dbw import cli, climatology, config, registry, schedule
from test_schedule import FakeRun


@pytest.fixture
def box(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / ".venv" / "bin").mkdir(parents=True)
    (root / ".venv" / "bin" / "dbw").write_text("", encoding="utf-8")
    (root / ".venv" / "Scripts").mkdir(parents=True)
    (root / ".venv" / "Scripts" / "dbw.exe").write_text("", encoding="utf-8")  # where make_job looks on Windows
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("DBW_DB", str(tmp_path / "t.sqlite"))
    monkeypatch.setattr(cli, "_root", lambda: root)
    monkeypatch.setattr(schedule, "default_time", lambda: "01:15")
    run = FakeRun()
    monkeypatch.setattr(schedule, "_call", run)
    cfg = tmp_path / "config.yaml"
    config.write(cfg, ["hadera"], tmp_path / "reports", registry.load())
    agents = home / "Library" / "LaunchAgents"
    return SimpleNamespace(root=root, home=home, run=run, cfg=str(cfg), cfgp=cfg, agents=agents,
                           plist=agents / "com.desalbloomwatch.dbw.plist", tmp=tmp_path)


MAC_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="launchd is macOS only (os.getuid, .venv/bin)")


def sched(box, *args):
    return cli.main(["schedule", *args, "--config", box.cfg])


def conf(box):
    return yaml.safe_load(box.cfgp.read_text(encoding="utf-8"))


# --- install -----------------------------------------------------------------------------------------

@MAC_ONLY
def test_install_launchd_writes_the_plist_loads_it_and_records_runner_and_time(box, capsys):
    assert sched(box, "install", "--runner", "launchd", "--time", "07:05") == 0
    p = plistlib.loads(box.plist.read_bytes())
    assert p["ProgramArguments"][0] == str(box.root / ".venv" / "bin" / "dbw") and p["WorkingDirectory"] == str(box.root)
    assert p["StartCalendarInterval"] == {"Hour": 7, "Minute": 5}
    assert [c[1] for c in box.run.calls] == ["bootout", "bootstrap"]
    assert conf(box)["runner"] == "launchd" and conf(box)["schedule"] == {"time": "07:05"}
    assert conf(box)["plants"] == ["hadera"]  # the rest of the config is kept
    assert "07:05" in capsys.readouterr().out


def test_install_without_a_time_uses_the_measured_default(box):
    sched(box, "install", "--runner", "cron")
    assert conf(box)["schedule"] == {"time": "01:15"}


def test_install_without_a_runner_uses_the_one_in_the_config_then_the_platform(box, monkeypatch):
    monkeypatch.setattr(schedule, "default_runner", lambda platform=None: "cron")
    sched(box, "install")
    assert box.run.calls[-1] == ["crontab", "-"] and conf(box)["runner"] == "cron"
    sched(box, "install", "--time", "02:00")
    assert conf(box)["runner"] == "cron" and conf(box)["schedule"]["time"] == "02:00"


@MAC_ONLY
def test_install_twice_is_one_job_and_one_config_entry(box):
    sched(box, "install", "--runner", "launchd", "--time", "07:05")
    sched(box, "install", "--runner", "launchd", "--time", "07:05")
    assert [p.name for p in box.agents.iterdir()] == ["com.desalbloomwatch.dbw.plist"]
    assert list(conf(box)).count("runner") == 1 and conf(box)["schedule"] == {"time": "07:05"}


@MAC_ONLY
def test_install_reinstall_with_a_new_time_moves_the_job(box):
    sched(box, "install", "--runner", "launchd", "--time", "07:05")
    sched(box, "install", "--runner", "launchd", "--time", "03:30")
    assert plistlib.loads(box.plist.read_bytes())["StartCalendarInterval"] == {"Hour": 3, "Minute": 30}
    assert conf(box)["schedule"]["time"] == "03:30"


def test_an_unknown_runner_is_refused_naming_the_three_options(box):
    with pytest.raises(SystemExit) as e:
        sched(box, "install", "--runner", "systemd")
    assert all(w in str(e.value) for w in ("launchd", "cron", "schtasks")) and box.run.calls == []


@pytest.mark.parametrize("bad", ["25:00", "7", "noon"])
def test_a_bad_time_is_refused(box, bad):
    with pytest.raises(SystemExit, match="HH:MM"):
        sched(box, "install", "--runner", "cron", "--time", bad)
    assert box.run.calls == [] and "schedule" not in conf(box)


def test_install_needs_a_config_because_the_job_cannot_report_without_one(box):
    box.cfgp.unlink()
    with pytest.raises(SystemExit, match="dbw setup"):
        sched(box, "install", "--runner", "cron")
    assert box.run.calls == []


def test_install_needs_the_venv_and_says_how_to_make_it(box):
    (box.root / ".venv" / "bin" / "dbw").unlink()
    with pytest.raises(SystemExit, match="venv"):
        sched(box, "install", "--runner", "cron")
    assert box.run.calls == []


@MAC_ONLY
def test_dry_run_prints_and_changes_nothing(box, capsys):
    before = box.cfgp.read_text(encoding="utf-8")
    box.cfgp.write_text(before, encoding="utf-8")
    assert sched(box, "install", "--runner", "launchd", "--time", "07:05", "--dry-run") == 0
    out = capsys.readouterr().out
    assert "<key>StartCalendarInterval</key>" in out and "dry run" in out
    assert box.run.calls == [] and not box.home.joinpath("Library").exists()
    assert box.cfgp.read_text(encoding="utf-8") == before


def test_dry_run_needs_neither_a_config_nor_the_venv(box):
    box.cfgp.unlink()
    (box.root / ".venv" / "bin" / "dbw").unlink()
    assert sched(box, "install", "--runner", "cron", "--dry-run") == 0


# --- status and remove ---------------------------------------------------------------------------------

@MAC_ONLY
def test_status_before_and_after_install(box, capsys):
    sched(box, "status", "--runner", "launchd")
    assert "installed: no" in capsys.readouterr().out
    sched(box, "install", "--runner", "launchd", "--time", "07:05")
    capsys.readouterr()
    log = box.root / "data" / "dbw-run.log"
    log.parent.mkdir(exist_ok=True)
    log.write_text("[2026-10-02 07:05:03+03:00] dbw run start\n[2026-10-02 07:06:01+03:00] RESULT ok\n", encoding="utf-8")
    assert sched(box, "status", "--runner", "launchd") == 0
    out = capsys.readouterr().out
    for needle in ("installed: yes", "runner: launchd", "time: 07:05", "next run: ", "last run: 2026-10-02 07:06 - ok",
                   f"log: {log}"):
        assert needle in out, needle


@MAC_ONLY
def test_status_with_no_log_says_never_ran(box, capsys):
    sched(box, "install", "--runner", "launchd")
    capsys.readouterr()
    sched(box, "status", "--runner", "launchd")
    assert "last run: never" in capsys.readouterr().out


@MAC_ONLY
def test_remove_takes_the_job_and_leaves_config_and_data(box, capsys):
    sched(box, "install", "--runner", "launchd", "--time", "07:05")
    (box.root / "data").mkdir(exist_ok=True)
    (box.root / "data" / "dbw-run.log").write_text("x", encoding="utf-8")
    capsys.readouterr()
    assert sched(box, "remove", "--runner", "launchd") == 0
    assert not box.plist.exists() and box.cfgp.exists() and (box.root / "data" / "dbw-run.log").exists()
    assert "removed" in capsys.readouterr().out


@MAC_ONLY
def test_remove_when_nothing_is_installed_is_not_an_error(box, capsys):
    box.run.answers[("launchctl", "bootout")] = (113, "", "Could not find service")  # what launchctl says for an absent job
    assert sched(box, "remove", "--runner", "launchd") == 0
    assert "not installed" in capsys.readouterr().out


# --- config -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("body,match", [("runner: systemd", "launchd, cron, schtasks"),
                                        ("schedule: {time: '25:00'}", "HH:MM"), ("schedule: nope", "schedule")])
def test_config_validates_runner_and_time(tmp_path, body, match):
    p = tmp_path / "c.yaml"
    p.write_text(f"plants: [hadera]\n{body}\n", encoding="utf-8")
    with pytest.raises(config.ConfigError, match=match):
        config.load(p)


def test_config_accepts_runner_and_time(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("plants: [hadera]\nrunner: cron\nschedule: {time: '07:05'}\n", encoding="utf-8")
    assert config.load(p)["runner"] == "cron"


def test_set_schedule_keeps_every_other_key(tmp_path):
    p = tmp_path / "c.yaml"
    config.write(p, ["hadera", "eilat"], "r", registry.load(), language="he")
    config.set_schedule(p, "cron", "07:05")
    cfg = config.load(p)
    assert cfg["plants"] == ["hadera", "eilat"] and cfg["report"]["language"] == "he"
    assert cfg["runner"] == "cron" and cfg["schedule"] == {"time": "07:05"}
    assert p.read_text(encoding="utf-8").startswith("# Written by `dbw setup`")


# --- setup offers the schedule -------------------------------------------------------------------------------

def setup(box, *extra):
    new = str(box.tmp / "new.yaml")
    return cli.main(["setup", "--plants", "hadera", "--out", str(box.tmp / "r"), "--config", new, "--skip-backfill",
                     *extra]), new


def test_setup_schedule_installs_and_records(box):
    rc, new = setup(box, "--yes", "--schedule", "--time", "07:05", "--runner", "cron")
    assert rc == 0 and box.run.calls[-1] == ["crontab", "-"]
    assert config.load(new)["runner"] == "cron" and config.load(new)["schedule"] == {"time": "07:05"}


def test_setup_schedule_without_a_time_uses_the_default(box):
    rc, new = setup(box, "--yes", "--schedule", "--runner", "cron")
    assert config.load(new)["schedule"] == {"time": "01:15"}


def test_setup_yes_alone_installs_nothing(box):
    rc, new = setup(box, "--yes")
    assert rc == 0 and box.run.calls == [] and "runner" not in config.load(new)


def test_setup_no_schedule_installs_nothing_even_interactively(box, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("no question expected"))
    rc, new = setup(box, "--language", "en", "--no-schedule", "--no-telegram")
    assert rc == 0 and box.run.calls == []


@pytest.mark.parametrize("answer,installed", [("", True), ("y", True), ("Y", True), ("n", False), ("no", False)])
def test_setup_asks_the_question_with_yes_as_the_default(box, monkeypatch, answer, installed):
    asked = []
    monkeypatch.setattr("builtins.input", lambda prompt="": asked.append(prompt) or answer)
    monkeypatch.setattr(schedule, "default_runner", lambda platform=None: "cron")
    rc, new = setup(box, "--language", "en", "--no-telegram")
    assert rc == 0 and asked == ["Run this every day at 01:15? [Y/n] "]
    assert bool(box.run.calls) is installed


def test_setup_schedule_and_no_schedule_conflict(box):
    with pytest.raises(SystemExit):
        setup(box, "--yes", "--schedule", "--no-schedule")


def test_setup_reports_a_failed_schedule_but_keeps_the_report(box, capsys):
    box.run.answers[("crontab", "-")] = (1, "", "crontab: permission denied")
    rc, new = setup(box, "--yes", "--schedule", "--runner", "cron")
    assert rc == 1 and "permission denied" in capsys.readouterr().err
    assert (box.tmp / "r").exists() and config.load(new)["plants"] == ["hadera"]
