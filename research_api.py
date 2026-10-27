"""Flask blueprint for the Research page (researcher.py)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import researcher

bp = Blueprint("research_api", __name__)


@bp.route("/api/research")
def api_research_state():
    return jsonify(researcher.state())


@bp.route("/api/research/run", methods=["POST"])
def api_research_run():
    if not researcher.start():
        return jsonify({"error": "Research is already running."}), 409
    return jsonify({"ok": True})


@bp.route("/api/research/channels", methods=["GET", "POST"])
def api_research_channels():
    if request.method == "GET":
        return jsonify({"channels": researcher.load_channels()})
    data = request.get_json(silent=True) or {}
    try:
        return jsonify({"channels": researcher.save_channels(data.get("channels") or [])})
    except researcher.ResearchError as exc:
        return jsonify({"error": str(exc)}), 400


@bp.route("/api/research/ideas", methods=["GET", "POST"])
def api_research_ideas():
    if request.method == "GET":
        return jsonify({"ideas": researcher.load_ideas()})
    data = request.get_json(silent=True) or {}
    try:
        if "index" in data:
            ideas = researcher.update_idea(int(data["index"]), data.get("done"), bool(data.get("delete")))
        else:
            ideas = researcher.save_idea(str(data.get("channel", "")), str(data.get("title", "")),
                                         str(data.get("angle", "")), str(data.get("link", "")))
        return jsonify({"ideas": ideas})
    except (researcher.ResearchError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
