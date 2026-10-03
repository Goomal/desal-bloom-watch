# Data sources — Phase 0 verification (2026-10-01)

Every number below was pulled by this leg on 2026-10-01 from a Mac in Israel, not copied from
the plan. Pull times are UTC. Sample boxes are small and chosen for the northern Gulf of Eilat
and for the Ashkelon coast; they are samples, not the final intake boxes (see `plants.yaml`).

Status vocabulary: `WORKS` / `STALE <last date>` / `DEAD` / `NEEDS-SIGNUP`.

| # | Source | Status |
|---|---|---|
| 1 | ERDDAP VIIRS NOAA-20 chl daily (4 km) | WORKS |
| 2 | ERDDAP VIIRS S-NPP chl daily (4 km) | WORKS |
| 3 | ERDDAP DINEOF gap-filled chl (9 km) | WORKS |
| 4 | ERDDAP N20 chl anomaly ratio | WORKS |
| 5 | NASA GIBS snapshot | WORKS |
| 6 | ERDDAP Sentinel-3 OLCI 300 m sectors | WORKS (90-day rolling window only) |
| 7 | SST: CoralTemp on ERDDAP | WORKS (licence flag; OISST not on CoastWatch) |
| 8 | Open-Meteo wind + dust | WORKS (free tier non-commercial only) |
| 9 | ISRAMAR time-series download | NEEDS-SIGNUP |
| 10 | ISRAMAR shelf currents forecast (SELIPS) | STALE 2026-08-22 |
| 11 | IUI Eilat NMP "available data" | DEAD for automation (page up, data host blocks) |
| 12 | MoEP freedom-of-information marine PDFs | WORKS in a browser; per-plant list not enumerable by script |
| 13 | Natural Earth 10 m land (bundled coastline for the report map) | WORKS (public domain, bundled, no network) |
| 14 | NASA GIBS true-colour underlay (report `--basemap gibs`) | WORKS (manual option, off by default) |

Count: 8 WORKS (rows 1-8) + 2 WORKS (rows 13-14, report map) + 1 WORKS-in-browser (row 12), 1 STALE, 1 NEEDS-SIGNUP, 1 DEAD.

ERDDAP notes that apply to rows 1-7:

- Base: `https://coastwatch.noaa.gov/erddap/griddap/<id>.csv?<var>[time][alt][lat][lon]`.
- Use `curl -g` (the square brackets are otherwise treated as a glob).
- VIIRS datasets have an altitude axis, so every query needs `[(0.0)]`; CoralTemp has none.
- Time axes are noon UTC for VIIRS/SST/DINEOF. OLCI sector datasets use real scene times
  (~07:40-08:30 UTC), so end a range with `(last)`; asking beyond the last time is HTTP 404.
- Cloud or sun-glint pixels come back as `NaN`. Count them; never treat them as zero.
- Pixels adjacent to land are contaminated (values of 80-280 mg/m3 seen near Ashkelon and the
  Eilat tip). Use sea-only boxes.
- Chlorophyll units are `mg m^-3`.

---

## 1. ERDDAP VIIRS NOAA-20 chlorophyll, daily — `noaacwN20VIIRSchlaDaily`

- URL (Eilat sample box):
  `https://coastwatch.noaa.gov/erddap/griddap/noaacwN20VIIRSchlaDaily.csv?chlor_a[(2026-09-24T12:00:00Z):1:(2026-09-27T12:00:00Z)][(0.0)][(29.40):1:(29.55)][(34.90):1:(35.00)]`
- Returns: CSV, columns `time, altitude, latitude, longitude, chlor_a`. Variable `chlor_a`, `mg m^-3`.
- Resolution: 4 km (grid step 0.0375 deg). Daily composite.
- Coverage: 2021-08-26 to 2026-09-29. **Not back to 2018**, so the plan's "history 2018 to now"
  cannot come from this dataset (see FINDINGS).
