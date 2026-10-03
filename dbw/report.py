"""The daily report: one in-memory model built from the store and the scorer, rendered as markdown,
email-safe HTML, a PNG map and a two-sentences-per-plant short message, in English, Hebrew or Arabic
(dbw/i18n.py; the PNG map stays English). Plain Python, no LLM, no network on the default path (the optional
NASA GIBS underlay is the one exception and falls back to the plain map when it fails)."""
import base64
import html
import json
import re
import textwrap
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path

from dbw import assess, i18n, registry
from dbw.climatology import Pctl
from dbw.i18n import Id, Msg
from dbw.providers import gibs, noaa_erddap
from dbw.score import MAX_AGE_DAYS, MIN_VALID_FRAC, RED_MULT, SENTINEL_MULT, Level

COASTLINE = Path(__file__).resolve().parent / "data" / "coastline.json"
FORMATS = ("html", "md", "png", "txt")
DISCLAIMER = ("Desal Bloom Watch is a satellite-based early-warning aid. It is not an operational decision "
              "tool and not a measurement at the intake: satellites see the top few metres, data lag about "
              "two days, and your own on-line analysers remain the real-time alarm.")
MAP_CREDIT = "Coastline: Natural Earth (public domain), naturalearthdata.com."
UNIT = "mg/m³"
COLOR = {Level.GREEN: "#2e9e5b", Level.YELLOW: "#e8b923", Level.ORANGE: "#ee7d17", Level.RED: "#d7263d",
         Level.GREY: "#8d99a6"}
EMOJI = {Level.GREEN: "\U0001F7E2", Level.YELLOW: "\U0001F7E1", Level.ORANGE: "\U0001F7E0", Level.RED: "\U0001F534",
         Level.GREY: "⚪"}
SEAS = ("mediterranean", "red_sea")
SEA_TITLE = {"mediterranean": "Eastern Mediterranean", "red_sea": "Gulf of Aqaba (Eilat)"}
SOURCE_ORDER = (assess.N20, assess.DINEOF, assess.SST)
GOOD_MAX_AGE = 2  # "How sure" is Good only when the clear view is at most this many days old ...
GOOD_MIN_SHARE = 0.5  # ... covers MORE than this share of the box, and comes from the sharp satellite
ERDDAP = "coastwatch.noaa.gov/erddap/griddap/"
SOURCE_URLS = {"app.src.n20": f"{ERDDAP}{assess.N20}.html", "app.src.dineof": f"{ERDDAP}{assess.DINEOF}.html",
               "app.src.sst": f"{ERDDAP}{assess.SST}.html", "app.src.coast": "naturalearthdata.com"}
GLOSSARY = ("chl", "unit", "normal", "sats", "sure", "upstream", "shared", "delay", "sst")
LEVELS_BY_SEVERITY = (Level.GREEN, Level.YELLOW, Level.ORANGE, Level.RED, Level.GREY)
ATTRIBUTION_KEYS = {noaa_erddap.ATTRIBUTION: "attr.noaa", MAP_CREDIT: "attr.coast", gibs.ATTRIBUTION: "attr.gibs"}


@dataclass(frozen=True)
class SentinelReport:
    id: str
    name: str
    sea: str
    polygon: tuple
    level: Level  # GREY no data / GREEN below its P90 / YELLOW >= P90 / ORANGE >= SENTINEL_MULT x P90
    value: float | None
    p90: float | None
    data_date: object


@dataclass(frozen=True)
class PlantReport:
    id: str
    name: str
    sea: str
    polygon: tuple
    level: Level
    label: Msg  # "ORANGE", or "ORANGE (upstream signal: tiran >= 1.5x P90; eilat itself is yellow)"
    own_level: Level  # the level this plant's own pixels give, without its sentinels
    prev_level: Level  # yesterday's level
    reasons: tuple  # score.py's reason lines, minus the source line and the shared-pixel flag
    value: float | None
    rank: str | None
    pctl: Pctl | None
    source: str | None
    source_label: str
    data_date: object
    age_days: int | None
    valid: int | None
    total: int | None
    confidence: Msg
    grey_why: str | None
    shared_with: list
    sentinels: tuple  # score.Sentinel list as the scorer saw them
    sst: object  # score.Sst | None
    extent: str | None
    lifted_by: tuple = ()  # ids of the sentinels that lifted the level above the plant's own
    prev_source: str | None = None  # the dataset yesterday's level rested on (None: no level yesterday)


@dataclass(frozen=True)
class SourceDate:
    id: str
    label: str
    latest: object  # newest valid date <= report date over the chosen boxes, or None
    age_days: int | None


@dataclass(frozen=True)
class Report:
    date: object
    plants: tuple  # PlantReport, worst first
    sentinels: tuple  # SentinelReport, the upstream boxes of the chosen plants
    sources: tuple  # SourceDate
    worst: Level
    changes: tuple  # (plant id, yesterday Level, today Level) where the level moved
    mode: str
    attributions: tuple = (noaa_erddap.ATTRIBUTION, MAP_CREDIT)
    notes: tuple = ()  # basemap fallback reasons
    upstream: str | None = None  # why NOAA could not be fetched on this run (the values are from the database)
    names: dict = field(default_factory=dict)  # box id -> English name, for every box in the registry


def sentinel_level(s):
    if s.value is None or s.p90 is None:
        return Level.GREY
    if s.value >= SENTINEL_MULT * s.p90:
        return Level.ORANGE
    return Level.YELLOW if s.value >= s.p90 else Level.GREEN


