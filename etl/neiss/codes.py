"""NEISS code lookups, transcribed from the official CPSC NEISS Coding Manual
(January 2019, https://www.cpsc.gov/s3fs-public/2019-NEISS-Coding-Manual.pdf)
and the CPSC Micromobility Products report (2017-2024) for product codes.

Every value here is sourced from those two CPSC documents -- nothing guessed.
"""
from __future__ import annotations

# Product codes relevant to bikes / e-bikes / scooters / hoverboards.
# CRITICAL HONESTY NOTE: e-bikes only got a dedicated code (5045) in 2024.
# Before that, e-bike injuries were folded into 5040 (all bicycles, powered
# or not) and only separable via CPSC's manual case-by-case investigation of
# ER narratives -- something this open pipeline cannot reproduce. So:
#   - 2024 data tagged 5045: directly, reliably "e-bike".
#   - any year tagged 5040 ("Bicycles"): e-bikes are IN there, unidentified.
PRODUCT_CODES = {
    "5040": "Bicycles (conventional + e-bikes prior to 2024, NOT separable)",
    "5045": "E-bikes (electric power-assisted pedal bicycles) -- 2024 onward only",
    "5046": "Bicycles, non-powered (introduced 2024, alongside 5045 split)",
    "5022": "Scooters, powered (e-scooters) -- 2020 onward",
    "5023": "Scooters, unpowered -- 2020 onward",
    "5024": "Scooters, unspecified powered/unpowered",
    "5025": "Self-balancing scooters / hoverboards",
    "5042": "Scooters/skateboards, powered (legacy code, used 2017-2019 only)",
}

# Codes that mean "this case cannot be confidently called an e-bike."
AMBIGUOUS_BIKE_CODE = "5040"
CONFIRMED_EBIKE_CODE = "5045"

DIAGNOSIS = {
    "41": "Ingested foreign object", "42": "Aspirated foreign object",
    "46": "Burn, electrical", "47": "Burn, not specified", "48": "Burn, scald",
    "49": "Burn, chemical", "50": "Amputation", "51": "Burn, thermal",
    "52": "Concussion", "53": "Contusion / abrasion", "54": "Crushing",
    "55": "Dislocation", "56": "Foreign body", "57": "Fracture",
    "58": "Hematoma", "59": "Laceration", "60": "Dental injury",
    "61": "Nerve damage", "62": "Internal organ injury", "63": "Puncture",
    "64": "Strain or sprain", "65": "Anoxia", "66": "Hemorrhage",
    "67": "Electric shock", "68": "Poisoning", "69": "Submersion / drowning",
    "71": "Other / not stated", "72": "Avulsion", "73": "Burn, radiation",
    "74": "Dermatitis / conjunctivitis",
}
# Diagnoses commonly read together as "head/brain injury" for the public
# dashboard's TBI-adjacent rollup. We show this grouping explicitly labeled
# as a rollup, never as a clinical TBI diagnosis (we don't have one).
HEAD_BRAIN_DIAGNOSES = {"52"}  # Concussion. Internal organ injury (62) is
# only head/brain-related when paired with Body_Part == Head (75); handled
# in transform, not here, since it depends on the body-part pairing.

BODY_PART = {
    "30": "Shoulder", "31": "Upper trunk", "32": "Elbow", "33": "Lower arm",
    "34": "Wrist", "35": "Knee", "36": "Lower leg", "37": "Ankle",
    "38": "Pubic region", "75": "Head", "76": "Face", "77": "Eyeball",
    "79": "Lower trunk", "80": "Upper arm", "81": "Upper leg", "82": "Hand",
    "83": "Foot", "84": "25-50% of body (burns)", "85": "All of body",
    "87": "Not recorded", "88": "Mouth", "89": "Neck", "92": "Finger",
    "93": "Toe", "94": "Ear", "0": "Internal",
}

DISPOSITION = {
    "1": "Treated and released", "2": "Transferred to another hospital",
    "4": "Treated and admitted (hospitalized)",
    "5": "Held for observation", "6": "Left without being seen",
    "8": "Fatality (incl. died in ED)", "9": "Not recorded",
}
FATAL_DISPOSITION = "8"
HOSPITALIZED_DISPOSITIONS = {"2", "4", "5"}

SEX = {"1": "Male", "2": "Female", "0": "Not recorded"}