- Lag: last day 2026-09-29 at pull time 2026-10-01, so about 2 days.
- Licence: NOAA CoastWatch, public domain US government data; credit NOAA CoastWatch.
- Sample, Eilat box 29.40-29.55 N, 34.90-35.00 E, 20 pixels, pulled 2026-10-01T16:58Z:

  | day (noon UTC) | valid px | min | mean | max (mg/m3) |
  |---|---|---|---|---|
  | 2026-09-24 | 12/20 | 0.049 | 0.133 | 0.586 |
  | 2026-09-25 | 12/20 | 0.002 | 0.071 | 0.151 |
  | 2026-09-26 | 12/20 | 0.049 | 0.121 | 0.250 |
  | 2026-09-27 | 12/20 | 0.056 | 0.137 | 0.323 |

  Earlier pull (16:39Z): 09-22, 09-28 and 09-29 were all NaN for this box. Ashkelon box
  31.55-31.75 N, 34.40-34.55 E (30 px, pulled 2026-10-01T17:02Z): 09-27 valid 25/30, min 0.399,
  mean 9.546, max 79.953; 09-28 valid 20/30, min 0.360, mean 5.022, max 12.849; 09-29 all NaN.
  Coast-contaminated, so a box has to sit seaward of the surf zone.

**Status: WORKS**

## 2. ERDDAP VIIRS S-NPP chlorophyll, daily — `noaacwNPPVIIRSchlaDaily`

- URL: `https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPVIIRSchlaDaily.csv?chlor_a[(2026-09-23T12:00:00Z):1:(2026-09-27T12:00:00Z)][(0.0)][(29.40):1:(29.55)][(34.90):1:(35.00)]`
- Returns: same layout as row 1. `mg m^-3`. Resolution 4 km.
- Coverage: 2025-09-22 to 2026-09-27. **Only about one year of history.**
- Lag: last day 2026-09-27 at pull time, so about 4 days.
- Licence: NOAA CoastWatch, public.
- Sample, same Eilat box, pulled 2026-10-01T16:58Z:

  | day | valid px | min | mean | max |
  |---|---|---|---|---|
  | 2026-09-23 | 13/20 | 0.181 | 0.238 | 0.465 |
  | 2026-09-25 | 11/20 | 0.180 | 0.233 | 0.299 |
  | 2026-09-26 | 0/20 | all NaN | | |
  | 2026-09-27 | 11/20 | 0.211 | 0.249 | 0.278 |

  S-NPP reads about 2x the N20 values on the same days (0.23-0.25 vs 0.07-0.14). Do not mix the
  two series in one percentile table without a bias check.

**Status: WORKS**

## 3. ERDDAP DINEOF gap-filled chlorophyll — `noaacwNPPN20VIIRSDINEOFDaily`

- URL: `https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPN20VIIRSDINEOFDaily.csv?chlor_a[(2026-09-25T12:00:00Z):1:(2026-09-29T12:00:00Z)][(0.0)][(29.40):1:(29.55)][(34.90):1:(35.00)]`
- Returns: gap-filled chlorophyll, no cloud holes. `mg m^-3`. Resolution about 9 km (0.083 deg).
- Coverage: 2020-05-05 to 2026-09-29. Lag about 2 days.
- Licence: NOAA CoastWatch, public. It is a statistical reconstruction, not an observation.
- Sample, same Eilat box (6 pixels), pulled 2026-10-01T16:58Z:

  | day | valid px | min | mean | max |
  |---|---|---|---|---|
  | 2026-09-25 | 6/6 | 0.185 | 0.222 | 0.252 |
  | 2026-09-26 | 6/6 | 0.184 | 0.222 | 0.250 |
  | 2026-09-27 | 6/6 | 0.190 | 0.224 | 0.251 |
  | 2026-09-28 | 6/6 | 0.188 | 0.225 | 0.251 |
  | 2026-09-29 | 6/6 | 0.187 | 0.224 | 0.252 |

  Smooth by construction (a 5-day range of 0.222-0.225). Fine for climatology and a fallback;
  it will lag a real fast bloom.

