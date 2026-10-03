"""The GitHub Actions workflow is not run here; this checks that it parses and has the pieces the brief asks for."""
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "daily.yml"
TEXT = WORKFLOW.read_text(encoding="utf-8")
DOC = yaml.safe_load(TEXT)
TRIGGERS = DOC.get("on", DOC.get(True))  # YAML 1.1 reads a bare `on` key as True
STEPS = DOC["jobs"]["run"]["steps"]


def test_triggers_are_a_daily_utc_cron_and_manual_dispatch_only():
    assert set(TRIGGERS) == {"schedule", "workflow_dispatch"}
    assert [c["cron"] for c in TRIGGERS["schedule"]] == ["0 4 * * *"]  # 04:00 UTC = 07:00 IDT / 06:00 IST
    assert "push" not in TRIGGERS and "pull_request" not in TRIGGERS


def test_steps_check_out_install_set_up_run_upload_and_cache():
    uses = [s["uses"] for s in STEPS if "uses" in s]
    runs = [s["run"] for s in STEPS if "run" in s]
    assert uses[0].startswith("actions/checkout@v") and any(u.startswith("actions/setup-python@v") for u in uses)
    assert any(u.startswith("actions/cache@v") for u in uses) and any(u.startswith("actions/upload-artifact@v") for u in uses)
    assert any(r.startswith("pip install") for r in runs)
    setup = next(r for r in runs if r.startswith("dbw setup"))
    assert "vars.DBW_PLANTS" in setup and "--yes" in setup and "--schedule" not in setup
    assert "dbw run" in runs and runs.index(setup) < runs.index("dbw run")


def test_actions_are_pinned_by_major_version_only():
    for s in STEPS:
        if "uses" in s:
            _, _, ref = s["uses"].partition("@")
            assert ref.startswith("v") and ref[1:].isdigit(), s["uses"]


def test_cache_holds_data_and_artifact_is_the_report_folder():
    cache = next(s for s in STEPS if s.get("uses", "").startswith("actions/cache@"))
    assert cache["with"]["path"] == "data"
    art = next(s for s in STEPS if s.get("uses", "").startswith("actions/upload-artifact@"))
    assert art["with"]["path"].rstrip("/") == "reports"


def test_secrets_are_a_commented_placeholder_only():
    assert "secrets." in TEXT and "# TELEGRAM_BOT_TOKEN: ${{ secrets." in TEXT
    assert not any("secrets." in str(v) for s in STEPS for v in s.values())
    assert "secrets." not in str(DOC["jobs"]["run"].get("env", {}))
