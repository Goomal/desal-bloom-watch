"""August 2026 hindcast as an offline regression test: a small real-data fixture
(tests/fixtures/hindcast_2026-08.json, made by scripts/export_hindcast_fixture.py) scored with the
shipped rules. The grid is the golden answer; a rule change that moves it must be a conscious one."""
import json
from datetime import date
from pathlib import Path

import pytest

from dbw import registry, store
from dbw.assess import CORE_BEFORE, Assessor, Level, hindcast_verdict, plan_clause_verdict, render_grid
from dbw.climatology import Pctl

FIX = json.loads((Path(__file__).parent / "fixtures" / "hindcast_2026-08.json").read_text(encoding="utf-8"))
START, END = date(2026, 8, 20), date(2026, 9, 10)
PLANTS = ("hadera", "sorek_a", "sorek_b", "palmachim", "ashdod", "ashkelon", "western_galilee", "eilat")

GOLDEN = """\
                 20 21 22 23 24 25 26 27 28 29 30 31 01 02 03 04 05 06 07 08 09 10
                 08 08 08 08 08 08 08 08 08 08 08 08 09 09 09 09 09 09 09 09 09 09
hadera            G  G  G  G  G  G  G  G  G  G  G  G  G  O  G  G  G  G  G  O  R  R
sorek_a           G  G  G  G  G  G  G  G  O  R  R  R  R  R  R  R  R  R  R  R  R  R
sorek_b           G  G  G  G  G  G  G  G  O  R  R  R  R  R  R  R  R  R  R  R  R  R
palmachim         G  G  G  G  G  G  G  G  G  G  G  G  G  R  R  R  R  R  R  R  R  R
ashdod            G  G  G  G  G  G  G  G  G  G  G  O  R  R  R  R  R  R  R  R  R  R
ashkelon          G  G  G  G  G  R  R  R  R  R  R  R  R  R  R  R  R  R  R  R  R  R
western_galilee   G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G
eilat             G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G"""


@pytest.fixture(scope="module")
def grid(tmp_path_factory):
    conn = store.connect(tmp_path_factory.mktemp("hc") / "hc.sqlite")
    for key, days in FIX["obs"].items():
        source, box = key.split("|")
        for day, vals in days.items():
            for stat, v in zip(("valid_count", "total_count", "median", "p90"), vals):
                if v is not None:
                    conn.execute("INSERT INTO obs(date, source, box, stat, value, fetched_at) VALUES (?,?,?,?,?,'')",
                                 (day, source, box, stat, v))
    conn.commit()
    for key, rows in FIX["pctl"].items():
        source, box = key.split("|")
        store.put_pctl(conn, source, box, "median", {int(k): (Pctl(*v) if v else None) for k, v in rows.items()})
    for source, cells in FIX["cells"].items():
        for box, (n, sig) in cells.items():
            conn.execute("INSERT INTO cells(source, box, n, signature) VALUES (?,?,?,?)", (source, box, n, sig))
    conn.commit()
    a = Assessor(conn, registry.load())  # shipped default mode, stored (leave-2026) percentiles
    return {p: a.assess_range(p, START, END) for p in PLANTS}


def test_grid_is_the_golden_one(grid):
    assert render_grid(grid) == GOLDEN


def test_core_plants_reach_orange_or_red_before_the_cutoff(grid):
    cut = date.fromisoformat(CORE_BEFORE)
    for p in ("ashkelon", "sorek_a", "sorek_b"):
        assert max(s.level for d, s in grid[p].items() if d < cut) >= Level.ORANGE


def test_revised_acceptance_clause_passes(grid):
    """Approved 2026-10-01: Ashkelon and (Ashdod or a Sorek box) reach orange+ before 30 Aug and
    Hadera stays below orange on every day before 30 Aug."""
    ok, facts = hindcast_verdict(grid, date.fromisoformat(CORE_BEFORE))
    assert ok, facts
    assert "ashkelon: worst before 2026-08-30 = RED" in facts
    assert "sorek: worst before 2026-08-30 = RED" in facts
    assert "hadera: worst before 2026-08-30 = GREEN" in facts


def test_original_plan_clause_still_fails_and_the_doc_says_so(grid):
    """Ashdod first turns orange on 31 Aug, one day late, and Hadera reaches red on 09 Sep."""
    ok, facts = plan_clause_verdict(grid, date.fromisoformat(CORE_BEFORE))
    assert not ok
    assert "ashdod: worst before 2026-08-30 = GREEN" in facts
    assert "hadera: worst over the window = RED" in facts
    assert grid["ashdod"][date(2026, 8, 31)].level is Level.ORANGE
    assert grid["hadera"][date(2026, 9, 9)].level is Level.RED


def test_nothing_is_grey_in_the_window(grid):
    assert all(s.level is not Level.GREY for row in grid.values() for s in row.values())


def test_reasons_carry_source_and_overlap_flag(grid):
    r = " | ".join(grid["sorek_a"][date(2026, 8, 29)].reasons)
    assert "source: N20" in r and "sorek_b" in r and "not independent" in r
