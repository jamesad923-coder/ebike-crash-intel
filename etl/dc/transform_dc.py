"""DC pilot: ward-level bicycle crash summary + Capital Bikeshare e-bike
trip context, kept deliberately separate (see fetch_capital_bikeshare.py
for why we don't compute a per-ward rate from this).

This is the project's first CITY-LEVEL crash source -- finer geography
than FARS/CRSS/ACS allow, and the proof-of-concept for whether a city
pilot is worth expanding to others.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dc.fetch_dc_crashes import cached_bicycle_crashes  # noqa: E402
from dc.fetch_capital_bikeshare import cached_recent_months  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "data"

RECENT_MONTHS = ["202601", "202602", "202603", "202604", "202605"]


def build_ward_summary() -> dict:
    records = cached_bicycle_crashes()
    by_ward = defaultdict(lambda: {
        "crashes": 0, "fatal": 0, "major_injury": 0, "minor_injury": 0,
        "speeding_involved": 0,
    })
    no_ward = 0
    features = []

    for r in records:
        ward = r.get("WARD")
        if not ward:
            no_ward += 1
            continue
        w = by_ward[ward]
        w["crashes"] += 1
        w["fatal"] += int(r.get("FATAL_BICYCLIST") or 0)
        w["major_injury"] += int(r.get("MAJORINJURIES_BICYCLIST") or 0)
        w["minor_injury"] += int(r.get("MINORINJURIES_BICYCLIST") or 0)
        w["speeding_involved"] += 1 if r.get("SPEEDING_INVOLVED") else 0

        lat, lon = r.get("LATITUDE"), r.get("LONGITUDE")
        if lat and lon:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "ward": ward,
                    "fatal": bool(r.get("FATAL_BICYCLIST")),
                    "major_injury": bool(r.get("MAJORINJURIES_BICYCLIST")),
                    "speeding_involved": bool(r.get("SPEEDING_INVOLVED")),
                },
            })

    ward_rows = [{"ward": w, **stats} for w, stats in by_ward.items()]
    ward_rows.sort(key=lambda r: -r["crashes"])

    return {
        "measure_note": (
            "Bicycle-involved crash COUNTS by DC ward, all years in the "
            "source dataset (not exposure-adjusted -- no per-ward "
            "ridership data is wired in; see the separate Capital "
            "Bikeshare e-bike trip context below, which is citywide "
            "context only, not used to compute a per-ward rate). Same "
            "federal-data-style gap applies here too: this is all "
            "bicyclist crashes, e-bikes included but not isolated -- DC's "
            "crash data has no e-bike-specific flag either."
        ),
        "records_with_no_ward": no_ward,
        "total_records": len(records),
        "by_ward": ward_rows,
        "geojson": {"type": "FeatureCollection", "features": features},
    }


def build_bikeshare_context() -> dict:
    monthly = cached_recent_months(RECENT_MONTHS)
    rows = []
    for m, counts in monthly.items():
        total = sum(counts.values())
        ebike = counts.get("electric_bike", 0)
        rows.append({
            "month": m,
            "total_trips": total,
            "electric_bike_trips": ebike,
            "classic_bike_trips": counts.get("classic_bike", 0),
            "electric_bike_share": round(ebike / total, 3) if total else 0,
        })
    rows.sort(key=lambda r: r["month"])
    return {
        "measure_note": (
            "Capital Bikeshare's own trip-history data, which uniquely "
            "DOES distinguish e-bike trips (rideable_type field) from "
            "classic bike trips -- a genuinely e-bike-specific signal, "
            "rare in this project's sources. But it covers ONLY Capital "
            "Bikeshare's fleet, not personally-owned e-bikes (most of "
            "what the news-sourced fatality reports involve), and is "
            "citywide, not ward-level -- shown as context, not blended "
            "into the ward crash counts above."
        ),
        "monthly": rows,
    }


def build(years: list[int] | None = None) -> dict:
    return {
        "ward_summary": build_ward_summary(),
        "bikeshare_context": build_bikeshare_context(),
    }


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    result = build()
    (OUT / "dc_pilot.json").write_text(json.dumps(result, indent=2))
    ws = result["ward_summary"]
    print(f"Total bicycle-crash records: {ws['total_records']} ({ws['records_with_no_ward']} with no ward)")
    print("By ward:")
    for r in ws["by_ward"]:
        print(f"  {r['ward']:10} crashes={r['crashes']:5}  fatal={r['fatal']:2}  "
              f"major={r['major_injury']:3}  minor={r['minor_injury']:4}")
    print(f"\nMapped points: {len(ws['geojson']['features'])}")
    print("\nCapital Bikeshare e-bike share by month:")
    for r in result["bikeshare_context"]["monthly"]:
        print(f"  {r['month']}: {r['electric_bike_share']*100:.0f}% e-bike "
              f"({r['electric_bike_trips']:,} of {r['total_trips']:,})")
    print(f"\nWrote {OUT / 'dc_pilot.json'}")
