"""DC pilot: ward-level bicycle crash summary + Capital Bikeshare e-bike
trip context, kept deliberately separate (see fetch_capital_bikeshare.py
for why we don't compute a per-ward rate from this).

This is the project's first CITY-LEVEL crash source -- finer geography
than FARS/CRSS/ACS allow, and the proof-of-concept for whether a city
pilot is worth expanding to others.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dc.fetch_dc_crashes import cached_bicycle_crashes  # noqa: E402
from dc.fetch_capital_bikeshare import cached_recent_months  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "data"

RECENT_MONTHS = ["202601", "202602", "202603", "202604", "202605"]

# The raw dataset spans 1996-2026, very unevenly (1 record in 1996, a gap
# to 2011, then ramping up -- 2016 onward is when DC's reporting clearly
# became consistent). Mixing 30 years of uneven reporting into one "total
# crashes by ward" number would make a ward look worse partly because it's
# been recorded for longer, not because it's more dangerous NOW. We filter
# the ward comparison to a fixed, recent, consistent window instead, and
# report the exact window used so nothing is silently decided for the reader.
RECENT_WINDOW_YEARS = 5


def _parse_crash_date(epoch_ms) -> datetime | None:
    if not epoch_ms:
        return None
    try:
        return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def build_ward_summary() -> dict:
    records = cached_bicycle_crashes()
    dated = [(r, _parse_crash_date(r.get("FROMDATE"))) for r in records]
    all_dates = [d for _, d in dated if d is not None]
    full_range = (min(all_dates), max(all_dates)) if all_dates else (None, None)

    cutoff_year = full_range[1].year - RECENT_WINDOW_YEARS + 1 if full_range[1] else None
    cutoff = datetime(cutoff_year, 1, 1, tzinfo=timezone.utc) if cutoff_year else None
    recent = [(r, d) for r, d in dated if d and cutoff and d >= cutoff]

    by_ward = defaultdict(lambda: {
        "crashes": 0, "fatal": 0, "major_injury": 0, "minor_injury": 0,
        "speeding_involved": 0,
    })
    no_ward = 0
    features = []

    for r, d in recent:
        ward = r.get("WARD")
        if not ward or ward == "Null":
            no_ward += 1
            continue
        w = by_ward[ward]
        w["crashes"] += 1
        w["fatal"] += int(r.get("FATAL_BICYCLIST") or 0)
        w["major_injury"] += int(r.get("MAJORINJURIES_BICYCLIST") or 0)
        w["minor_injury"] += int(r.get("MINORINJURIES_BICYCLIST") or 0)
        w["speeding_involved"] += 1 if r.get("SPEEDING_INVOLVED") else 0

        lat, lon = r.get("LATITUDE"), r.get("LONGITUDE")
        if lat and lon:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "ward": ward,
                    "fatal": bool(r.get("FATAL_BICYCLIST")),
                    "major_injury": bool(r.get("MAJORINJURIES_BICYCLIST")),
                    "minor_injury": bool(r.get("MINORINJURIES_BICYCLIST")),
                    "speeding_involved": bool(r.get("SPEEDING_INVOLVED")),
                    "date": d.strftime("%Y-%m-%d"),
                },
            })

    ward_rows = [{"ward": w, **stats} for w, stats in by_ward.items()]
    ward_rows.sort(key=lambda r: -r["crashes"])

    return {
        "date_window": {
            "start": cutoff.strftime("%Y-%m-%d") if cutoff else None,
            "end": full_range[1].strftime("%Y-%m-%d") if full_range[1] else None,
            "years": RECENT_WINDOW_YEARS,
            "full_dataset_start": full_range[0].strftime("%Y-%m-%d") if full_range[0] else None,
            "full_dataset_end": full_range[1].strftime("%Y-%m-%d") if full_range[1] else None,
        },
        "measure_note": (
            f"Bicycle-involved crash COUNTS by DC ward, filtered to the "
            f"most recent {RECENT_WINDOW_YEARS} years of data "
            f"({cutoff.strftime('%B %Y') if cutoff else '?'} through "
            f"{full_range[1].strftime('%B %Y') if full_range[1] else '?'}). "
            f"The full source dataset actually goes back to "
            f"{full_range[0].strftime('%Y') if full_range[0] else '?'}, but "
            f"reporting was sparse and inconsistent before 2016 -- mixing "
            f"30 years of uneven reporting into one ward total would make "
            f"a ward look worse partly because it's been recorded longer, "
            f"not because it's more dangerous now. NOT exposure-adjusted "
            f"-- no per-ward ridership data is wired in; see the separate "
            f"Capital Bikeshare e-bike trip context below, which is "
            f"citywide context only, not used to compute a per-ward rate. "
            f"Same federal-data-style gap applies here too: this is all "
            f"bicyclist crashes, e-bikes included but not isolated -- DC's "
            f"crash data has no e-bike-specific flag either."
        ),
        "records_with_no_ward_or_date": no_ward,
        "total_records_in_window": len(recent),
        "total_records_all_time": len(records),
        "by_ward": ward_rows,
        "geojson": {"type": "FeatureCollection", "features": features},
    }


def build_bikeshare_context() -> dict:
    monthly = cached_recent_months(RECENT_MONTHS)
    rows = []
    for m, counts in monthly.items():
        total = sum(counts.values())
        ebike = counts.get("electric_bike", 0)
        rows.append({
            "month": m,
            "total_trips": total,
            "electric_bike_trips": ebike,
            "classic_bike_trips": counts.get("classic_bike", 0),
            "electric_bike_share": round(ebike / total, 3) if total else 0,
        })
    rows.sort(key=lambda r: r["month"])
    return {
        "measure_note": (
            "Capital Bikeshare's own trip-history data, which uniquely "
            "DOES distinguish e-bike trips (rideable_type field) from "
            "classic bike trips -- a genuinely e-bike-specific signal, "
            "rare in this project's sources. But it covers ONLY Capital "
            "Bikeshare's fleet, not personally-owned e-bikes (most of "
            "what the news-sourced fatality reports involve), and is "
            "citywide, not ward-level -- shown as context, not blended "
            "into the ward crash counts above."
        ),
        "monthly": rows,
    }


def build(years: list[int] | None = None) -> dict:
    return {
        "ward_summary": build_ward_summary(),
        "bikeshare_context": build_bikeshare_context(),
    }


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    result = build()
    (OUT / "dc_pilot.json").write_text(json.dumps(result, indent=2))
    ws = result["ward_summary"]
    dw = ws["date_window"]
    print(f"Date window used: {dw['start']} to {dw['end']} ({dw['years']} years)")
    print(f"Full dataset actually spans: {dw['full_dataset_start']} to {dw['full_dataset_end']}")
    print(f"Records in window: {ws['total_records_in_window']} of {ws['total_records_all_time']} all-time "
          f"({ws['records_with_no_ward_or_date']} excluded: no ward/date)")
    print("By ward (in-window):")
    for r in ws["by_ward"]:
        print(f"  {r['ward']:10} crashes={r['crashes']:5}  fatal={r['fatal']:2}  "
              f"major={r['major_injury']:3}  minor={r['minor_injury']:4}")
    print(f"\nMapped points: {len(ws['geojson']['features'])}")
    print("\nCapital Bikeshare e-bike share by month:")
    for r in result["bikeshare_context"]["monthly"]:
        print(f"  {r['month']}: {r['electric_bike_share']*100:.0f}% e-bike "
              f"({r['electric_bike_trips']:,} of {r['total_trips']:,})")
    print(f"\nWrote {OUT / 'dc_pilot.json'}")
