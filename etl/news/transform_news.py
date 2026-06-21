"""Run fetch -> extract -> corroborate -> geocode -> publish for news-sourced
micromobility incidents.

Confidence tiers (the "bot review" layer the user asked for -- automated
sanity checks, not a human queue):
  - "corroborated": 2+ articles from DIFFERENT domains, same city+state,
    same outcome tier, within a 3-day window of each other. This is the
    closest we get to verifying a single real event without a human.
  - "single_source": only one outlet found it. Still published (per sign-off:
    auto-publish), but visually flagged as such in the dashboard.

Geocoding: only for incidents where extract.py found a confident AP-style
dateline (city + valid state abbreviation). Anything without a dateline is
NOT placed on the map and NOT given invented coordinates -- it goes in an
"unlocated reports" list instead. This is the honest-data-gaps rule applied
to a new source.

Output (web/data/news_incidents.geojson + news_unlocated.json) NEVER
contains: a name, an exact age, a street address, or raw article text.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.schema import source_stamp  # noqa: E402
from news.fetch_gdelt import fetch_articles  # noqa: E402
from news.extract import extract_incident  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "data"
CACHE = ROOT / "data" / "raw" / "news"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

STATE_FULL_NAME = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
    "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
    "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new hampshire", "NJ": "new jersey", "NM": "new mexico", "NY": "new york",
    "NC": "north carolina", "ND": "north dakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhode island", "SC": "south carolina",
    "SD": "south dakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
    "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west virginia",
    "WI": "wisconsin", "WY": "wyoming", "DC": "district of columbia",
}
PLACE_OSM_CLASSES = {"city", "town", "village", "hamlet", "county",
                      "administrative", "suburb", "borough"}


def geocode(city: str, state: str) -> tuple[float, float] | None:
    """Free OSM Nominatim geocode, city+state only (no street-level lookup,
    no need for it -- we only ever show city-level location anyway).

    Heuristic extraction produces real false positives (e.g. a Title-Case
    headline word coincidentally followed by ", MO" got matched as a place
    called "Promise" -- and Nominatim happily fuzzy-matched that to real
    coordinates in St. Louis rather than returning nothing). A non-empty
    geocode result is NOT proof the extracted place was real, so we
    cross-check Nominatim's own structured response: the result must be
    classified as an actual settlement/county/admin area, its address state
    must match what we extracted, and the matched name must overlap with
    what we searched for. Any check failing means "don't trust this," not
    "best guess" -- we'd rather under-place than mis-place a fatality.
    """
    params = {"q": f"{city}, {state}, USA", "format": "jsonv2",
              "addressdetails": 1, "limit": 1}
    url = NOMINATIM_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ebike-crash-intel/0.1 (research)"})
    try:
        time.sleep(1.1)
        with urllib.request.urlopen(req, timeout=15) as r:
            results = json.loads(r.read())
        if not results:
            return None
        res = results[0]

        if res.get("class") not in {"place", "boundary"} and res.get("type") not in PLACE_OSM_CLASSES:
            return None

        addr = res.get("address", {})
        result_state = (addr.get("state") or "").lower()
        expected_state = STATE_FULL_NAME.get(state, "")
        if expected_state and result_state and expected_state != result_state:
            return None

        matched_name = (res.get("name") or "").lower()
        city_words = {w.lower() for w in city.replace("County", "").split()}
        if matched_name and city_words and not (city_words & set(matched_name.split())):
            return None

        return float(res["lat"]), float(res["lon"])
    except Exception:
        return None


def _parse_date(seendate: str) -> datetime | None:
    try:
        return datetime.strptime(seendate[:8], "%Y%m%d")
    except Exception:
        return None


def corroborate(incidents: list[dict]) -> list[dict]:
    """Group by (city, state, outcome, device) within a 2-day window across
    distinct domains; tag each incident with the resulting confidence tier.

    CRITICAL: an incident with no extracted location has city=None. Grouping
    by (city, state, ...) naively would put EVERY unlocated incident into
    the same (None, None, outcome, device) bucket regardless of whether
    they're real, distinct events -- and falsely mark them "corroborated"
    just because two unrelated, unlocated articles both happened to fail
    location extraction. We caught exactly this bug in testing. Fix: an
    incident with no location is NEVER grouped with another incident -- it
    is always its own singleton, tier "single_source", full stop. Real
    corroboration requires a real location to anchor the comparison.
    """
    out = []
    groups = defaultdict(list)
    for inc in incidents:
        if inc["city"] is None:
            # No location anchor -- never group, never call it corroborated.
            inc2 = dict(inc)
            inc2["confidence_tier"] = "single_source"
            inc2["corroborating_domains"] = [inc["domain"]]
            out.append(inc2)
            continue
        key = (inc["city"], inc["state"], inc["outcome"], inc["device"])
        groups[key].append(inc)

    for key, group in groups.items():
        group.sort(key=lambda i: _parse_date(i["seendate"]) or datetime.min)
        for inc in group:
            d0 = _parse_date(inc["seendate"])
            window = [g for g in group if d0 and _parse_date(g["seendate"])
                      and abs((_parse_date(g["seendate"]) - d0).days) <= 2]
            domains = {g["domain"] for g in window}
            tier = "corroborated" if len(domains) >= 2 else "single_source"
            inc2 = dict(inc)
            inc2["confidence_tier"] = tier
            inc2["corroborating_domains"] = sorted(domains)
            out.append(inc2)
    return out


def dedupe_by_event(incidents: list[dict]) -> list[dict]:
    """Collapse multiple articles about the same real-world event (same
    city/state/device/outcome/~date) into one incident record, listing all
    source URLs instead of duplicating points on the map.

    Same rule as corroborate(): an incident with no location is never
    merged with another -- each is its own record. Keying on (None, None,
    ...) would otherwise silently fold together different, unrelated
    unlocated stories that happen to share a device/outcome/week.
    """
    groups = defaultdict(list)
    standalone = []
    for inc in incidents:
        if inc["city"] is None:
            standalone.append(inc)
            continue
        d = _parse_date(inc["seendate"])
        bucket = d.strftime("%Y-%W") if d else "unknown"
        key = (inc["city"], inc["state"], inc["device"], inc["outcome"], bucket)
        groups[key].append(inc)

    merged = []
    for key, group in groups.items():
        base = dict(group[0])
        base["sources"] = [{"domain": g["domain"], "url": g["url"], "date": g["seendate"]} for g in group]
        base["confidence_tier"] = group[0]["confidence_tier"]
        base["corroborating_domains"] = sorted({g["domain"] for g in group})
        merged.append(base)
    for inc in standalone:
        base = dict(inc)
        base["sources"] = [{"domain": inc["domain"], "url": inc["url"], "date": inc["seendate"]}]
        merged.append(base)
    return merged


def run(timespan="7d") -> dict:
    articles = fetch_articles(timespan=timespan)
    incidents = []
    for a in articles:
        inc = extract_incident(a)
        if inc:
            incidents.append(inc)

    tiered = corroborate(incidents)
    merged = dedupe_by_event(tiered)

    located = [i for i in merged if i["located"]]
    unlocated = [i for i in merged if not i["located"]]

    features = []
    for inc in located:
        geo = geocode(inc["city"], inc["state"])
        if geo is None:
            unlocated.append(inc)
            continue
        lat, lon = geo
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "city": inc["city"], "state": inc["state"],
                "location_precision": inc.get("location_precision"),
                "device": inc["device"], "outcome": inc["outcome"],
                "age_band": inc["age_band"],
                "confidence_tier": inc["confidence_tier"],
                "corroborating_domains": inc["corroborating_domains"],
                "sources": inc["sources"],
                "date": inc["seendate"],
            },
        })

    def public_fields(inc):
        return {k: v for k, v in inc.items() if not k.startswith("_internal")}

    geojson = {
        "type": "FeatureCollection",
        "provenance": source_stamp(
            "GDELT (news aggregation)", "Automated news-sourced incident reports", [],
            "https://www.gdeltproject.org/",
            "UNVERIFIED beyond automated cross-source checks. Each report is "
            "either 'corroborated' (2+ independent outlets, same city/outcome, "
            "within 3 days) or 'single_source' (one outlet only) -- shown "
            "explicitly. Extracted automatically from article text via "
            "keyword/dateline matching, not human-reviewed. Early news reports "
            "can be wrong about cause or severity. Never shows a name or exact "
            "age -- city, age BAND, device, and outcome only. Always check the "
            "linked source(s) before treating any single report as fact.",
        ),
        "features": features,
    }
    unlocated_out = {
        "note": "Reports where no confident city/state could be extracted "
                "from the article (no AP-style dateline found). Not placed "
                "on the map; not assigned invented coordinates.",
        "reports": [public_fields(i) for i in unlocated],
    }
    return {"geojson": geojson, "unlocated": unlocated_out, "raw_count": len(articles), "matched_count": len(incidents)}


if __name__ == "__main__":
    timespan = sys.argv[1] if len(sys.argv) > 1 else "7d"
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    try:
        result = run(timespan)
    except HTTPError as e:
        if e.code == 429:
            # GDELT's free, keyless API is shared across everyone using it --
            # a 429 here means it was busy at this exact moment, not that
            # anything is broken. Skip this cycle quietly (exit 0, no
            # "workflow failed" email) rather than erroring; the next
            # scheduled run picks it up normally. The data files are simply
            # left as they were after the last successful run.
            print("GDELT rate-limited this run (HTTP 429) -- skipping, "
                  "will retry on the next scheduled run. Not an error.")
            sys.exit(0)
        raise
    (OUT / "news_incidents.geojson").write_text(json.dumps(result["geojson"], indent=2))
    (OUT / "news_unlocated.json").write_text(json.dumps(result["unlocated"], indent=2))
    print(f"GDELT candidates fetched: {result['raw_count']}")
    print(f"Matched device+crash+outcome: {result['matched_count']}")
    print(f"Geocoded onto map: {len(result['geojson']['features'])}")
    print(f"Unlocated (listed, not mapped): {len(result['unlocated']['reports'])}")
    for f in result["geojson"]["features"]:
        p = f["properties"]
        print(f"  [{p['confidence_tier']}] {p['city']}, {p['state']} - {p['device']} - {p['outcome']} ({p['age_band']})")
