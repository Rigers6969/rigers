"""Flask blueprint for the Autopilot page (autopilot.py)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, send_file

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
    data = request.get_json(silent=True) or {}
    only = data.get("channel") or None
    length = data.get("length") if data.get("length") in ("short", "long") else None
    brief = str(data.get("brief") or "")[:3000]
    if brief.strip() and not only:
        return jsonify({"error": "Pick the channel for your video."}), 400
    if not autopilot.run_now(only, length, brief):
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


@bp.route("/api/autopilot/review")
def api_autopilot_review():
    return jsonify({"review": autopilot.review_list()})


@bp.route("/api/autopilot/review/<slug>/video")
def api_autopilot_review_video(slug):
    path = autopilot.video_file(slug)
    if path is None:
        return jsonify({"error": "Not found."}), 404
    return send_file(path, conditional=True)


@bp.route("/api/autopilot/review/<slug>/thumb/<int:n>")
def api_autopilot_review_thumb(slug, n):
    path = autopilot.thumb_file(slug, n)
    if path is None:
        return jsonify({"error": "Not found."}), 404
    return send_file(path, max_age=0)


@bp.route("/api/autopilot/review/<slug>", methods=["POST"])
def api_autopilot_review_action(slug):
    data = request.get_json(silent=True) or {}
    try:
        if data.get("action") == "reject":
            autopilot.reject(slug)
            return jsonify({"ok": True})
        return jsonify(autopilot.approve(slug, data.get("title"), int(data.get("thumb") or 1)))
    except autopilot.AutopilotError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Upload failed: {type(exc).__name__}: {exc}"}), 502
