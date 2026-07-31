# AITA Rank Finder

A simple site to look up AITA junior tennis rankings, compare players, and
search by rank number.

## Files
- `index.html` — the whole website (design + logic). You shouldn't need to edit this.
- `data.json` — all the ranking data. This is what changes when rankings update.
- `scripts/update_rankings.py` — the script that automatically fetches fresh
  rankings and rewrites `data.json`.
- `.github/workflows/update-rankings.yml` — tells GitHub to run that script
  automatically every Monday (and lets you trigger it manually anytime from
  the "Actions" tab on GitHub).

## How the automatic updates work
Every Monday, GitHub runs `update_rankings.py` on its own servers. If it
finds new ranking data, it saves the new `data.json` back to this repository.
Netlify is watching this repository, so it automatically re-publishes your
site with the new data — no action needed from you.

If a fetch fails for a category (e.g. the source site is briefly down or its
layout changed), that category is simply left unchanged rather than replaced
with broken data — check the "Actions" tab on GitHub to see the log if you
want to confirm everything ran cleanly.

## Manually forcing an update
Go to the "Actions" tab on GitHub → "Update AITA Rankings" → "Run workflow".
