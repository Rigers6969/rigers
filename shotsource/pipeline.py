"""Orchestrates one run: parse the shot list, query every enabled source
for each shot, run everything that comes back through the quality filter,
keep the top N per shot, and write the per-shot folders + manifest.csv +
rejections.csv.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from .cache import CachedSession, DiskCache, RateLimiter
from .config import Config, load_config
from .manifest import manifest_row, write_manifest
from .models import RawCandidate, ScoredCandidate, Shot
from .quality import combine_scores, hard_reject_reason, load_image_info, resolution_score, sharpness_score, sharpness_variance
from .rejection_log import RejectionLog
from .similarity import CaptionSimilarityScorer
from .sources.archive_org import ArchiveOrgSource
from .sources.base import BaseSource
from .sources.loc import LocSource
from .sources.openverse import OpenverseSource
from .sources.pexels import PexelsSource
from .sources.pixabay import PixabaySource
from .sources.unsplash import UnsplashSource
from .sources.wikimedia import WikimediaSource

logger = logging.getLogger("shotsource")

SOURCE_CLASSES = {
    "openverse": OpenverseSource,
    "wikimedia": WikimediaSource,
    "loc": LocSource,
    "archive_org": ArchiveOrgSource,
    "pexels": PexelsSource,
    "pixabay": PixabaySource,
    "unsplash": UnsplashSource,
}

_DEFAULT_API_KEY_ENV = {
    "pexels": "PEXELS_API_KEY",
    "pixabay": "PIXABAY_API_KEY",
    "unsplash": "UNSPLASH_ACCESS_KEY",
}


def parse_shots(path: str) -> List[Shot]:
    """Reads a shot list from JSON (a list of strings, or a list of
    {"id": ..., "description": ...} objects) or from markdown/plain text
    (one shot per bullet, numbered item, or non-empty line)."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")

    if p.suffix.lower() == ".json":
        data = json.loads(text)
        shots = []
        for i, item in enumerate(data, start=1):
            if isinstance(item, str):
                shots.append(Shot(id=f"shot-{i:03d}", description=item.strip()))
            elif isinstance(item, dict):
                description = (item.get("description") or item.get("shot") or "").strip()
                shots.append(Shot(id=str(item.get("id", f"shot-{i:03d}")), description=description))
        return [s for s in shots if s.description]

    shots = []
    for line in text.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if cleaned and not cleaned.startswith("#"):
            shots.append(Shot(id=f"shot-{len(shots) + 1:03d}", description=cleaned))
    return shots


def build_sources(config: Config, cache: DiskCache) -> Dict[str, BaseSource]:
    sources: Dict[str, BaseSource] = {}
    for name, cls in SOURCE_CLASSES.items():
        src_config = config.sources.get(name)
        if src_config is None or not src_config.enabled:
            continue
        rate_limiter = RateLimiter(src_config.requests_per_minute)
        http = CachedSession(cache, rate_limiter, config.http.user_agent, config.http.timeout_seconds)
        default_env = _DEFAULT_API_KEY_ENV.get(name)
        kwargs = {"api_key_env": src_config.api_key_env or default_env} if default_env else {}
        sources[name] = cls(http, src_config.max_results_per_shot, **kwargs)
    return sources


def _slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[-\s]+", "-", text)
    return text[:max_len] or "shot"


def _collect_candidates(shot: Shot, sources: Dict[str, BaseSource]) -> List[RawCandidate]:
    candidates: List[RawCandidate] = []
    for name, source in sources.items():
        try:
            found = source.search(shot.description)
        except Exception as exc:
            logger.warning("source %s failed for shot %r: %s", name, shot.description, exc)
            continue
        logger.debug("source %s returned %d candidates for shot %r", name, len(found), shot.description)
        candidates.extend(found)
    return candidates


