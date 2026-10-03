# Reading the report

The report has three layers, top to bottom. Nothing is dropped between layers; the technical numbers are only moved down.

1. **Plain layer** – a summary (which plants could not be judged, how fresh the satellite data is, what changed since yesterday) and one card per plant, worst first. No technical term appears here: no pixel counts, percentiles, dataset names, "sentinel" or "fallback" (`tests/test_readable.py` enforces this in English, Hebrew and Arabic).
2. **Technical details** – the table, the data dates and the per-plant fact blocks and reason lines, as before.
3. **How to read this report** – colour key, terms, limits and sources with public addresses, then the footer (attributions and disclaimer).

The report describes what the numbers mean. It never tells the plant what to do.

## The card

| Row | Source |
|---|---|
| Badge and level word | `PlantReport.level` (the upstream label stays in the technical layer) |
| What it means | one sentence from the scorer's reason codes (`report._what`) |
| Compared with normal for this time of year | `report.band`, below |
| How sure | `report.how_sure`, below |
| Upstream monitoring points | the plant's upstream boxes: how many sit above their own usual high |
| Shared satellite squares | only when two plants read exactly the same satellite squares |

### Compared with normal

The value is placed against the same seasonal percentiles the scorer used. No new threshold is introduced; each band names the one mark it rests on.

| Band | Rule | Mark shown in brackets |
|---|---|---|
| far above normal | value ≥ `RED_MULT` × P50 and ≥ P90 (the red rule) | how many times P50 it is, and P50 |
| very high | ≥ P97 | P97 |
| high | ≥ P90 | P90 |
| above normal | ≥ P75 | P75 |
| normal | below P75 | P75 (where "above normal" starts) |

### How sure

Three words. The rule lives in `report.how_sure` and is deliberately simple:

- **Good** – the level rests on the sharp 4 km satellite, the clear view is at most `GOOD_MAX_AGE` (2 days) old, and it covers more than `GOOD_MIN_SHARE` (half) of the plant's area.
- **Limited** – any other level: only half or less of the area was clear, the view is 3 days old, or only the smoothed 9 km satellite was available. Capping the smoothed satellite at Limited is a judgement call, not a scoring rule: it fills gaps from neighbouring days and places, so it is less direct evidence.
- **Low** – the level is grey (no usable view). Grey is never an all-clear.

These words do not change any level. They only say how far to lean on it.

### Changed since yesterday

Listed as `Plant YESTERDAY → TODAY`. When the level moved **and** the satellite the level rests on changed between yesterday and today (sharp 4 km ↔ smoothed 9 km), the line says so: *(satellite changed from sharp 4 km to smoothed 9 km; the two days are not directly comparable)*. The rule is `report.source_switched`. A grey on either side is no comparison, so no label. This only labels; it never alters a level.

The short `.txt` message carries the same note as one line under its header, only on a day when a level changed: `Changed since yesterday: Ashdod RED → GREEN (satellite changed; not directly comparable)`. Without a satellite switch the bracket is left out; with no change there is no line. Same rule, shorter words (`short.change*` in `dbw/locales/*.json`).

## Colour key

The appendix's colour key mirrors `docs/scoring.md`: green is below the usual high and not climbing; yellow is at or above P90, or above P75 and rising for 3 days; orange is at or above P97, or a yellow plant with an upstream point at 1.5 × its own P90; red is 3 × P50 and ≥ P90, or orange two days running; grey is no usable view (older than 3 days, under a quarter of the area visible, or too little history). The wording is in `dbw/locales/*.json` under `app.*`; see `docs/translations.md`.
