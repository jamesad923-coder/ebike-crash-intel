"""Fetch DC bike-lane/cycleway infrastructure from OpenStreetMap's free
Overpass API -- the "why" layer for crash clusters: was there a protected
or marked bike lane near where a crash happened?

Real, live, verified directly: Overpass returns way geometry for DC's
cycleway network with no key required. Overpass intermittently returns
HTTP 406 for reasons that don't track query content (confirmed: an
identical query succeeded on retry with no change) -- likely transient
server load, similar to GDELT's behavior elsewhere in this project. We
retry rather than treat a single 406 as a hard failure.

This is infrastructure CONTEXT only, matching the brief's explicit
constraint: imagery/OSM data does not detect crashes, it explains the
road environment around crashes we already know about from real crash
records (DC's MPD data) -- never the other way around.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.error import HTTPError

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "dc"

# DC bounding box (lat_min, lon_min, lat_max, lon_max) -- generous, includes
# a small margin beyond the official boundary so edge-of-ward crashes near
# a bike lane just across a ward line still find it.
DC_BBOX = (38.79, -77.12, 38.99, -76.91)


def _query(clauses: list[tuple[str, str]]) -> str:
    """Builds Overpass QL. Tag KEYS containing a colon (e.g.
    "cycleway:left") must be quoted -- way[cycleway:left=lane] is invalid
    syntax and Overpass rejects it; way["cycleway:left"="lane"] is correct.
    Confirmed directly: the unquoted form produced an HTTP 400."""
    bbox = ",".join(str(x) for x in DC_BBOX)
    ways = ";".join(f'way["{k}"="{v}"]({bbox})' for k, v in clauses)
    return f"[out:json][timeout:60];({ways};);out geom;"


def fetch_bike_lanes(max_retries=4) -> list[dict]:
    """Returns [{"id": int, "tags": {...}, "geometry": [[lat,lon], ...]}]
    for ways tagged as cycleways or having a cycleway lane/track."""
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
            with urllib.request.urlopen(req, timeout=70) as r:
                result = json.loads(r.read())
            return [
                {"id": el["id"], "tags": el.get("tags", {}),
                 "geometry": [[pt["lat"], pt["lon"]] for pt in el.get("geometry", [])]}
                for el in result.get("elements", []) if el.get("type") == "way"
            ]
        except HTTPError as e:
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            raise
    return []


def cached_bike_lanes() -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    cache_path = RAW / "dc_bike_lanes.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    lanes = fetch_bike_lanes()
    cache_path.write_text(json.dumps(lanes))
    return lanes


if __name__ == "__main__":
    lanes = fetch_bike_lanes()
    print(f"Fetched {len(lanes)} bike-lane/cycleway way segments")
    total_points = sum(len(w["geometry"]) for w in lanes)
    print(f"Total geometry points: {total_points}")
    for w in lanes[:3]:
        print(f"  way {w['id']}: {w['tags'].get('name', '(unnamed)')} -- {len(w['geometry'])} points")
