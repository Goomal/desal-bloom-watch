"""assess.py: store -> score glue, on a synthetic database. Offline."""
from datetime import date, timedelta

import pytest

from dbw import climatology as clim
from dbw import store
from dbw.assess import DINEOF, N20, SST, Assessor
from dbw.providers.base import BoxStats, NoData
from dbw.registry import Box
from dbw.score import Level

SQ = ((31.0, 34.0), (31.0, 34.1), (31.1, 34.1), (31.1, 34.0), (31.0, 34.0))
PLANT = Box("p", "plant", SQ, "mediterranean", ("s",))
TWIN = Box("twin", "plant", SQ, "mediterranean", ("s",))
SENT = Box("s", "sentinel", SQ, "mediterranean")
EVENT = date(2026, 8, 25)


def A(conn, boxes, mode="dineof", **kw):
    return Assessor(conn, boxes, mode=mode, **kw)


def bs(v, valid=10, total=10):
    return BoxStats(valid, total, v, v, v, v, v)


@pytest.fixture
def conn(tmp_path):
    c = store.connect(tmp_path / "t.sqlite")
    # 5 summers (2021..2025) of calm water, 1.00-1.19, 81 days each around Aug 25
    for source in (DINEOF, N20):
        for box in ("p", "twin", "s"):
            rows = {}
            for y in range(2021, 2026):
                for k in range(-40, 41):
                    rows[date(y, 8, 25) + timedelta(days=k)] = bs(1.0 + 0.01 * ((k * 7 + y) % 20))
            store.write_days(c, source, box, rows)
    for box in ("p", "twin", "s"):
        for source in (DINEOF, N20):
            clim.build_percentiles(c, source, box, min_n=5)
    return c


def put(conn, source, box, day, result):
    store.write_days(conn, source, box, {day: result})


def test_calm_summer_day_is_green(conn):
    put(conn, DINEOF, "p", EVENT, bs(1.0))
    sc = A(conn, [PLANT, SENT]).assess("p", EVENT)
    assert sc.level is Level.GREEN and sc.reasons[0].startswith("source: DINEOF")


def test_bloom_day_scores_high_and_reports_the_percentile(conn):
    put(conn, DINEOF, "p", EVENT, bs(9.0))
    sc = A(conn, [PLANT, SENT]).assess("p", EVENT)
    assert sc.level is Level.RED and sc.rank == ">=P97"


def test_day_without_a_row_is_grey_not_green(conn):
    sc = A(conn, [PLANT, SENT]).assess("p", date(2026, 8, 25))
    assert sc.level is Level.GREY


def test_nodata_row_is_grey(conn):
    put(conn, DINEOF, "p", EVENT, NoData("all_nan", total_count=10))
    assert A(conn, [PLANT, SENT]).assess("p", EVENT).level is Level.GREY


def test_sentinel_upgrade_uses_the_stored_sentinel_percentile(conn):
    p = A(conn, [PLANT, SENT]).pctl(DINEOF, "p", EVENT)
    put(conn, DINEOF, "p", EVENT, bs((p.p90 + p.p97) / 2))  # yellow on its own
    base = A(conn, [PLANT, SENT]).assess("p", EVENT)
    put(conn, DINEOF, "s", EVENT, bs(9.0))
    up = A(conn, [PLANT, SENT]).assess("p", EVENT)
    assert base.level is Level.YELLOW and up.level is Level.ORANGE
    assert any("s:" in r or "sentinel s" in r for r in up.reasons)


def test_leave_year_out_does_not_score_an_event_against_itself(conn):
    # a 2026 bloom of 20 days: left in, it raises its own P97; left out (as in the hindcast) it cannot
    for k in range(-10, 10):
        put(conn, DINEOF, "p", EVENT + timedelta(days=k), bs(3.0))
    clim.build_percentiles(conn, DINEOF, "p", min_n=5)
    kept = A(conn, [PLANT, SENT]).pctl(DINEOF, "p", EVENT)
    loo = A(conn, [PLANT, SENT], leave_out=True).pctl(DINEOF, "p", EVENT)
    assert loo.n < kept.n and loo.p97 < kept.p97 < 3.1


def test_identical_pixel_sets_are_flagged(conn):
    for b in ("p", "twin"):
        store.put_cells(conn, DINEOF, b, ((31.05, 34.05), (31.05, 34.07)))
    put(conn, DINEOF, "p", EVENT, bs(1.0))
    sc = A(conn, [PLANT, TWIN, SENT]).assess("p", EVENT)
    assert "shares the same satellite pixels with twin; not independent" in " | ".join(sc.reasons)


def test_different_pixel_sets_are_not_flagged(conn):
    store.put_cells(conn, DINEOF, "p", ((31.05, 34.05),))
    store.put_cells(conn, DINEOF, "twin", ((31.05, 34.07),))
    put(conn, DINEOF, "p", EVENT, bs(1.0))
    assert "shares" not in " | ".join(A(conn, [PLANT, TWIN, SENT]).assess("p", EVENT).reasons)


