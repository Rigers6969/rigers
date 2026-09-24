"""Logs every rejected candidate with its reason, so quality thresholds in
config.yaml can be tuned by looking at what got dropped and why - hard
rejects (size/aspect-ratio/watermark/duplicate), download/decode failures,
missing licensing, and candidates that scored below the top-N cutoff."""
from __future__ import annotations

import csv
from pathlib import Path

from .models import RawCandidate

FIELDNAMES = ["shot_id", "shot_description", "source", "media_id", "title", "direct_url", "reason"]


class RejectionLog:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=FIELDNAMES)
        self._writer.writeheader()

    def reject(self, shot_id: str, shot_description: str, candidate: RawCandidate, reason: str) -> None:
        self._writer.writerow({
            "shot_id": shot_id,
            "shot_description": shot_description,
            "source": candidate.source,
            "media_id": candidate.media_id,
            "title": candidate.title,
            "direct_url": candidate.direct_url,
            "reason": reason,
        })
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "RejectionLog":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
