"""Rough-cut stage — place one shot per narration beat, emit an FCP7 XML
that Premiere imports. Stub: writes the edit plan, XML export is next.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from pipeline import state as st

log = logging.getLogger(__name__)


def run(video_dir: Path, config: dict) -> None:
    video_dir = Path(video_dir)
    s = st.load(video_dir)
    if st.is_done(s, "cut"):
        log.info("cut: already done, skipping")
        return

    timings_path = video_dir / "audio" / "timings.json"
    if not timings_path.exists():
        raise FileNotFoundError("Run the transcribe stage first — the cut needs timings.")

    words = json.loads(timings_path.read_text(encoding="utf-8"))
    shots = s.get("shots") or []
    if not shots:
        raise ValueError("No shots to place.")

    duration = words[-1]["end"] if words else 0.0
    per_shot = duration / len(shots)
    plan = [
        {
            "shot": sh["n"],
            "start": round(i * per_shot, 2),
            "end": round((i + 1) * per_shot, 2),
            "folder": f"media/shot-{sh['n']:02d}",
        }
        for i, sh in enumerate(shots)
    ]

    out_dir = video_dir / "cut"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "edit_plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    st.mark_done(video_dir, s, "cut", duration=round(duration, 2), shots=len(plan))
