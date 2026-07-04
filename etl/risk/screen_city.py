"""Phase-1 systemic risk screening for a pilot city: grid-cell crash
concentration with persistence checking.

WHAT THIS IS: the standard first step of a High-Injury Network analysis.
Overlay a ~250m grid on the city, count bicyclist crashes per cell over
the multi-year window, rank, and check PERSISTENCE -- whether a cell is
concentrated in both halves of the window or just spiked once. Persistent
concentrations are the locations systemic-safety practice says to examine
first, because they reflect roadway conditions rather than chance.

WHAT THIS IS NOT (printed on the page, verbatim):
  - Not a prediction. It flags where documented crashes concentrate, not
    where the next one will happen.
  - Not exposure-adjusted. Busy corridors rank high partly because more
    people ride there. A high-count cell can be the SAFEST place per
    rider in the city. This screening supports engineering judgment;
    it never replaces it.
  - Cell boundaries are arbitrary ~250m squares; a hotspot straddling a
    boundary appears split. Real corridor studies come after screening.

Usage: python3 etl/risk/screen_city.py nyc   (also: dc, chicago, boston)
"""
from __future__ import annotations

import html
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"

BASE_URL = "https://jamesad923-coder.github.io/ebike-crash-intel"
REPO_URL = "https://github.com/jamesad923-coder/ebike-crash-intel"
CONTACT_EMAIL = "jamesad923@gmail.com"

CITIES = {
    "nyc": {"name": "New York City", "pilot": "nyc_pilot.json",
            "area_label": "borough", "center": [-73.95, 40.72], "zoom": 10.5},
    "dc": {"name": "Washington, DC", "pilot": "dc_pilot.json",
           "area_label": "ward", "center": [-77.02, 38.9], "zoom": 11.5},
    "chicago": {"name": "Chicago", "pilot": "chicago_pilot.json",
                "area_label": "ward", "center": [-87.65, 41.85], "zoom": 10.8},
    "boston": {"name": "Boston", "pilot": "boston_pilot.json",
               "area_label": "district", "center": [-71.07, 42.33], "zoom": 11.5},
}

CELL = 0.0025  # ~250m N-S; a little narrower E-W at these latitudes
TOP_N = 20
E = html.escape


def load_points(pilot_file: str, center: list[float]) -> list[dict]:
    """Load crash points, defensively dropping anything implausibly far
    from the city center (>0.75 deg, ~80km). NYC's source data shipped 340
    records at exactly (0,0) that parsed as valid floats -- the upstream
    transform now filters those, but the screener must never let a similar
    artifact in ANY city's data become a fake #1 'hotspot'."""
    data = json.loads((WEB / "data" / pilot_file).read_text())
    feats = data["ward_summary"]["geojson"]["features"]
    out = []
    dropped = 0
    for f in feats:
        lon, lat = f["geometry"]["coordinates"]
        if abs(lon - center[0]) > 0.75 or abs(lat - center[1]) > 0.75:
            dropped += 1
            continue
        p = f["properties"]
        out.append({
            "lon": lon, "lat": lat,
            "fatal": bool(p.get("fatal")),
            "near_lane": bool(p.get("near_bike_lane")),
            "area": p.get("ward", ""),
            "date": p.get("date") or "",
        })
    if dropped:
        print(f"  note: dropped {dropped} point(s) implausibly far from city center")
    return out


