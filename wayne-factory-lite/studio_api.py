"""Flask blueprint wrapping studio.py's voiceover generator and the
shotsource media finder for the web dashboard.

Script generation, voice synthesis, and media search can all take minutes,
so every real operation here runs as a background job (see jobs.py) and
the frontend polls GET /api/jobs/<id> until it's done.
"""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request, send_from_directory

import env_config  # noqa: F401  (loads .env before any os.environ default below)
from jobs import set_progress, start_job
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


def make_writer(engine: str, data: dict):
    """Shared by studio_api and auto_api so both build script writers the
    same way from the same request-shaped config dict."""
    if engine == "claude":
        api_key = str(data.get("anthropic_key", "")).strip()
        if not api_key:
            raise ValueError("anthropic_key is required for the Claude engine.")
        return ClaudeScriptWriter(api_key=api_key, model=data.get("model") or "claude-sonnet-5")
    return OllamaScriptWriter(
        model=data.get("model") or "llama3",
        host=str(data.get("ollama_host") or "http://localhost:11434"),
    )


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
    target_words = int(data.get("target_words", 2000))

    if not topic:
        return jsonify({"error": "topic is required."}), 400
    try:
        writer = make_writer(data.get("engine", "ollama"), data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    def task(job_id):
        try:
            return writer.generate_script(topic, target_words=target_words, progress=lambda m: set_progress(job_id, m))
        except ScriptGenerationError as exc:
            raise RuntimeError(str(exc))

    job_id = start_job(task)
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

    VOICEOVER_OUTPUT_DIR.mkdir(exist_ok=True)

    def task(job_id):
        out_path = VOICEOVER_OUTPUT_DIR / f"voiceover-{job_id}.mp3"
        try:
            synthesize_speech(script, voice, out_path, progress=lambda m: set_progress(job_id, m))
        except VoiceSynthesisError as exc:
            raise RuntimeError(str(exc))
        return {"filename": out_path.name}

    job_id = start_job(task)
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

    def task(job_id):
        from shotsource.pipeline import run_pipeline

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(shots_text)
            shots_path = f.name
        try:
            manifest_path = run_pipeline(
                shots_path, output_dir_override=str(MEDIA_OUTPUT_DIR),
                progress=lambda m: set_progress(job_id, m),
            )
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

    job_id = start_job(task)
    return jsonify({"job_id": job_id}), 202


@bp.route("/api/studio/media/file/<path:relpath>")
def get_media_file(relpath):
    path = _safe_media_path(relpath)
    if path is None or not path.exists():
        return jsonify({"error": "Not found."}), 404
    return send_from_directory(path.parent, path.name)
