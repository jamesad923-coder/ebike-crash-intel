"""Fetch Chicago ward boundary polygons and provide a point-in-ward lookup.

Real, live source confirmed directly: "Boundaries - Wards (2023-)"
(dataset p293-wvbd on Chicago's Socrata portal), found via Socrata's
catalog search API after an initially-guessed dataset ID 404'd -- same
verify-don't-assume lesson as DC's ward layer. 50 wards confirmed (1-50).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

WARD_URL = "https://data.cityofchicago.org/resource/p293-wvbd.geojson"
RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "chicago"


def fetch_ward_polygons() -> list[dict]:
    params = {"$limit": "60"}
    url = WARD_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ebike-crash-intel/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    out = []
    for f in data["features"]:
        geom = f["geometry"]
        # Chicago wards can be MultiPolygon; normalize to a list of rings
        # regardless of Polygon vs MultiPolygon so the lookup is uniform.
        if geom["type"] == "Polygon":
            rings = geom["coordinates"]
        else:  # MultiPolygon
            rings = [ring for poly in geom["coordinates"] for ring in poly]
        out.append({"ward": f"Ward {f['properties']['ward']}", "rings": rings})
    return out


def cached_ward_polygons() -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    cache_path = RAW / "chicago_ward_polygons.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    polys = fetch_ward_polygons()
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


def _bbox(rings: list[list[list[float]]]) -> tuple[float, float, float, float]:
    lons = [pt[0] for ring in rings for pt in ring]
    lats = [pt[1] for ring in rings for pt in ring]
    return min(lons), min(lats), max(lons), max(lats)


GRID_SIZE = 0.0015  # ~150m at Chicago's latitude


class WardLookup:
    """Precomputed grid rasterization, not per-point polygon testing.

    A first attempt (bbox pre-filter + full point-in-ring test per lookup)
    did not finish in a reasonable time against Chicago's real data
    volume (~1.7M Divvy trip points, 50 wards averaging thousands of
    vertices each) -- confirmed directly, not assumed. Paying the
    point-in-polygon cost ONCE per grid cell during setup (a few thousand
    cells, not millions of trips) and reducing every actual data-point
    lookup to an O(1) dict access is the fix: setup is slower, real
    lookups are essentially free.
    """

    def __init__(self, polygons: list[dict] | None = None):
        self.polygons = polygons or cached_ward_polygons()
        self._grid: dict[tuple[int, int], str] = {}
        for poly in self.polygons:
            minx, miny, maxx, maxy = _bbox(poly["rings"])
            gx0, gx1 = int(minx / GRID_SIZE), int(maxx / GRID_SIZE) + 1
            gy0, gy1 = int(miny / GRID_SIZE), int(maxy / GRID_SIZE) + 1
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    key = (gx, gy)
                    if key in self._grid:
                        continue  # already claimed by another ward's cell
                    lon, lat = (gx + 0.5) * GRID_SIZE, (gy + 0.5) * GRID_SIZE
                    for ring in poly["rings"]:
                        if _point_in_ring(lon, lat, ring):
                            self._grid[key] = poly["ward"]
                            break

    def ward_for(self, lon: float, lat: float) -> str | None:
        return self._grid.get((int(lon / GRID_SIZE), int(lat / GRID_SIZE)))


if __name__ == "__main__":
    polys = fetch_ward_polygons()
    print(f"Fetched {len(polys)} ward polygons")
    lookup = WardLookup(polys)
    tests = [
        ("Willis Tower (Ward 4ish, downtown)", -87.6359, 41.8789),
        ("Wrigley Field (North Side)", -87.6553, 41.9484),
        ("Navy Pier", -87.6098, 41.8917),
    ]
    for name, lon, lat in tests:
        print(f"  {name}: {lookup.ward_for(lon, lat)}")
