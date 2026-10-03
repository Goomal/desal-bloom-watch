"""DBW-3c: a report a plant manager can read. Two layers (plain summary + cards, then technical details), an
appendix that explains the colours and the terms, a source-switch label on level changes. Offline.
Fixtures: readable_db.json is a slice of real history (2026-10-02 ashdod RED -> GREEN on a satellite switch;
2026-09-29 four plants); golden_db.json has the older golden cases; golden_en_pre_readable/ is what the English
markdown and html looked like before this layout (nothing in it may be lost)."""
import dataclasses
import hashlib
import html as htmllib
import json
import re
from datetime import date
from pathlib import Path

import pytest

from dbw import i18n, registry, report, store
from dbw.assess import DINEOF, N20
from dbw.i18n import Msg
from dbw.score import Level
from test_golden_en import DB as GOLDEN_DB
from test_golden_en import _load

FIX = Path(__file__).parent / "fixtures"
READABLE_DB = json.loads((FIX / "readable_db.json").read_text(encoding="utf-8"))
LANGS = ("en", "he", "ar")
CASES = [("readable", n) for n in READABLE_DB] + [("golden", n) for n in GOLDEN_DB]


@pytest.fixture(scope="module")
def reports(tmp_path_factory):
    out = {}
    for kind, name in CASES:
        case = (READABLE_DB if kind == "readable" else GOLDEN_DB)[name]
        conn = store.connect(tmp_path_factory.mktemp(name) / "r.sqlite")
        _load(conn, case)
        out[name] = report.build_report(conn, registry.load(), case["plants"], date.fromisoformat(case["date"]))
    return out


def plant(rep, pid):
    return next(p for p in rep.plants if p.id == pid)


def visible(html):
    """The text of an html string: no tags, no style, entities decoded, whitespace collapsed."""
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    html = re.sub(r"<[^>]*>?", " ", html)
    return " ".join(htmllib.unescape(html).replace(i18n.FSI, "").replace(i18n.PDI, "").split())


def plain_md(rep, lang):
    md = report.render_markdown(rep, lang)
    head = "## " + Msg("tech.title").render(lang)
    assert head in md
    return md.partition(head)[0]


def plain_html(rep, lang):
    h = report.render_html(rep, lang=lang)
    assert 'id="technical"' in h
    return visible(h.partition('id="technical"')[0])


# --- scoring guard -------------------------------------------------------------------------------

def test_scoring_battery_file_is_byte_identical():
    """DBW-3c changes wording and layout only: the recorded score battery must not move (sha256 of the file)."""
    got = hashlib.sha256((FIX / "golden_en_score.json").read_bytes()).hexdigest()
    assert got == "3011158f56159dda4c86617d5a00901a002bcaa5553d2a244b98add728899ac9"


# --- the jargon ban ------------------------------------------------------------------------------

LATIN_JARGON = [r"pixel", r"DINEOF", r"N20", r"VIIRS", r"sentinel", r"fallback", r"\bn=", r"percentile",
                r"\bP(?:50|75|90|97)\b"]
LOCAL_JARGON = {
    "en": [],
    "he": ["פיקסל", "חלופה", "אחוזון", "סנטינל"],
    "ar": ["بكسل", "بديل", "مئين", "حارس"],
}


def jargon(text, lang):
    hits = [p for p in LATIN_JARGON if re.search(p, text, re.I if p.islower() else 0)]
    return hits + [p for p in LOCAL_JARGON[lang] if p in text]


@pytest.mark.parametrize("lang,text,expect", [
    ("en", "1/2 pixels valid", ["pixel"]),
    ("en", "P50 0.626 · P75 1.34, n=121", ["\\bn=", "\\bP(?:50|75|90|97)\\b"]),
    ("en", "DINEOF 9 km gap-filled, N20, VIIRS, a sentinel, fallback", ["DINEOF", "N20", "VIIRS", "sentinel", "fallback"]),
    ("he", "1/2 פיקסלים תקפים, חלופה, האחוזון ה-90", ["פיקסל", "חלופה", "אחוזון"]),
    ("ar", "بكسل صالح، بديل، المئين 90", ["بكسل", "بديل", "مئين"]),
    ("en", "Ashkelon is RED: 6.4 mg/m³, 4.2 times normal (sharp 4 km satellite)", []),
])
def test_jargon_checker_catches_the_banned_terms_and_passes_plain_text(lang, text, expect):
    assert sorted(jargon(text, lang)) == sorted(expect)


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("name", [n for _, n in CASES])
def test_plain_layer_has_no_jargon_in_markdown_and_html(reports, name, lang):
    rep = reports[name]
    for text in (plain_md(rep, lang), plain_html(rep, lang)):
        assert jargon(text, lang) == [], (name, lang, jargon(text, lang))


