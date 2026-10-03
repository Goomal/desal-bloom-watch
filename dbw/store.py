"""SQLite store: obs(date, source, box, stat, value). Idempotent per (date, source, box)."""
import hashlib
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from dbw.providers.base import BoxStats, NoData

STATS = ("valid_count", "total_count", "mean", "median", "p90", "min", "max")

SCHEMA = """
CREATE TABLE IF NOT EXISTS obs (
    date       TEXT NOT NULL,
    source     TEXT NOT NULL,
    box        TEXT NOT NULL,
    stat       TEXT NOT NULL,
    value      REAL,
    fetched_at TEXT NOT NULL,
    data_time  TEXT,
    note       TEXT,
    PRIMARY KEY (date, source, box, stat)
)"""

# Phase 2 tables. `coverage`: date windows a backfill request fully answered (so a re-run skips
# them even where the dataset has no slice). `cells`: the pixel set a box uses per source, to
# detect boxes that share cells. `pctl`: seasonal percentiles, rebuilt from obs, never hand-entered.
SCHEMA_EXTRA = (
    """CREATE TABLE IF NOT EXISTS coverage (
        source TEXT NOT NULL, box TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
        fetched_at TEXT NOT NULL, PRIMARY KEY (source, box, start))""",
    """CREATE TABLE IF NOT EXISTS cells (
        source TEXT NOT NULL, box TEXT NOT NULL, n INTEGER NOT NULL, signature TEXT NOT NULL,
        PRIMARY KEY (source, box))""",
    """CREATE TABLE IF NOT EXISTS pctl (
        source TEXT NOT NULL, box TEXT NOT NULL, stat TEXT NOT NULL, doy INTEGER NOT NULL,
        n INTEGER NOT NULL, p50 REAL, p75 REAL, p90 REAL, p97 REAL, built_at TEXT NOT NULL,
        PRIMARY KEY (source, box, stat, doy))""",
)


def default_path():
    return Path(os.environ.get("DBW_DB") or "data/dbw.sqlite")


def connect(path=None):
    path = Path(path) if path else default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)
    for stmt in SCHEMA_EXTRA:
        conn.execute(stmt)
    conn.commit()
    return conn


def _rows(result):
    """(rows, data_time, note) for a BoxStats / NoData."""
    if isinstance(result, BoxStats):
        return [(s, getattr(result, s)) for s in STATS if getattr(result, s) is not None], result.data_time, None
    if isinstance(result, NoData):
        rows = [("valid_count", 0)]
        if result.total_count is not None:
            rows.append(("total_count", result.total_count))
        return rows, None, result.reason
    raise TypeError(f"expected BoxStats or NoData, got {type(result).__name__}")


def _put(conn, day, source, box_id, result, fetched_at):
    rows, data_time, note = _rows(result)
    d = day.isoformat()
    conn.execute("DELETE FROM obs WHERE date=? AND source=? AND box=?", (d, source, box_id))
    conn.executemany(
        "INSERT INTO obs(date, source, box, stat, value, fetched_at, data_time, note)"
        " VALUES (?,?,?,?,?,?,?,?)"
        " ON CONFLICT(date, source, box, stat) DO UPDATE SET value=excluded.value,"
        " fetched_at=excluded.fetched_at, data_time=excluded.data_time, note=excluded.note",
        [(d, source, box_id, stat, value, fetched_at, data_time, note) for stat, value in rows])


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_result(conn, day, source, box_id, result, fetched_at=None):
    """Replace every row for (day, source, box) with this result, in one transaction.
    NoData writes valid_count = 0 (+ total_count if known) and the reason in `note`;
    no other stat is written, so nothing is ever zero-filled."""
    with conn:
        _put(conn, day, source, box_id, result, fetched_at or _now())


def write_days(conn, source, box_id, results, fetched_at=None):
    """write_result for many days ({date: result}) in ONE transaction (backfill writes thousands)."""
    fetched_at = fetched_at or _now()
    with conn:
        for day, result in results.items():
            _put(conn, day, source, box_id, result, fetched_at)