def _label(level, own, lifted, pid):
    if not lifted:
        return Msg(f"level.{level.name}")
    return Msg("label.upstream", level=Msg(f"level.{level.name}"), by=[_sentinel_by(s.id) for s in lifted],
               id=Id(pid), own=Msg(f"levelword.{own.name}"))


def _sentinel_by(sid):
    return Msg("sentinel.by", id=Id(sid), mult=f"{SENTINEL_MULT:g}")


def _plant(a, a0, box, day):
    pid = box.id
    prev = a.assess(pid, day - timedelta(days=1))
    sc = a.assess(pid, day, prev_level=prev.level)
    own = a0.assess(pid, day, prev_level=prev.level)
    sents = tuple(a.sentinel_status(pid, sc.source, day))
    lifted = ([s for s in sents if s.high and s.value >= SENTINEL_MULT * s.p90]
              if sc.level is not Level.GREY and own.level < sc.level else [])
    pc = a.pctl(sc.source, pid, day) if sc.as_of else None  # the slot the scorer ranked against
    st = a.days(sc.source, pid).get(sc.as_of) if sc.as_of else None
    age = (day - sc.as_of).days if sc.as_of else None
    shared = a.shared_with(sc.source, pid)
    body = [r for r in sc.reasons if r.code not in ("source", "shared")]
    grey_why = body[0] if sc.level is Level.GREY and body else None
    if st and st.total:
        seen = dict(pixels=f"{st.valid}/{st.total}", pct=f"{st.valid / st.total:.0%}", date=sc.as_of)
        conf = Msg("conf.aged" if age and age != 1 else "conf.aged_one", age=age, **seen) if age else Msg("conf.fresh", **seen)
    else:
        conf = Msg("conf.none")
    if grey_why:
        conf = Msg("conf.grey", level=Msg("level.GREY"), why=grey_why)
    return PlantReport(
        id=pid, name=box.name or pid, sea=box.sea, polygon=box.polygon, level=sc.level,
        label=_label(sc.level, own.level, lifted, pid), own_level=own.level, prev_level=prev.level,
        reasons=tuple(body), value=sc.value, rank=sc.rank, pctl=pc, source=sc.source,
        source_label=assess._label(sc.source), data_date=sc.as_of, age_days=age,
        valid=st.valid if st else None, total=st.total if st else None, confidence=conf,
        grey_why=grey_why, shared_with=shared, sentinels=sents, sst=a.sst_status(pid, day), extent=sc.extent,
        lifted_by=tuple(s.id for s in lifted), prev_source=prev.source)


def build_report(conn, boxes, plant_ids, day, mode=assess.MODES[0], upstream=None):
    """Report model for `plant_ids` (registry plant ids) as of `day`, from the store (no network).
    `upstream` is the reason NOAA could not be fetched on this run, shown in every format."""
    by_id = {b.id: b for b in boxes}
    unknown = [p for p in plant_ids if p not in by_id or by_id[p].kind != "plant"]
    if unknown:
        raise ValueError(f"unknown plant id(s): {', '.join(unknown)}")
    a = assess.Assessor(conn, boxes, mode=mode)
    a0 = assess.Assessor(conn, [replace(b, sentinels=()) if b.kind == "plant" else b for b in boxes], mode=mode)
    plants = sorted((_plant(a, a0, by_id[p], day) for p in plant_ids), key=lambda p: -p.level)
    sent_ids = list(dict.fromkeys(s for p in plants for s in by_id[p.id].sentinels))
    sents = []
    for sid in sent_ids:
        seen = next((s for p in plants for s in p.sentinels if s.id == sid), None)
        b = by_id[sid]
        sents.append(SentinelReport(sid, b.name or sid, b.sea, b.polygon, sentinel_level(seen) if seen else Level.GREY,
                                    seen.value if seen else None, seen.p90 if seen else None,
                                    seen.data_date if seen else None))
    chosen = [p.id for p in plants] + sent_ids
    wanted = (assess.N20, assess.DINEOF, assess.SST) if mode == assess.MODES[0] else (assess.DINEOF, assess.SST)
    sources = []
    for src in (s for s in SOURCE_ORDER if s in wanted):
        newest = [d for bid in chosen for d, st in a.days(src, bid).items() if d <= day and st.median is not None]
        latest = max(newest, default=None)
        sources.append(SourceDate(src, assess._label(src), latest, (day - latest).days if latest else None))
    changes = tuple((p.id, p.prev_level, p.level) for p in plants if p.prev_level != p.level)
    return Report(day, tuple(plants), tuple(sents), tuple(sources), max((p.level for p in plants), default=Level.GREY),
                  changes, mode, upstream=upstream, names={b.id: b.name or b.id for b in boxes})


# --- text pieces shared by markdown, HTML and the short message -----------------------------------

def _t(lang):
    """`t(code, **params)` -> that message worded in `lang`. Raises ValueError for an unknown language."""
    i18n.load(lang)
    def t(code, **params):
        return Msg(code, **params).render(lang)
    t.lang = lang
    return t


def _g(x):
    return f"{x:.3g}"


def _name(p, lang):
    return i18n.display_name(lang, p.id, p.name)


def _lv(level):
    return Msg(f"level.{level.name}")


def _attr(a, t):
    return t(ATTRIBUTION_KEYS[a]) if a in ATTRIBUTION_KEYS else a


def _pctl_line(p, t):
    if p.value is None:
        return None
    chl = f"{_g(p.value)} {UNIT}"
    if p.pctl is None:
        return chl
    pcts = (f"P50 {_g(p.pctl.p50)} · P75 {_g(p.pctl.p75)} · P90 {_g(p.pctl.p90)} · P97 {_g(p.pctl.p97)}, "
            f"n={p.pctl.n}")
    return t("pctl.line", chl=chl, rank=p.rank, pcts=pcts)


