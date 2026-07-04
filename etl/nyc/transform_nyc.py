"""NYC pilot: borough-level bicyclist crash summary + Citi Bike e-bike
trip exposure. Fourth city pilot.

Schema matches Chicago's chicago_pilot.json structure:
  ward_summary (using borough names as the "ward" field)
  ward_exposure (crashes relative to Citi Bike activity, by borough)

No separate bikeshare_context monthly trend -- unlike Boston/DC where
bikeshare was a secondary context layer, here the exposure table IS the
primary Citi Bike story (borough-level). A monthly trend could be added
later if useful.

HONESTY LIMITS:
  - No e-bike-specific flag in the NYPD crash data (same gap everywhere).
  - NYPD data has cyclist injury/fatality COUNTS per crash, not per person
    demographics -- no age, sex, or helmet data at this level.
  - Borough field is empty for some records; those are excluded from the
    borough summary but counted in total_records.
  - "near_bike_lane" is the standard OSM ~30m proximity flag; NYC has an
    extensive lane network so a high near_bike_lane % is expected -- this
    is infrastructure CONTEXT, not a cause.
  - Citi Bike coverage is concentrated in Manhattan and Brooklyn; Queens
    and Bronx have growing but sparser networks; Staten Island has almost
    none. The exposure ratio is especially uneven across boroughs because
    of this.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nyc.fetch_nyc_crashes import cached_bicycle_crashes  # noqa: E402
from nyc.fetch_citibike import cached_month_trips  # noqa: E402
from nyc.borough_boundaries import WardLookup  # noqa: E402
from nyc.fetch_bike_lanes import cached_bike_lanes  # noqa: E402
from dc.bike_lane_proximity import BikeLaneIndex  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "data"

CRASH_CUTOFF = "2021-01-01"

# NYPD borough field uses ALL CAPS; normalize to Title Case for display
BOROUGH_DISPLAY = {
    "MANHATTAN": "Manhattan",
    "BROOKLYN": "Brooklyn",
    "BRONX": "Bronx",
    "QUEENS": "Queens",
    "STATEN ISLAND": "Staten Island",
}


def _recent_months(n: int = 5) -> list[str]:
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
    lane_index = BikeLaneIndex(cached_bike_lanes())

    by_ward = defaultdict(lambda: {"crashes": 0, "fatal": 0, "cyclist_injured": 0, "near_bike_lane": 0})
    no_geo = 0
    no_borough = 0
    features = []

    for r in records:
        borough_raw = (r.get("borough") or "").strip().upper()
        borough = BOROUGH_DISPLAY.get(borough_raw)
        if not borough:
            no_borough += 1
            continue

        lat_s, lon_s = r.get("latitude"), r.get("longitude")
        if not lat_s or not lon_s:
            no_geo += 1
            continue
        try:
            lat, lon = float(lat_s), float(lon_s)
        except (ValueError, TypeError):
            no_geo += 1
            continue
        # NYPD's dataset contains placeholder coordinates -- 340 records sit
        # at exactly (0, 0) ("Null Island") -- which parse as valid floats
        # and then poison anything spatial downstream (the risk screening's
        # top "hotspot" was the 0,0 grid cell before this check). Reject
        # anything outside a generous NYC bounding box, treating it the
        # same as missing coordinates (excluded and counted in the
        # records_excluded_no_geo figure, like every other no-geo record).
        if not (40.3 < lat < 41.1) or not (-74.4 < lon < -73.5):
            no_geo += 1
            continue

        killed = int(r.get("number_of_cyclist_killed") or 0)
        injured = int(r.get("number_of_cyclist_injured") or 0)
        fatal = killed > 0
        near_lane = lane_index.is_near(lat, lon)

        w = by_ward[borough]
        w["crashes"] += 1
        w["fatal"] += killed
        w["cyclist_injured"] += injured
        w["near_bike_lane"] += int(near_lane)

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "ward": borough,
                "fatal": fatal,
                "cyclist_injured": injured,
                "near_bike_lane": near_lane,
                "date": (r.get("crash_date") or "")[:10],
            },
        })

    ward_rows = [{"ward": w, **stats} for w, stats in by_ward.items()]
    ward_rows.sort(key=lambda r: -r["crashes"])

    return {
        "date_window": {
            "start": CRASH_CUTOFF,
            "end": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "years": 5,
        },
        "measure_note": (
            f"Bicyclist-involved crash COUNTS by NYC borough, {CRASH_CUTOFF} "
            f"onward (~5 years). Source: NYPD Motor Vehicle Collisions - "
            f"Crashes (data.cityofnewyork.us, dataset h9gi-nx95). Crashes "
            f"included where number_of_cyclist_injured>0 OR "
            f"number_of_cyclist_killed>0. Counts are cyclists killed/injured "
            f"per CRASH RECORD, not per person -- one crash can involve "
            f"multiple cyclists. No e-bike flag, no age/sex/helmet data "
            f"available at this level. NOT exposure-adjusted. "
            f"'near_bike_lane' is OSM ~30m proximity; NYC's dense lane "
            f"network means a high pct is expected citywide."
        ),
        "records_excluded_no_borough": no_borough,
        "records_excluded_no_geo": no_geo,
        "total_records": len(records),
        "by_ward": ward_rows,
        "geojson": {"type": "FeatureCollection", "features": features},
    }


def build_ward_exposure() -> dict:
    borough_lookup = WardLookup()
    month_trips = cached_month_trips(RECENT_MONTHS)
    months_fetched = sorted(month_trips.keys())

    ward_trips = defaultdict(lambda: {"total": 0, "electric_bike": 0})
    unmapped = 0
    for trips in month_trips.values():
        for t in trips:
            borough = borough_lookup.ward_for(t["lon"], t["lat"])
            if not borough:
                unmapped += 1
                continue
            # borough_lookup returns ALL CAPS from the GeoJSON; convert
            display = BOROUGH_DISPLAY.get(borough, borough)
            ward_trips[display]["total"] += 1
            if t["rideable_type"] == "electric_bike":
                ward_trips[display]["electric_bike"] += 1

    if not months_fetched:
        return {
            "window": {"start": None, "end": None}, "unmapped_trips": 0,
            "measure_note": "No Citi Bike months were available.", "by_ward": [],
        }

    win_start_y, win_start_m = int(months_fetched[0][:4]), int(months_fetched[0][4:])
    win_start = datetime(win_start_y, win_start_m, 1, tzinfo=timezone.utc)
    last_y, last_m = int(months_fetched[-1][:4]), int(months_fetched[-1][4:])
    win_end = datetime(last_y + (1 if last_m == 12 else 0), 1 if last_m == 12 else last_m + 1, 1, tzinfo=timezone.utc)

    records = cached_bicycle_crashes(CRASH_CUTOFF)
    crashes_in_window = defaultdict(int)
    for r in records:
        cd = (r.get("crash_date") or "")[:10]
        if not cd:
            continue
        try:
            d = datetime.fromisoformat(cd).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if not (win_start <= d < win_end):
            continue
        borough_raw = (r.get("borough") or "").strip().upper()
        borough = BOROUGH_DISPLAY.get(borough_raw)
        if borough:
            crashes_in_window[borough] += 1

    rows = []
    for borough in sorted(set(ward_trips) | set(crashes_in_window)):
        trips = ward_trips.get(borough, {"total": 0, "electric_bike": 0})
        crashes = crashes_in_window.get(borough, 0)
        rate = (crashes / trips["total"] * 1000) if trips["total"] else None
        rows.append({
            "ward": borough,
            "crashes_in_window": crashes,
            "citibike_trips_in_window": trips["total"],
            "citibike_ebike_trips_in_window": trips["electric_bike"],
            "crashes_per_1000_citibike_trips": round(rate, 2) if rate is not None else None,
        })
    rows.sort(key=lambda r: -(r["crashes_per_1000_citibike_trips"] or 0))

    return {
        "window": {
            "start": win_start.strftime("%Y-%m-%d"),
            "end": (win_end - timedelta(days=1)).strftime("%Y-%m-%d"),
        },
        "unmapped_trips": unmapped,
        "measure_note": (
            "NOT a true risk-per-rider rate -- same caveat as DC and Chicago. "
            "Numerator: ALL cyclist crashes in a borough. Denominator: Citi "
            "Bike trips only. Citi Bike coverage is concentrated in Manhattan "
            "and Brooklyn; boroughs with few stations will show very high or "
            "n/a rates because the denominator is near zero, not because they "
            "are proportionally more dangerous per cyclist."
        ),
        "by_ward": rows,
    }


def build_bike_lanes_geojson() -> dict:
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
            "OpenStreetMap cycleway/bike-lane geometry within NYC, "
            "fetched via the free Overpass API. Shown for infrastructure "
            "CONTEXT only, never to detect crashes."
        ),
        "features": features,
    }


def build() -> dict:
    return {"ward_summary": build_ward_summary(), "ward_exposure": build_ward_exposure()}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    result = build()
    (OUT / "nyc_pilot.json").write_text(json.dumps(result, indent=2))
    ws = result["ward_summary"]
    print(f"Total records: {ws['total_records']} "
          f"({ws['records_excluded_no_borough']} no borough, "
          f"{ws['records_excluded_no_geo']} no geo)")
    print("By borough:")
    for r in ws["by_ward"]:
        pct_lane = (r["near_bike_lane"] / r["crashes"] * 100) if r["crashes"] else 0
        print(f"  {r['ward']:14} crashes={r['crashes']:5} fatal={r['fatal']:3} "
              f"injured={r['cyclist_injured']:5} near_lane={pct_lane:.0f}%")
    we = result["ward_exposure"]
    print(f"\nBorough exposure ({we['window']['start']} to {we['window']['end']}):")
    for r in we["by_ward"]:
        print(f"  {r['ward']:14} crashes={r['crashes_in_window']:4} "
              f"citibike_trips={r['citibike_trips_in_window']:7} "
              f"rate={r['crashes_per_1000_citibike_trips']}")

    lanes_geojson = build_bike_lanes_geojson()
    (OUT / "nyc_bike_lanes.geojson").write_text(json.dumps(lanes_geojson))
    print(f"\nWrote {OUT / 'nyc_pilot.json'} and {OUT / 'nyc_bike_lanes.geojson'} "
          f"({len(lanes_geojson['features'])} lane segments)")
