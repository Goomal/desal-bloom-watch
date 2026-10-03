# Scoring: how a level is made

Deterministic. No LLM, no network, no clock in the rules. `dbw/score.py` is pure functions;
`dbw/assess.py` is the only glue between the SQLite store and those functions. Every level
comes with reason lines, and every threshold is a named constant in `score.py`.

Satellite chlorophyll at the intake box is an **early-warning signal**, not a measurement
inside the plant. Levels say "this box looks unusual for this time of year", nothing more.

How the report words these levels for a reader (the plain cards, "How sure", the source-switch label) is in
`docs/reading-the-report.md`; none of it changes a level.

## 1. Data and history

| Source (ERDDAP id) | Resolution | From | Role |
|---|---|---|---|
| `noaacwN20VIIRSchlaDaily` (N20) | 4 km | 2021-08-26 | primary chlorophyll |
| `noaacwNPPN20VIIRSDINEOFDaily` (DINEOF) | 9 km, gap-filled | 2020-05-05 | fallback chlorophyll + long history |
| `noaacrwsstDaily` (CoralTemp) | 0.05 deg | whole backfill | SST reason line only |

`dbw backfill --from 2020-05-05` fills every plant and sentinel box. It makes one request per
sea, source and ~30-day chunk and cuts the boxes out locally with griddap's nearest-index rule
(a test proves a regional cut equals the box's own query, and a live cross-check of 442 results
had 0 mismatches). Boxes whose bbox edge lies midway between two pixels are asked alone.
It is resumable (a `coverage` table skips answered windows), never overwrites a stored row
without `--force`, halves a request on a 5xx and aborts after 6 failures in a row.

**The real backfill** (2020-05-05 to 2026-09-29, the newest slice ERDDAP had on 2026-10-01; 13 boxes):

| source | (date, box) results | of which with a median |
|---|---|---|
| DINEOF | 22,087 | 22,086 |
| N20 | 21,528 | 12,982 (the rest are all-cloud days, stored as no-data, never as zero) |
| CoralTemp SST | 30,407 | 30,407 |

212,849 + 107,966 + 154,604 obs rows (stat rows, 475,419 in all), no duplicates, 0 failed days.
Wall time about 110 minutes in four resumable runs (48 + 50 + 11 + 1 min). The proxy answered
502/503 in bursts twice; the run aborts after 6 failures in a row by design and the next run
continued from the coverage table. The last run, over everything, made 23 requests (the open-ended
newest chunks only), wrote 0 rows and rebuilt all 39 percentile tables: that is the resume proof.


**DINEOF has a real hole: no slices from 2022-07-06 to 2023-10-11** (read off the dataset's
time axis, not a download failure). A range request inside it returns one snapped slice from
outside the hole, so `backfill` keeps only rows with `from <= date <= to`. Windows with fewer
than 30 samples get no percentile and score grey.

## 2. Seasonal percentiles

Per (source, box): P50 / P75 / P90 / P97 of the box's **daily median chlorophyll**, over a
+-15-day circular window of the day of year, pooled across all years. 365-day calendar (Feb 29
counts as Feb 28). `MIN_N = 30` samples or the slot is `None` and the day is grey. Stored in
the `pctl` table; `dbw backfill` rebuilds it, and it can always be recomputed from `obs`
(`climatology.build_percentiles`). Nothing in `pctl` is hand-entered.

`leave_out` (hindcast, anti-overfit): percentiles are rebuilt in memory **without the scored
day's year**, so the 2026 event is never scored against itself.

## 3. Merging N20 and DINEOF: option (b)

Options were (a) DINEOF only, (b) N20 when usable else DINEOF, (c) one blended series.
**Shipped: (b), mode `n20_else_dineof`** (the default; `--mode dineof` gives (a)). Each source is
scored against **its own** percentiles, never mixed, because the two do not agree.

Overlap days (both sources have a valid box median, N20 with >= 25 % valid pixels):