def _source_line(p, t):
    if p.source is None or p.data_date is None:
        return None
    return t("source.line", label=p.source_label, date=p.data_date)


def _sentinel_lines(p, t):
    out = []
    for s in p.sentinels:
        if s.value is None or s.p90 is None:
            out.append(t("sl.none", id=Id(s.id)))
        else:
            state = "sl.high" if s.value >= SENTINEL_MULT * s.p90 else "sl.above" if s.high else "sl.below"
            out.append(t("sl.line", id=Id(s.id), value=f"{_g(s.value)} {UNIT}", p90=_g(s.p90), state=Msg(state)))
    return out


def _sst_line(p, t):
    if not p.sst or p.sst.value is None:
        return None
    sst = f"{p.sst.value:.1f} °C"
    if p.sst.normal is None:
        return t("sstline.only", sst=sst)
    return t("sstline.anom", sst=sst, anom=f"{p.sst.value - p.sst.normal:+.1f} °C")


def _shared_line(p, t):
    return t("shared.line", ids=[Id(i) for i in p.shared_with]) if p.shared_with else None


def _data_dates(rep, t):
    return [t("datedate.none", label=s.label) if not s.latest else
            t("datedate.one" if s.age_days == 1 else "datedate.some", label=s.label, latest=s.latest, age=s.age_days)
            for s in rep.sources]


def _changes(rep, t):
    if not rep.changes:
        return t("changes.none")
    return t("changes.some", items=[Msg("change.item", id=Id(i), before=_lv(a), after=_lv(b)) for i, a, b in rep.changes])


def _upstream_note(rep, t):
    """The 'NOAA could not be fetched today' line, or None on a normal run."""
    if not rep.upstream:
        return None
    latest = max((s.latest for s in rep.sources if s.latest), default=None)
    return t("note.upstream", reason=rep.upstream, date=latest) if latest else t("note.upstream.nodate", reason=rep.upstream)


def _note(n, lang):
    return n.render(lang) if isinstance(n, Msg) else n


def _chl_cell(p, t):
    return t("cell.chl", chl=f"{_g(p.value)} {UNIT}", rank=p.rank) if p.value is not None else "—"


def _facts(p, t):
    """[(key, text)] of one plant's detail block, in display order; empty texts are dropped by the renderers."""
    return [(t("key.chl"), _pctl_line(p, t)), (t("key.source"), _source_line(p, t)),
            (t("key.confidence"), p.confidence.render(t.lang)), (t("key.sst"), _sst_line(p, t)),
            (t("key.sentinels"), "; ".join(_sentinel_lines(p, t)) if p.sentinels else None),
            (t("key.shared"), _shared_line(p, t))]


# --- the plain layer: summary, cards, appendix (no jargon above the technical details) ------------

