"""Fetch NYC bike-lane/cycleway infrastructure from OpenStreetMap's
Overpass API. Same approach as DC, Chicago, and Boston -- only the bounding
box differs. NYC's larger area means more segments and a longer fetch.

NYC bounding box covers all five boroughs with a small margin.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "nyc"

NYC_BBOX = (40.49, -74.27, 40.93, -73.68)


def _query(clauses: list[tuple[str, str]]) -> str:
    bbox = ",".join(str(x) for x in NYC_BBOX)
    ways = ";".join(f'way["{k}"="{v}"]({bbox})' for k, v in clauses)
    return f"[out:json][timeout:90];({ways};);out geom;"


def fetch_bike_lanes(max_retries: int = 4) -> list[dict]:
    clauses = [
        ("highway", "cycleway"),
        ("cycleway", "lane"), ("cycleway", "track"), ("cycleway", "opposite_lane"),
        ("cycleway:left", "lane"), ("cycleway:left", "track"),
        ("cycleway:right", "lane"), ("cycleway:right", "track"),
        ("cycleway:both", "lane"), ("cycleway:both", "track"),
    ]
    data = _query(clauses)
    params = {"data": data}
    url = OVERPASS_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "*/*", "User-Agent": "ebike-crash-intel/0.1"})

    delay = 5
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=100) as r:
                result = json.loads(r.read())
            return [
                {"id": el["id"], "tags": el.get("tags", {}),
                 "geometry": [[pt["lat"], pt["lon"]] for pt in el.get("geometry", [])]}
                for el in result.get("elements", []) if el.get("type") == "way"
            ]
        except HTTPError:
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            raise
    return []


def cached_bike_lanes() -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    cache_path = RAW / "nyc_bike_lanes.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    lanes = fetch_bike_lanes()
    cache_path.write_text(json.dumps(lanes))
    return lanes


if __name__ == "__main__":
    lanes = fetch_bike_lanes()
    print(f"Fetched {len(lanes)} bike-lane/cycleway way segments")
    print(f"Total geometry points: {sum(len(w['geometry']) for w in lanes)}")
