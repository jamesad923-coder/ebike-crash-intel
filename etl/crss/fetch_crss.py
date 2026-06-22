"""Fetch CRSS (Crash Report Sampling System) National CSV archives from
NHTSA's static file host -- the non-fatal sibling of FARS.

CRSS is a nationally representative PROBABILITY SAMPLE of police-reported
crashes (it does NOT include fatal crashes -- those are FARS's domain).
Like NEISS, every CRSS row carries a sample WEIGHT; summing weights gives a
national estimate, not a raw count. Unlike FARS, CRSS has NO latitude/
longitude -- it cannot be mapped, only used for national-level statistics.

Same hosting pattern as FARS (no bot-blocking, fully scriptable), but a
slightly different URL shape -- verified directly rather than assumed:
  https://static.nhtsa.gov/nhtsa/downloads/CRSS/{year}/CRSS{year}CSV.zip
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen, Request

RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "crss"
URL = "https://static.nhtsa.gov/nhtsa/downloads/CRSS/{year}/CRSS{year}CSV.zip"


def fetch_year(year: int) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    zip_path = RAW / f"CRSS{year}CSV.zip"
    if not zip_path.exists():
        url = URL.format(year=year)
        print(f"  downloading {url}")
        req = Request(url, headers={"User-Agent": "ebike-crash-intel/0.1 (public-good research)"})
        with urlopen(req, timeout=300) as r, open(zip_path, "wb") as f:
            f.write(r.read())
    out_dir = RAW / str(year)
    out_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out_dir)
    csv_dirs = [p for p in out_dir.iterdir() if p.is_dir()]
    csv_dir = csv_dirs[0] if csv_dirs else out_dir
    print(f"  CRSS {year} ready: {csv_dir}")
    return csv_dir


if __name__ == "__main__":
    years = [int(y) for y in sys.argv[1:]] or [2022, 2023]
    for y in years:
        fetch_year(y)