def _short(name):
    """'Ashdod (Mekorot)' -> 'Ashdod': the name without its trailing bracket, for one-line sentences."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name)


def _pname(p, lang):
    return _short(_name(p, lang))


def _bname(rep, lang, bid):
    return _short(i18n.display_name(lang, bid, rep.names.get(bid, bid)))


def _join(names, t):
    names = list(names)
    return names[0] if len(names) < 2 else i18n.load(t.lang)["strings"]["sep"].join(names[:-1]) + t("join.and") + names[-1]


def _kind(source):
    return Msg("kind.sharp" if source == assess.N20 else "kind.smooth")


def source_switched(p, before):
    """True when the level moved from `before` to the plant's level AND the satellite the level rests on changed
    (sharp 4 km <-> smoothed 9 km), so the two days are not directly comparable. A grey on either side is no
    comparison at all."""
    return bool(p.prev_source and p.source and p.prev_source != p.source and before != p.level
                and Level.GREY not in (before, p.level))


def _when(age):
    return Msg("when.today" if age == 0 else "when.one" if age == 1 else "when.two" if age == 2 else "when.n", n=str(age))


def how_sure(p):
    """('good' | 'limited' | 'low', Msg): how far to trust the level. Low: no level could be given. Good: a clear view
    of MORE than GOOD_MIN_SHARE of the area, at most GOOD_MAX_AGE days old, from the sharp satellite. Limited: the rest."""
    if p.level is Level.GREY:
        word = Msg("sure.word.low")
        if p.data_date is None or p.age_days is None:
            return "low", Msg("sure.low.none", word=word)
        if p.age_days > MAX_AGE_DAYS:
            return "low", Msg("sure.low.stale", word=word, age=str(p.age_days))
        if p.total and p.valid / p.total < MIN_VALID_FRAC:
            return "low", Msg("sure.low.cover", word=word, pct=f"{p.valid / p.total:.0%}")
        return "low", Msg("sure.low.history", word=word)
    word = Msg("sure.word.limited")
    if p.source != assess.N20:
        return "limited", Msg("sure.limited.smooth", word=word, when=_when(p.age_days))
    share = p.valid / p.total if p.total else 0.0
    if share <= GOOD_MIN_SHARE:
        return "limited", (Msg("sure.limited.cover_half", word=word) if share == GOOD_MIN_SHARE else
                           Msg("sure.limited.cover", word=word, pct=f"{share:.0%}"))
    if p.age_days > GOOD_MAX_AGE:
        return "limited", Msg("sure.limited.old", word=word, age=str(p.age_days))
    return "good", Msg("sure.good", word=Msg("sure.word.good"), when=_when(p.age_days), kind=Msg("sure.sharp"))


def band(p):
    """(band name, Msg of the one threshold it rests on) for the plant's value against its seasonal percentiles, or
    None when there is nothing to compare. Same marks as the scorer (P50/P75/P90/P97 and RED_MULT x P50)."""
    if p.value is None or p.pctl is None:
        return None
    v, c = p.value, p.pctl
    if v >= RED_MULT * c.p50 and v >= c.p90:
        return "far", Msg("band.t.far", ratio=Msg("plain.times", n=f"{v / c.p50:.1f}"), v=_g(c.p50))
    for name, edge in (("very_high", c.p97), ("high", c.p90), ("above", c.p75)):
        if v >= edge:
            return name, Msg(f"band.t.{name}", v=_g(edge))
    return "normal", Msg("band.t.normal", v=_g(c.p75))


def _what(rep, p, lang):
    """The one sentence that says why this plant has its level, in plain words."""
    if p.level is Level.GREY:
        why = p.grey_why
        code = why.code if why is not None and why.code in ("stale", "low_coverage", "no_history") else "no_data"
        return Msg(f"plain.cause.{code}", **(why.params if code != "no_data" else {}))
    if p.lifted_by:
        return Msg("plain.cause.upstream", names=[_bname(rep, lang, i) for i in p.lifted_by],
                   own=Msg(f"levelword.{p.own_level.name}"))
    codes = {r.code: r for r in p.reasons}
    if "red_mult" in codes:
        return Msg("plain.cause.red_mult", ratio=Msg("plain.times", n=codes["red_mult"].params["ratio"].params["n"]))
    if "two_days" in codes:
        return Msg("plain.cause.two_days", orange=Msg("levelword.ORANGE"))
    for code, wanted in (("p97", ">=P97"), ("rising", None), ("p90", ">=P90"), ("p75", ">=P75")):
        if (wanted is None and "rising" in codes) or (wanted is not None and p.rank == wanted):
            return Msg(f"plain.cause.{code}")
    return Msg("plain.cause.normal")


def _upstream_row(rep, p, lang, t):
    n = len(p.sentinels)
    if not n:
        return None
    seen = [s for s in p.sentinels if s.value is not None and s.p90 is not None]
    high = [s for s in seen if s.high]
    if not seen:
        return t("up.nodata", n=str(n))
    line = (t("up.line", k=str(len(high)), n=str(len(seen)), names=[_bname(rep, lang, s.id) for s in high]) if high
            else t("up.none", n=str(len(seen))))
    return t("up.missing", line=line, m=str(n - len(seen))) if len(seen) < n else line


def _card(rep, p, lang, t):
    """[(label, text)] of one plant's plain card, in display order."""
    rows = [(t("plain.what"), _what(rep, p, lang).render(lang))]
    b = band(p)
    if b:
        rows.append((t("plain.vs"), t("plain.vs.line", band=Msg(f"band.{b[0]}"), value=f"{_g(p.value)} {UNIT}", why=b[1])))
    rows.append((t("plain.sure"), how_sure(p)[1].render(lang)))
    up = _upstream_row(rep, p, lang, t)
    if up:
        rows.append((t("plain.up"), up))
    if p.shared_with:
        names = [_pname(p, lang)] + [_bname(rep, lang, i) for i in p.shared_with]
        rows.append((t("plain.shared"), t("plain.shared.line", names=_join(names, t))))
    return rows


def _plain_changes(rep, lang, t):
    if not rep.changes:
        return t("changes.none")
    by_id = {p.id: p for p in rep.plants}
    items = []
    for pid, before, after in rep.changes:
        p = by_id[pid]
        item = Msg("change.item", id=_pname(p, lang), before=_lv(before), after=_lv(after))
        items.append(Msg("change.switch", item=item, before=_kind(p.prev_source), after=_kind(p.source))
                     if source_switched(p, before) else item)
    return t("changes.some", items=items)


def _short_changes(rep, lang, t):
    """The one-line change note of the short message, or None when no plant changed level since yesterday."""
    if not rep.changes:
        return None
    by_id = {p.id: p for p in rep.plants}
    items = []
    for pid, before, after in rep.changes:
        item = Msg("change.item", id=_pname(by_id[pid], lang), before=_lv(before), after=_lv(after))
        items.append(Msg("short.change.switch", item=item) if source_switched(by_id[pid], before) else item)
    return t("short.change", items=items)


def _summary(rep, lang, t):
    """The plain paragraphs under the title: who could not be judged, how fresh the satellite data is, what changed
    since yesterday."""
    if not rep.plants:
        return [t("sum.none")]
    out = []
    grey = [p for p in rep.plants if p.level is Level.GREY]
    if grey:
        out.append(t("sum.grey", names=_join([_pname(p, lang) for p in grey], t)))
    dates = sorted({p.data_date for p in rep.plants if p.data_date is not None})
    if not dates:
        out.append(t("sum.fresh.none"))
    elif len(dates) == 1:
        out.append(t("sum.fresh", date=i18n.short_date(lang, dates[0], rep.date), when=_when((rep.date - dates[0]).days)))
    else:
        out.append(t("sum.fresh.range", old=i18n.short_date(lang, dates[0], rep.date),
                     new=i18n.short_date(lang, dates[-1], rep.date), lo=str((rep.date - dates[-1]).days),
                     hi=str((rep.date - dates[0]).days)))
    out.append(_plain_changes(rep, lang, t))
    return out


