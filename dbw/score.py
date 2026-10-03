"""Deterministic bloom-risk level for one intake box on one day. Pure functions: no I/O, no clock,
no network, no LLM. Thresholds are the module constants below; docs/scoring.md justifies each.
A reason line is a `Msg` (code + values): it reads as the English line and renders in any report language."""
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import IntEnum

from dbw.climatology import Pctl
from dbw.i18n import Id, Msg

MIN_VALID_FRAC = 0.25  # share of the box's pixels that must be clear, else grey
MAX_AGE_DAYS = 3  # newest valid observation older than this -> grey (the feed lags ~2 days)
RISE_RATIO = 1.15  # latest / earliest valid value across the last 3 days to call it "rising"
RED_MULT = 3.0  # red when the value is this many times the seasonal median (and >= RED_EDGE)
RED_EDGE = "p90"
CONFIRM = True  # judge the lower of the newest two valid days (<= 3 days apart), so one spike cannot move the level
SENTINEL_MULT = 1.5  # a sentinel is 'high' at this multiple of its own seasonal P90
SST_WARM_C = 26.0  # warm-water picocyanobacteria (Uysal 2006)
SST_ANOMALY_C = 1.0  # ... and this far above the seasonal normal


class Level(IntEnum):
    GREY = -1  # no usable data. Never reported as green.
    GREEN = 0
    YELLOW = 1
    ORANGE = 2
    RED = 3


@dataclass(frozen=True)
class DayStat:
    """One day's statistics of the scored source over the box."""
    date: date
    valid: int
    total: int
    median: float | None  # None: nothing valid that day
    p90: float | None = None  # the day's own 90th percentile over the box's pixels


@dataclass(frozen=True)
class Sentinel:
    """An upstream early-warning box: its newest value and its own seasonal P90 (None = no data)."""
    id: str
    value: float | None
    p90: float | None
    data_date: date | None = None

    @property
    def high(self):
        return self.value is not None and self.p90 is not None and self.value >= self.p90


@dataclass(frozen=True)
class Sst:
    value: float | None  # box mean SST, deg C
    normal: float | None  # seasonal normal (P50 of the same window over the SST history)


@dataclass(frozen=True)
class Score:
    level: Level
    reasons: list = field(default_factory=list)
    as_of: date | None = None  # date of the observation the level rests on
    value: float | None = None
    rank: str | None = None  # where the value sits against the seasonal percentiles
    extent: str | None = None  # widespread | patchy | local
    source: str | None = None  # dataset the level rests on (set by the caller that chose it)


def rank_label(value, p):
    """'<P50' ... '>=P97': the highest seasonal percentile the value reaches."""
    for name, edge in (("P97", p.p97), ("P90", p.p90), ("P75", p.p75), ("P50", p.p50)):
        if value >= edge:
            return Msg("rank.ge", p=name)  # reads ">=P90" in English, worded in the report language elsewhere
    return Msg("rank.lt")


def extent_label(day, p):
    """How much of the box is above the box's seasonal P90, from the stored per-day stats:
    median >= P90 means at least half the pixels are; the day's own P90 >= P90 means at least a tenth."""
    if day.median is not None and day.median >= p.p90:
        return "widespread"
    if day.p90 is not None and day.p90 >= p.p90:
        return "patchy"
    return "local"


def _rising(valid_days, p):
    """Rising over 3 days above P75: >= 2 valid days in the 3-day window ending on the newest one,
    all >= P75, and the newest at least RISE_RATIO x the oldest."""
    end = valid_days[-1].date
    window = [d for d in valid_days if end - timedelta(days=2) <= d.date <= end]
    if len(window) < 2 or any(d.median < p.p75 for d in window):
        return False
    return window[-1].median >= RISE_RATIO * window[0].median


