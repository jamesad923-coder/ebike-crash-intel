# Data sources, lineage, and known limitations

Every artifact in `web/data/*.json` carries a `provenance` block matching the
detail below. This file is the canonical explanation; the in-app banners are
the short version.

## FARS — Fatality Analysis Reporting System (NHTSA)

- **What it is:** a census (not a sample) of fatal crashes involving a motor
  vehicle on a public road in the U.S.
- **Access:** `https://static.nhtsa.gov/nhtsa/downloads/FARS/{year}/National/FARS{year}NationalCSV.zip`
  — no authentication, no bot-blocking, fully scriptable. Verified live for
  2022 and 2023 (2026-06-20).
- **Files used:** `accident.csv` (location/time/lighting), `person.csv`
  (who, age, sex, injury severity), `pbtype.csv` (PBCAT pre-crash typing).
- **Who counts as a pedalcyclist:** `PER_TYP` 6 (Bicyclist) and 7 (Other
  Pedalcyclist). `PER_TYP` 8 (Person on a Personal Conveyance — e.g.
  scooters/skateboards) is tracked separately and NOT folded into bike
  counts.
- **Sentinel/unknown values handled:** age 998/999 -> "Unknown" age band;
  lat/lon 77.7777/88.8888/99.9999 (and out-of-US-bounds values) -> dropped
  from the map, kept in totals as "unknown location."
- **Known limitations (surfaced in the UI):**
  - Only crashes involving a motor vehicle on a public road. Single-bike
    falls are excluded entirely — this is the majority of real-world e-bike
    incidents, and FARS simply does not have them.
  - E-bikes are included with conventional bikes starting in the 2022 data
    year (motorized bicycles count as pedalcycles), but **cannot be
    separated** from regular bikes — there is no e-bike flag in FARS.
  - `HELM_USE` is a motor-vehicle-occupant field and is not reliably
    populated for cyclists (it reads "Not a Motor Vehicle Occupant" for
    essentially all pedalcyclist records in 2022-2023). Do not use FARS for
    helmet correlation — that's a NEISS question, and NEISS doesn't capture
    it well either (see below).
  - ~1-2% of records per year have unknown/invalid lat-lon and are omitted
    from the map (kept in summary totals).

## NEISS — National Electronic Injury Surveillance System (CPSC)

- **What it is:** a statistical sample of ER visits from ~100 hospitals,
  weighted to produce *national estimates* — not a census, not raw counts.
- **Access:** `https://www.cpsc.gov/cgibin/NEISSQuery/Data/Archived%20Data/{year}/neiss{year}.tsv`
  — this path is correct, but CPSC's server sits behind Akamai
  bot-protection that returns HTTP 403 to any scripted request (curl,
  Python `urllib`/`requests`), even with realistic browser headers. A real
  browser session passes. **This means NEISS refresh is a yearly,
  semi-manual step** (see `etl/neiss/fetch_neiss.py` for the exact
  procedure) — not a fully unattended pipeline like FARS. Verified live via
  an actual browser session (2026-06-20): the 2024 file is ~76MB / 361,673
  total records across all consumer products.
- **Product codes used** (sourced from the CPSC NEISS Coding Manual, Jan
  2019, and the CPSC Micromobility Products report 2017-2024):
  - `5045` — E-bikes (electric power-assisted pedal bicycles). **Introduced
    in 2024.** This is the only reliable, isolated e-bike code in NEISS.
  - `5040` — Bicycles. **Before 2024, e-bikes are inside this code,
    indistinguishable from conventional bikes** in any scripted extract.
    CPSC itself only separates them via manual case-by-case investigation
    of ER narratives (their "special studies"), which this open pipeline
    does not have access to or attempt to reproduce.
  - `5046` — Bicycles, non-powered (introduced 2024 alongside the 5045 split).
  - `5022`/`5023`/`5024` — powered/unpowered/unspecified scooters (2020+).
  - `5025` — self-balancing scooters / hoverboards.
  - `5042` — legacy "scooters/skateboards, powered" code, used 2017-2019
    only, since replaced by the above.
