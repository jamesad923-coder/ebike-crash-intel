"""Chicago pilot: ward-level bicyclist crash summary + Divvy e-bike trip
exposure, with two fields DC's data didn't have cleanly: helmet use and a
directly-reported bike-lane-location flag.

Second city pilot -- built only after verifying Chicago's data
independently (Socrata datasets, Divvy schema, ward boundaries), not
assumed to work just because DC did. See DATA_SOURCES.md for what
checked out and what's still a Chicago-specific limitation.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chicago.fetch_chicago_crashes import cached_bicycle_crashes  # noqa: E402
from chicago.fetch_divvy import cached_month_trips  # noqa: E402
from chicago.ward_boundaries import WardLookup  # noqa: E402
from chicago.fetch_bike_lanes import cached_bike_lanes  # noqa: E402
from dc.bike_lane_proximity import BikeLaneIndex  # noqa: E402 (fully generic, reused as-is)
from common.schema import age_band  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "data"

CRASH_CUTOFF = "2021-01-01"  # ~5 years, same window length as DC; Chicago's
# data goes back to 2015 but we did not separately verify pre-2021
# reporting consistency the way DC's 2016 cutoff was confirmed -- using a
# matching window length is a deliberate consistency choice, not a claim
# that Chicago has the same data-quality history as DC.

FATAL_VALUES = {"FATAL"}
MAJOR_VALUES = {"INCAPACITATING INJURY"}
MINOR_VALUES = {"NONINCAPACITATING INJURY", "REPORTED, NOT EVIDENT"}


def _recent_months(n=5) -> list[str]:
    now = datetime.now(timezone.utc)
    months = []
    y, m = now.year, now.month
    for _ in range(n):
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        months.append(f"{y}{m:02d}")
    return sorted(months)


RECENT_MONTHS = _recent_months()


def build_ward_summary() -> dict:
    records = cached_bicycle_crashes(CRASH_CUTOFF)
    lookup = WardLookup()
    lane_index = BikeLaneIndex(cached_bike_lanes())

    by_ward = defaultdict(lambda: {
        "crashes": 0, "fatal": 0, "major_injury": 0, "minor_injury": 0,
        "helmet_used": 0, "helmet_not_used": 0, "in_bike_lane": 0,
        "near_mapped_bike_lane": 0, "minors_involved": 0,
    })
    no_geo = 0
    features = []

    for r in records:
        lat, lon = r.get("crash_latitude"), r.get("crash_longitude")
        if not lat or not lon:
            no_geo += 1
            continue
        lat, lon = float(lat), float(lon)
        ward = lookup.ward_for(lon, lat)
        if not ward:
            no_geo += 1
            continue

        injury = r.get("injury_classification") or ""
        fatal = injury in FATAL_VALUES
        major = injury in MAJOR_VALUES
        minor_inj = injury in MINOR_VALUES
        safety = r.get("safety_equipment") or ""
        helmet_used = "HELMET" in safety and "NOT USED" not in safety and safety != "USAGE UNKNOWN"
        helmet_known = "HELMET" in safety or safety == "USAGE UNKNOWN" or safety == "NONE PRESENT"
        in_lane = r.get("pedpedal_location") == "BIKE LANE"
        near_lane = lane_index.is_near(lat, lon)
        band = age_band(r.get("age"))
        is_minor_age = band in ("0-12 (child)", "13-17 (teen)")

        w = by_ward[ward]
        w["crashes"] += 1
        w["fatal"] += int(fatal)
        w["major_injury"] += int(major)
        w["minor_injury"] += int(minor_inj)
        w["in_bike_lane"] += int(in_lane)
        w["near_mapped_bike_lane"] += int(near_lane)
        w["minors_involved"] += int(is_minor_age)
        if helmet_known:
            if helmet_used:
                w["helmet_used"] += 1
            else:
                w["helmet_not_used"] += 1

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "ward": ward, "fatal": fatal, "major_injury": major,
                "minor_injury": minor_inj, "in_bike_lane": in_lane,
                "near_mapped_bike_lane": near_lane,
                "helmet_used": helmet_used if helmet_known else None,
                "age_band": band,
                "date": (r.get("crash_date") or "")[:10],
            },
        })

    ward_rows = [{"ward": w, **stats} for w, stats in by_ward.items()]
    ward_rows.sort(key=lambda r: -r["crashes"])

    return {
        "date_window": {"start": CRASH_CUTOFF, "end": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
        "measure_note": (
            f"Bicyclist-involved crash COUNTS by Chicago ward, "
            f"{CRASH_CUTOFF} onward (Chicago's full data goes back to "
            f"2015; we used a window matching DC's in length, not because "
            f"we separately confirmed Chicago's pre-2021 reporting "
            f"consistency the way DC's was checked -- a deliberate "
            f"consistency choice, not an equivalent claim). NOT exposure-"
            f"adjusted on its own -- see ward_exposure for that. Chicago's "
            f"crash data has no e-bike-specific flag either, same gap as "
            f"every other source in this project. helmet_used/"
            f"helmet_not_used and in_bike_lane are DIRECTLY police-"
            f"reported fields -- more reliable than an estimate, but "
            f"still subject to whatever the reporting officer observed "
            f"and recorded at the scene. near_mapped_bike_lane is the "
            f"SEPARATE OSM-proximity estimate also used for DC (within "
            f"~30m of a mapped cycleway) -- it can disagree with "
            f"in_bike_lane (e.g. a real lane exists but isn't mapped on "
            f"OSM yet, or the officer's 'in bike lane' call was about a "
            f"lane too new/minor to be in OSM). Both are shown, not "
            f"reconciled into one number."
        ),
        "records_excluded_no_geo_or_ward": no_geo,
        "total_records": len(records),
        "by_ward": ward_rows,
        "geojson": {"type": "FeatureCollection", "features": features},
    }


def build_ward_exposure() -> dict:
    lookup = WardLookup()
    month_trips = cached_month_trips(RECENT_MONTHS)
    months_fetched = sorted(month_trips.keys())

    ward_trips = defaultdict(lambda: {"total": 0, "electric_bike": 0})
    unmapped = 0
    for trips in month_trips.values():
        for t in trips:
            ward = lookup.ward_for(t["lon"], t["lat"])
            if not ward:
                unmapped += 1
                continue
            ward_trips[ward]["total"] += 1
            if t["rideable_type"] == "electric_bike":
                ward_trips[ward]["electric_bike"] += 1

    if not months_fetched:
        return {"window": {"start": None, "end": None}, "unmapped_trips": 0,
                "measure_note": "No Divvy months were available.", "by_ward": []}

    win_start_y, win_start_m = int(months_fetched[0][:4]), int(months_fetched[0][4:])
    win_start = datetime(win_start_y, win_start_m, 1, tzinfo=timezone.utc)
    last_y, last_m = int(months_fetched[-1][:4]), int(months_fetched[-1][4:])
    win_end = datetime(last_y + (1 if last_m == 12 else 0), 1 if last_m == 12 else last_m + 1, 1, tzinfo=timezone.utc)

    records = cached_bicycle_crashes(CRASH_CUTOFF)
    crashes_in_window = defaultdict(int)
    for r in records:
        cd = r.get("crash_date")
        if not cd:
            continue
        d = datetime.fromisoformat(cd.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
        if not (win_start <= d < win_end):
            continue
        lat, lon = r.get("crash_latitude"), r.get("crash_longitude")
        if not lat or not lon:
            continue
        ward = lookup.ward_for(float(lon), float(lat))
        if ward:
            crashes_in_window[ward] += 1

    rows = []
    for ward in sorted(set(ward_trips) | set(crashes_in_window)):
        trips = ward_trips.get(ward, {"total": 0, "electric_bike": 0})
        crashes = crashes_in_window.get(ward, 0)
        rate = (crashes / trips["total"] * 1000) if trips["total"] else None
        rows.append({
            "ward": ward, "crashes_in_window": crashes,
            "divvy_trips_in_window": trips["total"],
            "divvy_ebike_trips_in_window": trips["electric_bike"],
            "crashes_per_1000_divvy_trips": round(rate, 2) if rate is not None else None,
        })
    rows.sort(key=lambda r: -(r["crashes_per_1000_divvy_trips"] or 0))

    return {
        "window": {"start": win_start.strftime("%Y-%m-%d"), "end": (win_end - timedelta(days=1)).strftime("%Y-%m-%d")},
        "unmapped_trips": unmapped,
        "measure_note": (
            "NOT a true risk-per-rider rate, same caveat as DC: the "
            "numerator (crashes) includes ALL cyclists, the denominator "
            "(Divvy trips) only Divvy's fleet. Read as 'crash activity "
            "relative to Divvy activity', not 'risk per cyclist'."
        ),
        "by_ward": rows,
    }


def build_bike_lanes_geojson() -> dict:
    """Written as a SEPARATE file, same reasoning as DC: the lane
    geometry (~7,600 ways, ~52,823 points) would meaningfully bloat the
    main payload; the dashboard already lazy-loads each tab independently."""
    lanes = cached_bike_lanes()
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in w["geometry"]]},
            "properties": {"name": w["tags"].get("name", "")},
        }
        for w in lanes if len(w["geometry"]) >= 2
    ]
    return {
        "type": "FeatureCollection",
        "provenance_note": (
            "OpenStreetMap cycleway/bike-lane geometry within Chicago, "
            "fetched via the free Overpass API. Crowdsourced/volunteer-"
            "mapped data -- shown for infrastructure CONTEXT only, never "
            "to detect crashes."
        ),
        "features": features,
    }


def build() -> dict:
    return {"ward_summary": build_ward_summary(), "ward_exposure": build_ward_exposure()}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    result = build()
    (OUT / "chicago_pilot.json").write_text(json.dumps(result, indent=2))
    ws = result["ward_summary"]
    print(f"Total records: {ws['total_records']} ({ws['records_excluded_no_geo_or_ward']} excluded: no geo/ward)")
    print("By ward (top 10):")
    for r in ws["by_ward"][:10]:
        helmet_known = r["helmet_used"] + r["helmet_not_used"]
        helmet_pct = (r["helmet_used"] / helmet_known * 100) if helmet_known else 0
        print(f"  {r['ward']:10} crashes={r['crashes']:4} fatal={r['fatal']:2} "
              f"major={r['major_injury']:3} helmet_used={helmet_pct:.0f}% "
              f"in_lane={r['in_bike_lane']:3} near_lane={r['near_mapped_bike_lane']:3} "
              f"minors={r['minors_involved']:3}")
    we = result["ward_exposure"]
    print(f"\nWard exposure ({we['window']['start']} to {we['window']['end']}):")
    for r in we["by_ward"][:10]:
        print(f"  {r['ward']:10} crashes={r['crashes_in_window']:3} "
              f"divvy_trips={r['divvy_trips_in_window']:6} rate={r['crashes_per_1000_divvy_trips']}")

    lanes_geojson = build_bike_lanes_geojson()
    (OUT / "chicago_bike_lanes.geojson").write_text(json.dumps(lanes_geojson))
    print(f"\nWrote {OUT / 'chicago_bike_lanes.geojson'} ({len(lanes_geojson['features'])} lane segments)")
    print(f"\nWrote {OUT / 'chicago_pilot.json'}")