def test_orange_two_days_running_in_a_range_becomes_red(conn):
    p = A(conn, [PLANT, SENT]).pctl(DINEOF, "p", EVENT)
    for k in (0, 1):
        put(conn, DINEOF, "p", EVENT + timedelta(days=k), bs(p.p97 + 0.005))  # orange, nowhere near 3 x median
    r = A(conn, [PLANT, SENT]).assess_range("p", EVENT, EVENT + timedelta(days=1))
    assert r[EVENT].level is Level.ORANGE and r[EVENT + timedelta(days=1)].level is Level.RED


def test_n20_mode_prefers_n20_and_falls_back_to_dineof(conn):
    put(conn, DINEOF, "p", EVENT, bs(1.0))
    a = A(conn, [PLANT, SENT], mode="n20_else_dineof")
    sc = a.assess("p", EVENT)  # N20 has nothing that day -> DINEOF
    assert sc.reasons[0].startswith("fallback: N20 no data") and sc.reasons[1].startswith("source: DINEOF")
    put(conn, N20, "p", EVENT, bs(1.0))
    assert A(conn, [PLANT, SENT], mode="n20_else_dineof").assess("p", EVENT).reasons[0].startswith("source: N20")
    put(conn, N20, "p", EVENT, bs(1.0, valid=1, total=20))  # N20 cloud-covered -> DINEOF
    sc = A(conn, [PLANT, SENT], mode="n20_else_dineof").assess("p", EVENT)
    assert sc.reasons[0].startswith("fallback: N20 low coverage") and sc.reasons[1].startswith("source: DINEOF")


def test_unknown_mode_is_rejected(conn):
    with pytest.raises(ValueError):
        A(conn, [PLANT], mode="blend")


# --- hindcast grid + verdict -----------------------------------------------------------------------
from dbw.assess import hindcast_verdict, plan_clause_verdict, render_grid
from dbw.score import Score

D0 = date(2026, 8, 25)


def row(*levels):
    return {D0 + timedelta(days=i): Score(lv) for i, lv in enumerate(levels)}


G, Y, O, R, N = Level.GREEN, Level.YELLOW, Level.ORANGE, Level.RED, Level.GREY


def test_grid_prints_one_letter_per_day_and_dot_for_grey():
    out = render_grid({"ashkelon": row(G, O, R, N), "hadera": row(G, G, Y, G)})
    lines = out.splitlines()
    assert lines[2].split()[1:] == ["G", "O", "R", "."] and lines[3].split()[1:] == ["G", "G", "Y", "G"]


CUT = D0 + timedelta(days=5)
CORE = {"ashkelon": row(G, O), "ashdod": row(G, G), "sorek_a": row(G, G), "sorek_b": row(O, G)}


def test_revised_verdict_passes_with_ashkelon_one_sorek_and_a_quiet_hadera():
    ok, facts = hindcast_verdict({**CORE, "hadera": row(G, Y)}, CUT)
    assert ok and any("hadera" in f for f in facts)


def test_revised_verdict_ashdod_can_stand_in_for_sorek():
    grid = {"ashkelon": row(R), "ashdod": row(O), "sorek_a": row(G), "sorek_b": row(G), "hadera": row(G)}
    assert hindcast_verdict(grid, CUT)[0]


def test_revised_verdict_fails_without_ashkelon():
    grid = {**CORE, "ashkelon": row(Y, Y), "hadera": row(G, G)}
    assert not hindcast_verdict(grid, CUT)[0]


def test_revised_verdict_fails_when_hadera_is_orange_before_the_cutoff():
    assert not hindcast_verdict({**CORE, "hadera": row(G, O)}, CUT)[0]


def test_revised_verdict_ignores_hadera_after_the_cutoff():
    hadera = {**row(G), D0 + timedelta(days=9): Score(R)}
    assert hindcast_verdict({**CORE, "hadera": hadera}, CUT)[0]


def test_revised_verdict_fails_when_a_core_plant_is_orange_only_after_the_cutoff():
    grid = {"ashkelon": row(G, G, O), "ashdod": row(O, O, O), "sorek_a": row(O, O, O), "sorek_b": row(G, G, G),
            "hadera": row(G, G, G)}
    assert not hindcast_verdict(grid, D0 + timedelta(days=2))[0]


def test_revised_verdict_fails_when_everything_is_grey():
    grid = {p: row(N, N) for p in ("ashkelon", "ashdod", "sorek_a", "sorek_b", "hadera")}
    assert not hindcast_verdict(grid, CUT)[0]


def test_original_plan_clause_needs_all_three_and_hadera_lower_over_the_window():
    ok_grid = {"ashkelon": row(G, O), "ashdod": row(Y, R), "sorek_a": row(G, G), "sorek_b": row(O, G), "hadera": row(G, Y)}
    assert plan_clause_verdict(ok_grid, CUT)[0]
    assert not plan_clause_verdict({**ok_grid, "ashdod": row(Y, Y)}, CUT)[0]  # Ashdod never orange
    assert not plan_clause_verdict({**ok_grid, "hadera": row(G, O)}, CUT)[0]  # Hadera as high as Sorek