| box | n overlap | median N20/DINEOF | r (log) | Spearman |
|---|---|---|---|---|
| hadera | 593 | 1.25 | 0.57 | 0.57 |
| sorek_a / sorek_b | 643 | 1.31 | 0.73 | 0.67 |
| palmachim | 625 | 1.57 | 0.72 | 0.66 |
| ashdod | 613 | 1.66 | 0.77 | 0.71 |
| ashkelon | 669 | 0.79 | 0.81 | 0.76 |
| western_galilee | 595 | 1.41 | 0.56 | 0.53 |
| eilat | 616 | 0.78 | 0.65 | 0.75 |
| port_said | 706 | 0.87 | 0.44 | 0.48 |
| el_arish | 695 | 0.85 | 0.62 | 0.59 |
| rafah | 666 | 0.96 | 0.79 | 0.73 |
| tiran | 695 | 0.72 | 0.30 | 0.27 |
| gulf_mid | 716 | 0.77 | 0.71 | 0.81 |

Why not (c): the ratio runs 0.72 to 1.66 and **flips direction by box** (N20 higher at Hadera
to Ashdod, lower at Ashkelon and the Red Sea). No single scale factor exists, and correlation is
only 0.3 to 0.8. A blend would invent a series. Why not (a) alone: in the Aug 2026 hindcast the
two sources date the onset differently and neither is uniformly earlier. N20 is earlier at
Ashkelon (red 25 Aug against orange 29 Aug) and Sorek (orange 28 Aug against 31 Aug), DINEOF is
earlier at Ashdod (30 against 31 Aug) and Palmachim (31 Aug against 02 Sep). Against the 30 Aug
cutoff N20 first misses only Ashdod (by one day); DINEOF only misses Ashdod and Sorek. The 4 km box also fits a 2 km-wide intake area better than a 9 km
smoothed cell. Why the fallback: N20 is cloudy (55 to 64 % of its days pass the coverage test per
box), DINEOF has a value on most days. A fallback day carries the reason line
`fallback: N20 <why grey>`, so the reader knows the level is DINEOF's.

## 4. Rules: PLAN section 4 draft vs shipped

| Level | PLAN draft | Shipped |
|---|---|---|
| grey | gap or cloud, never green | no valid day, newest valid > 3 days old, < 25 % of pixels valid, no percentile for the season, all-NaN day. Never green. |
| green | < P75 | below P90 and not rising. P75 to P90 is green with an "above normal" reason (the draft left that band undefined). |
| yellow | >= P90, or rising 3 d above P75 | same. Rising = >= 2 valid days in the last 3, all >= P75, newest >= 1.15x oldest. |
| orange | >= P97, or yellow + sentinel >= P90 | **>= P97, or yellow + a sentinel >= 1.5x its own P90** |
| red | >= 3x seasonal median, or orange 2 days running | **>= 3x seasonal median AND >= P90**, or orange 2 days running |
| (all levels) | one day's value | **the lower of the newest two valid days (<= 3 days apart)** |

Every change, with the reason:

1. **CONFIRM (two-day check).** A single-day box median can jump from cloud edges, glint or a
   few pixels. A bloom that matters lasts days. The level uses the lower of the newest two valid
   days; the reason line says when the newest value is not yet confirmed. Cost: onset is
   reported about one valid day later. This is the biggest single cut in false alarms.
2. **SENTINEL_MULT = 1.5.** A sentinel at its own P90 is, by definition, true about 10 % of
   days. Requiring 1.5x P90 makes the upgrade mean "upstream is clearly high".
3. **Red needs >= P90 too.** In clean water (Eilat, Gulf) 3x the median is still below P90, so the
   draft would colour ordinary variation red. P90 edge keeps red tied to the box's own tail.
4. **Orange 2 days running** uses the level reported for the previous calendar day; a grey day
   resets it.
