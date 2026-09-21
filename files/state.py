"""project.json is the only interface between stages.

Every stage reads it, does its work, writes back. No stage imports another.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = "project.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(video_dir: Path) -> dict:
    path = Path(video_dir) / STATE_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"No {STATE_FILE} in {video_dir}. Run: python init.py <slug>"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def save(video_dir: Path, state: dict) -> None:
    """Atomic write: temp file then rename, so a crash never leaves half a file."""
    path = Path(video_dir) / STATE_FILE
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def is_done(state: dict, stage: str) -> bool:
    return bool(state.get("stages", {}).get(stage, {}).get("done"))


def mark_done(video_dir: Path, state: dict, stage: str, **outputs) -> None:
    state.setdefault("stages", {})[stage] = {
        "done": True,
        "at": now(),
        "outputs": outputs,
    }
    state.pop("error", None)
    save(video_dir, state)


def mark_error(video_dir: Path, state: dict, stage: str, message: str) -> None:
    state["error"] = {"stage": stage, "at": now(), "message": str(message)}
    save(video_dir, state)


def clear(video_dir: Path, state: dict, stage: str) -> None:
    state.get("stages", {}).pop(stage, None)
    save(video_dir, state)


def new_state(slug: str, channel: str, title: str) -> dict:
    return {
        "slug": slug,
        "channel": channel,
        "title": title,
        "status": "draft",
        "created": now(),
        "shots": [],
        "stages": {},
    }
