#!/usr/bin/env python3
"""
update_rankings.py

Fetches current AITA junior ranking data (mirrored at buzzato.com, sourced
from AITA) for Boys/Girls U-14 and U-16, parses it, and writes data.json
in the same shape the website already expects.

Run manually:  python3 scripts/update_rankings.py
Run automatically: see .github/workflows/update-rankings.yml
"""
import json
import re
import sys
import datetime
import urllib.request
from html.parser import HTMLParser
CATEGORIES = {
    "Boys U-12": "https://buzzato.com/tennis/aita/rankings/show/Boys/U12",
    "Boys U-14": "https://buzzato.com/tennis/aita/rankings/show/Boys/U14",
    "Boys U-16": "https://buzzato.com/tennis/aita/rankings/show/Boys/U16",
    "Boys U-18": "https://buzzato.com/tennis/aita/rankings/show/Boys/U18",
    "Girls U-12": "https://buzzato.com/tennis/aita/rankings/show/Girls/U12",
    "Girls U-14": "https://buzzato.com/tennis/aita/rankings/show/Girls/U14",
    "Girls U-16": "https://buzzato.com/tennis/aita/rankings/show/Girls/U16",
    "Girls U-18": "https://buzzato.com/tennis/aita/rankings/show/Girls/U18",
    "Men Singles": "https://buzzato.com/tennis/aita/rankings/show/Men/Singles",
    "Men Doubles": "https://buzzato.com/tennis/aita/rankings/show/Men/Doubles",
    "Women Singles": "https://buzzato.com/tennis/aita/rankings/show/Women/Singles",
    "Women Doubles": "https://buzzato.com/tennis/aita/rankings/show/Women/Doubles",
}


USER_AGENT = "Mozilla/5.0 (compatible; AITA-Rank-Updater/1.0)"

NAME_ID_STATE_RE = re.compile(r'^(.*?)\s*\((\d+)\)\s*\(([A-Z]{2,3})\)')


class TableRowParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_category(html):
    parser = TableRowParser()
    parser.feed(html)
    rows = []
    for cells in parser.rows:
        if len(cells) < 3:
            continue
        rank_text, name_cell, points_text = cells[0], cells[1], cells[-1]
        if not rank_text.strip().isdigit():
            continue
        m = NAME_ID_STATE_RE.match(name_cell)
        if not m:
            continue
        name, aita_id, state = m.groups()
        try:
            points = float(points_text.strip())
        except ValueError:
            continue
        rows.append([int(rank_text), name.strip(), aita_id, state, points])
    rows.sort(key=lambda r: r[0])
    return rows


def main():
    categories = {}
    problems = []

    for cat_name, url in CATEGORIES.items():
        try:
            html = fetch(url)
            rows = parse_category(html)
            if len(rows) < 50:
                problems.append(f"{cat_name}: only parsed {len(rows)} rows, expected hundreds. Skipping update for this category.")
                continue
            categories[cat_name] = rows
            print(f"{cat_name}: parsed {len(rows)} rows OK")
        except Exception as e:
            problems.append(f"{cat_name}: fetch/parse failed ({e})")

    if not categories:
        print("No categories parsed successfully. Not touching data.json.", file=sys.stderr)
        for p in problems:
            print(" -", p, file=sys.stderr)
        sys.exit(1)

    try:
        with open("data.json", "r", encoding="utf-8") as f:
            old = json.load(f)
        old_categories = old.get("categories", {})
    except FileNotFoundError:
        old_categories = {}

    merged = dict(old_categories)
    merged.update(categories)

    today = datetime.date.today()
    day = today.day
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    as_of = today.strftime(f"{day}{suffix} %B, %Y")

    out = {"asOf": as_of, "categories": merged}
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))

    print(f"\nWrote data.json (asOf: {as_of})")
    if problems:
        print("\nSome categories were NOT updated this run:", file=sys.stderr)
        for p in problems:
            print(" -", p, file=sys.stderr)


if __name__ == "__main__":
    main()
