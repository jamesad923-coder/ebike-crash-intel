# Crash Atlas — U.S. Bicycle & E-Bike Crash Intelligence

An open-source platform over federal, city, and news-sourced crash data,
built to help riders, parents, planners, and journalists see patterns in
bicycle and e-bike crashes — **without inventing certainty the data
doesn't support.** Built by a high school e-bike rider in New Jersey
after too many close calls ([our story](web/about/index.html)).

Live: **https://jamesad923-coder.github.io/ebike-crash-intel/**

See [PROJECT_BRIEF.md](PROJECT_BRIEF.md) for the original mission brief and
[DATA_SOURCES.md](DATA_SOURCES.md) for per-source lineage and limitations.

## What this is

**The dashboard** — honest, separate views, deliberately not merged,
because they answer different questions and cannot be joined:

1. **Fatalities (FARS)** — a map of pedalcyclist fatalities in fatal
   motor-vehicle crashes, **2019–2024**, filterable by year, age band, and
   sex, with NHTSA's PBCAT pre-crash-action coding (what the report found,
   not an AI fault call). Federal, annual, lags ~1–2 years.
2. **Injuries (NEISS)** — national *estimates* (not counts) of micromobility
   ED visits, by device, age, and diagnosis, with a confirmed e-bike slice
   (2024 onward, the first year e-bikes got their own product code).
3. **Recent reports (news)** — automatically detected crash mentions from
   the last 7 days via GDELT, city/age-band/device/outcome only (never a
   name or exact age), tagged corroborated vs. single-source. Refreshes
   every 6 hours unattended (see AUTOMATION.md).
4. **Risk & Prevention** — an interpretable (no opaque ML) state risk
   ranking adjusted by a bike-commute exposure proxy, PBCAT factor
   cross-tabs for fatal (FARS) and non-fatal (CRSS) crashes, each paired
   with sourced prevention levers (FHWA/NACTO/NHTSA guidance).
5. **City Pilots** — ward/district/borough-level crash data with bikeshare
   e-bike exposure context and OSM bike-lane proximity, each city verified
   independently: **DC, Chicago, Boston, NYC**.

**Beyond the dashboard:**

- **341 per-city data pages** (`/cities/`) — static, SEO-indexable pages
  with each city's fatality record, honest caveats, a crash map, and
  social-share cards. Searchable index.
- **Crash-concentration screenings** (`/risk-screening/{city}/`) —
  HIN-style ~250m grid screening of city open data with a persistence
  check, for the four pilot cities. Count-based; supports engineering
  judgment, never replaces it.
- **Print-ready city safety reports** (`/reports/{st}/{city}/`) —
  light-themed, council-packet-ready documents ("Save as PDF" from any
  browser). Free to any city, school district, or local organization:
  jamesad923@gmail.com.
- **Auto-drafted data briefs** (`briefs/`) — when the news pipeline
  detects a new incident, it drafts a neutral data brief for that city
  (with a mandatory human-review checklist) and opens a repo issue.

## Quick start

Requires Python 3.9+ and **no other dependencies** (standard library only).
Social cards and report PDFs additionally use a local Chrome for headless
rendering.

```bash
# Federal fatality data (fully automatic, ~400MB of downloads first run)
python3 etl/fars/transform_fars.py            # defaults to 2019-2024

# Per-city aggregates -> 341 static city pages -> social cards
python3 etl/cities/build_city_data.py
python3 etl/cities/build_city_pages.py
python3 etl/cities/build_social_cards.py      # headless Chrome, ~7 min

# City pilot pipelines (each fetches its city's open data)
python3 etl/dc/transform_dc.py
python3 etl/chicago/transform_chicago.py
python3 etl/boston/transform_boston.py
python3 etl/nyc/transform_nyc.py

# Crash-concentration screening + print-ready reports
python3 etl/risk/screen_city.py nyc           # also: dc, chicago, boston
python3 etl/reports/build_city_report.py

# News-sourced recent reports (fully automatic, free, no key)
python3 etl/news/transform_news.py 7d

# NEISS requires one manual browser step first (CPSC blocks scripts) --
# see etl/neiss/fetch_neiss.py, then:
python3 etl/neiss/transform_neiss.py 2024

# Serve the dashboard (static page, no build step)
cd web && python3 -m http.server 8765
```

## Why this architecture

The data is small and updates annually-to-6-hourly, so v1 is
**data-as-committed-artifacts + a static page** — no server, no database,
no build step, no pip installs:

- `etl/` — Python connectors, one per source, honesty constraints
  documented inline (sentinel values, coding limitations, sample vs.
  census, upstream-source breakage notes).
- `data/raw/` — original downloads (gitignored; regenerate via ETL).
- `web/data/` — small, committed, reproducible artifacts the site reads.
  Every artifact carries a `provenance` block.
- `web/index.html` — the whole dashboard. MapLibre GL + vanilla JS.
- `.github/workflows/` — unattended refresh (news every 6h; risk and the
  four city pilots weekly) + auto-deploy to GitHub Pages. AUTOMATION.md
  has the honest details, including where GitHub's cron falls short.

## What's not here yet, and why

- **Rate-based hotspots.** No national ridership/exposure denominator
  exists. Counts are labeled as counts, everywhere, on purpose.
- **E-bike isolation in crash data.** Federal crash data cannot separate
  e-bikes from conventional bicycles; only NEISS (2024+) isolates them,
  as unmappable national estimates. Every page says so.
- **Court/legal outcomes.** Sparse, fragmented. Future phase.
- **Satellite crash detection.** Confirmed dead end — imagery's only
  legitimate role is infrastructure context.

## Data lineage and limitations

See [DATA_SOURCES.md](DATA_SOURCES.md) for exact source URLs, code
definitions, sentinel-value handling, and known gaps per dataset — plus
the parts of each city's data that broke or changed upstream and how the
pipeline handles that honestly.
