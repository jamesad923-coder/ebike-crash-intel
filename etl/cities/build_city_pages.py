"""Generate static, SEO-indexable per-city pages from city_stats.json.

Each page is fully server-rendered HTML (stats, trend bars, breakdowns are
real text in the document, not JS-rendered) so search engines and social
previews see the content. The only client-side pieces are the map (MapLibre,
points inlined at build time -- no extra fetch) and the "recent reports"
section, which filters the news pipeline's already-auto-refreshed
news_incidents.geojson in the browser so city pages stay current on news
without any regeneration or CI changes.

Output:
  web/cities/{state}/{city-slug}/index.html   one page per city
  web/cities/index.html                       crawlable directory
  web/sitemap.xml, web/robots.txt             SEO plumbing

Run after build_city_data.py. Pure stdlib.
"""
from __future__ import annotations

import html
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
CITIES_DIR = WEB / "cities"

# Site config -- swap BASE_URL when a custom domain lands (one line).
BASE_URL = "https://jamesad923-coder.github.io/ebike-crash-intel"
SITE_NAME = "Crash Atlas"
REPO_URL = "https://github.com/jamesad923-coder/ebike-crash-intel"
# Where the "request a data brief" CTA points.
CONTACT_EMAIL = "jamesad923@gmail.com"

# A page whose city has fewer than this many fatalities gets a prominent
# small-numbers caveat instead of a trend framing.
SMALL_N = 5

E = html.escape

CSS = """
:root { --bg:#0e1116; --panel:#161b22; --line:#2a313c; --txt:#e6edf3;
        --muted:#8b949e; --accent:#f78166; --warn:#d29922; --good:#3fb950;
        --minor:#a371f7; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--txt);
  font:14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }
.wrap { max-width:860px; margin:0 auto; padding:24px 18px 60px; }
header.site { border-bottom:1px solid var(--line); }
header.site .wrap { display:flex; align-items:baseline; gap:14px; padding:14px 18px; }
.wordmark { font-weight:700; font-size:17px; color:var(--txt); letter-spacing:0.2px; }
.wordmark:hover { text-decoration:none; color:var(--accent); }
.tagline { color:var(--muted); font-size:12px; }
h1 { font-size:24px; margin:26px 0 4px; }
h2 { font-size:15px; margin:30px 0 10px; color:var(--txt); }
.sub { color:var(--muted); margin:0 0 18px; }
.banner { background:var(--panel); border:1px solid var(--warn); border-radius:10px;
  padding:12px 14px; font-size:13px; color:var(--txt); margin:18px 0; }
.banner.smalln { border-color:var(--accent); }
.stats { display:flex; gap:14px; flex-wrap:wrap; margin:18px 0; }
.stat { background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:12px 16px; min-width:150px; flex:1; }
.stat .n { display:block; font-size:26px; font-weight:700; }
.stat .l { color:var(--muted); font-size:12px; }
.stat.minor .n { color:var(--minor); }
.bar-row { margin:7px 0; }
.bar-row .lab { display:flex; justify-content:space-between; font-size:12.5px;
  color:var(--txt); margin-bottom:3px; }
.bar-row .lab span:last-child { color:var(--muted); }
.bar { background:var(--line); border-radius:4px; height:8px; overflow:hidden; }
.bar i { display:block; height:100%; background:var(--accent); border-radius:4px; }
#map { height:420px; border-radius:10px; border:1px solid var(--line); margin:10px 0; }
/* MapLibre popups default to a white box, and this page's light --txt
   inherits into it: white-on-white. Match the dashboard's dark panel,
   and also restyle the tip arrow + close button. Scoped under #map
   (popups render inside the map container) because MapLibre's own
   stylesheet is linked AFTER this style block -- the ID selector wins
   on specificity regardless of load order. */
#map .maplibregl-popup-content { background:var(--panel); color:var(--txt);
  border:1px solid var(--line); border-radius:8px; font-size:12px; }
#map .maplibregl-popup-content b { color:var(--accent); }
#map .maplibregl-popup-close-button { color:var(--muted); font-size:14px; }
#map .maplibregl-popup-anchor-bottom .maplibregl-popup-tip { border-top-color:var(--panel); }
#map .maplibregl-popup-anchor-top .maplibregl-popup-tip { border-bottom-color:var(--panel); }
#map .maplibregl-popup-anchor-left .maplibregl-popup-tip { border-right-color:var(--panel); }
#map .maplibregl-popup-anchor-right .maplibregl-popup-tip { border-left-color:var(--panel); }
.legend { color:var(--muted); font-size:12px; margin-bottom:6px; }
.dot { display:inline-block; width:9px; height:9px; border-radius:50%;
  vertical-align:middle; margin-right:5px; }
.cta { background:var(--panel); border:1px solid var(--good); border-radius:10px;
  padding:16px; margin:30px 0; }
.cta b { color:var(--good); }
.news-item { background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:11px 14px; margin:8px 0; font-size:13px; }
.news-item .tier { font-size:11px; color:var(--warn); }
.news-item .tier.corroborated { color:var(--good); }
footer { border-top:1px solid var(--line); margin-top:44px; padding-top:16px;
  color:var(--muted); font-size:12px; }
.states h2 { margin-top:26px; }
.citylist { columns:2; column-gap:30px; padding-left:18px; margin:6px 0; }
.citylist li { margin:3px 0; break-inside:avoid; }
.citylist .n { color:var(--muted); font-size:12px; }
@media (max-width:600px){ .citylist { columns:1; } .stats { flex-direction:column; } }
"""


