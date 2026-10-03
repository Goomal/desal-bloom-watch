"""I/O glue between the store and the pure rules in score.py: assembles one box's series,
seasonal percentiles, upstream sentinels, SST and shared-pixel list for a day, then scores it.
Used by `dbw score` and `dbw hindcast`. No network."""
from dataclasses import replace
from datetime import timedelta

from dbw import climatology as clim
from dbw import store
from dbw.i18n import Msg
from dbw.score import MAX_AGE_DAYS, DayStat, Level, Score, Sentinel, Sst, score_box

DINEOF = "noaacwNPPN20VIIRSDINEOFDaily"
N20 = "noaacwN20VIIRSchlaDaily"
SST = "noaacrwsstDaily"
LOOKBACK = MAX_AGE_DAYS + 3  # days of history handed to score_box (3-day trend + staleness window)
MODES = ("n20_else_dineof", "dineof")


def _daystat(day, st):
    valid = int(st.get("valid_count") or 0)
    return DayStat(day, valid, int(st.get("total_count") or 0), st.get("median") if valid else None, st.get("p90"))


class Assessor:
    """`mode`: which chlorophyll source decides the level (docs/scoring.md).
    `leave_out`: score each day against percentiles built WITHOUT that day's year (honest hindcast);
    otherwise the stored `pctl` table is used, exactly what `dbw score` shows."""

    def __init__(self, conn, boxes, mode=MODES[0], leave_out=False):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.conn, self.mode, self.leave_out = conn, mode, leave_out
        self.boxes = {b.id: b for b in boxes}
        self._days, self._pc, self._cells = {}, {}, {}

    def days(self, source, box_id):
        key = (source, box_id)
        if key not in self._days:
            self._days[key] = {d: _daystat(d, st) for d, st in store.load_days(self.conn, source, box_id).items()}
        return self._days[key]

    def pctl(self, source, box_id, day):
        """Seasonal Pctl of the box's median for `day`'s slot, or None."""
        year = day.year if self.leave_out else None
        key = (source, box_id, year)
        if key not in self._pc:
            if self.leave_out:
                self._pc[key] = clim.seasonal_percentiles(store.load_series(self.conn, source, box_id), exclude_year=year)
            else:
                self._pc[key] = clim.load_percentiles(self.conn, source, box_id)
        return self._pc[key].get(clim.doy365(day))

    def window(self, source, box_id, day, back=LOOKBACK):
        d = self.days(source, box_id)
        return [d[x] for x in (day - timedelta(days=k) for k in range(back, -1, -1)) if x in d]

    def _latest(self, source, box_id, day):
        w = [s for s in self.window(source, box_id, day, MAX_AGE_DAYS) if s.median is not None]
        return w[-1] if w else None

    def _sentinels(self, plant, source, day):
        out = []
        for sid in plant.sentinels:
            s = self._latest(source, sid, day)
            p = self.pctl(source, sid, s.date) if s else None
            out.append(Sentinel(sid, s.median if s else None, p.p90 if p else None, s.date if s else None))
        return out

    def sentinel_status(self, plant_id, source, day):
        """The plant's upstream Sentinels as the scorer saw them for `source` on `day`."""
        return self._sentinels(self.boxes[plant_id], source, day)

    def sst_status(self, box_id, day):
        return self._sst(box_id, day)

    def _sst(self, box_id, day):
        s = self._latest(SST, box_id, day)
        if not s:
            return None
        p = self.pctl(SST, box_id, s.date)
        return Sst(s.median, p.p50 if p else None)

    def shared_with(self, source, box_id):
        """Other plants whose pixel set for `source` is identical to this box's."""
        if source not in self._cells:
            self._cells[source] = store.get_cells(self.conn, source)
        mine = self._cells[source].get(box_id)
        if not mine or not mine[0]:
            return []
        return sorted(b for b, c in self._cells[source].items()
                      if b != box_id and c == mine and b in self.boxes and self.boxes[b].kind == "plant")

    def _score(self, source, plant, day, prev_level):
        p = self.pctl(source, plant.id, day)
        sc = score_box(day, self.window(source, plant.id, day), p, self._sentinels(plant, source, day),
                       self._sst(plant.id, day), prev_level, self.shared_with(source, plant.id))
        return replace(sc, reasons=[Msg("source", label=_label(source))] + sc.reasons, source=source)

    def assess(self, plant_id, day, prev_level=None):
        plant = self.boxes[plant_id]
        if self.mode == "n20_else_dineof":
            sc = self._score(N20, plant, day, prev_level)
            if sc.level is not Level.GREY:
                return sc
            fb = self._score(DINEOF, plant, day, prev_level)
            return replace(fb, reasons=[Msg("fallback", reason=sc.reasons[1])] + fb.reasons) if fb.level is not Level.GREY else sc
        return self._score(DINEOF, plant, day, prev_level)

    def assess_range(self, plant_id, start, end):
        """{day: Score}, carrying each day's level into the next day's 'orange two days running'."""
        out, prev, d = {}, None, start
        while d <= end:
            out[d] = sc = self.assess(plant_id, d, prev)
            prev = sc.level if sc.level is not Level.GREY else None
            d += timedelta(days=1)
        return out


