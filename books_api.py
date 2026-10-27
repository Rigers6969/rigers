"""Flask blueprint for the Books page (books.py)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, send_file

import books

bp = Blueprint("books_api", __name__)


def _err(exc: Exception, code: int = 400):
    return jsonify({"error": str(exc)}), code


@bp.route("/api/books")
def api_books():
    return jsonify(books.library())


@bp.route("/api/books/<int:n>/download", methods=["POST"])
def api_book_download(n: int):
    try:
        return jsonify(books.download(n))
    except books.BookError as exc:
        return _err(exc)
    except Exception as exc:  # network problems on the user's PC
        return _err(f"Download failed: {type(exc).__name__}: {exc}", 502)


@bp.route("/api/books/download-all", methods=["POST"])
def api_books_download_all():
    if not books.download_all():
        return _err("Already downloading.", 409)
    return jsonify({"ok": True})


@bp.route("/api/books/<int:n>/status", methods=["POST"])
def api_book_status(n: int):
    try:
        return jsonify(books.set_status(n, str((request.get_json(silent=True) or {}).get("status", ""))))
    except books.BookError as exc:
        return _err(exc)


@bp.route("/api/books/<int:n>/read")
def api_book_read(n: int):
    try:
        page = request.args.get("page")
        return jsonify(books.read_page(n, int(page) if page is not None else None))
    except (books.BookError, ValueError) as exc:
        return _err(exc)


@bp.route("/api/books/<int:n>/epub")
def api_book_epub(n: int):
    try:
        b = books.book(n)
    except books.BookError as exc:
        return _err(exc, 404)
    if not b["epub"].exists():
        return _err("No e-book file for this one yet.", 404)
    return send_file(b["epub"], as_attachment=True, download_name=b["epub"].name)
