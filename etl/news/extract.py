"""Extract structured, privacy-safe signals from a news article.

PRIVACY RULE (do not weaken this): we extract and keep ONLY --
  - a city/state location (from an AP-style dateline, e.g. "HOBOKEN, N.J. --")
  - an age BAND (never an exact age, never a name)
  - a device keyword (e-bike / e-scooter / hoverboard / etc.)
  - an outcome tier (fatality / severe injury / injury / hospitalized)
  - the source URL + domain + publish date, so a reader can verify themselves
We do NOT store the article body, and we do NOT extract or store names. The
dateline regex and age-phrase regex are run against the fetched text and then
the text itself is discarded -- only the matched structured fields survive
into the output. If no dateline/device/outcome can be confidently matched,
the article is dropped, not guessed at.
"""
from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.schema import age_band  # noqa: E402

# US state abbreviations + a few common full names, for dateline matching.
STATE_ABBR = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
}

# AP-style dateline: "CITY, ST --" near the start of the article, e.g.
# "HOBOKEN, N.J. -- A 15-year-old ..." Most precise signal when present, but
# most local news (as opposed to wire-service copy) doesn't use one.
#
# Two-letter STATE GROUP allows an optional period after each letter
# ("NJ" or "N.J.") because AP style periods two-word state abbreviations
# in datelines -- "SOUTHAMPTON TWP., N.J. (WPVI) --" is a real example
# that the un-dotted-only pattern completely missed in testing. Matched as
# two separate single-letter groups and concatenated by the caller.
DATELINE_RE = re.compile(
    r"\b([A-Z][A-Za-z. ]{2,30}),\s*([A-Z])\.?([A-Z])\.?\b\s*[-–—]"
)

# Looser fallback: "City, ST" or "City, State" mentioned anywhere in the
# body, no dash required (e.g. "...crash in Hoboken, NJ on Tuesday").
# Capped at 1 extra word (not 2): wider caps invite picking up junk tokens
# like section labels ("LIVE", "SE") that precede the real place name.
CITY_STATE_RE = re.compile(
    r"\b([A-Z][a-zA-Z.]+(?: [A-Z][a-zA-Z.]+){0,1}),\s*([A-Z])\.?([A-Z])\.?\b"
)

# County mentions are common in local TV/newspaper copy even without a city
# name ("...crash in Clay County..."). Lower precision (county, not city)
# but still far better than nothing, and arguably MORE privacy-appropriate
# (coarser granularity) than a precise address would be.
COUNTY_RE = re.compile(r"\b([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+){0,1}) County\b")

# Junk tokens that can precede a real place name and get swept into the
# match: section labels, directionals, bylines. Stripped from the front.
JUNK_PREFIXES = {"live", "ne", "nw", "se", "sw", "n", "s", "e", "w", "breaking",
                  "update", "news", "local", "watch", "video", "photos"}

# A leading "X. Surname" (single initial + period) is almost always a
# person's name in news copy ("Dr. R. Waterman, MD"), not a place -- and
# critically, several state abbreviations double as titles/words (MD =
# Maryland AND "Doctor of Medicine"; OR = Oregon AND "or"; IN = Indiana AND
# "in"). We can't disambiguate those reliably, so we reject the personal-name
# shape outright rather than risk misattributing a crash to an uninvolved
# named person.
PERSON_NAME_RE = re.compile(r"^[A-Z]\.\s")

# Manually curated, intentionally small and incomplete: maps local U.S.
# news/TV-station domains to their home state. This is an approximation --
# the OUTLET's home market, not necessarily the exact crash location -- and
# is flagged as such (location_precision: "outlet_market") wherever used.
# Extend this table over time as more domains show up in real GDELT results.
DOMAIN_STATE = {
    "news4jax.com": "FL", "abc30.com": "CA", "wjla.com": "DC",
    "wmur.com": "NH", "mcall.com": "PA", "thetimes-tribune.com": "PA",
    "theoaklandpress.com": "MI", "dailybulletin.com": "CA",
    "10news.com": "CA",
}

DEVICE_PATTERNS = [
    (re.compile(r"e-?bike|electric bike|sur-?ron", re.I), "E-bike"),
    (re.compile(r"e-?scooter|electric scooter", re.I), "E-scooter"),
    (re.compile(r"hoverboard|self-balancing scooter", re.I), "Hoverboard"),
]

FATAL_RE = re.compile(r"\bkilled\b|\bdied\b|\bdead\b|\bfatal(ity|ly)?\b|\bdoa\b", re.I)
SEVERE_RE = re.compile(r"critical(ly)? (injured|condition)|life-threatening", re.I)
INJURY_RE = re.compile(r"\binjured\b|\bhurt\b|\bhospitalized\b", re.I)

