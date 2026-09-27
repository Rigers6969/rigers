"""Flask blueprint for the Trend Scout panel - lets you set niche
search keywords per channel, and preview what YouTube's search API
currently returns for them, without touching the writer model or
spending any production job (though the preview call itself still
spends quota, same as a real run would)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from trend_scout import (
    _api_key,
    fetch_trending_titles,
    load_all_scout_config,
    save_search_keywords,
)

bp = Blueprint("scout_api", __name__)


@bp.route("/api/scout/config")
def get_scout_config():
    return jsonify({"channels": load_all_scout_config()})


@bp.route("/api/scout/config", methods=["POST"])
def set_scout_config():
    data = request.get_json(silent=True) or {}
    channel = str(data.get("channel", "")).strip()
    raw_keywords = data.get("search_keywords")

    if not channel:
        return jsonify({"error": "channel is required."}), 400
    if not isinstance(raw_keywords, list):
        return jsonify({"error": "search_keywords must be a list of strings."}), 400

    save_search_keywords(channel, [str(k) for k in raw_keywords])
    return jsonify({"ok": True})


@bp.route("/api/scout/preview")
def preview():
    keyword = str(request.args.get("keyword", "")).strip()
    if not keyword:
        return jsonify({"error": "keyword is required."}), 400

    api_key = _api_key()
    if not api_key:
        return jsonify({"error": "YOUTUBE_API_KEY is not set in config.json - Trend Scout needs it, same key used for Dashboard stats."}), 400

    titles = fetch_trending_titles(keyword, api_key)
    if not titles:
        return jsonify({"titles": [], "note": "No results - check the API key/quota, or nothing matched that keyword in the last 14 days."})
    return jsonify({"titles": titles})