def fmt(n: int) -> str:
    return f"{n:,}"


def bars(rows: list[dict], denom: int | None = None) -> str:
    """Server-rendered bar rows -- same look as the dashboard, but real
    HTML text so search engines index the numbers."""
    if not rows:
        return '<p class="sub">Not coded in this city\'s records.</p>'
    mx = max(r["count"] for r in rows) or 1
    out = []
    for r in rows:
        pct = f' ({r["count"] / denom * 100:.0f}%)' if denom else ""
        out.append(
            f'<div class="bar-row"><div class="lab"><span>{E(str(r["label"]))}</span>'
            f'<span>{fmt(r["count"])}{pct}</span></div>'
            f'<div class="bar"><i style="width:{r["count"] / mx * 100:.1f}%"></i></div></div>'
        )
    return "\n".join(out)


def head(title: str, desc: str, canonical: str, jsonld: dict | None = None) -> str:
    ld = (f'<script type="application/ld+json">{json.dumps(jsonld)}</script>'
          if jsonld else "")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="{SITE_NAME}">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🚲</text></svg>">
{ld}
<style>{CSS}</style>
</head>"""


def site_header(root_rel: str) -> str:
    return f"""<header class="site"><div class="wrap">
<a class="wordmark" href="{root_rel}">🚲 {SITE_NAME}</a>
<span class="tagline">U.S. cyclist &amp; e-bike crash intelligence · open data, every number sourced</span>
</div></header>"""


def city_page(c: dict, meta: dict) -> str:
    y0, y1 = meta["years"][0], meta["years"][-1]
    name = f'{c["city"]}, {c["state_abbr"]}'
    canonical = f'{BASE_URL}/cities/{c["slug"]}/'
    title = f"{name} Bicycle & E-Bike Crash Data ({y0}–{y1}) | {SITE_NAME}"
    desc = (f'{c["total"]} cyclist fatalities recorded in {name} in federal '
            f"crash data, {y0}–{y1}, including {c['minors']} minors. "
            f"Mapped, sourced, and honestly caveated. Counts, not rates.")
    jsonld = {
        "@context": "https://schema.org", "@type": "Dataset",
        "name": f"Pedalcyclist fatalities in {name}, {y0}-{y1}",
        "description": desc, "url": canonical,
        "creator": {"@type": "Organization", "name": SITE_NAME},
        "isBasedOn": "https://www.nhtsa.gov/research-data/fatality-analysis-reporting-system-fars",
        "license": "https://creativecommons.org/publicdomain/zero/1.0/",
    }

    small = c["total"] < SMALL_N
    small_note = ("" if not small else
        '<div class="banner smalln"><b>Small numbers — read with care.</b> '
        f'This city has {c["total"]} recorded fatalit'
        f'{"y" if c["total"] == 1 else "ies"} in this window. A single crash '
        "changes this picture entirely; no trend can be inferred. This page "
        "exists because local safety discussions deserve real data, not "
        "because the numbers support conclusions on their own.</div>")

    trend_rows = [{"label": y, "count": n} for y, n in c["by_year"].items()]
    pts_js = json.dumps(c["points"])
    center_js = json.dumps(c["center"] or [-96, 38])
    zoom = 11 if c["center"] else 3

    map_block = ""
    if c["points"]:
        map_block = f"""
