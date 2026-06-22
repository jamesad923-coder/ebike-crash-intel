"""Fetch DC bicycle-involved crash records from Open Data DC's ArcGIS
FeatureServer (DDOT's "Vehicular Crash Data" layer, via Metropolitan Police
Department's COBALT crash system).

This is the project's first CITY-LEVEL crash source (vs. FARS/CRSS, which
are national). Real fields confirmed by direct query (not assumed):
ward, exact lat/lon, and PER-CRASH bicycle injury severity broken out as
FATAL_BICYCLIST / MAJORINJURIES_BICYCLIST / MINORINJURIES_BICYCLIST.

HONESTY LIMITS, repeated downstream:
  - No e-bike-specific flag here either -- same federal-data gap applies
    at the city level. This is "bicyclist" crashes broadly, e-bikes
    included but not isolated.
  - FROMDATE is the crash date; some historical records have a null date
    (kept, not dropped -- they still count toward ward totals, just can't
    be year-filtered).
  - maxRecordCount=1000 per query (confirmed via the service's own
    metadata) -- pagination via resultOffset is required for the full
    ~7,400+ record dataset; a single unpaginated query would silently
    truncate results.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Public_Safety_WebMercator/MapServer/24/query"
PAGE_SIZE = 1000
FIELDS = [
    "CCN", "FROMDATE", "WARD", "LATITUDE", "LONGITUDE", "ADDRESS",
    "FATAL_BICYCLIST", "MAJORINJURIES_BICYCLIST", "MINORINJURIES_BICYCLIST",
    "UNKNOWNINJURIES_BICYCLIST", "TOTAL_BICYCLES", "SPEEDING_INVOLVED",
]

RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "dc"


def fetch_bicycle_crashes() -> list[dict]:
    """Paginate through all bicycle-involved crash records (TOTAL_BICYCLES > 0)."""
    all_records = []
    offset = 0
    while True:
        params = {
            "where": "TOTAL_BICYCLES>0",
            "outFields": ",".join(FIELDS),
            "resultOffset": str(offset),
            "resultRecordCount": str(PAGE_SIZE),
            "orderByFields": "OBJECTID",
            "f": "json",
        }
        url = BASE_URL + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "ebike-crash-intel/0.1"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        features = data.get("features", [])
        if not features:
            break
        all_records.extend(f["attributes"] for f in features)
        if len(features) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.3)  # polite pacing, not strictly required but cheap to do
    return all_records


def cached_bicycle_crashes() -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    cache_path = RAW / "dc_bicycle_crashes.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    records = fetch_bicycle_crashes()
    cache_path.write_text(json.dumps(records))
    return records


if __name__ == "__main__":
    records = fetch_bicycle_crashes()
    print(f"Fetched {len(records)} bicycle-involved crash records")
    fatal = sum(1 for r in records if r.get("FATAL_BICYCLIST"))
    print(f"Fatal bicyclist outcomes: {fatal}")
    no_date = sum(1 for r in records if not r.get("FROMDATE"))
    print(f"Records with no date: {no_date}")
