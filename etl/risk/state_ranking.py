"""State-level relative risk ranking: FARS pedalcyclist fatalities adjusted
by the ACS bike-commute proxy (see etl/census/fetch_acs.py for why this
proxy, and its limits).

This produces a RATE (fatalities per bike-commuter), which is a genuinely
different, more honest number than a raw fatality count -- a state can rank
high on raw fatalities mostly because it's a big state with lots of riders,
and look completely different once adjusted. We show BOTH the raw count and
the adjusted rate side by side specifically so that contrast is visible,
not hidden behind a single ranked number.

REPEATED HONESTY CAVEAT (this is load-bearing, not boilerplate): the ACS
bike-commute share only captures commute trips. It misses recreational
riding, food/package delivery riding, and any trip by someone under working
age -- exactly the population most central to the e-bike injury story. A
state with low commute-cycling but heavy recreational/delivery e-bike use
would look artificially "low risk" here. We say this in the data AND the
UI must say it too, not just bury it in this file.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from census.fetch_acs import cached_bike_commute_by_state  # noqa: E402
from fars.transform_fars import transform as transform_fars  # noqa: E402


def build_ranking(years: list[int]) -> dict:
    fars = transform_fars(years)
    acs = cached_bike_commute_by_state()

    by_state = Counter()
    for f in fars["geojson"]["features"]:
        state = f["properties"].get("state")
        if state:
            by_state[state] += 1

    rows = []
    unmatched_states = []
    for state, fatalities in by_state.items():
        commute = acs.get(state)
        if not commute or commute["bike_commuters"] == 0:
            unmatched_states.append(state)
            continue
        # Fatalities per 10,000 bike commuters -- arbitrary scale chosen
        # purely so the numbers are readable (the raw per-commuter rate is
        # a tiny fraction); the scale factor changes nothing about ranking.
        rate = fatalities / commute["bike_commuters"] * 10_000
        rows.append({
            "state": state,
            "fatalities_raw_count": fatalities,
            "bike_commuters_acs_proxy": commute["bike_commuters"],
            "fatalities_per_10k_bike_commuters": round(rate, 2),
        })

    rows.sort(key=lambda r: -r["fatalities_per_10k_bike_commuters"])
    for i, r in enumerate(rows, 1):
        r["rate_rank"] = i
    by_raw_count = sorted(rows, key=lambda r: -r["fatalities_raw_count"])
    for i, r in enumerate(by_raw_count):
        next(x for x in rows if x["state"] == r["state"])["count_rank"] = i + 1

    return {
        "years": years,
        "measure_note": (
            "fatalities_per_10k_bike_commuters uses ACS commute-to-work "
            "cycling share as an exposure PROXY, not true ridership. It "
            "misses recreational, delivery, and minors' riding -- exactly "
            "the population central to e-bike injuries. Compare the rate "
            "rank against the raw count rank: a state can look very "
            "different on each. States with zero ACS bike-commuters "
            "couldn't be rate-adjusted and are listed separately, not "
            "silently dropped."
        ),
        "states_unrated_no_acs_data": unmatched_states,
        "ranking": rows,
    }


if __name__ == "__main__":
    years = [int(y) for y in sys.argv[1:]] or [2022, 2023]
    result = build_ranking(years)
    print(f"Ranked {len(result['ranking'])} states (rate-adjusted)")
    print(f"Unrated (no ACS bike-commute data): {result['states_unrated_no_acs_data']}")
    print("\nTop 10 by rate (fatalities per 10k bike commuters):")
    for r in result["ranking"][:10]:
        print(f"  rate_rank={r['rate_rank']:2}  count_rank={r['count_rank']:2}  "
              f"{r['state']:20} {r['fatalities_per_10k_bike_commuters']:.2f}  "
              f"(raw count: {r['fatalities_raw_count']})")