<h2>Where these crashes happened</h2>
<div class="legend"><span class="dot" style="background:var(--minor)"></span>under 18
&nbsp;&nbsp;<span class="dot" style="background:var(--accent)"></span>adult / unknown age
&nbsp;&nbsp;·&nbsp; {c["n_mapped"]} of {c["total"]} records have usable coordinates</div>
<div id="map"></div>
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script>
const PTS = {pts_js};
const map = new maplibregl.Map({{ container:"map",
  style: {{ version:8, sources: {{ carto: {{ type:"raster",
    tiles:["https://a.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}.png"],
    tileSize:256, attribution:"© OpenStreetMap, © CARTO" }} }},
    layers:[{{ id:"carto", type:"raster", source:"carto" }}] }},
  center: {center_js}, zoom: {zoom} }});
map.on("load", () => {{
  map.addSource("pts", {{ type:"geojson", data: {{ type:"FeatureCollection",
    features: PTS.map(p => ({{ type:"Feature",
      geometry: {{ type:"Point", coordinates:[p[0], p[1]] }},
      properties: {{ year:p[2], minor:p[3] }} }})) }} }});
  map.addLayer({{ id:"pts", type:"circle", source:"pts",
    paint: {{ "circle-radius":6, "circle-opacity":0.85,
      "circle-stroke-width":0.5, "circle-stroke-color":"#000",
      "circle-color":["case",["==",["get","minor"],1],"#a371f7","#f78166"] }} }});
  map.on("click","pts", e => {{
    const p = e.features[0].properties;
    new maplibregl.Popup().setLngLat(e.lngLat)
      .setHTML(`${{p.year}} · ${{p.minor ? "under 18" : "adult / unknown age"}}`)
      .addTo(map);
  }});
}});
</script>"""

    return f"""{head(title, desc, canonical, jsonld)}
<body>
{site_header("../../../")}
<div class="wrap">
<h1>{E(name)}: Cyclist Fatality Data</h1>
<p class="sub">Federal crash data (NHTSA FARS), {y0}–{y1} · counts, not rates · updated as federal data is released</p>

<div class="banner"><b>Read this first.</b> These are <b>counts, not rates</b> —
there is no city-level ridership data, so a higher count can simply mean more
people ride. This is <b>fatal motor-vehicle crashes only</b>: single-bike falls
and non-fatal injuries are not in this source. <b>E-bikes cannot be separated</b>
from conventional bicycles in federal data. And only about two-thirds of
records nationally are coded to a specific city, so this count is a
<b>floor</b> for {E(c["city"])}-area fatalities, not a ceiling.</div>
{small_note}

<div class="stats">
<div class="stat"><span class="n">{fmt(c["total"])}</span><span class="l">cyclist fatalities, {y0}–{y1}</span></div>
<div class="stat minor"><span class="n">{fmt(c["minors"])}</span><span class="l">were minors (under 18)</span></div>
<div class="stat"><span class="n">{fmt(c["n_mapped"])}</span><span class="l">have a mappable location</span></div>
</div>

<h2>Year by year</h2>
{bars(trend_rows)}

<h2>Age bands</h2>
{bars(c["by_age_band"], c["total"])}

<h2>Lighting at time of crash</h2>
{bars(c["top_lighting"], c["total"])}

<h2>What the crash reports coded (PBCAT)</h2>
<p class="sub">Pre-crash actions from NHTSA crash-typing — what the report found, not a fault judgment.</p>
{bars(c["top_crash_groups"])}
{map_block}

<div id="news-wrap" style="display:none">
<h2>Recent news-detected reports near {E(c["city"])}</h2>
<p class="sub">From an automated news scan (GDELT) — unverified beyond automated checks;
click through to sources before treating any report as fact.</p>
<div id="news-list"></div>
</div>

<div class="cta">
<b>Work on safety in {E(c["city"])}?</b> City staff, school districts, advocacy
groups, and local reporters can request a <b>free data brief</b> for {E(name)} —
this page's data plus state context and crash-pattern detail, in a format ready
for council discussions or reporting.
<a href="mailto:{CONTACT_EMAIL}?subject=Data%20brief%20request:%20{E(c['city'].replace(' ', '%20'))},%20{c['state_abbr']}">Request a brief</a>
· <a href="../../../">Explore the national dashboard</a>
</div>

<footer>
Source: NHTSA Fatality Analysis Reporting System (FARS), {y0}–{y1} national files.
{E(meta["coding_note"])}
Methodology and every data source documented in
<a href="{REPO_URL}/blob/main/DATA_SOURCES.md">DATA_SOURCES.md</a>.
Generated {meta["generated"]} · <a href="../../../about/">our story</a> ·
<a href="{REPO_URL}">open source</a> · no tracking on this site.
</footer>
</div>

