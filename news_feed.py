"""Pulls real financial headlines from public RSS feeds and caches them.

This is the "Google News" model, not scraping: each item is a headline +
a short snippet the publisher already put in their own feed for exactly
this purpose, plus a link back to the original article on the real
source site. Nothing here reproduces a full article - clicking through
to read the whole thing always happens on the publisher's own site.

Self-updating without any extra infrastructure (cron, Celery, etc.): a
TTL cache refetches the feeds the first time a request comes in after
the cache goes stale, so the page is always showing recent headlines
without the caller having to think about scheduling.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from html import unescape
from typing import Optional

import feedparser

logger = logging.getLogger("news_feed")

CACHE_TTL_SECONDS = 10 * 60  # 10 minutes - frequent enough to feel "live",
                              # not so frequent it hammers publishers' feeds.

# Real RSS feed URLs, confirmed via web search (2026) - each of these is
# the publisher's own official feed, meant to be syndicated. Only feeds
# whose exact URL could be confirmed are listed here; Investing.com and
# MarketWatch publish RSS too but their current feed URLs weren't pinned
# down with confidence, so they're left out rather than guessed - add
# them here once you have the real URL from
# https://www.investing.com/webmaster-tools/rss (pick a feed there, it
# gives you the exact link) or MarketWatch's own RSS page.
FEED_SOURCES = [
    {"name": "CNBC - US Top News", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html"},
    {"name": "CNBC - Finance", "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html"},
    {"name": "Yahoo Finance", "url": "https://finance.yahoo.com/news/rssindex"},
]


@dataclass
class NewsItem:
    title: str
    snippet: str
    link: str
    source: str
    published: str  # ISO 8601 if the feed gave a real date, else ""
    published_ts: float  # for sorting; 0 if unknown
    image_url: Optional[str] = None


def _clean_text(raw: str, limit: int = 280) -> str:
    """Feed summaries are often HTML fragments (bold tags, entities,
    trailing '<a href=...>Read more</a>' links) - strip that down to
    plain text so the frontend can render it as a snippet safely."""
    import re

    text = unescape(re.sub(r"<[^>]+>", " ", raw or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "..."
    return text


def _extract_image(entry) -> Optional[str]:
    media = getattr(entry, "media_content", None) or getattr(entry, "media_thumbnail", None)
    if media:
        url = media[0].get("url")
        if url:
            return url
    for link in getattr(entry, "links", []) or []:
        if str(link.get("type", "")).startswith("image/"):
            return link.get("href")
    return None


def _parse_feed(name: str, url: str) -> list[NewsItem]:
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        logger.warning("feed %s (%s) failed to parse: %s", name, url, parsed.get("bozo_exception"))
        return []

    items = []
    for entry in parsed.entries[:30]:
        title = _clean_text(getattr(entry, "title", ""), limit=200)
        link = getattr(entry, "link", "")
        if not title or not link:
            continue
        summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
        published_ts = 0.0
        published_iso = ""
        parsed_time = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        if parsed_time:
            published_ts = time.mktime(parsed_time)
            published_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", parsed_time)
        items.append(NewsItem(
            title=title,
            snippet=_clean_text(summary),
            link=link,
            source=name,
            published=published_iso,
            published_ts=published_ts,
            image_url=_extract_image(entry),
        ))
    return items


class NewsCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._items: list[NewsItem] = []
        self._fetched_at: float = 0.0
        self._errors: list[str] = []

    def get(self, force: bool = False) -> tuple[list[NewsItem], list[str], float]:
        with self._lock:
            stale = force or (time.time() - self._fetched_at) > CACHE_TTL_SECONDS
            if stale:
                self._refresh_locked()
            return list(self._items), list(self._errors), self._fetched_at

    def _refresh_locked(self) -> None:
        all_items: list[NewsItem] = []
        errors: list[str] = []
        seen_titles: set[str] = set()

        for feed in FEED_SOURCES:
            try:
                items = _parse_feed(feed["name"], feed["url"])
                for item in items:
                    key = item.title.lower().strip()
                    if key in seen_titles:
                        continue
                    seen_titles.add(key)
                    all_items.append(item)
            except Exception as exc:
                errors.append(f"{feed['name']}: {exc}")
                logger.warning("feed %s failed: %s", feed["name"], exc)

        all_items.sort(key=lambda i: i.published_ts, reverse=True)
        self._items = all_items
        self._errors = errors
        self._fetched_at = time.time()


_cache = NewsCache()


def get_headlines(force_refresh: bool = False) -> dict:
    items, errors, fetched_at = _cache.get(force=force_refresh)
    return {
        "items": [
            {
                "title": i.title,
                "snippet": i.snippet,
                "link": i.link,
                "source": i.source,
                "published": i.published,
                "image_url": i.image_url,
            }
            for i in items
        ],
        "errors": errors,
        "fetched_at": fetched_at,
        "sources": [f["name"] for f in FEED_SOURCES],
    }