- **Diagnosis/body-part/disposition codes:** transcribed directly from the
  CPSC NEISS Coding Manual (`etl/neiss/codes.py`). The "head/brain-related"
  rollup shown in the dashboard combines diagnosis 52 (Concussion) and
  diagnosis 62 (Internal organ injury) *only when paired with body part 75
  (Head)* — this is an explicit, labeled rollup, not a clinical TBI
  diagnosis, because NEISS does not code TBI directly.
- **Known limitations (surfaced in the UI):**
  - All figures are weighted **estimates**, not counts — we sum the NEISS
    `Weight` field. This project does not currently compute or display
    confidence intervals around those estimates (a real gap — flagged
    explicitly, not hidden). Small slices (e.g. fatalities, with a raw
    sample n typically under 30) carry very wide uncertainty; FARS is the
    better source for fatal pedalcyclist figures.
  - **No location field at all.** NEISS cannot be mapped or compared
    city-to-city under any circumstance.
  - Captures only injuries severe enough to bring someone to a sampled ED —
    undercounts minor injuries and misses anyone who didn't seek ED care.
  - Helmet use is not a structured NEISS field; any helmet signal would
    have to come from the free-text narrative, which this pipeline
    deliberately excludes from its raw extract for privacy reasons (see
    below).
- **Privacy handling:** the raw NEISS extract this project keeps
  (`data/raw/neiss/neiss{year}_micromobility.tsv`) explicitly drops
  `CPSC_Case_Number` and `Narrative_1` (free-text ER narrative) before being
  written to disk — only coded fields are retained. NEISS source data is
  already de-identified by CPSC; this is an extra precaution, not a fix to
  an existing leak.

## News-sourced reports (GDELT)

- **What it is:** an automated scan of GDELT's free global news index
  (`https://api.gdeltproject.org/api/v2/doc/doc`, no key required) for
  articles matching device terms (e-bike, e-scooter, hoverboard, etc.) AND
  crash/injury terms, run on a rolling window (default 7 days).
- **This is the only source in this project that can show something that
  happened yesterday** -- FARS and NEISS lag months to years. See
  AUTOMATION.md for how (and whether) this actually runs unattended.
- **Extraction is heuristic, not a person or an LLM:** `etl/news/extract.py`
  fetches each candidate article's text and pattern-matches a device
  keyword, a crash/injury keyword, an age phrase (mapped to a BAND, never an
  exact age), and a location. Location extraction tries, in order: an
  AP-style dateline, a looser "City, ST" mention anywhere in the text, a
  "X County" mention combined with a curated outlet-domain-to-state table,
  or the outlet's home state alone (too coarse to map). If none of these
  produce a confident match, the report is listed but NOT placed on the
  map -- no invented coordinates.
- **Geocoding cross-validation:** a non-empty Nominatim (OSM) result is not
  trusted blindly -- we found in testing that it will fuzzy-match garbage
  queries to real coordinates (a false-positive extracted place, "Promise,
  MO" from a Title-Case headline fragment, geocoded to real coordinates in
  St. Louis). We now require the result's own structured fields (place
  type, address state, name overlap) to corroborate what we searched for,
  rejecting the match otherwise.
- **Confidence tiers, shown on every report:** "corroborated" (2+
  independent domains, same city/state/device/outcome, within a 3-day
  window) or "single_source" (one outlet). Neither tier means verified by
  this project -- both are automated signals, not human review.
- **Privacy:** only city/county + age BAND + device + outcome + source
  link(s) are ever written to the public artifact. Article headlines (which
  can themselves name a minor) are used internally for dedup matching only
  and are explicitly excluded from `web/data/news_*.json` -- see the
  `_internal_title_for_dedup_only` field comment in `etl/news/extract.py`.
- **Known limitations:** early news reports can be wrong about cause or
  severity; heuristic extraction will have false positives and false
  negatives we haven't found yet (two specific ones caught during this
  project's own testing are documented in AUTOMATION.md); GDELT itself can
  rate-limit a shared IP, which a scheduled run (its own dedicated IP) is
  less exposed to than ad-hoc testing was.
- **Throttle-vehicle flag:** federal data (NEISS/FARS) has no e-bike Class
  1/2/3 or throttle-vs-pedal-assist field at all -- there is no way to get
  a clean class breakdown from any source this project has access to. News
  text sometimes names a specific throttle-capable vehicle (Sur-Ron,
  "electric dirt bike," "e-motorcycle," moped-style, etc.) that may not
  legally be a Class 1-3 e-bike. We flag this from text as
  `throttle_ambiguous: true`, separate from the device label -- a real
  example caught in testing: Carson Farias's vehicle was described in
  coverage as "his small electric dirt bike." This is a text-keyword
  signal, not a verified vehicle classification.

