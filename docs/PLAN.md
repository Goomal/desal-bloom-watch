# Desal Bloom Watch — plan (rev 2, 2026-10-01)

Daily algae-risk report for seawater desalination intakes in Israel (Mediterranean + Gulf of
Eilat). The engineer picks plants in a settings file. Every day the tool sends a full report
for those plants through the channels the engineer picked.

Personal project of Shay Levite, not employer property. Built on a Mac, published as a public
repo, installable as a Claude Code skill. Built one phase at a time, with an operator review
before each phase.

Background: the September 2026 algae event on the Israeli Mediterranean coast, when several
desalination plants had to cut production.

**Hard rule: no employer or client project information anywhere in this repo** (code,
registry, docs, tests, commit history). Public sources only. Every plant fact needs a public
source URL.

## 1. What the user gets

```yaml
# config.yaml  (engineer edits this, or the skill's setup wizard writes it)
plants: [eilat, ashkelon, sorek_b]          # ids from plants.yaml
report:
  time: "07:00"                            # local time of the machine that runs it
  language: en                             # en | he | ar
channels:                                  # enable any combination
  email:    { enabled: true,  to: [ops@example.com] }
  telegram: { enabled: false, chat_id: "" }
  slack:    { enabled: false, webhook: "" }
  webhook:  { enabled: false, url: "" }    # generic JSON POST (Teams, n8n, SCADA bridge)
  folder:   { enabled: true,  path: ~/reports }   # md + html + png + txt, e.g. a notes folder
runner: launchd                            # launchd | cron | schtasks | github-actions
```

Secrets (SMTP password, bot token, webhook URLs) never go in `config.yaml`. They go in `.env`
locally, or in GitHub Actions secrets.

**Daily report, every day, not only on alarm:**
- Header: worst level across the chosen plants, and what changed since yesterday.
- Per plant: traffic light, chlorophyll today vs its own seasonal normal (percentile), 3-day
  trend, SST, upstream sentinel status, data confidence (cloud / pixel count, data age), and
  what the level means for that plant's pretreatment type.
- Map: regional chlorophyll image with the chosen plants marked.
- 30-day sparkline per plant.
- Sources and data timestamps at the bottom.
- Subject line carries the level, e.g. `[ORANGE] Desal Bloom Watch 2026-10-02 — Ashkelon`.

## 2. Plant registry (`plants.yaml`, ships with the repo)

Every Israeli seawater desal plant, plus upstream "sentinel" points that are not plants.

| id | Plant | Sea | Notes |
|---|---|---|---|
| hadera | Hadera | Med | |
| sorek_a / sorek_b | Sorek A, Sorek B | Med | |
| palmachim | Palmachim | Med | |
| ashdod | Ashdod (Mekorot) | Med | |
| ashkelon | Ashkelon | Med | |
| western_galilee | Western Galilee | Med | under construction |
| eilat | Eilat seawater desal (Mekorot) | Red Sea | public data only |
| *sentinels* | Port Said, El-Arish, Rafah (Med); Tiran, mid-Gulf (Eilat) | | upstream early warning |

Each entry: onshore location, **intake box** (offshore polygon around the intake head),
intake depth and distance if public, pretreatment type (DAF / UF / MMF), upstream sentinels,
source of every field. Fields with no public source stay empty (`null`). The engineer can
override them in a private `plants.local.yaml` that is never committed.

`plants.local.yaml` is in `.gitignore`. The public registry holds public-source facts only.

## 3. Data sources

**Core (no signup, verified 2026-10-01 from this Mac):**

