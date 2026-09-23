"""Fetches real, advanced-level English grammar content for the in-app
"English" page - from two open, CC-BY-SA licensed Wikibooks, "English in
Use" and "English Grammar" (en.wikibooks.org), via the same public
MediaWiki action API pattern used elsewhere in this repo (see
shotsource/sources/wikimedia.py and english_learning/fetch_grammar.py).

Honest scope note: there is no free, openly-licensed source of official
CEFR-graded (B2/C1/C2) textbooks - the real ones (Cambridge, Oxford,
Cambridge English) are commercial and copyrighted, so this doesn't claim
to be one. What it pulls instead is the deepest, most advanced material
these two open books actually contain (subjunctive mood, sentence
structure, punctuation nuance, register and formal usage, and more) -
genuinely challenging content for upper-intermediate/advanced learners,
just not officially level-stamped.

Results are cached to disk (content/_grammar_guide/chapters.json) so the
page loads instantly; a "Refresh" button re-scrapes on demand.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

import requests

from producer import CONTENT_ROOT

API_URL = "https://en.wikibooks.org/w/api.php"
BOOKS = ["English in Use", "English Grammar"]
CACHE_PATH = CONTENT_ROOT / "_grammar_guide" / "chapters.json"
ProgressCB = Callable[[str], None]


def _list_chapter_titles(book_title: str, limit: int = 60) -> list[str]:
    resp = requests.get(API_URL, params={
        "action": "query",
        "list": "allpages",
        "apprefix": book_title,
        "apnamespace": 0,
        "aplimit": min(100, limit),
        "format": "json",
    }, timeout=15)
    resp.raise_for_status()
    pages = ((resp.json().get("query") or {}).get("allpages")) or []
    # Keep the book's own page and its "Book/Chapter" subpages; drop
    # anything that merely starts with the same words by coincidence.
    titles = [p["title"] for p in pages if p["title"] == book_title or p["title"].startswith(f"{book_title}/")]
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


def fetch_grammar_guide(progress: Optional[ProgressCB] = None) -> list[dict]:
    """Returns [{"book", "chapter", "text"}, ...] across both source
    books, skipping chapters with no real content (a stub page, or a
    title that resolves to nothing on that one request)."""
    results = []
    for book in BOOKS:
        if progress:
            progress(f'Listing chapters from "{book}"...')
        titles = _list_chapter_titles(book)
        for i, title in enumerate(titles, start=1):
            if progress:
                progress(f"{book} {i}/{len(titles)}: {title}")
            extract = _fetch_extract(title)
            if extract:
                chapter_name = title.split("/", 1)[1] if "/" in title else title
                results.append({"book": book, "chapter": chapter_name, "text": extract})
    return results


def refresh_cache(progress: Optional[ProgressCB] = None) -> list[dict]:
    chapters = fetch_grammar_guide(progress=progress)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps({"chapters": chapters}, indent=2), encoding="utf-8")
    return chapters


def load_cache() -> list[dict]:
    if not CACHE_PATH.exists():
        return []
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data.get("chapters", [])
