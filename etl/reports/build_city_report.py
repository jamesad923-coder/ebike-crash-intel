"""Generate plan-ready, print-first city safety data reports.

Unlike the site (dark, interactive), a report is a DOCUMENT: light
theme, print CSS, page-break aware -- "Save as PDF" from any browser
produces a clean artifact that forwards well inside a city hall and
drops into a council packet or an SS4A Safety Action Plan appendix.
That forwardability is the whole point: the email gets forwarded, the
attachment is the pitch that travels without us.

Sections: executive summary (auto-written, honest), FARS fatality
record, crash concentration screening (pilot cities only), state
context, the can/cannot-say block, methodology. No client-side JS at
all -- everything must survive printing.

Usage:
  python3 etl/reports/build_city_report.py            # default set
  python3 etl/reports/build_city_report.py ca/carlsbad ny/new-york-city
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"

BASE_URL = "https://jamesad923-coder.github.io/ebike-crash-intel"

# Anonymous, cookieless page-view counting (GoatCounter) -- the honest
# middle ground between "no tracking" and flying blind on whether outreach
# recipients ever open these pages. No personal data; copy on /about/
# says exactly what is collected.
GC_SCRIPT = ('<script data-goatcounter="https://crashatlas.goatcounter.com/count" '
             'async src="//gc.zgo.at/count.js"></script>')
REPO_URL = "https://github.com/jamesad923-coder/ebike-crash-intel"
CONTACT_EMAIL = "jamesad923@gmail.com"

# city_stats slug -> risk-screening key, for cities with pilot-level data.
PILOT_SCREENING = {
    "ny/new-york-city": "nyc",
    "dc/washington": "dc",
    "il/chicago": "chicago",
    "ma/boston": "boston",
}

# Default report set: the four data-rich pilots + the outreach beachhead.
DEFAULT_SLUGS = list(PILOT_SCREENING) + [
    "ca/encinitas", "ca/carlsbad", "ca/san-clemente",
    "ca/newport-beach", "ca/huntington-beach", "ca/oceanside",
]

E = html.escape

CSS = """
* { box-sizing:border-box; }
body { margin:0; background:#f6f7f9; color:#1a1f26;
  font:14px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
.page { max-width:820px; margin:0 auto; background:#fff; padding:44px 52px;
  box-shadow:0 1px 6px rgba(0,0,0,0.08); }
a { color:#b4432c; }
h1 { font-size:25px; margin:2px 0 4px; }
h2 { font-size:16px; margin:30px 0 8px; border-bottom:2px solid #e3e6ea;
  padding-bottom:5px; }
.kicker { color:#b4432c; font-weight:700; font-size:12px;
  text-transform:uppercase; letter-spacing:1.2px; }
.sub { color:#5b6570; margin:0 0 6px; font-size:13px; }
.rule { border:none; border-top:3px solid #1a1f26; margin:14px 0 4px; }
.summary { background:#f6f7f9; border-left:4px solid #b4432c; padding:12px 18px;
  margin:16px 0; }
.summary li { margin:5px 0; }
.stats { display:flex; gap:12px; margin:14px 0; }
.stat { border:1px solid #e3e6ea; border-radius:8px; padding:10px 14px; flex:1; }
.stat .n { display:block; font-size:24px; font-weight:700; }
.stat .l { color:#5b6570; font-size:11.5px; }
.stat.minor .n { color:#7c3aed; }
.bar-row { margin:6px 0; }
.bar-row .lab { display:flex; justify-content:space-between; font-size:12.5px;
  margin-bottom:2px; }
.bar-row .lab span:last-child { color:#5b6570; }
.bar { background:#e9ecf0; border-radius:3px; height:9px; }
.bar i { display:block; height:100%; background:#c2542f; border-radius:3px;
  print-color-adjust:exact; -webkit-print-color-adjust:exact; }
table { border-collapse:collapse; width:100%; font-size:12.5px; margin:10px 0; }
th { text-align:left; border-bottom:2px solid #1a1f26; padding:5px 8px 5px 0; }
td { border-bottom:1px solid #e3e6ea; padding:5px 8px 5px 0; }
.badge { font-size:10.5px; border:1px solid #2f9e44; color:#2f9e44;
  border-radius:8px; padding:0 7px; white-space:nowrap; }
.badge.ep { border-color:#9aa3ad; color:#9aa3ad; }
.note { background:#fff8e8; border:1px solid #e5c56b; border-radius:8px;
  padding:11px 15px; font-size:12.5px; margin:14px 0; }
.limits li { margin:6px 0; }
footer { color:#5b6570; font-size:11.5px; border-top:1px solid #e3e6ea;
  margin-top:34px; padding-top:12px; }
section { break-inside:avoid-page; }
@media print {
  body { background:#fff; }
  .page { box-shadow:none; padding:0; max-width:none; }
  a { color:#1a1f26; text-decoration:none; }
  @page { margin:18mm 16mm; }
}
"""


def fmt(n: int) -> str:
    return f"{n:,}"


def bars(rows: list[dict], denom: int | None = None) -> str:
    if not rows:
        return '<p class="sub">Not coded in this city\'s records.</p>'
    mx = max(r["count"] for r in rows) or 1
    out = []
    for r in rows:
        pct = f' ({r["count"] / denom * 100:.0f}%)' if denom else ""
        out.append(
            f'<div class="bar-row"><div class="lab"><span>{E(str(r["label"]))}</span>'
            f'<span>{fmt(r["count"])}{pct}</span></div>'
            f'<div class="bar"><i style="width:{r["count"] / mx * 100:.1f}%"></i></div></div>')
    return "\n".join(out)


def exec_summary(c: dict, years: list[int], state_line: str,
                 scr: dict | None) -> str:
    y0, y1 = years[0], years[-1]
    items = [f"<b>{fmt(c['total'])} cyclist fatalities</b> recorded in federal "
             f"crash data (FARS) for {E(c['city'])}, {y0}–{y1}"
             + (f", including <b>{c['minors']} minors</b> (under 18)." if c["minors"]
                else "; none were minors.")]

    if c["total"] >= 10:
        ys = sorted(c["by_year"].items())
        early = sum(n for _, n in ys[:2]) / 2
        late = sum(n for _, n in ys[-2:]) / 2
        if late > early * 1.25:
            items.append(f"Recorded fatalities have <b>risen</b>: the last two years "
                         f"average {late:.1f}/yr vs {early:.1f}/yr in the first two.")
        elif late < early * 0.75:
            items.append(f"Recorded fatalities have <b>declined</b>: the last two years "
                         f"average {late:.1f}/yr vs {early:.1f}/yr in the first two.")
        else:
            items.append(f"Recorded fatalities have held roughly steady "
                         f"(~{late:.1f}/yr recently).")
    else:
        items.append("Counts this small do not support trend statements — "
                     "a single crash changes the picture entirely.")

    if c["top_crash_groups"]:
        t = c["top_crash_groups"][0]
        items.append(f"The most common crash type coded by reporting officers "
                     f"(PBCAT): <b>“{E(t['label'])}”</b> ({t['count']} of "
                     f"{c['total']}) — a pattern, not a fault judgment.")
    if state_line:
        items.append(state_line)
    if scr:
        pers = sum(1 for x in scr["cells"] if x["persistent"])
        items.append(f"City-level crash concentration screening of "
                     f"{fmt(scr['n_points'])} recorded bicyclist crashes flags "
                     f"<b>{len(scr['cells'])} grid locations</b>, "
                     f"<b>{pers} persistent</b> across both halves of the data "
                     f"window — the locations most likely to reflect roadway "
                     f"conditions rather than chance.")
    return "<ul class='summary'>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def state_context(state_name: str, fars_summary: dict, risk: dict | None) -> tuple[str, str]:
    """Returns (one-line for exec summary, full section html)."""
    rows = fars_summary.get("by_state", [])
    total = next((r["count"] for r in rows if r["label"] == state_name), None)
    if total is None:
        return "", ""
    rank = 1 + sum(1 for r in rows if r["count"] > total)
    years = fars_summary["provenance"]["years"]
    line = (f"{E(state_name)} recorded <b>{fmt(total)}</b> pedalcyclist "
            f"fatalities statewide (#{rank} by raw count — counts, not rates).")
    section = (f"<p>{E(state_name)} recorded <b>{fmt(total)}</b> pedalcyclist "
               f"fatalities in FARS {years[0]}–{years[-1]}, ranking "
               f"<b>#{rank}</b> among states by raw count. Raw counts favor "
               f"large states: more residents, more riding, more exposure.</p>")
    if risk:
        try:
            r = next(x for x in risk["state_ranking"]["ranking"] if x["state"] == state_name)
            section += (f"<p>Adjusted for bike-commute share (a real but "
                        f"imperfect exposure proxy from ACS commute data — it "
                        f"misses recreational, delivery, and minors' riding), "
                        f"{E(state_name)} ranks <b>#{r['rate_rank']}</b> at "
                        f"{r['fatalities_per_10k_bike_commuters']} fatalities "
                        f"per 10,000 bike commuters (raw-count rank "
                        f"#{r['count_rank']}). The gap between the two ranks "
                        f"is itself informative.</p>")
        except (StopIteration, KeyError):
            pass
    return line, section


def screening_section(scr: dict, area_label: str = "area") -> str:
    y0, y1 = scr["window"][0][:4], scr["window"][1][:4]
    rows = []
    for i, c in enumerate(scr["cells"][:10], 1):
        badge = ('<span class="badge">persistent</span>' if c["persistent"]
                 else '<span class="badge ep">episodic</span>')
        rows.append(f"<tr><td>#{i}</td><td>{E(c['area'])}</td>"
                    f"<td>{c['total']}</td><td>{c['fatal']}</td>"
                    f"<td>{c['near_lane_share'] * 100:.0f}%</td><td>{badge}</td></tr>")
    pers = sum(1 for c in scr["cells"] if c["persistent"])
    return f"""
<p>Screening of <b>{fmt(scr["n_points"])}</b> recorded bicyclist crashes
({y0}–{y1}, city open data) across ~250m grid cells — the standard first step
of a High-Injury Network analysis. <b>Persistent</b> means concentrated in both
halves of the window (≥{scr["persistence_threshold"]} crashes in each):
those locations most likely reflect roadway conditions rather than chance, and
are where systemic-safety practice directs engineering attention first.
{pers} of the top {len(scr["cells"])} locations are persistent.</p>
<table><tr><th>Rank</th><th>Area</th><th>Crashes</th><th>Fatal</th>
<th>Near mapped bike lane</th><th>Pattern</th></tr>{"".join(rows)}</table>
<p class="sub">Interactive map version with exact locations:
{BASE_URL}/risk-screening/ · “Near mapped bike lane” = within ~30m of an
OpenStreetMap-mapped cycleway — infrastructure context, not a cause claim.</p>
<div class="note"><b>How to read this honestly:</b> this screening is
count-based and <b>not exposure-adjusted</b> — busy corridors rank high partly
because more people ride there, and a high-count location can be the safest
place per rider in the city. It identifies where to <b>look</b>, not what to
conclude. It supports engineering judgment; it never replaces it.</div>"""


def report(c: dict, meta: dict, fars_summary: dict, risk: dict | None,
           scr: dict | None) -> str:
    years = meta["years"]
    y0, y1 = years[0], years[-1]
    name = f"{c['city']}, {c['state_abbr']}"
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    state_line, state_sec = state_context(c["state"], fars_summary, risk)
    trend_rows = [{"label": y, "count": n} for y, n in c["by_year"].items()]

    small_note = ("" if c["total"] >= 5 else
        '<div class="note"><b>Small numbers — read with care.</b> This city\'s '
        'recorded fatality count is very low; no trend or comparison should be '
        'inferred from it. This report exists because local safety discussions '
        'deserve real data and honest framing, not because the counts alone '
        'support conclusions. The larger local picture (injuries, near misses) '
        'lives in data no federal source captures.</div>')

    scr_html = (f"<section><h2>Crash concentration screening (city open data)</h2>"
                f"{screening_section(scr)}</section>" if scr else "")

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(name)} Bicycle &amp; E-Bike Safety Data Report | Crash Atlas</title>
<meta name="robots" content="noindex">
<style>{CSS}</style></head>
<body><div class="page">

<div class="kicker">Crash Atlas · City Safety Data Report</div>
<h1>{E(name)}: Bicycle &amp; E-Bike Safety Data</h1>
<p class="sub">Prepared {today} · federal data {y0}–{y1} · every number sourced ·
may be reproduced and circulated freely</p>
<hr class="rule">

<section>
<h2>Executive summary</h2>
{exec_summary(c, years, state_line, scr)}
{small_note}
</section>

<section>
<h2>Fatality record (NHTSA FARS, {y0}–{y1})</h2>
<div class="stats">
<div class="stat"><span class="n">{fmt(c["total"])}</span><span class="l">cyclist fatalities recorded</span></div>
<div class="stat minor"><span class="n">{fmt(c["minors"])}</span><span class="l">were minors (under 18)</span></div>
<div class="stat"><span class="n">{fmt(c["n_mapped"])}</span><span class="l">with mappable location</span></div>
</div>
<h3 style="font-size:13.5px;margin:16px 0 4px">Year by year</h3>
{bars(trend_rows)}
<h3 style="font-size:13.5px;margin:16px 0 4px">Age bands</h3>
{bars(c["by_age_band"], c["total"])}
<h3 style="font-size:13.5px;margin:16px 0 4px">Lighting at time of crash</h3>
{bars(c["top_lighting"], c["total"])}
<h3 style="font-size:13.5px;margin:16px 0 4px">Crash types coded by reporting officers (PBCAT)</h3>
{bars(c["top_crash_groups"])}
<p class="sub">Interactive map of these crashes: {BASE_URL}/cities/{c["slug"]}/</p>
</section>

{scr_html}

<section>
<h2>State context</h2>
{state_sec}
</section>

<section>
<h2>What this data can and cannot say</h2>
<ul class="limits">
<li><b>Counts, not rates.</b> No city-level ridership denominator exists;
a higher count can simply mean more people ride.</li>
<li><b>Fatal motor-vehicle crashes only</b> in the federal record —
single-bike falls and non-fatal injuries (the majority of e-bike ED visits)
are absent from FARS entirely.</li>
<li><b>E-bikes cannot be separated</b> from conventional bicycles in federal
crash data. Only CPSC's NEISS isolates them (2024 onward), as national
emergency-department estimates that cannot be mapped to a city.</li>
<li>Only ~two-thirds of federal records are coded to a specific city — city
counts are a <b>floor</b>, not a ceiling.</li>
<li>Crash-type codes describe what the report found, <b>not fault</b>.</li>
</ul>
</section>

<section>
<h2>Methodology &amp; sources</h2>
<p>Fatality data: NHTSA Fatality Analysis Reporting System (FARS), national
files {y0}–{y1}, pedalcyclist person types, age-banded (never exact ages).
{"City crash screening: municipal open crash data via the Crash Atlas pilot pipeline, ~250m grid cells, persistence checked across window halves. " if scr else ""}
State exposure adjustment: ACS bike-commute share. Full methodology, source
documentation, and all code are public: {REPO_URL} — every number in this
report can be independently reproduced.</p>
</section>

<footer>
Prepared by <b>Crash Atlas</b> — an independent, open-data road-safety project
by James Adigun (our story: {BASE_URL}/about/).
Questions, corrections, or an expanded version of this report (no cost):
<a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a> ·
live dashboard: {BASE_URL}/ · report page: {BASE_URL}/reports/{c["slug"]}/
</footer>
{GC_SCRIPT}
</div></body></html>"""


def main() -> None:
    slugs = sys.argv[1:] or DEFAULT_SLUGS
    stats = json.loads((WEB / "data" / "city_stats.json").read_text())
    fars_summary = json.loads((WEB / "data" / "fars_summary.json").read_text())
    try:
        risk = json.loads((WEB / "data" / "risk_summary.json").read_text())
    except (OSError, json.JSONDecodeError):
        risk = None
    by_slug = {c["slug"]: c for c in stats["cities"]}

    for slug in slugs:
        c = by_slug.get(slug)
        if not c:
            print(f"  SKIP {slug}: not in city_stats.json")
            continue
        scr = None
        if slug in PILOT_SCREENING:
            p = WEB / "data" / f"risk_screen_{PILOT_SCREENING[slug]}.json"
            if p.exists():
                scr = json.loads(p.read_text())
        out = WEB / "reports" / slug
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(report(c, stats, fars_summary, risk, scr))
        print(f"  wrote reports/{slug}/ (screening: {'yes' if scr else 'no'})")


if __name__ == "__main__":
    main()