def _appendix(lang, t):
    """The 'How to read this report' appendix as [(kind, payload)] shared by markdown and HTML:
    h = heading, p = paragraph, key = [(level, name, means, when)], dl = [(term, text)], ul = [text]."""
    L = [("h", t("app.title")), ("p", t("app.intro")), ("h3", t("app.key.title")), ("p", t("app.key.lead")),
         ("key", [(lv, t(f"level.{lv.name}"), t(f"app.key.{lv.name}.means"), t(f"app.key.{lv.name}.when"))
                  for lv in LEVELS_BY_SEVERITY]),
         ("h3", t("app.gl.title")), ("dl", [(t(f"app.gl.{k}.t"), t(f"app.gl.{k}.d")) for k in GLOSSARY]),
         ("h3", t("app.lim.title")), ("ul", [t(f"app.lim.{i}") for i in range(1, 8)]),
         ("h3", t("app.src.title")),
         ("ul", [t("sources.line", what=Msg(k), url=u) for k, u in SOURCE_URLS.items()] + [t("app.src.rules")])]
    return L


# --- markdown -----------------------------------------------------------------------------------

def _technical_md(rep, lang, t):
    L = [f"## {t('tech.title')}", "", _changes(rep, t), ""]
    L += [f"| {t('th.plant')} | {t('th.level')} | {t('th.chl')} | {t('th.data')} |", "|---|---|---|---|"]
    for p in rep.plants:
        L.append(f"| {_name(p, lang)} | {EMOJI[p.level]} {p.label.render(lang)} | {_chl_cell(p, t)} | "
                 f"{_source_line(p, t) or t('cell.nodata')} |")
    L += ["", f"**{t('datedates')}**", ""] + [f"- {d}" for d in _data_dates(rep, t)] + [""]
    for p in rep.plants:
        L += [f"### {_name(p, lang)} — {EMOJI[p.level]} {p.label.render(lang)}", ""]
        for key, text in _facts(p, t):
            if text:
                L.append(f"- **{key}:** {text}")
        if p.reasons:
            L += [f"- **{t('key.why')}:**"] + [f"  - {r.render(lang)}" for r in p.reasons]
        L.append("")
    return L


def _appendix_md(lang, t):
    L = []
    for kind, x in _appendix(lang, t):
        if kind == "h":
            L += [f"## {x}", ""]
        elif kind == "h3":
            L += [f"### {x}", ""]
        elif kind == "p":
            L += [x, ""]
        elif kind == "key":
            L += [f"- {EMOJI[lv]} **{name}** — {means} {when}" for lv, name, means, when in x] + [""]
        elif kind == "dl":
            L += [f"- **{term}:** {text}" for term, text in x] + [""]
        else:
            L += [f"- {text}" for text in x] + [""]
    return L


def render_markdown(rep, lang=i18n.DEFAULT):
    """Plain summary and one card per plant first, then the technical details, the appendix, the sources."""
    t = _t(lang)
    summary = _summary(rep, lang, t)
    L = [f"# {t('title', date=rep.date)}", ""]
    for line in summary:
        L += [line, ""]
    if _upstream_note(rep, t):
        L += [f"> **{_upstream_note(rep, t)}**", ""]
    for p in rep.plants:
        L += [f"### {_name(p, lang)} — {EMOJI[p.level]} {_lv(p.level).render(lang)}", ""]
        L += [f"- **{key}:** {text}" for key, text in _card(rep, p, lang, t)] + [""]
    L += _technical_md(rep, lang, t) + _appendix_md(lang, t)
    L += ["---", "", f"**{t('sources.title')}**", ""] + [f"- {_attr(a, t)}" for a in rep.attributions]
    if rep.notes:
        L += ["", f"**{t('map.title')}**", ""] + [f"- {_note(n, lang)}" for n in rep.notes]
    L += ["", f"*{t('disclaimer')}*", ""]
    return "\n".join(L)


# --- HTML (email-safe: inline CSS, no JS, no external fonts or links) ----------------------------

def _e(x):
    """Escape for HTML; the Unicode isolates i18n puts around numbers and ids in RTL text become <bdi>."""
    return html.escape(str(x), quote=True).replace(i18n.FSI, "<bdi>").replace(i18n.PDI, "</bdi>")


def _badge(level, text):
    fg = "#222" if level is Level.YELLOW else "#fff"
    return (f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;background:{COLOR[level]};'
            f'color:{fg};font-weight:bold">{_e(text)}</span>')


def _appendix_html(lang, t, side):
    out = ['<div id="appendix" style="margin-top:24px;font-size:14px">']
    for kind, x in _appendix(lang, t):
        if kind == "h":
            out.append(f'<h2 style="font-size:19px;margin:0 0 8px">{_e(x)}</h2>')
        elif kind == "h3":
            out.append(f'<h3 style="font-size:16px;margin:16px 0 6px">{_e(x)}</h3>')
        elif kind == "p":
            out.append(f'<p style="margin:0 0 8px">{_e(x)}</p>')
        elif kind == "key":
            out.append('<table style="border-collapse:collapse;width:100%">' + "".join(
                f'<tr><td style="padding:6px 8px;border-bottom:1px solid #ddd;vertical-align:top;white-space:nowrap">'
                f'{_badge(lv, name)}</td><td style="padding:6px 8px;border-bottom:1px solid #ddd;vertical-align:top">'
                f'<b>{_e(means)}</b> {_e(when)}</td></tr>' for lv, name, means, when in x) + "</table>")
        elif kind == "dl":
            out.append(f'<ul style="margin:0;padding-{side}:20px">' + "".join(
                f"<li><b>{_e(term)}:</b> {_e(text)}</li>" for term, text in x) + "</ul>")
        else:
            out.append(f'<ul style="margin:0;padding-{side}:20px">' + "".join(f"<li>{_e(text)}</li>" for text in x) + "</ul>")
    out.append("</div>")
    return out


