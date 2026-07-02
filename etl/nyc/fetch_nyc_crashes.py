"""Fetch NYC bicycle-involved crash records from the NYPD Motor Vehicle
Collisions dataset via NYC Open Data (Socrata API).

Dataset confirmed: "Motor Vehicle Collisions - Crashes" (h9gi-nx95).
This is NYC's best-in-class crash dataset: geocoded, ~2M records since 2012,
with cyclist-specific injury/fatality counts PER CRASH RECORD.

Key fields confirmed directly:
  - crash_date: "YYYY-MM-DD" string
  - crash_time: "HH:MM" string
  - borough: "MANHATTAN", "BROOKLYN", "BRONX", "QUEENS", "STATEN ISLAND", or ""
  - latitude, longitude: float strings (some missing)
  - number_of_cyclist_injured: integer string
  - number_of_cyclist_killed: integer string

HONESTY LIMITS:
  - No e-bike-specific flag (same gap as every other source).
  - A single crash record may involve multiple cyclists; the injury/fatality
    counts are totals per crash, not per person.
  - Borough field is empty for some records; those are excluded from the
    borough-level summary but still count toward total records.
  - Dataset goes back to 2012; we use a ~5-year window matching the other
    city pilots for comparability.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

CRASHES_URL = "https://data.cityofnewyork.us/resource/h9gi-nx95.json"
PAGE_SIZE = 1000
RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "nyc"

FIELDS = [
    "crash_date", "crash_time", "borough",
    "latitude", "longitude",
    "number_of_cyclist_injured", "number_of_cyclist_killed",
    "on_street_name", "cross_street_name",
]


def _get(params: dict) -> list[dict]:
    url = CRASHES_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ebike-crash-intel/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_bicycle_crashes(cutoff_date: str) -> list[dict]:
    """All NYC crashes where at least one cyclist was injured or killed,
    on or after cutoff_date (YYYY-MM-DD). Paginated."""
    out = []
    offset = 0
    where = (
        f"(number_of_cyclist_injured>0 OR number_of_cyclist_killed>0)"
        f" AND crash_date>='{cutoff_date}T00:00:00.000'"
    )
    while True:
        rows = _get({
            "$where": where,
            "$select": ",".join(FIELDS),
            "$limit": PAGE_SIZE,
            "$offset": offset,
            "$order": "crash_date",
        })
        if not rows:
            break
        out.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.2)
    return out


def cached_bicycle_crashes(cutoff_date: str = "2021-01-01") -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    cache_path = RAW / "nyc_bicycle_crashes.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    records = fetch_bicycle_crashes(cutoff_date)
    cache_path.write_text(json.dumps(records))
    return records


if __name__ == "__main__":
    import sys
    cutoff = sys.argv[1] if len(sys.argv) > 1 else "2021-01-01"
    records = cached_bicycle_crashes(cutoff)
    print(f"Fetched {len(records)} cyclist-involved crash records since {cutoff}")
    fatal = sum(int(r.get("number_of_cyclist_killed") or 0) for r in records)
    injured = sum(int(r.get("number_of_cyclist_injured") or 0) for r in records)
    print(f"Total cyclist killed: {fatal}, injured: {injured}")
    with_geo = sum(1 for r in records if r.get("latitude") and r.get("longitude"))
    print(f"With lat/lon: {with_geo}")
    boroughs = {}
    for r in records:
        b = r.get("borough") or "Unknown"
        boroughs[b] = boroughs.get(b, 0) + 1
    print("By borough:", boroughs)
