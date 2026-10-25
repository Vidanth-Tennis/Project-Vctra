#!/usr/bin/env python3
"""
update_rankings.py  (runs automatically via GitHub Actions)

1. Reads the 12 AITA ranking lists from buzzato.com
2. Writes data.json   (current rankings + the REAL date of the list)
3. Updates history.json (best rank ever seen per player, per category).
   A best rank only ever improves (gets lower), never gets worse.
"""
import json
import re
import sys
import time

from common import CATEGORIES, fetch, page_text, date_key, TableRowParser
import aita_source

NAME_ID_STATE_RE = re.compile(r'^(.*?)\s*\((\d+)\)\s*\(([A-Z]{2,3})\)')
LIST_DATE_RE = re.compile(r"as on\s+(\d{1,2}(?:st|nd|rd|th)\s+[A-Za-z]+,\s*\d{4})")


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


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def update_history(history, cat, rows, list_date):
    """history[cat][id] = [best_rank, date_it_was_first_seen]"""
    h = history.setdefault(cat, {})
    for rank, _name, aita_id, _state, _pts in rows:
        old = h.get(aita_id)
        if old is None or rank < old[0]:
            h[aita_id] = [rank, list_date]


def main():
    categories, dates, problems = {}, {}, []

    previous = load_json("data.json", {})
    prev_cats = previous.get("categories", {})
    prev_dates = previous.get("asOfByCat", {})
    sources = dict(previous.get("source", {}))

    for n, (cat, url) in enumerate(CATEGORIES.items()):
        if n:
            time.sleep(2)  # be gentle with the websites

        # ---- 1. buzzato ----
        b_rows, b_date = None, None
        try:
            html = fetch(url)
            rows = parse_category(html)
            if len(rows) >= 50:
                m = LIST_DATE_RE.search(page_text(html))
                b_rows, b_date = rows, (m.group(1) if m else None)
                print(f"{cat}: buzzato {len(rows)} rows, list date: {b_date}")
            else:
                print(f"DIAGNOSTIC {cat}: buzzato parsed {len(rows)} rows, page length={len(html)}, <tr> count={html.count('<tr')}")
                print(f"DIAGNOSTIC {cat}: buzzato page starts with: {page_text(html)[:300]}")
        except Exception as e:
            print(f"{cat}: buzzato failed ({e})")

        # ---- 2. AITA's own site ----
        a_rows, a_key = None, None
        if cat in aita_source.AITA_URLS:
            try:
                res = aita_source.fetch_aita_category(cat)
                if res:
                    a_rows, a_key = res
            except Exception as e:
                print(f"{cat}: AITA site failed ({e})")
            time.sleep(1)

        # ---- 3. pick the one with the newest list ----
        b_key = date_key(b_date) if b_date else None
        old_count = len(prev_cats.get(cat, [])) or (len(b_rows) if b_rows else 0)
        a_ok = (a_rows is not None and a_key is not None
                and len(a_rows) >= 0.8 * old_count)          # looks like a full list
        choice = None
        if a_ok and b_rows is not None:
            choice = "aita" if a_key > b_key else "buzzato"   # tie -> keep buzzato
        elif a_ok:
            choice = "aita"
        elif b_rows is not None:
            choice = "buzzato"

        if choice == "aita":
            categories[cat] = a_rows
            dates[cat] = aita_source.format_date(a_key)
        elif choice == "buzzato":
            categories[cat] = b_rows
            dates[cat] = b_date
        else:
            problems.append(f"{cat}: neither source gave a usable list. Keeping old data.")
            continue
        sources[cat] = choice
        print(f"{cat}: using {choice} (list dated {dates[cat]})")

    if not categories:
        print("Nothing parsed. Not touching any files.", file=sys.stderr)
        for p in problems:
            print(" -", p, file=sys.stderr)
        sys.exit(1)

    old = previous
    merged = dict(old.get("categories", {}))
    merged.update(categories)
    cat_dates = dict(old.get("asOfByCat", {}))
    for cat, d in dates.items():
        if d:
            cat_dates[cat] = d

    # headline date = the newest list date we know about
    known = [d for d in cat_dates.values() if d]
    as_of = max(known, key=date_key) if known else old.get("asOf", "")

    history = load_json("history.json", {})
    for cat, rows in categories.items():
        update_history(history, cat, rows, dates.get(cat) or as_of)

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump({"asOf": as_of, "asOfByCat": cat_dates, "source": sources, "categories": merged},
                  f, separators=(",", ":"))
    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, separators=(",", ":"), sort_keys=True)

    print(f"\nWrote data.json (list date: {as_of}) and history.json")
    for p in problems:
        print(" -", p, file=sys.stderr)


if __name__ == "__main__":
    main()