def render_html(rep, png=None, lang=i18n.DEFAULT):
    """`png`: the map's bytes, embedded as a data: URI so the file shows its map wherever it is opened, alone."""
    t = _t(lang)
    rtl = i18n.is_rtl(lang)
    side = "right" if rtl else "left"
    title = html.escape(t("title", date=rep.date).replace(i18n.FSI, "").replace(i18n.PDI, ""), quote=True)
    head = (f'<!doctype html>\n<html lang="{lang}" dir="{"rtl" if rtl else "ltr"}">\n<head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title></head>\n')
    font = "font-family:Arial,Helvetica,sans-serif"
    td = "padding:6px 8px;border-bottom:1px solid #ddd;vertical-align:top"
    summary = _summary(rep, lang, t)
    out = [f'{head}<body style="margin:0;padding:16px;background:#f4f5f7;{font};color:#222'
           f'{";direction:rtl;text-align:right" if rtl else ""}">',
           '<div style="max-width:680px;margin:0 auto;background:#fff;padding:20px">',
           f'<h1 style="font-size:22px;margin:0 0 8px">{_e(t("title", date=rep.date))}</h1>']
    out += [f'<p style="margin:0 0 8px">{_e(x)}</p>' for x in summary]
    if _upstream_note(rep, t):
        out.append(f'<p style="margin:0 0 12px;padding:8px;background:#fff3cd;border:1px solid #e8b923"><b>{_e(_upstream_note(rep, t))}</b></p>')
    for p in rep.plants:
        out.append(f'<div style="margin:14px 0;padding:8px 12px;background:#fafafa;border-{side}:6px solid {COLOR[p.level]}">'
                   f'<h2 style="font-size:17px;margin:0 0 6px">{_e(_name(p, lang))} {_badge(p.level, _lv(p.level).render(lang))}</h2>'
                   f'<ul style="font-size:14px;margin:0;padding-{side}:20px">'
                   + "".join(f"<li><b>{_e(key)}:</b> {_e(text)}</li>" for key, text in _card(rep, p, lang, t)) + "</ul></div>")
    if png:
        out.append(f'<p><img src="data:image/png;base64,{base64.b64encode(png).decode("ascii")}" alt="{_e(t("map.alt"))}" '
                   f'style="max-width:100%;height:auto;border:1px solid #ddd"></p>')
    out += [f'<h2 id="technical" style="font-size:19px;margin:28px 0 8px">{_e(t("tech.title"))}</h2>',
            f'<p style="margin:0 0 12px">{_e(_changes(rep, t))}</p>',
            f'<table style="border-collapse:collapse;width:100%;font-size:14px">'
            f'<tr style="text-align:{side}"><th style="{td}">{_e(t("th.plant"))}</th><th style="{td}">{_e(t("th.level"))}</th>'
            f'<th style="{td}">{_e(t("th.chl"))}</th><th style="{td}">{_e(t("th.data"))}</th></tr>']
    for p in rep.plants:
        out.append(f'<tr><td style="{td}">{_e(_name(p, lang))}</td><td style="{td}">{_badge(p.level, p.label.render(lang))}</td>'
                   f'<td style="{td}">{_e(_chl_cell(p, t))}</td><td style="{td}">{_e(_source_line(p, t) or t("cell.nodata"))}</td></tr>')
    out.append("</table>")
    out.append(f'<p style="font-size:13px;margin:12px 0 4px"><b>{_e(t("datedates"))}</b></p><ul style="font-size:13px;margin:0">'
               + "".join(f"<li>{_e(d)}</li>" for d in _data_dates(rep, t)) + "</ul>")
    for p in rep.plants:
        out.append(f'<h3 style="font-size:17px;margin:20px 0 6px">{_e(_name(p, lang))} {_badge(p.level, p.label.render(lang))}</h3>'
                   f'<ul style="font-size:14px;margin:0;padding-{side}:20px">')
        for key, text in _facts(p, t):
            if text:
                out.append(f"<li><b>{_e(key)}:</b> {_e(text)}</li>")
        if p.reasons:
            out.append(f"<li><b>{_e(t('key.why'))}:</b><ul>" + "".join(f"<li>{_e(r.render(lang))}</li>" for r in p.reasons) + "</ul></li>")
        out.append("</ul>")
    out += _appendix_html(lang, t, side)
    out.append('<hr style="border:0;border-top:1px solid #ddd;margin:20px 0"><div id="sources" style="font-size:12px;color:#555">'
               f"<p><b>{_e(t('sources.title'))}</b></p><ul>" + "".join(f"<li>{_e(_attr(a, t))}</li>" for a in rep.attributions) + "</ul>"
               + (f"<p><b>{_e(t('map.title'))}</b></p><ul>" + "".join(f"<li>{_e(_note(n, lang))}</li>" for n in rep.notes) + "</ul>" if rep.notes else "")
               + f"<p><i>{_e(t('disclaimer'))}</i></p></div></div></body></html>")
    return "\n".join(out)


# --- short message (plain text, two sentences per plant) -----------------------------------------

