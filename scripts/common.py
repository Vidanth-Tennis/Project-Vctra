"""Shared helpers for the AITA scripts."""
import re
import urllib.request
from html.parser import HTMLParser

USER_AGENT = "Mozilla/5.0 (compatible; AITA-Rank-Updater/2.0; personal junior tennis project)"
BASE = "https://buzzato.com/tennis/aita"

CATEGORIES = {
    "Boys U-12": f"{BASE}/rankings/show/Boys/U12",
    "Boys U-14": f"{BASE}/rankings/show/Boys/U14",
    "Boys U-16": f"{BASE}/rankings/show/Boys/U16",
    "Boys U-18": f"{BASE}/rankings/show/Boys/U18",
    "Girls U-12": f"{BASE}/rankings/show/Girls/U12",
    "Girls U-14": f"{BASE}/rankings/show/Girls/U14",
    "Girls U-16": f"{BASE}/rankings/show/Girls/U16",
    "Girls U-18": f"{BASE}/rankings/show/Girls/U18",
    "Men Singles": f"{BASE}/rankings/show/Men/Singles",
    "Men Doubles": f"{BASE}/rankings/show/Men/Doubles",
    "Women Singles": f"{BASE}/rankings/show/Women/Singles",
    "Women Doubles": f"{BASE}/rankings/show/Women/Doubles",
}

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}
DATE_RE = r"\d{1,2}(?:st|nd|rd|th)\s+[A-Za-z]+,\s*\d{4}"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def date_key(text):
    """'5th October, 2026' -> (2026, 10, 5) so dates can be compared."""
    m = re.match(r"(\d{1,2})\w*\s+([A-Za-z]+),\s*(\d{4})", text or "")
    if not m or m.group(2) not in MONTHS:
        return (0, 0, 0)
    return (int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))


class TextParser(HTMLParser):
    """Turns a page into plain text (tags removed, scripts/styles skipped)."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self):
        return " ".join(" ".join(self.parts).split())


def page_text(html):
    p = TextParser()
    p.feed(html)
    return p.text()


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