## CRSS — Crash Report Sampling System (NHTSA)

- **What it is:** the non-fatal sibling of FARS -- a nationally
  representative PROBABILITY SAMPLE of police-reported crashes (it
  excludes fatal crashes entirely; those stay in FARS). Same file
  structure as FARS (`accident.csv`, `person.csv`, `pbtype.csv`) and the
  same `PER_TYP` pedalcyclist coding (6=Bicyclist, 7=Other Pedalcyclist),
  but every row carries a sample `WEIGHT` -- summing weights gives a
  national estimate, not a raw count -- and there is **no
  latitude/longitude** at all, so CRSS cannot be mapped, only used for
  national-level statistics.
- **Access:** `https://static.nhtsa.gov/nhtsa/downloads/CRSS/{year}/CRSS{year}CSV.zip`
  -- no authentication, no bot-blocking, fully scriptable, verified live
  for 2022 and 2023.
- **Why kept separate from the FARS factor profile, not merged:** FARS is
  an unweighted census (each row = one real fatal crash); CRSS is a
  weighted sample. Adding a FARS row-count to a CRSS weighted-sum would
  mix two different kinds of number and misrepresent both. The dashboard
  shows them as two toggleable, clearly-labeled views instead.
- **Real finding from combining the two:** the most common FATAL crash
  type is "Motorist Overtaking Bicyclist," but the most common NON-FATAL
  crash type is "Crossing Paths" / "Failed to Yield" -- consistent with
  overtaking crashes at speed being more likely to prove fatal than
  intersection/crossing conflicts. Neither profile alone would show this;
  having both, kept honestly separate, does.

## Census ACS — bike-commute exposure proxy

- **What it is:** American Community Survey 5-year estimates, table B08301
  ("Means of Transportation to Work"), variable B08301_018E (Bicycle) over
  B08301_001E (Total). Used as a state-level cycling-prevalence proxy to
  turn a FARS fatality COUNT into a rate.
- **Access:** `https://api.census.gov/data/2022/acs/acs5` -- as of May 2026
  Census requires a free API key for every request (previously
  rate-limited but key-optional). Sign up at
  `https://api.census.gov/data/key_signup.html`; the key must be activated
  via a link in the confirmation email before it works. Read from the
  `CENSUS_API_KEY` environment variable (a GitHub Actions secret in CI, a
  gitignored `.env.local` for local dev) -- never hardcoded.
- **Known limitation, repeated everywhere this data is used:** this is a
  COMMUTE-cycling proxy, not a ridership count. It misses recreational
  riding, delivery riding, and any trip by someone under working age --
  exactly the population most central to e-bike injuries. We use it
  because it's the best available free federal proxy, not because it's a
  good fit. A state can rank very differently on raw fatality count vs.
  this rate-adjusted measure; the dashboard shows both, side by side, on
  purpose.

## Risk & Prevention layer (this project's own model)

Three interpretable components, all built from FARS + ACS data already
described above -- no new external source, no opaque machine learning:

1. **State ranking** -- FARS fatalities ÷ ACS bike-commute proxy, per
   10,000 commuters. See the ACS caveat above.
2. **Factor profile** -- cross-tab of PBCAT crash type by lighting and
   time-of-day, from FARS `pbtype.csv`/`accident.csv`. Every combination
   shows its sample size; a 3-case pattern is displayed as a 3-case
   pattern, not implied to carry the same confidence as a 300-case one.
3. **Cluster flags** -- coarse (~0.15-degree) geographic binning of FARS
   fatality points, flagging areas with 3+ documented fatalities. This is
   a raw-count density flag, explicitly NOT an exposure-adjusted risk
   rate -- we have no street-level ridership data (see "Ridership/exposure"
   below). A busy urban area will appear here partly because more people
   ride there, not necessarily because it's more dangerous per rider.

Each factor-profile entry is paired with a prevention lever -- a citation
from FHWA/NACTO/NHTSA road-safety guidance matched to the PBCAT crash type,
defined in `etl/risk/prevention_levers.py`. These are NOT claims that our
data proves the lever works; they're pointers to where that evidence
already exists in the literature.

