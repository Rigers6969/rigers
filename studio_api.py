"""Flask blueprint wrapping studio.py's voiceover generator and the
shotsource media finder for the web dashboard.

Script generation, voice synthesis, and media search can all take minutes
(long scripts are many sequential LLM calls; media search hits up to seven
APIs and downloads/scores every candidate). A single HTTP request can't
sit open that long reliably, so every real operation here runs in a
background thread under a job id, and the frontend polls
GET /api/studio/jobs/<id> until it's done - the same shape a real job
queue would have, just in-memory since this is a single-user local tool.
"""
from __future__ import annotations

import csv
import re
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request, send_from_directory

import env_config  # noqa: F401  (loads .env before any os.environ default below)
from studio import (
    UK_MALE_VOICES,
    ClaudeScriptWriter,
    OllamaScriptWriter,
    ScriptGenerationError,
    VoiceSynthesisError,
    synthesize_speech,
)

APP_DIR = Path(__file__).resolve().parent
VOICEOVER_OUTPUT_DIR = APP_DIR / "voiceover_output"
MEDIA_OUTPUT_DIR = APP_DIR / "shot_media_output"

bp = Blueprint("studio_api", __name__)

_jobs_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def _new_job() -> str:
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {"status": "running", "progress": "Starting...", "result": None, "error": None}
    return job_id


def _set_progress(job_id: str, message: str) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["progress"] = message


def _finish_job(job_id: str, result=None, error: Optional[str] = None) -> None:
    with _jobs_lock:
        if job_id not in _jobs:
            return
        _jobs[job_id]["status"] = "error" if error else "done"
        _jobs[job_id]["result"] = result
        _jobs[job_id]["error"] = error


def _run_in_background(job_id: str, fn) -> None:
    def worker():
        try:
            result = fn()
            _finish_job(job_id, result=result)
        except Exception as exc:
            _finish_job(job_id, error=str(exc))

    threading.Thread(target=worker, daemon=True).start()


@bp.route("/api/studio/jobs/<job_id>")
def get_job(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return jsonify({"error": "No such job."}), 404
    return jsonify(job)


# ---------------------------------------------------------------------
# Voiceover generator
# ---------------------------------------------------------------------

@bp.route("/api/studio/voices")
def list_voices():
    return jsonify({"voices": [{"label": label, "id": vid} for label, vid in UK_MALE_VOICES.items()]})


@bp.route("/api/studio/script", methods=["POST"])
def generate_script():
    data = request.get_json(silent=True) or {}
    topic = str(data.get("topic", "")).strip()
    engine = data.get("engine", "ollama")
    target_words = int(data.get("target_words", 2000))

    if not topic:
        return jsonify({"error": "topic is required."}), 400

    if engine == "claude":
        api_key = str(data.get("anthropic_key", "")).strip()
        if not api_key:
            return jsonify({"error": "anthropic_key is required for the Claude engine."}), 400
        writer = ClaudeScriptWriter(api_key=api_key, model=data.get("model") or "claude-sonnet-5")
    else:
        writer = OllamaScriptWriter(
            model=data.get("model") or "llama3",
            host=str(data.get("ollama_host") or "http://localhost:11434"),
        )

    job_id = _new_job()

    def task():
        try:
            return writer.generate_script(topic, target_words=target_words, progress=lambda m: _set_progress(job_id, m))
        except ScriptGenerationError as exc:
            raise RuntimeError(str(exc))

    _run_in_background(job_id, task)
    return jsonify({"job_id": job_id}), 202


@bp.route("/api/studio/voiceover", methods=["POST"])
def generate_voiceover():
    data = request.get_json(silent=True) or {}
    script = str(data.get("script", "")).strip()
    voice = str(data.get("voice", "en-GB-RyanNeural"))

    if not script:
        return jsonify({"error": "script is required."}), 400
    if voice not in UK_MALE_VOICES.values():
        return jsonify({"error": "Unknown voice id."}), 400

    job_id = _new_job()
    out_path = VOICEOVER_OUTPUT_DIR / f"voiceover-{job_id}.mp3"

    def task():
        try:
            synthesize_speech(script, voice, out_path, progress=lambda m: _set_progress(job_id, m))
        except VoiceSynthesisError as exc:
            raise RuntimeError(str(exc))
        return {"filename": out_path.name}

    _run_in_background(job_id, task)
    return jsonify({"job_id": job_id}), 202


@bp.route("/api/studio/voiceover/file/<path:filename>")
def get_voiceover_file(filename):
    return send_from_directory(VOICEOVER_OUTPUT_DIR, filename)


# ---------------------------------------------------------------------
# Media finder
# ---------------------------------------------------------------------

def _safe_media_path(relpath: str) -> Optional[Path]:
    """Resolves relpath under MEDIA_OUTPUT_DIR, rejecting anything that
    escapes it (defense in depth against a manipulated path in a request)."""
    candidate = (MEDIA_OUTPUT_DIR / relpath).resolve()
    try:
        candidate.relative_to(MEDIA_OUTPUT_DIR.resolve())
    except ValueError:
        return None
    return candidate


@bp.route("/api/studio/media", methods=["POST"])
def find_media():
    data = request.get_json(silent=True) or {}
    shots_text = str(data.get("shots", "")).strip()
    if not shots_text:
        return jsonify({"error": "shots is required (one description per line)."}), 400

    job_id = _new_job()

    def task():
        from shotsource.pipeline import run_pipeline

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(shots_text)
            shots_path = f.name
        try:
            _set_progress(job_id, "Querying sources and quality-filtering results - this can take a while...")
            manifest_path = run_pipeline(shots_path, output_dir_override=str(MEDIA_OUTPUT_DIR))
        finally:
            Path(shots_path).unlink(missing_ok=True)

        rows = []
        if manifest_path.exists():
            with manifest_path.open(encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    local_path = row.get("local_path", "")
                    try:
                        rel = str(Path(local_path).resolve().relative_to(MEDIA_OUTPUT_DIR.resolve()))
                    except ValueError:
                        rel = None
                    row["image_url"] = f"/api/studio/media/file/{rel}" if rel else None
                    rows.append(row)
        return {"manifest": rows}

    _run_in_background(job_id, task)
    return jsonify({"job_id": job_id}), 202


@bp.route("/api/studio/media/file/<path:relpath>")
def get_media_file(relpath):
    path = _safe_media_path(relpath)
    if path is None or not path.exists():
        return jsonify({"error": "Not found."}), 404
    return send_from_directory(path.parent, path.name)
