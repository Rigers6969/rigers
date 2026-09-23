"""Flask blueprint for the in-app "English" page - a book-style view of
real, advanced-level grammar content scraped from Wikibooks (see
grammar_guide.py for the sources and the honest scope note on what
"advanced" does and doesn't mean here).
"""
from __future__ import annotations

from flask import Blueprint, jsonify

from grammar_guide import load_cache, refresh_cache
from jobs import start_job

bp = Blueprint("grammar_guide_api", __name__)


@bp.route("/api/english/chapters")
def get_chapters():
    return jsonify({"chapters": load_cache()})


@bp.route("/api/english/refresh", methods=["POST"])
def refresh():
    def task(job_id):
        from jobs import set_progress
        return {"chapters": refresh_cache(progress=lambda msg: set_progress(job_id, msg))}

    job_id = start_job(task)
    return jsonify({"job_id": job_id}), 202
