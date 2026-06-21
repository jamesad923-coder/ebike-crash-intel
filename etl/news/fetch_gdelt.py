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


def build_query(us_only: bool = True) -> str:
    devices = " OR ".join(DEVICE_TERMS)
    events = " OR ".join(EVENT_TERMS)
    q = f"({devices}) ({events})"
    if us_only:
        # CRITICAL for recall, not just relevance: without this, GDELT's
        # global volume on these generic terms is dominated by non-US
        # noise (UK/Ireland local papers, e-bike product/sales coverage,
        # etc.). We measured this directly -- of 75 results sorted by
        # recency, only ~11.5 HOURS of real-world time were covered before
        # the cap was hit, meaning a real story from days earlier (a teen's
        # fatal e-bike crash, confirmed indexed by GDELT) never made it into
        # our candidate set at all. It wasn't rejected by extraction -- it
        # was crowded out before extraction ever ran. Restricting to US
        # sources removes most of that noise and lets maxrecords actually
        # cover the requested timespan.
        q += " sourcecountry:US"
    return q


def fetch_articles(timespan="3d", maxrecords=250, max_retries=5, us_only: bool = True) -> list[dict]:
    """Query GDELT for recent candidate articles. Returns raw GDELT records
    (title, domain, url, seendate) -- no body text yet, no extraction yet.

    maxrecords defaults to 250, GDELT's documented maximum for the free DOC
    2.0 API -- using a smaller cap (we previously used 75) silently drops
    real stories under high global volume; see build_query()'s us_only note.
    """
    params = {
        "query": build_query(us_only=us_only),
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
                articles = data.get("articles", [])
                _warn_if_undercovered(articles, timespan, maxrecords)
                return articles
        except HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise
    return []


_TIMESPAN_DAYS = {"1d": 1, "3d": 3, "7d": 7, "14d": 14, "1week": 7, "2week": 14}


def _warn_if_undercovered(articles: list[dict], timespan: str, maxrecords: int) -> None:
    """If the maxrecords cap was hit and the returned articles span
    meaningfully less time than requested, the candidate set is silently
    incomplete -- older real stories within the requested window exist in
    GDELT but never made it into our results. Surface this loudly (stdout,
    visible in the Action log) rather than letting it fail silently, since
    this exact failure mode is what caused real crash reports to be missed.
    """
    if len(articles) < maxrecords or not articles:
        return
    requested_days = _TIMESPAN_DAYS.get(timespan)
    if not requested_days:
        return
    dates = sorted(a["seendate"][:8] for a in articles if a.get("seendate"))
    if not dates:
        return
    from datetime import datetime
    span_days = (datetime.strptime(dates[-1], "%Y%m%d") - datetime.strptime(dates[0], "%Y%m%d")).days
    if span_days < requested_days * 0.5:
        print(f"WARNING: hit maxrecords={maxrecords} cap, but results only "
              f"span {span_days}d of the requested {requested_days}d window "
              f"({dates[0]} to {dates[-1]}). Older real stories may be "
              f"missing from this run -- consider raising maxrecords or "
              f"narrowing the query further.")


if __name__ == "__main__":
    arts = fetch_articles()
    print(f"Fetched {len(arts)} candidate articles")
    for a in arts[:15]:
        print(f"  {a.get('seendate')} | {a.get('domain')} | {a.get('title')}")
