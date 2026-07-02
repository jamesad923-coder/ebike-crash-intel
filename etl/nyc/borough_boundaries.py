"""Fetch NYC Borough boundary polygons and provide a point-in-borough lookup.

Source: NYC Open Data "Borough Boundaries" dataset (7t3b-ywvw) -- the
standard administrative boundaries used by the city. Five boroughs:
Manhattan, Bronx, Brooklyn, Queens, Staten Island.

Uses the grid-rasterization approach from Chicago's WardLookup -- Citi Bike
has millions of trip points per month; per-point polygon testing would be
too slow.

NOTE: For crash data, NYPD already provides a borough field per record,
so this lookup is only used for Citi Bike station→borough mapping.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

BOROUGH_URL = (
    "https://data.cityofnewyork.us/api/geospatial/7t3b-ywvw"
    "?method=export&type=GeoJSON"
)
RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "nyc"


def fetch_borough_polygons() -> list[dict]:
    """Returns [{"ward": "MANHATTAN", "rings": [[[lon,lat], ...]]}, ...]"""
    req = urllib.request.Request(BOROUGH_URL, headers={"User-Agent": "ebike-crash-intel/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    out = []
    for f in data["features"]:
        name = (f["properties"].get("boro_name") or
                f["properties"].get("NAME") or
                f["properties"].get("BoroName") or "").upper()
        geom = f["geometry"]
        if geom["type"] == "Polygon":
            rings = geom["coordinates"]
        else:  # MultiPolygon
            rings = [ring for poly in geom["coordinates"] for ring in poly]
        if name:
            out.append({"ward": name, "rings": rings})
    return out


def cached_borough_polygons() -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    cache_path = RAW / "nyc_borough_polygons.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    polys = fetch_borough_polygons()
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


GRID_SIZE = 0.002  # ~200m at NYC's latitude -- coarser than Boston/Chicago
# because 5 boroughs cover a much larger area and NYC has fewer, simpler
# boundaries compared to 50 Chicago wards or 9 Boston districts.


class WardLookup:
    def __init__(self, polygons: list[dict] | None = None):
        self.polygons = polygons or cached_borough_polygons()
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
    polys = fetch_borough_polygons()
    print(f"Fetched {len(polys)} borough polygons: {[p['ward'] for p in polys]}")
    lookup = WardLookup(polys)
    tests = [
        ("Times Square (Manhattan)", -73.9857, 40.7580),
        ("Prospect Park (Brooklyn)", -73.9701, 40.6602),
        ("Yankee Stadium (Bronx)", -73.9283, 40.8296),
        ("JFK area (Queens)", -73.7877, 40.6437),
        ("St. George (Staten Island)", -74.0754, 40.6437),
    ]
    for name, lon, lat in tests:
        print(f"  {name}: {lookup.ward_for(lon, lat)}")
