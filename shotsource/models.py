"""Shared data models passed between sources, the quality filter, and the
manifest/output writer."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Shot:
    id: str
    description: str


@dataclass
class RawCandidate:
    """One media item as returned by a source's search - before download,
    hard-reject checks, or scoring."""

    source: str
    media_id: str
    title: str
    direct_url: str
    landing_url: str
    license: str
    license_url: str
    attribution: str
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class ScoredCandidate:
    """A candidate that survived hard-reject and has been downloaded and
    scored. `local_path` starts as the cache path and is rewritten to the
    final per-shot output path once it's copied there."""

    candidate: RawCandidate
    local_path: str
    width: int
    height: int
    resolution_score: float
    sharpness_score: float
    caption_similarity_score: float
    final_score: float