## DC Pilot — first city-level crash source

- **What it is:** the project's first crash source finer than national/
  state. Two real, verified, live feeds:
  1. **Open Data DC bicycle crashes** (DDOT/MPD COBALT system) --
     `https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Public_Safety_WebMercator/MapServer/24`,
     an ArcGIS FeatureServer, no key required. Confirmed live: 7,378
     bicycle-involved crash records with exact lat/lon, ward, and a
     PER-CRASH severity breakdown (`FATAL_BICYCLIST`,
     `MAJORINJURIES_BICYCLIST`, `MINORINJURIES_BICYCLIST`,
     `SPEEDING_INVOLVED`). `maxRecordCount` is 1000 -- `fetch_dc_crashes.py`
     paginates via `resultOffset` to get the full set; a naive single
     query would silently truncate to the first 1000 records.
  2. **Capital Bikeshare trip history** --
     `https://s3.amazonaws.com/capitalbikeshare-data/{YYYYMM}-capitalbikeshare-tripdata.zip`,
     published monthly, no key required. Genuinely **e-bike-specific**
     (`rideable_type` field distinguishes `electric_bike` from
     `classic_bike` per trip) -- a real find, rarer and better-targeted
     than the ACS commute proxy used at the state level. Confirmed live:
     e-bike trips are 68-74% of all Capital Bikeshare trips every month
     checked (Jan-May 2026).
- **Station-to-ward mapping (built):** `etl/dc/ward_boundaries.py` fetches
  DC's official "Wards from 2022" polygon layer
  (`https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Administrative_Other_Boundaries_WebMercator/MapServer/53`,
  found via the ArcGIS Online item-search API, same pattern as the crash
  layer) and does a plain ray-casting point-in-polygon test (the 8 ward
  polygons are single-ring, no holes -- confirmed directly, no GIS
  library needed). Verified against known landmarks (White House -> Ward
  2, Eastern Market -> Ward 6, Adams Morgan -> Ward 1, etc.) before
  trusting it. Each Capital Bikeshare station's trip data
  (`fetch_capital_bikeshare.py:fetch_month_by_station`) is mapped to a
  ward this way, giving a REAL per-ward bikeshare-activity figure instead
  of citywide-only context.
- **Why this still isn't a true per-ward RISK rate, even with real
  station-to-ward mapping:** the numerator (ward crash counts) includes
  ALL cyclists -- personal bikes, personal e-bikes, AND bikeshare riders.
  The denominator (bikeshare trips) counts ONLY Capital Bikeshare's
  fleet. These are different, overlapping-but-not-identical populations.
  `ward_exposure.measure_note` in the output (and the dashboard) calls
  this "crashes relative to bikeshare activity," explicitly not
  "risk per rider" -- the distinction matters and is stated every place
  the number appears, not just here. Both crash counts and trip counts
  in this specific comparison are restricted to the same Jan-May 2026
  window (the only window where both data sources actually overlap;
  the ward crash table elsewhere on the page uses a longer 5-year window
  for more statistical power on its own, separate question).
- **Real finding:** Wards 7 and 8 (east of the Anacostia River, lower
  bikeshare ridership) rank HIGHEST on crashes-per-1,000-bikeshare-trips
  (0.66 and 0.57), while Ward 2 (highest raw crash count AND highest
  bikeshare activity) ranks LOWEST (0.15) -- the same kind of inversion
  BikeMaps.org found with Strava data (busy, well-served areas look
  "dangerous" on raw counts partly because more riding happens there).
  About 14% of bikeshare trips in the dataset (213,811 of ~1.5M across
  5 months) start at stations outside DC proper (Arlington VA, Alexandria
  VA, Bethesda MD, Reston VA -- confirmed by inspecting the actual
  unmapped station names) and are excluded from ward totals rather than
  forced into the nearest ward.
- **Known limitations:** DC's crash data has no e-bike-specific flag
  either (same gap as FARS/NEISS/CRSS) -- ward counts are all bicycle
  crashes, e-bikes included but not isolated. Capital Bikeshare data
  covers only its own fleet, not personally-owned e-bikes (most of what
  the news-sourced fatality reports involve). The main ward table (5-year
  window, for statistical power) is still a raw count with no exposure
  adjustment; the separate ward-exposure comparison above addresses this
  partially, for the shorter overlapping window, with the population
  caveat already stated.
