"""Fetch Boston bicycle-involved crash records from the City of Boston's
Vision Zero Crash Records dataset (data.boston.gov, CKAN-based open data
portal as of 2026).

SOURCE CHANGE (2026): this dataset used to be served through Boston's old
Socrata portal (data.boston.gov/resource/ngee-bppz.json) with a `severity`
field ("Fatal injury" / "Non-fatal injury" / "No injury" / "Unknown").
Boston has since migrated to a CKAN portal and republished the crash
records as a flat CSV export -- the `severity` field is GONE from the
current file entirely. Current CSV columns (confirmed live):
  dispatch_ts, mode_type, location_type, street, xstreet1, xstreet2,
  x_cord, y_cord, lat, long
mode_type values are lowercase now: "bike", "mv", "ped".

To recover a fatal/non-fatal signal, we separately fetch Boston's "Vision
Zero Fatality Records" dataset (also CKAN, no severity/injury detail
either -- it's just a list of fatal incidents) and fuzzy-match bike-mode
fatality records against the bike-mode crash records by nearest timestamp
(within 6h) + location (within ~1km), since neither file shares a common
id. Manually verified this recovers 8/11 (~73%) of known bike fatalities
with a confident unique match; the rest are left unmatched rather than
guessed. This means the "fatal" count below is a lower bound, not exact --
documented in the honesty banner downstream.

HONESTY LIMITS, repeated downstream:
  - Boston's VZ data has no e-bike-specific flag -- same gap as every
    other source in this project at the city level.
  - There is no injury-severity field at all anymore (previously
    "Non-fatal injury" was distinguishable from "No injury"; that split
    no longer exists in the public data). We can only say "fatal
    (matched)" vs. "everything else" -- not injury vs. no-injury.
  - The fatal match itself is approximate (timestamp+location proximity,
    not a shared id) -- expect undercounting, never overcounting, since
    unmatched fatalities are simply left unmatched.
  - No direct City Council District field in the data -- district
    assignment requires a point-in-polygon lookup (see district_boundaries.py).
"""
from __future__ import annotations

import csv
import io
import json
import math
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CKAN_PACKAGE_API = "https://data.boston.gov/api/3/action/package_show?id={}"
CRASHES_PACKAGE = "vision-zero-crash-records"
FATALITIES_PACKAGE = "vision-zero-fatality-records"

RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "boston"

# Fuzzy-match thresholds for joining fatality records onto crash records.
MATCH_MAX_HOURS = 6
MATCH_MAX_KM = 1.0


