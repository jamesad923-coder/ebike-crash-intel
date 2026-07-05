"""Auto-draft a city data brief when the news pipeline detects a new
incident with a confident location.

The motion: a serious cyclist/e-bike incident hits local news -> within
days the city council or school board is discussing it -> that is the
moment a transportation director needs data context. This script drafts
that context automatically; a human reviews and sends it personally.
Nothing here is sent anywhere automatically -- the CI workflow opens a
GitHub issue per new brief (which emails the repo owner), and the send
is always a human decision.

PUBLIC-ARTIFACT RULE: this repo is public, so briefs are written as
neutral reference memos -- the same data brief the city pages offer
anyone for free. No outreach strategy, no sales language. The personal
cover note belongs in the sender's email, never in the artifact.

State: briefs/.state.json records which incidents already produced a
brief (keyed on stable incident fields, NOT confidence tier -- a report
being upgraded from single-source to corroborated must not produce a
duplicate brief).
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cities.build_city_data import STATE_ABBR, slugify  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "web" / "data"
BRIEFS = ROOT / "briefs"
STATE_FILE = BRIEFS / ".state.json"

BASE_URL = "https://jamesad923-coder.github.io/ebike-crash-intel"
REPO_URL = "https://github.com/jamesad923-coder/ebike-crash-intel"
CONTACT_EMAIL = "jamesad923@gmail.com"

ABBR_TO_STATE = {v: k for k, v in STATE_ABBR.items()}

# News extraction and FARS coding sometimes name the same city differently.
NEWS_CITY_ALIASES = {("new york", "NY"): "new york city"}


def incident_key(p: dict) -> str:
    raw = "|".join([
        (p.get("city") or "").lower(), p.get("state") or "",
        (p.get("date") or "")[:8], p.get("device") or "",
        p.get("age_band") or "",
    ])
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def fmt_date(d: str) -> str:
    d = (d or "")[:8]
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else "unknown date"


def state_context(state_name: str, fars_summary: dict, risk: dict | None) -> str:
    rows = fars_summary.get("by_state", [])
    total = next((r["count"] for r in rows if r["label"] == state_name), None)
    if total is None:
        return ""
    rank = 1 + sum(1 for r in rows if r["count"] > total)
    years = fars_summary["provenance"]["years"]
    out = (f"- **{state_name}**: {total} pedalcyclist fatalities in FARS "
           f"{years[0]}–{years[-1]} (#{rank} among states by raw count "
           f"— a count, not a rate; larger states rank high partly "
           f"because more people ride).")
    if risk:
        try:
            r = next(x for x in risk["state_ranking"]["ranking"]
                     if x["state"] == state_name)
            out += (f"\n- Adjusted for bike-commute share (an imperfect but "
                    f"real exposure proxy), {state_name} ranks "
                    f"**#{r['rate_rank']}** at "
                    f"{r['fatalities_per_10k_bike_commuters']} fatalities per "
                    f"10k bike commuters (raw-count rank #{r['count_rank']}).")
        except (StopIteration, KeyError):
            pass
    return out


def city_context(c: dict, years: list[int]) -> str:
    y0, y1 = years[0], years[-1]
    trend = ", ".join(f"{y}: {n}" for y, n in c["by_year"].items())
    lines = [
        f"- **{c['city']}, {c['state_abbr']}**: {c['total']} recorded cyclist "
        f"fatalit{'y' if c['total'] == 1 else 'ies'} in FARS {y0}–{y1}, "
        f"of which {c['minors']} {'was a minor' if c['minors'] == 1 else 'were minors'} (under 18).",
        f"- Year by year: {trend}.",
    ]
    if c["total"] < 5:
        lines.append(
            "- **Small numbers**: at this count, a single crash changes the "
            "picture entirely; no trend can be inferred from city data alone.")
    if c["top_crash_groups"]:
        top = c["top_crash_groups"][0]
        lines.append(
            f"- Most common crash type coded in this city's reports (PBCAT): "
            f"“{top['label']}” ({top['count']} of {c['total']}). This is "
            f"what crash reports found, not a fault judgment.")
    lines.append(f"- City data page: {BASE_URL}/cities/{c['slug']}/")
    return "\n".join(lines)


def build_brief(p: dict, city_rec: dict | None, fars_summary: dict,
                risk: dict | None) -> str:
    city, st = p.get("city", ""), p.get("state", "")
    state_name = ABBR_TO_STATE.get(st, st)
    years = fars_summary["provenance"]["years"]
    tier = ("corroborated by 2+ independent outlets"
            if p.get("confidence_tier") == "corroborated"
            else "single news source — treat as unconfirmed")
    srcs = "\n".join(f"  - [{s['domain']}]({s['url']})"
                     for s in p.get("sources", []))
    throttle = ("\n- The article text mentions a **throttle-capable vehicle** "
                "(e.g. Sur-Ron class) that may not legally be a Class 1–3 "
                "e-bike; federal data has no e-bike class field, so this is a "
                "keyword flag, not a classification."
                if p.get("throttle_ambiguous") else "")

    city_block = (city_context(city_rec, years) if city_rec else
                  f"- {city} has fewer than 3 recorded cyclist fatalities in "
                  f"FARS {years[0]}–{years[-1]}, so it does not have a "
                  f"standing city page. That is itself worth knowing: the "
                  f"local discussion is likely driven by injuries and near "
                  f"misses, which federal fatality data does not capture.")

    return f"""# Data brief: {p.get('device', 'cyclist')} {p.get('outcome', 'incident').lower()} reported in {city}, {st} ({fmt_date(p.get('date'))})

