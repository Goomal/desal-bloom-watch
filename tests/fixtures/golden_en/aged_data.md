# Desal Bloom Watch — 2026-10-02

Satellite data from 29 Sep, 3 days ago

No plant changed level since yesterday.

### Ashkelon — 🔴 RED

- **What it means:** Chlorophyll is 6.6 times the normal for this time of year.
- **Compared with normal for this time of year:** far above normal, 9.53 mg/m³ (6.6 times the usual middle of 1.44)
- **How sure:** Limited: smoothed satellite (gaps are filled in), data 3 days ago
- **Upstream monitoring points:** 2 of 3 above their usual high (El-Arish, Rafah)

### Hadera — 🟢 GREEN

- **What it means:** Chlorophyll is within the normal range for this time of year.
- **Compared with normal for this time of year:** normal, 0.367 mg/m³ (above normal starts at 0.445)
- **How sure:** Limited: smoothed satellite (gaps are filled in), data 3 days ago
- **Upstream monitoring points:** 2 of 3 above their usual high (El-Arish, Rafah)

## Technical details

No plant changed level since yesterday.

| Plant | Level | Chlorophyll | Data |
|---|---|---|---|
| Ashkelon | 🔴 RED | 9.53 mg/m³ (>=P90) | DINEOF 9 km gap-filled, data of 2026-09-29 |
| Hadera | 🟢 GREEN | 0.367 mg/m³ (>=P50) | DINEOF 9 km gap-filled, data of 2026-09-29 |

**Data dates**

- N20 VIIRS 4 km: 2026-09-29 (3 days before the report date)
- DINEOF 9 km gap-filled: 2026-09-30 (2 days before the report date)
- CoralTemp SST: 2026-09-30 (2 days before the report date)

### Ashkelon — 🔴 RED

- **Chlorophyll:** 9.53 mg/m³, >=P90 of its own seasonal normal (P50 1.44 · P75 2.91 · P90 8.25 · P97 9.56, n=121)
- **Source:** DINEOF 9 km gap-filled, data of 2026-09-29
- **Data confidence:** 1/1 pixels valid (100%) on 2026-09-29, 3 days old
- **SST:** 28.7 °C, -0.1 °C vs seasonal normal
- **Upstream sentinels:** port_said: 3.35 mg/m³ (P90 3.5; below P90); el_arish: 3.1 mg/m³ (P90 2.21; above P90); rafah: 6.42 mg/m³ (P90 5.28; above P90)
- **Why:**
  - fallback: N20 stale: newest valid observation is 4 days old (2026-09-28), limit 3
  - chl 9.53 mg/m3 is >=P90 of this box's own seasonal normal (P50 1.44, P75 2.91, P90 8.25, P97 9.56; n=121)
  - newest value 9.6 is not yet confirmed by the previous valid day (9.53, 1 d apart); judged at 9.53
  - value is 6.6x the seasonal median (red at 3x)
  - extent: at least half of the box is above its P90
  - sentinel port_said: 3.35, below its P90 3.5
  - sentinel el_arish: 3.1 >= its P90 2.21 (upstream is high)
  - sentinel rafah: 6.42 >= its P90 5.28 (upstream is high)
  - SST 28.7 C, -0.1 C vs normal
  - data: 1/1 pixels valid on 2026-09-29 (3 days old)

### Hadera — 🟢 GREEN

- **Chlorophyll:** 0.367 mg/m³, >=P50 of its own seasonal normal (P50 0.31 · P75 0.445 · P90 0.684 · P97 0.766, n=121)
- **Source:** DINEOF 9 km gap-filled, data of 2026-09-29
- **Data confidence:** 1/1 pixels valid (100%) on 2026-09-29, 3 days old
- **SST:** 28.5 °C, +0.2 °C vs seasonal normal
- **Upstream sentinels:** port_said: 3.35 mg/m³ (P90 3.5; below P90); el_arish: 3.1 mg/m³ (P90 2.21; above P90); rafah: 6.42 mg/m³ (P90 5.28; above P90)
- **Why:**
  - fallback: N20 stale: newest valid observation is 5 days old (2026-09-27), limit 3
  - chl 0.367 mg/m3 is >=P50 of this box's own seasonal normal (P50 0.31, P75 0.445, P90 0.684, P97 0.766; n=121)
  - sentinel port_said: 3.35, below its P90 3.5
  - sentinel el_arish: 3.1 >= its P90 2.21 (upstream is high)
  - sentinel rafah: 6.42 >= its P90 5.28 (upstream is high)
  - SST 28.5 C, +0.2 C vs normal
  - data: 1/1 pixels valid on 2026-09-29 (3 days old)

## How to read this report

This page explains the colours and the terms used in this report. It describes what the numbers mean; it does not tell anyone what to do.

