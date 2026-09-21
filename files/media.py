"""Fetch openly-licensed media per shot, filter for quality, keep the best few.

Queries the Openverse API only (add other sources once the filter is tuned).
Never scrapes: everything returned carries a licence.
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import time
from pathlib import Path

import requests
from PIL import Image

from pipeline import state as st

log = logging.getLogger(__name__)

OPENVERSE = "https://api.openverse.org/v1/images/"
UA = {"User-Agent": "video-pipeline/0.1 (personal documentary project)"}


def slugify(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:limit].rstrip("-") or "shot"


def search(query: str, per_page: int, cfg: dict) -> list[dict]:
    params = {
        "q": query,
        "page_size": per_page,
        "license_type": cfg.get("license_type", "commercial,modification"),
        "mature": "false",
    }
    r = requests.get(OPENVERSE, params=params, headers=UA, timeout=30)
    r.raise_for_status()
    return r.json().get("results", [])


def sharpness(img: Image.Image) -> float:
    """Variance-of-Laplacian, computed with Pillow only (no OpenCV needed)."""
    from PIL import ImageFilter

    g = img.convert("L").resize((512, 512))
    lap = g.filter(ImageFilter.FIND_EDGES)
    px = list(lap.getdata())
    mean = sum(px) / len(px)
    return sum((p - mean) ** 2 for p in px) / len(px)


def phash(img: Image.Image) -> str:
    g = img.convert("L").resize((16, 16))
    px = list(g.getdata())
    avg = sum(px) / len(px)
    bits = "".join("1" if p > avg else "0" for p in px)
    return hashlib.md5(bits.encode()).hexdigest()[:16]


def assess(raw: bytes, cfg: dict) -> tuple[bool, str, dict]:
    """Return (keep, reason, metrics). Reason explains every rejection."""
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        return False, f"unreadable ({exc.__class__.__name__})", {}

    w, h = img.size
    ratio = w / h if h else 0
    m = {"width": w, "height": h, "ratio": round(ratio, 3)}

    if w < cfg["min_width"]:
        return False, f"too small ({w}px < {cfg['min_width']})", m
    lo, hi = cfg["ratio_range"]
    if not (lo <= ratio <= hi):
        return False, f"aspect {ratio:.2f} outside {lo}-{hi}", m

    sharp = sharpness(img)
    m["sharpness"] = round(sharp, 1)
    if sharp < cfg["min_sharpness"]:
        return False, f"blurry ({sharp:.0f} < {cfg['min_sharpness']})", m

    m["phash"] = phash(img)
    m["score"] = round(min(w / 3840, 1.0) * 60 + min(sharp / 2000, 1.0) * 40, 1)
    return True, "ok", m


def run(video_dir: Path, config: dict) -> None:
    video_dir = Path(video_dir)
    s = st.load(video_dir)
    if st.is_done(s, "media"):
        log.info("media: already done, skipping")
        return

    cfg = config["media"]
    shots = s.get("shots") or []
    if not shots:
        raise ValueError("No shots in project.json — run the script stage first.")

    root = video_dir / "media"
    rejects = root / "rejected"
    root.mkdir(parents=True, exist_ok=True)
    rejects.mkdir(exist_ok=True)
    cache = Path(config["paths"]["cache"])
    cache.mkdir(parents=True, exist_ok=True)

    rows, seen_hashes, kept_total = [], set(), 0

    for shot in shots:
        n = shot["n"]
        query = shot.get("query_terms") or shot["description"]
        folder = root / f"shot-{n:02d}-{slugify(shot['description'])}"
        folder.mkdir(exist_ok=True)
        log.info("shot %02d: searching %r", n, query)

        try:
            results = search(query, cfg["candidates_per_shot"], cfg)
        except Exception as exc:
            log.warning("shot %02d: search failed (%s)", n, exc)
            continue

        scored, rank = [], 0
        for item in results:
            url = item.get("url")
            if not url:
                continue
            key = cache / (hashlib.sha1(url.encode()).hexdigest() + ".bin")
            try:
                if key.exists():
                    raw = key.read_bytes()
                else:
                    resp = requests.get(url, headers=UA, timeout=45)
                    resp.raise_for_status()
                    raw = resp.content
                    key.write_bytes(raw)
                    time.sleep(cfg["delay_seconds"])
            except Exception as exc:
                log.debug("  fetch failed: %s", exc)
                continue

            keep, reason, m = assess(raw, cfg)
            if keep and m["phash"] in seen_hashes:
                keep, reason = False, "duplicate of an earlier image"
            if not keep:
                (rejects / f"shot-{n:02d}-{slugify(reason, 30)}.jpg").write_bytes(raw[:2_000_000])
                log.info("  reject: %s", reason)
                continue
            seen_hashes.add(m["phash"])
            scored.append((m["score"], item, raw, m))

        scored.sort(key=lambda t: -t[0])
        for score, item, raw, m in scored[: cfg["keep_per_shot"]]:
            rank += 1
            name = f"{rank:02d}-{slugify(item.get('source', 'src'), 20)}.jpg"
            (folder / name).write_bytes(raw)
            rows.append({
                "shot": n,
                "file": str((folder / name).relative_to(video_dir)),
                "source_url": item.get("foreign_landing_url") or item.get("url"),
                "provider": item.get("source"),
                "licence": f"{item.get('license')} {item.get('license_version') or ''}".strip(),
                "attribution": item.get("attribution") or item.get("creator") or "",
                "score": m["score"],
                "width": m["width"],
                "sharpness": m.get("sharpness"),
            })
            kept_total += 1
        log.info("shot %02d: kept %d", n, rank)

    manifest = root / "manifest.csv"
    if rows:
        with manifest.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    st.mark_done(video_dir, s, "media", kept=kept_total, manifest=str(manifest.name))
    log.info("media: kept %d files across %d shots", kept_total, len(shots))