def existing_dates(conn, source, box_id, start, end):
    """Dates in [start, end] that already have obs rows for (source, box)."""
    q = "SELECT DISTINCT date FROM obs WHERE source=? AND box=? AND date BETWEEN ? AND ?"
    return {date.fromisoformat(r[0]) for r in conn.execute(q, (source, box_id, start.isoformat(), end.isoformat()))}


def is_covered(conn, source, box_id, start, end):
    q = "SELECT 1 FROM coverage WHERE source=? AND box=? AND start<=? AND end>=? LIMIT 1"
    return conn.execute(q, (source, box_id, start.isoformat(), end.isoformat())).fetchone() is not None


def mark_covered(conn, source, box_id, start, end):
    with conn:
        conn.execute("INSERT OR REPLACE INTO coverage(source, box, start, end, fetched_at) VALUES (?,?,?,?,?)",
                     (source, box_id, start.isoformat(), end.isoformat(), _now()))


def put_cells(conn, source, box_id, cells):
    sig = hashlib.sha1(repr(tuple(cells)).encode()).hexdigest()[:16]
    with conn:
        conn.execute("INSERT OR REPLACE INTO cells(source, box, n, signature) VALUES (?,?,?,?)",
                     (source, box_id, len(cells), sig))


def put_cells_signature(conn, source, box_id, n, signature):
    """Record a pixel set by its stored (count, signature), as exported by dbw/pctl_export.py."""
    with conn:
        conn.execute("INSERT OR REPLACE INTO cells(source, box, n, signature) VALUES (?,?,?,?)",
                     (source, box_id, n, signature))


def load_series(conn, source, box_id, stat="median"):
    """[(date, value)] of one stat for (source, box), oldest first. Days with no such stat
    (NoData rows) are simply not returned."""
    q = "SELECT date, value FROM obs WHERE source=? AND box=? AND stat=? ORDER BY date"
    return [(date.fromisoformat(d), v) for d, v in conn.execute(q, (source, box_id, stat))]


def count(conn):
    return conn.execute("SELECT COUNT(*) FROM obs").fetchone()[0]


def put_pctl(conn, source, box_id, stat, pctls):
    """Replace the percentile table of (source, box, stat). `pctls` = {doy: Pctl | None}; a None
    slot keeps its row (n unknown = 0) so 'too few samples' stays visible."""
    built = _now()
    with conn:
        conn.execute("DELETE FROM pctl WHERE source=? AND box=? AND stat=?", (source, box_id, stat))
        conn.executemany(
            "INSERT INTO pctl(source, box, stat, doy, n, p50, p75, p90, p97, built_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(source, box_id, stat, doy, *((p.n, p.p50, p.p75, p.p90, p.p97) if p else (0, None, None, None, None)), built)
             for doy, p in pctls.items()])


def get_pctl(conn, source, box_id, stat):
    """{doy: (n, p50, p75, p90, p97) | None}; empty dict when never built."""
    q = "SELECT doy, n, p50, p75, p90, p97 FROM pctl WHERE source=? AND box=? AND stat=?"
    return {doy: (n, *ps) if ps[0] is not None else None for doy, n, *ps in conn.execute(q, (source, box_id, stat))}


def load_days(conn, source, box_id):
    """{date: {stat: value}} for (source, box). A NoData day has valid_count 0 and no median."""
    q = "SELECT date, stat, value FROM obs WHERE source=? AND box=? ORDER BY date"
    out = {}
    for d, stat, v in conn.execute(q, (source, box_id)):
        out.setdefault(date.fromisoformat(d), {})[stat] = v
    return out


def get_cells(conn, source):
    """{box: (n, signature)} of the pixel sets recorded by backfill / run for `source`."""
    return {box: (n, sig) for box, n, sig in conn.execute("SELECT box, n, signature FROM cells WHERE source=?", (source,))}
