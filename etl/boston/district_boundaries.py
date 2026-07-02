"""Fetch Boston City Council District boundary polygons and provide a
point-in-district lookup.

Source: Boston Open Data (ArcGIS Hub) -- City Council Districts layer.
9 districts confirmed (labeled "District 1" through "District 9").
Uses the grid-rasterization approach from Chicago's WardLookup rather than
per-point polygon testing -- Boston's trip/crash volume warrants it.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

# Boston Open Data ArcGIS REST endpoint for City Council Districts.
# Returns GeoJSON with a DISTRICT property (integer 1-9).
# NOTE (2026): the old "City_Council_Districts" service now requires an
# auth token ("Token Required", error 499) -- it appears to have been
# superseded by the 2023-2032 redistricting layer below, found live via
# Boston's ArcGIS Hub catalog search, which is still public/tokenless.
DISTRICT_URL = (
    "https://services.arcgis.com/sFnw0xNflSi8J0uh/arcgis/rest/services/"
    "CityCouncilDistricts_2023_5_25/FeatureServer/0/query"
)
RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "boston"


def fetch_district_polygons() -> list[dict]:
    """Returns [{"ward": "District N", "rings": [[[lon,lat], ...]]}, ...]"""
    params = {
        "where": "1=1",
        "outFields": "DISTRICT",
        "outSR": "4326",
        "geometryPrecision": "5",
        "f": "geojson",
    }
    url = DISTRICT_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ebike-crash-intel/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    out = []
    for f in data["features"]:
        dist_num = f["properties"].get("DISTRICT") or f["properties"].get("district", "?")
        geom = f["geometry"]
        if geom["type"] == "Polygon":
            rings = geom["coordinates"]
        else:  # MultiPolygon
            rings = [ring for poly in geom["coordinates"] for ring in poly]
        out.append({"ward": f"District {dist_num}", "rings": rings})
    return out


def cached_district_polygons() -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    cache_path = RAW / "boston_district_polygons.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    polys = fetch_district_polygons()
    cache_path.write_text(json.dumps(polys))
    return polys


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    n = len(ring)
    x1, y1 = ring[0]
    for i in range(1, n + 1):
        x2, y2 = ring[i % n]
        if (y1 > lat) != (y2 > lat):
            x_intersect = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_intersect:
                inside = not inside
        x1, y1 = x2, y2
    return inside


def _bbox(rings: list) -> tuple[float, float, float, float]:
    lons = [pt[0] for ring in rings for pt in ring]
    lats = [pt[1] for ring in rings for pt in ring]
    return min(lons), min(lats), max(lons), max(lats)


GRID_SIZE = 0.001  # ~100m at Boston's latitude


class WardLookup:
    """Grid-rasterized district lookup. See Chicago's WardLookup for
    rationale: per-point polygon testing is too slow at trip volume."""

    def __init__(self, polygons: list[dict] | None = None):
        self.polygons = polygons or cached_district_polygons()
        self._grid: dict[tuple[int, int], str] = {}
        for poly in self.polygons:
            minx, miny, maxx, maxy = _bbox(poly["rings"])
            gx0, gx1 = int(minx / GRID_SIZE), int(maxx / GRID_SIZE) + 1
            gy0, gy1 = int(miny / GRID_SIZE), int(maxy / GRID_SIZE) + 1
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    key = (gx, gy)
                    if key in self._grid:
                        continue
                    lon_c = (gx + 0.5) * GRID_SIZE
                    lat_c = (gy + 0.5) * GRID_SIZE
                    for ring in poly["rings"]:
                        if _point_in_ring(lon_c, lat_c, ring):
                            self._grid[key] = poly["ward"]
                            break

    def ward_for(self, lon: float, lat: float) -> str | None:
        return self._grid.get((int(lon / GRID_SIZE), int(lat / GRID_SIZE)))


if __name__ == "__main__":
    polys = fetch_district_polygons()
    print(f"Fetched {len(polys)} district polygons")
    lookup = WardLookup(polys)
    tests = [
        ("Faneuil Hall (District 1/2 area)", -71.0560, 42.3600),
        ("Fenway area", -71.0970, 42.3467),
        ("South Boston", -71.0437, 42.3367),
    ]
    for name, lon, lat in tests:
        print(f"  {name}: {lookup.ward_for(lon, lat)}")
