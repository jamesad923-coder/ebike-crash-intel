"""Fetch FARS National CSV archives from NHTSA's static file host.

FARS (Fatality Analysis Reporting System) is a census of fatal motor-vehicle
traffic crashes on public roads. It is already de-identified (no names/PII).

Key limitation we surface everywhere downstream:
  * FARS only includes crashes involving a motor vehicle on a public road, so
    single-bike falls (a huge share of e-bike injuries) are NOT here.
  * "Pedalcyclist" includes motorized bicycles (e-bikes) from 2022, but FARS
    does NOT separate e-bikes from conventional bikes. So this is
    "pedalcyclist & micromobility fatalities", with e-bikes included-not-isolated.

This host (static.nhtsa.gov) serves the zips directly with no bot-blocking,
so the whole fetch is reproducible from a script.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen, Request

RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "fars"
URL = "https://static.nhtsa.gov/nhtsa/downloads/FARS/{year}/National/FARS{year}NationalCSV.zip"


def fetch_year(year: int) -> Path:
    """Download + unzip one FARS year. Returns the extracted CSV directory."""
    RAW.mkdir(parents=True, exist_ok=True)
    zip_path = RAW / f"FARS{year}NationalCSV.zip"
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
    # NHTSA nests the CSVs one folder deep (e.g. FARS2023NationalCSV/).
    csv_dirs = [p for p in out_dir.iterdir() if p.is_dir()]
    csv_dir = csv_dirs[0] if csv_dirs else out_dir
    print(f"  FARS {year} ready: {csv_dir}")
    return csv_dir


if __name__ == "__main__":
    years = [int(y) for y in sys.argv[1:]] or [2022, 2023]
    for y in years:
        fetch_year(y)
