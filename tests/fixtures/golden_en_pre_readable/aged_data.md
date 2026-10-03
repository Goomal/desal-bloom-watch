# Desal Bloom Watch — 2026-10-02

**Worst level: RED (ashkelon).** No plant changed level since yesterday.

| Plant | Level | Chlorophyll | Data |
|---|---|---|---|
| Ashkelon | 🔴 RED | 9.53 mg/m³ (>=P90) | DINEOF 9 km gap-filled, data of 2026-09-29 |
| Hadera | 🟢 GREEN | 0.367 mg/m³ (>=P50) | DINEOF 9 km gap-filled, data of 2026-09-29 |

**Data dates**

- N20 VIIRS 4 km: 2026-09-29 (3 days before the report date)
- DINEOF 9 km gap-filled: 2026-09-30 (2 days before the report date)
- CoralTemp SST: 2026-09-30 (2 days before the report date)

## Ashkelon — 🔴 RED

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

## Hadera — 🟢 GREEN

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

---

**Sources**

- Data: NOAA CoastWatch (public domain, US government data). SST: NOAA Coral Reef Watch CoralTemp; licence text carries an OSTIA academic-research clause, so use is research use only.
- Coastline: Natural Earth (public domain), naturalearthdata.com.

*Desal Bloom Watch is a satellite-based early-warning aid. It is not an operational decision tool and not a measurement at the intake: satellites see the top few metres, data lag about two days, and your own on-line analysers remain the real-time alarm.*
