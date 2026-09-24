"""Flask backend for Wayne Factory Lite - a standalone sibling of The
Wayne Factory, for a second YouTube channel (History, Science, or
whatever's next). This is its own self-contained app: its own copy of
the production pipeline, its own config, its own content/ folder - it
does not import anything from the main Wayne Factory app.

Only three pages: Dashboard, Produce, Thumbnails - no Videos/Studio
manual-tool page, no News, no English guide. Same automatic captions
(for Shorts), automatic background music, and 9:16 vertical Shorts
support as the main app, since this is the same producer.py/
video_assembler.py/video_editor.py pipeline, just deployed on its own.

Run with:
    python web_server.py
Then open http://localhost:5000

Configure credentials by copying config.example.json to config.json and
filling in this channel's own YouTube channel ID and API key (see
analytics.py's docstring for how to obtain them). config.json is
gitignored, same as the main app.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from analytics import StatsFetchError, fetch_youtube_revenue, fetch_youtube_stats
from studio_api import bp as studio_bp
from auto_api import bp as auto_bp
from jobs import bp as jobs_bp
from editor_api import bp as editor_bp
from thumbnail_api import bp as thumbnail_bp

APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"
CONFIG_PATH = APP_DIR / "config.json"

app = Flask(__name__, static_folder=None)
app.register_blueprint(studio_bp)
app.register_blueprint(auto_bp)
app.register_blueprint(jobs_bp)
app.register_blueprint(editor_bp)
app.register_blueprint(thumbnail_bp)


def load_config() -> dict:
    """Config here is one shared YOUTUBE_API_KEY (a key isn't tied to a
    single channel - the same one can look up any channel by ID) plus a
    CHANNELS list, each just a display name + channel ID - this site is
    meant to run more than one channel (History, Science, whatever's
    next) side by side on one Dashboard."""
    file_config: dict = {}
    if CONFIG_PATH.exists():
        try:
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
                '{"YOUTUBE_API_KEY": "...", "CHANNELS": [...]} - '
                f"got a {type(file_config).__name__} instead"
            )

    api_key = file_config.get("YOUTUBE_API_KEY") or os.environ.get("YOUTUBE_API_KEY", "")
    api_key = api_key.strip() if isinstance(api_key, str) else api_key

    raw_channels = file_config.get("CHANNELS")
    channels = []
    if isinstance(raw_channels, list):
        for entry in raw_channels:
            if not isinstance(entry, dict):
                continue
            channel_id = str(entry.get("YOUTUBE_CHANNEL_ID", "")).strip()
            name = str(entry.get("name", "")).strip() or channel_id
            if channel_id:
                channels.append({"name": name, "channel_id": channel_id})

    return {"YOUTUBE_API_KEY": api_key, "CHANNELS": channels}


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(WEB_DIR, filename)


@app.route("/api/stats")
def api_stats():
    result: dict = {"channels": [], "errors": []}

    try:
        config = load_config()
    except Exception as exc:
        result["errors"].append(str(exc))
        return jsonify(result)

    if not config["YOUTUBE_API_KEY"]:
        result["errors"].append("YouTube not configured: set YOUTUBE_API_KEY in config.json")
        return jsonify(result)
    if not config["CHANNELS"]:
        result["errors"].append("No channels configured: add at least one to CHANNELS in config.json")
        return jsonify(result)

    for channel in config["CHANNELS"]:
        entry = {"name": channel["name"], "youtube": None, "error": None}
        try:
            entry["youtube"] = fetch_youtube_stats(channel["channel_id"], config["YOUTUBE_API_KEY"])
        except Exception as exc:
            entry["error"] = str(exc)
            result["errors"].append(f"{channel['name']}: {exc}")
        result["channels"].append(entry)

    return jsonify(result)


REVENUE_GOAL = 10000.0


@app.route("/api/revenue")
def api_revenue():
    try:
        data = fetch_youtube_revenue()
        return jsonify({
            "goal": REVENUE_GOAL,
            "current": data["total_revenue"],
            "currency": data.get("currency", "USD"),
            "note": data.get("note"),
        })
    except StatsFetchError as exc:
        return jsonify({"goal": REVENUE_GOAL, "current": 0.0, "currency": "USD", "note": str(exc)})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
