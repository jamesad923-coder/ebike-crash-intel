"""Fetch Boston bicycle-involved crash records from the City of Boston's
Vision Zero Crash Records dataset via Socrata API (data.boston.gov).

Real fields confirmed against the live dataset:
  - dispatch_ts: ISO datetime string (crash timestamp)
  - mode_type: "BIKE", "MV", "PED", "MOPED", etc.
  - lat, long: WGS84 coordinates as strings
  - severity: "Fatal injury", "Non-fatal injury", "No injury", "Unknown"
  - street, xstreet: street / cross-street names (context only)

HONESTY LIMITS, repeated downstream:
  - Boston's VZ data has no e-bike-specific flag -- same gap as every
    other source in this project at the city level.
  - "Non-fatal injury" is the finest severity granularity available here;
    there is no separate major/minor split the way DC's MPD data has
    MAJORINJURIES_BICYCLIST / MINORINJURIES_BICYCLIST.
  - No direct City Council District field in the data -- district
    assignment requires a point-in-polygon lookup (see district_boundaries.py).
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

CRASHES_URL = "https://data.boston.gov/resource/ngee-bppz.json"
PAGE_SIZE = 1000
RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "boston"

FIELDS = [
    "dispatch_ts", "lat", "long", "mode_type", "severity", "street", "xstreet",
]


def _get(params: dict) -> list[dict]:
    url = CRASHES_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ebike-crash-intel/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_bicycle_crashes() -> list[dict]:
    """All Boston crash records where mode_type='BIKE', paginated."""
    out = []
    offset = 0
    while True:
        rows = _get({
            "$where": "mode_type='BIKE'",
            "$select": ",".join(FIELDS),
            "$limit": PAGE_SIZE,
            "$offset": offset,
            "$order": "dispatch_ts",
        })
        if not rows:
            break
        out.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.2)
    return out


def cached_bicycle_crashes() -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    cache_path = RAW / "boston_bicycle_crashes.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    records = fetch_bicycle_crashes()
    cache_path.write_text(json.dumps(records))
    return records


if __name__ == "__main__":
    records = fetch_bicycle_crashes()
    print(f"Fetched {len(records)} bicycle-involved crash records")
    fatal = sum(1 for r in records if (r.get("severity") or "").lower().startswith("fatal"))
    print(f"Fatal: {fatal}")
    no_coords = sum(1 for r in records if not r.get("lat") or not r.get("long"))
    print(f"Records with no coordinates: {no_coords}")
    severities = {}
    for r in records:
        s = r.get("severity") or "Unknown"
        severities[s] = severities.get(s, 0) + 1
    print("Severity breakdown:", severities)