# Deliberately NOT "hit by" or bare "struck" -- both are dangerously generic
# in English ("hit by a BB gun pellet", "struck a deal", "struck out") and
# caused a real false positive in testing: an article about teens on e-bikes
# shooting pedestrians with BB guns matched as an e-bike CRASH because the
# article said people were "hit by the projectiles." Requiring an article +
# noun after "struck/hit by" anchors these to an actual collision.
CRASH_RE = re.compile(
    r"\bcrash(ed|es|ing)?\b|\bcollision\b|\baccident\b|"
    r"\b(struck|hit) by (a|an|the) (car|truck|vehicle|driver|suv|van|bus|motorist)\b|"
    r"\bran into\b|\bplowed into\b|\bstruck (a|an|the) (pedestrian|cyclist|rider)\b",
    re.I,
)

# Negation cues checked in a window around a candidate crash/outcome match.
# Plain keyword matching has no idea "no one was hurt" negates "hurt" --
# this is exactly what let the BB-gun article through ("no one reported any
# serious injury" was treated the same as a real injury report).
NEGATION_RE = re.compile(
    r"\bno\b|\bnobody\b|\bno one\b|\bnone\b|\bwithout\b|\bnot\b|n't\b|\bzero\b",
    re.I,
)

# Device, crash, and outcome mentions must occur within this many characters
# of each other to count as describing the same event -- otherwise a long
# article that happens to mention an e-bike in one paragraph and an unrelated
# "crash" in another could be wrongly stitched together.
PROXIMITY_WINDOW = 500


def _negated_nearby(text: str, start: int, end: int, window: int = 50) -> bool:
    """True if a negation cue appears in the ~window chars immediately
    before the match (where "no", "nobody", "without" etc. typically sit
    relative to the thing they're negating)."""
    return bool(NEGATION_RE.search(text[max(0, start - window):end]))

AGE_NUM_RE = re.compile(r"\b(\d{1,2})[\s-]year[\s-]old\b", re.I)
TEEN_RE = re.compile(r"\bteen(ager)?\b", re.I)
CHILD_RE = re.compile(r"\bchild\b|\bkid\b", re.I)