**Status: WORKS**

## 4. ERDDAP N20 chlorophyll anomaly ratio — `noaacwN20VIIRSchlanomratDaily`

- URL: `https://coastwatch.noaa.gov/erddap/griddap/noaacwN20VIIRSchlanomratDaily.csv?chlor_a_pdif[(2026-09-24T12:00:00Z):1:(2026-09-27T12:00:00Z)][(0.0)][(29.40):1:(29.55)][(34.90):1:(35.00)]`
- Returns: variable `chlor_a_pdif`, no units attribute. Observed range -0.99 to 6.9, consistent
  with a fractional difference from climatology (confirm against the dataset metadata in Phase 1).
- Resolution: 48 pixels in the same box, so about 2 km. Coverage 2018-08-06 to 2026-09-28.
  Lag about 3 days.
- Licence: NOAA CoastWatch, public.
- Sample, Eilat box, pulled 2026-10-01T16:58Z:

  | day | valid px | min | mean | max |
  |---|---|---|---|---|
  | 2026-09-24 | 33/48 | -0.689 | 0.494 | 1.453 |
  | 2026-09-25 | 23/48 | -0.988 | 0.210 | 1.889 |
  | 2026-09-26 | 29/48 | -0.761 | 0.462 | 1.106 |
  | 2026-09-27 | 28/48 | 0.189 | 1.326 | 6.886 |

  09-28 was all NaN for this box.

**Status: WORKS**

## 5. NASA GIBS snapshot (map image)

- URL: `https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=VIIRS_NOAA20_Chlorophyll_a&CRS=EPSG:4326&BBOX=29,33,34,37&WIDTH=600&HEIGHT=600&FORMAT=image/png&TIME=2026-09-29`
  (WMS 1.3.0 with EPSG:4326: BBOX order is lat_min,lon_min,lat_max,lon_max.)
- Returns: PNG, transparent chlorophyll overlay (white/transparent = no data). Pulled
  2026-10-01T16:42:57Z: HTTP 200, `image/png`, 39,519 bytes. Not numeric values; for the map in
  the report only.
- Other layers tested the same way: `S3A_OLCI_Chlorophyll_a` (200, PNG 32,854 B) and
  `VIIRS_NOAA20_CorrectedReflectance_TrueColor` (200, JPEG 72,128 B, use `FORMAT=image/jpeg`).
- Time extents read from GetCapabilities: N20 chl 2018-02-24 to 2026-10-01 daily; S3A OLCI chl to
  2026-09-30; true colour to 2026-10-01. Lag 0-1 day.
- Licence: NASA EOSDIS open data policy, free use; acknowledge NASA GIBS / EOSDIS.

**Status: WORKS**

## 6. ERDDAP Sentinel-3 OLCI 300 m sectors

Dataset ids found by searching the CoastWatch catalogue. Two 300 m sectors cover the plan's area:

- `noaacwS3AOLCIchlaSectorKHDaily`: lat 14.89-30.26, lon 19.96-40.04 — **covers the Gulf of Aqaba / Eilat**.
- `noaacwS3AOLCIchlaSectorKIDaily`: lat 29.81-45.19, lon 19.96-40.04 — **covers the E. Mediterranean coast**.
- Same grid, 0.0025 deg (about 300 m), L3 daily. S3B twins `noaacwS3BOLCIchla...` exist; S3B KH was
  all NaN on the days tried.
- **Window: only about the last 90 days.** No multi-year history here. Phase 2 needs another route
  for history (global 4 km OLCI below, or Copernicus Marine, optional).
- Global 4 km sibling `noaacwS3AOLCIchlaDaily` covers 2019-06-06 to 2026-09-29, but at the Eilat
  tip it reads coast-contaminated (2026-09-25, 14/20 valid px, mean 2.570, max 30.013; pulled 17:02Z).
