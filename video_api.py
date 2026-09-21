"""Flask blueprint that wraps the files/ video pipeline (init.py, build.py)
so it can be driven from the web dashboard instead of the terminal.

Deliberately shells out to init.py/build.py as subprocesses rather than
importing the pipeline package directly - that's exactly what running them
by hand does, so there's no behavior drift between the CLI and the web UI,
and no risk of the pipeline's imports colliding with the web server's own.
"""
from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import sys
from pathlib import Path

from flask import Blueprint, jsonify, request

APP_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = APP_DIR / "files"
VIDEOS_ROOT = PIPELINE_DIR / "videos"

STAGE_NAMES = ["script", "media", "transcribe", "cut", "meta"]
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
RUN_TIMEOUT_SECONDS = 900  # media search + whisper transcription can be slow

bp = Blueprint("video_api", __name__)


def _video_dir(slug: str) -> Path:
    return VIDEOS_ROOT / slug


def _read_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_manifest(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _project_summary(slug: str) -> dict | None:
    project = _read_json(_video_dir(slug) / "project.json")
    if project is None:
        return None
    stages = project.get("stages", {})
    return {
        "slug": slug,
        "title": project.get("title", ""),
        "channel": project.get("channel", ""),
        "created": project.get("created", ""),
        "stages_done": [name for name in STAGE_NAMES if stages.get(name, {}).get("done")],
        "error": project.get("error"),
    }


@bp.route("/api/videos")
def list_videos():
    if not VIDEOS_ROOT.exists():
        return jsonify({"videos": []})
    summaries = []
    for entry in sorted(VIDEOS_ROOT.iterdir()):
        if entry.is_dir():
            summary = _project_summary(entry.name)
            if summary:
                summaries.append(summary)
    return jsonify({"videos": summaries})


@bp.route("/api/videos", methods=["POST"])
def create_video():
    data = request.get_json(silent=True) or {}
    slug = str(data.get("slug", "")).strip().lower()
    channel = str(data.get("channel", "")).strip()
    title = str(data.get("title", "")).strip()

    if not SLUG_RE.match(slug):
        return jsonify({"error": "Slug must be lowercase letters, numbers and hyphens only (max 40 chars)."}), 400
    if not channel or not title:
        return jsonify({"error": "Channel and title are required."}), 400
    if _video_dir(slug).exists():
        return jsonify({"error": f"A project named '{slug}' already exists."}), 409

    try:
        result = subprocess.run(
            [sys.executable, "init.py", slug, "--channel", channel, "--title", title, "--root", "videos"],
            cwd=PIPELINE_DIR, capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "init.py timed out."}), 500

    if result.returncode != 0:
        return jsonify({"error": (result.stderr or result.stdout or "init.py failed").strip()}), 500

    return jsonify(_project_summary(slug)), 201


@bp.route("/api/videos/<slug>")
def get_video(slug):
    if not SLUG_RE.match(slug):
        return jsonify({"error": "Invalid slug."}), 400
    video_dir = _video_dir(slug)
    project = _read_json(video_dir / "project.json")
    if project is None:
        return jsonify({"error": f"No such project: {slug}"}), 404

    script_path = video_dir / "script.md"
    audio_path = video_dir / "audio" / "vo.wav"

    return jsonify({
        "project": project,
        "script": script_path.read_text(encoding="utf-8") if script_path.exists() else "",
        "audio_uploaded": audio_path.exists(),
        "manifest": _read_manifest(video_dir / "media" / "manifest.csv"),
        "edit_plan": _read_json(video_dir / "cut" / "edit_plan.json"),
        "metadata": _read_json(video_dir / "meta" / "metadata.json"),
    })


@bp.route("/api/videos/<slug>/script", methods=["PUT"])
def save_script(slug):
    if not SLUG_RE.match(slug):
        return jsonify({"error": "Invalid slug."}), 400
    video_dir = _video_dir(slug)
    if not video_dir.exists():
        return jsonify({"error": f"No such project: {slug}"}), 404

    data = request.get_json(silent=True) or {}
    content = data.get("content", "")
    if not isinstance(content, str):
        return jsonify({"error": "content must be a string."}), 400

    (video_dir / "script.md").write_text(content, encoding="utf-8")
    return jsonify({"ok": True})


@bp.route("/api/videos/<slug>/audio", methods=["POST"])
def upload_audio(slug):
    if not SLUG_RE.match(slug):
        return jsonify({"error": "Invalid slug."}), 400
    video_dir = _video_dir(slug)
    if not video_dir.exists():
        return jsonify({"error": f"No such project: {slug}"}), 404

    upload = request.files.get("audio")
    if upload is None or upload.filename == "":
        return jsonify({"error": "No audio file in the request."}), 400

    audio_dir = video_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    upload.save(audio_dir / "vo.wav")
    return jsonify({"ok": True})


@bp.route("/api/videos/<slug>/run", methods=["POST"])
def run_stage(slug):
    if not SLUG_RE.match(slug):
        return jsonify({"error": "Invalid slug."}), 400
    video_dir = _video_dir(slug)
    if not video_dir.exists():
        return jsonify({"error": f"No such project: {slug}"}), 404

    data = request.get_json(silent=True) or {}
    stage = data.get("stage")
    force = bool(data.get("force"))

    if stage is not None and stage not in STAGE_NAMES:
        return jsonify({"error": f"Unknown stage {stage!r}. Must be one of {STAGE_NAMES}."}), 400

    args = [sys.executable, "build.py", f"videos/{slug}"]
    if stage:
        args += ["--only", stage]
    if force:
        args.append("--force")

    try:
        result = subprocess.run(
            args, cwd=PIPELINE_DIR, capture_output=True, text=True, timeout=RUN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "log": f"Timed out after {RUN_TIMEOUT_SECONDS}s."}), 500

    log = (result.stdout or "") + (result.stderr or "")
    return jsonify({
        "ok": result.returncode == 0,
        "log": log.strip(),
        "project": _read_json(video_dir / "project.json"),
    })
