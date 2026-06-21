"""Contributing-factor risk profile: cross-tab PBCAT crash type x lighting
x time-of-day from FARS pedalcyclist fatalities already on disk.

This is deliberately NOT a machine-learning model. It's an interpretable
frequency table: "of N fatal crashes coded under these conditions, here is
the most common PBCAT crash type and its share." Simple, auditable, and
matches the brief's "start simple and interpretable before anything fancy."

Every cell carries its own sample size (N). A condition combination with
N=3 is shown with the same structure as one with N=200, but the dashboard
must show N prominently -- a 3-case pattern is an anecdote, not a finding,
and we will not let the UI imply otherwise.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fars.fetch_fars import fetch_year  # noqa: E402

PEDALCYCLIST = {"6", "7"}

# Collapse FARS's many specific hour values into broad, human-readable
# buckets -- "2am" granularity is noise for a pattern table like this.
def hour_bucket(hour_str: str) -> str:
    try:
        h = int(hour_str)
    except (ValueError, TypeError):
        return "Unknown"
    if h > 23:
        return "Unknown"
    if 5 <= h < 10:
        return "Morning (5-10am)"
    if 10 <= h < 15:
        return "Midday (10am-3pm)"
    if 15 <= h < 19:
        return "Afternoon/Evening rush (3-7pm)"
    if 19 <= h < 23:
        return "Night (7-11pm)"
    return "Late night/early morning (11pm-5am)"


def _read(path: Path) -> list[dict]:
    with open(path, encoding="latin-1") as fh:
        return list(csv.DictReader(fh))


def build_profile(years: list[int]) -> dict:
    # key: (lighting, hour_bucket) -> Counter of PBCAT crash group -> count
    combos = defaultdict(lambda: defaultdict(int))
    combo_totals = defaultdict(int)

    for year in years:
        csv_dir = fetch_year(year)
        acc = {a["ST_CASE"]: a for a in _read(csv_dir / "accident.csv")}
        pbtype = {}
        for r in _read(csv_dir / "pbtype.csv"):
            pbtype[(r["ST_CASE"], r["VEH_NO"], r["PER_NO"])] = r

        for p in _read(csv_dir / "person.csv"):
            if p["PER_TYP"] not in PEDALCYCLIST:
                continue
            a = acc.get(p["ST_CASE"], {})
            pb = pbtype.get((p["ST_CASE"], p["VEH_NO"], p["PER_NO"]), {})
            crash_group = (pb.get("BIKECGPNAME") or "").strip()
            if not crash_group or crash_group.lower() == "not a cyclist":
                continue

            lighting = a.get("LGT_CONDNAME", "Unknown").strip() or "Unknown"
            bucket = hour_bucket(a.get("HOUR", ""))
            key = (lighting, bucket)
            combos[key][crash_group] += 1
            combo_totals[key] += 1

    profiles = []
    for (lighting, bucket), counter in combos.items():
        total = combo_totals[(lighting, bucket)]
        top_type, top_count = max(counter.items(), key=lambda kv: kv[1])
        profiles.append({
            "lighting": lighting,
            "time_of_day": bucket,
            "sample_size": total,
            "top_crash_type": top_type,
            "top_crash_type_share": round(top_count / total, 3),
            "top_crash_type_count": top_count,
            "all_types": sorted(
                [{"label": k, "count": v} for k, v in counter.items()],
                key=lambda r: -r["count"],
            ),
        })
    # Largest, most statistically meaningful combinations first.
    profiles.sort(key=lambda r: -r["sample_size"])
    return {"years": years, "profiles": profiles}


if __name__ == "__main__":
    years = [int(y) for y in sys.argv[1:]] or [2022, 2023]
    result = build_profile(years)
    print(f"Built {len(result['profiles'])} lighting x time-of-day combinations")
    for p in result["profiles"][:8]:
        print(f"  n={p['sample_size']:3}  {p['lighting']:20} {p['time_of_day']:30} "
              f"-> {p['top_crash_type']} ({p['top_crash_type_share']*100:.0f}%)")