- URL (sea-only Eilat box, `(last)` end):
  `https://coastwatch.noaa.gov/erddap/griddap/noaacwS3AOLCIchlaSectorKHDaily.csv?chlor_a[(2026-09-24T00:00:00Z):1:(last)][(0.0)][(29.46):1:(29.52)][(34.94):1:(34.98)]`
- URL (Ashkelon):
  `https://coastwatch.noaa.gov/erddap/griddap/noaacwS3AOLCIchlaSectorKIDaily.csv?chlor_a[(2026-09-25T00:00:00Z):1:(last)][(0.0)][(31.60):1:(31.66)][(34.44):1:(34.50)]`
- Licence/terms: the dataset requires the credit "Contains modified Copernicus Sentinel data".
- Samples, pulled 2026-10-01T16:58Z. KH, Eilat sea-only box (408 px):

  | scene time (UTC) | valid px | min | mean | max |
  |---|---|---|---|---|
  | 2026-09-24T08:09Z | 341/408 | 0.010 | 0.109 | 0.632 |
  | 2026-09-25T07:43Z | 382/408 | 0.010 | 0.168 | 0.687 |
  | 2026-09-26 / 27 / 28 | 0/408 | all NaN | | |
  | 2026-09-29T07:40Z | 385/408 | 0.010 | 0.130 | 0.366 |

  KI, Ashkelon box (625 px): only 2026-09-25T08:29Z had data (317/625, min 3.549, mean 11.306,
  max 128.559); 09-26 to 09-29 all NaN. A larger earlier box at the Eilat tip (29.45-29.55 N)
  included land-adjacent pixels and gave max 279.6; sea-only boxes are essential at 300 m.

**Status: WORKS** (90-day rolling window; heavy cloud/glint NaN days)

## 7. SST — NOAA CoralTemp on ERDDAP — `noaacrwsstDaily`

- URL (Ashkelon box): `https://coastwatch.noaa.gov/erddap/griddap/noaacrwsstDaily.csv?analysed_sst[(2026-09-25T12:00:00Z):1:(2026-09-29T12:00:00Z)][(31.60):1:(31.66)][(34.44):1:(34.50)]`
- Returns: variable `analysed_sst`, `degree_C`. No altitude axis. 0.05 deg (about 5 km), daily,
  1985-01-01 to 2026-09-29, lag about 2 days. Anomaly sibling `noaacrwsstanomalyDaily`
  (`sea_surface_temperature_anomaly`).
- Sample pulled 2026-10-01T16:58Z, Ashkelon box (9 px, all valid): means 29.277, 29.107, 29.004,
  29.006, 28.698 for 09-25 to 09-29. Eilat box 29.40-29.55 N, 34.90-35.00 E (9 px, pulled 17:02Z):
  5/9 valid each day (the rest is land), means 26.780, 26.736, 26.866, 26.902, 26.628 for 09-25 to
  09-29. Anomaly (`noaacrwsstanomalyDaily`, Ashkelon box, 17:02Z): means 2.287, 2.342, 2.090 C for
  09-27 to 09-29.
- **Licence:** the dataset licence text includes the OSTIA clause "pure academic research only", no
  commercial use, a maximum period of 5 years, and a reproduction licence form. Decided 2026-10-03: the
  tool keeps CoralTemp, and the README, the report footer and the bundled percentile export say the SST
  numbers stay under this licence text (research use); none of them claims public domain for SST.
- OISST: not found on CoastWatch (catalogue search empty). `upwell.pfeg.noaa.gov` OISST agg
  returned code 000 (unreachable) from this Mac. CoralTemp is the SST source.

**Status: WORKS**

## 8. Open-Meteo wind + dust (no key)

All pulled 2026-10-01T16:42:52Z for 31.65 N, 34.5 E (Ashkelon offshore).

