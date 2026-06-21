"""Evidence-based prevention levers, mapped to PBCAT crash types.

These are NOT model outputs -- they are citations from established road-
safety literature/guidance, paired with the PBCAT crash type they're most
relevant to. The model identifies WHICH pattern is common in the data; this
file says what the broader literature recommends for that pattern. We do
not claim our data proves the lever works -- we cite where that evidence
already lives (FHWA, NACTO, NHTSA countermeasure guidance).

Keep this list small and well-sourced rather than exhaustive and vague.
"""
from __future__ import annotations

LEVERS = {
    "Motorist Overtaking Bicyclist": {
        "levers": ["Protected/separated bike lanes", "Lower posted speed limits",
                   "Safe passing distance laws"],
        "why": "Removes the need for a motorist to judge passing distance "
               "at all, or reduces the speed differential and stopping "
               "distance if a misjudgment happens.",
        "source": "FHWA Bikeway Selection Guide; NACTO Urban Bikeway Design Guide",
    },
    "Bicyclist Failed to Yield - Midblock": {
        "levers": ["Midblock crossing islands/refuges", "Improved street lighting",
                   "Rider education on midblock crossing risk"],
        "why": "Midblock crossings lack the visual cues and right-of-way "
               "clarity of a signalized intersection.",
        "source": "FHWA PBCAT crash-type countermeasure tables",
    },
    "Bicyclist Failed to Yield - Sign-Controlled Intersection": {
        "levers": ["All-way stop conversion where warranted", "Sightline clearance at stop signs",
                   "Intersection daylighting (removing parking near corners)"],
        "why": "Sign-controlled intersections rely entirely on driver/rider "
               "judgment; clearing sightlines and adding daylighting reduces "
               "the chance of a missed yield.",
        "source": "NACTO Don't Give Up at the Intersection",
    },
    "Bicyclist Failed to Yield - Signalized Intersection": {
        "levers": ["Bicycle-specific signal phases", "Protected intersection design",
                   "Leading bicycle intervals"],
        "why": "Separates bicycle and turning-vehicle movements in time, "
               "removing the conflict rather than relying on yielding.",
        "source": "NACTO Urban Bikeway Design Guide -- Bicycle Signals",
    },
    "Wrong-Way / Wrong-Side": {
        "levers": ["Contraflow bike lanes where wrong-way riding is common",
                   "Rider education on direction-of-travel laws"],
        "why": "Wrong-way riding puts the cyclist outside a driver's normal "
               "scanning pattern at intersections and driveways.",
        "source": "FHWA PBCAT crash-type countermeasure tables",
    },
    "Bicyclist Left Turn / Merge": {
        "levers": ["Two-stage turn boxes", "Protected intersection design"],
        "why": "Lets a cyclist complete a left turn in two signal phases "
               "without merging across traffic.",
        "source": "NACTO Urban Bikeway Design Guide",
    },
    "Crossing Paths - Other Circumstances": {
        "levers": ["Improved lighting at conflict points", "Sightline clearance",
                   "Speed reduction near crossings"],
        "why": "A catch-all for path-crossing conflicts not otherwise typed; "
               "general visibility and speed countermeasures apply broadly.",
        "source": "FHWA PBCAT v3 User Guide",
    },
    "Parallel Paths - Other Circumstances": {
        "levers": ["Separated/protected bike lanes", "Buffer width increases"],
        "why": "Reduces the chance of a parallel-path conflict escalating "
               "to contact in the first place.",
        "source": "FHWA Bikeway Selection Guide",
    },
}

GENERAL_LIGHTING_LEVER = {
    "levers": ["Street lighting improvements", "Bicycle-mounted lighting/reflective gear requirements or education"],
    "why": "Dark-unlit conditions show a substantially higher concentration "
           "of fatal motorist-overtaking crashes than daylight in our own "
           "factor profile -- lighting is one of the few levers a city can "
           "act on directly and quickly.",
    "source": "NHTSA Countermeasures That Work (Pedestrian/Bicyclist Safety chapter)",
}


def lever_for(crash_type: str) -> dict | None:
    return LEVERS.get(crash_type)
