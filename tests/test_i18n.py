"""Locale files: same keys and same placeholders in every language; Msg words one reason in any language."""
import copy
import re
from string import Formatter

import pytest

from dbw import i18n, registry
from dbw.score import Level

LANGS = ("en", "he", "ar")


def fields(template):
    return sorted({name for _, name, _, _ in Formatter().parse(template) if name is not None})


def test_the_three_languages_are_registered_and_load():
    assert i18n.LANGUAGES == LANGS and i18n.DEFAULT == "en"
    for lang in LANGS:
        assert set(i18n.load(lang)) == {"meta", "strings", "names"}


PLURAL = (".one", ".two")  # a language may word 1 or 2 days apart on its own; English keeps the base text


def test_every_language_has_exactly_the_english_keys():
    en = set(i18n.load("en")["strings"])
    for lang in LANGS[1:]:
        have = set(i18n.load(lang)["strings"])
        assert not en - have, f"{lang} is missing {sorted(en - have)}"
        extra = {k for k in have - en if not (k.endswith(PLURAL) and k.rsplit(".", 1)[0] in en)}
        assert not extra, f"{lang} has keys English lacks: {sorted(extra)}"


def test_every_language_uses_the_same_placeholders_per_key():
    en = i18n.load("en")["strings"]
    for lang in LANGS[1:]:
        for key, template in i18n.load(lang)["strings"].items():
            base = key.rsplit(".", 1)[0] if key.endswith(PLURAL) and key not in en else key
            want = fields(en[base])
            # "one day" / "two days" may be worded without the number; nothing else may differ
            assert fields(template) in (want, [f for f in want if f != "age"]), f"{lang}:{key} {fields(template)} != {want}"


def test_meta_has_a_name_and_a_direction_in_every_language():
    assert {l: i18n.load(l)["meta"]["dir"] for l in LANGS} == {"en": "ltr", "he": "rtl", "ar": "rtl"}
    assert [i18n.load(l)["meta"]["name"] for l in LANGS] == ["English", "עברית", "العربية"]


def test_no_template_is_empty_and_digits_stay_western():
    for lang in LANGS:
        for key, template in i18n.load(lang)["strings"].items():
            assert template.strip(), f"{lang}:{key} is empty"
            assert not re.search("[٠-٩۰-۹]", template), f"{lang}:{key} has non-Western digits"


def test_every_level_has_a_word_in_both_cases_of_use():
    for lang in LANGS:
        s = i18n.load(lang)["strings"]
        for lv in Level:
            assert f"level.{lv.name}" in s and f"levelword.{lv.name}" in s


def test_display_names_are_keyed_by_plant_id_and_cover_every_plant():
    plants = {b.id for b in registry.load()}  # plants and the upstream sentinel boxes
    assert i18n.load("en")["names"] == {}  # English falls back to plants.yaml and the bare id
    for lang in LANGS[1:]:
        assert set(i18n.load(lang)["names"]) == plants


def test_msg_is_its_english_text_and_renders_in_other_languages():
    m = i18n.Msg("sentinel.none", id="tiran")
    assert m == "sentinel tiran: no data" and isinstance(m, str)
    assert m.render("en") == "sentinel tiran: no data"
    he = m.render("he")
    assert he != str(m) and i18n.FSI + "tiran" + i18n.PDI in he


def test_msg_nested_in_msg_is_worded_in_the_target_language_once():
    inner = i18n.Msg("sentinel.none", id="tiran")
    outer = i18n.Msg("fallback", reason=inner)
    assert outer == "fallback: N20 sentinel tiran: no data"
    assert outer.render("ar") == i18n.Msg("fallback", reason=inner).render("ar")
    assert inner.render("ar") in outer.render("ar") and i18n.FSI + inner.render("ar") not in outer.render("ar")


def test_english_has_no_bidi_marks():
    out = i18n.Msg("sentinel.none", id="tiran").render("en")
    assert i18n.FSI not in out and i18n.PDI not in out


def test_msg_survives_copy():
    m = i18n.Msg("sentinel.none", id="tiran")
    c = copy.deepcopy(m)
    assert c == m and c.code == m.code and c.params == m.params


def test_unknown_language_is_an_error():
    with pytest.raises(ValueError):
        i18n.load("fr")
