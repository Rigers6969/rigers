"""Flask blueprint for the self-updating financial news page: real
headlines (RSS, headline + snippet + link back to the source - see
news_feed.py) plus real YouTube videos on the same topics, embedded via
YouTube's own player (an iframe embed, not a download - the same thing
any legitimate news site does).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from flask import Blueprint, jsonify, request

import env_config  # noqa: F401  (loads .env before any os.environ read below)
from news_feed import get_headlines

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

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


@bp.route("/api/news/videos")
def api_news_videos():
    """Real YouTube videos matching a query, for embedding via YouTube's
    own <iframe> player - each one plays on youtube.com's infrastructure,
    it's never downloaded or re-hosted."""
    api_key = _youtube_api_key()
    if not api_key:
        return jsonify({
            "videos": [],
            "error": "YOUTUBE_API_KEY not set in config.json or .env - the news text still works without it.",
        })

    query = request.args.get("q", "stock market news today").strip() or "stock market news today"
    try:
        resp = requests.get(
            f"{YOUTUBE_API_BASE}/search",
            params={
                "key": api_key,
                "q": query,
                "part": "snippet",
                "type": "video",
                "order": "date",
                "relevanceLanguage": "en",
                "maxResults": 6,
                "safeSearch": "strict",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        return jsonify({"videos": [], "error": f"YouTube search failed: {exc}"})

    videos = []
    for item in data.get("items", []):
        video_id = (item.get("id") or {}).get("videoId")
        snippet = item.get("snippet") or {}
        if not video_id:
            continue
        videos.append({
            "video_id": video_id,
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "published": snippet.get("publishedAt", ""),
            "thumbnail": ((snippet.get("thumbnails") or {}).get("medium") or {}).get("url"),
        })

    return jsonify({"videos": videos, "query": query})
