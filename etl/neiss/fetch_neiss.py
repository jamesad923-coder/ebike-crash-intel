"""Fetch NEISS micromobility-related case rows for a given year.

IMPORTANT CONSTRAINT (read before "fixing" this with more retries):
CPSC's file server (www.cpsc.gov) sits behind Akamai bot-protection that
rejects plain scripted requests (curl, requests, urllib all get HTTP 403),
even with a normal browser User-Agent header. A real browser session passes.
This is unlike FARS, which is served from a plain static host with no
blocking.

Practical effect: NEISS ingestion for this project is a yearly, semi-manual
step, not a fully unattended cron job like FARS. Given NEISS only publishes
one file per calendar year, this is an acceptable trade-off, not a deal
breaker -- but it MUST be documented, not silently hidden.

How to refresh NEISS data (do this once a year, after CPSC posts the file):
  1. Open https://www.cpsc.gov/Research--Statistics/NEISS-Injury-Data in an
     actual browser.
  2. Open browser devtools console on that page and run a same-origin fetch
     against the year's TSV, e.g.:
       /cgibin/NEISSQuery/Data/Archived%20Data/{year}/neiss{year}.tsv
     filtering rows to the product codes in etl/neiss/codes.py
     (PRODUCT_CODES) and dropping Narrative_1/CPSC_Case_Number for privacy,
     then save the result as
       data/raw/neiss/neiss{year}_micromobility.tsv
  3. Run `python3 etl/neiss/transform_neiss.py {year}`.

This module just defines that expected raw-file path and a normal helper
to load it -- it deliberately does NOT attempt to scrape cpsc.gov itself.
"""
from __future__ import annotations

from pathlib import Path

RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "neiss"


def raw_path(year: int) -> Path:
    return RAW / f"neiss{year}_micromobility.tsv"


def load_rows(year: int) -> list[dict]:
    import csv

    path = raw_path(year)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. NEISS requires a one-time browser-assisted "
            "fetch each year -- see the module docstring in fetch_neiss.py "
            "for the exact steps."
        )
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))