5. **Extent** is a reason line, not a level driver: median >= P90 = widespread, day's own P90 >=
   P90 = patchy, else local. (Taken from stored daily stats, no pixel storage.)
6. **SST** is a reason line only: >= 26 C and >= 1 C above the box's seasonal P50 prints "warm water
   favours picocyanobacteria". It moves no level.
7. **Shared pixels** (below) are a reason line only.

Not changed: P97 for orange, 3x for red, 1.15 rising ratio, +-15-day window.

## 5. Plants that look at the same pixels

At runtime `Assessor.shared_with` compares the stored pixel-set signature of each plant box
per source. Sorek A, Sorek B and Palmachim use identical 4 km cells in N20, so Sorek A and B
always have the same level and the reasons say:
`shares the same satellite pixels with sorek_b, palmachim; not independent`.
They are **not merged** and `plants.yaml` is untouched. Two plants agreeing is not two
confirmations.

## 6. Anti-overfit check

Rule: no tuning to the one Aug 2026 event without checking what the rules do on the whole
history. Each cell is **orange-or-red days / red days** scored with the year left out
(`leave_out`), merge mode (b). Right-hand columns: share of scored days at orange+ and at red,
and share of days grey.

Before tuning (PLAN draft: `CONFIRM = False`, `SENTINEL_MULT = 1.0`):

| plant | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | orange+ % | red % | grey % |
|---|---|---|---|---|---|---|---|---|---|---|
| hadera | 16 / 13 | 24 / 16 | 36 / 30 | 33 / 24 | 34 / 31 | 12 / 7 | 41 / 34 | 8.6 | 6.8 | 2 |
| sorek_a | 36 / 32 | 26 / 22 | 41 / 33 | 21 / 13 | 11 / 8 | 28 / 21 | 57 / 52 | 9.7 | 8.0 | 2 |
| sorek_b | 36 / 32 | 26 / 22 | 41 / 33 | 21 / 13 | 11 / 8 | 28 / 21 | 57 / 52 | 9.7 | 8.0 | 2 |
| palmachim | 36 / 32 | 25 / 18 | 36 / 29 | 22 / 13 | 11 / 6 | 28 / 21 | 61 / 56 | 9.7 | 7.7 | 2 |
| ashdod | 43 / 33 | 27 / 22 | 39 / 31 | 12 / 9 | 10 / 7 | 27 / 20 | 69 / 56 | 10.0 | 7.9 | 2 |
| ashkelon | 24 / 18 | 30 / 20 | 38 / 31 | 20 / 16 | 14 / 8 | 27 / 23 | 75 / 68 | 10.1 | 8.2 | 3 |
| western_galilee | 12 / 8 | 19 / 15 | 19 / 12 | 29 / 22 | 91 / 77 | 5 / 2 | 14 / 10 | 8.4 | 6.5 | 2 |
| eilat | 30 / 20 | 66 / 46 | 61 / 54 | 16 / 11 | 3 / 0 | 53 / 37 | 19 / 16 | 11.2 | 8.3 | 4 |

Shipped rules:

| plant | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | orange+ % | red % | grey % |
|---|---|---|---|---|---|---|---|---|---|---|
| hadera | 12 / 10 | 13 / 11 | 16 / 14 | 21 / 18 | 12 / 12 | 8 / 5 | 20 / 16 | 4.5 | 3.8 | 2 |
| sorek_a | 26 / 22 | 10 / 9 | 27 / 24 | 7 / 5 | 3 / 2 | 14 / 10 | 44 / 40 | 5.8 | 4.9 | 2 |
| sorek_b | 26 / 22 | 10 / 9 | 27 / 24 | 7 / 5 | 3 / 2 | 14 / 10 | 44 / 40 | 5.8 | 4.9 | 2 |
| palmachim | 26 / 22 | 9 / 7 | 24 / 22 | 11 / 7 | 2 / 0 | 17 / 12 | 43 / 41 | 5.8 | 4.9 | 2 |
| ashdod | 18 / 14 | 13 / 11 | 22 / 19 | 6 / 5 | 4 / 3 | 17 / 15 | 47 / 41 | 5.6 | 4.8 | 2 |
| ashkelon | 5 / 4 | 13 / 10 | 23 / 18 | 2 / 0 | 2 / 1 | 13 / 11 | 56 / 52 | 5.1 | 4.3 | 3 |
| western_galilee | 8 / 7 | 10 / 7 | 2 / 2 | 17 / 15 | 66 / 56 | 4 / 2 | 2 / 0 | 4.8 | 3.9 | 2 |
| eilat | 6 / 3 | 20 / 13 | 38 / 35 | 4 / 4 | 0 / 0 | 30 / 26 | 14 / 11 | 5.1 | 4.2 | 4 |