def _label(source):
    return {DINEOF: "DINEOF 9 km gap-filled", N20: "N20 VIIRS 4 km", SST: "CoralTemp SST"}.get(source, source)


LETTER = {Level.GREY: ".", Level.GREEN: "G", Level.YELLOW: "Y", Level.ORANGE: "O", Level.RED: "R"}
CORE_BEFORE = "2026-08-30"


def render_grid(grid):
    """{plant: {day: Score}} -> text grid, one row per plant, one column per day (G Y O R, . = grey)."""
    days = sorted(next(iter(grid.values())))
    w = max(len(p) for p in grid)
    lines = [" " * w + "  " + " ".join(f"{d.day:02d}" for d in days),
             " " * w + "  " + " ".join(f"{d.month:02d}" for d in days)]
    for plant, row in grid.items():
        lines.append(f"{plant:<{w}}  " + " ".join(f" {LETTER[row[d].level]}" for d in days))
    return "\n".join(lines)


def worst(row, before=None):
    """Highest level in a plant's row (optionally only days before `before`); GREY counts as lowest."""
    return max((s.level for d, s in row.items() if before is None or d < before), default=Level.GREY)


def _facts(grid, before):
    top = {p: worst(grid[p], before) for p in ("ashkelon", "ashdod", "sorek_a", "sorek_b") if p in grid}
    sorek = max(top.get("sorek_a", Level.GREY), top.get("sorek_b", Level.GREY))
    return {"ashkelon": top.get("ashkelon", Level.GREY), "ashdod": top.get("ashdod", Level.GREY), "sorek": sorek}


def hindcast_verdict(grid, before):
    """Acceptance clause as revised and approved on 2026-10-01: Ashkelon AND at least one of Ashdod /
    any Sorek box reach orange or red on some day before `before`, AND Hadera stays below orange on
    every day before `before`. -> (bool, [facts])."""
    need = _facts(grid, before)
    hadera = worst(grid["hadera"], before) if "hadera" in grid else Level.GREY
    facts = [f"{p}: worst before {before} = {lv.name}" for p, lv in need.items()]
    facts.append(f"hadera: worst before {before} = {hadera.name}")
    ok = (need["ashkelon"] >= Level.ORANGE and max(need["ashdod"], need["sorek"]) >= Level.ORANGE
          and hadera < Level.ORANGE)
    return ok, facts


def plan_clause_verdict(grid, before):
    """The original PLAN section 4 clause, kept so the report can show it still fails: Ashkelon, Ashdod
    and a Sorek box all orange+ before `before`, and Hadera's worst level over the WHOLE window lower
    than each of theirs. -> (bool, [facts])."""
    need = _facts(grid, before)
    hadera = worst(grid["hadera"]) if "hadera" in grid else Level.GREY
    facts = [f"{p}: worst before {before} = {lv.name}" for p, lv in need.items()]
    facts.append(f"hadera: worst over the window = {hadera.name}")
    ok = all(lv >= Level.ORANGE for lv in need.values()) and all(hadera < lv for lv in need.values())
    return ok, facts
