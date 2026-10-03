# Eilat history review

Every day since 2020-06 on which the scorer rates the `eilat` intake box ORANGE or RED, as the shipped rules (`docs/scoring.md`) would have rated it that day. Written to be read by someone who knows the Gulf of Aqaba, so false alarms can be called out. Values are the box median chlorophyll-a (mg/m3). Percentiles are the box's own seasonal window with the day's own year left out (leave-year-out), so no day is judged against itself. Source = N20 VIIRS 4 km where >= 25 % of the box is clear, else DINEOF 9 km.

**112 orange-or-red days of 2212 scored days (5.1 %)** in 27 episodes; 92 are RED, 20 ORANGE. By month: Jan 2, Feb 12, Mar 7, Apr 23, May 28, Jun 10, Jul 3, Aug 9, Sep 4, Oct 5, Nov 2, Dec 7.

Triggers: 74 days are at or above the box's own P97; 26 days are only YELLOW on the box (>= P90) lifted to ORANGE because an upstream sentinel (tiran / gulf_mid) is >= 1.5x its own P90; the others sit between P90 and P97 and were carried up by the orange-two-days-running or 3x-median rules. The sentinel-lifted days have values barely above P90 and are the likeliest false alarms: judge those first.

## Episodes

| episode | days | peak chl | peak vs P97 |
|---|---|---|---|
| 2020-06-28 .. 2020-06-28 | 1 | 0.32 on 2020-06-28 | 1.0x |
| 2020-07-19 .. 2020-07-21 | 3 | 0.22 on 2020-07-20 | 1.0x |
| 2020-12-30 .. 2020-12-31 | 2 | 0.51 on 2020-12-30 | 1.0x |
| 2021-08-09 .. 2021-08-14 | 6 | 0.27 on 2021-08-09 | 1.2x |
| 2021-08-29 .. 2021-09-01 | 4 | 0.26 on 2021-08-29 | 1.0x |
| 2021-09-09 .. 2021-09-10 | 2 | 0.26 on 2021-09-10 | 1.0x |
| 2021-09-21 .. 2021-09-21 | 1 | 0.23 on 2021-09-21 | 0.8x |
| 2021-10-15 .. 2021-10-15 | 1 | 0.35 on 2021-10-15 | 1.1x |
| 2021-10-29 .. 2021-11-02 | 5 | 0.52 on 2021-10-29 | 1.1x |
| 2021-12-16 .. 2021-12-16 | 1 | 0.95 on 2021-12-16 | 1.1x |
| 2022-04-11 .. 2022-04-11 | 1 | 1.20 on 2022-04-11 | 0.9x |
| 2022-04-20 .. 2022-04-30 | 10 | 1.54 on 2022-04-20 | 1.0x |
| 2022-05-06 .. 2022-05-24 | 19 | 0.71 on 2022-05-13 | 0.7x |
| 2022-06-20 .. 2022-06-22 | 3 | 0.28 on 2022-06-20 | 0.9x |
| 2022-06-25 .. 2022-06-30 | 5 | 0.22 on 2022-06-26 | 1.1x |
| 2023-03-04 .. 2023-03-07 | 4 | 0.84 on 2023-03-04 | 1.2x |
| 2025-03-22 .. 2025-03-22 | 1 | 0.72 on 2025-03-22 | 1.0x |
| 2025-03-30 .. 2025-04-02 | 4 | 1.43 on 2025-03-30 | 1.8x |
| 2025-04-09 .. 2025-04-09 | 1 | 1.17 on 2025-04-09 | 1.2x |
| 2025-04-17 .. 2025-04-25 | 9 | 1.75 on 2025-04-25 | 1.5x |
| 2025-05-22 .. 2025-05-30 | 9 | 0.79 on 2025-05-29 | 1.5x |
| 2025-06-05 .. 2025-06-05 | 1 | 0.45 on 2025-06-05 | 1.1x |
| 2025-10-27 .. 2025-10-27 | 1 | 0.62 on 2025-10-27 | 1.4x |
| 2025-12-07 .. 2025-12-10 | 4 | 0.85 on 2025-12-08 | 1.5x |
| 2026-01-27 .. 2026-01-28 | 2 | 0.60 on 2026-01-27 | 1.0x |
| 2026-02-02 .. 2026-02-11 | 10 | 0.66 on 2026-02-02 | 1.3x |
| 2026-02-16 .. 2026-02-17 | 2 | 0.36 on 2026-02-16 | 1.0x |

