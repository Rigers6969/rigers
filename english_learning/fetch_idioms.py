"""Fetches real English idioms + their meanings from Wiktionary
(en.wiktionary.org), via the same public MediaWiki action API this repo
already uses for Wikimedia Commons (see shotsource/sources/wikimedia.py) -
free, no key, CC-BY-SA licensed content.

Category:English_idioms (en.wiktionary.org/wiki/Category:English_idioms)
holds 10,000+ real idiom entries - this pages through it and pulls a
plain-text summary for each idiom via the API's own extract feature
(explaintext strips wikitext markup server-side, so this doesn't need to
parse MediaWiki syntax by hand).
"""
from __future__ import annotations

from typing import Callable, Optional

import requests

API_URL = "https://en.wiktionary.org/w/api.php"
ProgressCB = Callable[[str], None]


def _list_idiom_titles(limit: int) -> list[str]:
    titles: list[str] = []
    cmcontinue = None
    while len(titles) < limit:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": "Category:English_idioms",
            "cmlimit": min(50, limit - len(titles)),
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        resp = requests.get(API_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        members = (data.get("query") or {}).get("categorymembers", [])
        titles.extend(m["title"] for m in members if m.get("ns") == 0)
        cmcontinue = (data.get("continue") or {}).get("cmcontinue")
        if not cmcontinue or not members:
            break
    return titles[:limit]


def _fetch_extract(title: str) -> str:
    resp = requests.get(API_URL, params={
        "action": "query",
        "prop": "extracts",
        "exintro": 1,
        "explaintext": 1,
        "titles": title,
        "format": "json",
    }, timeout=15)
    resp.raise_for_status()
    pages = ((resp.json().get("query") or {}).get("pages")) or {}
    for page in pages.values():
        extract = (page.get("extract") or "").strip()
        if extract:
            return extract
    return ""


def fetch_idioms(limit: int = 80, progress: Optional[ProgressCB] = None) -> list[dict]:
    """Returns [{"phrase": "...", "meaning": "..."}, ...]. An idiom whose
    extract comes back empty (a stub page, or the API hiccups on that one
    title) is skipped rather than shown blank in the PDF."""
    if progress:
        progress("Listing idioms from Wiktionary...")
    titles = _list_idiom_titles(limit)

    results = []
    for i, title in enumerate(titles, start=1):
        if progress:
            progress(f"Idiom {i}/{len(titles)}: {title}")
        extract = _fetch_extract(title)
        if extract:
            results.append({"phrase": title, "meaning": extract})
    return results
