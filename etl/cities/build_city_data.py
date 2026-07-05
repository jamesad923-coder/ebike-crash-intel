"""Aggregate FARS pedalcyclist fatalities per (state, city) into a single
committed artifact (web/data/city_stats.json) that the static city-page
generator renders from.

Why aggregate from RAW FARS rather than the published geojson: the geojson
only contains mappable points (valid coordinates), but a city's honest
fatality COUNT must include records whose coordinates FARS withheld or
mis-coded. So totals here come from the full person/accident join; the
mappable subset is carried separately for the page map.

HONESTY LIMITS (repeated on every generated page):
  - Only ~67% of pedalcyclist fatality records are coded to a city at all;
    rural/unincorporated crashes usually aren't. City counts are therefore
    a FLOOR for "fatalities in and around this city", never a ceiling.
  - Counts, not rates -- no city-level ridership denominator exists.
  - FARS = fatal motor-vehicle crashes only; single-bike falls and
    non-fatal injuries are absent. E-bikes cannot be separated.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.schema import age_band, MINOR_BANDS, source_stamp  # noqa: E402
from fars.fetch_fars import fetch_year, DEFAULT_YEARS  # noqa: E402
from fars.transform_fars import (  # noqa: E402
    _read, _valid_geo, clean_place, PEDALCYCLIST,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "data"

# FARS codes the same place inconsistently across years; merge known aliases.
CITY_ALIASES = {
    ("New York", "New York"): "New York City",
}

# Cities included regardless of fatality count -- places where e-bike
# safety is an active council-level issue (the outreach beachhead). A page
# with a small count still matters there; the generator adds a prominent
# small-numbers caveat.
ALWAYS_INCLUDE = {
    # SoCal coastal cities with council-level e-bike debates
    ("Encinitas", "California"),
    ("Carlsbad", "California"),
    ("San Clemente", "California"),
    ("Newport Beach", "California"),
    ("Dana Point", "California"),
    ("Laguna Beach", "California"),
    # Jersey Shore towns with active teen e-bike ordinance debates --
    # also the home turf: Crash Atlas is built in Wall, NJ. Township
    # naming varies in FARS ("Brick" vs "Brick Township"), so both
    # variants are listed; absent ones (zero FARS records in the
    # window) simply don't materialize, which is itself the honest
    # story: the shore's e-bike crisis is injuries and near-misses,
    # which fatality data cannot see.
    ("Wall", "New Jersey"), ("Wall Township", "New Jersey"),
    ("Toms River", "New Jersey"), ("Toms River Township", "New Jersey"),
    ("Brick", "New Jersey"), ("Brick Township", "New Jersey"),
    ("Middletown", "New Jersey"), ("Middletown Township", "New Jersey"),
    ("Long Branch", "New Jersey"),
    ("Asbury Park", "New Jersey"),
    ("Manasquan", "New Jersey"),
    ("Belmar", "New Jersey"),
}

# Cities below this total are excluded from the artifact (too noisy to
# publish a page for), unless allowlisted above.
MIN_FATALITIES = 3

STATE_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME",
    "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "Puerto Rico": "PR", "Virgin Islands (U.S.)": "VI", "Virgin Islands": "VI",
}


def slugify(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-").replace("--", "-")


def build(years: list[int]) -> dict:
    per_city = defaultdict(lambda: {
        "total": 0, "minors": 0,
        "by_year": Counter(), "by_age_band": Counter(), "by_sex": Counter(),
        "by_lighting": Counter(), "by_crash_group": Counter(),
        "points": [],  # [lon, lat, year, is_minor] -- mappable subset only
    })
    total_records = 0
    city_coded = 0

    for year in years:
        csv_dir = fetch_year(year)
        acc = {a["ST_CASE"]: a for a in _read(csv_dir, "accident.csv")}
        pbtype = {}
        for r in _read(csv_dir, "pbtype.csv"):
            pbtype[(r["ST_CASE"], r["VEH_NO"], r["PER_NO"])] = r

        for p in _read(csv_dir, "person.csv"):
            if p["PER_TYP"] not in PEDALCYCLIST:
                continue
            total_records += 1
            a = acc.get(p["ST_CASE"], {})
            state = a.get("STATENAME", "")
            city = clean_place(a.get("CITYNAME"))
            if not city or not state:
                continue
            city = CITY_ALIASES.get((city, state), city)
            city_coded += 1

            band = age_band(p.get("AGE"))
            c = per_city[(city, state)]
            c["total"] += 1
            c["by_year"][year] += 1
            c["by_age_band"][band] += 1
            c["by_sex"][p.get("SEXNAME", "Unknown")] += 1
            c["by_lighting"][a.get("LGT_CONDNAME", "Unknown")] += 1
            pb = pbtype.get((p["ST_CASE"], p["VEH_NO"], p["PER_NO"]), {})
            grp = (pb.get("BIKECGPNAME") or "").strip()
            if grp and grp.lower() != "not a cyclist":
                c["by_crash_group"][grp] += 1
            if band in MINOR_BANDS:
                c["minors"] += 1

            geo = _valid_geo(a.get("LATITUDE", ""), a.get("LONGITUD", ""))
            if geo is not None:
                c["points"].append([geo[1], geo[0], year, int(band in MINOR_BANDS)])

    cities = []
    for (city, state), c in per_city.items():
        if c["total"] < MIN_FATALITIES and (city, state) not in ALWAYS_INCLUDE:
            continue
        abbr = STATE_ABBR.get(state, "")
        if not abbr:
            continue
        pts = c["points"]
        center = None
        if pts:
            center = [round(sum(p[0] for p in pts) / len(pts), 4),
                      round(sum(p[1] for p in pts) / len(pts), 4)]
        top = lambda cnt, n: [{"label": k, "count": v} for k, v in cnt.most_common(n)]
        cities.append({
            "city": city, "state": state, "state_abbr": abbr,
            "slug": f"{abbr.lower()}/{slugify(city)}",
            "total": c["total"], "minors": c["minors"],
            "by_year": {str(y): c["by_year"].get(y, 0) for y in years},
            "by_age_band": top(c["by_age_band"], None),
            "by_sex": top(c["by_sex"], None),
            "top_lighting": top(c["by_lighting"], 4),
            "top_crash_groups": top(c["by_crash_group"], 5),
            "n_mapped": len(pts),
            "center": center,
            "points": pts,
        })
    cities.sort(key=lambda r: (-r["total"], r["state"], r["city"]))

    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "years": years,
        "provenance": source_stamp(
            "NHTSA", "FARS (National)", years,
            "https://www.nhtsa.gov/research-data/fatality-analysis-reporting-system-fars",
            "Fatal motor-vehicle crashes on public roads only. Counts, not "
            "rates. E-bikes included with conventional bikes, not separable.",
        ),
        "coding_note": (
            f"Of {total_records} pedalcyclist fatality records {years[0]}-"
            f"{years[-1]}, {city_coded} ({city_coded / total_records * 100:.0f}%) "
            f"are coded to a specific city; rural and unincorporated-area "
            f"crashes usually are not. City totals are a floor, not a ceiling."
        ),
        "min_fatalities": MIN_FATALITIES,
        "cities": cities,
    }


if __name__ == "__main__":
    years = [int(y) for y in sys.argv[1:]] or DEFAULT_YEARS
    OUT.mkdir(parents=True, exist_ok=True)
    result = build(years)
    (OUT / "city_stats.json").write_text(json.dumps(result))
    print(f"Wrote {len(result['cities'])} cities to city_stats.json")
    print(result["coding_note"])
    for r in result["cities"][:10]:
        print(f"  {r['total']:4}  {r['city']}, {r['state_abbr']}  (mapped {r['n_mapped']})")
