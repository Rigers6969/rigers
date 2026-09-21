"""Metadata stage — chapters from timings, description scaffold, attribution
block assembled from the media manifest.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from pipeline import state as st

log = logging.getLogger(__name__)


def hhmmss(seconds: float) -> str:
    m, sec = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{sec:02d}" if h else f"{m:d}:{sec:02d}"


def run(video_dir: Path, config: dict) -> None:
    video_dir = Path(video_dir)
    s = st.load(video_dir)
    if st.is_done(s, "meta"):
        log.info("meta: already done, skipping")
        return

    out_dir = video_dir / "meta"
    out_dir.mkdir(exist_ok=True)

    chapters = []
    plan_path = video_dir / "cut" / "edit_plan.json"
    if plan_path.exists():
        for entry in json.loads(plan_path.read_text(encoding="utf-8")):
            chapters.append(f"{hhmmss(entry['start'])} Shot {entry['shot']}")

    credits = []
    manifest = video_dir / "media" / "manifest.csv"
    if manifest.exists():
        with manifest.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("attribution"):
                    credits.append(f"{row['attribution']} ({row['licence']}) {row['source_url']}")

    meta = {
        "title": s.get("title", ""),
        "channel": s.get("channel", ""),
        "chapters": chapters,
        "credits": sorted(set(credits)),
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    st.mark_done(video_dir, s, "meta", chapters=len(chapters), credits=len(meta["credits"]))
