"""
One-time seeding of best-ever ranks from buzzato player profiles.

Why this exists
---------------
update_rankings.py can only record the best rank it has *seen* since the site
started watching (four lists so far), so "best ever" is wrong for most players.
Each buzzato player profile publishes the real best-ever rank per category,
with the date it was achieved, going back years. This script reads those and
merges them into history.json.

Safety
------
It never makes a best rank worse, and it refuses to write anything unless it
parsed a convincing share of the profiles it fetched. On a weak result it
prints the raw page text it saw and exits without touching history.json, so a
layout change can never silently poison the data.

Usage (via the workflow):
  mode=probe  -> fetch a handful of profiles, print what they contain, write nothing
  mode=seed   -> full run, merge into history.json
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, CATEGORIES, USER_AGENT, MONTHS, page_text  # noqa: E402

MODE = os.environ.get("MODE", "probe").strip().lower()
LIMIT = int(os.environ.get("LIMIT", "0") or 0)
DELAY = float(os.environ.get("DELAY", "1.0"))
PROBE_IDS = [i.strip() for i in os.environ.get("PROBE_IDS", "").split(",") if i.strip()]

# Category labels as they may appear on a profile page -> our data.json keys
CAT_PATTERNS = [
    (re.compile(r"\bBoys?\s*-?\s*U\s*-?\s*12\b", re.I), "Boys U-12"),
    (re.compile(r"\bBoys?\s*-?\s*U\s*-?\s*14\b", re.I), "Boys U-14"),
    (re.compile(r"\bBoys?\s*-?\s*U\s*-?\s*16\b", re.I), "Boys U-16"),
    (re.compile(r"\bBoys?\s*-?\s*U\s*-?\s*18\b", re.I), "Boys U-18"),
    (re.compile(r"\bGirls?\s*-?\s*U\s*-?\s*12\b", re.I), "Girls U-12"),
    (re.compile(r"\bGirls?\s*-?\s*U\s*-?\s*14\b", re.I), "Girls U-14"),
    (re.compile(r"\bGirls?\s*-?\s*U\s*-?\s*16\b", re.I), "Girls U-16"),
    (re.compile(r"\bGirls?\s*-?\s*U\s*-?\s*18\b", re.I), "Girls U-18"),
    (re.compile(r"\bMen'?s?\s+Singles\b", re.I), "Men Singles"),
    (re.compile(r"\bMen'?s?\s+Doubles\b", re.I), "Men Doubles"),
    (re.compile(r"\bWomen'?s?\s+Singles\b", re.I), "Women Singles"),
    (re.compile(r"\bWomen'?s?\s+Doubles\b", re.I), "Women Doubles"),
]

DATE_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9}),?\s+(\d{4})", re.I)
MONTH_LOOKUP = {m.lower(): i for m, i in MONTHS.items()}
MONTH_LOOKUP.update({m.lower()[:3]: i for m, i in MONTHS.items()})


def norm_date(day, mon, year):
    """Return '12th October, 2026' style text, or None if the month is unknown."""
    key = mon.lower()
    if key not in MONTH_LOOKUP:
        return None
    full = [m for m, i in MONTHS.items() if i == MONTH_LOOKUP[key]][0]
    d = int(day)
    suffix = "th" if 11 <= d <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")
    return f"{d}{suffix} {full}, {year}"


def fetch(url, tries=3):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            last = e
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(2 * (attempt + 1))
    raise last


def profile_urls_from_lists():
    """Harvest exact profile links from the 12 ranking pages.

    This avoids guessing the name part of a profile URL: we use the links the
    site itself publishes.
    """
    href_re = re.compile(r'href=["\'](/tennis/aita/player/(\d+)/[^"\']*)["\']', re.I)
    urls = {}
    for cat, url in CATEGORIES.items():
        try:
            html = fetch(url)
        except Exception as e:  # noqa: BLE001
            print(f"  ! could not read list page for {cat}: {e}")
            continue
        found = 0
        for path, pid in href_re.findall(html):
            if pid not in urls:
                urls[pid] = "https://buzzato.com" + path
                found += 1
        print(f"  {cat}: {found} new profile links")
        time.sleep(DELAY)
    return urls


def rank_candidates(text):
    """Plausible ranking positions in a piece of text, as (rank, position).

    Skips anything that looks like a year, an ordinal day (3rd, 14th) or a
    points total with a decimal point.
    """
    out = []
    for m in re.finditer(r"\b(\d{1,5})(st|nd|rd|th)?\b(\.\d+)?", text):
        if m.group(2) or m.group(3):
            continue                      # 14th / 161.75
        n = int(m.group(1))
        if 1900 <= n <= 2100:
            continue                      # a year
        if 1 <= n <= 99999:
            out.append((n, m.start()))
    return out


def find_best_section(text):
    """Return the slice of page text most likely to hold the best-ever figures."""
    low = text.lower()
    for kw in ("best ever", "best-ever", "career best", "highest rank", "best rank", "best"):
        i = low.find(kw)
        if i != -1:
            return text[i:i + 1200]
    return ""


def parse_bests(text):
    """Pull {category: (rank, date)} out of a profile page's text.

    Looks for a category label followed closely by a rank number and a date.
    Anything it cannot read confidently is skipped rather than guessed.
    """
    section = find_best_section(text)
    if not section:
        return {}
    out = {}
    for pat, cat in CAT_PATTERNS:
        for m in pat.finditer(section):
            window = section[m.end():m.end() + 160]
            date_m = DATE_RE.search(window)
            if not date_m:
                continue
            # take the date out before hunting for the rank, so the day or the
            # year can never be mistaken for a ranking position
            # blank the date out but keep the length, so distances stay honest
            stripped = (window[:date_m.start()]
                        + " " * (date_m.end() - date_m.start())
                        + window[date_m.end():])

            # The rank may sit just after the label ("Boys U-14  151") or just
            # before it ("151  Boys U-14"). Take whichever number sits closest
            # to the label, so a neighbouring row can't be picked up by mistake.
            after = rank_candidates(stripped)
            best_after = (after[0][0], after[0][1]) if after else None

            before_txt = DATE_RE.sub(
                lambda d: " " * len(d.group(0)),
                section[max(0, m.start() - 60):m.start()])
            before = rank_candidates(before_txt)
            best_before = (before[-1][0],
                           len(before_txt) - before[-1][1]) if before else None

            if best_after and best_before:
                rank = best_after[0] if best_after[1] <= best_before[1] else best_before[0]
            elif best_after:
                rank = best_after[0]
            elif best_before:
                rank = best_before[0]
            else:
                continue
            when = norm_date(*date_m.groups())
            if not when:
                continue
            prev = out.get(cat)
            if prev is None or rank < prev[0]:
                out[cat] = (rank, when)
            break
    return out


def main():
    data = json.load(open("data.json", encoding="utf-8"))
    cats = data["categories"]

    # every player we actually rank, and the categories they appear in
    players = {}
    for cat, rows in cats.items():
        for r in rows:
            pid = r[2]
            if pid:
                players.setdefault(pid, set()).add(cat)
    print(f"{len(players)} unique AITA numbers across {len(cats)} categories\n")

    print("Collecting profile links from the ranking pages...")
    urls = profile_urls_from_lists()
    print(f"\nGot profile links for {len(urls)} players "
          f"({len(set(urls) & set(players))} of ours)\n")

    targets = PROBE_IDS if PROBE_IDS else [p for p in players if p in urls]
    if MODE == "probe":
        targets = targets[:5]
    elif LIMIT:
        targets = targets[:LIMIT]

    # current rank per (player, category), used to sanity-check what we parse
    current = {}
    for cat, rows in cats.items():
        for r in rows:
            if r[2]:
                current[(r[2], cat)] = r[0]

    parsed, empty, failed, rejected = {}, [], 0, []
    samples = []
    for n, pid in enumerate(targets, 1):
        url = urls.get(pid) or f"{BASE}/player/{pid}/"
        try:
            text = page_text(fetch(url))
        except Exception as e:  # noqa: BLE001
            failed += 1
            if failed <= 5:
                print(f"  ! {pid}: {e}")
            time.sleep(DELAY)
            continue
        bests = parse_bests(text)
        # A best-ever rank can never be WORSE than the player's current rank.
        # Current ranks come from data.json, so this catches a misread page.
        for cat in list(bests):
            cur = current.get((pid, cat))
            if cur is not None and bests[cat][0] > cur:
                rejected.append((pid, cat, bests[cat][0], cur))
                del bests[cat]
        if bests:
            parsed[pid] = bests
        else:
            empty.append(pid)
        if len(samples) < 3:
            samples.append((pid, url, find_best_section(text)[:700] or text[:700]))
        if n % 250 == 0:
            print(f"  ...{n}/{len(targets)} read, {len(parsed)} with best-ever data")
        time.sleep(DELAY)

    attempted = len(parsed) + len(empty)
    rate = (len(parsed) / attempted) if attempted else 0
    print(f"\nRead {attempted} profiles, {len(parsed)} gave best-ever data "
          f"({rate:.0%}), {failed} failed to load")
    if rejected:
        print(f"{len(rejected)} entries rejected for being worse than the player's "
              f"current rank (a best-ever cannot be worse). First few:")
        for pid, cat, bad, cur in rejected[:5]:
            print(f"   {pid} {cat}: page said best {bad}, but current rank is {cur}")
        if len(rejected) > attempted * 0.25:
            print("ABORTING: too many impossible values, the page layout was probably "
                  "misread. history.json was NOT changed.")
            sys.exit(1)

    print("\n--- what the pages actually said (first 3) ---")
    for pid, url, snippet in samples:
        print(f"\n[{pid}] {url}\n{snippet}\n   -> parsed: {parsed.get(pid, {})}")
    print("--- end samples ---\n")

    if MODE == "probe":
        print("PROBE MODE: nothing written. Check the samples above.")
        return

    # safety gate: never write from a run that clearly misread the pages
    if attempted < 20 or rate < 0.6:
        print("ABORTING: too few profiles parsed cleanly, so history.json was NOT "
              "changed. The samples above show what the page looked like.")
        sys.exit(1)

    history = json.load(open("history.json", encoding="utf-8")) if os.path.exists("history.json") else {}
    improved = added = 0
    for pid, bests in parsed.items():
        for cat, (rank, when) in bests.items():
            if cat not in cats:
                continue
            h = history.setdefault(cat, {})
            cur = h.get(pid)
            if cur is None:
                h[pid] = [rank, when]
                added += 1
            elif rank < cur[0]:
                h[pid] = [rank, when]
                improved += 1

    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, separators=(",", ":"), sort_keys=True)
    print(f"history.json updated: {added} new best-ever entries, "
          f"{improved} existing bests corrected to a better rank")


if __name__ == "__main__":
    main()
