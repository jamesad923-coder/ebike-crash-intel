"""Fetch Capital Bikeshare's published monthly trip-history CSVs and
aggregate e-bike vs classic-bike trip volume.

This is a genuinely e-bike-SPECIFIC exposure signal (rideable_type field
distinguishes "electric_bike" from "classic_bike" per trip) -- a real find,
and a better fit for this project than the ACS commute-cycling proxy used
at the state level. Confirmed directly: in the most recent month checked,
electric_bike trips (401,009) outnumbered classic_bike trips (191,546)
roughly 2:1.

HONESTY LIMIT, repeated downstream: this covers Capital Bikeshare's own
fleet ONLY -- it says nothing about personally-owned e-bikes, which is
most of what the teen-fatality news stories we already track involve. We
present this as bikeshare-rider context, not a true citywide e-bike
exposure denominator, and we do NOT use it to compute a per-ward crash
RATE -- that would require mapping each trip's station to a ward, which
we have not built, and faking a rate without that would be exactly the
kind of invented precision this project exists to avoid.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

S3_BASE = "https://s3.amazonaws.com/capitalbikeshare-data"
RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "dc"


def fetch_month(yyyymm: str) -> dict:
    """Returns {"electric_bike": n, "classic_bike": n, "docked_bike": n, ...}
    trip counts for one month, e.g. fetch_month("202605")."""
    url = f"{S3_BASE}/{yyyymm}-capitalbikeshare-tripdata.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "ebike-crash-intel/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        zip_bytes = r.read()

    counts: dict[str, int] = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        csv_name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(csv_name) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            for row in reader:
                rtype = row.get("rideable_type", "unknown")
                counts[rtype] = counts.get(rtype, 0) + 1
    return counts


def cached_recent_months(months: list[str]) -> dict[str, dict]:
    """Fetch + cache trip-type counts for a list of "YYYYMM" months."""
    RAW.mkdir(parents=True, exist_ok=True)
    cache_path = RAW / "capital_bikeshare_monthly_counts.json"
    cached = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    for m in months:
        if m not in cached:
            print(f"  fetching Capital Bikeshare trips for {m}...")
            cached[m] = fetch_month(m)
    cache_path.write_text(json.dumps(cached, indent=2))
    return {m: cached[m] for m in months}


if __name__ == "__main__":
    months = sys.argv[1:] or ["202605"]
    result = cached_recent_months(months)
    for m, counts in result.items():
        total = sum(counts.values())
        ebike = counts.get("electric_bike", 0)
        print(f"{m}: {total:,} total trips -- {ebike:,} e-bike ({ebike/total*100:.0f}%), "
              f"{counts.get('classic_bike', 0):,} classic")