- **Date-window correction (caught by the user, fixed):** the raw crash
  dataset actually spans 1996-2026, but reporting was sparse and
  inconsistent before roughly 2016. The ward table originally summed
  all 30 years into one cumulative total -- which would make a ward
  look worse partly because it's been recorded longer, not because it's
  more dangerous now. Fixed: `transform_dc.py` now filters to a fixed,
  recent window (the most recent 5 years, computed dynamically from the
  data's own max date) and reports BOTH the windowed and all-time record
  counts, plus the exact date range, explicitly in the dashboard -- not
  just in this file.
- **Real finding (in the corrected 5-year window, Jan 2022-Jun 2026):**
  Ward 7 had 3 bicyclist fatalities from 128 crashes on record, vs.
  Ward 1's 0 fatalities from 418 crashes -- a worse fatal-outcome ratio
  in Ward 7, consistent with documented infrastructure disparities east
  of the Anacostia River. These are still small counts (a handful of
  fatalities citywide), so this is stated as a pattern worth
  investigating, not statistically robust proof of a real disparity.
- **This is a proof of concept**, not a template assumed to generalize:
  whether other cities have comparably good open data (exact crash
  coordinates, per-mode severity breakdown, AND a bikeshare system that
  actually distinguishes e-bike trips) would need to be checked city by
  city, the same way DC was verified here rather than assumed.

## DC Pilot — OpenStreetMap bike-lane infrastructure context

- **What it is:** the "why" layer for the DC crash data above -- was
  there a marked/protected bike lane near where a crash happened? Fetched
  via the free Overpass API (`https://overpass-api.de/api/interpreter`,
  no key required) for DC's bounding box, matching `highway=cycleway` and
  `cycleway`/`cycleway:left`/`cycleway:right`/`cycleway:both` =
  `lane`/`track`/`opposite_lane` tags. Confirmed live: 5,375 way segments,
  38,877 geometry points.
- **A real syntax bug worth knowing about if extending this:** Overpass
  QL requires quoting tag KEYS that contain a colon --
  `way["cycleway:left"="lane"]` is correct, `way[cycleway:left=lane]`
  returns HTTP 400. Found by testing directly, not assumed.
- **Method:** grid-indexed nearest-vertex distance (not true point-to-
  line-segment geometry) -- DC's OSM cycleways are densely vertexed
  (10-12 points per short urban segment, confirmed directly), so nearest-
  vertex is a reasonable stand-in without a GIS library dependency. A
  crash is flagged "near a bike lane" if within 30 meters of any lane
  vertex -- chosen to absorb GPS/mapping imprecision in both datasets,
  not as a precise "the lane was right there" claim. Verified against a
  known true-positive (an exact lane vertex coordinate) and a known
  true-negative (200m offset) before trusting it.
- **Critical framing, stated in the data and the dashboard, not just
  here:** this is infrastructure CONTEXT, never a cause and never crash
  DETECTION -- the brief is explicit that imagery/OSM cannot detect
  crashes; this only explains the road environment around crashes DC's
  own MPD data already documented.
- **Real finding, ties together with the ward-exposure data above:**
  Wards 7 and 8 -- the same two wards that rank WORST on
  crashes-per-1,000-bikeshare-trips -- also have by far the LOWEST share
  of crashes occurring near a mapped bike lane (7% and 4%, vs. 45-53% in
  Wards 1, 2, and 6). Visually obvious on the map too: the green lane
  network is visibly sparser east of the Anacostia River. Consistent
  with documented infrastructure disparities, not proof of a causal
  mechanism on its own.
- **Known limitation:** OSM is crowdsourced/volunteer-mapped, not an
  official DDOT bike-lane inventory (though it draws heavily from one) --
  coverage and accuracy depend on contributor activity, and a real lane
  could exist but not be mapped, or vice versa.

## Chicago Pilot — second city, verified independently

- **What it is:** the second city-level pilot, built only after checking
  Chicago's data on its own terms -- not assumed to work just because DC
  did. Two real, verified, live feeds:
  1. **Chicago Data Portal** (Socrata) -- "Traffic Crashes - People"
     (`u6pd-qa9d`) filtered to `person_type='BICYCLE'`, joined in Python
     to "Traffic Crashes - Crashes" (`85ca-t3if`) via `crash_record_id`
     for lat/lon and conditions (Socrata can't join across datasets
     server-side). Confirmed live: 11,162 bicyclist records since
     2021-01-01, 99.8% successfully geo-joined.
  2. **Divvy trip history** (`https://s3.amazonaws.com/divvy-tripdata/`) --
     Divvy is operated by Lyft, the same company as Capital Bikeshare,
     and publishes the IDENTICAL schema including the e-bike-specific
     `rideable_type` field. ~67-70% of trips checked were `electric_bike`.
     Genuinely simpler than DC's case: every trip row carries its own
     lat/lon directly (even the ~21% with no station_id -- dockless
     e-bike trips), so no station-to-coordinate lookup is needed first.
- **Two fields Chicago has that DC's data didn't, both DIRECTLY
  police-reported (not an estimate):**
  - `safety_equipment` -- helmet use, a real correlation field no other
    source in this project has cleanly. ~34% of records with a known
    value showed a helmet was used.
  - `pedpedal_location` -- whether the bicyclist was reported "IN BIKE
    LANE" vs "IN ROADWAY"/etc. at the time of the crash. More reliable
    than DC's OSM-proximity estimate (which only tells you a lane was
    NEARBY, not that the cyclist was using it) -- but still only as
    accurate as what the reporting officer observed and recorded.