@pytest.mark.parametrize("lang", LANGS)
def test_technical_layer_keeps_the_technical_words(reports, lang):
    md = report.render_markdown(reports["switch"], lang)
    tech = md.partition("## " + Msg("tech.title").render(lang))[2]
    assert "P50" in tech and "DINEOF" in tech and "n=" in tech


# --- layout: plain, technical, appendix, footer, in that order -------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_markdown_layers_come_in_order(reports, lang):
    rep = reports["four"]
    md = report.render_markdown(rep, lang)
    marks = ["## " + Msg("tech.title").render(lang), "## " + Msg("app.title").render(lang),
             "**" + Msg("sources.title").render(lang) + "**", Msg("disclaimer").render(lang)]
    at = [md.index(m) for m in marks]
    assert at == sorted(at) and len(set(at)) == 4
    assert md.index(i18n.display_name(lang, "ashkelon", "Ashkelon")) < at[0]  # the cards are above the details


@pytest.mark.parametrize("lang", LANGS)
def test_html_layers_come_in_order(reports, lang):
    h = report.render_html(reports["four"], png=b"\x89PNG\r\n\x1a\nm", lang=lang)
    at = [h.index(m) for m in ('src="data:image/png;base64,', 'id="technical"', 'id="appendix"', 'id="sources"')]
    assert at[0] < at[1] < at[2] < at[3]
    low = h.lower()
    for bad in ("<script", "<details", "<link", "@import", "src:", "http://", "https://"):
        assert bad not in low, bad
    assert "<a " not in low  # URLs are printed as text, nothing to click in a mail client


def test_cards_are_worst_first(reports):
    plain = plain_md(reports["four"], "en")
    assert plain.index("Ashkelon") < plain.index("Hadera") < plain.index("Eilat")


# --- the plain summary and the cards (English wording) -------------------------------------------

def test_summary_gives_the_data_freshness_and_no_worst_level_headline(reports):
    plain = plain_md(reports["four"], "en")
    assert "2026-09-29" in plain and "RED" in plain and "Ashkelon" in plain  # title date; the Ashkelon card says RED
    assert "Worst level" not in plain
    assert re.search(r"Satellite data from \d+ \w+(?: to \d+ \w+)?, \d+(?: to \d+)? days? ago", plain), plain


def test_card_for_a_red_plant_says_what_it_means_and_how_far_above_normal(reports):
    card = plain_md(reports["four"], "en").partition("### Ashkelon")[2].partition("###")[0]
    assert "RED" in card
    assert "Compared with normal for this time of year" in card and "far above normal" in card
    assert "6.4 mg/m³" in card and "4.2 times" in card  # the one threshold that matters, in plain words
    assert "How sure" in card


def test_card_for_a_calm_plant_is_normal(reports):
    card = plain_md(reports["switch"], "en").partition("### Ashdod")[2].partition("###")[0]
    assert "GREEN" in card and "normal" in card and "1.29 mg/m³" in card
    assert "far above" not in card


@pytest.mark.parametrize("lang", ["he", "ar"])
def test_cards_use_the_localised_words(reports, lang):
    card = plain_md(reports["four"], lang).partition("### " + i18n.display_name(lang, "ashkelon", "Ashkelon"))[2]
    assert Msg("plain.vs").render(lang) in card and Msg("band.far").render(lang) in card
    assert Msg("plain.sure").render(lang) in card
    assert Msg("level.RED").render(lang) in card


def test_upstream_row_and_shared_row_are_in_plain_words(reports):
    rep = reports["upstream_red_shared"]
    plain = plain_md(rep, "en")
    assert re.search(r"Upstream monitoring points:\*{0,2} \d of \d above their usual high", plain), plain
    assert "are read from the same satellite squares, so they move together" in plain
    assert "pixel" not in plain


def test_upstream_label_is_still_there_in_the_technical_layer(reports):
    rep = reports["upstream_orange"]
    eilat = plant(rep, "eilat")
    md = report.render_markdown(rep)
    assert eilat.label in md.partition("## Technical details")[2]
    assert "upstream" in plain_md(rep, "en").lower()  # the plain card says the level comes from upstream


