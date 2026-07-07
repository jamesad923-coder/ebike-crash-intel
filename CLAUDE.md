# CLAUDE.md — Crash Atlas

Read this before touching anything. It encodes two weeks of hard-won
lessons; ignoring it will re-break things that already broke once.

## What this is

**Crash Atlas** (repo: ebike-crash-intel) is a public, open-data U.S.
bicycle & e-bike crash intelligence platform — and an early-stage company.
Built and run by **James Adigun, a high school student in Wall, NJ, and an
e-bike rider** (his friends' injuries are the origin story — see /about/).
He is a minor: free offerings have zero friction; paid contracts will need
a parent co-signer (his dad handles the LLC when ready). Bootstrap path,
no VC. The business motion: free city data briefs/reports to city staff,
school districts, and advocates; the paid version later is deeper
screening/analysis. Contact: jamesad923@gmail.com.

Live site: https://jamesad923-coder.github.io/ebike-crash-intel/
(GitHub Pages, deploys from main via deploy-pages.yml). No custom domain
yet — buying one is a known TODO; BASE_URL constants in the generators
are the one-line change when it lands.

## The honesty rules (the brand — never weaken these)

1. **Counts, not rates** — no ridership denominator exists; never imply
   risk comparisons the data can't support. Every page says so.
2. **Limits stated up front** — federal data can't separate e-bikes from
   bicycles; FARS is fatal motor-vehicle crashes only; single-bike falls
   are invisible; only ~67% of FARS records are coded to a city. Every
   artifact carries a provenance block and a "what this can't say" section.
3. **No black boxes** — screening "supports engineering judgment, never
   replaces it." Never the word "prediction."
4. **Privacy, especially minors** — age bands only, never names, even when
   a news source prints them.
5. **Never guess** — no invented email addresses (bounces burn credibility),
   no guessed locations (demote to unlocated), no fuzzy matches presented
   as exact (Boston's fatal flag is a documented lower bound).
6. **Under-report rather than mis-tag.** When a pipeline isn't confident,
   it drops or demotes; it never invents.

## Architecture

Static site + committed data artifacts + stdlib-only Python ETL. No
database, no build step, no pip dependencies (keep it that way).

- `etl/` — one connector per source. Honesty limits documented in
  docstrings; downstream artifacts repeat them.
- `web/index.html` — the entire dashboard (vanilla JS + MapLibre 4.7.1).
- `web/data/*.json|geojson` — committed artifacts the site reads.
- `web/cities/{st}/{slug}/` — 341 static SEO city pages + card.png social
  cards. `web/reports/{slug}/` — print-first outreach reports (noindex).
  `web/risk-screening/{city}/` — HIN-style screening demos (4 pilots).
- `.github/workflows/` — refresh-news (6h, also drafts briefs + opens
  issues), refresh-risk / refresh-{dc,chicago,boston,nyc}-pilot (weekly),
  deploy-pages (on push to main + after bot workflows via workflow_run).
- `briefs/` — auto-drafted incident briefs (public, neutral tone, reviewer
  checklist at top). `outreach/` — **gitignored** private CRM (contacts.json,
  log.json, queue/); never commit it, the repo is public.

### Regeneration order (matters)

```bash
python3 etl/fars/transform_fars.py            # FARS 2019-2024 artifacts
python3 etl/cities/build_city_data.py         # per-city aggregates
python3 etl/cities/build_city_pages.py        # 341 pages + sitemap (keeps card.pngs)
python3 etl/cities/build_social_cards.py      # og:image cards (headless Chrome, ~7min)
python3 etl/risk/screen_city.py nyc|dc|chicago|boston   # screening page + json
python3 etl/reports/build_city_report.py [slugs...]     # print-first reports
python3 etl/outreach/prepare.py {slug}        # outreach kit (PDF+draft+contact)
cd web && python3 -m http.server 8765         # local serve (no build step)
```

## Hard-won gotchas — check before you "fix" something

- **MapLibre layer race**: `map.loaded()` is false during tile loading even
  after 'load' fired → layers silently never add ON THE LIVE SITE while
  localhost looks fine. Always use the `whenMapReady()` helper in
  web/index.html for addSource/addLayer. Verify map changes on the
  DEPLOYED site, not just localhost.
- **Popup CSS**: MapLibre's stylesheet loads after page CSS; unscoped
  `.maplibregl-popup-content` overrides LOSE. Scope under `#map`.
- **Python 3.9 local vs 3.11 CI**: `fromisoformat` can't parse bare "+00"
  offsets on 3.9 — normalize timestamps (this silently disabled Boston's
  date window once). Also FARS CSVs vary filename case across years
  (person.csv vs Person.CSV) — use the case-insensitive `_find()`.
- **Upstream data sources break constantly** (all happened in one week):
  Boston moved Socrata→CKAN and DROPPED its severity field; NYC retired
  its borough-boundary dataset id; NYPD ships 340 records at exactly (0,0)
  "Null Island"; CKAN's S3 redirect carries a ":443" port that breaks
  urllib SigV4. Validate coordinates against a city bbox; resolve CKAN
  URLs via the package API; never hardcode dataset tmp-filenames.
- **News location extraction lies**: page chrome is full of stray
  "City, ST" strings (a Milwaukee station's story got tagged Sacramento).
  extract.py anchors on the outlet's home state (DOMAIN_STATE) and demotes
  conflicts to unlocated. Briefs carry a mandatory reviewer checklist —
  never send one without doing it.
- **Deploys fail transiently**: verify via the Actions API after every
  push; retrigger with an empty commit if deploy-pages failed. Bot
  auto-refresh commits land constantly — `git pull --rebase` before push.
- **card.png preservation**: build_city_pages.py deletes only index.html
  files (NOT rmtree) so social cards survive page rebuilds. Keep it that way.
- **Gmail redirect interstitial**: raw URLs in outreach emails go through
  Google's "Redirect Notice" (github.io has no domain reputation). Drafts
  use HTML `<a>` anchors; a custom domain is the real fix.

## The outreach machine (etl/outreach/)

**The line we hold: the machine drafts, a human (James) sends. Never
automate the send.** Flow for "prep [city]": find_contacts.py (CivicPlus
directory walker, de-obfuscates their JS-split emails) or web search when
scrapers are blocked → verify the top hit against the source page → add
to outreach/contacts.json → prepare.py {slug} (report built on demand,
PDF via headless Chrome from the LIVE page, email drafted with a
city-specific data point) → Gmail draft via the Gmail MCP connector
(HTML body; connector can't attach — James attaches the PDF) → James
reviews + sends → `--mark-sent` starts the 7-day follow-up clock
(`--list` shows it). Beachheads: Jersey Shore towns (home turf —
Monmouth/Ocean County teen e-bike ordinance fights) + SoCal coastal
cities (Encinitas declared an e-bike emergency).

## Working with James

- Bias to action; build → **verify in a real browser** (chrome-devtools
  MCP) → commit with a thorough message explaining WHY → push to main
  (pushes deploy the live site) → confirm deploy green. He has explicitly
  authorized this loop; ask only for genuinely destructive/scope changes.
- He values honest pushback and gets real reasoning, not hedging. Explain
  technical things plainly — he's sharp, learning fast, and the founder;
  don't paper over trade-offs.
- UX roadmap and outreach state live in auto-memory
  (~/.claude/projects/.../memory/) — check MEMORY.md at session start.
- Commit style: imperative subject, body explains root cause and why the
  fix is right; `Co-Authored-By: Claude <model> <noreply@anthropic.com>`.