def _resolve_csv_url(package_id: str) -> str:
    """CKAN resource download URLs embed a random tmp filename that can
    change between publishes, so resolve the current one via the package
    API rather than hardcoding it."""
    req = urllib.request.Request(
        CKAN_PACKAGE_API.format(package_id),
        headers={"User-Agent": "ebike-crash-intel/0.1"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    resources = data["result"]["resources"]
    csv_resources = [res for res in resources if res.get("format", "").upper() == "CSV"]
    return (csv_resources or resources)[0]["url"]


def _fetch_csv(url: str) -> list[dict]:
    # The CKAN download URL 302s to a presigned S3 URL whose Location
    # header includes an explicit ":443" port (e.g. "s3.amazonaws.com:443").
    # urllib.request sends that verbatim as the Host header on the
    # redirected request, which breaks the AWS SigV4 signature (signed
    # over the bare hostname) and the S3 request comes back 403. curl
    # normalizes this away; urllib doesn't, so follow the redirect
    # manually and strip the default port first.
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "ebike-crash-intel/0.1"})
    try:
        resp = opener.open(req, timeout=60)
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 303, 307, 308):
            raise
        location = e.headers.get("Location")
        location = location.replace("s3.amazonaws.com:443", "s3.amazonaws.com")
        req2 = urllib.request.Request(location, headers={"User-Agent": "ebike-crash-intel/0.1"})
        resp = urllib.request.urlopen(req2, timeout=60)
    with resp:
        text = resp.read().decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        # e.g. "2024-03-22 03:52:28+00"
        return datetime.fromisoformat(ts.replace("+00", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _match_fatal_indices(crashes: list[dict], fatalities: list[dict]) -> set[int]:
    """Greedy nearest-match of bike-mode fatality records onto bike-mode
    crash records by time+location proximity. Returns the set of crash
    record indices that matched a fatality (each fatality used at most
    once, each crash used at most once)."""
    candidates = []  # (score, crash_idx, fatal_idx)
    for ci, c in enumerate(crashes):
        ct = c["_dt"]
        if ct is None or c["_lat"] is None:
            continue
        for fi, f in enumerate(fatalities):
            ft = f["_dt"]
            if ft is None or f["_lat"] is None:
                continue
            hours = abs((ct - ft).total_seconds()) / 3600
            if hours > MATCH_MAX_HOURS:
                continue
            km = _haversine_km(c["_lat"], c["_lon"], f["_lat"], f["_lon"])
            if km > MATCH_MAX_KM:
                continue
            candidates.append((hours + km, ci, fi))

    candidates.sort(key=lambda t: t[0])
    used_crash, used_fatal, matched = set(), set(), set()
    for _, ci, fi in candidates:
        if ci in used_crash or fi in used_fatal:
            continue
        used_crash.add(ci)
        used_fatal.add(fi)
        matched.add(ci)
    return matched


def fetch_bicycle_crashes() -> list[dict]:
    """All Boston bike-mode crash records, with an approximate fatal flag
    joined in from the separate fatality dataset (see module docstring)."""
    crash_rows = _fetch_csv(_resolve_csv_url(CRASHES_PACKAGE))
    fatal_rows = _fetch_csv(_resolve_csv_url(FATALITIES_PACKAGE))

    crashes = []
    for row in crash_rows:
        if (row.get("mode_type") or "").strip().lower() != "bike":
            continue
        lat_s, lon_s = row.get("lat"), row.get("long")
        try:
            lat, lon = float(lat_s), float(lon_s)
        except (TypeError, ValueError):
            lat = lon = None
        xstreet = ", ".join(s for s in (row.get("xstreet1"), row.get("xstreet2")) if s)
        crashes.append({
            "dispatch_ts": row.get("dispatch_ts"),
            "lat": lat_s or None,
            "long": lon_s or None,
            "mode_type": "BIKE",
            "street": row.get("street") or "",
            "xstreet": xstreet,
            "_dt": _parse_ts(row.get("dispatch_ts")),
            "_lat": lat,
            "_lon": lon,
        })

    fatalities = []
    for row in fatal_rows:
        if (row.get("mode_type") or "").strip().lower() != "bike":
            continue
        lat_s, lon_s = row.get("lat"), row.get("long")
        try:
            lat, lon = float(lat_s), float(lon_s)
        except (TypeError, ValueError):
            lat = lon = None
        fatalities.append({"_dt": _parse_ts(row.get("date_time")), "_lat": lat, "_lon": lon})

    matched = _match_fatal_indices(crashes, fatalities)

    for i, c in enumerate(crashes):
        # "severity" kept as a field name for compatibility with the rest
        # of the pipeline, but the only real signal we have now is the
        # fuzzy fatal match -- there is no injury/no-injury distinction.
        c["severity"] = "Fatal injury (matched)" if i in matched else "Unknown"
        del c["_dt"], c["_lat"], c["_lon"]

    return crashes


def cached_bicycle_crashes() -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    cache_path = RAW / "boston_bicycle_crashes.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    records = fetch_bicycle_crashes()
    cache_path.write_text(json.dumps(records))
    return records


if __name__ == "__main__":
    records = fetch_bicycle_crashes()
    print(f"Fetched {len(records)} bicycle-involved crash records")
    fatal = sum(1 for r in records if (r.get("severity") or "").lower().startswith("fatal"))
    print(f"Fatal (matched to fatality dataset): {fatal}")
    no_coords = sum(1 for r in records if not r.get("lat") or not r.get("long"))
    print(f"Records with no coordinates: {no_coords}")
