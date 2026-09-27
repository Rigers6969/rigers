"""Flask blueprint for the Trend Scout panel - lets you set which
competitor channels to watch per channel, and preview what their free
YouTube RSS feeds currently return, without touching the writer model
or spending any production job."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from trend_scout import (
    fetch_channel_recent_titles,
    load_all_competitors,
    save_competitor_ids,
)

bp = Blueprint("scout_api", __name__)


@bp.route("/api/scout/competitors")
def get_competitors():
    return jsonify({"channels": load_all_competitors()})


@bp.route("/api/scout/competitors", methods=["POST"])
def set_competitors():
    data = request.get_json(silent=True) or {}
    channel = str(data.get("channel", "")).strip()
    raw_ids = data.get("competitor_channel_ids")

    if not channel:
        return jsonify({"error": "channel is required."}), 400
    if not isinstance(raw_ids, list):
        return jsonify({"error": "competitor_channel_ids must be a list of strings."}), 400

    save_competitor_ids(channel, [str(i) for i in raw_ids])
    return jsonify({"ok": True})


@bp.route("/api/scout/preview")
def preview():
    channel_id = str(request.args.get("channel_id", "")).strip()
    if not channel_id:
        return jsonify({"error": "channel_id is required."}), 400
    titles = fetch_channel_recent_titles(channel_id)
    if not titles:
        return jsonify({"titles": [], "note": "No titles found - check the channel ID, or that channel's feed may be unreachable right now."})
    return jsonify({"titles": titles})
