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

Configure credentials by copying config.example.json to config.json and
filling in your values (see analytics.py's docstring for exactly how to
obtain each one). Edit config.json in a plain text editor (Notepad is
fine) - this is deliberately simpler than environment variables, which
have to be retyped every terminal session and are easy to paste
incorrectly (a partial paste is silently accepted as a short, wrong
value - there's no error until the API rejects it). config.json is
gitignored, so your real credentials never get committed.

Environment variables (YOUTUBE_CHANNEL_ID, YOUTUBE_API_KEY, IG_USER_ID,
IG_ACCESS_TOKEN) still work too, as a fallback for anything not set in
config.json - useful for a real deployment, not needed for local use.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from analytics import StatsFetchError, fetch_instagram_stats, fetch_youtube_stats
from video_api import bp as video_bp

APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"
CONFIG_PATH = APP_DIR / "config.json"

app = Flask(__name__, static_folder=None)
app.register_blueprint(video_bp)


def load_config() -> dict:
    """Reads credentials from config.json if present, falling back to
    environment variables for any key it doesn't set. Values are stripped
    of surrounding whitespace - a trailing newline from a copy-paste into
    a text file is a common, silent source of "invalid" credentials."""
    file_config: dict = {}
    if CONFIG_PATH.exists():
        try:
            # utf-8-sig (not plain utf-8) strips a byte-order-mark if
            # present without erroring - Windows tools like PowerShell's
            # Set-Content or Notepad can write one, and plain utf-8 decoding
            # would raise UnicodeDecodeError on it (an exception type the
            # caller wasn't catching, which surfaced as an opaque HTML 500
            # error page instead of a JSON response - exactly what a user
            # hit). It's a no-op for a file that has no BOM.
            raw_text = CONFIG_PATH.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError) as exc:
            raise RuntimeError(f"config.json could not be read: {exc}") from exc
        try:
            file_config = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"config.json is not valid JSON: {exc}") from exc
        if not isinstance(file_config, dict):
            raise RuntimeError(
                "config.json must contain a JSON object like "
                '{"YOUTUBE_CHANNEL_ID": "...", ...} - '
                f"got a {type(file_config).__name__} instead"
            )

    def get(key: str) -> str:
        value = file_config.get(key) or os.environ.get(key, "")
        return value.strip() if isinstance(value, str) else value

    return {
        "YOUTUBE_CHANNEL_ID": get("YOUTUBE_CHANNEL_ID"),
        "YOUTUBE_API_KEY": get("YOUTUBE_API_KEY"),
        "IG_USER_ID": get("IG_USER_ID"),
        "IG_ACCESS_TOKEN": get("IG_ACCESS_TOKEN"),
    }


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(WEB_DIR, filename)


@app.route("/api/stats")
def api_stats():
    result: dict = {"youtube": None, "instagram": None, "errors": []}

    try:
        config = load_config()
    except Exception as exc:
        # Whatever goes wrong reading/parsing config.json, the frontend must
        # still get back valid JSON - an uncaught exception here previously
        # fell through to Flask's default HTML error page, which broke the
        # page's fetch() call with a confusing "Unexpected token '<'" parse
        # error instead of showing the actual problem.
        result["errors"].append(str(exc))
        return jsonify(result)

    if config["YOUTUBE_CHANNEL_ID"] and config["YOUTUBE_API_KEY"]:
        try:
            result["youtube"] = fetch_youtube_stats(config["YOUTUBE_CHANNEL_ID"], config["YOUTUBE_API_KEY"])
        except Exception as exc:
            result["errors"].append(f"YouTube: {exc}")
    else:
        result["errors"].append(
            "YouTube not configured: set YOUTUBE_CHANNEL_ID and YOUTUBE_API_KEY in config.json"
        )

    if config["IG_USER_ID"] and config["IG_ACCESS_TOKEN"]:
        try:
            result["instagram"] = fetch_instagram_stats(config["IG_USER_ID"], config["IG_ACCESS_TOKEN"])
        except Exception as exc:
            result["errors"].append(f"Instagram: {exc}")
    else:
        result["errors"].append("Instagram not configured: set IG_USER_ID and IG_ACCESS_TOKEN in config.json")

    return jsonify(result)


if __name__ == "__main__":
    # threaded=True so a slow pipeline run (media search, whisper transcription)
    # doesn't block the stats dashboard from loading in another tab.
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