def _cause(p):
    """Why this plant has its level, as one clause: the grey reason, else the strongest rule that fired."""
    if p.level is Level.GREY:
        why = p.grey_why
        if why is None:
            return Msg("cause.no_data")
        return Msg(f"cause.{why.code}", **why.params) if f"cause.{why.code}" in i18n.load(i18n.DEFAULT)["strings"] else why
    codes = {r.code: r for r in p.reasons}
    if "red_mult" in codes:
        return Msg("cause.red_mult", ratio=codes["red_mult"].params["ratio"])
    if "two_days" in codes:
        return Msg("cause.two_days")
    for code, wanted in (("cause.p97", ">=P97"), ("cause.rising", None), ("cause.p90", ">=P90"), ("cause.p75", ">=P75")):
        if (wanted is None and "rising" in codes) or (wanted is not None and p.rank == wanted):
            return Msg(code)
    return Msg("cause.normal")


def _plant_short(p, lang, t, ref):
    """Exactly two sentences: 1) name, level and the main cause; 2) the value, the one seasonal threshold it is
    judged against and the data date (for a grey: that nothing could be compared, and why it is not a green)."""
    if p.lifted_by:
        first = t("short.s1.upstream", name=_name(p, lang), level=_lv(p.level),
                  by=[_sentinel_by(i) for i in p.lifted_by], id=Id(p.id), own=Msg(f"levelword.{p.own_level.name}"))
    else:
        first = t("short.s1", name=_name(p, lang), level=_lv(p.level), cause=_cause(p))
    when = i18n.short_date(lang, p.data_date, ref) if p.data_date is not None else None
    if p.level is not Level.GREY and p.value is not None and p.pctl is not None:
        name = p.rank.params["p"] if p.rank.code == "rank.ge" else None
        edge = getattr(p.pctl, name.lower()) if name else p.pctl.p50
        rel = Msg(f"short.rel.{name or 'lt'}", v=_g(edge))
        second = t("short.s2", chl=f"{_g(p.value)} {UNIT}", rel=rel, date=when)
    elif when is not None and p.source is not None:
        second = t("short.s2.grey_dated", date=when)
    else:
        second = t("short.s2.grey_none")
    return f"{EMOJI[p.level]} {first} {second}"


RLM = "\u200f"


def _plain(text, lang):
    """One line of the plain-text message: no Unicode isolates (some clients draw them as boxes); in a right-to-left
    language a right-to-left mark where the line would start or end with a Latin or number run."""
    text = "".join(c for c in text if c not in (i18n.FSI, i18n.PDI, "\u2066", "\u2067"))
    if not i18n.is_rtl(lang):
        return text
    word = [c for c in text if c.isalnum()]
    if word and word[0].isascii():
        text = RLM + text
    if word and word[-1].isascii():
        text += RLM
    return text


def render_text(rep, lang=i18n.DEFAULT, report_file="default"):
    """The short message: a one-line header, one paragraph per plant (worst first), one closing line. `report_file`
    is the file the closing line points to (default: the html report); None when no md or html report is written."""
    t = _t(lang)
    head = t("short.header" if rep.plants else "short.header.none", date=rep.date)
    if report_file == "default":
        report_file = f"dbw-report-{rep.date}.html"
    closing = t("short.closing", file=report_file) if report_file else t("short.closing.nofile")
    parts = [head] + [x for x in (_short_changes(rep, lang, t), _upstream_note(rep, t)) if x] \
        + [_plant_short(p, lang, t, rep.date) for p in rep.plants] + [closing]
    return "\n\n".join(_plain(x, lang) for x in parts) + "\n"


# --- PNG map ------------------------------------------------------------------------------------

def _coastline():
    return json.loads(COASTLINE.read_text(encoding="utf-8"))["regions"]


def _panel_boxes(rep, sea):
    """[(id, polygon, level, is_plant, text)] drawn on one sea's panel."""
    items = [(p.id, p.polygon, p.level, True, f"{p.id} · {p.level.name}" + (" (upstream)" if p.label != p.level.name else ""))
             for p in rep.plants if p.sea == sea]
    items += [(s.id, s.polygon, s.level, False, f"{s.id} (sentinel)") for s in rep.sentinels if s.sea == sea]
    return items


def view_bbox(rep, sea, pad=0.25):
    """(lat_min, lat_max, lon_min, lon_max) of the drawn boxes plus padding; the GIBS image uses the same one."""
    pts = [pt for _, poly, *_ in _panel_boxes(rep, sea) for pt in poly]
    lats, lons = [p[0] for p in pts], [p[1] for p in pts]
    return min(lats) - pad, max(lats) + pad, min(lons) - pad, max(lons) + pad


def _seas(rep):
    return [s for s in SEAS if _panel_boxes(rep, s)]