- **A real performance problem, found and fixed:** the initial ward
  lookup (bounding-box pre-filter + full point-in-ring test per call)
  did not finish in a reasonable time against Chicago's real data volume
  (~1.7M Divvy trip points to map). Fixed by precomputing a grid
  rasterization ONCE at startup (test each ~150m grid cell's center
  against the ward polygons a single time, cache the result), turning
  every actual per-point lookup into an O(1) dict access. Setup cost
  ~13 seconds; the full pipeline (crash join + 5 months of trip mapping)
  completed in under 30 seconds afterward. Tradeoff made explicit: this
  approximates true polygon boundaries at ~150m grid resolution, so a
  thin band of points right at a ward boundary could be assigned to the
  adjacent ward -- accepted as a small, known imprecision for citywide
  aggregate analysis, not exact-everywhere geometry.
- **A real URL-length bug, found and fixed:** the person-to-crash join
  initially batched 200 `crash_record_id` values per query (each ID is
  ~128 hex characters) and hit HTTP 414 (Request-URI Too Large).
  Reduced to batches of 25.
- **Privacy:** the People dataset includes exact age per record (a real
  11-year-old's exact age appeared in a sample record pulled during
  development) -- age-banded immediately using this project's existing
  `age_band()` function, the same privacy rule applied everywhere else;
  exact age is never stored or displayed.
- **Known limitation:** the 2021 cutoff matches DC's window LENGTH as a
  consistency choice -- it is not a claim that Chicago's pre-2021
  reporting was separately verified for consistency the way DC's 2016
  cutoff was (DC's actual per-year record counts were checked directly;
  Chicago's were not, beyond confirming the dataset's full range).
- **OSM bike-lane layer added too** -- same Overpass API approach as DC
  (`etl/chicago/fetch_bike_lanes.py`, bounding box derived directly from
  the ward polygon coordinates rather than guessed). Confirmed live:
  7,600 way segments, 52,823 geometry points. The proximity-index module
  (`etl/dc/bike_lane_proximity.py`) is fully generic and reused as-is for
  Chicago, no duplication. Chicago is the only pilot with BOTH signals
  shown side by side, deliberately not reconciled into one number:
  `in_bike_lane` (direct police report) and `near_mapped_bike_lane`
  (~30m OSM-proximity estimate, same method as DC) -- they can and do
  disagree (the near-lane count runs consistently higher than the
  reported-in-lane count across every ward checked), since OSM coverage
  and an officer's on-scene call are two different, imperfect signals.

## Boston Pilot — third city, and a case study in upstream breakage

- **Source:** City of Boston Vision Zero Crash Records + Vision Zero
  Fatality Records (data.boston.gov, CKAN portal). Bluebikes trip data
  (hubway-data S3 bucket) for e-bike exposure context; Boston City Council
  District boundaries for point-in-polygon district assignment.
