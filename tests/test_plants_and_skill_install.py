"""`dbw plants` (the registry grouped by sea, north to south) and `dbw skill install` (copy skill/ where Claude Code / Codex look)."""
import json
import os

import pytest

from dbw import cli, registry

ROOT = cli._root()


def test_plant_groups_are_by_sea_and_north_to_south():
    groups = cli.plant_groups(registry.load())
    assert [sea for sea, _ in groups] == ["mediterranean", "red_sea"]
    for _, plants in groups:
        lats = [p["lat"] for p in plants]
        assert lats == sorted(lats, reverse=True)
    assert groups[0][1][0]["id"] == "western_galilee" and groups[1][1][0]["id"] == "eilat"
    assert all(p["id"] != "tiran" for _, plants in groups for p in plants)  # sentinels are not offered


def test_plants_prints_the_groups_and_json(capsys):
    assert cli.main(["plants"]) == 0
    out = capsys.readouterr().out
    assert out.index("mediterranean") < out.index("hadera") < out.index("ashkelon") < out.index("red_sea") < out.index("eilat")
    assert cli.main(["plants", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [g["sea"] for g in data] == ["mediterranean", "red_sea"]
    assert {"id", "name", "lat"} <= set(data[0]["plants"][0])


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    return tmp_path / "home"


def test_skill_install_copies_to_the_claude_folder_by_default(home, capsys):
    assert cli.main(["skill", "install"]) == 0
    dest = home / ".claude" / "skills" / "desal-bloom-watch"
    assert (dest / "SKILL.md").read_bytes() == (ROOT / "skill" / "SKILL.md").read_bytes()
    assert not dest.is_symlink() and not (home / ".agents").exists()
    assert str(dest) in capsys.readouterr().out


def test_skill_install_codex_and_both(home):
    assert cli.main(["skill", "install", "--codex"]) == 0
    assert (home / ".agents" / "skills" / "desal-bloom-watch" / "SKILL.md").is_file() and not (home / ".claude").exists()
    assert cli.main(["skill", "install", "--claude", "--codex", "--force"]) == 0
    assert (home / ".claude" / "skills" / "desal-bloom-watch" / "SKILL.md").is_file()


def test_skill_install_project_goes_under_the_current_folder(home, tmp_path):
    assert cli.main(["skill", "install", "--project", "--claude", "--codex"]) == 0
    assert (tmp_path / ".claude" / "skills" / "desal-bloom-watch" / "SKILL.md").is_file()
    assert (tmp_path / ".agents" / "skills" / "desal-bloom-watch" / "SKILL.md").is_file()
    assert not home.exists()


def test_skill_install_refuses_to_overwrite_without_force_and_changes_nothing(home, capsys):
    dest = home / ".claude" / "skills" / "desal-bloom-watch"
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text("mine", encoding="utf-8")
    assert cli.main(["skill", "install", "--claude", "--codex"]) == 1
    assert "--force" in capsys.readouterr().err
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == "mine"
    assert not (home / ".agents").exists()  # all-or-nothing: the free target is not written either
    assert cli.main(["skill", "install", "--force"]) == 0
    assert (dest / "SKILL.md").read_bytes() == (ROOT / "skill" / "SKILL.md").read_bytes()


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_force_replaces_a_link_without_touching_what_it_points_at(home, tmp_path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "keep.txt").write_text("keep", encoding="utf-8")
    dest = home / ".claude" / "skills" / "desal-bloom-watch"
    dest.parent.mkdir(parents=True)
    dest.symlink_to(target, target_is_directory=True)
    assert cli.main(["skill", "install", "--force"]) == 0
    assert not dest.is_symlink() and (dest / "SKILL.md").is_file()
    assert (target / "keep.txt").read_text(encoding="utf-8") == "keep"
