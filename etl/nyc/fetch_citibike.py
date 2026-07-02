"""Fetch Citi Bike (NYC) monthly trip-history CSVs from their S3 bucket.

Confirmed: Citi Bike is operated by Lyft on the same platform as Divvy and
Bluebikes. The rideable_type field ("electric_bike" / "classic_bike") has
been present since Lyft's acquisition. Trip CSVs include per-trip
start_lat / start_lng.

S3 bucket: s3.amazonaws.com/tripdata
File naming: {YYYYMM}-citibike-tripdata.csv.zip
  Some months may also be available as .zip (without .csv); we try both.

NOTE: Citi Bike also publishes a Jersey City (JC) dataset with prefix
"JC-{YYYYMM}-citibike-tripdata.csv.zip" -- excluded here since JC is
outside NYC's five boroughs.
"""
from __future__ import annotations

import csv
import io
import json
import socket
import sys
import time
import urllib.request
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError

S3_BASE = "https://s3.amazonaws.com/tripdata"
RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "nyc"

# NYC Citi Bike monthly files are very large (hundreds of MB), so slow or
# reset connections are common. Use a generous read timeout and retry a
# few times on transient network errors rather than letting one timeout
# abort the whole multi-month build.
DOWNLOAD_TIMEOUT = 600
MAX_RETRIES = 4


def _download(url: str) -> bytes:
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(url, headers={"User-Agent": "ebike-crash-intel/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as r:
                return r.read()
        except HTTPError:
            raise  # 404 / other HTTP status handled by caller
        except (URLError, socket.timeout, ConnectionError) as e:
            last_err = e
            wait = 5 * attempt
            print(f"    download attempt {attempt}/{MAX_RETRIES} failed ({e}); "
                  f"retrying in {wait}s...")
            time.sleep(wait)
    raise last_err  # type: ignore[misc]


def fetch_month_trips(yyyymm: str) -> list[dict]:
    """Returns [{"rideable_type": str, "lat": float, "lon": float}] for
    every Citi Bike trip in one month (NYC fleet only, not JC)."""
    # Try standard .csv.zip first, then .zip fallback
    for suffix in [f"{yyyymm}-citibike-tripdata.csv.zip",
                   f"{yyyymm}-citibike-tripdata.zip"]:
        url = f"{S3_BASE}/{suffix}"
        try:
            zip_bytes = _download(url)
            break
        except HTTPError as e:
            if e.code == 404:
                continue
            raise
    else:
        raise HTTPError(url, 404, "Not found under either naming convention", {}, None)  # type: ignore[arg-type]

    trips = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        # Exclude JC files if accidentally bundled in
        csv_names = [n for n in z.namelist()
                     if n.endswith(".csv") and "__MACOSX" not in n and not n.startswith("JC")]
        if not csv_names:
            return []
        with z.open(csv_names[0]) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            for row in reader:
                lat = row.get("start_lat")
                lon = row.get("start_lng")
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
        cache_path = RAW / f"citibike_trips_{m}.json"
        if cache_path.exists():
            out[m] = json.loads(cache_path.read_text())
            continue
        print(f"  fetching Citi Bike trips for {m}...")
        try:
            trips = fetch_month_trips(m)
        except HTTPError as e:
            print(f"    skipping {m}: not available ({e.code})")
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