- **The 2026 source change that matters:** Boston migrated off Socrata and
  the republished crash CSV **dropped its severity field entirely** — there
  is no fatal/injury/no-injury coding in the public data anymore. The
  pipeline recovers an approximate fatal flag by fuzzy-matching the
  separate fatality dataset on timestamp (±6h) + location (~1km), since
  the two files share no id. Manually verified: ~8/11 known bike
  fatalities match confidently; the rest stay unmatched rather than
  guessed. **Boston's fatal count is a documented lower bound, not exact.**
- Window: 2021-01-01 onward (~5 years, matching DC/Chicago as a
  consistency choice). No e-bike flag, no speeding field, no injury
  severity — all stated in the UI banner.
- Full details and the honesty limits: `etl/boston/*.py` docstrings.

## NYC Pilot — fourth city, the largest dataset

- **Source:** NYC Motor Vehicle Collisions (NYPD, data.cityofnewyork.us),
  filtered to crashes with ≥1 cyclist injured or killed; borough comes
  directly from the NYPD record. Citi Bike monthly trip files (NYC fleet
  only, Jersey City excluded) for exposure context; Borough Boundaries
  dataset `gthc-hcne` (the older `7t3b-ywvw` id was retired upstream).
- **Data-quality catch worth remembering:** 340 NYPD records carry
  placeholder coordinates at exactly (0, 0) — "Null Island" — which parse
  as valid floats and briefly ranked as the city's top crash-concentration
  cell before a bounding-box check was added. Coordinates outside a
  generous NYC bbox are treated as missing (counted in
  `records_excluded_no_geo`), same as any other no-geo record.
- ~27k cyclist crashes across the five boroughs (~21k mappable); no
  e-bike flag (same gap as every city); Citi-Bike-only exposure caveat
  identical to the other pilots.
- Full details: `etl/nyc/*.py` docstrings.

## City data pages, screenings, and reports (derived layers)

Three public layers are **derived** from the sources above rather than new
sources — documented here so nothing looks like it appeared from nowhere:

- **`/cities/` (341 pages)** — per-city FARS aggregates from the raw
  national files (full person/accident join, so totals include records
  without usable coordinates). Only ~67% of pedalcyclist fatality records
  are coded to a city at all (rural/unincorporated crashes usually
  aren't), so **city counts are a floor, not a ceiling** — stated on every
  page. Cities appear at ≥3 fatalities 2019–2024, plus an allowlist of
  towns with active e-bike policy debates (small counts, prominently
  caveated). NYC is coded as both "New York" and "New York City" across
  FARS years and is merged.
- **`/risk-screening/{city}/`** — ~250m grid-cell concentration screening
  over each pilot city's open crash data, with persistence checked across
  window halves. Count-based, not exposure-adjusted, not a prediction —
  the page says so in its own banner.
- **`/reports/{st}/{city}/`** — print-first safety data reports composed
  from the layers above; nothing new is computed there.

## Sources not yet integrated (and why)

| Source | Status | Why not yet |
|---|---|---|
| News ingestion (GDELT) | **Done** | Live -- see "News-sourced reports" above. |
| State-level exposure proxy (ACS bike-commute) | **Done** | Live -- see "Risk & Prevention layer" above. Commute-only; not true ridership. |
| NHTSA CRSS (non-fatal crash estimates) | **Done** | Live -- see "CRSS" above. |
| City/county open-data portals (Vision Zero etc.) | Phase 3 | Coverage varies wildly by city; needed for any real street-level rate work, paired with exposure data. |
| True ridership/exposure (GBFS, Strava Metro) | Phase 3 | The hardest gap — no national street-level denominator exists; only a few cities publish anything usable. ACS commute data is a partial, coarser stand-in at the state level only. |
| OpenStreetMap / infrastructure context | Phase 3 | Legitimate role is bike-lane/intersection context near a known crash point, not crash detection. |
| Court records (PACER, state systems) | Phase 4 | Fragmented, slow, sparse coverage; needs careful "adjudicated outcome, not AI fault" framing. |
| Satellite/aerial crash detection | **Not planned** | Doesn't work for crash detection. Confirmed dead end; imagery's only legitimate use here is static infrastructure context. |
