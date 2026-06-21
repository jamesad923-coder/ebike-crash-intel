"""Shared schema, constants, and small helpers for all ETL connectors.

Design principle for this whole project: make data gaps *visible*, never hidden.
Every artifact we emit carries explicit provenance (which source, which year) and
honest limitations. We never invent precision the source can't support.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Age banding. We display BANDS, never an exact age, in any public artifact.
# This matters most for minors (brief: never re-identify an injured child).
# ---------------------------------------------------------------------------
AGE_BANDS = [
    (0, 12, "0-12 (child)"),
    (13, 17, "13-17 (teen)"),
    (18, 24, "18-24"),
    (25, 44, "25-44"),
    (45, 64, "45-64"),
    (65, 199, "65+"),
]
AGE_UNKNOWN = "Unknown"
MINOR_BANDS = {"0-12 (child)", "13-17 (teen)"}


def age_band(age) -> str:
    """Map a raw age to a display band. Unknown/sentinel ages -> 'Unknown'.

    FARS uses 998/999 for unknown; NEISS uses 2 for '<2' and may be blank.
    """
    try:
        a = int(age)
    except (TypeError, ValueError):
        return AGE_UNKNOWN
    if a >= 998 or a < 0:
        return AGE_UNKNOWN
    for lo, hi, label in AGE_BANDS:
        if lo <= a <= hi:
            return label
    return AGE_UNKNOWN


# ---------------------------------------------------------------------------
# Provenance / data-quality vocabulary used across artifacts.
# ---------------------------------------------------------------------------
# What kind of number is this? Counts and rates must never be confused.
MEASURE_COUNT = "count"            # a literal count of records
MEASURE_ESTIMATE = "national_estimate"  # weighted sample estimate (NEISS)
MEASURE_RATE = "rate"              # per-exposure rate (needs a denominator)

# Confidence in a single record's e-bike classification, etc.
CONFIDENCE = ("high", "medium", "low")


def source_stamp(source: str, dataset: str, years, url: str, limits: str) -> dict:
    """A provenance block we attach to every emitted artifact."""
    return {
        "source": source,
        "dataset": dataset,
        "years": list(years),
        "url": url,
        "limitations": limits,
    }
