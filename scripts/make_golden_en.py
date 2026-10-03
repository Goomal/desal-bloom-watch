"""Writes the English golden fixtures for tests/test_golden_en.py (run ONCE, at the commit before the i18n
refactor, from a full history database). Copies only the rows each case needs into tests/fixtures/golden_db.json,
renders md + html from that subset, and checks that the subset renders exactly like the full database.
Do not re-run it after the refactor: the point is that the `en` output stays byte-identical to what this wrote."""
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from dbw import climatology as clim
from dbw import registry, report, store

CASES = {  # name: (report date, plants)
    "upstream_red_shared": (date(2026, 9, 2), ["hadera", "ashkelon", "sorek_a", "sorek_b"]),  # hadera lifted by a sentinel, ashkelon red, sorek_a/b share pixels
    "upstream_orange": (date(2026, 8, 27), ["ashkelon", "eilat"]),
    "grey_no_data": (date(2023, 8, 25), ["eilat", "hadera"]),  # eilat: no valid observation
    "grey_stale": (date(2023, 9, 15), ["eilat", "palmachim"]),  # eilat: newest valid observation too old
    "aged_data": (date(2026, 10, 2), ["ashkelon", "hadera"]),  # newest data is 3 days older than the report date
}
WINDOW = 8
FIX = Path("tests/fixtures")


def subset(src, case_boxes, day):
    ids = sorted(case_boxes)
    ph = ",".join("?" * len(ids))
    lo, hi = (day - timedelta(days=WINDOW)).isoformat(), day.isoformat()
    doys = sorted({clim.doy365(day - timedelta(days=k)) for k in range(WINDOW)})
    dph = ",".join("?" * len(doys))
    cols = "date,source,box,stat,value,fetched_at,data_time,note"
    obs = [list(r) for r in src.execute(
        f"SELECT {cols} FROM obs WHERE box IN ({ph}) AND date BETWEEN ? AND ?", (*ids, lo, hi))]
    # the report header names the newest valid date per source even when it is older than the window
    for source, box in src.execute(f"SELECT DISTINCT source, box FROM obs WHERE box IN ({ph})", ids).fetchall():
        newest = src.execute("SELECT MAX(date) FROM obs WHERE source=? AND box=? AND stat='median' AND date<=?",
                             (source, box, hi)).fetchone()[0]
        if newest and newest < lo:
            obs += [list(r) for r in src.execute(f"SELECT {cols} FROM obs WHERE source=? AND box=? AND date=?",
                                                 (source, box, newest))]
    return {
        "obs": _round(obs, {4}),
        "pctl": _round([list(r) for r in src.execute(
            f"SELECT source,box,stat,doy,n,p50,p75,p90,p97,built_at FROM pctl WHERE box IN ({ph}) AND doy IN ({dph})",
            (*ids, *doys))], {5, 6, 7, 8}),
        "cells": [list(r) for r in src.execute(f"SELECT source,box,n,signature FROM cells WHERE box IN ({ph})", ids)],
    }


def _round(rows, cols):
    """Round the float columns to 6 decimals: shorter fixture, and the checks below prove the render is unchanged."""
    return [[round(v, 6) if i in cols and isinstance(v, float) else v for i, v in enumerate(r)] for r in rows]


def load(conn, data):
    with conn:
        conn.executemany("INSERT INTO obs(date,source,box,stat,value,fetched_at,data_time,note) VALUES (?,?,?,?,?,?,?,?)", data["obs"])
        conn.executemany("INSERT INTO pctl(source,box,stat,doy,n,p50,p75,p90,p97,built_at) VALUES (?,?,?,?,?,?,?,?,?,?)", data["pctl"])
        conn.executemany("INSERT INTO cells(source,box,n,signature) VALUES (?,?,?,?)", data["cells"])


def main():
    boxes = registry.load()
    by_id = {b.id: b for b in boxes}
    full = store.connect()
    out = {}
    for name, (day, plants) in CASES.items():
        ids = set(plants) | {s for p in plants for s in by_id[p].sentinels}
        out[name] = {"date": day.isoformat(), "plants": plants, **subset(full, ids, day)}
        tmp = store.connect(Path(tempfile.mkdtemp()) / "g.sqlite")
        load(tmp, out[name])
        a = report.build_report(full, boxes, plants, day)
        b = report.build_report(tmp, boxes, plants, day)
        for fn in (report.render_markdown, report.render_html):
            if fn(a) != fn(b):
                sys.exit(f"{name}: subset database renders differently from the full one ({fn.__name__}); widen WINDOW")
        stem = FIX / "golden_en" / name
        stem.with_suffix(".md").write_text(report.render_markdown(b), encoding="utf-8")
        stem.with_suffix(".html").write_text(report.render_html(b), encoding="utf-8")
        print(name, day, [f"{p.id}:{p.level.name}" for p in b.plants])
    (FIX / "golden_db.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
