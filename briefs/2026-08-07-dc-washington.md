# Data brief: E-bike fatality reported in Washington, DC (2026-08-07)

*Auto-drafted by the Crash Atlas news pipeline. Everything below is from
public data with sources linked; the incident itself was detected by
automated news scanning and is **not independently verified**.*

> **Before using this brief (reviewer checklist):**
> 1. Open each source below and confirm the article is actually about
>    Washington, DC — automated location extraction does sometimes attach
>    the wrong city to a story.
> 2. Confirm the outcome and age band against the article text.
> 3. If either check fails, discard this brief; do not send it.

## What was detected

- Reported: **E-bike**, outcome coded
  “Fatality”, age band 0-12 (child).
- Confidence: single news source — treat as unconfirmed.
- The article text mentions a **throttle-capable vehicle** (e.g. Sur-Ron class) that may not legally be a Class 1–3 e-bike; federal data has no e-bike class field, so this is a keyword flag, not a classification.
- Location precision: `city_state_mention` (automated
  keyword extraction, not human-read).
- Sources:
  - [okcfox.com](https://okcfox.com/news/fox-25-investigates/edmond-parents-raise-school-safety-concerns-over-walking-routes-traffic-and-e-bikes)

## Washington in the federal fatality data

- **Washington, DC**: 12 recorded cyclist fatalities in FARS 2019–2024, of which 1 was a minor (under 18).
- Year by year: 2019: 1, 2020: 1, 2021: 3, 2022: 3, 2023: 3, 2024: 1.
- Most common crash type coded in this city's reports (PBCAT): “Other / Unusual Circumstances” (2 of 12). This is what crash reports found, not a fault judgment.
- City data page: https://jamesad923-coder.github.io/ebike-crash-intel/cities/dc/washington/

## State context

- **District of Columbia**: 12 pedalcyclist fatalities in FARS 2019–2024 (#43 among states by raw count — a count, not a rate; larger states rank high partly because more people ride).
- Adjusted for bike-commute share (an imperfect but real exposure proxy), District of Columbia ranks **#51** at 4.93 fatalities per 10k bike commuters (raw-count rank #42).

## What this data can and cannot say

- FARS covers **fatal motor-vehicle crashes on public roads only** — the
  far larger number of single-bike falls and non-fatal injuries is absent.
- **E-bikes cannot be separated** from conventional bicycles in federal
  crash data. Only CPSC's NEISS (2024 onward) isolates them, as national
  emergency-department estimates that cannot be mapped to a city.
- All figures are **counts, not rates** — no city-level ridership
  denominator exists.

---
*Crash Atlas is an independent open-data project by James Adigun:
[our story](https://jamesad923-coder.github.io/ebike-crash-intel/about/) · [dashboard](https://jamesad923-coder.github.io/ebike-crash-intel/) ·
[methodology](https://github.com/jamesad923-coder/ebike-crash-intel/blob/main/DATA_SOURCES.md). City staff, school
districts, local organizations, and reporters can request an expanded
brief at no cost: [jamesad923@gmail.com](mailto:jamesad923@gmail.com).*
