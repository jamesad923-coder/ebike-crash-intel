"""Build a ready-to-send outreach package for a city: report PDF +
drafted email + contact card, in one command.

  python3 etl/outreach/prepare.py nj/toms-river     # build package
  python3 etl/outreach/prepare.py --list            # log + follow-up clock
  python3 etl/outreach/prepare.py --mark-sent nj/toms-river
  python3 etl/outreach/prepare.py --mark-replied nj/toms-river "met Tues"

THE LINE WE HOLD: the machine drafts, a human sends. This tool produces
outreach/queue/{slug}/ containing everything ready to go -- James reads
the draft, checks the contact card's verification note, attaches the
PDF, and presses send himself. Nothing here talks to a mail server.

Everything under outreach/ is gitignored: the repo is public and city
staff shouldn't find themselves in a visible prospect tracker.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
OUTREACH = ROOT / "outreach"
QUEUE = OUTREACH / "queue"
CONTACTS = OUTREACH / "contacts.json"
LOG = OUTREACH / "log.json"

BASE_URL = "https://jamesad923-coder.github.io/ebike-crash-intel"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

sys.path.insert(0, str(ROOT / "etl"))


def _load(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def ensure_report(slug: str) -> dict:
    """Make sure the city has a generated report; returns its city_stats
    record. Builds the report on the fly for any of the 341 covered cities."""
    stats = _load(WEB / "data" / "city_stats.json", None)
    if stats is None:
        sys.exit("web/data/city_stats.json missing -- run etl/cities/build_city_data.py")
    rec = next((c for c in stats["cities"] if c["slug"] == slug), None)
    if rec is None:
        near = [c["slug"] for c in stats["cities"] if slug.split("/")[-1][:4] in c["slug"]]
        sys.exit(f"{slug!r} not in city_stats. Similar: {near[:6]}")
    if not (WEB / "reports" / slug / "index.html").exists():
        from reports.build_city_report import main as build_reports  # noqa: E402
        argv, sys.argv = sys.argv, ["build_city_report.py", slug]
        try:
            build_reports()
        finally:
            sys.argv = argv
    return rec


def make_pdf(slug: str, city: str, dest: Path) -> str:
    """Print the report to PDF via headless Chrome. Prefers the LIVE url
    (what we attach should be exactly what the emailed link shows);
    falls back to the local file if offline."""
    name = f"Crash-Atlas-{city.replace(' ', '-')}-Safety-Data-Report.pdf"
    out = dest / name
    for src in (f"{BASE_URL}/reports/{slug}/",
                (WEB / "reports" / slug / "index.html").as_uri()):
        r = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={out}", src],
            capture_output=True, timeout=90)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 20000:
            return name + ("" if src.startswith("http") else "  [from LOCAL file -- live site unreachable]")
    return f"PDF FAILED -- print manually: {BASE_URL}/reports/{slug}/  (Cmd+P > Save as PDF)"


def stood_out_line(rec: dict, years: list[int]) -> str:
    """The auto-drafted 'one thing that stood out' -- the sentence that
    proves the email isn't a mail merge. Marked for human review."""
    y0 = years[0]
    n = rec["total"]
    if n == 0:
        return (f"federal data shows zero recorded cyclist fatalities in "
                f"{rec['city']} since {y0} — which sounds like good news, but "
                f"mostly shows what fatality data can't see: the injuries and "
                f"near-misses happening to riders my age, which never reach "
                f"any federal dataset.")
    if n < 5:
        return (f"federal data records just {n} cyclist fatalit"
                f"{'y' if n == 1 else 'ies'} in {rec['city']} since {y0} — but "
                f"that number mostly shows what fatality data can't see: the "
                f"injuries and near-misses happening to riders my age, which "
                f"never reach any federal dataset.")
    top = rec["top_crash_groups"][0] if rec["top_crash_groups"] else None
    extra = (f" The most common crash type coded in your city's reports: "
             f"“{top['label']}” ({top['count']} of {n}).") if top else ""
    m = rec["minors"]
    minors_txt = ("none of them minors" if m == 0 else
                  f"including {m} minor{'s' if m != 1 else ''} (under 18)")
    return (f"federal data records {n} cyclist fatalities in {rec['city']} "
            f"since {y0}, {minors_txt}.{extra}")


