"""Flask blueprint for the standalone Thumbnails page - the same
Pillow-based generator used by the Edit page (thumbnail_generator.py),
but usable on its own without an existing video project. Generated
images are saved to content/_thumbnails/ (shared scratch space, not a
video folder) so they can be served back and downloaded.
"""
from __future__ import annotations

import uuid

from flask import Blueprint, jsonify, request, send_from_directory

from producer import CONTENT_ROOT
from thumbnail_generator import ThumbnailError, generate_thumbnail

bp = Blueprint("thumbnail_api", __name__)

THUMBNAILS_DIR = CONTENT_ROOT / "_thumbnails"
_ASPECT_EXT = {"16:9": "jpg", "9:16": "jpg"}


@bp.route("/api/thumbnail/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True) or {}
    headline = str(data.get("headline", "")).strip()
    if not headline:
        return jsonify({"error": "headline is required."}), 400
    aspect = str(data.get("aspect", "16:9"))
    if aspect not in _ASPECT_EXT:
        return jsonify({"error": f"Unknown aspect {aspect!r} - use 16:9 or 9:16."}), 400

    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{_ASPECT_EXT[aspect]}"

    try:
        generate_thumbnail(
            headline=headline,
            kicker=str(data.get("kicker", "")).strip(),
            tag=str(data.get("tag", "")).strip(),
            brand=str(data.get("brand", "")).strip(),
            aspect=aspect,
            out_path=THUMBNAILS_DIR / filename,
        )
    except ThumbnailError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"thumbnail_url": f"/api/thumbnail/file/{filename}"})


@bp.route("/api/thumbnail/file/<filename>")
def get_file(filename):
    from werkzeug.utils import secure_filename

    safe_name = secure_filename(filename)
    if not safe_name or safe_name != filename or not (THUMBNAILS_DIR / safe_name).exists():
        return jsonify({"error": "Not found."}), 404
    as_attachment = request.args.get("download") == "1"
    return send_from_directory(THUMBNAILS_DIR, safe_name, as_attachment=as_attachment, download_name="thumbnail.jpg" if as_attachment else None)