def score_box(day, series, pctl, sentinels=(), sst=None, prev_level=None, shared_with=()):
    """Level + reasons for one box as of `day`.

    series       DayStat list of the scored source (any order; days after `day` are ignored)
    pctl         the box's seasonal Pctl for this day of year, or None when history is too thin
    sentinels    Sentinel list for this plant's upstream boxes
    sst          Sst for the box, optional
    prev_level   the level reported for the previous day (for "orange two days running"), optional
    shared_with  ids of other boxes that use exactly the same pixels (not independent evidence)
    """
    notes = []
    if shared_with:
        notes.append(Msg("shared", ids=[Id(i) for i in shared_with]))
    valid = sorted((d for d in series if d.date <= day and d.median is not None and d.valid > 0),
                   key=lambda d: d.date)
    if not valid:
        return Score(Level.GREY, [Msg("no_data")] + notes)
    latest = valid[-1]
    age = (day - latest.date).days
    if age > MAX_AGE_DAYS:
        return Score(Level.GREY, [Msg("stale", age=age, date=latest.date, limit=MAX_AGE_DAYS)] + notes,
                     as_of=latest.date)
    frac = latest.valid / latest.total if latest.total else 0.0
    if frac < MIN_VALID_FRAC:
        return Score(Level.GREY, [Msg("low_coverage", pixels=f"{latest.valid}/{latest.total}", date=latest.date,
                                      pct=f"{frac:.0%}", need=f"{MIN_VALID_FRAC:.0%}")] + notes,
                     as_of=latest.date)
    if pctl is None:
        return Score(Level.GREY, [Msg("no_history")] + notes,
                     as_of=latest.date)

    v = latest.median
    prev = [d for d in valid[:-1] if (latest.date - d.date).days <= 3]
    held = None
    if CONFIRM and prev and prev[-1].median < v:
        held, v = v, prev[-1].median
    rank = rank_label(v, pctl)
    reasons = [Msg("chl", chl=f"{v:.3g} mg/m3", rank=rank,
                   pcts=f"P50 {pctl.p50:.3g}, P75 {pctl.p75:.3g}, P90 {pctl.p90:.3g}, P97 {pctl.p97:.3g}; n={pctl.n}")]
    if held is not None:
        reasons.append(Msg("unconfirmed", held=f"{held:.3g}", v=f"{v:.3g}", gap=(latest.date - prev[-1].date).days))
    level = Level.GREEN
    if v >= pctl.p90:
        level = Level.YELLOW
    rising = _rising(valid, pctl)
    if rising:
        level = max(level, Level.YELLOW)
        reasons.append(Msg("rising"))
    if v >= pctl.p97:
        level = max(level, Level.ORANGE)
    high = [s for s in sentinels if s.high and s.value >= SENTINEL_MULT * s.p90]
    if level >= Level.YELLOW and high:
        level = max(level, Level.ORANGE)
        reasons.append(Msg("upgraded"))
    if v >= RED_MULT * pctl.p50 and v >= getattr(pctl, RED_EDGE):
        level = Level.RED
        reasons.append(Msg("red_mult", ratio=Msg("times", n=f"{v / pctl.p50:.1f}"), mult=Msg("times", n=f"{RED_MULT:g}")))
    elif level >= Level.ORANGE and prev_level is not None and prev_level >= Level.ORANGE:
        level = Level.RED
        reasons.append(Msg("two_days"))

    extent = extent_label(latest, pctl)
    if level >= Level.YELLOW:
        reasons.append(Msg(f"extent.{extent}"))
    for s in sentinels:
        if s.value is None or s.p90 is None:
            reasons.append(Msg("sentinel.none", id=Id(s.id)))
        elif s.high:
            reasons.append(Msg("sentinel.high", id=Id(s.id), value=f"{s.value:.3g}", p90=f"{s.p90:.3g}"))
        else:
            reasons.append(Msg("sentinel.low", id=Id(s.id), value=f"{s.value:.3g}", p90=f"{s.p90:.3g}"))
    if sst and sst.value is not None:
        anom = None if sst.normal is None else sst.value - sst.normal
        if sst.value >= SST_WARM_C and anom is not None and anom >= SST_ANOMALY_C:
            reasons.append(Msg("sst.warm", sst=f"{sst.value:.1f} C", anom=f"{anom:+.1f} C"))
        elif anom is None:
            reasons.append(Msg("sst.only", sst=f"{sst.value:.1f} C"))
        else:
            reasons.append(Msg("sst.anom", sst=f"{sst.value:.1f} C", anom=f"{anom:+.1f} C"))
    pixels = f"{latest.valid}/{latest.total}"
    reasons.append(Msg("data.aged", pixels=pixels, date=latest.date, age=age) if age
                   else Msg("data", pixels=pixels, date=latest.date))
    return Score(level, reasons + notes, as_of=latest.date, value=v, rank=rank, extent=extent)
