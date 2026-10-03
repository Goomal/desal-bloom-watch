"""Report wording in en / he / ar. A reason or label is a `Msg`: a message code plus its values. It is its own
English text (so it still compares and prints as the plain string it used to be); `render(lang)` words it
from dbw/locales/<lang>.json. Fixed strings kept in the repo: no translation service, no model, no network."""
import json
from functools import lru_cache
from pathlib import Path

LANGUAGES = ("en", "he", "ar")
DEFAULT = "en"
FSI, PDI = "⁨", "⁩"  # Unicode first-strong isolate / pop: keep a number, id or date in reading order inside RTL text
LOCALES = Path(__file__).resolve().parent / "locales"


@lru_cache(maxsize=None)
def load(lang):
    """The parsed locale file: {"meta": {name, dir}, "strings": {key: template}, "names": {plant id: display name}}."""
    if lang not in LANGUAGES:
        raise ValueError(f"language must be one of {', '.join(LANGUAGES)} (got {lang!r})")
    return json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))


def is_rtl(lang):
    return load(lang)["meta"]["dir"] == "rtl"


class Id(str):
    """A plant or sentinel id inside a Msg: it is the id itself in English and in any language with no name for it,
    and the display name (from `names` in the locale file) otherwise."""


def _value(v, lang, loc):
    if isinstance(v, Msg):
        return v.render(lang)
    if isinstance(v, Id) and v in loc["names"]:
        return loc["names"][v]
    if isinstance(v, (list, tuple)):
        return loc["strings"]["sep"].join(_value(x, lang, loc) for x in v)
    return FSI + str(v) + PDI if loc["meta"]["dir"] == "rtl" else str(v)


def _template(strings, code, params):
    """The template for `code`; a language may word a count of 1 or 2 days apart as `<code>.one` / `<code>.two`
    (English has no such keys and keeps the base text)."""
    n = params.get("age")
    if isinstance(n, int):
        for suffix, count in ((".one", 1), (".two", 2)):
            if n == count and code + suffix in strings:
                return strings[code + suffix]
    return strings[code]


def _fill(lang, code, params):
    loc = load(lang)
    return _template(loc["strings"], code, params).format(**{k: _value(v, lang, loc) for k, v in params.items()})


class Msg(str):
    """`Msg("sentinel.none", id="tiran")` is "sentinel tiran: no data"; `.render("he")` is the Hebrew line.
    Values are pre-formatted strings (Western digits, units attached); a Msg value is worded in the same language,
    a list is joined with the language's separator. In RTL languages each plain value sits in a Unicode isolate."""

    def __new__(cls, code, **params):
        self = super().__new__(cls, _fill(DEFAULT, code, params))
        self.code, self.params = code, params
        return self

    def __getnewargs_ex__(self):
        return (self.code,), self.params

    def render(self, lang=DEFAULT):
        return self if lang == DEFAULT else _fill(lang, self.code, self.params)


def display_name(lang, plant_id, fallback):
    """The plant's name in `lang`, else `fallback` (the English name from plants.yaml)."""
    return load(lang)["names"].get(plant_id, fallback)


def short_date(lang, day, ref):
    """'28 Sep' in the language (the year is added when it is not the report's year)."""
    out = f"{day.day} {load(lang)['meta']['months'][day.month - 1]}"
    return out if day.year == ref.year else f"{out} {day.year}"
