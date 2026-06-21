# Claude Code Prompt — U.S. E-Bike Crash Intelligence & Prevention System


---

You are my engineering partner on an open-source public-good project. Read this whole brief, then **do not write any code yet** — your first job is to plan with me (see "How we'll work" at the bottom).

## The mission

Build an open-source **U.S. E-Bike & Micromobility Crash Intelligence System**: a platform that aggregates public data on e-bike crashes across the United States, surfaces *where*, *which bikes*, and *what factors* drive crashes, models *risk* so spots and conditions can be flagged before someone gets hurt, and presents it all clearly for the public — riders, parents, city planners, journalists, and the families of people who've been hurt or killed.

## Why this matters (keep this in mind for every design decision)

E-bike injuries have exploded — national ER data shows e-bike injuries roughly 30x higher in 2022 than 2017, and micromobility fatalities have climbed every year. Kids and teens are a real and growing share. Right now this data is scattered across a dozen incompatible federal, state, city, news, and court sources, so no one can see the full picture. If we stitch it together, model it honestly, and open-source it, we can help prevent crashes and bring some clarity to people who've lost someone. **Clarity and honesty matter more than flashy claims here.** Never invent precision the data can't support — a misleading "risk score" shown to a grieving family is worse than no score.

## What the system does (feature scope)

1. **Crash aggregation** — Ingest e-bike/micromobility crash records from public sources into one normalized schema. De-duplicate the same incident reported in multiple places.
2. **Geospatial hotspots** — Map crashes to locations; identify high-risk corridors and intersections. **Critical:** rank by *rate* (crashes per unit of ridership/exposure), not raw counts, wherever exposure data exists — otherwise busy areas always look "dangerous" just because more people ride there. Where exposure is unknown, label counts as counts and say so.
3. **Contributing-factor analysis** — Identify factors associated with crashes: device type/class (Class 1/2/3, throttle vs pedal-assist), speed, time of day, lighting, helmet use, road type, presence/absence of bike infrastructure, weather, rider behavior, driver behavior.
4. **Responsibility — done honestly.** Do **not** have the system assert fault on its own. Instead track (a) *coded contributing factors* from police reports and NHTSA's Ped/Bike crash-typing (PBCAT) — these describe pre-crash actions of the cyclist, the motorist, or other parties — and (b) the *adjudicated outcome* where court records exist. Present "what the report/court found," never "the AI decided whose fault it was." Always show the source and its limits.
5. **Demographics** — Age bands (with explicit attention to minors vs adults vs older adults), and where reliably available, sex and other documented attributes. Be careful and respectful; never expose anything that could identify an individual minor.
6. **Injury & outcome profile** — Injury types (TBI/head, fractures, lacerations, fatality), severity, hospitalization, helmet correlation.
7. **Legal/court tracking** — Where public court records exist, link crashes to case outcomes (settlements, liability findings, charges). Treat as sparse and incomplete.
8. **Risk / prevention modeling** — Probabilistic models that estimate elevated-risk locations, conditions, device types, and rider profiles, paired with **evidence-based prevention levers** (infrastructure, helmet, speed, lighting, education). Every prediction must ship with an uncertainty/confidence indicator and the data behind it.
9. **Public, open dashboard** — Clean, accessible, free. Filter by state/city, device, age, factor, outcome. Built so a parent, planner, or reporter can actually understand it.

## Real data sources to build on (all public — verify current access yourself)

- **CPSC NEISS & CPSRMS** — national ER-injury sample; e-bikes vs e-scooters coded separately since 2021; includes age, sex, body part, diagnosis, narrative. This is the injury/demographic/severity backbone. (NEISS has a public data API/portal.)
- **NHTSA FARS** — census of *fatal* motor-vehicle traffic crashes, 100+ coded fields, no PII, downloadable. *Limitation: only crashes involving a motor vehicle on a public road — single-bike falls are excluded.* Note pedalcyclists include motorized bikes starting 2022.
- **NHTSA CRSS** — nationally representative *non-fatal* crash estimates.
- **NHTSA PBCAT / Ped-Bike crash typing** — codes pre-crash actions → the legitimate, source-backed basis for the "responsibility" feature.
- **City/county open-data portals** (Vision Zero, high-injury networks) — street-level geocoded crashes; coverage varies widely by city.
- **News ingestion** — local news is often the *only* source for an individual crash; use it to catch what federal data misses (treat as lower-confidence, needs verification/dedup).
- **Court records** — PACER (federal) and state/county systems (fragmented) for adjudicated outcomes.
- **OpenStreetMap / road network + aerial/street imagery** — for infrastructure context (bike-lane presence, intersection geometry, road class). *This is the real role of imagery here — not crash detection.*
- **Census / ACS** — population denominators and demographic context.
- **Ridership/exposure** — bikeshare feeds (GBFS), Strava Metro, city counts — needed to turn counts into rates. Flag this as one of the hardest gaps to fill.

## Hard constraints — respect these or the project fails

- **No fabricated certainty.** Surface uncertainty everywhere. Correlation ≠ causation; say so.
- **Privacy, especially minors.** Aggregate and anonymize. Never publish anything that re-identifies an injured individual, particularly a child. FARS/NEISS are already de-identified — keep it that way downstream.
- **The "satellite crash detection" idea doesn't work** — be honest with me about that. Imagery is for infrastructure context only.
- **Data is fragmented and incomplete by design** — different sources use incompatible codes, miss single-bike crashes, lag months/years, and undercount. Build the schema and the UI to make these gaps *visible*, not hidden.
- **Open source & reproducible** — clear licensing, documented data lineage, every number traceable to a source.

## Suggested architecture (propose your own improvements)

I tend to build with **FastAPI (Python) + Next.js**, with a composite-scoring engine pattern. A reasonable shape:
- **Ingestion layer** — per-source connectors (NEISS, FARS, city portals, news, courts), each normalizing into a shared crash schema.
- **Storage** — PostgreSQL + PostGIS for geospatial; raw-source archive for lineage.
- **Processing** — dedup/entity-resolution, geocoding, factor extraction, exposure joining.
- **Modeling** — risk/hotspot models (start simple and interpretable before anything fancy) with confidence outputs.
- **API** — FastAPI serving query + model endpoints.
- **Frontend** — Next.js public dashboard with maps, filters, and prominent data-quality/uncertainty indicators.

## How we'll work (do this first)

1. **Ask me your clarifying questions** — scope for v1 (one city/state vs national? fatal-only vs all-injury first?), my skill level and time, hosting budget, and anything ambiguous above.
2. **Propose a phased plan** — what the smallest genuinely-useful MVP is (I'd guess: one or two solid data sources + a working map + honest filters), then later phases. Tell me what's easy, what's hard, and what's *not realistically possible* with public data.
3. **Recommend the stack and schema** and explain trade-offs.
4. **Wait for my sign-off**, then build incrementally — show me working slices, not a giant code dump.

Start by telling me what you'd want to clarify, and give me your honest read on the most valuable and most realistic v1.
