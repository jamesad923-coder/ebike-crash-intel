"""Transform raw NEISS micromobility rows into honest, weighted national
estimate artifacts.

NEISS is a STATISTICAL SAMPLE of ~100 hospital EDs, not a census. Every case
carries a sample Weight; summing weights gives a national ESTIMATE with a
margin of error we are not attempting to compute here (NEISS publishes
estimate methodology separately). We therefore NEVER call these "counts" --
they are estimates, and every output says so.

NEISS has NO location field. It cannot go on a map. Do not be tempted to
join it to FARS by geography -- there is nothing to join on.

E-bike isolation honesty (see etl/neiss/codes.py for sourcing):
  * 2024+: product code 5045 is a clean, dedicated "e-bike" code.
  * pre-2024: e-bikes are inside 5040 (all bicycles) and CANNOT be isolated
    from a raw extract. We report 5040 honestly as "bicycles (e-bikes
    included, not separable)" for those years -- we do NOT estimate or
    guess an e-bike share.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.schema import age_band, MINOR_BANDS, source_stamp, MEASURE_ESTIMATE  # noqa: E402
from neiss.codes import (  # noqa: E402
    PRODUCT_CODES, DIAGNOSIS, BODY_PART, DISPOSITION, SEX,
    CONFIRMED_EBIKE_CODE, AMBIGUOUS_BIKE_CODE, FATAL_DISPOSITION,
    HOSPITALIZED_DISPOSITIONS,
)
from neiss.fetch_neiss import load_rows  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "data"


def device_label(p1: str, p2: str, p3: str) -> str | None:
    """Pick the single most specific device label for a case, or None if
    none of the three product slots are in our micromobility code set."""
    for code in (p1, p2, p3):
        if code == CONFIRMED_EBIKE_CODE:
            return "E-bike (confirmed, 2024+ only)"
    for code in (p1, p2, p3):
        if code == AMBIGUOUS_BIKE_CODE:
            return "Bicycle (e-bikes included, not separable)"
    for code in (p1, p2, p3):
        if code in PRODUCT_CODES:
            return PRODUCT_CODES[code]
    return None


def transform(year: int) -> dict:
    rows = load_rows(year)

    by_device = defaultdict(float)       # weighted national estimate
    by_device_raw = defaultdict(int)      # raw case count (sample size)
    by_age_band = defaultdict(float)
    by_sex = defaultdict(float)
    by_diagnosis = defaultdict(float)
    by_body_part = defaultdict(float)
    head_brain_estimate = 0.0
    fatalities_raw = 0
    fatalities_weighted = 0.0
    hospitalized_weighted = 0.0
    minors_weighted = 0.0
    total_weighted = 0.0
    total_raw = 0

    # Device-specific slices, keyed by device label, for cross-tabs.
    device_age = defaultdict(lambda: defaultdict(float))
    device_diag = defaultdict(lambda: defaultdict(float))

    for r in rows:
        w = float(r["Weight"])
        dev = device_label(r["Product_1"], r["Product_2"], r["Product_3"])
        if dev is None:
            continue  # not one of our target product codes

        total_weighted += w
        total_raw += 1
        by_device[dev] += w
        by_device_raw[dev] += 1

        band = age_band(r["Age"])
        by_age_band[band] += w
        device_age[dev][band] += w
        if band in MINOR_BANDS:
            minors_weighted += w

        sex = SEX.get(r["Sex"], "Unknown")
        by_sex[sex] += w

        diag1 = DIAGNOSIS.get(r["Diagnosis"], "Unknown")
        by_diagnosis[diag1] += w
        device_diag[dev][diag1] += w
        bp1 = BODY_PART.get(r["Body_Part"], "Unknown")
        by_body_part[bp1] += w

        if r["Diagnosis"] == "52" or (r["Diagnosis"] == "62" and r["Body_Part"] == "75"):
            head_brain_estimate += w  # concussion, or internal injury to the head

        disp = r["Disposition"]
        if disp == FATAL_DISPOSITION:
            fatalities_raw += 1
            fatalities_weighted += w
        if disp in HOSPITALIZED_DISPOSITIONS:
            hospitalized_weighted += w

    def top(d: dict, n=None):
        items = sorted(d.items(), key=lambda kv: -kv[1])[:n]
        return [{"label": k, "estimate": round(v)} for k, v in items]

    provenance = source_stamp(
        "CPSC", "NEISS (National Electronic Injury Surveillance System)", [year],
        "https://www.cpsc.gov/Research--Statistics/NEISS-Injury-Data",
        "NEISS samples ~100 hospital EDs nationally; figures here are WEIGHTED "
        "NATIONAL ESTIMATES, not raw counts, and carry sampling uncertainty "
        "not shown in this v1. NEISS has NO location field -- these numbers "
        "cannot be mapped or compared city-to-city. E-bikes only have a "
        "dedicated product code (5045) from 2024 onward; in earlier years "
        "e-bikes are mixed into the general 'Bicycles' code (5040) and "
        "cannot be isolated from this data. NEISS undercounts single-bike "
        "falls relative to ED visits because it only captures cases that "
        "presented to a sampled ED.",
    )

    return {
        "year": year,
        "measure": MEASURE_ESTIMATE,
        "provenance": provenance,
        "sample_size_raw_cases": total_raw,
        "totals": {
            "estimated_ed_visits": round(total_weighted),
            "estimated_minors": round(minors_weighted),
            "estimated_fatalities": round(fatalities_weighted),
            "estimated_hospitalized": round(hospitalized_weighted),
            "estimated_head_or_brain_related": round(head_brain_estimate),
        },
        "data_quality": {
            "fatalities_raw_sample_n": fatalities_raw,
            "fatality_estimate_caveat": (
                "Fatality estimates from a sample this size carry very wide "
                "uncertainty. FARS, a census, is the better source for fatal "
                "pedalcyclist counts -- see fars_summary.json."
                if fatalities_raw < 30 else None
            ),
            "ebike_isolation": (
                "Confirmed e-bike code (5045) used: counts are reliable."
                if year >= 2024 else
                "Pre-2024: e-bikes are inside the 'Bicycles' (5040) total "
                "and not separable. Do not read 'Bicycles' as a bicycle-only figure."
            ),
        },
        "by_device": top(by_device),
        "by_device_raw_n": dict(by_device_raw),
        "by_age_band": top(by_age_band),
        "by_sex": top(by_sex),
        "by_diagnosis": top(by_diagnosis, 10),
        "by_body_part": top(by_body_part, 10),
        "by_device_age_band": {
            dev: top(bands) for dev, bands in device_age.items()
        },
        "by_device_diagnosis": {
            dev: top(diags, 6) for dev, diags in device_diag.items()
        },
    }


if __name__ == "__main__":
    years = [int(y) for y in sys.argv[1:]] or [2024]
    OUT.mkdir(parents=True, exist_ok=True)
    all_years = {}
    for year in years:
        result = transform(year)
        all_years[str(year)] = result
        print(f"\n=== NEISS {year} ===")
        print(f"Raw sample cases matched: {result['sample_size_raw_cases']}")
        print(f"Estimated ED visits (all tracked devices): {result['totals']['estimated_ed_visits']:,}")
        print(f"Estimated minors: {result['totals']['estimated_minors']:,}")
        print("By device (estimate):")
        for row in result["by_device"]:
            print(f"   {row['estimate']:>8,}  {row['label']}")
    (OUT / "neiss_summary.json").write_text(json.dumps(all_years, indent=2))
    print(f"\nWrote {OUT / 'neiss_summary.json'}")
