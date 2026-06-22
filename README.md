# U.S. Pedalcyclist & E-Bike Crash Intelligence (v1)

An open-source dashboard over two federal public-safety datasets, built to
help riders, parents, planners, and journalists see patterns in pedalcyclist
crashes and micromobility injuries — **without inventing certainty the data
doesn't support.**

See [PROJECT_BRIEF.md](PROJECT_BRIEF.md) for the full mission and constraints.

## What this v1 actually is

Three honest, separate views — deliberately not merged, because they answer
different questions, run on different timescales, and cannot be joined:

1. **Fatalities (FARS)** — a map of pedalcyclist fatalities in fatal
   motor-vehicle crashes, 2022-2023, with NHTSA's PBCAT pre-crash-action
   coding (what the report found, not an AI fault call). Federal, annual,
   lags ~1-2 years.
2. **Injuries (NEISS)** — national *estimates* (not counts) of micromobility
   ED visits for 2024, broken out by device, age, and diagnosis, with a
   confirmed e-bike slice. Federal, annual.
3. **Recent reports (news)** — automatically detected crash mentions from
   the last 7 days via GDELT's free news index, city/age-band/device/outcome
   only (never a name or exact age), tagged corroborated vs. single-source.
   This is the only tab that can show something that happened yesterday —
   see AUTOMATION.md for what "automatic" actually requires here and what's
   still a manual step.
4. **Risk & Prevention** — this project's own interpretable model, built
   entirely from FARS + CRSS + Census ACS data (no opaque ML): a
   state-level risk ranking adjusted by a bike-commute exposure proxy, a
   PBCAT contributing-factor cross-tab for BOTH fatal (FARS) and
   non-fatal (CRSS) crashes shown side by side, and raw-count fatality
   cluster flags -- each paired with a sourced, evidence-based prevention
   lever (FHWA/NACTO/NHTSA guidance). See DATA_SOURCES.md for what this
   can and can't honestly claim.
5. **DC Pilot** — the first city-level crash source: 7,378 real,
   geocoded bicycle crashes by ward (Open Data DC), shown alongside
   Capital Bikeshare's e-bike-specific trip data (a real find -- e-bike
   trips are 68-74% of all bikeshare trips every month checked) as
   separate citywide context, not blended into a fake per-ward rate. A
   proof of concept for whether other cities are worth adding next.

## Quick start

Requires Python 3.9+ and no other dependencies (standard library only).

```bash
# 1. Fetch + transform FARS (fully automatic, ~70MB download)
python3 etl/fars/transform_fars.py 2022 2023

# 2. NEISS requires one manual step first (see etl/neiss/fetch_neiss.py
#    docstring — CPSC's server blocks scripted requests). Then:
python3 etl/neiss/transform_neiss.py 2024

# 3. News-sourced recent reports (fully automatic, free, no key —
#    see AUTOMATION.md for how to make this actually run on a schedule)
python3 etl/news/transform_news.py 7d

# 4. Serve the dashboard (it's a static page, no build step)
cd web && python3 -m http.server 8765
# open http://localhost:8765
```

Deploying is the same idea: push `web/` to Vercel, Cloudflare Pages, GitHub
Pages, or any static host. No server, no database, no build step.

## Why this architecture

The underlying data is small (a few thousand FARS records/year, ~20k NEISS
sample rows/year) and updates annually. Running a database + API server for
that would add cost and maintenance for no benefit, so v1 is
**data-as-committed-artifacts + a static page**:

- `etl/` — Python connectors, one per source, each with the honesty
  constraints documented inline (sentinel values, code limitations, sample
  vs. census, etc.)
- `data/raw/` — the original downloaded files (gitignored; regenerate
  via the ETL scripts)
- `web/data/*.json` / `*.geojson` — the small, committed, reproducible
  output artifacts the dashboard reads. Every artifact carries a
  `provenance` block (source, dataset, years, URL, limitations).
- `web/index.html` — the whole frontend. MapLibre GL for the map,
  vanilla JS for filtering/charts, no build tooling.

This will need to change in Phase 3 (city-level data + real-time
exposure/ridership) — see DATA_SOURCES.md for the phase plan.

## What's not here yet, and why

- **Rate-based hotspots.** No national ridership/exposure denominator
  exists. Counts are counts; a busy area looks "dangerous" partly because
  more people ride there. Labeled honestly in the UI.
- **Court/legal outcomes.** Sparse, fragmented across federal/state systems.
  Phase 4.
- **News-sourced crashes.** Valuable for catching what federal data misses,
  but high dedup/verification/privacy risk. Phase 4, lower-confidence tier.
- **City-level street data.** Coverage varies hugely by city. Phase 3.
- **Satellite crash detection.** Doesn't work — confirmed dead end. Imagery's
  only legitimate role here is infrastructure context (bike lanes, etc.),
  not detecting crashes.

## Data lineage and limitations

See [DATA_SOURCES.md](DATA_SOURCES.md) for exact source URLs, code
definitions, sentinel-value handling, and known gaps per dataset.
