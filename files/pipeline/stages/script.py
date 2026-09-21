"""Script stage — placeholder.

You write the script with Claude and drop it in as script.md, then list the
shots in project.json. This stage just validates that both exist.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from pipeline import state as st

log = logging.getLogger(__name__)

SHOT_RE = re.compile(r"^\s*(\d+)\.\s*\*(.+?)\*", re.M)


def run(video_dir: Path, config: dict) -> None:
    video_dir = Path(video_dir)
    s = st.load(video_dir)
    if st.is_done(s, "script"):
        log.info("script: already done, skipping")
        return

    path = video_dir / "script.md"
    if not path.exists():
        raise FileNotFoundError(f"Write the script to {path} first.")

    text = path.read_text(encoding="utf-8")
    if not s.get("shots"):
        # best-effort: pull numbered italic shot lines out of the script
        found = SHOT_RE.findall(text)
        s["shots"] = [
            {"n": i + 1, "description": d.strip()[:120], "query_terms": ""}
            for i, (_, d) in enumerate(found)
        ]
        log.info("script: extracted %d shots", len(s["shots"]))

    words = len(text.split())
    st.mark_done(video_dir, s, "script", words=words, shots=len(s["shots"]))
