"""A committed export of the per-box seasonal percentiles (and the pixel-set signatures), so a fresh
`dbw setup` fetches only recent days instead of six years of history. The numbers are recomputed from
the stored NOAA history by scripts/export_percentiles.py; nothing here is hand-entered. No network."""
import json
from datetime import datetime, timezone
from pathlib import Path

from dbw import climatology, store
from dbw.providers import noaa_erddap

BUNDLED = Path(__file__).resolve().parent / "data" / "percentiles.json"
DECIMALS = 4
METHOD = (f"Per box and source, the daily box median is bucketed on a 365-day calendar (Feb 29 counts as Feb 28) "
          f"and each day of year gets P50, P75, P90 and P97 over a +-{climatology.HALF_WINDOW}-day window across all "
          f"years; a window with fewer than {climatology.MIN_N} samples has no percentile (null, the day scores grey). "
          "Same code as `dbw backfill` + percentile rebuild (dbw/climatology.py).")


def build(conn, box_ids, sources=climatology.BACKFILL_SOURCES):
    """The export dict for `box_ids`, recomputed from obs in `conn`."""
    pctl, cells, first, last = {}, {}, None, None
    for src in sources:
        pctl[src], cells[src] = {}, {}
        for box in box_ids:
            series = store.load_series(conn, src, box, climatology.PCTL_STAT)
            if not series:
                continue
            first = min(first or series[0][0], series[0][0])
            last = max(last or series[-1][0], series[-1][0])
            pc = climatology.seasonal_percentiles(series)
            pctl[src][box] = [[doy, p.n, *(round(x, DECIMALS) for x in (p.p50, p.p75, p.p90, p.p97))] if p else [doy, 0]
                              for doy, p in sorted(pc.items())]
        for box, (n, sig) in store.get_cells(conn, src).items():
            if box in box_ids:
                cells[src][box] = [n, sig]
    return {
        "header": {
            "what": "Seasonal chlorophyll / SST percentiles per box, for dbw setup (see docs/percentile-export.md)",
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "history": {"first": first.isoformat() if first else None, "last": last.isoformat() if last else None},
            "datasets": {s: f"{noaa_erddap.BASE}/{s}.html" for s in sources},
            "stat": climatology.PCTL_STAT,
            "method": METHOD,
            "columns": ["doy", "n", "p50", "p75", "p90", "p97"],
            "licence": "Derived from NOAA CoastWatch data. Chlorophyll: public domain, US government data. SST: NOAA Coral Reef Watch CoralTemp, under its own licence text (research use; see docs/sources.md).",
        },
        "pctl": pctl,
        "cells": cells,
    }


def write(path, data):
    Path(path).write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")


def load(path=None):
    """The export dict, or None when the file does not exist."""
    path = Path(path) if path else BUNDLED
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def install(conn, data, box_ids):
    """Load the export for `box_ids` into `conn`. A (source, box) that already has percentiles
    (the user backfilled their own) is left alone. Returns the number of (source, box) loaded."""
    loaded = 0
    for src, boxes in data["pctl"].items():
        for box in box_ids:
            rows = boxes.get(box)
            if rows is None or store.get_pctl(conn, src, box, data["header"]["stat"]):
                continue
            pc = {r[0]: (climatology.Pctl(*r[1:]) if len(r) > 2 else None) for r in rows}
            store.put_pctl(conn, src, box, data["header"]["stat"], pc)
            loaded += 1
    for src, boxes in data["cells"].items():
        for box in box_ids:
            if box in boxes:
                store.put_cells_signature(conn, src, box, *boxes[box])
    return loaded
