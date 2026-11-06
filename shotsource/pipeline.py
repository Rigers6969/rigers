"""Orchestrates one run: parse the shot list, query every enabled source
for each shot, run everything that comes back through the quality filter,
keep the top N per shot, and write the per-shot folders + manifest.csv +
rejections.csv.
"""
from __future__ import annotations

import copy
import json
import logging
import re
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional

from .cache import CachedSession, DiskCache, RateLimiter
from .config import Config, load_config
from .manifest import manifest_row, write_manifest
from .models import RawCandidate, ScoredCandidate, Shot
from .quality import combine_scores, hard_reject_reason, load_image_info, resolution_score, sharpness_score, sharpness_variance
from .rejection_log import RejectionLog
from .similarity import CaptionSimilarityScorer
from .sources.archive_org import ArchiveOrgSource
from .sources.base import BaseSource
from .sources.flickr import FlickrSource
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
    "flickr": FlickrSource,
}

_DEFAULT_API_KEY_ENV = {
    "pexels": "PEXELS_API_KEY",
    "pixabay": "PIXABAY_API_KEY",
    "unsplash": "UNSPLASH_ACCESS_KEY",
    "flickr": "FLICKR_API_KEY",
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
        http = CachedSession(cache, rate_limiter, config.http.user_agent, config.http.timeout_seconds,
                             limit_downloads=name == "loc")
        default_env = _DEFAULT_API_KEY_ENV.get(name)
        kwargs = {"api_key_env": src_config.api_key_env or default_env} if default_env else {}
        sources[name] = cls(http, src_config.max_results_per_shot, **kwargs)
    return sources


def _slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[-\s]+", "-", text)
    return text[:max_len] or "shot"


def _collect_candidates(shot: Shot, sources: Dict[str, BaseSource]) -> List[RawCandidate]:
    """Asks every source at the same time (each still keeps its own rate limit)."""
    def ask(item):
        name, source = item
        try:
            found = source.search(shot.description)
        except Exception as exc:
            logger.warning("source %s failed for shot %r: %s", name, shot.description, exc)
            return []
        logger.debug("source %s returned %d candidates for shot %r", name, len(found), shot.description)
        return found

    candidates: List[RawCandidate] = []
    if not sources:
        return candidates
    with ThreadPoolExecutor(max_workers=len(sources)) as pool:
        for found in pool.map(ask, sources.items()):  # map keeps the source order
            candidates.extend(found)
    return candidates


def _caption_scores(similarity, description: str, titles: List[str]) -> List[float]:
    if hasattr(similarity, "score_many"):
        return similarity.score_many(description, titles)
    return [similarity.score(description, t) for t in titles]


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

    # 1. Free checks first (licence, title relevance) - no download needed for those.
    licensed = []
    for candidate in candidates:
        if not candidate.license.strip() or candidate.license.strip().upper() == "UNKNOWN":
            reject_log.reject(shot.id, shot.description, candidate, "license missing or unclear")
            continue
        licensed.append(candidate)
    caption_of = dict(zip(map(id, licensed), _caption_scores(similarity, shot.description, [c.title for c in licensed])))
    relevant = []
    for candidate in licensed:
        cs = caption_of[id(candidate)]
        if cs < scoring_cfg.min_caption_similarity:
            reject_log.reject(
                shot.id, shot.description, candidate,
                f"not relevant to shot ({cs:.2f} similarity below {scoring_cfg.min_caption_similarity} minimum)",
            )
        else:
            relevant.append(candidate)
    # 2. Download only the most relevant few, several at once.
    relevant.sort(key=lambda c: caption_of[id(c)], reverse=True)
    keep = max(config.top_n_per_shot * 3, 12)
    for candidate in relevant[keep:]:
        reject_log.reject(shot.id, shot.description, candidate, "not downloaded: weaker title match than the best ones")
    relevant = relevant[:keep]

    def fetch(candidate):
        try:
            return sources.get(candidate.source).http.get_binary(candidate.direct_url), None
        except Exception as exc:
            return None, exc

    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(fetch, relevant))

    # 3. Quality checks in relevance order; stop once there are plenty of good ones.
    for candidate, (local_path, error) in zip(relevant, fetched):
        if len(scored) >= config.top_n_per_shot * 2:
            reject_log.reject(shot.id, shot.description, candidate, "skipped: enough good images already")
            continue
        if error is not None:
            reject_log.reject(shot.id, shot.description, candidate, f"download failed: {error}")
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

        caption_score = caption_of[id(candidate)]

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


