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

## Sources not yet integrated (and why)

| Source | Status | Why not yet |
|---|---|---|
| NHTSA CRSS (non-fatal crash estimates) | Phase 2 | Adds depth to FARS-style crashes; not essential for v1's two-source MVP. |
| City/county open-data portals (Vision Zero etc.) | Phase 3 | Coverage varies wildly by city; needed for any real rate-based hotspot work, paired with exposure data. |
| Ridership/exposure (GBFS, Strava Metro) | Phase 3 | The hardest gap — no national denominator exists at all; only a few cities publish anything usable. |
| OpenStreetMap / infrastructure context | Phase 3 | Legitimate role is bike-lane/intersection context near a known crash point, not crash detection. |
| Court records (PACER, state systems) | Phase 4 | Fragmented, slow, sparse coverage; needs careful "adjudicated outcome, not AI fault" framing. |
| News ingestion | Phase 4 | Only source for many individual crashes federal data misses, but the dedup/verification/privacy burden is high — explicitly lower-confidence tier when added. |
| Satellite/aerial crash detection | **Not planned** | Doesn't work for crash detection. Confirmed dead end; imagery's only legitimate use here is static infrastructure context. |
