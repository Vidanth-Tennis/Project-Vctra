"""
aita_source.py - reads rankings straight from AITA's own site (aitatennis.com).

Written without being able to open the site, so it is deliberately flexible and
careful: it guesses the columns from the content of each cell, and update_rankings.py
only trusts the result if it has a clear list date and looks complete.
Anything odd -> returns None and buzzato is used instead.
"""
import datetime
import re

from common import MONTHS, TableRowParser, fetch, page_text

AITA_URLS = {
    "Boys U-12": "https://www.aitatennis.com/rankings?gender=male&cat=BU-12",
    "Boys U-14": "https://www.aitatennis.com/rankings?gender=male&cat=BU-14",
    "Boys U-16": "https://www.aitatennis.com/rankings?gender=male&cat=BU-16",
    "Boys U-18": "https://www.aitatennis.com/rankings?gender=male&cat=BU-18",
    "Girls U-12": "https://www.aitatennis.com/rankings?gender=female&cat=GU-12",
    "Girls U-14": "https://www.aitatennis.com/rankings?gender=female&cat=GU-14",
    "Girls U-16": "https://www.aitatennis.com/rankings?gender=female&cat=GU-16",
    "Girls U-18": "https://www.aitatennis.com/rankings?gender=female&cat=GU-18",
}

MON_RE = "|".join(MONTHS)
DATE_PATTERNS = [
    # 12th October, 2026 / 12 October 2026 / 12 Oct 2026
    (re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9}),?\s+(\d{4})"), "dmy_name"),
    # 12/10/2026, 12-10-2026, 12.10.2026
    (re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})"), "dmy_num"),
    # 2026-10-12
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "ymd"),
]
KEYWORD = r"(?:as\s+on|as\s+of|dated|ranking\s+date|rankings?\s+(?:for|of)|updated(?:\s+on)?|week\s+of|effective)"


def _month(name):
    for full, n in MONTHS.items():
        if full.lower().startswith(name.lower()[:3]):
            return n
    return None


def find_list_date(text):
    """Finds a date written right after a keyword like 'as on' / 'updated'.
    Returns (y, m, d) or None. Never guesses from unrelated dates on the page."""
    today = datetime.date.today()
    best = None
    for m in re.finditer(KEYWORD + r"[:\s\-]*(.{0,30})", text, re.I):
        chunk = m.group(1)
        for pat, kind in DATE_PATTERNS:
            d = pat.search(chunk)
            if not d:
                continue
            try:
                if kind == "dmy_name":
                    mon = _month(d.group(2))
                    key = (int(d.group(3)), mon, int(d.group(1)))
                elif kind == "dmy_num":
                    key = (int(d.group(3)), int(d.group(2)), int(d.group(1)))
                else:
                    key = (int(d.group(1)), int(d.group(2)), int(d.group(3)))
                datetime.date(*key)
            except (TypeError, ValueError):
                continue
            if key <= tuple((today + datetime.timedelta(days=1)).timetuple()[:3]):
                if best is None or key > best:
                    best = key
            break
    return best


def format_date(key):
    y, m, d = key
    suffix = "th" if 11 <= d <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")
    month = [k for k, v in MONTHS.items() if v == m][0]
    return f"{d}{suffix} {month}, {y}"


def _table_rows(html):
    p = TableRowParser()
    p.feed(html)
    return p.rows


def parse_aita_table(html):
    """Guess each column from what is in it. Returns rows like the buzzato ones:
    [rank, NAME, aitaId, STATE, points]"""
    rows = []
    for cells in _table_rows(html):
        if len(cells) < 4:
            continue
        cells = [c.strip() for c in cells]
        if not cells[0].isdigit():
            continue
        rank = int(cells[0])
        aita_id = next((c for c in cells[1:] if re.fullmatch(r"\d{5,7}", c)), None)
        state = next((c for c in cells[1:] if re.fullmatch(r"[A-Z]{2,3}", c)), None)
        name_candidates = [c for c in cells[1:] if re.search(r"[A-Za-z]{2}", c)
                           and not re.fullmatch(r"[A-Z]{2,3}", c)]
        name = max(name_candidates, key=len) if name_candidates else None
        points = None
        for c in reversed(cells[1:]):
            try:
                points = float(c.replace(",", ""))
                break
            except ValueError:
                continue
        if not (aita_id and state and name and points is not None):
            continue
        if aita_id == cells[0] or points == float(aita_id):
            continue
        rows.append([rank, name, aita_id, state, points])
    rows.sort(key=lambda r: r[0])
    return rows


def fetch_aita_category(cat):
    """Returns (rows, date_key) or None if anything looks off."""
    url = AITA_URLS.get(cat)
    if not url:
        return None
    html = fetch(url)
    rows = parse_aita_table(html)
    date = find_list_date(page_text(html))
    print(f"AITA {cat}: {len(rows)} rows, list date: {date}")
    if len(rows) < 50:
        print(f"AITA {cat}: page starts with: {page_text(html)[:200]}")
        return None
    return rows, date