def fetch_text(url: str, timeout=15) -> str:
    """Best-effort fetch of the article body, stripped of tags. Returns ""
    on any failure (paywall, block, timeout) -- the caller falls back to
    title-only extraction, which is strictly weaker but still safe.

    Modern news sites often SSR-inject large inline <style> blocks (e.g.
    styled-components dumps tens of KB of CSS into <head>). A small read
    budget can land mid-block with no closing tag in view, so the strip
    regex finds nothing to remove and the "stripped" text is mostly CSS
    noise with the real article text never reached. We read a much larger
    window and drop <head> wholesale to avoid this.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ebike-crash-intel/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(300000).decode("utf-8", errors="ignore")
        text = re.sub(r"<head.*?</head>", " ", raw, flags=re.S | re.I)
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&amp;|&nbsp;|&#\d+;", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text[:8000]
    except Exception:
        return ""


def extract_device(text: str) -> tuple[str, int] | None:
    """Returns (label, match_start) for the first device mention, or None."""
    for pattern, label in DEVICE_PATTERNS:
        m = pattern.search(text)
        if m:
            return label, m.start()
    return None


def extract_outcome(text: str) -> tuple[str, int] | None:
    """Returns (tier, match_start) for the most severe NON-NEGATED outcome
    mention, or None. Each candidate match is checked for a negation cue
    immediately before it ("no one was hurt" must not count as "hurt")."""
    for pattern, tier in [(FATAL_RE, "Fatality"), (SEVERE_RE, "Severe injury"), (INJURY_RE, "Injury")]:
        for m in pattern.finditer(text):
            if not _negated_nearby(text, m.start(), m.end()):
                return tier, m.start()
    return None


def extract_crash_position(text: str) -> int | None:
    """Returns the position of the first non-negated crash-event mention,
    or None. Negation check matters here too: 'no collision occurred' or
    similar should not count."""
    for m in CRASH_RE.finditer(text):
        if not _negated_nearby(text, m.start(), m.end()):
            return m.start()
    return None


def extract_age_band(text: str) -> str:
    m = AGE_NUM_RE.search(text)
    if m:
        return age_band(m.group(1))
    if TEEN_RE.search(text):
        return "13-17 (teen)"
    if CHILD_RE.search(text):
        return "0-12 (child)"
    return "Unknown"


STREET_SUFFIXES = {"st", "st.", "ave", "ave.", "rd", "rd.", "dr", "dr.",
                    "drive", "blvd", "blvd.", "ln", "ln.", "way", "ct",
                    "ct.", "pl", "pl.", "street", "avenue", "road", "lane",
                    "court", "place", "highway", "hwy", "hwy."}


def _clean_place(raw: str) -> str:
    """Multi-word matches before a ', ST' or 'County' can accidentally
    include a street name or section-label/directional token that precedes
    the real place ('Farnam St. Omaha, NE' -> 'Omaha'; 'SE Cedar Rapids' ->
    'Cedar Rapids'; 'Live Fresno County' -> 'Fresno County'). Strip both."""
    words = raw.split()
    for i, w in enumerate(words):
        if w.lower().rstrip(".") in {s.rstrip(".") for s in STREET_SUFFIXES}:
            words = words[i + 1:]
    while words and words[0].lower().rstrip(".") in JUNK_PREFIXES:
        words = words[1:]
    place = " ".join(words).strip()
    # AP-style datelines are SHOUTED IN ALL CAPS ("SOUTHAMPTON TWP.",
    # N.J.) -- fine for matching/geocoding (case-insensitive) but ugly to
    # display. Title-case anything that came through fully upper-case.
    if place.isupper():
        place = place.title()
    return place


def extract_location(text: str, domain: str | None = None) -> tuple[str, str, str] | None:
    """Returns (place, state, precision) or None. precision is one of:
    "dateline" (city, high confidence), "city_state_mention" (city, medium),
    "county+outlet_market" (county, medium -- coarser by nature), or
    "outlet_market" (state only, from a curated domain table, lowest)."""
    m = DATELINE_RE.search(text[:1500])
    if m:
        state = (m.group(2) + m.group(3)).upper()
        if state in STATE_ABBR and not PERSON_NAME_RE.match(m.group(1)):
            place = _clean_place(m.group(1).strip(", "))
            if place:
                return place, state, "dateline"

    for m in CITY_STATE_RE.finditer(text):
        state = (m.group(2) + m.group(3)).upper()
        if state not in STATE_ABBR or PERSON_NAME_RE.match(m.group(1)):
            continue
        place = _clean_place(m.group(1).strip(", "))
        if place:
            return place, state, "city_state_mention"

    m = COUNTY_RE.search(text)
    if m and domain in DOMAIN_STATE:
        county = _clean_place(m.group(1))
        if county:
            return f"{county} County", DOMAIN_STATE[domain], "county+outlet_market"

    if domain in DOMAIN_STATE:
        return None, DOMAIN_STATE[domain], "outlet_market"

    return None


def extract_incident(article: dict) -> dict | None:
    """Try full-text extraction; fall back to title-only. Returns None if we
    can't confidently confirm BOTH a device and a crash/injury event -- we'd
    rather under-report than mis-tag an unrelated article.

    Headlines ("Man killed in e-bike crash") are short and virtually always
    state device+crash+outcome together about the SAME event -- checking
    the title alone first is both more reliable and avoids a real failure
    mode we hit in testing: requiring proximity across the full article let
    real incidents get rejected when the device was re-mentioned far from
    the body's crash/outcome language, while a title-only check would have
    confirmed them immediately. Body text (with a wider but still-bounded
    proximity window) is the fallback when the title alone isn't enough.
    """
    # GDELT's title field inserts spaces around hyphens within words
    # ("e - bike", "14 - year - old") -- silently breaks every hyphen-aware
    # regex (device, age) until normalized back to "e-bike", "14-year-old".
    title = re.sub(r"(?<=\w) - (?=\w)", "-", article.get("title", "") or "")
    body = fetch_text(article.get("url", ""))
    text = (title + " " + body) if body else title

    title_device = extract_device(title)
    title_crash = extract_crash_position(title)
    title_outcome = extract_outcome(title)
    if title_device and title_crash is not None and title_outcome:
        device, outcome = title_device[0], title_outcome[0]
    else:
        device_match = extract_device(text)
        if not device_match:
            return None
        device, device_pos = device_match

        crash_pos = extract_crash_position(text)
        if crash_pos is None:
            return None

        outcome_match = extract_outcome(text)
        if not outcome_match:
            return None
        outcome, outcome_pos = outcome_match

        # All three signals must describe the SAME event, not three
        # unrelated mentions scattered across a long page (nav links,
        # related-stories blocks, etc.).
        positions = [device_pos, crash_pos, outcome_pos]
        if max(positions) - min(positions) > PROXIMITY_WINDOW:
            return None

    loc = extract_location(text if body else "", article.get("domain")) if body else (
        (None, DOMAIN_STATE[article["domain"]], "outlet_market")
        if article.get("domain") in DOMAIN_STATE else None
    )
    # "located" requires a place name (city/county), not just an outlet's
    # home state -- state-only is too coarse to put a point on a map.
    has_place = bool(loc and loc[0])
    return {
        "device": device,
        "outcome": outcome,
        "age_band": extract_age_band(text),
        "city": loc[0] if loc else None,
        "state": loc[1] if loc else None,
        "location_precision": loc[2] if loc else None,
        "located": has_place,
        "domain": article.get("domain"),
        "url": article.get("url"),
        "seendate": article.get("seendate"),
        # Headlines can themselves name a minor ("Jane Doe, 15, killed...").
        # Keep ONLY for internal dedup matching -- never serialize this into
        # web/data/*.json or render it in the dashboard. Public output shows
        # domain + url + our structured fields only.
        "_internal_title_for_dedup_only": title,
    }
