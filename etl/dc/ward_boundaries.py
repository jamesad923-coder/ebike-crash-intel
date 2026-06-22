"""Fetch DC ward boundary polygons and provide a point-in-ward lookup.

Real, live ArcGIS source confirmed directly (not assumed): "Wards from
2022" layer, owned by DCGISopendata, single-ring polygons (no holes, no
multipart geometry) -- a plain ray-casting point-in-polygon test is
sufficient, no GIS library dependency needed.

This is what makes a REAL per-ward bikeshare exposure measure possible:
without it, Capital Bikeshare trip data and ward crash counts have no way
to be joined at all (a trip has a lat/lon; a ward total does not).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

WARD_URL = "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Administrative_Other_Boundaries_WebMercator/MapServer/53/query"
RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "dc"


def fetch_ward_polygons() -> list[dict]:
    """Returns [{"ward": "Ward 1", "rings": [[[lon,lat], ...]]}, ...]"""
    params = {
        "where": "1=1", "outFields": "WARD", "outSR": "4326",
        "geometryPrecision": "5", "f": "geojson",
    }
    url = WARD_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ebike-crash-intel/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    out = []
    for f in data["features"]:
        out.append({
            "ward": f"Ward {f['properties']['WARD']}",
            "rings": f["geometry"]["coordinates"],
        })
    return out


def cached_ward_polygons() -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    cache_path = RAW / "ward_polygons.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    polys = fetch_ward_polygons()
    cache_path.write_text(json.dumps(polys))
    return polys


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """Standard ray-casting test. ring is a list of [lon, lat] pairs."""
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


class WardLookup:
    """Build once, call .ward_for(lon, lat) many times -- avoids refetching
    or reparsing the polygons per lookup."""

    def __init__(self, polygons: list[dict] | None = None):
        self.polygons = polygons or cached_ward_polygons()

    def ward_for(self, lon: float, lat: float) -> str | None:
        for poly in self.polygons:
            for ring in poly["rings"]:
                if _point_in_ring(lon, lat, ring):
                    return poly["ward"]
        return None


if __name__ == "__main__":
    polys = fetch_ward_polygons()
    print(f"Fetched {len(polys)} ward polygons")
    lookup = WardLookup(polys)
    # Sanity check: a known DC landmark per ward area.
    tests = [
        ("White House", -77.0365, 38.8977),
        ("Nationals Park (Ward 6)", -77.0074, 38.8730),
        ("Anacostia (Ward 8)", -76.9897, 38.8626),
    ]
    for name, lon, lat in tests:
        print(f"  {name}: {lookup.ward_for(lon, lat)}")
