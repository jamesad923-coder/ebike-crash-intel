"""Best-effort contact discovery for a city government website.

Usage:
  python3 etl/outreach/find_contacts.py https://www.tomsrivertownship.com

Walks the site's staff-directory pages and surfaces name/title/email
candidates ranked by how relevant the title is to street safety
(engineer, transportation, public works, administrator). Many small-city
sites run CivicPlus/CivicEngage, whose /Directory.aspx structure is
predictable; a generic mailto/contact-page scan covers the rest.

HONESTY RULE: this tool REPORTS what it found and where; it never
guesses an address into the output. If a directory lists names but no
emails (common -- e.g. Middletown NJ), it says exactly that and prints
the pages it tried, so the human knows the 30-second phone call is the
next step. Guessed patterns bounce, and bounces burn credibility.

Output is meant to be pasted (after human eyes) into outreach/contacts.json.
"""
from __future__ import annotations

import html
import re
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; CrashAtlas-outreach/0.1; contact jamesad923@gmail.com)"}

# Title keywords, highest-value first -- used to rank candidates.
TITLE_SCORES = [
    (re.compile(r"traffic engineer|transportation (director|manager|planner)", re.I), 100),
    (re.compile(r"township engineer|city engineer|municipal engineer", re.I), 90),
    (re.compile(r"\bengineer(ing)?\b", re.I), 60),
    (re.compile(r"public works", re.I), 50),
    (re.compile(r"(township|city|borough) (administrator|manager)", re.I), 40),
    (re.compile(r"safety|mobility|complete streets|vision zero", re.I), 70),
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.(?:gov|org|com|us|net)")
MAILTO_RE = re.compile(r'mailto:([^"\'?]+)', re.I)
# CivicPlus obfuscates staff emails by splitting user/domain across JS
# vars and assembling at runtime:
#   var wsd="jmele"; var xsd="tomsrivertownship.com";
# -- the address never appears contiguously in the HTML, so the plain
# regexes above can't see it. Reassemble it ourselves.
CIVICPLUS_OBF_RE = re.compile(r'var\s+wsd="([^"]+)";\s*var\s+xsd="([^"]+)"')
EID_RE = re.compile(r'[Dd]irectory\.aspx\?EID=(\d+)')

# Paths worth probing on any city site, in order.
PROBE_PATHS = [
    "/Directory.aspx", "/directory.aspx", "/staff-directory", "/directory",
    "/departments", "/government/departments/department-contacts",
    "/contact", "/Contact", "/142/Contact",
]
# CivicPlus department-directory links look like Directory.aspx?did=N
DID_RE = re.compile(r'Directory\.aspx\?did=(\d+)', re.I)


def fetch(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read(400000).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def strip_tags(chunk: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", chunk)).strip()


def score_title(text: str) -> int:
    return max((s for rx, s in TITLE_SCORES if rx.search(text)), default=0)


def scan_page(url: str, page: str) -> list[dict]:
    """Pull (email, nearby-text) candidates from one page."""
    out = []
    obfuscated = {f"{u}@{d}" for u, d in CIVICPLUS_OBF_RE.findall(page)}
    for m in set(MAILTO_RE.findall(page)) | set(EMAIL_RE.findall(page)) | obfuscated:
        email = html.unescape(m).strip()
        if any(bad in email.lower() for bad in (
                "example.", "webmaster", "no-reply", "noreply", "donotreply",
                # CMS-vendor/system addresses, never a human contact:
                "revize.com", "civicplus", "granicus", "subscribers", "sitemail")):
            continue
        # context: text within ~300 chars around the first occurrence;
        # obfuscated addresses aren't contiguous in the HTML, so anchor
        # on their wsd variable instead.
        i = page.find(m)
        if i < 0:
            i = max(page.find(f'var wsd="{m.split("@")[0]}"'), 0)
        ctx = strip_tags(page[max(0, i - 300):i + 300])
        out.append({"email": email, "context": ctx[:220], "score": score_title(ctx), "source": url})
    return out


def discover(base: str) -> tuple[list[dict], list[str]]:
    base = base.rstrip("/")
    tried, candidates, dept_pages = [], [], set()

    for path in PROBE_PATHS:
        url = base + path
        page = fetch(url)
        tried.append(url + ("" if page else "  [unreachable]"))
        if not page:
            continue
        candidates += scan_page(url, page)
        # CivicPlus: harvest department sub-directories, prioritizing ones
        # whose link text smells like engineering/public works/admin.
        for did in set(DID_RE.findall(page)):
            dept_pages.add(f"{base}/Directory.aspx?did={did}")

    eids: set[str] = set()
    for url in sorted(dept_pages):
        page = fetch(url)
        tried.append(url + ("" if page else "  [unreachable]"))
        if page:
            candidates += scan_page(url, page)
            eids |= set(EID_RE.findall(page))

    # CivicPlus keeps the actual (obfuscated) email on per-person EID
    # pages, not the department listing. Politely bounded walk.
    import time
    for eid in sorted(eids, key=int)[:60]:
        url = f"{base}/directory.aspx?EID={eid}"
        page = fetch(url)
        if page:
            candidates += scan_page(url, page)
        time.sleep(0.25)
    if eids:
        tried.append(f"[walked {min(len(eids), 60)} of {len(eids)} staff EID pages]")

    # dedupe by email, keep best score
    best: dict[str, dict] = {}
    for c in candidates:
        k = c["email"].lower()
        if k not in best or c["score"] > best[k]["score"]:
            best[k] = c
    ranked = sorted(best.values(), key=lambda c: -c["score"])
    return ranked, tried


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: find_contacts.py https://www.cityexample.gov")
    ranked, tried = discover(sys.argv[1])
    if ranked:
        print(f"Found {len(ranked)} email candidate(s), best-scored first:\n")
        for c in ranked[:12]:
            print(f"  [{c['score']:3}] {c['email']}")
            print(f"        {c['context'][:150]}")
            print(f"        from: {c['source']}\n")
        print("REVIEW before use: confirm the person/title on the source page,")
        print("then add to outreach/contacts.json. Never send to an unverified hit.")
    else:
        print("No published emails found. Pages tried:")
        for t in tried:
            print("  ", t)
        print("\nNext step is the 30-second phone call to the department line --")
        print("do NOT guess an address pattern; bounces burn credibility.")


if __name__ == "__main__":
    main()