### Colour key

A level is judged on the lower of the two newest clear satellite days, so one odd day cannot move it.

- 🟢 **GREEN** — Looks normal for the season. Chlorophyll is below the usual high for this time of year and is not climbing.
- 🟡 **YELLOW** — Higher than usual. Chlorophyll is at or above the usual high for this time of year (the top 1 in 10 of past values), or it is above normal and has been rising for 3 days.
- 🟠 **ORANGE** — Clearly unusual. Chlorophyll is at or above the very high mark for this time of year (the top 3 in 100), or a yellow plant has an upstream monitoring point at least 1.5 times its own usual high (an upstream signal).
- 🔴 **RED** — Far outside the normal range, or unusual again after an unusual day. Chlorophyll is at least 3 times the normal for this time of year and at or above the usual high, or the plant was orange or red yesterday and is orange again today (two days running).
- ⚪ **GREY** — No level can be given. Grey is never an all-clear. There was no clear satellite view in the last 3 days, less than a quarter of the area was visible, or there is not enough past data for this time of year.

### Terms

- **Chlorophyll-a:** A green pigment in algae. Satellites measure it as a sign of how much algae there is in the surface water.
- **mg/m³:** Milligrams of chlorophyll-a in one cubic metre of seawater. The higher the number, the more algae.
- **Normal for this time of year:** The comparison is with the same time of year since 2020, in the same area and from the same satellite. Normal: not in the top quarter of past values. Above normal: the top quarter. High: the top 1 in 10. Very high: the top 3 in 100. Far above normal: at least 3 times the usual middle. The technical details give the exact marks (the 50th, 75th, 90th and 97th percentiles).
- **The two satellites:** The sharp satellite sees the sea in 4 km squares and gives the most detailed view, but cloud often blocks it. The smoothed satellite uses 9 km squares and fills the gaps from neighbouring days and places, so it almost always has a value but shows fewer small patches. The report uses the sharp one when it has a recent clear view and the smoothed one otherwise. Because they see the sea differently, a level can change on the day the report switches from one to the other even though the water did not change; the report says so when that happens.
- **How sure:** Good: a clear view of more than half of the area, at most 2 days old, from the sharp satellite. Limited: only part of the area was clear, the view is 3 days old, or only the smoothed satellite was available. Low: no level could be given.
- **Upstream monitoring points:** Places along the coast (Port Said, El-Arish and Rafah for the Mediterranean plants; the Strait of Tiran and mid-gulf for Eilat) where algae can show up before they reach the intake. A plant's level can be raised when such a point is far above its own usual high.
- **Shared satellite squares:** Two plants whose areas fall on exactly the same satellite squares get exactly the same readings, so they are not two independent confirmations.
- **The delay of about 2 days:** Satellite data arrive about 2 days after the pass, so the newest view is usually from 2 days ago, not from today.
- **Sea surface temperature (SST):** Shown in the technical details only; it never changes a level. Warm water (26 °C or more and at least 1 °C above normal) favours very small algae called picocyanobacteria.

### Limits

- The satellite sees only the top few metres of the sea.
- Cloud, dust and sun glare hide the sea or distort the reading.
- Squares near the shore are less reliable.
- A satellite square is bigger than an intake, so a patch next to the intake can be missed or averaged away.
- "Normal" rests on only about six years of history.
- This is an early warning, not a measurement at the intake.
- The plant's own online analysers remain the real-time alarm.

### Where the numbers come from

- Sharp satellite chlorophyll-a (NOAA, the VIIRS sensor on the NOAA-20 satellite, 4 km): coastwatch.noaa.gov/erddap/griddap/noaacwN20VIIRSchlaDaily.html
- Smoothed satellite chlorophyll-a (NOAA, gaps filled with the DINEOF method, 9 km): coastwatch.noaa.gov/erddap/griddap/noaacwNPPN20VIIRSDINEOFDaily.html
- Sea surface temperature (NOAA Coral Reef Watch, CoralTemp): coastwatch.noaa.gov/erddap/griddap/noaacrwsstDaily.html
- Coastline on the map (Natural Earth, public domain): naturalearthdata.com
- The exact rules, marks and the reasons for them are in docs/scoring.md and docs/reading-the-report.md in the project.

---

**Sources**

- Data: NOAA CoastWatch (public domain, US government data). SST: NOAA Coral Reef Watch CoralTemp; licence text carries an OSTIA academic-research clause, so use is research use only.
- Coastline: Natural Earth (public domain), naturalearthdata.com.

*Desal Bloom Watch is a satellite-based early-warning aid. It is not an operational decision tool and not a measurement at the intake: satellites see the top few metres, data lag about two days, and your own on-line analysers remain the real-time alarm.*