# --- how sure (confidence word) ------------------------------------------------------------------

def base(reports):
    p = plant(reports["four"], "hadera")
    assert p.level is Level.GREEN and p.source == N20
    return dataclasses.replace(p, age_days=2, valid=2, total=2)


def grade(p):
    return report.how_sure(p)[0]


def test_good_needs_a_recent_clear_view_by_the_sharp_satellite(reports):
    p = base(reports)
    assert grade(p) == "good"
    assert report.how_sure(p)[1].startswith("Good: clear view 2 days ago (sharp satellite)")
    assert grade(dataclasses.replace(p, age_days=0, valid=3, total=4)) == "good"


def test_limited_when_the_view_is_partial_old_or_smoothed(reports):
    p = base(reports)
    half = report.how_sure(dataclasses.replace(p, valid=1, total=2))
    assert half[0] == "limited" and half[1].startswith("Limited: half the area was cloud-free")
    assert grade(dataclasses.replace(p, valid=1, total=3)) == "limited"
    assert grade(dataclasses.replace(p, age_days=3)) == "limited"
    smooth = report.how_sure(dataclasses.replace(p, source=DINEOF))
    assert smooth[0] == "limited" and "smoothed" in smooth[1]


def test_low_for_every_grey(reports):
    p = base(reports)
    stale = dataclasses.replace(p, level=Level.GREY, age_days=5, valid=2, total=2)
    g, text = report.how_sure(stale)
    assert g == "low" and text.startswith("Low: no clear view for 5 days")
    none = dataclasses.replace(p, level=Level.GREY, age_days=None, valid=0, total=0, data_date=None)
    assert report.how_sure(none)[0] == "low" and "no satellite data" in report.how_sure(none)[1]


@pytest.mark.parametrize("lang", LANGS)
def test_how_sure_words_exist_in_every_language(reports, lang):
    for word in ("good", "limited", "low"):
        assert Msg(f"sure.word.{word}").render(lang)
    g, msg = report.how_sure(base(reports))
    assert msg.render(lang).startswith(Msg(f"sure.word.{g}").render(lang))


def test_the_how_sure_rule_is_documented():
    doc = (Path(__file__).parent.parent / "docs" / "reading-the-report.md").read_text(encoding="utf-8")
    assert "How sure" in doc
    for const in ("GOOD_MAX_AGE", "GOOD_MIN_SHARE"):
        assert const in doc and hasattr(report, const)
    assert f"{report.GOOD_MAX_AGE} days" in doc


# --- changed since yesterday + the source-switch label ---------------------------------------------

def test_the_model_remembers_yesterdays_source(reports):
    rep = reports["switch"]
    a = plant(rep, "ashdod")
    assert rep.changes == (("ashdod", Level.RED, Level.GREEN),)
    assert a.prev_source == N20 and a.source == DINEOF


def test_level_change_across_a_satellite_switch_is_labelled(reports):
    plain = plain_md(reports["switch"], "en")
    line = next(l for l in plain.splitlines() if "Changed since yesterday" in l)
    assert "Ashdod RED → GREEN" in line
    assert "satellite changed from sharp 4 km to smoothed 9 km" in line
    assert "the two days are not directly comparable" in line
    assert "Changed since yesterday" in plain_html(reports["switch"], "en")
    assert "not directly comparable" in plain_html(reports["switch"], "en")


@pytest.mark.parametrize("lang", ["he", "ar"])
def test_the_switch_label_is_localised(reports, lang):
    sharp, smooth = Msg("kind.sharp").render(lang), Msg("kind.smooth").render(lang)
    name = report._short(i18n.display_name(lang, "ashdod", "Ashdod"))
    lines = [l for l in plain_md(reports["switch"], lang).splitlines() if sharp in l and smooth in l]
    assert len(lines) == 1 and name in lines[0] and Msg("level.RED").render(lang) in lines[0]
    assert "satellite" not in lines[0]


def test_no_label_when_the_source_did_not_change(reports):
    rep = reports["switch"]
    same = dataclasses.replace(rep, plants=tuple(dataclasses.replace(p, prev_source=p.source) for p in rep.plants))
    assert "directly comparable" not in plain_md(same, "en")
    assert "Ashdod RED → GREEN" in plain_md(same, "en")


