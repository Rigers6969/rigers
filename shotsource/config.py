"""Loads shotsource.config.default.yaml and deep-merges an optional
user-supplied YAML file on top of it, then builds typed dataclasses so the
rest of the codebase gets attribute access with real defaults instead of
scattered dict.get() calls.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PACKAGE_DIR / "config.default.yaml"


@dataclass
class SourceConfig:
    enabled: bool = True
    requests_per_minute: float = 20.0
    max_results_per_shot: int = 30
    api_key_env: str = ""


@dataclass
class HardRejectConfig:
    min_width_px: int = 1920
    aspect_ratio_min: float = 1.2
    aspect_ratio_max: float = 2.4
    dedup_hamming_threshold: int = 5
    watermark_keywords: list = field(default_factory=list)
    watermark_edge_density_multiplier: float = 2.5


@dataclass
class ScoringWeights:
    resolution: float = 0.3
    sharpness: float = 0.3
    caption_similarity: float = 0.4


@dataclass
class ScoringConfig:
    weights: ScoringWeights = field(default_factory=ScoringWeights)
    resolution_reference_width_px: float = 3840.0
    sharpness_reference_variance: float = 800.0
    embedding_model: str = "all-MiniLM-L6-v2"


@dataclass
class QualityConfig:
    hard_reject: HardRejectConfig = field(default_factory=HardRejectConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)


@dataclass
class HttpConfig:
    user_agent: str = "shotsource-cli/1.0"
    timeout_seconds: float = 30.0


@dataclass
class Config:
    output_dir: str = "./shot_media_output"
    cache_dir: str = "./.shotsource_cache"
    cache_ttl_hours: float = 168.0
    top_n_per_shot: int = 5
    sources: dict = field(default_factory=dict)
    quality: QualityConfig = field(default_factory=QualityConfig)
    http: HttpConfig = field(default_factory=HttpConfig)


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _build_config(data: dict) -> Config:
    sources = {name: SourceConfig(**(cfg or {})) for name, cfg in (data.get("sources") or {}).items()}

    quality_data = data.get("quality") or {}
    hard_reject_data = quality_data.get("hard_reject") or {}
    scoring_data = dict(quality_data.get("scoring") or {})
    weights_data = scoring_data.pop("weights", {}) or {}

    quality = QualityConfig(
        hard_reject=HardRejectConfig(**hard_reject_data),
        scoring=ScoringConfig(weights=ScoringWeights(**weights_data), **scoring_data),
    )
    http = HttpConfig(**(data.get("http") or {}))

    defaults = Config()
    return Config(
        output_dir=data.get("output_dir", defaults.output_dir),
        cache_dir=data.get("cache_dir", defaults.cache_dir),
        cache_ttl_hours=data.get("cache_ttl_hours", defaults.cache_ttl_hours),
        top_n_per_shot=data.get("top_n_per_shot", defaults.top_n_per_shot),
        sources=sources,
        quality=quality,
        http=http,
    )


def load_config(path: Optional[str] = None) -> Config:
    """Loads the packaged defaults and deep-merges `path` (if given) on top,
    so a user's config only needs to list the values they want to change."""
    with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
        merged = yaml.safe_load(f) or {}
    if path:
        with open(path, "r", encoding="utf-8") as f:
            override = yaml.safe_load(f) or {}
        merged = _deep_merge(merged, override)
    return _build_config(merged)
