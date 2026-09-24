"""Flask blueprint for post-production edits (background music + burned-in
captions) on an already-produced video - reached from Produce's project
list via "Edit", not from re-running Produce itself.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests
from flask import Blueprint, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

import env_config  # noqa: F401  (loads .env before any os.environ read below)
from jobs import start_job
from music_finder import search_tracks
from producer import CONTENT_ROOT
from thumbnail_generator import ThumbnailError, generate_thumbnail
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
    has_thumbnail = (video_dir / "thumbnail.jpg").exists()

    youtube_title = ""
    metadata_path = video_dir / "metadata.json"
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            youtube_title = (metadata.get("youtube") or {}).get("title", "")
        except (json.JSONDecodeError, OSError):
            pass

    return jsonify({
        "slug": slug,
        "has_base_video": has_base,
        "has_edited": has_edited,
        "base_video_url": f"/api/auto/videos/{slug}/video" if has_base else None,
        "edited_video_url": f"/api/editor/{slug}/video" if has_edited else None,
        "youtube_title": youtube_title,
        "has_thumbnail": has_thumbnail,
        "thumbnail_url": f"/api/editor/{slug}/thumbnail" if has_thumbnail else None,
    })


@bp.route("/api/editor/<slug>/video")
def get_edited_video(slug):
    video_dir = _safe_content_path(slug)
    if video_dir is None or not (video_dir / "final_edited.mp4").exists():
        return jsonify({"error": "Not found."}), 404
    return send_from_directory(video_dir, "final_edited.mp4")


_THUMBNAIL_FILENAMES = {"16:9": "thumbnail.jpg", "9:16": "thumbnail_vertical.jpg"}


def _thumbnail_filename(aspect: str) -> str | None:
    return _THUMBNAIL_FILENAMES.get(aspect)


@bp.route("/api/editor/<slug>/thumbnail")
def get_thumbnail(slug):
    aspect = request.args.get("aspect", "16:9")
    filename = _thumbnail_filename(aspect)
    video_dir = _safe_content_path(slug)
    if filename is None or video_dir is None or not (video_dir / filename).exists():
        return jsonify({"error": "Not found."}), 404
    return send_from_directory(video_dir, filename)


@bp.route("/api/editor/<slug>/thumbnail", methods=["POST"])
def make_thumbnail(slug):
    video_dir = _safe_content_path(slug)
    if video_dir is None or not video_dir.exists():
        return jsonify({"error": f"No such video: {slug}"}), 404

    data = request.get_json(silent=True) or {}
    headline = str(data.get("headline", "")).strip()
    if not headline:
        return jsonify({"error": "headline is required."}), 400
    aspect = str(data.get("aspect", "16:9"))
    filename = _thumbnail_filename(aspect)
    if filename is None:
        return jsonify({"error": f"Unknown aspect {aspect!r} - use 16:9 or 9:16."}), 400

    try:
        generate_thumbnail(
            headline=headline,
            kicker=str(data.get("kicker", "")).strip(),
            tag=str(data.get("tag", "")).strip(),
            brand=str(data.get("brand", "")).strip(),
            aspect=aspect,
            out_path=video_dir / filename,
        )
    except ThumbnailError as exc:
        return jsonify({"error": str(exc)}), 400

    from obsidian_export import refresh_video_note

    refresh_video_note(video_dir)

    return jsonify({"thumbnail_url": f"/api/editor/{slug}/thumbnail?aspect={aspect}"})


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
        from obsidian_export import refresh_video_note

        refresh_video_note(video_dir)
        return {"video_url": f"/api/editor/{slug}/video"}

    job_id = start_job(task)
    return jsonify({"job_id": job_id}), 202