def test_no_label_when_nothing_changed_or_the_level_is_grey(reports):
    four = plain_md(reports["four"], "en")
    assert "No plant changed level since yesterday." in four and "directly comparable" not in four
    rep = reports["switch"]
    grey = dataclasses.replace(rep, plants=tuple(dataclasses.replace(p, level=Level.GREY) if p.id == "ashdod" else p
                                                for p in rep.plants),
                               changes=(("ashdod", Level.RED, Level.GREY),))
    assert "directly comparable" not in plain_md(grey, "en")


def test_switch_rule_helper(reports):
    a = plant(reports["switch"], "ashdod")
    assert report.source_switched(a, Level.RED) is True
    assert report.source_switched(dataclasses.replace(a, prev_source=a.source), Level.RED) is False
    assert report.source_switched(dataclasses.replace(a, prev_source=None), Level.RED) is False


# --- the short .txt message carries a one-line change note ------------------------------------------

def txt_paragraphs(rep, lang):
    return report.render_text(rep, lang).strip("\n").split("\n\n")


def no_switch(rep):
    return dataclasses.replace(rep, plants=tuple(dataclasses.replace(p, prev_source=p.source) for p in rep.plants))


def test_txt_change_line_with_a_source_switch(reports):
    parts = txt_paragraphs(reports["switch"], "en")
    assert parts[1] == "Changed since yesterday: Ashdod RED → GREEN (satellite changed; not directly comparable)"
    assert parts[0].startswith("Desal Bloom Watch 2026-10-02")
    assert len(parts) == 1 + 1 + len(reports["switch"].plants) + 1  # header, change line, plants, closing


def test_txt_change_line_without_a_source_switch(reports):
    parts = txt_paragraphs(no_switch(reports["switch"]), "en")
    assert parts[1] == "Changed since yesterday: Ashdod RED → GREEN"
    assert "comparable" not in report.render_text(no_switch(reports["switch"]), "en")


def test_txt_has_no_change_line_when_nothing_changed(reports):
    text = report.render_text(reports["four"], "en")
    assert "Changed since yesterday" not in text
    parts = txt_paragraphs(reports["four"], "en")
    assert len(parts) == 1 + len(reports["four"].plants) + 1  # header, plants, closing: no extra line


@pytest.mark.parametrize("lang", ["he", "ar"])
def test_txt_change_line_is_localised(reports, lang):
    sw = txt_paragraphs(reports["switch"], lang)[1]
    plain = txt_paragraphs(no_switch(reports["switch"]), lang)[1]
    name = report._short(i18n.display_name(lang, "ashdod", "Ashdod"))
    for line in (sw, plain):
        assert name in line and Msg("level.RED").render(lang) in line and Msg("level.GREEN").render(lang) in line
        assert "Changed" not in line and "satellite" not in line
    assert sw.startswith(plain.rstrip(report.RLM)) or plain.rstrip(report.RLM) in sw
    assert len(sw) > len(plain) and "\n" not in sw
    assert not set(sw) & set(i18n.FSI + i18n.PDI)


def test_txt_change_line_shows_every_change(reports):
    rep = reports["switch"]
    two = dataclasses.replace(no_switch(rep), changes=(("ashdod", Level.RED, Level.GREEN), ("eilat", Level.GREEN, Level.YELLOW)))
    line = txt_paragraphs(two, "en")[1]
    eilat = report._short(plant(rep, "eilat").name)
    assert "Ashdod RED → GREEN" in line and f"{eilat} GREEN → YELLOW" in line and "\n" not in line


# --- nothing lost -------------------------------------------------------------------------------

OLD = FIX / "golden_en_pre_readable"
NUM = re.compile(r"\d+(?:\.\d+)?")


@pytest.mark.parametrize("name", sorted(p.stem for p in OLD.glob("*.md")))
def test_every_line_of_the_old_markdown_is_still_in_the_new_one(reports, name):
    old = (OLD / f"{name}.md").read_text(encoding="utf-8").splitlines()
    new = report.render_markdown(reports[name])
    # the per-plant details moved down one heading level (## -> ###)
    lines = {l.replace("### ", "## ", 1) if l.startswith("### ") else l for l in new.splitlines()}
    summary = ("**Worst level", "**Changed since", "No plant changed", "|")
    for line in filter(str.strip, old):
        if line.startswith(summary) or line.startswith("Changed since") or "Worst level" in line:
            for tok in NUM.findall(line):  # headline, changes and table row: their numbers must survive
                assert tok in new, (name, line, tok)
            continue
        assert line in lines, (name, line)


