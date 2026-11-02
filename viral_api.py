"""Flask blueprint for the Viral Analyzer page (viral.py)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import viral

bp = Blueprint("viral_api", __name__)


@bp.route("/api/viral")
def api_viral_state():
    return jsonify({"status": viral.status(), "history": viral.history()})


@bp.route("/api/viral/analyze", methods=["POST"])
def api_viral_analyze():
    url = str((request.get_json(silent=True) or {}).get("url", "")).strip()
    try:
        ok = viral.start_analyze(url)
    except viral.ViralError as exc:
        return jsonify({"error": str(exc)}), 400
    return (jsonify({"ok": True}) if ok else (jsonify({"error": "Something is already running - wait for it to finish."}), 409))


@bp.route("/api/viral/<vid>/make", methods=["POST"])
def api_viral_make(vid):
    data = request.get_json(silent=True) or {}
    try:
        ok = viral.start_version(vid, str(data.get("topic", "")), str(data.get("channel", "Paper Trail")))
    except viral.ViralError as exc:
        return jsonify({"error": str(exc)}), 400
    return (jsonify({"ok": True}) if ok else (jsonify({"error": "Something is already running - wait for it to finish."}), 409))
