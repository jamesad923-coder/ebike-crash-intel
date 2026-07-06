"""Generate og:image social cards for every city page (1200x630 PNG).

Why this exists: the distribution channel for teen e-bike safety content
is a parent sharing a link into a Facebook group or group chat. A bare
link with no preview card gets skimmed past; a bold card ("TOMS RIVER,
NJ — 2 cyclist fatalities recorded 2019-2024") gets opened and reshared.

Renders a small HTML template per city through the same headless Chrome
used for report PDFs. Output: web/cities/{slug}/card.png, plus one
generic card at web/card.png for the dashboard and cities index.

Run after build_city_data.py. ~1s per city; grab a coffee.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def card_html(kicker: str, title: str, big: str, sub: str, minors: str = "") -> str:
    minors_html = (f'<div style="font-size:34px;color:#a371f7;margin-top:6px">{minors}</div>'
                   if minors else "")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
* {{ margin:0; box-sizing:border-box; }}
body {{ width:1200px; height:630px; background:#0e1116; color:#e6edf3;
  font-family:-apple-system, "Segoe UI", Roboto, sans-serif; display:flex; }}
.bar {{ width:14px; background:#f78166; }}
.pad {{ padding:56px 64px; display:flex; flex-direction:column; height:100%; width:100%; }}
.kicker {{ color:#f78166; font-weight:700; font-size:28px; letter-spacing:2px;
  text-transform:uppercase; }}
.title {{ font-size:64px; font-weight:800; margin-top:18px; line-height:1.1; }}
.big {{ font-size:52px; font-weight:700; margin-top:auto; color:#e6edf3; }}
.big b {{ color:#f78166; font-size:96px; }}
.sub {{ color:#8b949e; font-size:26px; margin-top:14px; }}
.foot {{ color:#8b949e; font-size:24px; margin-top:34px; border-top:1px solid #2a313c;
  padding-top:18px; }}
</style></head><body>
<div class="bar"></div>
<div class="pad">
  <div class="kicker">{kicker}</div>
  <div class="title">{title}</div>
  <div class="big">{big}</div>
  {minors_html}
  <div class="sub">{sub}</div>
  <div class="foot">🚲 Crash Atlas · open data · counts, not rates · every number sourced</div>
</div>
</body></html>"""


def render(html: str, out: Path) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
        tmp = f.name
    r = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--window-size=1200,630",
         "--hide-scrollbars", f"--screenshot={out}", Path(tmp).as_uri()],
        capture_output=True, timeout=60)
    Path(tmp).unlink(missing_ok=True)
    return r.returncode == 0 and out.exists()


def main() -> None:
    data = json.loads((WEB / "data" / "city_stats.json").read_text())
    years = data["years"]
    y0, y1 = years[0], years[-1]

    # Generic site card
    total = sum(c["total"] for c in data["cities"])
    ok = render(card_html(
        "U.S. Cyclist & E-Bike Crash Data",
        "Every number sourced.<br>Every limit stated.",
        f"<b>{len(data['cities'])}</b> city data pages",
        f"Federal crash data {y0}–{y1} · built by a high school e-bike rider in NJ"),
        WEB / "card.png")
    print(("ok  " if ok else "FAIL") + " site card")

    done = 0
    only = set(sys.argv[1:])
    for c in data["cities"]:
        if only and c["slug"] not in only:
            continue
        n = c["total"]
        big = (f"<b>{n}</b> cyclist fatalit{'y' if n == 1 else 'ies'} recorded"
               if n else "<b>0</b> recorded cyclist fatalities")
        minors = (f"{c['minors']} were minors (under 18)" if c["minors"] else "")
        html = card_html(
            "Cyclist Safety Data", f"{c['city']}, {c['state_abbr']}",
            big, f"NHTSA federal crash data, {y0}–{y1} · fatal motor-vehicle crashes only",
            minors)
        out = WEB / "cities" / c["slug"] / "card.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        if render(html, out):
            done += 1
        else:
            print("FAIL", c["slug"])
    print(f"rendered {done} city cards")


if __name__ == "__main__":
    main()