@pytest.mark.parametrize("name", sorted(p.stem for p in OLD.glob("*.html")))
def test_every_number_and_phrase_of_the_old_html_is_still_in_the_new_one(reports, name):
    old = visible((OLD / f"{name}.html").read_text(encoding="utf-8"))
    new = visible(report.render_html(reports[name]))
    for tok in set(NUM.findall(old)):
        assert tok in new, (name, tok)
    for line in re.findall(r"(?:Chlorophyll|Source|Data confidence|SST|Upstream sentinels|Shared pixels): [^<]*?(?= (?:Chlorophyll|Source|"
                           r"Data confidence|SST|Upstream sentinels|Shared pixels|Why)\b|$)", old):
        assert line.strip() in new, (name, line)


# --- the appendix ---------------------------------------------------------------------------------

APP_KEYS = sorted(k for k in i18n.load("en")["strings"] if k.startswith("app."))


def test_the_appendix_strings_are_plain_text_without_placeholders():
    assert len(APP_KEYS) > 25
    for k in APP_KEYS:
        assert "{" not in i18n.load("en")["strings"][k], k


@pytest.mark.parametrize("lang", LANGS)
def test_appendix_is_in_markdown_with_every_section(reports, lang):
    md = report.render_markdown(reports["four"], lang)
    start = md.index("## " + Msg("app.title").render(lang))
    app = md[start:md.index("\n---\n", start)]
    assert app
    for k in APP_KEYS:
        assert Msg(k).render(lang) in app, (lang, k)


@pytest.mark.parametrize("lang", LANGS)
def test_appendix_is_in_html_with_every_section(reports, lang):
    h = report.render_html(reports["four"], lang=lang)
    app = visible(h.partition('id="appendix"')[2].partition('id="sources"')[0])
    assert app
    for k in APP_KEYS:
        assert visible(htmllib.escape(Msg(k).render(lang))) in app, (lang, k)


@pytest.mark.parametrize("lang", LANGS)
def test_colour_key_has_every_colour_with_its_trigger_and_its_meaning(lang):
    for lv in ("GREEN", "YELLOW", "ORANGE", "RED", "GREY"):
        assert Msg(f"app.key.{lv}.when").render(lang) and Msg(f"app.key.{lv}.means").render(lang)
    when = {lv: Msg(f"app.key.{lv}.when").render("en") for lv in ("YELLOW", "ORANGE", "RED", "GREY")}
    assert "upstream" in when["ORANGE"] and "two days running" in when["RED"]


def test_the_appendix_has_no_instructions_to_the_plant():
    text = " ".join(i18n.load("en")["strings"][k] for k in APP_KEYS).lower()
    for bad in ("you should", "you must", "shut", "stop the", "switch off", "dose", "increase the", "reduce the", "call "):
        assert bad not in text, bad


def test_the_appendix_names_each_source_with_its_public_address(reports):
    text = report.render_markdown(reports["four"], "en")
    for url in (f"coastwatch.noaa.gov/erddap/griddap/{N20}", f"coastwatch.noaa.gov/erddap/griddap/{DINEOF}",
                "coastwatch.noaa.gov/erddap/griddap/noaacrwsstDaily", "naturalearthdata.com", "docs/scoring.md"):
        assert url in text, url


def test_the_appendix_states_the_limits():
    text = " ".join(i18n.load("en")["strings"][k] for k in APP_KEYS).lower()
    for must in ("top few metres", "cloud", "dust", "near the shore", "early warning", "not a measurement", "analysers"):
        assert must in text, must


# --- translations --------------------------------------------------------------------------------

NEW_PREFIXES = ("plain.", "sure.", "band.", "app.", "kind.", "up.", "tech.", "sum.", "when.", "card.")


@pytest.mark.parametrize("lang", ["he", "ar"])
def test_every_new_string_is_translated(lang):
    en, other = i18n.load("en")["strings"], i18n.load(lang)["strings"]
    script = re.compile("[א-ת]" if lang == "he" else "[؀-ۿ]")
    keys = [k for k in en if k.startswith(NEW_PREFIXES) or k in ("change.switch", "join.and")]
    assert len(keys) > 60
    for k in keys:
        assert k in other, (lang, k)
        if re.search("[A-Za-z]{4}", re.sub(r"\{\w+\}", "", en[k])):
            assert script.search(other[k]), (lang, k)
