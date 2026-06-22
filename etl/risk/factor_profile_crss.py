"""CRSS-based contributing-factor profile: the non-fatal sibling of
factor_profile.py (which uses FARS, fatal crashes only).

Why a SEPARATE module rather than merging into one number: FARS is an
unweighted census (every row = one real fatal crash) while CRSS is a
weighted probability SAMPLE of non-fatal police-reported crashes (summing
WEIGHT gives a national estimate). Naively adding a FARS row-count to a
CRSS weighted-sum would mix two different kinds of number with different
meanings and silently mislead. We keep them as two clearly-labeled,
parallel views instead: "fatal crashes only (census)" and "all
police-reported crashes, fatal+non-fatal severities are NOT combined here
-- CRSS excludes fatal crashes by design, so this profile is non-fatal
crashes only (weighted national estimate)."
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crss.fetch_crss import fetch_year  # noqa: E402
from risk.factor_profile import hour_bucket  # noqa: E402

PEDALCYCLIST = {"6", "7"}


def _read(path: Path) -> list[dict]:
    with open(path, encoding="latin-1") as fh:
        return list(csv.DictReader(fh))


def build_profile_crss(years: list[int]) -> dict:
    combos = defaultdict(lambda: defaultdict(float))
    combo_totals = defaultdict(float)
    combo_raw_n = defaultdict(int)

    for year in years:
        csv_dir = fetch_year(year)
        acc = {a["CASENUM"]: a for a in _read(csv_dir / "accident.csv")}
        pbtype = {}
        for r in _read(csv_dir / "pbtype.csv"):
            pbtype[(r["CASENUM"], r["VEH_NO"], r["PER_NO"])] = r

        for p in _read(csv_dir / "person.csv"):
            if p["PER_TYP"] not in PEDALCYCLIST:
                continue
            a = acc.get(p["CASENUM"], {})
            pb = pbtype.get((p["CASENUM"], p["VEH_NO"], p["PER_NO"]), {})
            crash_group = (pb.get("BIKECGPNAME") or "").strip()
            if not crash_group or crash_group.lower() == "not a cyclist":
                continue

            weight = float(p.get("WEIGHT") or 0)
            lighting = a.get("LGT_CONDNAME", "Unknown").strip() or "Unknown"
            bucket = hour_bucket(a.get("HOUR", ""))
            key = (lighting, bucket)
            combos[key][crash_group] += weight
            combo_totals[key] += weight
            combo_raw_n[key] += 1

    profiles = []
    for (lighting, bucket), counter in combos.items():
        total = combo_totals[(lighting, bucket)]
        if total <= 0:
            continue
        top_type, top_weight = max(counter.items(), key=lambda kv: kv[1])
        profiles.append({
            "lighting": lighting,
            "time_of_day": bucket,
            "raw_sample_n": combo_raw_n[(lighting, bucket)],
            "estimated_crashes": round(total),
            "top_crash_type": top_type,
            "top_crash_type_share": round(top_weight / total, 3),
            "top_crash_type_estimate": round(top_weight),
        })
    profiles.sort(key=lambda r: -r["estimated_crashes"])
    return {
        "years": years,
        "measure_note": (
            "CRSS is a weighted probability sample of NON-FATAL "
            "police-reported crashes -- it excludes fatal crashes by "
            "design (those are FARS's domain, shown separately). Figures "
            "here are weighted NATIONAL ESTIMATES, not raw counts. Each "
            "combination also shows raw_sample_n -- the actual number of "
            "sampled cases behind the estimate -- since a small raw "
            "sample can still produce a large-looking weighted estimate."
        ),
        "profiles": profiles,
    }


if __name__ == "__main__":
    years = [int(y) for y in sys.argv[1:]] or [2022, 2023]
    result = build_profile_crss(years)
    print(f"Built {len(result['profiles'])} lighting x time-of-day combinations (CRSS, non-fatal)")
    for p in result["profiles"][:8]:
        print(f"  raw_n={p['raw_sample_n']:4} est={p['estimated_crashes']:6,}  "
              f"{p['lighting']:20} {p['time_of_day']:30} -> {p['top_crash_type']} "
              f"({p['top_crash_type_share']*100:.0f}%)")
