"""Fetches real grammar content from Wikibooks' "English in Use"
(en.wikibooks.org/wiki/English_in_Use) - a real, CC-BY-SA licensed
Wikibook covering grammar, punctuation, and formal usage, via the same
public MediaWiki action API family used elsewhere in this repo (see
shotsource/sources/wikimedia.py and fetch_idioms.py).

A Wikibook is a main page plus subpages (one per chapter) - this lists
the book's direct subpages and pulls a plain-text extract from each.
"""
from __future__ import annotations

from typing import Callable, Optional

import requests

API_URL = "https://en.wikibooks.org/w/api.php"
BOOK_TITLE = "English in Use"
ProgressCB = Callable[[str], None]


def _list_chapter_titles(limit: int) -> list[str]:
    resp = requests.get(API_URL, params={
        "action": "query",
        "list": "allpages",
        "apprefix": BOOK_TITLE,
        "apnamespace": 0,
        "aplimit": min(100, limit),
        "format": "json",
    }, timeout=15)
    resp.raise_for_status()
    pages = ((resp.json().get("query") or {}).get("allpages")) or []
    # Keep the book's own page and its "Book/Chapter" subpages; drop
    # anything that merely starts with the same words by coincidence.
    titles = [p["title"] for p in pages if p["title"] == BOOK_TITLE or p["title"].startswith(f"{BOOK_TITLE}/")]
    return titles[:limit]


def _fetch_extract(title: str) -> str:
    resp = requests.get(API_URL, params={
        "action": "query",
        "prop": "extracts",
        "explaintext": 1,
        "titles": title,
        "format": "json",
    }, timeout=20)
    resp.raise_for_status()
    pages = ((resp.json().get("query") or {}).get("pages")) or {}
    for page in pages.values():
        extract = (page.get("extract") or "").strip()
        if extract:
            return extract
    return ""


def fetch_grammar(limit: int = 20, progress: Optional[ProgressCB] = None) -> list[dict]:
    """Returns [{"chapter": "...", "text": "..."}, ...], one entry per
    chapter of the Wikibook that actually has content."""
    if progress:
        progress("Listing grammar chapters from Wikibooks...")
    titles = _list_chapter_titles(limit)

    results = []
    for i, title in enumerate(titles, start=1):
        if progress:
            progress(f"Grammar {i}/{len(titles)}: {title}")
        extract = _fetch_extract(title)
        if extract:
            chapter_name = title.split("/", 1)[1] if "/" in title else title
            results.append({"chapter": chapter_name, "text": extract})
    return results
