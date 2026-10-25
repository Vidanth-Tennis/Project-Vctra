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


def _num(text):
    try:
        return float(text.replace(",", "").strip())
    except ValueError:
        return None


def parse_category(html):
    """Works out the columns from what is in each cell, so a small layout
    change on the website doesn't break it."""
    parser = TableRowParser()
    parser.feed(html)
    rows = []
    for cells in parser.rows:
        cells = [c.strip() for c in cells]
        if len(cells) < 3:
            continue
        m_rank = re.fullmatch(r"#?(\d{1,5})\.?", cells[0])
        if not m_rank:
            continue
        rest = cells[1:]
        joined = " ".join(rest)

        m_id = re.search(r"\((\d{5,7})\)", joined)
        aita_id, name = None, None
        if m_id:
            aita_id = m_id.group(1)
            name = joined[:m_id.start()]
        else:
            for c in rest:
                if re.fullmatch(r"\d{5,7}", c):
                    aita_id = c
                    break
            alpha = [c for c in rest if re.search(r"[A-Za-z]{2}", c)
                     and not re.fullmatch(r"\(?[A-Z]{2,3}\)?", c)]
            name = max(alpha, key=len) if alpha else None
        m_state = re.search(r"\(([A-Z]{2,3})\)", joined)
        state = m_state.group(1) if m_state else next(
            (c for c in rest if re.fullmatch(r"[A-Z]{2,3}", c)), None)

        points = None
        for c in reversed(rest):
            if aita_id and c == aita_id:
                continue
            v = _num(c)
            if v is not None:
                points = v
                break
        if not (aita_id and state and name and points is not None):
            continue
        name = re.sub(r"[\[\]]", "", name).strip(" -|")
        if not name:
            continue
        rows.append([int(m_rank.group(1)), name, aita_id, state, points])
    rows.sort(key=lambda r: r[0])
    return rows


def sample_rows(html, n=3):
    """For the log: shows what the table rows really look like."""
    parser = TableRowParser()
    parser.feed(html)
    shown = [r for r in parser.rows if len(r) >= 3][:n + 2]
    return shown[:n + 2]


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

    WATCH = "445026"   # prints this player's rank from each source, to help debugging

    def watch(label, rows):
        hit = next((r for r in rows if r[2] == WATCH), None)
        if hit:
            print(f"   {label}: player {WATCH} is #{hit[0]} with {hit[4]} points")

    for n, (cat, url) in enumerate(CATEGORIES.items()):
        if n:
            time.sleep(2)  # be gentle with the websites
        candidates = []   # (date_key, preference, source_name, rows, date_text)

        old_count = len(prev_cats.get(cat, []))
        need = max(50, int(0.8 * old_count))          # a complete list, not a partial page
        prev_key = date_key(prev_dates[cat]) if prev_dates.get(cat) else None

        # ---- buzzato ----
        try:
            html = fetch(url)
            rows = parse_category(html)
            m = LIST_DATE_RE.search(page_text(html))
            b_date = m.group(1) if m else None
            print(f"{cat}: buzzato {len(rows)} rows, list date: {b_date}")
            if len(rows) < 50:
                print(f"DIAGNOSTIC {cat}: buzzato page length={len(html)}, <tr> count={html.count('<tr')}")
                for r in sample_rows(html):
                    print(f"DIAGNOSTIC {cat}: sample row cells: {r}")
            else:
                watch("buzzato", rows)
                if len(rows) < need:
                    print(f"{cat}: buzzato list looks incomplete ({len(rows)} of ~{old_count}) - not trusting it")
                elif b_date:
                    candidates.append((date_key(b_date), 1, "buzzato", rows, b_date))
        except Exception as e:
            print(f"{cat}: buzzato failed ({e})")

        # ---- AITA's own site ----
        if cat in aita_source.AITA_URLS:
            try:
                res = aita_source.fetch_aita_category(cat)
                if res:
                    a_rows, a_key = res
                    watch("AITA", a_rows)
                    if a_key is None:
                        print(f"{cat}: AITA list has no clear date - not trusting it")
                    elif len(a_rows) < need:
                        print(f"{cat}: AITA list looks incomplete - not trusting it")
                    else:
                        candidates.append((a_key, 0, "aita", a_rows, aita_source.format_date(a_key)))
            except Exception as e:
                print(f"{cat}: AITA site failed ({e})")
            time.sleep(1)

        # ---- newest complete list wins (tie -> buzzato) ----
        if candidates:
            candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
            key, _pref, source, rows, date_text = candidates[0]
            if prev_key and key < prev_key:
                problems.append(f"{cat}: newest list ({date_text}) is OLDER than what we already have. Keeping old data.")
                continue
            categories[cat] = rows
            dates[cat] = date_text
            sources[cat] = source
            print(f"{cat}: using {source} (list dated {date_text})")
        else:
            problems.append(f"{cat}: no usable list from either source. Keeping old data.")

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
