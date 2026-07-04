"""Transform raw FARS CSVs into honest, mappable artifacts.

Outputs (written to web/public/data/ so the static dashboard can read them):
  * fars_points.geojson  - one point per pedalcyclist fatality, age-BANDED
                           (never exact age), with crash type + conditions.
  * fars_summary.json    - aggregates (by year/state/age band/PBCAT group/
                           lighting/time) plus an explicit data-quality block.

We join three FARS files:
  accident.csv  -> location, date/time, lighting (the crash)
  person.csv    -> who (person type, age, sex, injury severity)
  pbtype.csv    -> PBCAT crash typing (the SOURCE-BACKED basis for the
                   "what the report found" / contributing-factor feature)
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.schema import age_band, MINOR_BANDS, source_stamp, MEASURE_COUNT  # noqa: E402
from fars.fetch_fars import fetch_year  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "data"

# Person types that are pedalcyclists. 6=Bicyclist, 7=Other Pedalcyclist.
# (8 = "Person on a Personal Conveyance" = e-scooters/skateboards: tracked
#  separately as broader micromobility, not folded into the bike count.)
PEDALCYCLIST = {"6", "7"}
PERSONAL_CONVEYANCE = {"8"}

# FARS sentinel/unknown values we must treat as missing, not real data.
LAT_BAD = {"77.7777", "88.8888", "99.9999", ""}
LON_BAD = {"777.7777", "888.8888", "999.9999", ""}

# CITYNAME/COUNTYNAME sentinels meaning "no real place coded" -- about a
# third of pedalcyclist fatalities (mostly rural/unincorporated) carry one
# of these instead of a city. Treated as empty, never shown as a place.
PLACE_BAD = {"NOT APPLICABLE", "NOT REPORTED", "REPORTED AS UNKNOWN", "UNKNOWN", ""}


def clean_place(name: str | None) -> str:
    """Normalize a FARS CITYNAME/COUNTYNAME to display case, or '' if it's
    a sentinel. FARS ships these as all-caps ('LOS ANGELES'), and county
    names carry an embedded FIPS code ('MOBILE (97)') that we strip."""
    n = (name or "").strip()
    if n.endswith(")") and "(" in n:
        n = n[:n.rindex("(")].strip()
    if n.upper() in PLACE_BAD:
        return ""
    return n.title()


def _find(csv_dir: Path, name: str) -> Path:
    """Resolve a FARS CSV by name, case-insensitively. NHTSA's zips are
    inconsistent about casing across years -- 2022/2023 ship lowercase
    (accident.csv, person.csv, pbtype.csv) while 2019 and earlier ship
    mixed-case (accident.CSV, Person.CSV, PBType.CSV). macOS's default
    filesystem hides this, but the Linux CI runner is case-sensitive, so
    match on lowercased name to stay reproducible across both."""
    target = name.lower()
    for p in csv_dir.iterdir():
        if p.name.lower() == target:
            return p
    raise FileNotFoundError(f"{name} not found in {csv_dir}")


def _read(csv_dir: Path, name: str) -> list[dict]:
    with open(_find(csv_dir, name), encoding="latin-1") as fh:
        return list(csv.DictReader(fh))


def _valid_geo(lat: str, lon: str):
    if lat in LAT_BAD or lon in LON_BAD:
        return None
    try:
        la, lo = float(lat), float(lon)
    except ValueError:
        return None
    # Continental US-ish sanity bounds (incl. AK/HI/PR).
    if not (15 < la < 72) or not (-180 < lo < -64):
        return None
    return round(la, 4), round(lo, 4)


def transform(years: list[int]) -> dict:
    features = []
    # aggregates
    by_year = Counter()
    by_state = Counter()
    by_age_band = Counter()
    by_sex = Counter()
    by_lighting = Counter()
    by_hour = Counter()
    by_pbcat_group = Counter()
    minors = Counter()  # by year
    geo_known = Counter()
    geo_unknown = Counter()

    for year in years:
        csv_dir = fetch_year(year)
        acc = {a["ST_CASE"]: a for a in _read(csv_dir, "accident.csv")}
        # PBCAT keyed by case+veh+person
        pbtype = {}
        for r in _read(csv_dir, "pbtype.csv"):
            pbtype[(r["ST_CASE"], r["VEH_NO"], r["PER_NO"])] = r

        for p in _read(csv_dir, "person.csv"):
            if p["PER_TYP"] not in PEDALCYCLIST:
                continue
            a = acc.get(p["ST_CASE"], {})
            band = age_band(p.get("AGE"))
            sex = p.get("SEXNAME", "Unknown")
            light = a.get("LGT_CONDNAME", "Unknown")
            hour = p.get("HOUR") if "HOUR" in p else a.get("HOUR", "")
            pb = pbtype.get((p["ST_CASE"], p["VEH_NO"], p["PER_NO"]), {})
            crash_group = (pb.get("BIKECGPNAME") or "").strip()
            crash_type = (pb.get("BIKECTYPENAME") or "").strip()

            by_year[year] += 1
            by_state[a.get("STATENAME", "Unknown")] += 1
            by_age_band[band] += 1
            by_sex[sex] += 1
            by_lighting[light] += 1
            try:
                by_hour[int(a.get("HOUR", 99))] += 1
            except ValueError:
                by_hour[99] += 1
            if crash_group and crash_group.lower() != "not a cyclist":
                by_pbcat_group[crash_group] += 1
            if band in MINOR_BANDS:
                minors[year] += 1

            geo = _valid_geo(a.get("LATITUDE", ""), a.get("LONGITUD", ""))
            if geo is None:
                geo_unknown[year] += 1
                continue
            geo_known[year] += 1
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [geo[1], geo[0]]},
                "properties": {
                    "year": year,
                    "state": a.get("STATENAME", ""),
                    "city": clean_place(a.get("CITYNAME")),    # '' if not coded to a city
                    "county": clean_place(a.get("COUNTYNAME")),
                    "age_band": band,           # banded, never exact
                    "sex": sex,
                    "lighting": light,
                    "hour": a.get("HOURNAME", ""),
                    "month": a.get("MONTHNAME", ""),
                    "crash_group": crash_group,  # PBCAT (what the report coded)
                    "crash_type": crash_type,
                },
            })

    geojson = {
        "type": "FeatureCollection",
        "provenance": source_stamp(
            "NHTSA", "FARS (National)", years,
            "https://www.nhtsa.gov/research-data/fatality-analysis-reporting-system-fars",
            "Fatal motor-vehicle crashes on public roads ONLY. Single-bike falls "
            "are excluded. E-bikes are included with conventional bikes from 2022 "
            "but cannot be separated. ~1-2% of records have unknown location and "
            "are omitted from the map but kept in totals.",
        ),
        "features": features,
    }

    def top(counter, n=None):
        items = counter.most_common(n)
        return [{"label": str(k), "count": v} for k, v in items]

    summary = {
        "measure": MEASURE_COUNT,
        "measure_note": "These are COUNTS of fatalities, not rates. We have no "
                        "national ridership denominator, so do not read a high "
                        "count as a high per-rider risk.",
        "provenance": geojson["provenance"],
        "totals": {
            "fatalities": sum(by_year.values()),
            "by_year": {str(y): by_year[y] for y in sorted(by_year)},
            "minors_by_year": {str(y): minors[y] for y in sorted(minors)},
        },
        "by_state": top(by_state),
        "by_age_band": top(by_age_band),
        "by_sex": top(by_sex),
        "by_lighting": top(by_lighting),
        "by_pbcat_crash_group": top(by_pbcat_group),
        "by_hour": {str(h): by_hour[h] for h in sorted(by_hour)},
        "data_quality": {
            "geo_known": {str(y): geo_known[y] for y in sorted(geo_known)},
            "geo_unknown": {str(y): geo_unknown[y] for y in sorted(geo_unknown)},
            "helmet": "FARS does not reliably code helmet use for cyclists "
                      "(HELM_USE is a motor-vehicle-occupant field). Helmet "
                      "correlation should come from NEISS, not FARS.",
            "ebike_isolation": "Not possible in FARS. Counts are all pedalcyclists.",
        },
    }
    return {"geojson": geojson, "summary": summary}


if __name__ == "__main__":
    years = [int(y) for y in sys.argv[1:]] or [2019, 2020, 2021, 2022, 2023, 2024]
    OUT.mkdir(parents=True, exist_ok=True)
    result = transform(years)
    (OUT / "fars_points.geojson").write_text(json.dumps(result["geojson"]))
    (OUT / "fars_summary.json").write_text(json.dumps(result["summary"], indent=2))
    s = result["summary"]
    print(f"\nWrote {len(result['geojson']['features'])} mappable points")
    print(f"Total pedalcyclist fatalities {years}: {s['totals']['fatalities']}")
    print(f"By year: {s['totals']['by_year']}")
    print(f"Minors by year: {s['totals']['minors_by_year']}")
    print("Top PBCAT crash groups:")
    for row in s["by_pbcat_crash_group"][:5]:
        print(f"   {row['count']:4}  {row['label']}")