def draw_map(rep, underlays=None):
    """matplotlib Figure: land from the bundled coastline (or a GIBS image where given), the chosen
    intake boxes and their sentinels coloured by level, a legend, attributions and the disclaimer."""
    import math

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch, Polygon

    underlays = underlays or {}
    land = _coastline()
    seas = _seas(rep)
    boxes = {s: view_bbox(rep, s) for s in seas}
    # leave the right 30 % of each panel for the label column
    views = {}
    for s, (la0, la1, lo0, lo1) in boxes.items():
        views[s] = (la0, la1, lo0, lo0 + (lo1 - lo0) / 0.70)
    widths = [(v[3] - v[2]) * math.cos(math.radians((v[0] + v[1]) / 2)) / (v[1] - v[0]) for v in views.values()]
    fig = plt.figure(figsize=(min(13.0, max(8.0, 6.0 * sum(widths))), 7.4), dpi=100)
    gs = fig.add_gridspec(1, len(seas), width_ratios=widths, left=0.04, right=0.98, top=0.90, bottom=0.27,
                          wspace=0.12)
    for col, sea in enumerate(seas):
        ax = fig.add_subplot(gs[0, col])
        la0, la1, lo0, lo1 = views[sea]
        ax.set_facecolor("#dfeaf2")
        if sea in underlays:
            ax.imshow(underlays[sea], extent=(lo0, lo1, la0, la1), aspect="auto", zorder=0)
        else:
            for ring in land[sea]["rings"]:
                ax.add_patch(Polygon(ring, closed=True, facecolor="#ebe6d6", edgecolor="#9a917a", lw=0.8, zorder=1))
        ax.set_xlim(lo0, lo1)
        ax.set_ylim(la0, la1)
        ax.set_aspect(1 / math.cos(math.radians((la0 + la1) / 2)))
        ax.set_title(SEA_TITLE[sea], fontsize=11)
        ax.tick_params(labelsize=7)
        ax.grid(color="#ffffff", alpha=0.35, lw=0.5)
        items = sorted(_panel_boxes(rep, sea), key=lambda i: sum(p[0] for p in i[1][:4]) / 4)
        ys = [la0 + (la1 - la0) * (0.06 + 0.88 * k / max(len(items) - 1, 1)) for k in range(len(items))]
        for (bid, poly, level, is_plant, text), y in zip(items, ys):
            ring = [(lon, lat) for lat, lon in poly]
            ax.add_patch(Polygon(ring, closed=True, facecolor=COLOR[level], edgecolor="#222", lw=1.2,
                                 ls="-" if is_plant else "--", alpha=0.85, zorder=3))
            cy, cx = sum(p[0] for p in poly[:4]) / 4, sum(p[1] for p in poly[:4]) / 4
            ax.plot([cx], [cy], marker="o" if is_plant else "s", ms=9 if is_plant else 7, mfc=COLOR[level],
                    mec="#222", mew=1.2, zorder=4)
            ax.annotate(text, xy=(cx, cy), xytext=(0.74, (y - la0) / (la1 - la0)), textcoords="axes fraction",
                        fontsize=8, va="center", ha="left", zorder=5,
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8),
                        arrowprops=dict(arrowstyle="-", color="#555", lw=0.7, shrinkA=0, shrinkB=4))
    fig.suptitle(f"Desal Bloom Watch — {rep.date}", fontsize=12, y=0.975)
    handles = [Patch(fc=COLOR[l], ec="#222", label=l.name.title()) for l in
               (Level.GREEN, Level.YELLOW, Level.ORANGE, Level.RED, Level.GREY)]
    handles += [Line2D([], [], marker="o", ls="", mfc="white", mec="#222", label="plant intake box"),
                Line2D([], [], marker="s", ls="", mfc="white", mec="#222",
                       label=f"sentinel (yellow ≥ P90, orange ≥ {SENTINEL_MULT:g}× P90)")]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=8, frameon=False, bbox_to_anchor=(0.5, 0.185))
    notes = list(rep.attributions) + list(rep.notes) + [DISCLAIMER]
    wrapped = "\n".join(line for n in notes for line in textwrap.wrap(n, 150, break_on_hyphens=False) or [""])
    fig.text(0.02, 0.155, wrapped, fontsize=7, va="top", ha="left", color="#333")
    return fig


def fetch_underlays(rep, fetch=gibs.http_get_bytes):
    """({sea: image}, [one note per distinct failure reason]) for the optional GIBS underlay."""
    imgs, failed = {}, {}
    for sea in _seas(rep):
        la0, la1, lo0, lo1 = view_bbox(rep, sea)
        img, why = gibs.fetch_image((la0, la1, lo0, lo0 + (lo1 - lo0) / 0.70), rep.date, fetch=fetch)
        if img is None:
            failed.setdefault(why, []).append(sea)
        else:
            imgs[sea] = img
    return imgs, [Msg("map.fallback", why=why, seas=[Id(sea) for sea in seas]) for why, seas in failed.items()]


def render_png(rep, path, underlays=None):
    import matplotlib.pyplot as plt
    fig = draw_map(rep, underlays)
    fig.savefig(path, dpi=100, format="png")
    plt.close(fig)


# --- write ---------------------------------------------------------------------------------------

def write_report(rep, out_dir, formats=FORMATS, basemap="none", fetch=gibs.http_get_bytes, lang=i18n.DEFAULT):
    """Write dbw-report-<date>.{html,md,png,txt} into `out_dir`, the text in `lang` (the PNG map stays English).
    -> ({format: Path}, [fallback notes])."""
    i18n.load(lang)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    unknown = [f for f in formats if f not in FORMATS]
    if unknown:
        raise ValueError(f"unknown format(s): {', '.join(unknown)}")
    underlays, notes = {}, []
    if basemap == "gibs" and "png" in formats:
        underlays, notes = fetch_underlays(rep, fetch)
        rep = replace(rep, notes=tuple(notes), attributions=rep.attributions + ((gibs.ATTRIBUTION,) if underlays else ()))
    stem = f"dbw-report-{rep.date}"
    files = {}
    if "png" in formats:
        files["png"] = out_dir / f"{stem}.png"
        render_png(rep, files["png"], underlays)
    if "md" in formats:
        files["md"] = out_dir / f"{stem}.md"
        files["md"].write_text(render_markdown(rep, lang), encoding="utf-8")
    if "html" in formats:
        files["html"] = out_dir / f"{stem}.html"
        files["html"].write_text(render_html(rep, png=files["png"].read_bytes() if "png" in files else None, lang=lang),
                                 encoding="utf-8")
    if "txt" in formats:
        files["txt"] = out_dir / f"{stem}.txt"
        shown = next((files[f].name for f in ("html", "md") if f in files), None)
        files["txt"].write_text(render_text(rep, lang, report_file=shown), encoding="utf-8")
    return files, notes
