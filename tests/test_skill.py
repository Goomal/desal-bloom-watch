"""The skill file: one SKILL.md for Claude Code and Codex, reachable from a clone through a committed relative link."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = ROOT / ".agents" / "skills" / "desal-bloom-watch"
SKILL = (ROOT / "skill" / "SKILL.md").read_text(encoding="utf-8")


def frontmatter():
    return dict(line.split(": ", 1) for line in SKILL.split("---")[1].strip().splitlines())


def test_codex_link_is_a_relative_symlink_to_the_skill_folder():
    assert LINK.is_symlink() and Path(os.readlink(LINK)).as_posix() == "../../skill"
    assert (LINK / "SKILL.md").read_text(encoding="utf-8") == SKILL


def test_frontmatter_has_the_codex_keys_and_the_menu_hint():
    fm = frontmatter()
    assert fm["name"] == "desal-bloom-watch" and fm["description"]
    assert fm["argument-hint"] == '"[setup|run|schedule|explain|add-plant]"'


def test_start_here_menu_comes_first_and_has_the_four_choices():
    assert SKILL.index("## Start here") < SKILL.index("## 1. ")
    menu = SKILL.split("## Start here")[1].split("## 1. ")[0]
    for choice in ("Setup", "Run today's report", "Schedule daily run", "Explain a report"):
        assert choice in menu
    assert "four options" in menu and "Add a plant" not in menu
    assert "Other" in menu and "`add-plant`" in menu  # a fifth route, said in the question text


def test_schedule_section_drives_the_three_commands_and_names_the_log():
    section = SKILL.split("## 5. Schedule")[1].split("\n## ")[0]
    for needle in ("dbw schedule status", "dbw schedule install --time", "dbw schedule remove", "data/dbw-run.log",
                   "Every day at", "Not now", "07:00"):
        assert needle in section
    assert "numbered plain-text list" in section or "plain text" in section


def test_setup_asks_the_daily_run_question_with_three_options():
    setup = SKILL.split("## 1. Setup")[1].split("\n## 2. ")[0]
    assert "Daily run" in setup
    for option in ("Every day at 07:00 (Recommended)", "Pick another time", "Not now"):
        assert option in setup
    assert "--schedule" in setup and "--no-schedule" in setup


def test_plants_come_from_dbw_plants_and_the_install_route_is_dbw_skill_install():
    assert "dbw plants --json" in SKILL and "registry.load()" not in SKILL
    install = SKILL.split("## Install the skill")[1]
    assert "dbw skill install" in install and install.index("dbw skill install") < install.index("ln -s")
    assert "--codex" in install and "--force" in install
    assert "plain text file" in install  # the Windows caveat about the committed link


def test_venv_tool_paths_are_given_per_os():
    assert "py -3 -m venv .venv" in SKILL and ".venv\\Scripts\\dbw" in SKILL and ".venv/bin/dbw" in SKILL


def test_setup_asks_the_language_and_passes_it():
    assert "Report language" in SKILL and "--language <en|he|ar>" in SKILL
    for label in ("English", "עברית", "العربية"):
        assert label in SKILL


def test_codex_paragraph_and_fallback():
    assert ".agents/skills/desal-bloom-watch -> ../../skill" in SKILL
    assert "~/.agents/skills" in SKILL and "$desal-bloom-watch setup" in SKILL
    assert re.search(r"Codex has no checkbox picker", SKILL)


def test_setup_asks_the_telegram_question_after_the_daily_run_and_defers_the_work_to_section_6():
    setup = SKILL.split("## 1. Setup")[1].split("\n## 2. ")[0]
    assert setup.index("Daily run") < setup.index("Telegram (a second call")
    q = " ".join(setup.split("Telegram (a second call")[1].split("4. **Confirm")[0].split())
    assert '"Yes" and "Not now"' in q and "single-choice" in q and "do not pass `--telegram`" in q


def test_telegram_section_drives_the_commands_and_never_touches_the_token():
    section = " ".join(SKILL.split("## 6. Telegram")[1].split("\n## ")[0].split())
    for needle in ("dbw telegram chat-id", "dbw telegram chat-id --write", "--pick", "dbw send-test telegram", "--latest",
                   "@BotFather", "DBW_TELEGRAM_TOKEN", "partial: telegram failed", "add a group", "docs/telegram.md"):
        assert needle.lower() in section.lower()
    assert "Never ask the user to paste the bot token into the chat" in section
    assert "Never read the `.env` file" in section and "in their own" in section
    assert "`telegram` is section 6" in SKILL
