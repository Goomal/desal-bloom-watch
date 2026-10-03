"""NOAA CoastWatch ERDDAP griddap provider: chlorophyll (4 datasets) and CoralTemp SST."""
import csv
import io
import math
import urllib.parse
from dataclasses import dataclass
from datetime import date as Date

from dbw.providers.base import FetchError, NoData, http_get, summarize

BASE = "https://coastwatch.noaa.gov/erddap/griddap"
ATTRIBUTION = ("Data: NOAA CoastWatch (public domain, US government data). "
               "SST: NOAA Coral Reef Watch CoralTemp; licence text carries an OSTIA "
               "academic-research clause, so use is research use only.")


@dataclass(frozen=True)
class Source:
    var: str
    has_alt: bool  # VIIRS datasets have an altitude axis, CoralTemp does not
    short: str


SOURCES = {
    "noaacwN20VIIRSchlaDaily": Source("chlor_a", True, "chl_n20"),
    "noaacwNPPN20VIIRSDINEOFDaily": Source("chlor_a", True, "chl_dineof"),
    "noaacwNPPVIIRSchlaDaily": Source("chlor_a", True, "chl_npp"),
    "noaacwN20VIIRSchlanomratDaily": Source("chlor_a_pdif", True, "chl_anom"),
    "noaacrwsstDaily": Source("analysed_sst", False, "sst"),
}


# First time slice of each dataset (docs/sources.md). A range query that starts earlier is a 404.
FIRST_DATE = {
    "noaacwN20VIIRSchlaDaily": Date(2021, 8, 26),
    "noaacwNPPN20VIIRSDINEOFDaily": Date(2020, 5, 5),
    "noaacwNPPVIIRSchlaDaily": Date(2025, 9, 22),
    "noaacwN20VIIRSchlanomratDaily": Date(2018, 8, 6),
    "noaacrwsstDaily": Date(1985, 1, 1),
}


def build_url(source, box, day):
    """griddap CSV query for one day (noon UTC) over the box bbox. The square brackets are
    percent-encoded so no client or proxy treats them as a glob."""
    src = SOURCES[source]
    lat0, lat1, lon0, lon1 = box.bbox
    t = f"({day.isoformat()}T12:00:00Z)"
    alt = "[(0.0)]" if src.has_alt else ""
    query = f"{src.var}[{t}:1:{t}]{alt}[({lat0}):1:({lat1})][({lon0}):1:({lon1})]"
    return f"{BASE}/{source}.csv?" + urllib.parse.quote(query, safe="():,.-=")


def build_range_url(source, bbox, start, end=None):
    """griddap CSV query for a time range (noon UTC, inclusive) over bbox = (lat0, lat1, lon0, lon1).
    `end=None` means the dataset's latest slice. ERDDAP's proxy cuts requests that run longer
    than ~10 s, so callers keep the range to about a month."""
    src = SOURCES[source]
    lat0, lat1, lon0, lon1 = bbox
    t1 = "(last)" if end is None else f"({end.isoformat()}T12:00:00Z)"
    alt = "[(0.0)]" if src.has_alt else ""
    query = (f"{src.var}[({start.isoformat()}T12:00:00Z):1:{t1}]{alt}"
             f"[({lat0}):1:({lat1})][({lon0}):1:({lon1})]")
    return f"{BASE}/{source}.csv?" + urllib.parse.quote(query, safe="():,.-=")


def point_in_polygon(lat, lon, polygon):
    inside = False
    n = len(polygon)
    for i in range(n):
        (y1, x1), (y2, x2) = polygon[i], polygon[(i + 1) % n]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def parse_csv(text, polygon=None, day=None):
    """ERDDAP CSV (header row + units row + data) -> BoxStats | NoData.
    When `polygon` is given, only pixels whose centre is inside it count. When `day` is given,
    the returned slice must be that UTC day: ERDDAP snaps a missing time to the nearest slice,
    and a neighbouring day's pixels must never be stored under the requested date."""
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 3:
        return NoData("empty grid: no data rows")
    header = rows[0]
    li, lo, vi, ti = (header.index("latitude"), header.index("longitude"),
                      len(header) - 1, header.index("time"))
    values, data_time = [], None
    for r in rows[2:]:
        if len(r) != len(header):
            continue
        if day is not None and r[ti][:10] != day.isoformat():
            return NoData(f"no slice for {day}; nearest is {r[ti]}")
        if polygon is not None and not point_in_polygon(float(r[li]), float(r[lo]), polygon):
            continue
        data_time = r[ti]
        try:
            v = float(r[vi])
        except ValueError:
            v = math.nan
        values.append(v)
    if not values:
        return NoData("no pixel centre inside polygon" if polygon else "empty grid: no data rows")
    return summarize(values, len(values), data_time)