| Source | What | Res. | Lag |
|---|---|---|---|
| NOAA CoastWatch ERDDAP `noaacwN20VIIRSchlaDaily` | Chl-a, VIIRS NOAA-20 | 4 km | ~2 d |
| ERDDAP `noaacwNPPVIIRSchlaDaily` | Chl-a, VIIRS S-NPP (second pass) | 4 km | ~4 d |
| ERDDAP `noaacwNPPN20VIIRSDINEOFDaily` | Chl-a gap-filled (no cloud holes) | 9 km | ~2 d |
| ERDDAP `noaacwN20VIIRSchlanomratDaily` | Chl-a anomaly ratio | 2 km | ~3 d |
| NASA GIBS snapshot | Chl-a / true-colour map image | — | ~1 d |

Sample pull, northern Gulf of Eilat 20–23 Sep 2026: 0.008–0.20 mg/m³ (4 km),
0.17–0.24 (gap-filled). Med intakes on 3–5 Sep 2026: 4–6 mg/m³ south, 0.47 Hadera
(research notes). That's one to two orders of magnitude between seas, so every alarm compares each plant to
**its own seasonal history**, never to a fixed number.

**To verify in Phase 0:** ERDDAP Sentinel-3 OLCI 300 m sectors (intake-scale, needed for the
narrow Eilat gulf), SST (CoralTemp/OISST on ERDDAP), wind and dust (Open-Meteo, no key).

**Israeli official sources (MoEP-funded):**
MoEP doesn't publish a daily feed itself. It funds and sets the National Monitoring Programs,
run by IOLR (Med) and IUI (Eilat), and it sets each plant's marine-monitoring permit.

| Source | What's there | Role in the tool | Status 2026-10-01 |
|---|---|---|---|
| IOLR / ISRAMAR Hadera station (2.3 km offshore) | fluorescence (chlorophyll), turbidity, T, S, O₂ | in-situ check next to Hadera intake | page live, but its plot was last updated **Dec 2025** |
| ISRAMAR Ashkelon station (2012) | same sensors | in-situ next to Ashkelon | "temporarily not accessible" |
| ISRAMAR Time-Series download (HaderaCTD, AshkelonCTD, Gulf of Eilat DB) | historical in-situ | calibrate satellite vs in-water | to test |
| ISRAMAR Israel-shelf currents forecast | currents, T, S | future: "patch reaches intake in N days" | to test |
| IUI Eilat National Monitoring Program, "available data" | Gulf of Eilat profiles incl. chlorophyll | calibration, Eilat seasonal baseline | site moved, old link 404, new page exists |
| MoEP gov.il freedom-of-information PDFs | per-site marine monitoring reports | per-plant reference values, read once | to collect |

Design consequence: the satellite is the daily driver. Israeli in-situ data is (a) a
calibration layer and (b) a live "second opinion" plugin that turns itself on when a station
publishes fresh data and drops out cleanly when it doesn't.

**Optional: Copernicus Marine.** EU satellite service with a sharper Med product (300 m,
history back to 1998). Free, but each user must register and put a username/password in
`.env`. So it's an optional plugin. The core works without it.

## 4. Risk model (deterministic, no LLM)

Per plant, per day:
1. Chl-a in intake box vs that box's seasonal percentiles (history 2020-05-05→now, the start of the gap-filled DINEOF record; see `docs/sources.md`).
2. 3-day trend.
3. Spatial extent: share of valid pixels above the box's P90.
4. Upstream sentinels: is a sentinel already high? (Med: Nile plume moves north along the coast.)
5. SST + anomaly (warm-water picocyanobacteria favour >26 °C, Uysal 2006).
6. Data confidence: gap or cloud days are reported as **grey / no data**, never green.

| Level | Draft rule (tuned in Phase 2) |
|---|---|
| green | < P75 |
| yellow | ≥ P90, or rising 3 d above P75 |
| orange | ≥ P97, or yellow + upstream sentinel ≥ P90 |
| red | ≥ 3× seasonal median, or orange 2 days running |

What each level means depends on the plant's pretreatment type (DAF plants have more margin
than MMF-only). The text comes from `plants.yaml`, the engineer can edit it locally.

