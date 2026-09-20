"""Flask backend for the Wayne Factory web dashboard.

This serves a real HTML/CSS/JavaScript website (in web/) instead of a
Streamlit app - Streamlit's components render inside sandboxed iframes,
which blocks full-page canvas animation and other effects that need the
real page DOM. A plain backend + static frontend has none of those limits.

The backend's only job is to keep your API keys/tokens server-side. The
frontend calls GET /api/stats and never sees the credentials themselves.

Run with:
    python web_server.py
Then open http://localhost:5000

Configure credentials via environment variables (see analytics.py's
docstring for exactly how to obtain each one):
    YOUTUBE_CHANNEL_ID, YOUTUBE_API_KEY
    IG_USER_ID, IG_ACCESS_TOKEN
"""
from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from analytics import StatsFetchError, fetch_instagram_stats, fetch_youtube_stats

APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"

app = Flask(__name__, static_folder=None)


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(WEB_DIR, filename)


@app.route("/api/stats")
def api_stats():
    result: dict = {"youtube": None, "instagram": None, "errors": []}

    channel_id = os.environ.get("YOUTUBE_CHANNEL_ID")
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if channel_id and api_key:
        try:
            result["youtube"] = fetch_youtube_stats(channel_id, api_key)
        except Exception as exc:
            result["errors"].append(f"YouTube: {exc}")
    else:
        result["errors"].append("YouTube not configured: set YOUTUBE_CHANNEL_ID and YOUTUBE_API_KEY")

    ig_user_id = os.environ.get("IG_USER_ID")
    ig_token = os.environ.get("IG_ACCESS_TOKEN")
    if ig_user_id and ig_token:
        try:
            result["instagram"] = fetch_instagram_stats(ig_user_id, ig_token)
        except Exception as exc:
            result["errors"].append(f"Instagram: {exc}")
    else:
        result["errors"].append("Instagram not configured: set IG_USER_ID and IG_ACCESS_TOKEN")

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
