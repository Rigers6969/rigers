"""Flask blueprint for the Autopilot page (autopilot.py)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import autopilot

bp = Blueprint("autopilot_api", __name__)
autopilot.start_scheduler()


@bp.route("/api/autopilot")
def api_autopilot():
    return jsonify(autopilot.status())


@bp.route("/api/autopilot/settings", methods=["POST"])
def api_autopilot_settings():
    try:
        autopilot.save_settings(request.get_json(silent=True) or {})
        return jsonify(autopilot.status())
    except (autopilot.AutopilotError, ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400


@bp.route("/api/autopilot/run", methods=["POST"])
def api_autopilot_run():
    only = (request.get_json(silent=True) or {}).get("channel") or None
    if not autopilot.run_now(only):
        return jsonify({"error": "The Autopilot is already working."}), 409
    return jsonify({"ok": True})


@bp.route("/api/autopilot/connect", methods=["POST"])
def api_autopilot_connect():
    channel = str((request.get_json(silent=True) or {}).get("channel", "")).strip()
    if not channel:
        return jsonify({"error": "Which channel?"}), 400
    try:
        autopilot.connect(channel)  # waits until you finish Google's sign-in in the browser
        return jsonify(autopilot.status())
    except autopilot.AutopilotError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Sign-in failed: {type(exc).__name__}: {exc}"}), 502