**Acceptance test:** a hindcast of 20 Aug–10 Sep 2026 must show Ashkelon/Ashdod/Sorek at
orange+ before 30 Aug, and Hadera lower. If not, the rules are wrong.
Result (2026-10-01): the original clause fails on real data (Hadera itself went orange from 2 Sep). A
revised clause was approved and passes: Ashkelon and at least one of Ashdod/Sorek orange+ before 30 Aug,
Hadera below orange before 30 Aug. Both verdicts are in `docs/scoring.md` and `tests/test_hindcast.py`.

## 5. Architecture

```
desal_bloom_watch/
  plants.yaml            public registry (sourced)
  config.example.yaml    copy to config.yaml
  .env.example           secrets template
  dbw/providers/         noaa_erddap.py, gibs.py, openmeteo.py, isramar.py, copernicus.py (opt)
  dbw/store.py           SQLite: obs(date, source, box, stat, value)
  dbw/climatology.py     backfill + seasonal percentiles per box
  dbw/data/percentiles.json  bundled percentile export, so a fresh setup skips the 6-year backfill
  dbw/score.py           levels + reasons (pure, unit-tested)
  dbw/report.py          HTML email + markdown + PNG map
  dbw/channels/          email.py, telegram.py, slack.py, webhook.py, folder.py
  dbw/cli.py             dbw setup | backfill | run | send-test | doctor
  runners/               launchd plist, cron line, .github/workflows/daily.yml
  skill/SKILL.md         Claude Code skill
  tests/                 fixtures = real ERDDAP CSV, hindcast test
```

**Claude Code skill:** setup wizard (pick plants, channels, runner, write config, `send-test`),
run on demand, explain a report, add a plant. The daily run is plain Python. No Claude needed,
no token cost, so it also works for engineers without Claude.

## 6. Phases (console legs)

| # | Leg | Done when |
|---|---|---|
| 0 | **Sources + registry.** Test OLCI 300 m, SST, Open-Meteo, ISRAMAR time-series download, IUI data page, MoEP PDFs. Intake boxes for every plant (OSM, public EIA/permit docs). | `docs/sources.md` with a working URL and sample values per source. `plants.yaml` with a source per field, gaps marked `null` |
| 1 | **Engine.** Repo, venv, providers, store, `dbw run --date`. | Run for all plants writes rows. Re-run doesn't duplicate. Tests pass |
| 2 | **History + scoring.** Backfill 2020-05→now, percentiles, `score.py`. | **Aug 2026 hindcast passes (§4).** Shay reviews the list of past orange/red days for Eilat |
| 3 | **Report + skill.** HTML/md/PNG report, `dbw setup` wizard, `skill/SKILL.md`. | Fresh clone + `/desal-bloom-watch setup` produces a report for 2 chosen plants |
| 4 | **Channels + runners.** All 5 channels, all 4 runners, `send-test`. | Each channel gets a test report. Each runner documented. launchd tested on the Mac |
| 5 | **Mac pilot.** Shay's config, 7 days of daily reports. | 7 reports arrived. Missed days backfilled. Issues fixed |
| 6 | **Publish.** README (EN, HE section), license, CI on GitHub Actions, secret scan + scan for non-public plant data, first release. | **Shay approves before the first push.** Repo public, CI green, install from README works on a clean machine |

## 7. Decisions (made)

1. **Repo:** `desal-bloom-watch` on Shay's personal GitHub.
2. **License:** MIT.
3. **Pilot plants:** Ashdod + Eilat on the Mac pilot; every plant is available.

## 8. Known limits

- Satellites see the top few metres. Open intakes typically draw from ~10–20 m (check per plant). A subsurface
  bloom can slip by. The plant's own chlorophyll/turbidity analyzer stays the real-time alarm.
- ~2-day data lag. This is a watch, not a trip signal.
- 4 km pixels at the narrow Eilat gulf tip are coast-contaminated. 300 m (Phase 0) fixes most of it.
- In-situ IOLR stations are currently stale. The tool must work without them.
- Public tool, not an operational guarantee. The README says so.
