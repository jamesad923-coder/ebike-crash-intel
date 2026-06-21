"""Repeat-fatality cluster flagging from FARS pedalcyclist fatality points.

This is explicitly NOT a corridor-level RISK model -- that would need
street-level ridership/exposure data we don't have (see DATA_SOURCES.md;
BikeMaps.org does this with Strava Metro, we don't have an equivalent).
What this IS: a simple geographic density flag -- "multiple documented
fatalities have occurred within roughly this area" -- using only counts,
labeled as counts, with no claim about ridership or true risk rate. A busy
urban grid will surface here partly because more riding happens there, not
necessarily because it's more dangerous per rider. The dashboard must repeat
this caveat, not just this docstring.

Method: bin fatalities into a coarse lat/lon grid (~0.15 degrees, roughly a
10-15km cell depending on latitude) and flag any cell with >=3 fatalities
across the available years as a cluster. Grid cells are a deliberately
coarse area, not a precise corridor or intersection -- consistent with not
overstating precision the data can't support.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fars.transform_fars import transform as transform_fars  # noqa: E402

GRID_SIZE = 0.15  # degrees
MIN_CLUSTER_SIZE = 3


def build_clusters(years: list[int]) -> dict:
    result = transform_fars(years)
    features = result["geojson"]["features"]

    cells = defaultdict(list)
    for f in features:
        lon, lat = f["geometry"]["coordinates"]
        cell = (round(lat / GRID_SIZE), round(lon / GRID_SIZE))
        cells[cell].append(f["properties"])

    clusters = []
    for (cy, cx), points in cells.items():
        if len(points) < MIN_CLUSTER_SIZE:
            continue
        center_lat = (cy + 0.5) * GRID_SIZE
        center_lon = (cx + 0.5) * GRID_SIZE
        states = sorted({p["state"] for p in points if p.get("state")})
        minors = sum(1 for p in points
                     if "child" in p["age_band"] or "teen" in p["age_band"])
        clusters.append({
            "center": [round(center_lon, 4), round(center_lat, 4)],
            "fatality_count": len(points),
            "states": states,
            "minors_involved": minors,
            "years": sorted({p["year"] for p in points}),
            "note": f"{len(points)} documented fatalities within ~"
                    f"{GRID_SIZE}-degree area across {result['summary']['totals']['by_year']}"
                    f" -- a count-based pattern flag, not an exposure-adjusted risk rate.",
        })
    clusters.sort(key=lambda c: -c["fatality_count"])
    return {
        "years": years,
        "grid_size_degrees": GRID_SIZE,
        "min_cluster_size": MIN_CLUSTER_SIZE,
        "measure_note": "Counts of documented fatalities in a coarse area, "
                         "NOT an exposure-adjusted risk rate. We have no "
                         "ridership data at this granularity (see "
                         "DATA_SOURCES.md) -- busier areas will show up here "
                         "partly because more people ride there.",
        "clusters": clusters,
    }


if __name__ == "__main__":
    years = [int(y) for y in sys.argv[1:]] or [2022, 2023]
    result = build_clusters(years)
    print(f"Found {len(result['clusters'])} clusters (>={MIN_CLUSTER_SIZE} fatalities, ~{GRID_SIZE}deg cells)")
    for c in result["clusters"][:10]:
        print(f"  {c['fatality_count']:2}  {c['states']}  minors={c['minors_involved']}  {c['center']}")
