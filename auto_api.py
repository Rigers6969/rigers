"""Flask blueprint for one-shot auto-production: give it a topic, get back
a finished content/<slug>/ folder (script, shot list, voiceover, stock
media, and a notes.txt with YouTube/Instagram/Facebook metadata) with no
further manual steps.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request, send_from_directory

import env_config  # noqa: F401
from jobs import start_job
from producer import CONTENT_ROOT, produce_video
from studio_api import make_writer

bp = Blueprint("auto_api", __name__)

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")


@bp.route("/api/auto/produce", methods=["POST"])
def produce():
    data = request.get_json(silent=True) or {}
    topic = str(data.get("topic", "")).strip()
    channel = str(data.get("channel", "")).strip() or "Paper Trail"
    voice = str(data.get("voice", "en-GB-RyanNeural"))
    target_words = int(data.get("target_words", 1500))
    style_slug = (str(data.get("style_slug", "")).strip() or None)

    if not topic:
        return jsonify({"error": "topic is required."}), 400
    try:
        writer = make_writer(data.get("engine", "ollama"), data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    def task(job_id):
        from jobs import set_progress

        return produce_video(
            topic, channel, writer, voice=voice, target_words=target_words,
            style_slug=style_slug, progress=lambda m: set_progress(job_id, m),
        )

    job_id = start_job(task)
    return jsonify({"job_id": job_id}), 202


def _safe_content_path(slug: str, *parts: str) -> Optional[Path]:
    if not SLUG_RE.match(slug):
        return None
    candidate = CONTENT_ROOT.joinpath(slug, *parts).resolve()
    try:
        candidate.relative_to((CONTENT_ROOT / slug).resolve())
    except ValueError:
        return None
    return candidate


@bp.route("/api/auto/videos")
def list_videos():
    if not CONTENT_ROOT.exists():
        return jsonify({"videos": []})
    videos = []
    for entry in sorted(CONTENT_ROOT.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        metadata_path = entry / "metadata.json"
        metadata = {}
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        videos.append({
            "slug": entry.name,
            "title": (metadata.get("youtube") or {}).get("title") or entry.name,
            "has_script": (entry / "script.txt").exists(),
            "has_voiceover": (entry / "voiceover.mp3").exists(),
            "has_media": (entry / "media" / "manifest.csv").exists(),
            "has_video": (entry / "final.mp4").exists(),
        })
    return jsonify({"videos": videos})


@bp.route("/api/auto/videos/<slug>")
def get_video(slug):
    video_dir = _safe_content_path(slug)
    if video_dir is None or not video_dir.exists():
        return jsonify({"error": f"No such video: {slug}"}), 404

    script = (video_dir / "script.txt").read_text(encoding="utf-8") if (video_dir / "script.txt").exists() else ""
    notes = (video_dir / "notes.txt").read_text(encoding="utf-8") if (video_dir / "notes.txt").exists() else ""
    metadata = {}
    if (video_dir / "metadata.json").exists():
        metadata = json.loads((video_dir / "metadata.json").read_text(encoding="utf-8"))
    shots = []
    if (video_dir / "shots.json").exists():
        shots = json.loads((video_dir / "shots.json").read_text(encoding="utf-8"))

    manifest = []
    manifest_path = video_dir / "media" / "manifest.csv"
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                local_path = row.get("local_path", "")
                try:
                    rel = str(Path(local_path).resolve().relative_to((video_dir / "media").resolve()))
                except ValueError:
                    rel = None
                row["image_url"] = f"/api/auto/videos/{slug}/media/{rel}" if rel else None
                manifest.append(row)

    return jsonify({
        "slug": slug,
        "script": script,
        "notes": notes,
        "metadata": metadata,
        "shots": shots,
        "manifest": manifest,
        "voiceover_url": f"/api/auto/videos/{slug}/voiceover" if (video_dir / "voiceover.mp3").exists() else None,
        "video_url": f"/api/auto/videos/{slug}/video" if (video_dir / "final.mp4").exists() else None,
    })


@bp.route("/api/auto/videos/<slug>/voiceover")
def get_voiceover(slug):
    video_dir = _safe_content_path(slug)
    if video_dir is None or not (video_dir / "voiceover.mp3").exists():
        return jsonify({"error": "Not found."}), 404
    return send_from_directory(video_dir, "voiceover.mp3")


@bp.route("/api/auto/videos/<slug>/video")
def get_video_file(slug):
    video_dir = _safe_content_path(slug)
    if video_dir is None or not (video_dir / "final.mp4").exists():
        return jsonify({"error": "Not found."}), 404
    return send_from_directory(video_dir, "final.mp4")


@bp.route("/api/auto/videos/<slug>/assemble", methods=["POST"])
def assemble(slug):
    video_dir = _safe_content_path(slug)
    if video_dir is None or not video_dir.exists():
        return jsonify({"error": f"No such video: {slug}"}), 404

    data = request.get_json(silent=True) or {}
    style_slug = (str(data.get("style_slug", "")).strip() or None)
    style = None
    if style_slug:
        style_path = CONTENT_ROOT / "_styles" / f"{style_slug}.json"
        if style_path.exists():
            style = json.loads(style_path.read_text(encoding="utf-8"))

    def task(job_id):
        from jobs import set_progress
        from video_assembler import assemble_video

        assemble_video(video_dir, progress=lambda m: set_progress(job_id, m), style=style)
        return {"video_url": f"/api/auto/videos/{slug}/video"}

    job_id = start_job(task)
    return jsonify({"job_id": job_id}), 202


@bp.route("/api/style/profiles")
def list_style_profiles():
    styles_dir = CONTENT_ROOT / "_styles"
    if not styles_dir.exists():
        return jsonify({"profiles": []})
    profiles = []
    for path in sorted(styles_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        profiles.append({
            "slug": data.get("slug", path.stem),
            "source_title": data.get("source_title", path.stem),
            "avg_shot_seconds": data.get("avg_shot_seconds"),
        })
    return jsonify({"profiles": profiles})


@bp.route("/api/style/analyze", methods=["POST"])
def analyze_style():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()
    api_key = str(data.get("anthropic_key", "")).strip()

    if not url:
        return jsonify({"error": "url is required."}), 400
    if not api_key:
        return jsonify({"error": "anthropic_key is required (used once, for the vision analysis step)."}), 400

    def task(job_id):
        from jobs import set_progress
        from style_analyzer import build_style_profile

        return build_style_profile(url, api_key, progress=lambda m: set_progress(job_id, m))

    job_id = start_job(task)
    return jsonify({"job_id": job_id}), 202


@bp.route("/api/auto/videos/<slug>/media/<path:relpath>")
def get_media_file(slug, relpath):
    path = _safe_content_path(slug, "media", relpath)
    if path is None or not path.exists():
        return jsonify({"error": "Not found."}), 404
    return send_from_directory(path.parent, path.name)