## Every day

| date | level | chl | P50 / P90 / P97 | rank | reasons |
|---|---|---|---|---|---|
| 2020-06-28 | ORANGE | 0.32 | 0.21 / 0.28 / 0.32 | >=P97 | fallback: N20; source: DINEOF; held back by previous day; sentinel tiran; sentinel gulf_mid |
| 2020-07-19 | ORANGE | 0.22 | 0.19 / 0.21 / 0.22 | >=P97 | fallback: N20; source: DINEOF; held back by previous day; sentinel gulf_mid |
| 2020-07-20 | RED | 0.22 | 0.19 / 0.21 / 0.22 | >=P97 | fallback: N20; source: DINEOF; held back by previous day; orange 2 days running; sentinel gulf_mid |
| 2020-07-21 | RED | 0.22 | 0.19 / 0.21 / 0.22 | >=P97 | fallback: N20; source: DINEOF; orange 2 days running; sentinel gulf_mid |
| 2020-12-30 | ORANGE | 0.51 | 0.36 / 0.46 / 0.51 | >=P97 | fallback: N20; source: DINEOF; held back by previous day; sentinel tiran; sentinel gulf_mid |
| 2020-12-31 | RED | 0.51 | 0.35 / 0.46 / 0.49 | >=P97 | fallback: N20; source: DINEOF; held back by previous day; orange 2 days running; sentinel tiran; sentinel gulf_mid |
| 2021-08-09 | ORANGE | 0.27 | 0.19 / 0.22 / 0.23 | >=P97 | fallback: N20; source: DINEOF; held back by previous day; sentinel gulf_mid; SST warm |
| 2021-08-10 | RED | 0.27 | 0.19 / 0.22 / 0.23 | >=P97 | fallback: N20; source: DINEOF; orange 2 days running |
| 2021-08-11 | RED | 0.27 | 0.19 / 0.22 / 0.23 | >=P97 | fallback: N20; source: DINEOF; orange 2 days running |
| 2021-08-12 | RED | 0.25 | 0.19 / 0.22 / 0.23 | >=P97 | fallback: N20; source: DINEOF; orange 2 days running; sentinel gulf_mid |
| 2021-08-13 | RED | 0.24 | 0.19 / 0.22 / 0.23 | >=P97 | fallback: N20; source: DINEOF; orange 2 days running; sentinel gulf_mid |
| 2021-08-14 | RED | 0.23 | 0.19 / 0.22 / 0.23 | >=P97 | fallback: N20; source: DINEOF; orange 2 days running; sentinel gulf_mid |
| 2021-08-29 | ORANGE | 0.26 | 0.09 / 0.18 / 0.26 | >=P90 | source: N20; sentinel upgrade; sentinel gulf_mid |
| 2021-08-30 | RED | 0.26 | 0.09 / 0.18 / 0.26 | >=P97 | source: N20; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2021-08-31 | RED | 0.26 | 0.09 / 0.19 / 0.26 | >=P97 | source: N20; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2021-09-01 | RED | 0.26 | 0.10 / 0.20 / 0.26 | >=P97 | source: N20; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2021-09-09 | ORANGE | 0.23 | 0.11 / 0.19 / 0.25 | >=P90 | source: N20; held back by previous day; sentinel upgrade; sentinel gulf_mid |
| 2021-09-10 | RED | 0.26 | 0.11 / 0.21 / 0.27 | >=P90 | source: N20; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2021-09-21 | ORANGE | 0.23 | 0.12 / 0.22 / 0.27 | >=P90 | source: N20; held back by previous day; sentinel upgrade; sentinel gulf_mid |
| 2021-10-15 | ORANGE | 0.35 | 0.25 / 0.29 / 0.31 | >=P97 | fallback: N20; source: DINEOF; held back by previous day; sentinel gulf_mid |
| 2021-10-29 | ORANGE | 0.52 | 0.21 / 0.39 / 0.46 | >=P97 | source: N20; sentinel gulf_mid |
| 2021-10-30 | RED | 0.52 | 0.21 / 0.39 / 0.46 | >=P97 | source: N20; orange 2 days running; sentinel gulf_mid |
| 2021-10-31 | RED | 0.52 | 0.22 / 0.39 / 0.46 | >=P97 | source: N20; orange 2 days running; sentinel gulf_mid |
| 2021-11-01 | RED | 0.52 | 0.22 / 0.39 / 0.46 | >=P97 | source: N20; orange 2 days running; sentinel gulf_mid |
| 2021-11-02 | RED | 0.40 | 0.27 / 0.31 / 0.33 | >=P97 | fallback: N20; source: DINEOF; held back by previous day; orange 2 days running; sentinel gulf_mid |
| 2021-12-16 | ORANGE | 0.95 | 0.35 / 0.62 / 0.83 | >=P97 | source: N20; sentinel tiran |
| 2022-04-11 | RED | 1.20 | 0.35 / 0.99 / 1.34 | >=P90 | fallback: N20; source: DINEOF; held back by previous day; sentinel upgrade; 3.5x the seasonal median; sentinel tiran; sentinel gulf_mid |
| 2022-04-20 | RED | 1.54 | 0.32 / 0.74 / 1.48 | >=P97 | source: N20; 4.8x the seasonal median; sentinel tiran |
| 2022-04-21 | RED | 1.54 | 0.31 / 0.76 / 1.49 | >=P97 | source: N20; 5.0x the seasonal median |
| 2022-04-22 | RED | 1.54 | 0.29 / 0.76 / 1.49 | >=P97 | source: N20; 5.3x the seasonal median |
| 2022-04-24 | ORANGE | 0.59 | 0.29 / 0.57 / 1.37 | >=P90 | source: N20; held back by previous day; sentinel upgrade; sentinel gulf_mid |
| 2022-04-25 | RED | 0.59 | 0.28 / 0.51 / 1.36 | >=P90 | source: N20; held back by previous day; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-04-26 | RED | 0.59 | 0.27 / 0.50 / 1.37 | >=P90 | source: N20; held back by previous day; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-04-27 | RED | 0.59 | 0.26 / 0.50 / 1.39 | >=P90 | source: N20; held back by previous day; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-04-28 | RED | 0.78 | 0.30 / 0.48 / 1.15 | >=P90 | fallback: N20; source: DINEOF; held back by previous day; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-04-29 | RED | 0.99 | 0.30 / 0.48 / 1.14 | >=P90 | fallback: N20; source: DINEOF; sentinel upgrade; 3.3x the seasonal median; sentinel gulf_mid |
| 2022-04-30 | RED | 0.99 | 0.30 / 0.48 / 1.13 | >=P90 | fallback: N20; source: DINEOF; held back by previous day; 3.4x the seasonal median; sentinel gulf_mid |
| 2022-05-06 | ORANGE | 0.61 | 0.21 / 0.43 / 0.48 | >=P97 | source: N20; sentinel upgrade; sentinel gulf_mid |
| 2022-05-07 | RED | 0.61 | 0.21 / 0.43 / 0.48 | >=P97 | source: N20; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-05-08 | RED | 0.61 | 0.21 / 0.43 / 0.48 | >=P97 | source: N20; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-05-09 | RED | 0.61 | 0.20 / 0.43 / 0.48 | >=P97 | source: N20; sentinel upgrade; 3.0x the seasonal median; sentinel gulf_mid |
| 2022-05-10 | RED | 0.70 | 0.29 / 0.41 / 0.95 | >=P90 | fallback: N20; source: DINEOF; held back by previous day; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-05-11 | RED | 0.57 | 0.29 / 0.41 / 0.95 | >=P90 | fallback: N20; source: DINEOF; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-05-12 | RED | 0.57 | 0.29 / 0.41 / 1.01 | >=P90 | fallback: N20; source: DINEOF; held back by previous day; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-05-13 | RED | 0.71 | 0.29 / 0.40 / 1.01 | >=P90 | fallback: N20; source: DINEOF; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-05-14 | RED | 0.71 | 0.28 / 0.41 / 1.01 | >=P90 | fallback: N20; source: DINEOF; held back by previous day; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-05-15 | RED | 0.49 | 0.28 / 0.41 / 1.01 | >=P90 | fallback: N20; source: DINEOF; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-05-16 | RED | 0.49 | 0.28 / 0.40 / 1.01 | >=P90 | fallback: N20; source: DINEOF; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-05-17 | RED | 0.49 | 0.28 / 0.40 / 1.01 | >=P90 | fallback: N20; source: DINEOF; held back by previous day; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-05-18 | RED | 0.50 | 0.27 / 0.40 / 1.01 | >=P90 | fallback: N20; source: DINEOF; held back by previous day; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-05-19 | RED | 0.51 | 0.27 / 0.41 / 1.01 | >=P90 | fallback: N20; source: DINEOF; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-05-20 | RED | 0.47 | 0.27 / 0.41 / 1.01 | >=P90 | fallback: N20; source: DINEOF; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-05-21 | RED | 0.46 | 0.26 / 0.41 / 1.01 | >=P90 | fallback: N20; source: DINEOF; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-05-22 | RED | 0.46 | 0.26 / 0.41 / 1.01 | >=P90 | fallback: N20; source: DINEOF; held back by previous day; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2022-05-23 | RED | 0.53 | 0.14 / 0.43 / 0.45 | >=P97 | source: N20; 3.8x the seasonal median; sentinel tiran; sentinel gulf_mid |
| 2022-05-24 | RED | 0.46 | 0.13 / 0.43 / 0.45 | >=P97 | source: N20; 3.6x the seasonal median; sentinel tiran |
| 2022-06-20 | RED | 0.28 | 0.07 / 0.28 / 0.32 | >=P90 | source: N20; held back by previous day; 4.0x the seasonal median |
| 2022-06-21 | RED | 0.27 | 0.07 / 0.24 / 0.30 | >=P90 | source: N20; 3.8x the seasonal median; sentinel gulf_mid |
| 2022-06-22 | RED | 0.27 | 0.06 / 0.21 / 0.30 | >=P90 | source: N20; 4.2x the seasonal median; sentinel gulf_mid |
| 2022-06-25 | ORANGE | 0.20 | 0.07 / 0.18 / 0.30 | >=P90 | source: N20; held back by previous day; sentinel upgrade; sentinel tiran; sentinel gulf_mid |
| 2022-06-26 | RED | 0.22 | 0.07 / 0.14 / 0.20 | >=P97 | source: N20; 3.2x the seasonal median; sentinel tiran; sentinel gulf_mid |
| 2022-06-27 | RED | 0.22 | 0.06 / 0.14 / 0.20 | >=P97 | source: N20; 3.5x the seasonal median; sentinel tiran; sentinel gulf_mid |
| 2022-06-28 | RED | 0.22 | 0.06 / 0.18 / 0.22 | >=P90 | source: N20; 3.5x the seasonal median; sentinel tiran; sentinel gulf_mid |
| 2022-06-30 | RED | 0.21 | 0.06 / 0.18 / 0.22 | >=P90 | source: N20; held back by previous day; 3.3x the seasonal median |
| 2023-03-04 | RED | 0.84 | 0.27 / 0.54 / 0.69 | >=P97 | source: N20; 3.0x the seasonal median |
| 2023-03-05 | RED | 0.79 | 0.28 / 0.54 / 0.69 | >=P97 | source: N20; orange 2 days running; sentinel gulf_mid |
| 2023-03-06 | RED | 0.79 | 0.28 / 0.58 / 0.72 | >=P97 | source: N20; orange 2 days running; sentinel gulf_mid |
| 2023-03-07 | RED | 0.79 | 0.28 / 0.61 / 0.75 | >=P97 | source: N20; orange 2 days running; sentinel gulf_mid |
| 2025-03-22 | ORANGE | 0.72 | 0.31 / 0.58 / 0.70 | >=P97 | source: N20; held back by previous day |
| 2025-03-30 | RED | 1.43 | 0.35 / 0.66 / 0.79 | >=P97 | source: N20; 4.0x the seasonal median |
| 2025-03-31 | RED | 1.40 | 0.35 / 0.63 / 0.79 | >=P97 | source: N20; 4.0x the seasonal median |
| 2025-04-01 | RED | 1.40 | 0.34 / 0.63 / 0.79 | >=P97 | source: N20; 4.1x the seasonal median |
| 2025-04-02 | RED | 1.40 | 0.34 / 0.64 / 0.79 | >=P97 | source: N20; 4.2x the seasonal median; sentinel gulf_mid |
| 2025-04-09 | RED | 1.17 | 0.32 / 0.62 / 0.98 | >=P97 | fallback: N20; source: DINEOF; 3.6x the seasonal median; sentinel gulf_mid |
| 2025-04-17 | RED | 1.19 | 0.31 / 0.67 / 1.12 | >=P97 | source: N20; held back by previous day; sentinel upgrade; 3.8x the seasonal median; sentinel tiran; sentinel gulf_mid |
| 2025-04-18 | RED | 1.19 | 0.31 / 0.69 / 1.16 | >=P97 | source: N20; held back by previous day; 3.9x the seasonal median; sentinel gulf_mid |
| 2025-04-19 | RED | 1.26 | 0.31 / 0.69 / 1.16 | >=P97 | source: N20; 4.1x the seasonal median |
| 2025-04-20 | RED | 1.26 | 0.29 / 0.69 / 1.16 | >=P97 | source: N20; held back by previous day; 4.3x the seasonal median; sentinel tiran |
| 2025-04-21 | RED | 1.26 | 0.29 / 0.69 / 1.16 | >=P97 | source: N20; held back by previous day; 4.3x the seasonal median; sentinel tiran |
| 2025-04-22 | RED | 1.26 | 0.28 / 0.69 / 1.16 | >=P97 | source: N20; held back by previous day; 4.4x the seasonal median; sentinel tiran |
| 2025-04-23 | RED | 1.26 | 0.27 / 0.62 / 0.80 | >=P97 | source: N20; held back by previous day; 4.7x the seasonal median; sentinel tiran |
| 2025-04-24 | RED | 1.69 | 0.32 / 0.76 / 1.13 | >=P97 | fallback: N20; source: DINEOF; held back by previous day; 5.2x the seasonal median |
| 2025-04-25 | RED | 1.75 | 0.32 / 0.76 / 1.13 | >=P97 | fallback: N20; source: DINEOF; 5.5x the seasonal median |
| 2025-05-22 | ORANGE | 0.38 | 0.29 / 0.48 / 0.68 | >=P75 | fallback: N20; source: DINEOF; held back by previous day; sentinel upgrade; sentinel tiran |
| 2025-05-23 | RED | 0.41 | 0.10 / 0.28 / 0.47 | >=P90 | source: N20; 3.9x the seasonal median |
| 2025-05-24 | RED | 0.41 | 0.09 / 0.30 / 0.47 | >=P90 | source: N20; held back by previous day; 4.4x the seasonal median |
| 2025-05-25 | RED | 0.43 | 0.09 / 0.32 / 0.47 | >=P90 | source: N20; 4.5x the seasonal median |
| 2025-05-26 | RED | 0.43 | 0.11 / 0.32 / 0.46 | >=P90 | source: N20; 3.7x the seasonal median; sentinel gulf_mid |
| 2025-05-27 | RED | 0.43 | 0.11 / 0.32 / 0.46 | >=P90 | source: N20; 3.8x the seasonal median; sentinel gulf_mid |
| 2025-05-28 | RED | 0.43 | 0.11 / 0.32 / 0.46 | >=P90 | source: N20; 3.8x the seasonal median; sentinel gulf_mid |
| 2025-05-29 | RED | 0.79 | 0.25 / 0.42 / 0.53 | >=P97 | fallback: N20; source: DINEOF; sentinel upgrade; 3.2x the seasonal median; sentinel tiran |
| 2025-05-30 | RED | 0.70 | 0.25 / 0.42 / 0.51 | >=P97 | fallback: N20; source: DINEOF; orange 2 days running; sentinel tiran |
| 2025-06-05 | RED | 0.45 | 0.13 / 0.34 / 0.42 | >=P97 | source: N20; held back by previous day; 3.6x the seasonal median; sentinel tiran; sentinel gulf_mid |
| 2025-10-27 | ORANGE | 0.62 | 0.23 / 0.33 / 0.46 | >=P97 | source: N20; sentinel tiran |
| 2025-12-07 | ORANGE | 0.70 | 0.41 / 0.54 / 0.57 | >=P97 | fallback: N20; source: DINEOF; held back by previous day |
| 2025-12-08 | RED | 0.85 | 0.41 / 0.54 / 0.57 | >=P97 | fallback: N20; source: DINEOF; held back by previous day; orange 2 days running |
| 2025-12-09 | RED | 0.63 | 0.41 / 0.55 / 0.57 | >=P97 | fallback: N20; source: DINEOF; orange 2 days running |
| 2025-12-10 | RED | 0.58 | 0.42 / 0.55 / 0.57 | >=P97 | fallback: N20; source: DINEOF; orange 2 days running |
| 2026-01-27 | ORANGE | 0.60 | 0.25 / 0.37 / 0.60 | >=P97 | source: N20; sentinel gulf_mid |
| 2026-01-28 | RED | 0.60 | 0.25 / 0.37 / 0.50 | >=P97 | source: N20; orange 2 days running; sentinel gulf_mid |
| 2026-02-02 | ORANGE | 0.66 | 0.25 / 0.38 / 0.50 | >=P97 | source: N20; sentinel tiran; sentinel gulf_mid |
| 2026-02-03 | RED | 0.66 | 0.24 / 0.36 / 0.50 | >=P97 | source: N20; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2026-02-04 | RED | 0.63 | 0.24 / 0.35 / 0.50 | >=P97 | source: N20; orange 2 days running |
| 2026-02-05 | RED | 0.63 | 0.25 / 0.36 / 0.50 | >=P97 | source: N20; held back by previous day; orange 2 days running; sentinel gulf_mid |
| 2026-02-06 | RED | 0.57 | 0.24 / 0.33 / 0.49 | >=P97 | source: N20; orange 2 days running; sentinel gulf_mid |
| 2026-02-07 | RED | 0.57 | 0.23 / 0.35 / 0.49 | >=P97 | source: N20; orange 2 days running; sentinel gulf_mid |
| 2026-02-08 | RED | 0.57 | 0.23 / 0.36 / 0.49 | >=P97 | source: N20; held back by previous day; orange 2 days running; sentinel gulf_mid |
| 2026-02-09 | RED | 0.57 | 0.24 / 0.34 / 0.46 | >=P97 | source: N20; held back by previous day; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2026-02-10 | RED | 0.57 | 0.23 / 0.36 / 0.46 | >=P97 | source: N20; held back by previous day; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2026-02-11 | RED | 0.57 | 0.24 / 0.36 / 0.46 | >=P97 | source: N20; held back by previous day; sentinel upgrade; orange 2 days running; sentinel gulf_mid |
| 2026-02-16 | ORANGE | 0.36 | 0.29 / 0.33 / 0.35 | >=P97 | fallback: N20; source: DINEOF; held back by previous day; sentinel gulf_mid |
| 2026-02-17 | RED | 0.36 | 0.29 / 0.33 / 0.35 | >=P97 | fallback: N20; source: DINEOF; orange 2 days running; sentinel gulf_mid |