def _clip_row(shot: Shot, clip: dict, path: Path) -> dict:
    return {
        "shot_id": shot.id, "shot_description": shot.description, "rank": 1, "source": clip["source"],
        "media_id": clip["id"], "title": clip["title"], "source_url": clip["page"], "direct_url": clip["url"],
        "license": clip["license"], "license_url": clip["license_url"], "attribution": clip["credit"],
        "width": clip.get("width") or "", "height": clip.get("height") or "", "resolution_score": "", "sharpness_score": "",
        "caption_similarity_score": round(clip.get("similarity", 0), 4), "final_score": round(clip.get("similarity", 0), 4),
        "local_path": str(path),
    }


def run_shot(
    shot: Shot,
    sources: Dict[str, BaseSource],
    similarity: CaptionSimilarityScorer,
    config: Config,
    output_dir: Path,
    reject_log: RejectionLog,
    clips: Optional[dict] = None,
) -> List[dict]:
    if clips is not None:
        # A real video clip first (modern topics only); if one fits, the slow photo search is skipped.
        from . import video_clips

        try:
            clip = video_clips.best_clip(shot.description, similarity, clips["used"], portrait=clips["portrait"])
            if clip:
                src = video_clips.download(clip, Path(config.cache_dir) / "clips")
                shot_dir = output_dir / _slugify(f"{shot.id}-{shot.description}")
                shot_dir.mkdir(parents=True, exist_ok=True)
                dest = shot_dir / f"01_{clip['source']}_{_slugify(clip['id'], 20)}.mp4"
                shutil.copyfile(src, dest)
                clips["used"].add(clip["id"])
                return [_clip_row(shot, clip, dest)]
        except Exception as exc:
            logger.warning("video clip search failed for %r: %s", shot.description, exc)
    candidates = _collect_candidates(shot, sources)
    scored = _score_candidates(shot, candidates, sources, similarity, config, reject_log)

    if not scored and candidates:
        # Nothing cleared the normal relevance floor - rather than leaving
        # this shot with zero media (which breaks the final assembly, not
        # just looks sparse), retry once against the same already-fetched
        # candidates with a relaxed floor. Re-scoring hits the on-disk
        # cache, not the network, so this doesn't cost extra API calls.
        logger.info("  shot %s: 0 matches at normal threshold, retrying relaxed", shot.id)
        relaxed_config = copy.deepcopy(config)
        relaxed_config.quality.scoring.min_caption_similarity /= 2
        scored = _score_candidates(shot, candidates, sources, similarity, relaxed_config, reject_log)

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


def run_pipeline(
    shots_path: str,
    config_path: Optional[str] = None,
    output_dir_override: Optional[str] = None,
    progress: Optional[Callable[[str], None]] = None,
    video_clips: bool = True,
    portrait: bool = False,
) -> Path:
    """progress, if given, is called once per shot (not per source/candidate -
    that would be too chatty) so a caller running this as a long background
    job can show real movement instead of one static "searching..." message
    for the whole run, which otherwise looks identical whether it's working
    normally or actually stuck."""
    def report(msg: str) -> None:
        if progress:
            progress(msg)

    config = load_config(config_path)
    output_dir = Path(output_dir_override or config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cache = DiskCache(Path(config.cache_dir), config.cache_ttl_hours)
    sources = build_sources(config, cache)
    similarity = CaptionSimilarityScorer(config.quality.scoring.embedding_model)

    shots = parse_shots(shots_path)
    if not shots:
        raise ValueError(f"No shots found in {shots_path}")

    from . import video_clips as _vc

    clips = {"used": set(), "portrait": portrait} if video_clips and _vc.have_keys() else None
    if clips is not None:
        report("Video clips: on (Pexels/Pixabay) - photos are used for old-history shots and when no clip fits.")
    all_rows: List[dict] = []
    with RejectionLog(output_dir / "rejections.csv") as reject_log:
        for i, shot in enumerate(shots, start=1):
            report(f"Shot {i}/{len(shots)}: searching for \"{shot.description[:60]}\"...")
            logger.info("Processing shot %s: %s", shot.id, shot.description)
            rows = run_shot(shot, sources, similarity, config, output_dir, reject_log, clips=clips)
            all_rows.extend(rows)
            logger.info("  -> kept %d (of up to %d) for %s", len(rows), config.top_n_per_shot, shot.id)
            kind = "video clip" if rows and rows[0]["local_path"].endswith(".mp4") else f"{len(rows)} photo(s)"
            report(f"Shot {i}/{len(shots)}: kept {kind}.")

    manifest_path = output_dir / "manifest.csv"
    write_manifest(manifest_path, all_rows)
    logger.info("Wrote manifest with %d rows to %s", len(all_rows), manifest_path)
    return manifest_path
