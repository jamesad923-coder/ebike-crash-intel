"""Fetch recent micromobility-crash news mentions from GDELT's free DOC 2.0 API.

GDELT (gdeltproject.org) indexes worldwide online news and exposes a free,
keyless search API. This is the realistic "automatic" path to catching a
crash federal data won't show for years: NEISS/FARS lag months to years,
but a local news story about a crash is often online within hours.

Why this, not a paid news API: free, no key, no quota signup, good enough
recall for a v1. Tradeoff: GDELT indexes article METADATA (title, domain,
URL, date) well but full-text retrieval is a separate fetch per article
(done in extract.py) and is not always successful (paywalls, blocks).

Rate limiting note: GDELT asks for <=1 request every 5 seconds per IP. In
testing from a shared sandbox IP we saw intermittent HTTP 429 even when
spaced further apart than that -- evidence the limit is enforced across
concurrent users sharing an egress IP, not just our own request pacing.
Production runs (e.g. a GitHub Actions runner) will have their own IP and
should see this less. We retry with backoff regardless.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# Device keywords OR'd together, crash/injury keywords OR'd together.
# GDELT's query language needs hyphenated terms quoted, e.g. "e-bike".
DEVICE_TERMS = ['"e-bike"', '"electric bike"', "ebike", '"e-scooter"',
                '"electric scooter"', "hoverboard", '"Sur-Ron"']
EVENT_TERMS = ["crash", "killed", "struck", "collision", "injured", "dead", "hit"]


def build_query() -> str:
    devices = " OR ".join(DEVICE_TERMS)
    events = " OR ".join(EVENT_TERMS)
    return f"({devices}) ({events})"


def fetch_articles(timespan="3d", maxrecords=75, max_retries=5) -> list[dict]:
    """Query GDELT for recent candidate articles. Returns raw GDELT records
    (title, domain, url, seendate) -- no body text yet, no extraction yet.
    """
    params = {
        "query": build_query(),
        "mode": "artlist",
        "maxrecords": str(maxrecords),
        "format": "json",
        "timespan": timespan,
        "sort": "datedesc",
    }
    url = GDELT_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "ebike-crash-intel/0.1"})

    delay = 5
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8") or "{}")
                return data.get("articles", [])
        except HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise
    return []


if __name__ == "__main__":
    arts = fetch_articles()
    print(f"Fetched {len(arts)} candidate articles")
    for a in arts[:15]:
        print(f"  {a.get('seendate')} | {a.get('domain')} | {a.get('title')}")
