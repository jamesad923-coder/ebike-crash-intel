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

**This is live, not theoretical** -- the repo is public at
`github.com/jamesad923-coder/ebike-crash-intel`, hosted on GitHub Pages,
and three scheduled GitHub Actions workflows run unattended:

- **`refresh-news.yml`** -- every 6 hours, runs `etl/news/transform_news.py`
  and commits updated `web/data/news_*.json`. This is the one that matters
  for "show it within hours, not years."
- **`refresh-risk.yml`** -- weekly (Mondays), rebuilds the Risk & Prevention
  layer. As a side effect this also re-fetches FARS and CRSS for whatever
  years are passed to it, so FARS/CRSS effectively get refreshed weekly too,
  even though there's no separate `refresh-fars.yml` -- one less workflow to
  maintain, same result.
- **`refresh-dc-pilot.yml`** -- weekly (Mondays), rebuilds the DC ward
  crash summary and Capital Bikeshare e-bike trip context.
- **`deploy-pages.yml`** -- fires after any of the above (via
  `workflow_run`, since GitHub deliberately doesn't let a bot's own commit
  trigger other workflows via `push` -- this took a real fix to discover
  and wire up, see git history) and republishes the live site. A new crash
  report goes from "GDELT indexed the article" to "live on the public map"
  with nobody touching a keyboard, typically within the 6-hour window.

**A real gap observed in production, not hypothetical:** GitHub's own cron
scheduler is not 100% reliable -- one scheduled news-refresh slot (00:17 UTC
on 2026-06-22) never fired at all, with no error, no failed run, just
nothing in the run history. This seems to coincide with heavy push activity
on the repo around that time (many commits, each triggering its own deploy
run) possibly contending for scheduler capacity. Recovered by triggering the
workflow manually. Worth knowing: "scheduled" means "GitHub will usually run
this close to on time," not "guaranteed."

## What's still manual, and stays manual

- **NEISS** (the injury-estimate tab) cannot be scheduled the same way.
  CPSC's server blocks scripted requests entirely (see DATA_SOURCES.md) --
  only a real browser session gets through. NEISS also only updates once a
  year, so this is a low-cost manual step, not a gap that undermines the
  "automatic" goal -- the part that actually needs to be fast (new crashes)
  already is.

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
