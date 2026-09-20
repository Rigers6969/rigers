"""Disk cache + rate limiting for outbound requests to the media source
APIs. Every source module goes through a CachedSession so re-running the
CLI while tuning quality thresholds doesn't re-hit the same API endpoints
or re-download the same images, and so each source respects its own
requests-per-minute limit.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from threading import Lock
from typing import Optional

import requests


class RateLimiter:
    """Blocks in wait() just long enough to keep calls to roughly
    `requests_per_minute` on average - a simple fixed-interval limiter,
    not a bursty token bucket, since these are polite API clients, not a
    load test."""

    def __init__(self, requests_per_minute: float):
        self._min_interval = 60.0 / requests_per_minute if requests_per_minute > 0 else 0.0
        self._lock = Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        with self._lock:
            remaining = self._min_interval - (time.monotonic() - self._last_call)
            if remaining > 0:
                time.sleep(remaining)
            self._last_call = time.monotonic()


def _hash_key(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


class DiskCache:
    """Content-addressable cache split into two kinds of entries: JSON API
    responses (keyed by request URL+params, expire after `ttl_hours`) and
    downloaded images (keyed by their source URL, kept indefinitely since
    the same URL always means the same bytes)."""

    def __init__(self, cache_dir: Path, ttl_hours: float):
        self.json_dir = cache_dir / "json"
        self.image_dir = cache_dir / "images"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_hours * 3600.0

    def get_json(self, cache_key: str) -> Optional[dict]:
        path = self.json_dir / f"{cache_key}.json"
        if not path.exists():
            return None
        if self.ttl_seconds > 0 and time.time() - path.stat().st_mtime > self.ttl_seconds:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def put_json(self, cache_key: str, data: dict) -> None:
        path = self.json_dir / f"{cache_key}.json"
        path.write_text(json.dumps(data), encoding="utf-8")

    def image_path_for(self, url: str) -> Path:
        ext = Path(url.split("?")[0]).suffix
        if not ext or len(ext) > 6:
            ext = ".jpg"
        return self.image_dir / f"{_hash_key(url)}{ext}"

    @staticmethod
    def key_for(*parts: str) -> str:
        return _hash_key(*parts)


class CachedSession:
    """What source modules actually call: get_json() for API search/lookup
    calls, get_binary() to download (or reuse a cached copy of) an image."""

    def __init__(self, cache: DiskCache, rate_limiter: RateLimiter, user_agent: str, timeout: float):
        self.cache = cache
        self.rate_limiter = rate_limiter
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.timeout = timeout

    def get_json(self, url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> dict:
        params = params or {}
        cache_key = DiskCache.key_for(url, json.dumps(params, sort_keys=True, default=str))
        cached = self.cache.get_json(cache_key)
        if cached is not None:
            return cached
        self.rate_limiter.wait()
        resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        self.cache.put_json(cache_key, data)
        return data

    def get_binary(self, url: str) -> Path:
        path = self.cache.image_path_for(url)
        if path.exists() and path.stat().st_size > 0:
            return path
        self.rate_limiter.wait()
        resp = self.session.get(url, timeout=self.timeout, stream=True)
        resp.raise_for_status()
        tmp_path = path.with_suffix(path.suffix + ".part")
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        tmp_path.replace(path)
        return path