class RangeGrid(dict):
    """{UTC date: {(lat, lon): value}} from a multi-day response; `times` keeps each day's time string."""
    def __init__(self):
        super().__init__()
        self.times = {}


def parse_range_csv(text):
    """Multi-day ERDDAP CSV -> RangeGrid, pixels grouped by the UTC date of their time column.
    NaN (cloud) stays NaN. A day the dataset does not have is simply absent: there is no
    nearest-time snap on a range query, so no neighbouring day can land under another date."""
    rows = list(csv.reader(io.StringIO(text)))
    grid = RangeGrid()
    if len(rows) < 3:
        return grid
    header = rows[0]
    li, lo, vi, ti = (header.index("latitude"), header.index("longitude"),
                      len(header) - 1, header.index("time"))
    for r in rows[2:]:
        if len(r) != len(header):
            continue
        d = Date.fromisoformat(r[ti][:10])
        try:
            v = float(r[vi])
        except ValueError:
            v = math.nan
        grid.setdefault(d, {})[(float(r[li]), float(r[lo]))] = v
        grid.times[d] = r[ti]
    return grid


def _window(axis, lo, hi):
    """Axis values griddap returns for a request lo..hi: nearest grid point to each end, and all
    between. [] when the request lies wholly off this axis."""
    step = min((b - a for a, b in zip(axis, axis[1:])), default=0.05)
    if hi < axis[0] - step / 2 or lo > axis[-1] + step / 2:
        return []
    i0 = min(range(len(axis)), key=lambda i: abs(axis[i] - lo))
    i1 = min(range(len(axis)), key=lambda i: abs(axis[i] - hi))
    return axis[i0:i1 + 1]


def has_tie(grid, box):
    """True when a bbox edge of `box` lies midway between two pixel centres of the grid. ERDDAP breaks
    such a tie in a way that depends on its stored axis doubles (observed: the same box can take the
    inner pixel on one edge and the outer on another), so a box cut from a bigger grid may not match
    its own query; callers fetch it alone."""
    pixels = {px for day in grid.values() for px in day}
    lat0, lat1, lon0, lon1 = box.bbox
    for axis, edges in ((sorted({p[0] for p in pixels}), (lat0, lat1)), (sorted({p[1] for p in pixels}), (lon0, lon1))):
        for e in edges:
            near = sorted(abs(a - e) for a in axis)[:2]
            if len(near) == 2 and abs(near[0] - near[1]) < 1e-6 and axis[0] <= e <= axis[-1]:
                return True
    return False


def range_stats(grid, box):
    """({date: BoxStats | NoData}, cells) for one box cut out of a (regional) RangeGrid. The
    pixel set is the one griddap returns for the box's own query (nearest-grid-index rule at the
    bbox edges), plus the polygon-centre mask for non-rectangular boxes, so backfill agrees with
    the daily per-box `dbw run`. `cells` is the sorted tuple of (lat, lon) used."""
    pixels = {px for day in grid.values() for px in day}
    if not pixels:
        return {}, ()
    lat0, lat1, lon0, lon1 = box.bbox
    lats = _window(sorted({p[0] for p in pixels}), lat0, lat1)
    lons = _window(sorted({p[1] for p in pixels}), lon0, lon1)
    cells = tuple(sorted(p for p in pixels if p[0] in lats and p[1] in lons
                         and (box.is_rectangle or point_in_polygon(p[0], p[1], box.polygon))))
    if not cells:
        return {}, ()
    out = {d: summarize([day.get(c, math.nan) for c in cells], len(cells), grid.times[d])
           for d, day in grid.items()}
    return out, cells


class ErddapProvider:
    def __init__(self, source, http_get=http_get):
        if source not in SOURCES:
            raise KeyError(source)
        self.source = source
        self.short = SOURCES[source].short
        self._get = http_get

    def fetch(self, box, day: Date):
        try:
            text = self._get(build_url(self.source, box, day))
        except FetchError as e:
            return NoData(str(e), reachable=e.reachable)
        return parse_csv(text, None if box.is_rectangle else box.polygon, day)
