# Making this actually automatic

You asked for a Hoboken-style scenario — a 15-year-old killed on an e-bike
today should show up on the map, not in three years when FARS publishes its
next annual file. That now works (see the "Recent reports" tab), but there's
an honest gap between "the pipeline works when I run it" and "this refreshes
itself with nobody at the keyboard." This file is about closing that gap.

## What does NOT make this automatic

**Tools available inside this chat session (e.g. scheduling a recurring
prompt) are not a fit for an always-on public dashboard.** They are
session-bound, capped at 7 days, and only fire while a session is idle and
open. A real public site needs something that runs whether or not anyone is
chatting with an AI at the time. Don't mistake "I can schedule this in our
conversation" for "this is now live infrastructure" -- it isn't.

## What does

**A scheduled GitHub Actions workflow**, already written and committed at
`.github/workflows/refresh-news.yml`. It runs `etl/news/transform_news.py`
every 6 hours and commits the updated `web/data/news_*.json` files. Because
the dashboard is a static site that already reads those files directly, a
new commit *is* the deploy -- if `web/` is hosted on Vercel/Cloudflare
Pages/GitHub Pages with auto-deploy-on-push, a new crash report goes from
"GDELT indexed the article" to "live on your public map" with no manual
step, typically within the 6-hour window.

**This workflow is written but not running.** It only executes once this
project exists as a real GitHub repository with Actions enabled. That means:

1. Creating a GitHub repo (public, since Actions minutes are free there)
2. Pushing this code to it
3. Confirming the Action runs successfully at least once

Steps 1-2 are exactly the kind of "visible to others / shared state" action
I don't take without you explicitly saying so -- creating a public repo and
pushing your project to it is a real, visible action with consequences (it's
public, it's discoverable, it represents you). Tell me to go ahead and I will
set this up; I won't do it unannounced.

## What's still manual, and stays manual

- **NEISS** (the injury-estimate tab) cannot be scheduled the same way.
  CPSC's server blocks scripted requests entirely (see DATA_SOURCES.md) --
  only a real browser session gets through. NEISS also only updates once a
  year, so this is a low-cost manual step, not a gap that undermines the
  "automatic" goal -- the part that actually needs to be fast (new crashes)
  already is.
- **FARS** could be added to the same scheduled workflow (it's fully
  scriptable, like news), but it only updates annually too, so scheduling it
  more than a few times a year buys nothing. Not included in the workflow
  above for that reason -- rerun `etl/fars/transform_fars.py <year>` by hand
  when NHTSA publishes a new year.

## The honest residual risk, even once this is running

The news pipeline is heuristic (keyword/pattern matching over article text),
not a human reading every report, and not an LLM either (no API key is
wired in for this v1 -- see "Possible upgrade" below). In testing this
session it correctly caught a real local-TV story about a 14-year-old's
e-bike death in Clay County, FL, and a same-week story about a child fatality
in Omaha -- but it also produced false-positive location matches along the
way (a doctor's credential "R. Waterman, MD" misread as Maryland; a
Title-Case headline fragment "Promise, MO" misread as a town) that we had to
specifically catch and block. We added validation for the cases we found.
**There will be classes of error we haven't found yet.** This is why every
report carries a "corroborated / single-source" badge and a source link, and
why the system is built to drop a report rather than guess when it isn't
confident -- but treat the news tab as a lead to verify, not a verified feed,
even after automation is switched on.

**Possible upgrade, if you want better extraction later:** swap the
regex-based extraction in `etl/news/extract.py` for an LLM call (e.g. the
Claude API) per candidate article, which would handle location/age/device
extraction far more reliably than pattern matching. That requires an API key
and has a small per-article cost, so it's a deliberate tradeoff to make later,
not a default for a free v1.
