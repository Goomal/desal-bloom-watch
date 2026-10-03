"""The report in en / he / ar, and the two-sentences-per-plant short message (format `txt`). Offline."""
import re

import pytest

from dbw import i18n, registry, report
from dbw.i18n import Msg
from dbw.providers import gibs, noaa_erddap
from dbw.score import Level
from test_report import EVENT, conn, rep  # noqa: F401  (fixtures: the calm-history database and its report)

LANGS = ("en", "he", "ar")
ALL_PLANTS = [b.id for b in registry.load() if b.kind == "plant"]
MARKDOWN_SYNTAX = re.compile(r"[*#|`>\[\]]")
HEBREW, ARABIC = re.compile("[א-ת]"), re.compile("[؀-ۿ]")
SCRIPT = {"he": HEBREW, "ar": ARABIC}


@pytest.fixture(scope="module")
def rep8(conn):  # noqa: F811
    return report.build_report(conn, registry.load(), ALL_PLANTS, EVENT, mode="dineof")


def plant(rep, pid):
    return next(p for p in rep.plants if p.id == pid)


def paragraphs(text):
    return text.strip("\n").split("\n\n")


def plant_paragraphs(rep, text):
    """The per-plant paragraphs of the short message: not the header, the change line (when plants changed) or the closing."""
    return paragraphs(text)[1 + bool(rep.changes):-1]


def sentences(paragraph):
    """Terminated sentences: . ! ? or the Arabic question mark followed by whitespace or the end (not a decimal point)."""
    return re.findall(r"[.!?؟](?=\s|$)", paragraph)


# --- the formats and the language switch --------------------------------------------------------

def test_txt_is_a_format_and_a_default():
    from dbw import config
    assert "txt" in report.FORMATS and "txt" in config.FORMATS


def test_english_is_the_default_language(rep):
    assert report.render_markdown(rep, "en") == report.render_markdown(rep)
    assert report.render_html(rep, lang="en") == report.render_html(rep)


def test_english_html_has_no_direction_marks(rep):
    h = report.render_html(rep)
    assert h.startswith('<!doctype html>\n<html lang="en" dir="ltr">\n<head>') and "<bdi>" not in h
    assert "direction:rtl" not in h.replace(" ", "")


def test_unknown_language_is_rejected_by_every_renderer(rep):
    for fn in (report.render_markdown, report.render_html, report.render_text):
        with pytest.raises(ValueError):
            fn(rep, lang="fr")


# --- right-to-left HTML --------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["he", "ar"])
def test_html_is_rtl_email_safe_and_isolates_numbers(rep, lang):
    h = report.render_html(rep, png=b"\x89PNG\r\n\x1a\nx", lang=lang)
    assert h.startswith(f'<!doctype html>\n<html lang="{lang}" dir="rtl">\n<head><meta charset="utf-8">') and "<bdi>" in h
    assert 'name="viewport"' in h and "<title>" in h and "</head>\n<body" in h
    low = h.lower()
    assert "<script" not in low and "<link" not in low and "@import" not in low and "src:" not in low
    assert 'src="data:image/png;base64,' in h
    assert "direction:rtl" in h.replace(" ", "")
    assert "<bdi>9 mg/m³</bdi>" in h  # ashkelon's value stays one left-to-right unit
    assert i18n.FSI not in h and i18n.PDI not in h  # isolates became <bdi>
    assert "Worst level" not in h and "Plant</th>" not in h


@pytest.mark.parametrize("lang", ["he", "ar"])
def test_html_is_in_the_chosen_script_with_western_digits(rep, lang):
    h = report.render_html(rep, lang=lang)
    text = re.sub(r"<[^>]+>", " ", h)
    assert SCRIPT[lang].search(text)
    assert not re.search("[٠-٩۰-۹]", text)
    for pid in ("hadera", "ashkelon", "eilat"):
        assert i18n.display_name(lang, pid, "") in h