def draft_email(rec: dict, contact: dict | None, years: list[int]) -> str:
    in_nj = rec["state_abbr"] == "NJ"
    where = "in Wall" if in_nj else "in Wall, New Jersey,"
    subject_tail = ("free report from a local student project" if in_nj
                    else "free report from a student-built open-data project")
    surname = ""
    if contact and contact.get("name"):
        surname = contact["name"].split()[-1]
    greeting = f"Hi Mr./Ms. {surname}," if surname else "Hi,"
    to_line = contact.get("email", "MANUAL LOOKUP NEEDED") if contact else "MANUAL LOOKUP NEEDED"
    cc = f"\nCC: {contact['cc']}" if contact and contact.get("cc") else ""

    return f"""TO: {to_line}{cc}
SUBJECT: Cyclist crash data for {rec['city']} — {subject_tail}

{greeting}

[REVIEW: greeting title, and personalize the stood-out line below if you know something local]

I'm James Adigun, a high school student {where} and an e-bike rider. After my friends and I had too many close calls, I built Crash Atlas — an open-data project that maps U.S. bike and e-bike crash data, with every number sourced.

I put together a safety data report for {rec['city']} — attached, and also at {BASE_URL}/reports/{rec['slug']}/. One thing that stood out: {stood_out_line(rec, years)}

It's free, it can go straight into a council packet, and corrections are welcome — if your team finds anything wrong, I want to know.

Happy to walk anyone through it.

James Adigun
Crash Atlas — {BASE_URL}/
Our story: {BASE_URL}/about/
"""


def prepare(slug: str) -> None:
    rec = ensure_report(slug)
    stats = _load(WEB / "data" / "city_stats.json", {})
    years = stats["years"]
    contacts = _load(CONTACTS, {})
    contact = contacts.get(slug)

    pkg = QUEUE / slug
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)

    pdf_status = make_pdf(slug, rec["city"], pkg)
    (pkg / "email.txt").write_text(draft_email(rec, contact, years))
    (pkg / "contact.json").write_text(json.dumps(
        contact or {"status": "NO CONTACT ON FILE",
                    "next": "run find_contacts.py on the city site, verify, add to outreach/contacts.json"},
        indent=2))

    log = _load(LOG, [])
    entry = next((e for e in log if e["city"] == slug), None)
    if entry is None:
        entry = {"city": slug, "contact": (contact or {}).get("email", ""),
                 "artifact": f"reports/{slug}/", "status": "prepared",
                 "send_date": None, "followup_due": None, "notes": ""}
        log.append(entry)
    else:
        entry["status"] = entry["status"] if entry["status"] in ("scheduled", "sent") else "prepared"
    LOG.write_text(json.dumps(log, indent=2))

    print(f"Package ready: {pkg.relative_to(ROOT)}/")
    print(f"  email.txt      drafted ({'contact on file' if contact else 'NO CONTACT -- lookup needed'})")
    print(f"  PDF            {pdf_status}")
    if contact and "INFERRED" in contact.get("verified", "").upper():
        print(f"  ⚠ contact email is inferred, not verified: {contact['verified']}")
    print("Review email.txt, attach the PDF, send from Gmail, then: --mark-sent", slug)


def mark(slug: str, status: str, note: str = "") -> None:
    log = _load(LOG, [])
    entry = next((e for e in log if e["city"] == slug), None)
    if entry is None:
        sys.exit(f"{slug} not in outreach log")
    entry["status"] = status
    if status == "sent":
        entry["send_date"] = _today()
        entry["followup_due"] = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
    if note:
        entry["notes"] = (entry.get("notes", "") + " | " + note).strip(" |")
    LOG.write_text(json.dumps(log, indent=2))
    print(f"{slug}: {status}" + (f" (follow-up due {entry['followup_due']})" if status == "sent" else ""))


def list_log() -> None:
    log = _load(LOG, [])
    if not log:
        print("Outreach log is empty.")
        return
    today = _today()
    print(f"{'city':22} {'status':10} {'sent':11} {'follow-up':11} contact")
    for e in sorted(log, key=lambda x: x.get("followup_due") or "9999"):
        due = e.get("followup_due") or ""
        flag = "  <-- FOLLOW UP" if (due and due <= today and e["status"] == "sent") else ""
        print(f"{e['city']:22} {e['status']:10} {e.get('send_date') or '-':11} "
              f"{due or '-':11} {e.get('contact','')}{flag}")
        if e.get("notes"):
            print(f"{'':22} note: {e['notes']}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == "--list":
        list_log()
    elif args[0] == "--mark-sent":
        mark(args[1], "sent", " ".join(args[2:]))
    elif args[0] == "--mark-replied":
        mark(args[1], "replied", " ".join(args[2:]))
    elif args[0] == "--mark-bounced":
        mark(args[1], "bounced", " ".join(args[2:]))
    else:
        prepare(args[0])


if __name__ == "__main__":
    main()
