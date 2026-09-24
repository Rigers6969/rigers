"""Flask blueprint for the Produce page's Schedule panel - CRUD over
schedule.json (see scheduler.py for the actual background production
loop this config drives)."""
from __future__ import annotations

from typing import Optional

from flask import Blueprint, jsonify, request

from scheduler import get_entry_job_id, load_schedule, new_entry_id, save_schedule

bp = Blueprint("scheduler_api", __name__)

VALID_ENGINES = {"ollama", "claude"}
VALID_LENGTHS = {"short", "long"}


def _validate_entry(data: dict) -> tuple[Optional[dict], Optional[str]]:
    channel = str(data.get("channel", "")).strip()
    start = str(data.get("start", "")).strip()
    end = str(data.get("end", "")).strip()
    if not channel:
        return None, "channel is required."
    if not start or not end:
        return None, "start and end time are required."
    if start >= end:
        return None, "start time must be before end time (overnight windows aren't supported)."
    engine = str(data.get("engine", "ollama")).strip() or "ollama"
    if engine not in VALID_ENGINES:
        return None, f"engine must be one of {sorted(VALID_ENGINES)}."
    length = str(data.get("length", "long")).strip() or "long"
    if length not in VALID_LENGTHS:
        return None, f"length must be one of {sorted(VALID_LENGTHS)}."

    entry = {
        "id": data.get("id") or new_entry_id(),
        "channel": channel,
        "start": start,
        "end": end,
        "enabled": bool(data.get("enabled", True)),
        "engine": engine,
        "ollama_host": str(data.get("ollama_host", "http://localhost:11434")).strip(),
        "anthropic_key": str(data.get("anthropic_key", "")).strip(),
        "length": length,
        "voice": str(data.get("voice", "en-GB-RyanNeural")).strip(),
    }
    return entry, None


@bp.route("/api/schedule")
def get_schedule():
    return jsonify({"entries": load_schedule()})


@bp.route("/api/schedule/<entry_id>/job")
def get_schedule_entry_job(entry_id):
    """The job_id of today's run for this entry, if the scheduler has
    started one - null otherwise (window hasn't opened yet today, or
    the entry is disabled). The Schedule panel polls this + the regular
    GET /api/jobs/<job_id> to show whether a window actually fired."""
    return jsonify({"job_id": get_entry_job_id(entry_id)})


@bp.route("/api/schedule", methods=["POST"])
def add_schedule_entry():
    data = request.get_json(silent=True) or {}
    entry, error = _validate_entry(data)
    if error:
        return jsonify({"error": error}), 400
    entries = load_schedule()
    entries.append(entry)
    save_schedule(entries)
    return jsonify({"entries": entries}), 201


@bp.route("/api/schedule/<entry_id>", methods=["PUT"])
def update_schedule_entry(entry_id):
    data = request.get_json(silent=True) or {}
    data["id"] = entry_id
    entry, error = _validate_entry(data)
    if error:
        return jsonify({"error": error}), 400
    entries = load_schedule()
    for i, existing in enumerate(entries):
        if existing["id"] == entry_id:
            entries[i] = entry
            save_schedule(entries)
            return jsonify({"entries": entries})
    return jsonify({"error": f"No schedule entry with id {entry_id}"}), 404


@bp.route("/api/schedule/<entry_id>", methods=["DELETE"])
def delete_schedule_entry(entry_id):
    entries = load_schedule()
    remaining = [e for e in entries if e["id"] != entry_id]
    if len(remaining) == len(entries):
        return jsonify({"error": f"No schedule entry with id {entry_id}"}), 404
    save_schedule(remaining)
    return jsonify({"entries": remaining})