# --- markdown ------------------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["he", "ar"])
def test_markdown_is_translated_but_data_stays_as_is(rep, lang):
    md = report.render_markdown(rep, lang)
    assert SCRIPT[lang].search(md) and not re.search("[٠-٩۰-۹]", md)
    assert report.DISCLAIMER not in md and noaa_erddap.ATTRIBUTION not in md
    assert "Natural Earth" in md and "NOAA CoastWatch" in md  # licence and dataset names stay
    assert "mg/m³" in md and "DINEOF" in md and "2026-08-25" in md
    assert "Worst level" not in md and "Data confidence" not in md


@pytest.mark.parametrize("lang", ["he", "ar"])
def test_grey_reason_and_upstream_label_are_translated(rep, lang):
    md = report.render_markdown(rep, lang)
    assert Msg("no_data").render(lang) in md or Msg("conf.grey", level=Msg("level.GREY"), why=Msg("no_data")).render(lang) in md
    assert Msg("no_data").render("en") not in md
    eilat = plant(rep, "eilat")
    assert "upstream signal" not in md and i18n.display_name(lang, "tiran", "") in md and "tiran" not in md
    assert eilat.lifted_by  # the structured fact the localised label is built from
    label = Msg("label.upstream", level=Msg("level.ORANGE"), by=[Msg("sentinel.by", id=i18n.Id("tiran"), mult="1.5")],
                id=i18n.Id("eilat"), own=Msg("levelword.YELLOW")).render(lang)
    assert label in md


@pytest.mark.parametrize("lang", ["he", "ar"])
def test_shared_pixel_flag_is_translated(rep, lang):
    md = report.render_markdown(rep, lang)
    assert "shares the same satellite pixels" not in md
    assert Msg("shared.line", ids=[i18n.Id("sorek_b")]).render(lang) in md


def test_localised_label_keeps_the_english_label_on_the_model(rep):
    assert plant(rep, "eilat").label == "ORANGE (upstream signal: tiran ≥ 1.5× P90; eilat itself is yellow)"


def test_png_labels_stay_english_in_every_language(rep, tmp_path):
    sizes = {}
    for lang in LANGS:
        files, _ = report.write_report(rep, tmp_path / lang, ["png"], lang=lang)
        sizes[lang] = files["png"].read_bytes()
    assert sizes["he"] == sizes["en"] == sizes["ar"]


def test_write_report_writes_txt_and_the_language_choice(rep, tmp_path):
    files, notes = report.write_report(rep, tmp_path, ["html", "md", "txt"], lang="he")
    assert sorted(p.name for p in files.values()) == ["dbw-report-2026-08-25.html", "dbw-report-2026-08-25.md",
                                                       "dbw-report-2026-08-25.txt"]
    assert 'lang="he"' in files["html"].read_text(encoding="utf-8")
    assert HEBREW.search(files["txt"].read_text(encoding="utf-8"))


# --- the short message ---------------------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_every_plant_gets_exactly_two_sentences(rep8, lang):
    body = plant_paragraphs(rep8, report.render_text(rep8, lang))
    assert len(body) == 8
    for p in body:
        assert len(sentences(p)) == 2, p


@pytest.mark.parametrize("lang", LANGS)
def test_short_message_is_plain_text_under_the_telegram_cap(rep8, lang):
    text = report.render_text(rep8, lang)
    assert not MARKDOWN_SYNTAX.search(text)
    assert len(text) < 3500, len(text)


@pytest.mark.parametrize("lang", LANGS)
def test_plants_come_worst_first(rep8, lang):
    text = report.render_text(rep8, lang)
    names = [i18n.display_name(lang, p.id, p.name) for p in rep8.plants]
    at = [text.index(n) for n in names]
    assert at == sorted(at)
    assert rep8.plants[0].id == "ashkelon" and names[0] in plant_paragraphs(rep8, text)[0]


