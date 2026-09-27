"""Signal for topic invention: what's actually getting views right now
in this channel's niche, so Ollama isn't just guessing a topic blind.
Feeds into producer.py's generate_topic_idea() as extra context, the
same way video_reviewer.py's "lessons" do - just sourced from outside
the app instead of from your own past videos.

Uses the YouTube Data API's search.list, with the same YOUTUBE_API_KEY
already configured for the Dashboard's stats (see analytics.py) - no
extra credentials needed. This is fully automatic (you just give it a
few niche keywords, not specific channels to track), but it costs real
quota: 100 units per keyword search, out of the project's shared
10,000/day budget (also spent by YouTube uploads at 1,600 units each -
see youtube_publisher.py) - so this should run sparingly (a handful of
times a day, not once per video).

order=viewCount + publishedAfter together approximate "trending": a
plain view-count sort would surface old viral videos forever, so
restricting to the last N days turns it into "highest-viewed among
what's recent" - the closest proxy to "hot right now" the search API
offers without a second, more expensive call.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

RECENT_DAYS = 14
MAX_RESULTS_PER_KEYWORD = 8
MAX_TITLES_TOTAL = 15


def _read_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {}


def _api_key() -> str:
    return str(_read_config().get("YOUTUBE_API_KEY", "")).strip()


def load_search_keywords(channel_name: str) -> list[str]:
    """The niche search keywords configured for `channel_name`, or []
    if none are set up yet."""
    config = _read_config()
    for entry in config.get("CHANNELS", []) or []:
        if isinstance(entry, dict) and entry.get("name") == channel_name:
            keywords = entry.get("SEARCH_KEYWORDS", [])
            return [str(k).strip() for k in keywords if str(k).strip()] if isinstance(keywords, list) else []
    return []


def load_all_scout_config() -> list[dict]:
    """Every channel's name + search keywords, for the Trend Scout
    panel to display and edit - includes channels that don't have
    Dashboard stats set up yet, since this only needs the API key."""
    config = _read_config()
    out = []
    for entry in config.get("CHANNELS", []) or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        keywords = entry.get("SEARCH_KEYWORDS", [])
        out.append({
            "name": name,
            "search_keywords": [str(k).strip() for k in keywords if str(k).strip()] if isinstance(keywords, list) else [],
        })
    return out


def save_search_keywords(channel_name: str, keywords: list[str]) -> None:
    """Writes `keywords` for `channel_name` into config.json, creating a
    CHANNELS entry for it if one doesn't exist yet (a channel can use
    Trend Scout without having Dashboard stats set up)."""
    config = _read_config()
    channels = config.get("CHANNELS")
    if not isinstance(channels, list):
        channels = []
    cleaned = [str(k).strip() for k in keywords if str(k).strip()]

    for entry in channels:
        if isinstance(entry, dict) and entry.get("name") == channel_name:
            entry["SEARCH_KEYWORDS"] = cleaned
            break
    else:
        channels.append({"name": channel_name, "YOUTUBE_CHANNEL_ID": "", "SEARCH_KEYWORDS": cleaned})

    config["CHANNELS"] = channels
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")


def fetch_trending_titles(keyword: str, api_key: str, max_results: int = MAX_RESULTS_PER_KEYWORD) -> list[str]:
    """Titles of the highest-viewed videos matching `keyword` uploaded
    in the last RECENT_DAYS days - the search API's closest proxy for
    "trending" (see module docstring). Returns [] on any failure (bad
    key, quota exhausted, network down) rather than raising - this is
    optional context, never a reason to fail a video."""
    published_after = (datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        resp = requests.get(
            f"{YOUTUBE_API_BASE}/search",
            params={
                "part": "snippet", "q": keyword, "type": "video",
                "order": "viewCount", "publishedAfter": published_after,
                "maxResults": max_results, "key": api_key,
            },
            timeout=15,
        )
        data = resp.json()
    except Exception:
        return []

    if "error" in data:
        return []
    titles = [item.get("snippet", {}).get("title", "").strip() for item in data.get("items", [])]
    return [t for t in titles if t]


def build_scout_guidance(channel_name: str) -> str:
    """Recent high-viewed titles for this channel's configured niche
    keywords, formatted for the topic-idea prompt. Returns "" if no
    keywords or API key are configured, or nothing came back - the
    prompt template treats that as "no scouting data available"."""
    keywords = load_search_keywords(channel_name)
    api_key = _api_key()
    if not keywords or not api_key:
        return ""

    all_titles: list[str] = []
    for keyword in keywords:
        for title in fetch_trending_titles(keyword, api_key):
            if title not in all_titles:
                all_titles.append(title)
        if len(all_titles) >= MAX_TITLES_TOTAL:
            break

    if not all_titles:
        return ""

    lines = "\n".join(f"- {t}" for t in all_titles[:MAX_TITLES_TOTAL])
    return (
        f"Videos getting notably high views in the last {RECENT_DAYS} days for topics like this one "
        "(for a sense of what's currently resonating - don't copy them, but topics in a similar vein "
        "are worth considering):\n" + lines
    )
