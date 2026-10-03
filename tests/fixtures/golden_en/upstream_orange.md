# Desal Bloom Watch — 2026-08-27

Satellite data from 27 Aug, today

Changed since yesterday: Ashkelon GREEN → ORANGE.

### Ashkelon — 🟠 ORANGE

- **What it means:** The level is raised because upstream monitoring points (Rafah) are far above their usual high. On its own satellite squares this plant would be yellow.
- **Compared with normal for this time of year:** above normal, 4.56 mg/m³ (the top quarter starts at 2.65)
- **How sure:** Good: clear view today (sharp satellite)
- **Upstream monitoring points:** 2 of 3 above their usual high (El-Arish, Rafah)

### Eilat seawater desalination (Mekorot) — 🟢 GREEN

- **What it means:** Chlorophyll is within the normal range for this time of year.
- **Compared with normal for this time of year:** normal, 0.0756 mg/m³ (above normal starts at 0.14)
- **How sure:** Good: clear view today (sharp satellite)
- **Upstream monitoring points:** none of 2 above their usual high

## Technical details

Changed since yesterday: ashkelon GREEN → ORANGE.

| Plant | Level | Chlorophyll | Data |
|---|---|---|---|
| Ashkelon | 🟠 ORANGE (upstream signal: rafah ≥ 1.5× P90; ashkelon itself is yellow) | 4.56 mg/m³ (>=P75) | N20 VIIRS 4 km, data of 2026-08-27 |
| Eilat seawater desalination (Mekorot) | 🟢 GREEN | 0.0756 mg/m³ (<P50) | N20 VIIRS 4 km, data of 2026-08-27 |

**Data dates**

- N20 VIIRS 4 km: 2026-08-27 (0 days before the report date)
- DINEOF 9 km gap-filled: 2026-08-27 (0 days before the report date)
- CoralTemp SST: 2026-08-27 (0 days before the report date)

### Ashkelon — 🟠 ORANGE (upstream signal: rafah ≥ 1.5× P90; ashkelon itself is yellow)

- **Chlorophyll:** 4.56 mg/m³, >=P75 of its own seasonal normal (P50 1.55 · P75 2.65 · P90 7.84 · P97 17.3, n=115)
- **Source:** N20 VIIRS 4 km, data of 2026-08-27
- **Data confidence:** 6/6 pixels valid (100%) on 2026-08-27
- **SST:** 30.0 °C, +0.3 °C vs seasonal normal
- **Upstream sentinels:** port_said: 1.8 mg/m³ (P90 3.39; below P90); el_arish: 3.06 mg/m³ (P90 3.05; above P90); rafah: 13.9 mg/m³ (P90 8.34; upstream is high)
- **Why:**
  - chl 4.56 mg/m3 is >=P75 of this box's own seasonal normal (P50 1.55, P75 2.65, P90 7.84, P97 17.3; n=115)
  - newest value 8.74 is not yet confirmed by the previous valid day (4.56, 1 d apart); judged at 4.56
  - rising over 3 days while above P75
  - yellow plus upstream sentinel at or above its P90: upgraded to orange
  - extent: at least half of the box is above its P90
  - sentinel port_said: 1.8, below its P90 3.39
  - sentinel el_arish: 3.06 >= its P90 3.05 (upstream is high)
  - sentinel rafah: 13.9 >= its P90 8.34 (upstream is high)
  - SST 30.0 C, +0.3 C vs normal
  - data: 6/6 pixels valid on 2026-08-27

### Eilat seawater desalination (Mekorot) — 🟢 GREEN

- **Chlorophyll:** 0.0756 mg/m³, <P50 of its own seasonal normal (P50 0.0962 · P75 0.14 · P90 0.214 · P97 0.263, n=74)
- **Source:** N20 VIIRS 4 km, data of 2026-08-27
- **Data confidence:** 3/4 pixels valid (75%) on 2026-08-27
- **SST:** 27.7 °C, -0.1 °C vs seasonal normal
- **Upstream sentinels:** tiran: 0.829 mg/m³ (P90 1.08; below P90); gulf_mid: 0.00161 mg/m³ (P90 0.145; below P90)
- **Why:**
  - chl 0.0756 mg/m3 is <P50 of this box's own seasonal normal (P50 0.0962, P75 0.14, P90 0.214, P97 0.263; n=74)
  - newest value 0.244 is not yet confirmed by the previous valid day (0.0756, 1 d apart); judged at 0.0756
  - sentinel tiran: 0.829, below its P90 1.08
  - sentinel gulf_mid: 0.00161, below its P90 0.145
  - SST 27.7 C, -0.1 C vs normal
  - data: 3/4 pixels valid on 2026-08-27

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
