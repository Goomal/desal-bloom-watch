"""Export the small offline fixture behind tests/test_hindcast.py from a filled data/dbw.sqlite:
daily box stats for every plant and sentinel over the hindcast window (plus the look-back), the
seasonal percentiles of those days built WITHOUT the hindcast year, and the pixel-set signatures.
Usage: python scripts/export_hindcast_fixture.py [--from 2026-08-10] [--to 2026-09-10]"""
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from dbw import climatology as clim
from dbw import registry, store
from dbw.assess import DINEOF, N20

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "hindcast_2026-08.json"
STATS = ("valid_count", "total_count", "median", "p90")


def _r(v):
    """5 decimals: far below the satellite noise, and keeps the fixture small."""
    return None if v is None else round(v, 5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="2026-08-10")
    ap.add_argument("--to", dest="end", default="2026-09-10")
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    conn = store.connect()
    boxes = registry.load()
    doys = sorted({clim.doy365(start + timedelta(days=k)) for k in range((end - start).days + 1)})
    out = {"year": end.year, "obs": {}, "pctl": {}, "cells": {}}
    for source in (N20, DINEOF):
        out["cells"][source] = {b: list(v) for b, v in store.get_cells(conn, source).items()}
        for box in boxes:
            days = store.load_days(conn, source, box.id)
            rows = {d.isoformat(): [_r(st.get(k)) for k in STATS] for d, st in days.items() if start <= d <= end}
            if rows:
                out["obs"][f"{source}|{box.id}"] = rows
            pc = clim.seasonal_percentiles(store.load_series(conn, source, box.id), exclude_year=end.year)
            out["pctl"][f"{source}|{box.id}"] = {str(k): [_r(v) for v in pc[k].__dict__.values()] if pc[k] else None for k in doys}
    OUT.write_text(json.dumps(out, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    print(f"{OUT}: {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
