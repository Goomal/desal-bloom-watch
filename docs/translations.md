# Translations

The report speaks English, Hebrew (`he`) and Arabic (`ar`). The language is chosen at setup
(`dbw setup --language he`), stored as `report.language` in `config.yaml`, and can be overridden for one
render with `dbw report --language ar`. The same history database renders in any language, with no refetch.

## What is translated

Everything a reader reads in the html, markdown and short text (`.txt`) reports: headings, level words,
reasons, confidence lines, the disclaimer, the data attributions, the basemap fallback note, the upstream-outage
note, and the display names of the plants and of the upstream sentinel boxes (Tiran, Port Said, El-Arish, Rafah,
mid-gulf).

The plain layer (summary, plant cards, "How to read this report" appendix; DBW-3c) is translated in full. Its
keys are prefixed `plain.`, `sum.`, `when.`, `band.`, `sure.`, `up.`, `kind.`, `tech.` and `app.`, plus
`change.switch` and `join.and`. Hebrew uses "פי 4.2" for multiples, "ריבועי לוויין" for satellite squares and
"נקודות ניטור במעלה הזרם" for upstream monitoring points; the sharp and smoothed satellites are "חד של 4 ק״מ" and
"מוחלק של 9 ק״מ". The same terms are banned from the plain layer in every language (`tests/test_readable.py`:
no pixel, percentile, P50-P97, `n=`, DINEOF, N20, VIIRS, sentinel or fallback, and the Hebrew and Arabic words
for them).

## What stays as it is

- Map labels in the PNG (English in every language).
- Numbers (Western digits 0-9), units (`mg/m³`), box ids (`tiran`, `sorek_b`), dataset names (NOAA CoastWatch,
  DINEOF, Natural Earth, NASA GIBS), URLs and licence names.
- The `reason` lines in the database and `dbw run` console output are English.

## Where the strings live

`dbw/locales/en.json`, `he.json`, `ar.json`. Each file has:

- `meta`: `name` (the language in its own script), `dir` (`ltr` or `rtl`) and `months` (twelve short month names,
  for dates like "28 Sep" in the short message).
- `strings`: flat dotted keys (`level.RED`, `short.s1`, `attr.gibs`) mapping to templates with `{placeholders}`.
- `names`: plant and sentinel id to display name. English is empty and falls back to `plants.yaml` and the bare id.

Reasons are built in code as `Msg(code, **values)` (`dbw/i18n.py`). A `Msg` is its own English text, so English
output is byte-identical to the pre-translation report (`tests/test_golden_en.py`), and `.render(lang)` words it
from the locale file. No translation service, no model call, no network.

(English still matches the goldens for the score battery; the English report text itself is regenerated
whenever its layout changes, see `tests/fixtures/golden_en/`.)

Two mechanisms keep English identical while other languages read naturally:

- **Names.** An id inside a message (`Id("tiran")`) is the bare id in English and the entry under `names` in a
  language that has one.
- **Plural suffix.** When a message has an `{age}` of 1 or 2 days, a language may word it with its own key
  `<code>.one` or `<code>.two` (Hebrew "בן יום אחד", "בני יומיים"; the Hebrew dual is a word of its own). English has
  none, so it keeps the base text ("1 days old", which the English goldens contain). `tests/test_i18n.py` allows
  these extra keys and lets them drop the `{age}` placeholder, nothing else.

`tests/test_i18n.py` fails when a language misses a key, has an extra key, changes a placeholder, leaves a
template empty or uses non-Western digits.

## Review status

The Hebrew and Arabic wording (including the whole `app.*` appendix, the `plain.*` cards and the `sure.*` words)
was written by an AI model. Hebrew has been rewritten once for natural Israeli
phrasing (seasonal-median multiples, the age strings, "נקודת ניטור במעלה הזרם" for an upstream sentinel) but no native
speaker has read it end to end: treat it as a draft. **The Arabic has not been reviewed by anyone**, not by a native
speaker and not by a second pass; expect stiff or wrong phrasing, and have an Arabic reader check it before it goes
to people who rely on it. The NASA GIBS acknowledgement is
translated in `attr.gibs`: the English sentence is NASA's requested wording, the he/ar versions are not NASA's.
Corrections are plain edits to the JSON file and need no code change.

## Add a language

1. Copy `dbw/locales/en.json` to `dbw/locales/<code>.json`. Translate every value, keep every `{placeholder}`.
   Set `meta.name` and `meta.dir`. Add a display name per plant id under `names`.
2. Add the code to `LANGUAGES` in `dbw/i18n.py`. The CLI choices, the config check and the setup prompt read it.
3. Add the code to `LANGS` in `tests/test_i18n.py` and `tests/test_report_i18n.py`, run `pytest`. `names` must cover
   every plant and sentinel id and `meta.months` must have twelve entries.
4. For a right-to-left language use `"dir": "rtl"`: html gets `dir="rtl"`, and values inside the text are wrapped
   in Unicode isolates so a number or id keeps its reading order.

## Right to left: best effort

- **HTML** sets `<html lang dir="rtl">`, `direction:rtl` on the body, and wraps each number, unit and id in
  `<bdi>`. It uses inline styles only, no scripts, links or web fonts.
- **Markdown** has no direction control. The file carries the right text and isolate characters, but how a
  viewer lays out a right-to-left line (GitHub, an editor, a mail client) is up to that viewer and has not been
  verified here. Use the html report when layout matters.
- **Plain text (`.txt`)** carries no Unicode isolates (U+2066 to U+2069): some chat clients draw them as boxes.
  Instead each line gets a right-to-left mark (U+200F) only where it would otherwise start or end with a Latin
  letter or a number (the header "Desal Bloom Watch ...", a closing file name, a line ending in "P90 5.11"), which
  keeps the line right-to-left in a viewer that guesses direction from the first and last character. Numbers inside
  a line are left plain. How each chat client lays out a mixed line has not been tested across clients.
- There is no bidi library and no bundled font. The viewer needs Hebrew or Arabic glyphs.
