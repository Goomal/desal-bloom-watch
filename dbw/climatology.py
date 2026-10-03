"""Seasonal percentiles per box: P50/P75/P90/P97 of a +-15-day circular window across all years."""
import math
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from dbw import store
from dbw.providers import noaa_erddap
from dbw.providers.base import FetchError, UpstreamUnreachable, http_get, percentile

HALF_WINDOW = 15
MIN_N = 30  # samples in a window; below this there is no percentile and the day scores grey
PCTL_STAT = "median"  # the per-day box statistic the percentiles are built on
FIRST_BACKFILL = date(2020, 5, 5)  # earliest slice of the longest chlorophyll history (DINEOF)
BACKFILL_SOURCES = ("noaacwNPPN20VIIRSDINEOFDaily", "noaacwN20VIIRSchlaDaily", "noaacrwsstDaily")
CHUNK_DAYS = 30  # ERDDAP's proxy cuts requests that run past ~10 s; a month answers in ~3 s
LAG_DAYS = 3  # a chunk ending within this many days of today is requested open-ended ("last")
MAX_CONSECUTIVE_FAILURES = 6
_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


@dataclass(frozen=True)
class Pctl:
    n: int
    p50: float
    p75: float
    p90: float
    p97: float


def doy365(d):
    """Day of year in a 365-day calendar: Feb 29 counts as Feb 28, so a date has the same slot every year."""
    day = min(d.day, 28) if d.month == 2 else d.day
    return _CUM[d.month - 1] + day


def seasonal_percentiles(series, min_n=MIN_N, half_window=HALF_WINDOW, exclude_year=None):
    """{doy 1..365: Pctl | None} from `series` = iterable of (date, value). None/NaN values are
    skipped. A slot with fewer than `min_n` samples in its window gets None (never a made-up number).
    `exclude_year` leaves one year out, so a hindcast of that year is not scored against itself."""
    buckets = [[] for _ in range(365)]
    for d, v in series:
        if v is None or math.isnan(v) or d.year == exclude_year:
            continue
        buckets[doy365(d) - 1].append(v)
    out = {}
    for doy in range(1, 366):
        vals = sorted(v for k in range(-half_window, half_window + 1)
                      for v in buckets[(doy - 1 + k) % 365])
        out[doy] = (Pctl(len(vals), *(percentile(vals, q) for q in (0.5, 0.75, 0.9, 0.97)))
                    if len(vals) >= max(min_n, 1) else None)
    return out


def build_percentiles(conn, source, box_id, stat=PCTL_STAT, min_n=MIN_N):
    """Recompute and store the seasonal percentiles of one (source, box) from obs."""
    pc = seasonal_percentiles(store.load_series(conn, source, box_id, stat), min_n=min_n)
    store.put_pctl(conn, source, box_id, stat, pc)
    return pc


def load_percentiles(conn, source, box_id, stat=PCTL_STAT):
    return {doy: (Pctl(*row) if row else None) for doy, row in store.get_pctl(conn, source, box_id, stat).items()}


@dataclass
class SourceReport:
    requests: int = 0
    days_written: int = 0  # (date, box) results stored
    skipped_chunks: int = 0
    failed: list = field(default_factory=list)
    seconds: float = 0.0


def chunk_ranges(start, end, days=CHUNK_DAYS):
    """[(a, b)] covering start..end inclusive; boundaries sit on fixed calendar multiples of `days`
    so two runs with different --from still share chunks (and so the coverage table keeps skipping)."""
    out, a = [], start
    while a <= end:
        b = min(end, date.fromordinal((a.toordinal() // days + 1) * days - 1))
        out.append((a, b))
        a = b + timedelta(days=1)
    return out


def _fetch(get, source, bbox, a, b, open_end, sleep, delay, rep, state):
    """RangeGrid for a..b. On a 5xx / network failure the range is halved and retried, down to one
    day; a range that still fails is added to rep.failed and contributes nothing."""
    grid = noaa_erddap.RangeGrid()
    if state["requests"]:
        sleep(delay)
    state["requests"] += 1
    rep.requests += 1
    try:
        text = get(noaa_erddap.build_range_url(source, bbox, a, None if open_end else b))
    except FetchError as e:
        if e.reachable:  # 4xx: ERDDAP's "no matching results" -- nothing in this window
            state["fails"] = 0
            return grid, False
        state["fails"] += 1
        if state["fails"] >= MAX_CONSECUTIVE_FAILURES:
            raise UpstreamUnreachable(f"{source}: {state['fails']} failed requests in a row ({e}); is ERDDAP down?",
                                      reason=str(e)) from e
        if a >= b:
            rep.failed.append(f"{a}: {e}")
            return grid, False
        mid = a + (b - a) // 2
        left, ok_l = _fetch(get, source, bbox, a, mid, False, sleep, delay, rep, state)
        right, ok_r = _fetch(get, source, bbox, mid + timedelta(days=1), b, open_end, sleep, delay, rep, state)
        for g in (left, right):
            for d, px in g.items():
                grid[d] = px
                grid.times[d] = g.times[d]
        return grid, ok_l and ok_r
    state["fails"] = 0
    return noaa_erddap.parse_range_csv(text), True


def backfill(conn, boxes, sources, start, end, force=False, get=http_get, sleep=time.sleep,
             delay=1.0, chunk_days=CHUNK_DAYS, today=None, log=print):
    """Fill obs for every (source, box) over start..end with ~monthly REGIONAL range requests (one
    per sea per source per chunk), cut into boxes locally. Resumable: a window already answered
    (coverage) is skipped and an existing (date, source, box) row is never overwritten, unless
    `force`. Days the dataset lacks get no row. Returns {source: SourceReport}."""
    today = today or date.today()
    reports = {}
    for source in sources:
        rep = reports[source] = SourceReport()
        t0 = time.monotonic()
        state = {"requests": 0, "fails": 0}
        first = noaa_erddap.FIRST_DATE[source]
        for sea in sorted({b.sea for b in boxes}, key=str):
            region = [b for b in boxes if b.sea == sea]
            for a, b in chunk_ranges(max(start, first), end, chunk_days):
                open_end = b >= today - timedelta(days=LAG_DAYS)
                need = [bx for bx in region if force or open_end or not store.is_covered(conn, source, bx.id, a, b)]
                if not need:
                    rep.skipped_chunks += 1
                    continue
                lats = [bx.bbox[0] for bx in need] + [bx.bbox[1] for bx in need]
                lons = [bx.bbox[2] for bx in need] + [bx.bbox[3] for bx in need]
                bbox = (min(lats), max(lats), min(lons), max(lons))
                grid, ok = _fetch(get, source, bbox, a, b, open_end, sleep, delay, rep, state)
                for bx in need:
                    g, g_ok = grid, ok
                    if bx.bbox != bbox and noaa_erddap.has_tie(grid, bx):
                        g, g_ok = _fetch(get, source, bx.bbox, a, b, open_end, sleep, delay, rep, state)
                    stats, cells = noaa_erddap.range_stats(g, bx)
                    have = set() if force else store.existing_dates(conn, source, bx.id, a, b)
                    new = {d: r for d, r in stats.items() if a <= d <= b and d not in have}
                    store.write_days(conn, source, bx.id, new)
                    rep.days_written += len(new)
                    if cells:
                        store.put_cells(conn, source, bx.id, cells)
                    if g_ok and not open_end:
                        store.mark_covered(conn, source, bx.id, a, b)
                log(f"{source} {sea} {a}..{b}: {len(grid)} days, {rep.requests} requests so far")
        rep.seconds = time.monotonic() - t0
    return reports
