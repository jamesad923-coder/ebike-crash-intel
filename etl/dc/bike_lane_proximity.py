"""Is a crash near a mapped bike lane? The "why" layer for crash patterns
-- infrastructure context, never crash detection (the brief is explicit
that imagery/OSM cannot and must not be used to detect crashes; this is
the legitimate use: explaining the road environment around crashes we
already know about from DC's own MPD crash records).

Method: grid-index every bike-lane vertex (OSM way geometry, ~38,877
points across 5,375 segments), then for each crash point check only the
nearby grid cells for the closest lane vertex. This approximates true
point-to-line-segment distance using vertex density -- DC's OSM cycleway
ways are densely vertexed enough (10-12 points per short urban segment,
confirmed directly) that nearest-vertex is a reasonable stand-in without
needing a full point-to-segment geometry library.

THRESHOLD CHOICE: 30 meters. Chosen to absorb GPS/geocoding imprecision
in both the crash dataset and OSM mapping, not because 30m is some
precise "the bike lane was right there" claim -- a crash flagged "near a
bike lane" means within ~30m of one, not necessarily ON it or caused by
its absence/presence. State this caveat wherever the result is shown.
"""
from __future__ import annotations

import math
from collections import defaultdict

GRID_SIZE = 0.001  # roughly 100m at DC's latitude
PROXIMITY_THRESHOLD_M = 30


def _grid_key(lat: float, lon: float) -> tuple[int, int]:
    return (round(lat / GRID_SIZE), round(lon / GRID_SIZE))


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class BikeLaneIndex:
    def __init__(self, lanes: list[dict]):
        self.grid: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
        for way in lanes:
            for lat, lon in way["geometry"]:
                self.grid[_grid_key(lat, lon)].append((lat, lon))

    def is_near(self, lat: float, lon: float, threshold_m: float = PROXIMITY_THRESHOLD_M) -> bool:
        gy, gx = _grid_key(lat, lon)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for plat, plon in self.grid.get((gy + dy, gx + dx), []):
                    if _haversine_m(lat, lon, plat, plon) <= threshold_m:
                        return True
        return False


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from dc.fetch_bike_lanes import cached_bike_lanes  # noqa: E402

    lanes = cached_bike_lanes()
    idx = BikeLaneIndex(lanes)
    # Sanity check: a point ON the Capital Crescent Trail should be "near";
    # a point in the middle of a park far from any street should not.
    print("On a known trail (should be True):", idx.is_near(38.9301, -77.0810))
    print("Middle of Rock Creek Park (should likely be False):", idx.is_near(38.9550, -77.0550))
