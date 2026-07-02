"""Boston pilot: district-level bicycle crash summary + Bluebikes e-bike
trip context. Third city pilot after DC and Chicago -- verified independently,
same schema discipline.

Schema matches DC's dc_pilot.json structure:
  ward_summary (using "District N" labels in the ward field)
  bikeshare_context (monthly Bluebikes trend -- same Lyft platform as DC)
  ward_exposure (crashes relative to Bluebikes activity, by district)

HONESTY LIMITS:
  - Boston VZ data has no e-bike-specific flag (same gap as every city).
  - Severity only available as "Fatal injury" / "Non-fatal injury" / other
    -- no separate major/minor split; "injury" here means any non-fatal
    crash that Boston coded as a non-fatal injury.
  - No speeding field available in Boston's VZ dataset.
  - District assignment via point-in-polygon against Boston City Council
    District boundaries (no district field directly in the crash records).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from boston.fetch_boston_crashes import cached_bicycle_crashes  # noqa: E402
from boston.fetch_bluebikes import cached_month_trips  # noqa: E402
from boston.district_boundaries import WardLookup  # noqa: E402
from boston.fetch_bike_lanes import cached_bike_lanes  # noqa: E402
from dc.bike_lane_proximity import BikeLaneIndex  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "data"

CRASH_CUTOFF = "2021-01-01"  # ~5 years, matching DC and Chicago window length


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


def _parse_date(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _is_fatal(severity: str | None) -> bool:
    return "fatal" in (severity or "").lower()


def _is_injury(severity: str | None) -> bool:
    s = (severity or "").lower()
    return "non-fatal" in s or "injury" in s


def build_ward_summary() -> dict:
    records = cached_bicycle_crashes()
    lookup = WardLookup()
    lane_index = BikeLaneIndex(cached_bike_lanes())

    cutoff = datetime.fromisoformat(CRASH_CUTOFF).replace(tzinfo=timezone.utc)

    by_ward = defaultdict(lambda: {"crashes": 0, "fatal": 0, "injury": 0, "near_bike_lane": 0})
    no_geo = 0
    features = []
    all_dates = []

    for r in records:
        d = _parse_date(r.get("dispatch_ts"))
        if d and d < cutoff:
            continue

        lat_s, lon_s = r.get("lat"), r.get("long")
        if not lat_s or not lon_s:
            no_geo += 1
            continue
        try:
            lat, lon = float(lat_s), float(lon_s)
        except (ValueError, TypeError):
            no_geo += 1
            continue

        district = lookup.ward_for(lon, lat)
        if not district:
            no_geo += 1
            continue

        if d:
            all_dates.append(d)

        fatal = _is_fatal(r.get("severity"))
        injury = _is_injury(r.get("severity"))
        near_lane = lane_index.is_near(lat, lon)

        w = by_ward[district]
        w["crashes"] += 1
        w["fatal"] += int(fatal)
        w["injury"] += int(injury and not fatal)
        w["near_bike_lane"] += int(near_lane)

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "ward": district,
                "fatal": fatal,
                "injury": injury,
                "near_bike_lane": near_lane,
                "date": d.strftime("%Y-%m-%d") if d else "",
            },
        })

    ward_rows = [{"ward": w, **stats} for w, stats in by_ward.items()]
    ward_rows.sort(key=lambda r: -r["crashes"])
    end_date = max(all_dates).strftime("%Y-%m-%d") if all_dates else None

    return {
        "date_window": {
            "start": CRASH_CUTOFF,
            "end": end_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "years": 5,
        },
        "measure_note": (
            f"Bicyclist-involved crash COUNTS by Boston City Council District, "
            f"{CRASH_CUTOFF} onward (~5 years, matching DC and Chicago window "
            f"length as a consistency choice). Source: City of Boston Vision "
            f"Zero Crash Records (data.boston.gov). NOT exposure-adjusted -- "
            f"no per-district ridership data available. Boston's VZ data has "
            f"no e-bike-specific flag and no separate major/minor injury split "
            f"(only 'Fatal injury' vs 'Non-fatal injury'). District assigned "
            f"via point-in-polygon against official City Council District "
            f"boundaries -- no district field in the crash records directly. "
            f"'near_bike_lane' means within ~30m of an OSM-mapped cycleway "
            f"(infrastructure context, not a cause)."
        ),
        "records_excluded_no_geo_or_district": no_geo,
        "total_records": len(records),
        "by_ward": ward_rows,
        "geojson": {"type": "FeatureCollection", "features": features},
    }


def build_bikeshare_context() -> dict:
    month_trips = cached_month_trips(RECENT_MONTHS)
    rows = []
    for m, trips in sorted(month_trips.items()):
        total = len(trips)
        ebike = sum(1 for t in trips if t["rideable_type"] == "electric_bike")
        classic = sum(1 for t in trips if t["rideable_type"] == "classic_bike")
        rows.append({
            "month": m,
            "total_trips": total,
            "electric_bike_trips": ebike,
            "classic_bike_trips": classic,
            "electric_bike_share": round(ebike / total, 3) if total else 0,
        })
    return {
        "measure_note": (
            "Bluebikes monthly trip data (hubway-data S3 bucket -- Bluebikes "
            "was originally called Hubway). Same Lyft platform as Capital "
            "Bikeshare and Divvy; same rideable_type field distinguishing "
            "electric_bike from classic_bike per trip. Covers ONLY Bluebikes' "
            "own fleet -- says nothing about personally-owned e-bikes. Shown "
            "as citywide context, not blended into district crash counts."
        ),
        "monthly": rows,
    }


def build_ward_exposure() -> dict:
    lookup = WardLookup()
    month_trips = cached_month_trips(RECENT_MONTHS)
    months_fetched = sorted(month_trips.keys())

    ward_trips = defaultdict(lambda: {"total": 0, "electric_bike": 0})
    unmapped = 0
    for trips in month_trips.values():
        for t in trips:
            district = lookup.ward_for(t["lon"], t["lat"])
            if not district:
                unmapped += 1
                continue
            ward_trips[district]["total"] += 1
            if t["rideable_type"] == "electric_bike":
                ward_trips[district]["electric_bike"] += 1

    if not months_fetched:
        return {
            "window": {"start": None, "end": None}, "unmapped_trips": 0,
            "measure_note": "No Bluebikes months were available.", "by_ward": [],
        }

    win_start_y, win_start_m = int(months_fetched[0][:4]), int(months_fetched[0][4:])
    win_start = datetime(win_start_y, win_start_m, 1, tzinfo=timezone.utc)
    last_y, last_m = int(months_fetched[-1][:4]), int(months_fetched[-1][4:])
    win_end = datetime(last_y + (1 if last_m == 12 else 0), 1 if last_m == 12 else last_m + 1, 1, tzinfo=timezone.utc)

    records = cached_bicycle_crashes()
    crashes_in_window = defaultdict(int)
    for r in records:
        d = _parse_date(r.get("dispatch_ts"))
        if not d or not (win_start <= d < win_end):
            continue
        lat_s, lon_s = r.get("lat"), r.get("long")
        if not lat_s or not lon_s:
            continue
        try:
            lat, lon = float(lat_s), float(lon_s)
        except (ValueError, TypeError):
            continue
        district = lookup.ward_for(lon, lat)
        if district:
            crashes_in_window[district] += 1

    rows = []
    for district in sorted(set(ward_trips) | set(crashes_in_window)):
        trips = ward_trips.get(district, {"total": 0, "electric_bike": 0})
        crashes = crashes_in_window.get(district, 0)
        rate = (crashes / trips["total"] * 1000) if trips["total"] else None
        rows.append({
            "ward": district,
            "crashes_in_window": crashes,
            "bluebikes_trips_in_window": trips["total"],
            "bluebikes_ebike_trips_in_window": trips["electric_bike"],
            "crashes_per_1000_bluebikes_trips": round(rate, 2) if rate is not None else None,
        })
    rows.sort(key=lambda r: -(r["crashes_per_1000_bluebikes_trips"] or 0))

    return {
        "window": {
            "start": win_start.strftime("%Y-%m-%d"),
            "end": (win_end - timedelta(days=1)).strftime("%Y-%m-%d"),
        },
        "unmapped_trips": unmapped,
        "measure_note": (
            "NOT a true risk-per-rider rate -- same caveat as DC and Chicago. "
            "Numerator (crashes) includes ALL cyclists; denominator (Bluebikes "
            "trips) is Bluebikes' fleet only. Read as 'crash activity relative "
            "to Bluebikes activity', not 'risk per cyclist'."
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
            "OpenStreetMap cycleway/bike-lane geometry within Boston, "
            "fetched via the free Overpass API. Shown for infrastructure "
            "CONTEXT only, never to detect crashes."
        ),
        "features": features,
    }


def build() -> dict:
    return {
        "ward_summary": build_ward_summary(),
        "bikeshare_context": build_bikeshare_context(),
        "ward_exposure": build_ward_exposure(),
    }


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    result = build()
    (OUT / "boston_pilot.json").write_text(json.dumps(result, indent=2))
    ws = result["ward_summary"]
    print(f"Total records: {ws['total_records']} ({ws['records_excluded_no_geo_or_district']} excluded)")
    print("By district:")
    for r in ws["by_ward"]:
        pct_lane = (r["near_bike_lane"] / r["crashes"] * 100) if r["crashes"] else 0
        print(f"  {r['ward']:12} crashes={r['crashes']:4} fatal={r['fatal']:2} "
              f"injury={r['injury']:4} near_lane={pct_lane:.0f}%")

    lanes_geojson = build_bike_lanes_geojson()
    (OUT / "boston_bike_lanes.geojson").write_text(json.dumps(lanes_geojson))
    print(f"\nWrote {OUT / 'boston_pilot.json'} and {OUT / 'boston_bike_lanes.geojson'} "
          f"({len(lanes_geojson['features'])} lane segments)")

    we = result["ward_exposure"]
    print(f"\nWard exposure ({we['window']['start']} to {we['window']['end']}):")
    for r in we["by_ward"]:
        print(f"  {r['ward']:12} crashes={r['crashes_in_window']:3} "
              f"bluebikes_trips={r['bluebikes_trips_in_window']:6} "
              f"rate={r['crashes_per_1000_bluebikes_trips']}")
