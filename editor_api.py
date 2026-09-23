"""Flask blueprint for post-production edits (background music + burned-in
captions) on an already-produced video - reached from Produce's project
list via "Edit", not from re-running Produce itself.
"""
from __future__ import annotations

import re
from pathlib import Path

import requests
from flask import Blueprint, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

import env_config  # noqa: F401  (loads .env before any os.environ read below)
from jobs import start_job
from music_finder import search_tracks
from producer import CONTENT_ROOT
from video_editor import CAPTION_STYLES, DEFAULT_CAPTION_STYLE, MUSIC_LIBRARY_DIR, apply_edits, list_music_library

bp = Blueprint("editor_api", __name__)

ALLOWED_MUSIC_EXT = {".mp3", ".wav", ".m4a", ".ogg"}


def _safe_content_path(slug: str, *parts: str) -> Path | None:
    """Mirrors auto_api.py's own path-safety helper - kept local rather
    than importing a private name across modules."""
    import re

    if not re.match(r"^[a-z0-9][a-z0-9-]{0,59}$", slug):
        return None
    candidate = CONTENT_ROOT.joinpath(slug, *parts).resolve()
    try:
        candidate.relative_to((CONTENT_ROOT / slug).resolve())
    except ValueError:
        return None
    return candidate


@bp.route("/api/editor/caption-styles")
def caption_styles():
    return jsonify({
        "styles": [{"id": key, "label": val["label"]} for key, val in CAPTION_STYLES.items()],
        "default": DEFAULT_CAPTION_STYLE,
    })


@bp.route("/api/editor/music")
def list_music():
    return jsonify({"tracks": list_music_library()})


@bp.route("/api/editor/music/search")
def search_music():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"tracks": [], "error": "q is required."}), 400
    return jsonify(search_tracks(query))


def _music_filename_for(track: dict) -> str:
    raw = f"{track.get('artist', 'unknown')} - {track.get('title', 'untitled')} ({track.get('id', '')})"
    safe = re.sub(r"[^\w\s()-]", "", raw).strip()
    safe = re.sub(r"\s+", " ", safe)
    return secure_filename(f"{safe}.mp3") or f"jamendo-{track.get('id', 'track')}.mp3"


@bp.route("/api/editor/music/import", methods=["POST"])
def import_music():
    data = request.get_json(silent=True) or {}
    download_url = str(data.get("download_url", "")).strip()
    if not download_url.startswith("https://") and not download_url.startswith("http://"):
        return jsonify({"error": "A valid download_url is required."}), 400

    filename = _music_filename_for(data)

    try:
        resp = requests.get(download_url, timeout=30, stream=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return jsonify({"error": f"Download failed: {exc}"}), 502

    MUSIC_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    dest = MUSIC_LIBRARY_DIR / filename
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)

    return jsonify({"filename": filename})


@bp.route("/api/editor/music/upload", methods=["POST"])
def upload_music():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file uploaded."}), 400
    filename = secure_filename(file.filename)
    ext = Path(filename).suffix.lower()
    if not filename or ext not in ALLOWED_MUSIC_EXT:
        return jsonify({"error": f"Unsupported file type - use mp3, wav, m4a, or ogg."}), 400
    MUSIC_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    file.save(MUSIC_LIBRARY_DIR / filename)
    return jsonify({"filename": filename})


@bp.route("/api/editor/music/file/<path:filename>")
def get_music_file(filename):
    safe_name = secure_filename(filename)
    if not safe_name or safe_name != filename:
        return jsonify({"error": "Not found."}), 404
    path = MUSIC_LIBRARY_DIR / safe_name
    if not path.exists():
        return jsonify({"error": "Not found."}), 404
    return send_from_directory(MUSIC_LIBRARY_DIR, safe_name)


@bp.route("/api/editor/<slug>/state")
def get_state(slug):
    video_dir = _safe_content_path(slug)
    if video_dir is None or not video_dir.exists():
        return jsonify({"error": f"No such video: {slug}"}), 404

    has_base = (video_dir / "final.mp4").exists()
    has_edited = (video_dir / "final_edited.mp4").exists()
    return jsonify({
        "slug": slug,
        "has_base_video": has_base,
        "has_edited": has_edited,
        "base_video_url": f"/api/auto/videos/{slug}/video" if has_base else None,
        "edited_video_url": f"/api/editor/{slug}/video" if has_edited else None,
    })


@bp.route("/api/editor/<slug>/video")
def get_edited_video(slug):
    video_dir = _safe_content_path(slug)
    if video_dir is None or not (video_dir / "final_edited.mp4").exists():
        return jsonify({"error": "Not found."}), 404
    return send_from_directory(video_dir, "final_edited.mp4")


@bp.route("/api/editor/<slug>/apply", methods=["POST"])
def apply(slug):
    video_dir = _safe_content_path(slug)
    if video_dir is None or not video_dir.exists():
        return jsonify({"error": f"No such video: {slug}"}), 404
    if not (video_dir / "final.mp4").exists():
        return jsonify({"error": "This video hasn't been assembled yet - assemble it on the Produce page first."}), 400

    data = request.get_json(silent=True) or {}
    add_captions = bool(data.get("add_captions"))
    caption_style = str(data.get("caption_style", DEFAULT_CAPTION_STYLE))
    music_filename = str(data.get("music_filename", "")).strip() or None

    music_path = None
    if music_filename:
        safe_name = secure_filename(music_filename)
        if not safe_name or safe_name != music_filename:
            return jsonify({"error": "Invalid music filename."}), 400
        candidate = MUSIC_LIBRARY_DIR / safe_name
        if not candidate.exists():
            return jsonify({"error": f"No such music track: {music_filename}"}), 400
        music_path = candidate

    def task(job_id):
        from jobs import set_progress

        apply_edits(
            video_dir,
            add_captions=add_captions,
            caption_style=caption_style,
            music_path=music_path,
            progress=lambda m: set_progress(job_id, m),
        )
        return {"video_url": f"/api/editor/{slug}/video"}

    job_id = start_job(task)
    return jsonify({"job_id": job_id}), 202
