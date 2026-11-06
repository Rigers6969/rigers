"""Real video clips (b-roll) for a shot, from Pexels Videos and Pixabay Videos (both free, need a free key).

For each shot it asks both sites at once, picks the clip whose title/tags match the shot best, and
downloads ONE file in about 1080p (not 4K) - 5-15 MB instead of 100+ MB. Shots about old history
("1920s", "Victorian", "ancient"...) are skipped on purpose: modern stock video looks wrong there,
and old photos look right.

Keys come from the environment (PEXELS_API_KEY, PIXABAY_API_KEY), e.g. the .env file the
Autopilot page writes. Without keys this module does nothing.
"""
from __future__ import annotations

import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import requests

PEXELS_URL = "https://api.pexels.com/videos/search"
PIXABAY_URL = "https://pixabay.com/api/videos/"
UA = "WayneFactory/1.0 (personal video tool)"
OLD = re.compile(r"\b(1[0-8]\d\d|19[0-5]\d)s?\b|ancient|medieval|victorian|century|roman empire|pharaoh|"
                 r"vintage|archival|historic|old photo|black and white|world war|wwi|wwii|colonial", re.I)


def have_keys() -> bool:
    return bool(os.environ.get("PEXELS_API_KEY") or os.environ.get("PIXABAY_API_KEY"))


def is_historical(description: str) -> bool:
    return bool(OLD.search(description or ""))


def _pexels(query: str, portrait: bool) -> list[dict]:
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        return []
    r = requests.get(PEXELS_URL, params={"query": query[:100], "per_page": 12, "orientation": "portrait" if portrait else "landscape"},
                     headers={"Authorization": key, "User-Agent": UA}, timeout=20)
    r.raise_for_status()
    target = 1080 if portrait else 1920
    out = []
    for v in r.json().get("videos") or []:
        files = [f for f in v.get("video_files") or [] if f.get("file_type") == "video/mp4" and f.get("link") and f.get("width")]
        if not files or (v.get("duration") or 0) < 3:
            continue
        okay = [f for f in files if f["width"] <= target * 1.1] or files  # about 1080p, not 4K
        best = min(okay, key=lambda f: abs(f["width"] - target))
        slug = re.sub(r"-\d+/?$", "", (v.get("url") or "").rstrip("/").rsplit("/", 1)[-1])
        out.append({"source": "pexels_video", "id": f"pexels-{v.get('id')}", "title": slug.replace("-", " "),
                    "url": best["link"], "width": best.get("width"), "height": best.get("height"),
                    "duration": v.get("duration"), "page": v.get("url", ""),
                    "credit": f"Video by {(v.get('user') or {}).get('name', 'unknown')} on Pexels ({v.get('url', '')})",
                    "license": "Pexels License", "license_url": "https://www.pexels.com/license/"})
    return out


def _pixabay(query: str, portrait: bool) -> list[dict]:
    key = os.environ.get("PIXABAY_API_KEY", "")
    if not key:
        return []
    r = requests.get(PIXABAY_URL, params={"key": key, "q": query[:100], "per_page": 12, "safesearch": "true"},
                     headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    out = []
    for h in r.json().get("hits") or []:
        vids = h.get("videos") or {}
        pick = None
        for size in ("large", "medium", "small"):
            f = vids.get(size) or {}
            if f.get("url") and 0 < (f.get("width") or 0) <= 2000:
                pick = f
                break
        if not pick or (h.get("duration") or 0) < 3:
            continue
        if portrait and (pick.get("height") or 0) <= (pick.get("width") or 0):
            continue  # Pixabay has no orientation filter; vertical Shorts want vertical clips
        out.append({"source": "pixabay_video", "id": f"pixabay-{h.get('id')}", "title": h.get("tags", ""),
                    "url": pick["url"], "width": pick.get("width"), "height": pick.get("height"),
                    "duration": h.get("duration"), "page": h.get("pageURL", ""),
                    "credit": f"Video by {h.get('user', 'unknown')} on Pixabay ({h.get('pageURL', '')})",
                    "license": "Pixabay Content License", "license_url": "https://pixabay.com/service/license-summary/"})
    return out


def search(query: str, portrait: bool = False) -> list[dict]:
    """Both sites at the same time; a site that fails is just skipped."""
    def safe(fn):
        try:
            return fn(query, portrait)
        except Exception:
            return []
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.map(safe, (_pexels, _pixabay))
    return a + b


def download(clip: dict, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / (hashlib.sha1(clip["url"].encode()).hexdigest()[:20] + ".mp4")
    if path.exists() and path.stat().st_size > 0:
        return path
    tmp = path.with_suffix(".part")
    with requests.get(clip["url"], headers={"User-Agent": UA}, timeout=60, stream=True) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    tmp.replace(path)
    return path


def best_clip(description: str, similarity, used: set, portrait: bool = False, min_similarity: float = 0.25) -> Optional[dict]:
    """The best-matching clip not used yet in this video, or None."""
    if not have_keys() or is_historical(description):
        return None
    clips = [c for c in search(description, portrait) if c["id"] not in used]
    if not clips:
        return None
    titles = [c["title"] for c in clips]
    scores = similarity.score_many(description, titles) if hasattr(similarity, "score_many") \
        else [similarity.score(description, t) for t in titles]
    score, clip = max(zip(scores, clips), key=lambda x: x[0])
    if score < min_similarity:
        return None
    clip["similarity"] = score
    return clip
