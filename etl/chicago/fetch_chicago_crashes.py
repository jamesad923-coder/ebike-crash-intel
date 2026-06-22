"""Fetch Chicago bicycle-involved crash records via the city's Socrata API.

Real, live, verified directly (not assumed): Chicago publishes crash data
across THREE linked datasets (Socrata can't join across datasets server-
side, so we join in Python):
  - "Traffic Crashes - People" (u6pd-qa9d): one row per person, including
    person_type="BICYCLE" -- this is how we find bicyclists at all. Carries
    age, sex, injury_classification, safety_equipment (HELMET use -- a
    real field this project doesn't have cleanly from any other source),
    and pedpedal_location ("BIKE LANE" vs "IN ROADWAY" -- a directly
    police-reported field, more reliable than the OSM-proximity estimate
    built for DC).
  - "Traffic Crashes - Crashes" (85ca-t3if): one row per crash, with
    lat/lon, lighting/weather/road conditions, and crash_date. Joined to
    the People rows via crash_record_id.

Chicago's data goes back to 2015 (full range 2015-08 to present, confirmed
directly) -- same kind of "don't silently mix uneven years" consideration
as DC, though Chicago's reporting looks more consistent throughout (not
verified to the same depth as DC's pre-2016 gap; flagged as an assumption,
not a confirmed fact, in DATA_SOURCES.md).
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

PEOPLE_URL = "https://data.cityofchicago.org/resource/u6pd-qa9d.json"
CRASHES_URL = "https://data.cityofchicago.org/resource/85ca-t3if.json"
RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "chicago"

PAGE_SIZE = 1000
JOIN_BATCH_SIZE = 25  # crash_record_id values are ~128 hex chars each --
# the original 200-per-batch attempt produced an HTTP 414 (URI too long),
# confirmed directly. 25 keeps the query URL comfortably under typical
# server/proxy URL length limits.


def _get(url: str, params: dict) -> list[dict]:
    full_url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full_url, headers={"User-Agent": "ebike-crash-intel/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_bicycle_people(cutoff_date: str) -> list[dict]:
    """All person records with person_type=BICYCLE on/after cutoff_date
    (YYYY-MM-DD), paginated."""
    out = []
    offset = 0
    where = f"person_type='BICYCLE' AND crash_date>='{cutoff_date}'"
    while True:
        rows = _get(PEOPLE_URL, {
            "$where": where, "$limit": PAGE_SIZE, "$offset": offset,
            "$order": "crash_record_id",
        })
        if not rows:
            break
        out.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.2)
    return out


def fetch_crashes_by_id(crash_record_ids: list[str]) -> dict[str, dict]:
    """Batch-fetch crash records (lat/lon, conditions) for a specific set
    of crash_record_ids -- avoids pulling Chicago's full ~500K-crash table
    just to find the ~11K that involve a bicyclist."""
    out = {}
    ids = list(set(crash_record_ids))
    for i in range(0, len(ids), JOIN_BATCH_SIZE):
        batch = ids[i:i + JOIN_BATCH_SIZE]
        id_list = ",".join(f"'{cid}'" for cid in batch)
        rows = _get(CRASHES_URL, {
            "$where": f"crash_record_id in ({id_list})",
            "$select": "crash_record_id,crash_date,latitude,longitude,lighting_condition,"
                       "weather_condition,roadway_surface_cond,posted_speed_limit,crash_hour",
            "$limit": JOIN_BATCH_SIZE,
        })
        for r in rows:
            out[r["crash_record_id"]] = r
        time.sleep(0.2)
    return out


def cached_bicycle_crashes(cutoff_date: str = "2021-01-01") -> list[dict]:
    """Returns joined person+crash records: one row per bicyclist person
    record, with crash-level fields merged in."""
    RAW.mkdir(parents=True, exist_ok=True)
    cache_path = RAW / "chicago_bicycle_crashes.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    people = fetch_bicycle_people(cutoff_date)
    crash_ids = [p["crash_record_id"] for p in people]
    crashes = fetch_crashes_by_id(crash_ids)

    joined = []
    for p in people:
        c = crashes.get(p["crash_record_id"], {})
        joined.append({**p, **{f"crash_{k}": v for k, v in c.items() if k != "crash_record_id"}})

    cache_path.write_text(json.dumps(joined))
    return joined


if __name__ == "__main__":
    import sys
    cutoff = sys.argv[1] if len(sys.argv) > 1 else "2021-01-01"
    records = cached_bicycle_crashes(cutoff)
    print(f"Fetched {len(records)} bicyclist person records since {cutoff}")
    with_geo = sum(1 for r in records if r.get("crash_latitude"))
    print(f"With lat/lon (joined successfully): {with_geo}")
    helmet_used = sum(1 for r in records if "HELMET" in (r.get("safety_equipment") or "") and "NOT USED" not in (r.get("safety_equipment") or ""))
    print(f"Helmet used (of those with a safety_equipment value): {helmet_used}")
    in_bike_lane = sum(1 for r in records if r.get("pedpedal_location") == "BIKE LANE")
    print(f"Reported as 'in bike lane' at crash time: {in_bike_lane}")