@pytest.mark.parametrize("lang", LANGS)
def test_header_and_closing_line(rep8, lang):
    parts = paragraphs(report.render_text(rep8, lang))
    assert parts[0].strip(report.RLM) == "Desal Bloom Watch 2026-08-25"  # no level in the header
    assert "\n" not in parts[0] and "\n" not in parts[-1]
    assert "dbw-report-2026-08-25.html" in parts[-1]


@pytest.mark.parametrize("lang", LANGS)
def test_grey_plant_says_why_and_is_never_a_green(rep8, lang):
    para = next(p for p in plant_paragraphs(rep8, report.render_text(rep8, lang))
                if i18n.display_name(lang, "palmachim", "Palmachim") in p)
    assert Msg("level.GREY").render(lang) in para
    assert Msg("cause.no_data").render(lang) in para
    assert Msg("short.s2.grey_none").render(lang) in para
    assert report.EMOJI[Level.GREEN] not in para
    assert Msg("level.GREEN").render(lang) not in re.split(r"[.!?؟](?=\s)", para)[0]  # the level slot, not "not a green"


@pytest.mark.parametrize("lang", LANGS)
def test_upstream_lift_says_so(rep8, lang):
    para = next(p for p in plant_paragraphs(rep8, report.render_text(rep8, lang))
                if i18n.display_name(lang, "eilat", plant(rep8, "eilat").name) in p)
    assert i18n.display_name(lang, "tiran", "tiran") in para and Msg("levelword.YELLOW").render(lang) in para
    assert Msg("level.ORANGE").render(lang) in para
    assert Msg("cause.p90").render(lang) not in para  # the plant's own pixels are not the reason


@pytest.mark.parametrize("lang", LANGS)
def test_second_sentence_gives_the_value_one_threshold_and_the_data_date(rep8, lang):
    para = next(p for p in plant_paragraphs(rep8, report.render_text(rep8, lang))
                if i18n.display_name(lang, "ashkelon", "Ashkelon") in p)
    second = re.split(r"(?<=[.!?؟])\s+", para)[-1].replace(i18n.FSI, "").replace(i18n.PDI, "")
    assert "9 mg/m³" in second and i18n.short_date(lang, EVENT, EVENT) in second
    thresholds = re.findall(r"P(?:50|75|90|97)\b", second)
    assert len(thresholds) == 1, second  # one threshold, not the whole ladder
    assert "DINEOF" not in second


def test_english_short_message_reads_as_plain_words(rep8):
    parts = paragraphs(report.render_text(rep8, "en"))
    assert parts[0] == "Desal Bloom Watch 2026-08-25"
    first = plant_paragraphs(rep8, report.render_text(rep8, "en"))[0]
    assert first.startswith("\U0001F534 Ashkelon is RED: ") and "seasonal median" in first
    assert not re.search(r"\n", first)


ISOLATES = "".join(chr(c) for c in range(0x2066, 0x206A))  # LRI RLI FSI PDI: some chat clients show them as boxes


@pytest.mark.parametrize("lang", LANGS)
def test_text_has_no_bidi_isolates_in_any_language(rep8, lang):
    assert not set(report.render_text(rep8, lang)) & set(ISOLATES)


@pytest.mark.parametrize("lang", ["he", "ar"])
def test_rtl_text_marks_only_lines_that_start_or_end_with_latin_or_digits(rep8, lang):
    text = report.render_text(rep8, lang)
    for line in filter(None, text.split("\n")):
        word = [c for c in line if c.isalnum()]
        assert line.startswith(report.RLM) == word[0].isascii(), line
        assert line.endswith(report.RLM) == word[-1].isascii(), line
    assert report.RLM in text and "\u200e" not in text
    assert report.RLM not in report.render_text(rep8, "en")


def test_attribution_keys_match_the_provider_sentences():
    en = i18n.load("en")["strings"]
    assert en["attr.noaa"] == noaa_erddap.ATTRIBUTION and en["attr.gibs"] == gibs.ATTRIBUTION
    assert en["attr.coast"] == report.MAP_CREDIT and en["disclaimer"] == report.DISCLAIMER
