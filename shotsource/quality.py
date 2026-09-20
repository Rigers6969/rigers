"""Hard-reject and scoring logic for downloaded candidate images.

Kept as pure functions operating on already-loaded image data wherever
possible, so this can be unit tested with synthetic images and no network
access.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import cv2
import imagehash
import numpy as np
from PIL import Image

from .config import HardRejectConfig, ScoringWeights


@dataclass
class ImageInfo:
    width: int
    height: int
    gray: np.ndarray
    phash: imagehash.ImageHash


def load_image_info(path: str) -> ImageInfo:
    pil_image = Image.open(path).convert("RGB")
    width, height = pil_image.size
    gray = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2GRAY)
    phash = imagehash.phash(pil_image)
    return ImageInfo(width=width, height=height, gray=gray, phash=phash)


def sharpness_variance(gray: np.ndarray) -> float:
    """Variance of the Laplacian - the standard cheap sharpness proxy: a
    blurry image has few strong edges, so its second-derivative response
    has low variance."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def has_watermark_keyword(text: str, keywords: List[str]) -> bool:
    lowered = (text or "").lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def has_watermark_band(gray: np.ndarray, multiplier: float) -> bool:
    """Heuristic, not a trained detector: stock-photo watermarks are
    usually a horizontal band of dense, high-contrast text/logo edges
    across the vertical center or the bottom strip. Flags an image whose
    edge density in those bands is anomalously high relative to its own
    overall average - tune `multiplier` via config if it misfires."""
    edges = cv2.Canny(gray, 100, 200)
    height = edges.shape[0]
    overall_density = edges.mean()
    if overall_density <= 0:
        return False
    band_specs = [
        (0.40, 0.60),  # centered band - common diagonal-watermark placement
        (0.85, 1.00),  # bottom strip - common caption/credit watermark placement
    ]
    for start_frac, end_frac in band_specs:
        start, end = int(height * start_frac), int(height * end_frac)
        if end <= start:
            continue
        band_density = edges[start:end, :].mean()
        if band_density >= overall_density * multiplier:
            return True
    return False


def hard_reject_reason(
    info: ImageInfo,
    title: str,
    config: HardRejectConfig,
    seen_hashes: List[imagehash.ImageHash],
) -> Optional[str]:
    """Returns a human-readable rejection reason, or None if the image
    survives every hard-reject check."""
    if info.width < config.min_width_px:
        return f"width {info.width}px below minimum {config.min_width_px}px"

    aspect = info.width / info.height if info.height else 0.0
    if not (config.aspect_ratio_min <= aspect <= config.aspect_ratio_max):
        return f"aspect ratio {aspect:.2f} outside [{config.aspect_ratio_min}, {config.aspect_ratio_max}]"

    if has_watermark_keyword(title, config.watermark_keywords):
        return "watermark keyword found in title/caption"

    if has_watermark_band(info.gray, config.watermark_edge_density_multiplier):
        return "possible watermark detected (edge-density heuristic)"

    for seen in seen_hashes:
        distance = info.phash - seen
        if distance <= config.dedup_hamming_threshold:
            return f"duplicate perceptual hash (hamming distance {distance} <= {config.dedup_hamming_threshold})"

    return None


def resolution_score(width: int, reference_width: float) -> float:
    if reference_width <= 0:
        return 1.0
    return min(width / reference_width, 1.0)


def sharpness_score(variance: float, reference_variance: float) -> float:
    if reference_variance <= 0:
        return 1.0
    return min(variance / reference_variance, 1.0)


def combine_scores(resolution: float, sharpness: float, caption_similarity: float, weights: ScoringWeights) -> float:
    return (
        weights.resolution * resolution
        + weights.sharpness * sharpness
        + weights.caption_similarity * caption_similarity
    )
