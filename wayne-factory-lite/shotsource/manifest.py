"""CSV manifest writer for the media kept for each shot."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .models import ScoredCandidate

FIELDNAMES = [
    "shot_id", "shot_description", "rank", "source", "media_id", "title",
    "source_url", "direct_url", "license", "license_url", "attribution",
    "width", "height", "resolution_score", "sharpness_score",
    "caption_similarity_score", "final_score", "local_path",
]


def manifest_row(shot_id: str, shot_description: str, rank: int, scored: ScoredCandidate) -> dict:
    c = scored.candidate
    return {
        "shot_id": shot_id,
        "shot_description": shot_description,
        "rank": rank,
        "source": c.source,
        "media_id": c.media_id,
        "title": c.title,
        "source_url": c.landing_url,
        "direct_url": c.direct_url,
        "license": c.license,
        "license_url": c.license_url,
        "attribution": c.attribution,
        "width": scored.width,
        "height": scored.height,
        "resolution_score": round(scored.resolution_score, 4),
        "sharpness_score": round(scored.sharpness_score, 4),
        "caption_similarity_score": round(scored.caption_similarity_score, 4),
        "final_score": round(scored.final_score, 4),
        "local_path": scored.local_path,
    }


def write_manifest(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