- Wind (forecast API with 2 past days):
  `https://api.open-meteo.com/v1/forecast?latitude=31.65&longitude=34.5&hourly=wind_speed_10m,wind_direction_10m,wind_gusts_10m&past_days=2&forecast_days=1&timezone=Asia%2FJerusalem&wind_speed_unit=ms`
  HTTP 200, 72 hourly values, 2026-09-29T00:00 to 2026-10-01T23:00. Samples: 2.82 m/s at 276 deg,
  5.17 at 255, 1.80 at 199, 3.71 at 284, 0.45 at 243.
- Dust and aerosols:
  `https://air-quality-api.open-meteo.com/v1/air-quality?latitude=31.65&longitude=34.5&hourly=dust,pm10,aerosol_optical_depth&past_days=2&forecast_days=1&timezone=Asia%2FJerusalem`
  HTTP 200. Dust 0.0-2.0 ug/m3, PM10 12.3-17.2 ug/m3, aerosol optical depth 0.12-0.30.
- History (for backfill):
  `https://archive-api.open-meteo.com/v1/archive?latitude=31.65&longitude=34.5&start_date=2026-09-25&end_date=2026-09-27&hourly=wind_speed_10m,wind_direction_10m&wind_speed_unit=ms&timezone=Asia%2FJerusalem`
  HTTP 200, 72 values, first 4.21 m/s at 5 deg.
