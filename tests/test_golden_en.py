"""The English output must not change by accident. golden_en_score.json was written by scripts/make_golden_en_score.py
at the commit before the i18n refactor (1bc304f) and has not moved since: the scoring rules are untouched.
tests/fixtures/golden_en/*.{md,html} were written by scripts/make_golden_en.py at that commit and REGENERATED in
DBW-3c, when the report got its plain layer (summary, cards, appendix) on top of the technical details; what the old
layout contained is kept in golden_en_pre_readable/ and tests/test_readable.py proves none of it was lost.
golden_db.json is the slice of the database the cases need."""
import json
from datetime import date
from pathlib import Path

import pytest

from dbw import registry, report, store
from dbw.score import score_box

import golden_scenarios

FIX = Path(__file__).parent / "fixtures"
DB = json.loads((FIX / "golden_db.json").read_text(encoding="utf-8"))


def _load(conn, data):
    with conn:
        conn.executemany("INSERT INTO obs(date,source,box,stat,value,fetched_at,data_time,note) VALUES (?,?,?,?,?,?,?,?)", data["obs"])
        conn.executemany("INSERT INTO pctl(source,box,stat,doy,n,p50,p75,p90,p97,built_at) VALUES (?,?,?,?,?,?,?,?,?,?)", data["pctl"])
        conn.executemany("INSERT INTO cells(source,box,n,signature) VALUES (?,?,?,?)", data["cells"])


@pytest.fixture(scope="module")
def reports(tmp_path_factory):
    out = {}
    for name, case in DB.items():
        conn = store.connect(tmp_path_factory.mktemp(name) / "g.sqlite")
        _load(conn, case)
        out[name] = report.build_report(conn, registry.load(), case["plants"], date.fromisoformat(case["date"]))
    return out


@pytest.mark.parametrize("name", list(DB))
def test_en_markdown_is_byte_identical_to_the_golden(reports, name):
    assert report.render_markdown(reports[name]).encode("utf-8") == (FIX / "golden_en" / f"{name}.md").read_bytes()


@pytest.mark.parametrize("name", list(DB))
def test_en_html_is_byte_identical_to_the_golden(reports, name):
    assert report.render_html(reports[name]).encode("utf-8") == (FIX / "golden_en" / f"{name}.html").read_bytes()


@pytest.mark.parametrize("name", list(DB))
def test_en_html_has_a_proper_head(name):
    """DBW-4 6c added <!doctype>, <html lang dir>, <head> (charset, viewport, title)."""
    head = (FIX / "golden_en" / f"{name}.html").read_text(encoding="utf-8").partition("<body ")[0]
    assert head.startswith('<!doctype html>\n<html lang="en" dir="ltr">\n<head><meta charset="utf-8">')
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in head
    assert "<title>Desal Bloom Watch — " in head and head.endswith("</head>\n")


def test_goldens_cover_upstream_signal_and_both_grey_reasons():
    text = "\n".join(p.read_text(encoding="utf-8") for p in (FIX / "golden_en").glob("*.md"))
    assert "upstream signal" in text and "no data: no valid observation" in text and "stale: newest valid" in text
    assert "shares the same satellite pixels" in text and "days old" in text


def test_score_battery_is_unchanged():
    golden = json.loads((FIX / "golden_en_score.json").read_text(encoding="utf-8"))
    seen = 0
    for key, kw in golden_scenarios.scenarios():
        sc = score_box(**kw)
        got = {"level": int(sc.level), "reasons": [str(r) for r in sc.reasons], "as_of": str(sc.as_of), "value": sc.value,
               "rank": sc.rank, "extent": sc.extent}
        assert got == golden[key], key
        seen += 1
    assert seen == len(golden) > 1000
