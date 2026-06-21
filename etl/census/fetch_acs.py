"""Fetch state-level bike-commute share from the Census ACS 5-year estimates.

Why this exists: turning a fatality COUNT into anything resembling a RISK
requires a denominator. We have no national ridership data (the brief calls
this "one of the hardest gaps to fill" -- BikeMaps.org solves it locally
with Strava Metro, which we don't have access to). ACS table B08301 asks
commuters their primary means of transportation to work, including
"Bicycle" -- this is a real, free, federal, no-rate-limit proxy for cycling
prevalence by state.

HONESTY CAVEAT THIS MODULE MUST CARRY DOWNSTREAM: this is a COMMUTE-cycling
proxy, not a ridership count. It misses recreational riding, delivery
riding, and trips by minors (who don't commute to work) -- exactly the
population this project cares most about for e-bikes. We use it because
it's the best available federal data, not because it's a good fit. Any
"risk ranking" built on it must say so every time, not just once in a
docstring.

As of May 2026, Census requires an API key for every request (previously
rate-limited but key-optional). Free, instant signup at
https://api.census.gov/data/key_signup.html -- read from the
CENSUS_API_KEY environment variable, never hardcoded.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def _load_dotenv_local() -> None:
    """Local-dev convenience only: if CENSUS_API_KEY isn't already in the
    environment, check for a gitignored .env.local at the repo root. CI
    (GitHub Actions) sets the real env var from a repo secret and never
    touches this file."""
    if os.environ.get("CENSUS_API_KEY"):
        return
    env_path = Path(__file__).resolve().parents[2] / ".env.local"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv_local()

ACS_URL = "https://api.census.gov/data/2022/acs/acs5"
TOTAL_COMMUTERS_VAR = "B08301_001E"   # Total workers 16+ who commute
BIKE_COMMUTERS_VAR = "B08301_018E"    # ...of whom bike to work

RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "census"


def fetch_bike_commute_by_state() -> dict[str, dict]:
    """Returns {state_name: {"total_commuters": int, "bike_commuters": int,
    "bike_commute_share": float}} for all 50 states + DC."""
    key = os.environ.get("CENSUS_API_KEY")
    if not key:
        raise RuntimeError(
            "CENSUS_API_KEY not set. Get a free key at "
            "https://api.census.gov/data/key_signup.html and export it, "
            "or set it as a GitHub Actions secret for CI runs."
        )
    params = {
        "get": f"NAME,{TOTAL_COMMUTERS_VAR},{BIKE_COMMUTERS_VAR}",
        "for": "state:*",
        "key": key,
    }
    url = ACS_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ebike-crash-intel/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        rows = json.loads(r.read())

    header, *data_rows = rows
    idx = {c: i for i, c in enumerate(header)}
    out = {}
    for row in data_rows:
        name = row[idx["NAME"]]
        total = int(row[idx[TOTAL_COMMUTERS_VAR]])
        bike = int(row[idx[BIKE_COMMUTERS_VAR]])
        out[name] = {
            "total_commuters": total,
            "bike_commuters": bike,
            "bike_commute_share": (bike / total) if total else 0.0,
        }
    return out


def cached_bike_commute_by_state() -> dict[str, dict]:
    """Fetch + cache to disk (ACS 5-year estimates update annually; no need
    to hit the API every pipeline run)."""
    RAW.mkdir(parents=True, exist_ok=True)
    cache_path = RAW / "acs_bike_commute_by_state.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    data = fetch_bike_commute_by_state()
    cache_path.write_text(json.dumps(data, indent=2))
    return data


if __name__ == "__main__":
    data = fetch_bike_commute_by_state()
    ranked = sorted(data.items(), key=lambda kv: -kv[1]["bike_commute_share"])
    print(f"Fetched bike-commute data for {len(data)} states/DC")
    print("\nTop 10 by bike-commute share:")
    for name, d in ranked[:10]:
        pct = d["bike_commute_share"] * 100
        print(f"  {pct:.2f}%  {name}  ({d['bike_commuters']:,} of {d['total_commuters']:,} commuters)")
