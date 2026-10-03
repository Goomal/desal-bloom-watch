# Percentile export (`dbw/data/percentiles.json`)

Scoring compares a day's box value with seasonal percentiles built from six years of satellite
history. Fetching that history takes about an hour per fresh install, so the repo ships the
percentiles instead, and `dbw setup` fetches only the last 45 days.

## Where the numbers came from

- **Source:** NOAA CoastWatch ERDDAP (chlorophyll: public-domain US government data; CoralTemp SST: its own licence
  text, research use, see `docs/sources.md`): the DINEOF gap-filled
  chlorophyll (`noaacwNPPN20VIIRSDINEOFDaily`), VIIRS NOAA-20 chlorophyll
  (`noaacwN20VIIRSchlaDaily`) and CoralTemp SST (`noaacrwsstDaily`). URLs and licences:
  `docs/sources.md` rows 1, 3 and 7.
- **Pulled by:** `dbw backfill --from 2020-05-05` into `data/dbw.sqlite`, then
  `.venv/bin/python scripts/export_percentiles.py`. The script recomputes the percentiles from the
  stored observations (not from a stored table), for every box in `plants.yaml`.
- **Date range, method, build time:** in the file's `header` (history 2020-05-05 .. 2026-09-29;
  P50/P75/P90/P97 of the daily box median over a +-15-day window on a 365-day calendar; fewer than
  30 samples means no percentile and a grey day). Values are rounded to 4 decimals.
- **Also in the file:** the pixel-set signature per box and source, so the shared-pixel flag works
  for plants you did not choose.

## What setup does with it

`dbw setup` loads the export for the chosen plants and their sentinels, then fetches the last 45
days so the report has fresh data and yesterday for the two-day confirmation. If you already have
percentiles of your own in the database they are left alone. `dbw setup --full-history` skips the
export and rebuilds everything from a full backfill.

## Refreshing it

Once a year, or after a scoring change: backfill to today, run the script, commit the file.
Rounding to 4 decimals can move the printed SST "vs normal" by 0.1 C against a full-history
database; levels were identical on the 352 plant-days compared (2026-08-18 .. 2026-09-30).