Reading it honestly:

- The draft puts every plant at 8 to 11 % orange+ days over six years, which is far above the
  ~3 % that P97 alone gives. A level that is orange one day in ten is noise. The tuning halves it.
- Shipped rules sit at 4.5 to 5.8 %. That is **still at or slightly over the 5 % guard** for
  Sorek, Palmachim, Ashdod, Ashkelon and Eilat. It was not pushed lower because every further cut
  needs a rule that has no physical defence (for example demanding three days of persistence, which
  would delay a real bloom by days) or that is tuned to the Aug 2026 grid.
- The excess is concentrated in a few seasons: 2026 holds 44 to 56 orange+ days at Sorek, Palmachim,
  Ashdod and Ashkelon, which is the event itself, and single seasons stand out elsewhere (Eilat 2022: 38, Eilat 2025: 30,
  Western Galilee 2024: 66). Several years are close to zero (Ashkelon 2020, 2023, 2024: 5, 2, 2 days).
- The 2026 numbers are leave-year-out, so they are not self-scored.
- Nothing here validates the levels against intake events: there is no plant data in this repo.
  The check only shows the rules are not trigger-happy and not tied to one year.

## 7. Hindcast 20 Aug to 10 Sep 2026

`dbw hindcast --from 2026-08-20 --to 2026-09-10` (leave-2026 percentiles, shipped rules):

```
                 20 21 22 23 24 25 26 27 28 29 30 31 01 02 03 04 05 06 07 08 09 10
                 08 08 08 08 08 08 08 08 08 08 08 08 09 09 09 09 09 09 09 09 09 09
hadera            G  G  G  G  G  G  G  G  G  G  G  G  G  O  G  G  G  G  G  O  R  R
sorek_a           G  G  G  G  G  G  G  G  O  R  R  R  R  R  R  R  R  R  R  R  R  R
sorek_b           G  G  G  G  G  G  G  G  O  R  R  R  R  R  R  R  R  R  R  R  R  R
palmachim         G  G  G  G  G  G  G  G  G  G  G  G  G  R  R  R  R  R  R  R  R  R
ashdod            G  G  G  G  G  G  G  G  G  G  G  O  R  R  R  R  R  R  R  R  R  R
ashkelon          G  G  G  G  G  R  R  R  R  R  R  R  R  R  R  R  R  R  R  R  R  R
western_galilee   G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G
eilat             G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G  G
```

### Verdict

**The original PLAN section 4 clause FAILS.** It asked for Ashkelon, Ashdod and a Sorek box at
orange+ before 30 Aug and Hadera lower over the whole window. Two things break it:

- **Ashdod first reaches orange on 31 Aug**, one day after the cutoff. N20 has no valid pixel at
  Ashdod on 29 and 30 Aug (cloud); on 31 Aug it shows 13.9 mg/m3 raw, but the two-day check judges
  the lower of the newest two valid days, 3.72 on 28 Aug (P90 3.58, P97 5.0), so the day scores
  yellow plus a sentinel above 1.5x its P90 = orange. Ashkelon (red 25 Aug) and Sorek A/B (orange
  28 Aug, red 29 Aug) pass.
