"""Fetch Divvy (Chicago bikeshare) monthly trip-history CSVs.

Confirmed directly: Divvy is operated by Lyft, same company as Capital
Bikeshare, and publishes the EXACT same schema -- including the
e-bike-specific `rideable_type` field ("electric_bike" vs "classic_bike").
~70% of trips checked were electric_bike, consistent with DC's finding.

Genuinely SIMPLER than Capital Bikeshare's case: every Divvy trip row has
its own start_lat/start_lng directly (confirmed: 100% of rows in a sample
month), even for the ~21% of trips with no station_id (dockless e-bike
trips). No need to build a station-to-coordinate lookup first -- map each
trip's own coordinate straight to a ward.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path
from urllib.error import HTTPError

S3_BASE = "https://s3.amazonaws.com/divvy-tripdata"
RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "chicago"


def fetch_month_trips(yyyymm: str) -> list[dict]:
    """Returns [{"rideable_type": str, "lat": float, "lon": float}] for
    every trip in one month -- only the fields needed for ward mapping +
    e-bike share, not full trip records (no need to retain ride_id/times/
    member type for this project's purposes)."""
    url = f"{S3_BASE}/{yyyymm}-divvy-tripdata.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "ebike-crash-intel/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        zip_bytes = r.read()

    trips = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        csv_name = next(n for n in z.namelist() if n.endswith(".csv") and "__MACOSX" not in n)
        with z.open(csv_name) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            for row in reader:
                lat, lon = row.get("start_lat"), row.get("start_lng")
                if not lat or not lon:
                    continue
                trips.append({
                    "rideable_type": row.get("rideable_type", "unknown"),
                    "lat": round(float(lat), 5),
                    "lon": round(float(lon), 5),
                })
    return trips


def cached_month_trips(months: list[str]) -> dict[str, list[dict]]:
    RAW.mkdir(parents=True, exist_ok=True)
    out = {}
    for m in months:
        cache_path = RAW / f"divvy_trips_{m}.json"
        if cache_path.exists():
            out[m] = json.loads(cache_path.read_text())
            continue
        print(f"  fetching Divvy trips for {m}...")
        try:
            trips = fetch_month_trips(m)
        except HTTPError as e:
            print(f"    skipping {m}: not available yet ({e.code})")
            continue
        cache_path.write_text(json.dumps(trips))
        out[m] = trips
    return out


if __name__ == "__main__":
    months = sys.argv[1:] or ["202605"]
    result = cached_month_trips(months)
    for m, trips in result.items():
        total = len(trips)
        ebike = sum(1 for t in trips if t["rideable_type"] == "electric_bike")
        print(f"{m}: {total:,} total trips -- {ebike:,} e-bike ({ebike/total*100:.0f}%)" if total else f"{m}: no data")
