"""Orchestrates the Risk & Prevention layer: state ranking, factor profile,
and cluster flagging, each paired with sourced prevention levers.

This is the project's core differentiator (per the Crash Atlas brief) --
none of the comparable public tools (PeopleForBikes' White Line, BikeMaps.org,
city Vision Zero dashboards) pair exposure-adjusted ranking, structured
PBCAT factor analysis, AND sourced prevention guidance in one place. All
three pieces here are interpretable (no opaque ML), every number carries
its sample size, and the honesty caveats from each component module are
preserved into the final artifact, not summarized away.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from risk.state_ranking import build_ranking  # noqa: E402
from risk.factor_profile import build_profile  # noqa: E402
from risk.factor_profile_crss import build_profile_crss  # noqa: E402
from risk.clusters import build_clusters  # noqa: E402
from risk.prevention_levers import lever_for, GENERAL_LIGHTING_LEVER  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "data"


def _attach_levers(profiles: list[dict]) -> None:
    for p in profiles:
        lever = lever_for(p["top_crash_type"])
        if lever:
            p["prevention_lever"] = lever
        elif "Dark" in p["lighting"]:
            p["prevention_lever"] = GENERAL_LIGHTING_LEVER


def build(years: list[int]) -> dict:
    ranking = build_ranking(years)
    profile = build_profile(years)
    profile_crss = build_profile_crss(years)
    clusters = build_clusters(years)

    _attach_levers(profile["profiles"])
    _attach_levers(profile_crss["profiles"])

    return {
        "years": years,
        "methodology_note": (
            "Interpretable components, no opaque machine learning: "
            "(1) state ranking adjusts FARS fatality counts by an ACS "
            "commute-cycling proxy -- a real but limited exposure "
            "denominator; (2) TWO factor profiles, kept separate on "
            "purpose -- fatal crashes (FARS, census, raw counts) and "
            "non-fatal crashes (CRSS, weighted probability-sample "
            "estimate) -- because mixing an unweighted census with a "
            "weighted sample into one number would misrepresent both; "
            "(3) cluster flags are raw fatality-count density, not an "
            "exposure-adjusted rate. Prevention levers are citations from "
            "FHWA/NACTO/NHTSA road-safety guidance tied to the matching "
            "PBCAT crash type, not claims our data proves the lever works."
        ),
        "state_ranking": ranking,
        "factor_profile": profile,
        "factor_profile_crss": profile_crss,
        "clusters": clusters,
    }


if __name__ == "__main__":
    years = [int(y) for y in sys.argv[1:]] or [2022, 2023]
    OUT.mkdir(parents=True, exist_ok=True)
    result = build(years)
    (OUT / "risk_summary.json").write_text(json.dumps(result, indent=2))
    print(f"States ranked: {len(result['state_ranking']['ranking'])}")
    print(f"Factor-profile combinations (fatal/FARS): {len(result['factor_profile']['profiles'])}")
    print(f"Factor-profile combinations (non-fatal/CRSS): {len(result['factor_profile_crss']['profiles'])}")
    print(f"Clusters flagged: {len(result['clusters']['clusters'])}")
    print(f"\nWrote {OUT / 'risk_summary.json'}")
