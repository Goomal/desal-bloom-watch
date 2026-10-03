"""DBW-3d: the HTML report carries its own map (a file that travels alone must still show it), and no report
format has a "worst level" headline any more (the per-plant badges already say it). Offline."""
import base64
import html
import re

import pytest

from dbw import i18n, report
from test_report import conn, rep  # noqa: F401  (fixtures: the calm-history database and its report)
from test_report_i18n import rep8  # noqa: F401

LANGS = ("en", "he", "ar")
PNG_SIG = b"\x89PNG\r\n\x1a\n"
DATA_SRC = re.compile(r'<img src="data:image/png;base64,([A-Za-z0-9+/=]+)"')
HEADLINE_WORDS = {"en": ("Worst level", "worst level"), "he": ("הרמה הגבוהה ביותר",), "ar": ("أعلى مستوى",)}


# --- the map travels inside the html ---------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_written_html_embeds_the_map_as_a_data_uri_and_has_no_relative_png(rep, tmp_path, lang):
    files, _ = report.write_report(rep, tmp_path, ["html", "png"], lang=lang)
    h = files["html"].read_text(encoding="utf-8")
    found = DATA_SRC.findall(h)
    assert len(found) == 1
    assert base64.b64decode(found[0]).startswith(PNG_SIG)
    assert base64.b64decode(found[0]) == files["png"].read_bytes()  # the very map that is also written beside it
    assert not re.search(r'src="(?!data:)[^"]*"', h)  # no relative (or any other) image source
    assert f'alt="{report._t(lang)("map.alt")}"' in h  # alt text kept
    assert files["png"].exists()


def test_html_without_a_map_has_no_img(rep, tmp_path):
    files, _ = report.write_report(rep, tmp_path, ["html"])
    assert "<img" not in files["html"].read_text(encoding="utf-8")


def test_render_html_embeds_given_png_bytes_and_keeps_the_alt_text(rep):
    png = PNG_SIG + b"fake"
    h = report.render_html(rep, png=png)
    assert f'src="data:image/png;base64,{base64.b64encode(png).decode()}"' in h
    assert f'alt="{report._t(i18n.DEFAULT)("map.alt")}"' in h
    low = h.lower()
    assert "<script" not in low and "<link" not in low and "@import" not in low and "http" not in low


# --- no "worst level" headline anywhere ---------------------------------------------------------------

@pytest.mark.parametrize("lang", LANGS)
def test_no_format_has_the_worst_level_headline(rep8, lang):
    md, h, txt = report.render_markdown(rep8, lang), report.render_html(rep8, lang=lang), report.render_text(rep8, lang)
    for name, text in (("md", md), ("html", h), ("txt", txt)):
        for w in HEADLINE_WORDS[lang]:
            assert w not in text, (name, w)


@pytest.mark.parametrize("lang", LANGS)
def test_technical_section_starts_with_the_changes_text_only(rep8, lang):
    t = report._t(lang)
    tech = report.render_markdown(rep8, lang).partition("## " + t("tech.title"))[2].lstrip("\n")
    assert tech.startswith(report._changes(rep8, t) + "\n\n|")
    h = report.render_html(rep8, lang=lang)
    assert h.partition('id="technical"')[2].partition("<table")[0].rstrip().endswith(
        f'<p style="margin:0 0 12px">{html.escape(report._changes(rep8, t))}</p>')


@pytest.mark.parametrize("lang", LANGS)
def test_txt_header_is_the_title_and_date_only(rep8, lang):
    first = report.render_text(rep8, lang).split("\n\n")[0]
    assert first.strip(report.RLM) == "Desal Bloom Watch 2026-08-25"


def test_png_title_is_title_and_date_only(rep):
    assert report.draw_map(rep).get_suptitle() == "Desal Bloom Watch — 2026-08-25"


def test_summary_keeps_grey_freshness_and_changes_lines(rep8):
    t = report._t("en")
    grey = [p for p in rep8.plants if p.level.name == "GREY"]
    assert grey  # eilat has no data in this fixture history
    names = report._join([report._pname(p, "en") for p in grey], t)
    assert report._summary(rep8, "en", t) == [t("sum.grey", names=names), report._summary(rep8, "en", t)[1],
                                              report._plain_changes(rep8, "en", t)]
    assert report._summary(rep8, "en", t)[1].startswith("Satellite data from")


def test_unused_headline_keys_are_gone_from_every_locale():
    for lang in LANGS:
        keys = i18n.load(lang)["strings"]
        gone = [k for k in keys if k == "headline" or k.startswith(("headline.", "sum.worst", "sum.mean."))]
        assert not gone, (lang, gone)
        assert keys["short.header"].count("{") == 1  # just the date
        assert "{level}" not in keys["short.header"] and "{ids}" not in keys["short.header"]