def _score_candidates(
    shot: Shot,
    candidates: List[RawCandidate],
    sources: Dict[str, BaseSource],
    similarity: CaptionSimilarityScorer,
    config: Config,
    reject_log: RejectionLog,
) -> List[ScoredCandidate]:
    hard_cfg = config.quality.hard_reject
    scoring_cfg = config.quality.scoring
    seen_hashes = []
    scored: List[ScoredCandidate] = []

    for candidate in candidates:
        if not candidate.license.strip() or candidate.license.strip().upper() == "UNKNOWN":
            reject_log.reject(shot.id, shot.description, candidate, "license missing or unclear")
            continue

        source = sources.get(candidate.source)
        try:
            local_path = source.http.get_binary(candidate.direct_url)
        except Exception as exc:
            reject_log.reject(shot.id, shot.description, candidate, f"download failed: {exc}")
            continue

        try:
            info = load_image_info(str(local_path))
        except Exception as exc:
            reject_log.reject(shot.id, shot.description, candidate, f"unreadable image: {exc}")
            continue

        reason = hard_reject_reason(info, candidate.title, hard_cfg, seen_hashes)
        if reason:
            reject_log.reject(shot.id, shot.description, candidate, reason)
            continue
        seen_hashes.append(info.phash)

        caption_score = similarity.score(shot.description, candidate.title)
        if caption_score < scoring_cfg.min_caption_similarity:
            reject_log.reject(
                shot.id, shot.description, candidate,
                f"not relevant to shot ({caption_score:.2f} similarity below {scoring_cfg.min_caption_similarity} minimum)",
            )
            continue

        variance = sharpness_variance(info.gray)
        res_score = resolution_score(info.width, scoring_cfg.resolution_reference_width_px)
        sharp_score = sharpness_score(variance, scoring_cfg.sharpness_reference_variance)
        final = combine_scores(res_score, sharp_score, caption_score, scoring_cfg.weights)

        scored.append(ScoredCandidate(
            candidate=candidate,
            local_path=str(local_path),
            width=info.width,
            height=info.height,
            resolution_score=res_score,
            sharpness_score=sharp_score,
            caption_similarity_score=caption_score,
            final_score=final,
        ))

    return scored


def run_shot(
    shot: Shot,
    sources: Dict[str, BaseSource],
    similarity: CaptionSimilarityScorer,
    config: Config,
    output_dir: Path,
    reject_log: RejectionLog,
) -> List[dict]:
    candidates = _collect_candidates(shot, sources)
    scored = _score_candidates(shot, candidates, sources, similarity, config, reject_log)
    scored.sort(key=lambda s: s.final_score, reverse=True)

    top = scored[: config.top_n_per_shot]
    for dropped in scored[config.top_n_per_shot :]:
        reject_log.reject(shot.id, shot.description, dropped.candidate, "below top-N cutoff after scoring")

    shot_dir = output_dir / _slugify(f"{shot.id}-{shot.description}")
    shot_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for rank, item in enumerate(top, start=1):
        ext = Path(item.local_path).suffix or ".jpg"
        dest = shot_dir / f"{rank:02d}_{item.candidate.source}_{_slugify(item.candidate.media_id, 20)}{ext}"
        shutil.copyfile(item.local_path, dest)
        item.local_path = str(dest)
        rows.append(manifest_row(shot.id, shot.description, rank, item))

    return rows


def run_pipeline(shots_path: str, config_path: Optional[str] = None, output_dir_override: Optional[str] = None) -> Path:
    config = load_config(config_path)
    output_dir = Path(output_dir_override or config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cache = DiskCache(Path(config.cache_dir), config.cache_ttl_hours)
    sources = build_sources(config, cache)
    similarity = CaptionSimilarityScorer(config.quality.scoring.embedding_model)

    shots = parse_shots(shots_path)
    if not shots:
        raise ValueError(f"No shots found in {shots_path}")

    all_rows: List[dict] = []
    with RejectionLog(output_dir / "rejections.csv") as reject_log:
        for shot in shots:
            logger.info("Processing shot %s: %s", shot.id, shot.description)
            rows = run_shot(shot, sources, similarity, config, output_dir, reject_log)
            all_rows.extend(rows)
            logger.info("  -> kept %d (of up to %d) for %s", len(rows), config.top_n_per_shot, shot.id)

    manifest_path = output_dir / "manifest.csv"
    write_manifest(manifest_path, all_rows)
    logger.info("Wrote manifest with %d rows to %s", len(all_rows), manifest_path)
    return manifest_path