- **Hadera reaches red on 9 and 10 Sep on real data**: 2.11 mg/m3 against P50 0.53, P90 1.01,
  P97 1.19 (4x the seasonal median), after orange days on 2 Sep (1.36) and 8 Sep (1.23). The clause
  assumes Hadera stays quiet for the whole window; the data say otherwise from 2 Sep.

**The revised clause PASSES, and it is a criterion change, not a pass of the original.** Shay
approved on 2026-10-01: *Ashkelon AND at least one of {Ashdod, any Sorek box} reach orange or red
on at least one day before 2026-08-30, AND Hadera stays below orange on every day before
2026-08-30.* Result: Ashkelon RED (25 Aug), Sorek RED (orange 28 Aug), Hadera GREEN on every day
before 30 Aug. `dbw hindcast` prints both verdicts, and `tests/test_hindcast.py` asserts the
revised clause passes **and** that the original still fails, so nobody can mistake one for the
other. The rules were tuned on the 6-year false-alarm rate (section 6), not on this grid.

The same grid under the untuned PLAN draft (`CONFIRM = False`, `SENTINEL_MULT = 1.0`):

```
hadera            G  G  G  G  G  G  G  G  G  G  G  O  R  R  G  G  G  O  R  R  R  R
sorek_a / _b      G  G  G  G  G  G  G  G  O  R  R  R  R  R  R  R  R  R  R  R  R  R
palmachim         G  G  G  G  G  G  G  G  G  G  G  R  R  R  R  R  R  R  R  R  R  R
ashdod            G  G  G  G  G  G  G  G  O  R  R  R  R  R  R  R  R  R  R  R  R  R
ashkelon          G  G  G  G  G  R  R  R  R  R  R  R  R  R  R  R  R  R  R  R  R  R
eilat             G  G  G  G  G  G  G  Y  G  G  G  G  G  G  G  G  G  G  G  G  G  G
```

The draft lets Ashdod pass (orange 28 Aug) but turns Hadera orange on 31 Aug and red on 1 Sep,
so it fails the original clause too, and it also fails the revised one (Hadera orange before
30 Aug is not allowed). It flags Eilat yellow on 27 Aug. In other words the tuning that brings
the false-alarm rate down also keeps Hadera quiet until 2 Sep, and costs Ashdod one day.

Under DINEOF only (mode (a)) the revised clause fails: Ashkelon orange 29 Aug, Ashdod orange 30 Aug,
Sorek and Palmachim orange 31 Aug, Hadera red from 6 Sep.

The grid is an offline regression test: `tests/test_hindcast.py` with a real-data fixture
(`tests/fixtures/hindcast_2026-08.json`, made by `scripts/export_hindcast_fixture.py`).
It asserts the golden grid and the verdict, so a rule change that moves the grid fails loudly.

## 8. Eilat

`docs/eilat-history-review.md` lists every orange and red day of the whole history for the Gulf
of Aqaba box with level, value against its percentiles and reasons. Eilat chlorophyll is very
low (median about 0.25 mg/m3), so a small absolute rise is a large percentile move; read that
list as "unusual for Eilat", not "bloom".

## 9. Limits

- Six years of history (DINEOF 2020, N20 2021), with a 15-month DINEOF hole. Percentiles of a
  rare event from six summers are rough. P97 of a 31-day window is the top 3 % of roughly 150 to 190 samples, so about 5 values.
- Satellite sees the surface of the box, not the intake depth, and nothing inside the plant.
  Cloud and the 4 km pixel size hide coastal strips; 9 km DINEOF smooths everything.
- Sorek A, Sorek B and Palmachim are one set of pixels (section 5).
- No wind, current or plant data. Upstream sentinels are the only transport signal.
- `*_anomaly` datasets are not used: they are not a substitute for a percentile of the box's own
  history.
- Levels are a signal for a human to look, with the reasons shown. They are not a prediction.
