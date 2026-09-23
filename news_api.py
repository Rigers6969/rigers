"""Flask blueprint for the self-updating financial news page: real
headlines (RSS, headline + snippet + link back to the source - see
news_feed.py) plus real YouTube videos on the same topics, embedded via
YouTube's own player (an iframe embed, not a download - the same thing
any legitimate news site does).
"""
from __future__ import annotations

import json
import os
import threading
import time
from html import unescape
from pathlib import Path

import requests
from flask import Blueprint, jsonify, request

import env_config  # noqa: F401  (loads .env before any os.environ read below)
from news_feed import get_headlines

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# Real, verified channel IDs (resolved via the YouTube Data API's own
# channels.list?forHandle=... against each outlet's official @handle -
# never hand-typed/guessed) for actual news organizations. Video search
# is restricted to just these channels rather than an open keyword
# search, which otherwise surfaces random finance YouTubers - including
# ones running paid-newsletter sales pitches dressed up as "analysis",
# not the news coverage this page is supposed to show.
NEWS_CHANNEL_IDS = {
    "CNBC": "UCvJJ_dzjViJCoLf5uKUTwoA",
    "Bloomberg Television": "UCIALMKvObZNtJ6AmdCLP7Lg",
    "Yahoo Finance": "UCEAZeUIeJs0IjQiqTCdVSIg",
    "Reuters": "UChqUTb7kYRX8-EiaN3XFrSQ",
}

_VIDEO_CACHE_TTL_SECONDS = 15 * 60
_video_cache_lock = threading.Lock()
_video_cache: dict[str, tuple[float, list[dict]]] = {}  # query -> (fetched_at, videos)

bp = Blueprint("news_api", __name__)


def _youtube_api_key() -> str:
    """Reuses the same YOUTUBE_API_KEY already used for the dashboard's
    stats card (config.json, falling back to the environment) - one key
    covers both, no separate setup needed."""
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
            value = str(data.get("YOUTUBE_API_KEY") or "").strip()
            if value:
                return value
        except (OSError, json.JSONDecodeError):
            pass
    return os.environ.get("YOUTUBE_API_KEY", "").strip()


@bp.route("/api/news/headlines")
def api_news_headlines():
    force = request.args.get("force") == "1"
    return jsonify(get_headlines(force_refresh=force))


def _search_channel(api_key: str, channel_id: str, query: str) -> list[dict]:
    resp = requests.get(
        f"{YOUTUBE_API_BASE}/search",
        params={
            "key": api_key,
            "q": query,
            "channelId": channel_id,
            "part": "snippet",
            "type": "video",
            "order": "date",
            "maxResults": 4,
        },
        timeout=10,
    )
    resp.raise_for_status()
    videos = []
    for item in resp.json().get("items", []):
        video_id = (item.get("id") or {}).get("videoId")
        snippet = item.get("snippet") or {}
        if not video_id:
            continue
        videos.append({
            "video_id": video_id,
            "title": unescape(snippet.get("title", "")),
            "channel": snippet.get("channelTitle", ""),
            "published": snippet.get("publishedAt", ""),
            "thumbnail": ((snippet.get("thumbnails") or {}).get("medium") or {}).get("url"),
        })
    return videos


@bp.route("/api/news/videos")
def api_news_videos():
    """Real YouTube videos matching a query, restricted to actual news
    organizations' channels (see NEWS_CHANNEL_IDS) and embedded via
    YouTube's own <iframe> player - each one plays on youtube.com's
    infrastructure, it's never downloaded or re-hosted.

    Cached per-query for 15 minutes: this is 4 API calls (one per
    channel) per cache miss, and YouTube's search.list quota cost adds
    up fast if every page load or auto-refresh repeated it."""
    api_key = _youtube_api_key()
    if not api_key:
        return jsonify({
            "videos": [],
            "error": "YOUTUBE_API_KEY not set in config.json or .env - the news text still works without it.",
        })

    query = request.args.get("q", "stock market news today").strip() or "stock market news today"

    with _video_cache_lock:
        cached = _video_cache.get(query)
        if cached and (time.time() - cached[0]) < _VIDEO_CACHE_TTL_SECONDS:
            return jsonify({"videos": cached[1], "query": query})

    all_videos: list[dict] = []
    errors: list[str] = []
    for channel_id in NEWS_CHANNEL_IDS.values():
        try:
            all_videos.extend(_search_channel(api_key, channel_id, query))
        except requests.RequestException as exc:
            errors.append(str(exc))

    all_videos.sort(key=lambda v: v["published"], reverse=True)
    all_videos = all_videos[:8]

    with _video_cache_lock:
        _video_cache[query] = (time.time(), all_videos)

    result = {"videos": all_videos, "query": query}
    if errors and not all_videos:
        result["error"] = f"YouTube search failed: {errors[0]}"
    return jsonify(result)
