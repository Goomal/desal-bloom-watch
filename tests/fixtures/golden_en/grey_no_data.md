# Desal Bloom Watch — 2023-08-25

Eilat seawater desalination could not be judged today (this is not an all-clear)

Satellite data from 25 Aug, today

Changed since yesterday: Hadera YELLOW → GREEN.

### Hadera — 🟢 GREEN

- **What it means:** Chlorophyll is above normal for this time of year, but not rising.
- **Compared with normal for this time of year:** above normal, 0.923 mg/m³ (the top quarter starts at 0.914)
- **How sure:** Good: clear view today (sharp satellite)
- **Upstream monitoring points:** none of 3 above their usual high

### Eilat seawater desalination (Mekorot) — ⚪ GREY

- **What it means:** There is no usable satellite data for this plant, so no level can be given. This is not an all-clear.
- **How sure:** Low: no satellite data
- **Upstream monitoring points:** none of 2 above their usual high

## Technical details

Changed since yesterday: hadera YELLOW → GREEN.

| Plant | Level | Chlorophyll | Data |
|---|---|---|---|
| Hadera | 🟢 GREEN | 0.923 mg/m³ (>=P75) | N20 VIIRS 4 km, data of 2023-08-25 |
| Eilat seawater desalination (Mekorot) | ⚪ GREY | — | no data |

**Data dates**

- N20 VIIRS 4 km: 2023-08-25 (0 days before the report date)
- DINEOF 9 km gap-filled: 2022-07-05 (416 days before the report date)
- CoralTemp SST: 2023-08-25 (0 days before the report date)

### Hadera — 🟢 GREEN

- **Chlorophyll:** 0.923 mg/m³, >=P75 of its own seasonal normal (P50 0.651 · P75 0.914 · P90 1.22 · P97 1.53, n=102)
- **Source:** N20 VIIRS 4 km, data of 2023-08-25
- **Data confidence:** 3/4 pixels valid (75%) on 2023-08-25
- **SST:** 29.9 °C, +0.2 °C vs seasonal normal
- **Upstream sentinels:** port_said: 2.48 mg/m³ (P90 3.27; below P90); el_arish: 0.769 mg/m³ (P90 3.5; below P90); rafah: 1.19 mg/m³ (P90 8.49; below P90)
- **Why:**
  - chl 0.923 mg/m3 is >=P75 of this box's own seasonal normal (P50 0.651, P75 0.914, P90 1.22, P97 1.53; n=102)
  - sentinel port_said: 2.48, below its P90 3.27
  - sentinel el_arish: 0.769, below its P90 3.5
  - sentinel rafah: 1.19, below its P90 8.49
  - SST 29.9 C, +0.2 C vs normal
  - data: 3/4 pixels valid on 2023-08-25

### Eilat seawater desalination (Mekorot) — ⚪ GREY

- **Data confidence:** GREY: no data: no valid observation for this box
- **SST:** 26.8 °C, -1.1 °C vs seasonal normal
- **Upstream sentinels:** tiran: 0.789 mg/m³ (P90 1.1; below P90); gulf_mid: 0.12 mg/m³ (P90 0.126; below P90)
- **Why:**
  - no data: no valid observation for this box

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