<script>
// Recent reports: filter the auto-refreshed news feed to this city,
// client-side, so this static page stays current without regeneration.
fetch("../../../data/news_incidents.geojson").then(r => r.json()).then(d => {{
  const CITY = {json.dumps(c["city"].lower())}, ST = {json.dumps(c["state_abbr"])};
  const hits = (d.features || []).filter(f => {{
    const p = f.properties || {{}};
    return (p.city || "").toLowerCase() === CITY && p.state === ST;
  }});
  if (!hits.length) return;
  document.getElementById("news-wrap").style.display = "";
  document.getElementById("news-list").innerHTML = hits.map(f => {{
    const p = f.properties;
    const tier = p.confidence_tier === "corroborated"
      ? '<span class="tier corroborated">corroborated (2+ outlets)</span>'
      : '<span class="tier">single source</span>';
    const src = (p.sources && p.sources[0]) ? p.sources[0] : null;
    const link = src ? ` · <a href="${{src.url}}" rel="nofollow">${{src.domain}}</a>` : "";
    const date = (p.date || "").slice(0,4) + "-" + (p.date || "").slice(4,6) + "-" + (p.date || "").slice(6,8);
    return `<div class="news-item">${{date}} · ${{p.device || "unknown device"}} ·
      ${{p.outcome || ""}} · age band: ${{p.age_band || "unknown"}} · ${{tier}}${{link}}</div>`;
  }}).join("");
}}).catch(() => {{}});
</script>
</body></html>"""


def index_page(cities: list[dict], meta: dict) -> str:
    y0, y1 = meta["years"][0], meta["years"][-1]
    canonical = f"{BASE_URL}/cities/"
    title = f"Bicycle & E-Bike Crash Data by City ({y0}–{y1}) | {SITE_NAME}"
    desc = (f"Cyclist fatality data pages for {len(cities)} U.S. cities, from "
            f"federal crash data {y0}–{y1}. Mapped, sourced, honestly caveated.")

    by_state: dict[str, list[dict]] = {}
    for c in cities:
        by_state.setdefault(c["state"], []).append(c)

    sections = []
    for state in sorted(by_state):
        rows = sorted(by_state[state], key=lambda r: -r["total"])
        items = "\n".join(
            f'<li><a href="{c["slug"]}/">{E(c["city"])}</a> '
            f'<span class="n">({c["total"]})</span></li>' for c in rows)
        sections.append(f"<h2>{E(state)}</h2>\n<ul class=\"citylist\">{items}</ul>")

    return f"""{head(title, desc, canonical)}
<body>
{site_header("../")}
<div class="wrap states">
<h1>Crash Data by City</h1>
<p class="sub">Cyclist fatality pages for {len(cities)} U.S. cities · NHTSA FARS {y0}–{y1}
· number in parentheses is total recorded fatalities</p>

<div class="banner"><b>Read this first.</b> City pages show <b>counts, not
rates</b> — more fatalities often just means more riding. Cities appear here
when they have at least {meta["min_fatalities"]} recorded fatalities in the window
(a handful of cities with active local e-bike safety discussions are included
below that threshold, clearly caveated). {E(meta["coding_note"])}</div>

{"".join(sections)}

<footer>
Source: NHTSA FARS {y0}–{y1} · generated {meta["generated"]} ·
<a href="{REPO_URL}">open source</a> · <a href="../">national dashboard</a>
</footer>
</div>
</body></html>"""


def build() -> None:
    data = json.loads((WEB / "data" / "city_stats.json").read_text())
    cities, meta = data["cities"], data

    # Fully regenerated output -- safe to clear, nothing hand-edited lives here.
    if CITIES_DIR.exists():
        shutil.rmtree(CITIES_DIR)
    CITIES_DIR.mkdir(parents=True)

    for c in cities:
        page_dir = CITIES_DIR / c["slug"]
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(city_page(c, meta))

    (CITIES_DIR / "index.html").write_text(index_page(cities, meta))

    urls = [f"{BASE_URL}/", f"{BASE_URL}/about/", f"{BASE_URL}/cities/"] + [
        f"{BASE_URL}/cities/{c['slug']}/" for c in cities]
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               + "\n".join(f"  <url><loc>{u}</loc></url>" for u in urls)
               + "\n</urlset>\n")
    (WEB / "sitemap.xml").write_text(sitemap)
    (WEB / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")

    print(f"Generated {len(cities)} city pages + index + sitemap ({len(urls)} URLs)")


if __name__ == "__main__":
    sys.exit(build())
