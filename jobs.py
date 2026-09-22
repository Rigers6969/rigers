"""Generic in-memory background job registry, shared by every Flask
blueprint that needs to run something slow (script writing, TTS, media
search, or all of them chained together) without blocking the request.

A single shared registry means the frontend only ever needs to know one
polling endpoint (GET /api/jobs/<id>), regardless of which blueprint
started the job.
"""
from __future__ import annotations

import threading
import uuid
from typing import Callable, Optional

from flask import Blueprint, jsonify

bp = Blueprint("jobs_api", __name__)

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def new_job() -> str:
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {"status": "running", "progress": "Starting...", "result": None, "error": None}
    return job_id


def set_progress(job_id: str, message: str) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id]["progress"] = message


def _finish(job_id: str, result=None, error: Optional[str] = None) -> None:
    with _lock:
        if job_id not in _jobs:
            return
        _jobs[job_id]["status"] = "error" if error else "done"
        _jobs[job_id]["result"] = result
        _jobs[job_id]["error"] = error


def run_in_background(job_id: str, fn: Callable[[str], object]) -> None:
    def worker():
        try:
            result = fn(job_id)
            _finish(job_id, result=result)
        except Exception as exc:
            _finish(job_id, error=str(exc))

    threading.Thread(target=worker, daemon=True).start()


def start_job(fn: Callable[[str], object]) -> str:
    """Allocates a job id and immediately runs fn(job_id) in the background -
    fn receives its own job id so it can call set_progress(job_id, ...)."""
    job_id = new_job()
    run_in_background(job_id, fn)
    return job_id


@bp.route("/api/jobs/<job_id>")
def get_job(job_id):
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        return jsonify({"error": "No such job."}), 404
    return jsonify(job)
