"""TOP G: the War Room - your daily routine checklist, streak, and your own photo wall.

Photos: put any pictures into the topg_photos folder next to this file (on your PC only - the
folder is never uploaded to GitHub). The War Room shows them.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_from_directory

APP_DIR = Path(__file__).resolve().parent
PHOTOS = APP_DIR / "topg_photos"
STATE = APP_DIR / "topg.json"
IMG = re.compile(r"\.(jpe?g|png|webp|gif)$", re.I)

DEFAULT_TASKS = [
    "Up at 07:00. No snooze.",
    "Train: 50 push-ups + 50 squats (or the gym)",
    "Homework 30 min - phone in another room",
    "Post today's Short",
    "Edit / After Effects: 1 hour minimum",
    "Read or listen: 20 min",
    "No doomscrolling. No junk food.",
    "Plan tomorrow in 2 lines",
]

bp = Blueprint("topg_api", __name__)


def _load() -> dict:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        d = {}
    d.setdefault("tasks", DEFAULT_TASKS)
    d.setdefault("days", {})
    return d


def _save(d: dict) -> None:
    STATE.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def streak(d: dict, today: date | None = None) -> int:
    """Days in a row with every task done (today counts once it's complete)."""
    today = today or date.today()
    n, day = 0, today
    while True:
        done = d["days"].get(day.isoformat(), [])
        if len(d["tasks"]) and len([x for x in done if x]) >= len(d["tasks"]):
            n += 1
        elif day != today:
            break
        day -= timedelta(days=1)
        if day < today - timedelta(days=800):
            break
    return n


def state() -> dict:
    d = _load()
    today = date.today().isoformat()
    done = (d["days"].get(today) or [])[: len(d["tasks"])]
    done += [False] * (len(d["tasks"]) - len(done))
    best = 0
    return {"tasks": d["tasks"], "done": done, "streak": streak(d), "today": today,
            "photos": sorted(p.name for p in PHOTOS.glob("*") if IMG.search(p.name)) if PHOTOS.exists() else [],
            "best": max(best, streak(d))}


@bp.route("/api/topg")
def api_topg():
    PHOTOS.mkdir(exist_ok=True)
    return jsonify(state())


@bp.route("/api/topg/check", methods=["POST"])
def api_topg_check():
    data = request.get_json(silent=True) or {}
    d = _load()
    today = date.today().isoformat()
    done = (d["days"].get(today) or [])[: len(d["tasks"])]
    done += [False] * (len(d["tasks"]) - len(done))
    i = int(data.get("i", -1))
    if 0 <= i < len(done):
        done[i] = bool(data.get("on"))
    d["days"][today] = done
    _save(d)
    return jsonify(state())


@bp.route("/api/topg/tasks", methods=["POST"])
def api_topg_tasks():
    tasks = [str(t).strip()[:80] for t in (request.get_json(silent=True) or {}).get("tasks") or [] if str(t).strip()][:15]
    if not tasks:
        return jsonify({"error": "Add at least one task."}), 400
    d = _load()
    d["tasks"] = tasks
    _save(d)
    return jsonify(state())


@bp.route("/topg-photos/<path:name>")
def topg_photo(name):
    if not IMG.search(name) or "/" in name or "\\" in name:
        abort(404)
    return send_from_directory(PHOTOS, name)