- Resolution: model grid, hourly. Lag: near real time (forecast).
- Terms (https://open-meteo.com/en/terms, read 2026-10-01T16:55Z): the free API is **for
  non-commercial use only**, under 10,000 calls/day, 5,000/hour, 600/minute; data is CC BY 4.0
  with attribution. A personal open-source tool fits; a commercial user needs a paid plan.

**Status: WORKS**

## 9. ISRAMAR time series (HaderaCTD, AshkelonCTD, Gulf of Eilat DB)

- Site: `https://isramar.ocean.org.il/isramar2009/`. Time-series page:
  `https://isramar.ocean.org.il/isramar_data/TimeSeries.aspx` (loads, pulled 2026-10-01T16:43Z).
- Stations listed: IOLR_Buoy_Meteo, HaderaRDI, ShikBuoyCTD, HaderaLevel, AshkelonRDI, ShikBuoyRDI,
  IOLR_Roof_Meteo, AshkelonCTD, ShikBuoyTw, HaderaCTD. Quality classes NRT and DLY. Date range
  offered: 2011-03-22 to 2026-09-30.
- **Download test:** the download button reads "Log In for Download" and is disabled. The download
  guide page says data are "available after log in for registered users only", with a register
  link. I did not sign up (out of scope; no accounts created by this leg). Cruise data
  (`CastMap.aspx`, `DownloadGuid.aspx`) need the same login.
- Gulf of Eilat: `GulfofEilat.aspx` only links IOLR PDF reports (Gulf of Elat IOLR reports, thermal
  water climate, organic and metal pollutants). There is no downloadable Eilat database there.
- What is open without login:
  - Hadera station images, `https://isramar.ocean.org.il/isramar2009/station/HaderaCTD.aspx`
    (plots only, no machine-readable CTD data). `HD_Temp_Salinity.png` was updated
    2026-10-01 16:37 GMT and shows 13 m temperature about 28.4-28.9 C and salinity about
    39.40-39.50 PSU for 09-27 to 10-01. **`HD_Fluor_Turbid.png` (fluorescence, 13 m, mg/m3)
    ends 2025-12-03** (Last-Modified 2025-12-23). Fluorescence is the one that matters here.
  - Hadera wave JSON, `https://isramar.ocean.org.il/isramar2009/station/data/Hadera_Hs_Per.json`:
    `{"datetime":"2026-10-01 16:00 UTC", ...}`, Hs 1.14 m, peak period 7.3 s, Hmax 1.4478 m. Live.
  - Ashkelon: AshkelonCTD and AshkelonRDI pages say "Data from this station is temporarily not
    accessible!".
- Terms: terms page says data are "a public service" and the user is solely responsible; the
  Hebrew footer says no use of the data without written permission from IOLR. Treat reuse as
  needing written permission; **do not republish ISRAMAR data in the repo**.

**Status: NEEDS-SIGNUP** (Hadera fluorescence plot: STALE 2025-12-03; Ashkelon stations: STALE, "temporarily not accessible")

## 10. ISRAMAR shelf currents forecast (SELIPS)

- URL: `https://isramar.ocean.org.il/isramar2009/selips/default.aspx` (loads, pulled 2026-10-01T16:44Z).
- Page shows "Forecast time: 2026-08-22 12:00" and "No Images Available". Forecast is about
  40 days old.
- `https://isramar.ocean.org.il/CurrentsBuoy/default.asp` returns "Page not found".
- Wave-model pages (`.../wave_model/default.aspx?model=swan`) return 200 but are not currents.
- Same IOLR terms as row 9.

**Status: STALE 2026-08-22** (the legacy CurrentsBuoy page: DEAD)

## 11. IUI Eilat National Monitoring Program, "available data"

- New landing page: `https://iui-eilat.ac.il/en/available-data` (HTTP 200, pulled 2026-10-01).
  Siblings: `.../en/about-monitoring-program`, `.../en/nmp-reports`, `.../en/nmp-methods`,
  `.../en/nmp-team`. The old `Research/NMPMeteoData.aspx` and `Research/NMPAbout.aspx` links redirect
  or 404.
- Page text: all NMP data is open for public download and use. Two groups: meteorological (pier
  station, continuous, Israeli winter time GMT+2) and ecological/oceanographic from survey
  campaigns (released after QC; `.asc` / `.cmv` comma-separated text). The page asks for
  acknowledgement: "National Monitoring Program of Israel in the Gulf of Eilat" plus a link.
- Data endpoints are hosted on meteo-tech.co.il:
  `http://www.meteo-tech.co.il/EilatYam_data/ey_data.asp` and
  `https://www.meteo-tech.co.il/EilatYam_data/ey_ctd_data_download.asp`. **Both return a Cloudflare
  "Sorry, you have been blocked" page** to curl, to the fetch tool, and to a real Chrome tab, with
  no login prompt. I did not try to get around it. `https://yameilat.huji.ac.il/` also returned a
  block page to curl.
- Alternative: coral station dashboard `https://iui-orders.huji.ac.il/pam-dashboard-cms-i-open-reef`
  (found by search, not tested).
- Consequence: the data is public in principle, but cannot be read by an unattended job from this
  Mac today. Resolve by asking IUI (outward-facing; Shay's call) or by saving files manually once.

**Status: DEAD** for automation (landing page WORKS; data host blocked)

## 12. MoEP freedom-of-information marine-monitoring PDFs

Found by search plus one real-browser read (gov.il returns HTTP 403 to curl and to the fetch
tool, but loads in Chrome). Nothing was bulk-downloaded and no PDF was opened.

- Desalination policy page (read in Chrome 2026-10-01):
  `https://www.gov.il/he/pages/desalination_facilities_moep_policy`. Lists the 2021 plant status
  with annual output (Ashkelon 121 MCM, Hadera 137-159, Ashdod 100, Palmachim 90-105, Sorek
  152-180) and planned plants (Sorek 2, Western Galilee, Emek Hefer, 200 MCM/yr each). Attached
  policy PDFs: 2002 Mediterranean policy, 2008 addendum on discharge to sea, 2002 guidelines for a
  background and follow-up marine monitoring programme, 2008 opinion on iron and additives in
  backwash, 2008 note on landfilling filter solids.
- Environmental data FOI collector, titled "Freedom of information - environmental data":
  `https://www.gov.il/he/Departments/DynamicCollectors/freedom-of-information`. The page loads
  in Chrome, but its result list did not render in the browser tool, so the per-site marine
  reports could not be enumerated. Search results say monitoring reports sit there.
- National marine monitoring summary (found by search, not opened):
  `https://www.gov.il/BlobFolder/reports/monitoring_the_marine_environment/he/marine_coastal_environment_monitoring_marine_environment_2017.pdf`
- Plant-side reports exist too, for example IEC's Rutenberg site marine monitoring 2021 PDF (found
  by search, not opened).
- Terms: gov.il general terms apply; reports are FOI publications. Read once per plant by hand;
  do not scrape.

**Status: WORKS** in a browser (per-plant report list not enumerated; open item for Shay)

## 13. Natural Earth 10 m land polygons (bundled coastline for the PNG map)

- URL: `https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson`
  (also `https://www.naturalearthdata.com/downloads/10m-physical-vectors/`). Used once, by hand, by
  `scripts/build_coastline.py`, which clips it to two regions (eastern Mediterranean, northern Red
  Sea) and writes `dbw/data/coastline.json` (21,120 bytes). The report never fetches it at run time.
- Licence, read at `https://www.naturalearthdata.com/about/terms-of-use/` on 2026-10-01: "All
  versions of Natural Earth raster + vector map data found on this website are in the public
  domain." No attribution required; the report still prints "Made with Natural Earth".
- Caveat: at 10 m scale the coast is coarse for a 4 km pixel map. An intake marker can sit on or
  just past the drawn coastline. Drawn position is indicative only.

**Status: WORKS**

## 14. NASA GIBS true-colour underlay for the report map (`--basemap gibs`)

- URL: `https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS=VIIRS_NOAA20_CorrectedReflectance_TrueColor&CRS=EPSG:4326&BBOX=31,32.5,33.5,35&WIDTH=600&HEIGHT=600&FORMAT=image/jpeg&TIME=2026-09-29`
  (BBOX order is lat_min,lon_min,lat_max,lon_max.) No key.
- Pulled 2026-10-01T21:50Z: HTTP 200, `image/jpeg`, 86,469 bytes. `tests/test_live.py` fetches a real
  image and checks it is not blank (`pytest -m live -k gibs`).
- Off by default and never on the daily path. A failed or blank fetch (GIBS returns a blank image
  for a date with no pass) falls back to the plain map and the report says why.
- Licence: NASA EOSDIS open data policy, free use. The report prints the acknowledgement only when
  the underlay was actually used: "we acknowledge the use of imagery provided by services from
  NASA's Global Imagery Browse Services (GIBS), part of NASA's Earth Science Data and Information
  System (ESDIS)."

**Status: WORKS**

---

## FINDINGS for the plan

1. **History is shorter than the plan assumes.** N20 chl starts 2021-08-26, S-NPP 2025-09-22,
   OLCI sectors keep only about 90 days. Only DINEOF (2020-05-05) and the anomaly ratio
   (2018-08-06) go further back. The §4 "seasonal percentiles from 2018" needs DINEOF, a
   NOAA-20 + S-NPP merge with a bias check, or Copernicus Marine.
2. **300 m works for Eilat.** A sea-only OLCI box gave mean 0.109-0.168 mg/m3 on valid days, while
   the 4 km N20 box that touches the coast has a max up to 0.586. Cloud NaN is common (3 of 6 days
   all NaN).
3. **Licences:** CoralTemp text has an OSTIA academic-only clause; Open-Meteo free tier is
   non-commercial; ISRAMAR needs written permission; Copernicus credit string for OLCI.
4. **Israeli in-situ data is not usable automatically today:** ISRAMAR needs a login, Hadera
   fluorescence stopped 2025-12-03, Ashkelon stations are down, SELIPS is stale, IUI data host is
   Cloudflare-blocked. The plan already treats these as an optional plugin; confirmed.