*Auto-drafted by the Crash Atlas news pipeline. Everything below is from
public data with sources linked; the incident itself was detected by
automated news scanning and is **not independently verified**.*

> **Before using this brief (reviewer checklist):**
> 1. Open each source below and confirm the article is actually about
>    {city}, {st} — automated location extraction does sometimes attach
>    the wrong city to a story.
> 2. Confirm the outcome and age band against the article text.
> 3. If either check fails, discard this brief; do not send it.

## What was detected

- Reported: **{p.get('device', 'unknown device')}**, outcome coded
  “{p.get('outcome', 'unknown')}”, age band {p.get('age_band', 'unknown')}.
- Confidence: {tier}.{throttle}
- Location precision: `{p.get('location_precision', 'unknown')}` (automated
  keyword extraction, not human-read).
- Sources:
{srcs}

## {city} in the federal fatality data

{city_block}

## State context

{state_context(state_name, fars_summary, risk)}

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
[about]({BASE_URL}/about/) · [dashboard]({BASE_URL}/) ·
[methodology]({REPO_URL}/blob/main/DATA_SOURCES.md). City staff, school
districts, local organizations, and reporters can request an expanded
brief at no cost: [{CONTACT_EMAIL}](mailto:{CONTACT_EMAIL}).*
"""


def main() -> None:
    incidents = json.loads((DATA / "news_incidents.geojson").read_text())
    city_stats = json.loads((DATA / "city_stats.json").read_text())
    fars_summary = json.loads((DATA / "fars_summary.json").read_text())
    try:
        risk = json.loads((DATA / "risk_summary.json").read_text())
    except (OSError, json.JSONDecodeError):
        risk = None

    by_key = {}
    for c in city_stats["cities"]:
        by_key[(c["city"].lower(), c["state_abbr"])] = c

    BRIEFS.mkdir(exist_ok=True)
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

    new = 0
    for f in incidents.get("features", []):
        p = f.get("properties", {})
        city, st = p.get("city"), p.get("state")
        if not city or not st:
            continue
        key = incident_key(p)
        if key in state:
            continue

        lookup = NEWS_CITY_ALIASES.get((city.lower(), st), city.lower())
        city_rec = by_key.get((lookup, st))
        brief = build_brief(p, city_rec, fars_summary, risk)
        name = f"{fmt_date(p.get('date'))}-{st.lower()}-{slugify(city)}.md"
        path = BRIEFS / name
        path.write_text(brief)
        state[key] = {"file": name,
                      "generated": datetime.now(timezone.utc).isoformat()}
        print(f"NEW {path.relative_to(ROOT)}")
        new += 1

    STATE_FILE.write_text(json.dumps(state, indent=2))
    print(f"{new} new brief(s); {len(state)} total tracked.", file=sys.stderr)


if __name__ == "__main__":
    main()