def screen(points: list[dict]) -> dict:
    dates = sorted(p["date"] for p in points if p["date"])
    midpoint = dates[len(dates) // 2] if dates else ""

    cells = defaultdict(lambda: {
        "total": 0, "fatal": 0, "near_lane": 0,
        "first_half": 0, "second_half": 0, "by_year": Counter(), "areas": Counter(),
    })
    for p in points:
        key = (int(p["lon"] / CELL), int(p["lat"] / CELL))
        c = cells[key]
        c["total"] += 1
        c["fatal"] += p["fatal"]
        c["near_lane"] += p["near_lane"]
        if p["date"]:
            c["by_year"][p["date"][:4]] += 1
            if p["date"] <= midpoint:
                c["first_half"] += 1
            else:
                c["second_half"] += 1
        if p["area"]:
            c["areas"][p["area"]] += 1

    # Persistence: concentrated in BOTH halves of the window. The bar for
    # "concentrated" in a half is the 90th-percentile half-count across
    # cells that have any crashes -- self-scaling, no magic constant.
    halves = sorted(max(c["first_half"], c["second_half"]) for c in cells.values())
    p90 = halves[int(len(halves) * 0.9)] if halves else 0
    threshold = max(2, p90 // 2)

    ranked = []
    for (gx, gy), c in cells.items():
        persistent = c["first_half"] >= threshold and c["second_half"] >= threshold
        ranked.append({
            "bounds": [round(gx * CELL, 5), round(gy * CELL, 5),
                       round((gx + 1) * CELL, 5), round((gy + 1) * CELL, 5)],
            "center": [round((gx + 0.5) * CELL, 5), round((gy + 0.5) * CELL, 5)],
            "total": c["total"], "fatal": c["fatal"],
            "near_lane_share": round(c["near_lane"] / c["total"], 2),
            "first_half": c["first_half"], "second_half": c["second_half"],
            "persistent": persistent,
            "by_year": dict(sorted(c["by_year"].items())),
            "area": c["areas"].most_common(1)[0][0] if c["areas"] else "",
        })
    ranked.sort(key=lambda r: (-r["total"], -r["fatal"]))

    window = (dates[0], dates[-1]) if dates else ("", "")
    return {"cells": ranked[:TOP_N], "n_cells_with_crashes": len(cells),
            "n_points": len(points), "window": window,
            "persistence_threshold": threshold, "midpoint": midpoint}


def factors_line(c: dict) -> str:
    out = []
    if c["fatal"]:
        out.append(f'<b style="color:var(--minor)">{c["fatal"]} fatal</b>')
    if c["near_lane_share"] < 0.35:
        out.append(f"only {c['near_lane_share'] * 100:.0f}% of crashes near any "
                   f"mapped bike lane — possible network gap (context, not cause)")
    elif c["near_lane_share"] > 0.75:
        out.append(f"{c['near_lane_share'] * 100:.0f}% near a mapped lane — "
                   f"infrastructure present; conflict points worth an engineering look")
    out.append("persistent across both halves of the window"
               if c["persistent"] else
               "NOT persistent — concentration may be episodic")
    return " · ".join(out)


def page(city_key: str, cfg: dict, s: dict) -> str:
    name = cfg["name"]
    title = f"Bicyclist Crash Concentration Screening: {name} | Crash Atlas"
    desc = (f"Grid-cell screening of {s['n_points']:,} recorded bicyclist "
            f"crashes in {name} — the first step of a High-Injury Network "
            f"analysis. Count-based, honestly caveated, not a prediction.")
    canonical = f"{BASE_URL}/risk-screening/{city_key}/"
    y0, y1 = s["window"][0][:4], s["window"][1][:4]

    cards = []
    for i, c in enumerate(s["cells"], 1):
        yr = ", ".join(f"{y}: {n}" for y, n in c["by_year"].items())
        badge = ('<span class="badge persistent">persistent</span>' if c["persistent"]
                 else '<span class="badge">episodic</span>')
        cards.append(f"""<div class="cell-card" data-i="{i - 1}">
<div class="cell-head"><b>#{i}</b> · {E(c["area"])} · {c["total"]} crashes {badge}</div>
<div class="cell-factors">{factors_line(c)}</div>
<div class="cell-years">{yr}</div>
</div>""")

    cells_js = json.dumps(s["cells"])
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🚲</text></svg>">
<style>
:root {{ --bg:#0e1116; --panel:#161b22; --line:#2a313c; --txt:#e6edf3;
  --muted:#8b949e; --accent:#f78166; --warn:#d29922; --good:#3fb950; --minor:#a371f7; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--txt);
  font:14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
a {{ color:var(--accent); text-decoration:none; }} a:hover {{ text-decoration:underline; }}
header.site {{ border-bottom:1px solid var(--line); padding:14px 18px; }}
.wordmark {{ font-weight:700; font-size:17px; color:var(--txt); }}
.tagline {{ color:var(--muted); font-size:12px; margin-left:12px; }}
.layout {{ display:grid; grid-template-columns:420px 1fr; gap:0; height:calc(100vh - 51px); }}
.side {{ overflow-y:auto; padding:18px; border-right:1px solid var(--line); }}
h1 {{ font-size:19px; margin:4px 0 2px; }}
.sub {{ color:var(--muted); margin:0 0 12px; font-size:12.5px; }}
.banner {{ background:var(--panel); border:1px solid var(--warn); border-radius:10px;
  padding:11px 13px; font-size:12.5px; margin:12px 0; }}
.cell-card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:10px 12px; margin:8px 0; cursor:pointer; font-size:12.5px; }}
.cell-card:hover, .cell-card.active {{ border-color:var(--accent); }}
.cell-head {{ font-size:13px; }}
.cell-factors {{ color:var(--muted); margin:4px 0; }}
.cell-years {{ color:var(--muted); font-size:11.5px; }}
.badge {{ font-size:10.5px; border:1px solid var(--muted); color:var(--muted);
  border-radius:8px; padding:1px 7px; margin-left:6px; }}
.badge.persistent {{ border-color:var(--good); color:var(--good); }}
#map {{ height:100%; }}
footer {{ color:var(--muted); font-size:11.5px; padding:14px 0; }}
@media (max-width:800px) {{ .layout {{ grid-template-columns:1fr; height:auto; }}
  #map {{ height:420px; }} }}
</style>
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css">
</head><body>
<header class="site"><a class="wordmark" href="../../">🚲 Crash Atlas</a>
<span class="tagline">Risk screening demo · count-based · supports judgment, never replaces it</span></header>
<div class="layout">
<div class="side">
<h1>{E(name)}: Crash Concentration Screening</h1>
<p class="sub">{s["n_points"]:,} recorded bicyclist crashes, {y0}–{y1} ·
top {len(s["cells"])} of {s["n_cells_with_crashes"]:,} ~250m grid cells ·
generated {datetime.now().strftime("%Y-%m-%d")}</p>

<div class="banner"><b>Read this first.</b> This is the first step of a
High-Injury-Network-style analysis: where documented crashes <b>concentrate</b>.
It is <b>not a prediction</b> and <b>not exposure-adjusted</b> — busy corridors
rank high partly because more people ride there; a high-count cell can be the
safest place per rider in the city. <b>Persistent</b> means concentrated in both
halves of the window (≥{s["persistence_threshold"]} crashes in each) — those
locations most likely reflect roadway conditions rather than chance, and are
where systemic-safety practice says to look first. Cell boundaries are
arbitrary ~250m squares. This screening <b>supports engineering judgment; it
never replaces it</b>.</div>

{"".join(cards)}

<footer>Source: city open crash data via the <a href="../../">Crash Atlas</a>
pilot pipeline · method &amp; code <a href="{REPO_URL}">open source</a> ·
city staff can request the full-resolution version:
<a href="mailto:{CONTACT_EMAIL}?subject=Risk%20screening:%20{E(name.replace(" ", "%20"))}">{CONTACT_EMAIL}</a></footer>
</div>
<div id="map"></div>
</div>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script>
const CELLS = {cells_js};
const map = new maplibregl.Map({{ container:"map",
  style: {{ version:8, sources: {{ carto: {{ type:"raster",
    tiles:["https://a.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}.png"],
    tileSize:256, attribution:"© OpenStreetMap, © CARTO" }} }},
    layers:[{{ id:"carto", type:"raster", source:"carto" }}] }},
  center: {json.dumps(cfg["center"])}, zoom: {cfg["zoom"]} }});
map.on("load", () => {{
  map.addSource("cells", {{ type:"geojson", data: {{ type:"FeatureCollection",
    features: CELLS.map((c, i) => ({{ type:"Feature",
      geometry: {{ type:"Polygon", coordinates: [[
        [c.bounds[0], c.bounds[1]], [c.bounds[2], c.bounds[1]],
        [c.bounds[2], c.bounds[3]], [c.bounds[0], c.bounds[3]],
        [c.bounds[0], c.bounds[1]]]] }},
      properties: {{ i, total: c.total, persistent: c.persistent ? 1 : 0 }} }})) }} }});
  map.addLayer({{ id:"cells-fill", type:"fill", source:"cells",
    paint: {{ "fill-color": ["case", ["==", ["get","persistent"], 1], "#f78166", "#d29922"],
      "fill-opacity": 0.35 }} }});
  map.addLayer({{ id:"cells-line", type:"line", source:"cells",
    paint: {{ "line-color": ["case", ["==", ["get","persistent"], 1], "#f78166", "#d29922"],
      "line-width": 1.5 }} }});
  map.on("click", "cells-fill", e => {{
    const i = e.features[0].properties.i;
    document.querySelectorAll(".cell-card").forEach(el => el.classList.remove("active"));
    const card = document.querySelector(`.cell-card[data-i="${{i}}"]`);
    if (card) {{ card.classList.add("active"); card.scrollIntoView({{ behavior:"smooth", block:"center" }}); }}
  }});
  map.on("mouseenter","cells-fill",()=>map.getCanvas().style.cursor="pointer");
  map.on("mouseleave","cells-fill",()=>map.getCanvas().style.cursor="");
}});
document.querySelectorAll(".cell-card").forEach(el => el.addEventListener("click", () => {{
  const c = CELLS[+el.dataset.i];
  document.querySelectorAll(".cell-card").forEach(x => x.classList.remove("active"));
  el.classList.add("active");
  map.flyTo({{ center: c.center, zoom: 14.5 }});
}}));
</script>
</body></html>"""


def main() -> None:
    city_key = (sys.argv[1] if len(sys.argv) > 1 else "nyc").lower()
    if city_key not in CITIES:
        sys.exit(f"unknown city {city_key!r}; choose from {sorted(CITIES)}")
    cfg = CITIES[city_key]
    points = load_points(cfg["pilot"], cfg["center"])
    s = screen(points)
    out_dir = WEB / "risk-screening" / city_key
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(page(city_key, cfg, s))
    # Machine-readable artifact so other generators (the plan-ready city
    # reports) can embed the screening without re-deriving it.
    (WEB / "data" / f"risk_screen_{city_key}.json").write_text(json.dumps(
        {"city": cfg["name"], "generated": datetime.now().strftime("%Y-%m-%d"), **s}))
    print(f"{cfg['name']}: {s['n_points']:,} points -> "
          f"{s['n_cells_with_crashes']:,} cells with crashes; "
          f"persistence threshold {s['persistence_threshold']}/half")
    for i, c in enumerate(s["cells"][:8], 1):
        print(f"  #{i}: {c['area']:14} total={c['total']:3} fatal={c['fatal']} "
              f"halves={c['first_half']}/{c['second_half']} "
              f"{'PERSISTENT' if c['persistent'] else 'episodic'}")
    print(f"Wrote {out_dir / 'index.html'}")


if __name__ == "__main__":
    main()
