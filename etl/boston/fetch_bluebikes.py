"""Fetch Bluebikes (Boston) monthly trip-history CSVs from their S3 bucket.

Confirmed directly: Bluebikes is operated by Lyft on the same platform as
Capital Bikeshare and Divvy, and publishes the same CSV schema, including
the e-bike-specific rideable_type field ("electric_bike" / "classic_bike").
Trip files include per-trip start_lat / start_lng -- no station-level
indirection needed (unlike Capital Bikeshare's DC pipeline, which was built
before per-trip coordinates were consistently available).

S3 bucket confirmed: s3.amazonaws.com/hubway-data (Bluebikes was originally
called Hubway; the bucket name was not updated when the brand changed).
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

S3_BASE = "https://s3.amazonaws.com/hubway-data"
RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "boston"


def fetch_month_trips(yyyymm: str) -> list[dict]:
    """Returns [{"rideable_type": str, "lat": float, "lon": float}] for
    every trip in one month -- only the fields needed for district mapping
    and e-bike share tallying."""
    url = f"{S3_BASE}/{yyyymm}-bluebikes-tripdata.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "ebike-crash-intel/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        zip_bytes = r.read()

    trips = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        csv_name = next(n for n in z.namelist() if n.endswith(".csv") and "__MACOSX" not in n)
        with z.open(csv_name) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            for row in reader:
                lat = row.get("start_lat") or row.get("latitude")
                lon = row.get("start_lng") or row.get("longitude")
                if not lat or not lon:
                    continue
                try:
                    trips.append({
                        "rideable_type": row.get("rideable_type", "unknown"),
                        "lat": round(float(lat), 5),
                        "lon": round(float(lon), 5),
                    })
                except (ValueError, TypeError):
                    continue
    return trips


def cached_month_trips(months: list[str]) -> dict[str, list[dict]]:
    RAW.mkdir(parents=True, exist_ok=True)
    out = {}
    for m in months:
        cache_path = RAW / f"bluebikes_trips_{m}.json"
        if cache_path.exists():
            out[m] = json.loads(cache_path.read_text())
            continue
        print(f"  fetching Bluebikes trips for {m}...")
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
        print(f"{m}: {total:,} total -- {ebike:,} e-bike ({ebike/total*100:.0f}%)" if total else f"{m}: no data")
