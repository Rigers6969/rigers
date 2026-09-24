"""Second, trimmed-down Wayne Factory site - Dashboard, Produce, and
Thumbnails only (no Videos/Studio/News/English tabs) - for running a
second YouTube channel (e.g. History or Science) alongside the main
site, with its own credentials in config_lite.json.

Shares all the same backend logic (producer.py, video_assembler.py,
video_editor.py, thumbnail_generator.py, studio.py, shotsource/, etc.)
and the same content/ folder as web_server.py - videos from both sites
land in the same place and show up in the same Obsidian vault, since
producer.py already keeps every video in its own uniquely-slugged
folder regardless of which channel name it was produced under. Only
the page set and the Dashboard's own YouTube credentials are separate.

Run with:
    python web_server_lite.py
Then open http://localhost:5001 (a different port from web_server.py's
5000, so both can run at the same time).

Configure this site's own YouTube channel by copying
config_lite.example.json to config_lite.json and filling in that
channel's own YOUTUBE_CHANNEL_ID and YOUTUBE_API_KEY - see
web_server.py's docstring for exactly how to obtain them. config_lite.json
is gitignored, same as config.json.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Must happen before any import below (studio_api etc. all transitively
# import producer.py, which reads this env var once at import time to
# decide CONTENT_ROOT) - this is what keeps this site's videos in their
# own content_lite/ folder instead of mixing into web_server.py's content/.
os.environ.setdefault("WAYNE_CONTENT_DIR", "content_lite")

from flask import Flask, jsonify, send_from_directory

from analytics import StatsFetchError, fetch_youtube_revenue, fetch_youtube_stats
from studio_api import bp as studio_bp
from auto_api import bp as auto_bp
from jobs import bp as jobs_bp
from editor_api import bp as editor_bp
from thumbnail_api import bp as thumbnail_bp

APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web_lite"
CONFIG_PATH = APP_DIR / "config_lite.json"

app = Flask(__name__, static_folder=None)
app.register_blueprint(studio_bp)
app.register_blueprint(auto_bp)
app.register_blueprint(jobs_bp)
app.register_blueprint(editor_bp)
app.register_blueprint(thumbnail_bp)


def load_config() -> dict:
    """Same logic as web_server.py's load_config(), reading this site's
    own config_lite.json instead - see that function's docstring for why
    utf-8-sig and per-key stripping matter."""
    file_config: dict = {}
    if CONFIG_PATH.exists():
        try:
            raw_text = CONFIG_PATH.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError) as exc:
            raise RuntimeError(f"config_lite.json could not be read: {exc}") from exc
        try:
            file_config = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"config_lite.json is not valid JSON: {exc}") from exc
        if not isinstance(file_config, dict):
            raise RuntimeError(
                "config_lite.json must contain a JSON object like "
                '{"YOUTUBE_CHANNEL_ID": "...", ...} - '
                f"got a {type(file_config).__name__} instead"
            )

    def get(key: str) -> str:
        value = file_config.get(key) or os.environ.get(key, "")
        return value.strip() if isinstance(value, str) else value

    return {
        "YOUTUBE_CHANNEL_ID": get("YOUTUBE_CHANNEL_ID"),
        "YOUTUBE_API_KEY": get("YOUTUBE_API_KEY"),
    }


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(WEB_DIR, filename)


@app.route("/api/stats")
def api_stats():
    result: dict = {"youtube": None, "errors": []}

    try:
        config = load_config()
    except Exception as exc:
        result["errors"].append(str(exc))
        return jsonify(result)

    if config["YOUTUBE_CHANNEL_ID"] and config["YOUTUBE_API_KEY"]:
        try:
            result["youtube"] = fetch_youtube_stats(config["YOUTUBE_CHANNEL_ID"], config["YOUTUBE_API_KEY"])
        except Exception as exc:
            result["errors"].append(f"YouTube: {exc}")
    else:
        result["errors"].append(
            "YouTube not configured: set YOUTUBE_CHANNEL_ID and YOUTUBE_API_KEY in config_lite.json"
        )

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
    app.run(host="127.0.0.1", port=5001, debug=False, threaded=True)
