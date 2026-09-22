"""Analyzes a reference YouTube video's editing style and turns it into a
reusable profile - pacing (average shot length, from real scene-cut
detection) plus a qualitative read (captions, zoom style, color) from
Claude's vision on sampled frames. video_assembler.py can then use a
profile's pacing to match its cut rhythm instead of a fixed default.

This does NOT reuse any of the reference video's actual footage/audio in
your output - only the structural pattern (how fast it cuts, whether it
uses captions) is extracted and reapplied to your own materials. That's
the same thing as a human editor studying a competitor's pacing, not a
copyright concern the way reusing their actual clips would be.
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

from json_utils import extract_json_items

APP_DIR = Path(__file__).resolve().parent
STYLE_PROFILES_DIR = APP_DIR / "content" / "_styles"

ProgressCB = Callable[[str], None]

MAX_FRAMES_FOR_ANALYSIS = 10
DOWNLOAD_TIMEOUT_SECONDS = 300
FFMPEG_TIMEOUT_SECONDS = 120

STYLE_PROMPT = """You are a video editor analyzing another creator's editing style from sampled frames of their video, so the pattern (not the footage itself) can be applied to a different video's own content.

Cut pacing (measured directly, not from these frames): average shot length is {avg_shot:.1f} seconds, over {n_cuts} detected cuts in a {duration:.0f}-second video.

Look at these {n_frames} sampled frames (in chronological order) and describe, as ONLY a JSON object shaped exactly like this, no other text, no markdown fences:
{{
  "uses_captions": true or false,
  "caption_style": "short description of caption style if used, else empty string",
  "zoom_style": "one of: static, slow-zoom, dynamic-zoom-and-pan",
  "color_treatment": "short description - e.g. 'warm/desaturated', 'high contrast', 'natural'",
  "overall_notes": "1-2 sentences on the general visual approach"
}}
"""


class StyleAnalysisError(RuntimeError):
    pass


def slugify(text: str, limit: int = 60) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[-\s]+", "-", text)
    return text[:limit] or "style"


def _run(args: list[str], timeout: float, error_prefix: str) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise StyleAnalysisError(f"{error_prefix}: timed out after {timeout:.0f}s.")
    if result.returncode != 0:
        raise StyleAnalysisError(f"{error_prefix}: {result.stderr[-1500:]}")
    return result


def download_reference_video(url: str, out_dir: Path, progress: Optional[ProgressCB] = None) -> tuple[Path, str]:
    """Downloads a capped-resolution copy (480p is plenty for pacing/style
    analysis, and keeps this fast) - returns (video_path, video_title)."""
    import yt_dlp

    out_dir.mkdir(parents=True, exist_ok=True)

    def hook(d):
        if progress and d.get("status") == "downloading":
            progress(f"Downloading reference video: {(d.get('_percent_str') or '').strip()}")

    ydl_opts = {
        "outtmpl": str(out_dir / "reference.%(ext)s"),
        "format": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[height<=480]",
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        raise StyleAnalysisError(f"Could not download '{url}': {exc}") from exc

    candidates = sorted(out_dir.glob("reference.*"))
    mp4_candidates = [p for p in candidates if p.suffix == ".mp4"]
    if not mp4_candidates and not candidates:
        raise StyleAnalysisError("yt-dlp reported success but no output file was found.")
    video_path = mp4_candidates[0] if mp4_candidates else candidates[0]
    return video_path, info.get("title", url)


def detect_cuts(video_path: Path, threshold: float = 0.3) -> list[float]:
    """Returns timestamps (seconds) of detected scene changes, via ffmpeg's
    scene-detection filter - a real measurement, not an estimate."""
    result = _run(
        ["ffmpeg", "-i", str(video_path), "-filter:v", f"select='gt(scene,{threshold})',showinfo",
         "-f", "null", "-"],
        timeout=FFMPEG_TIMEOUT_SECONDS, error_prefix="Scene detection failed",
    )
    # showinfo writes to stderr - scan for pts_time on every selected frame.
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", result.stderr)]


def get_duration_seconds(video_path: Path) -> float:
    result = _run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        timeout=30, error_prefix="Could not read video duration",
    )
    return float(result.stdout.strip())


def extract_sample_frames(video_path: Path, timestamps: list[float], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frame_paths = []
    for i, t in enumerate(timestamps, start=1):
        out_path = out_dir / f"frame_{i:02d}.jpg"
        _run(
            ["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video_path), "-frames:v", "1", "-q:v", "3", str(out_path)],
            timeout=30, error_prefix=f"Could not extract frame at {t:.1f}s",
        )
        if out_path.exists():
            frame_paths.append(out_path)
    return frame_paths


def _pick_sample_timestamps(cut_times: list[float], duration: float, n: int) -> list[float]:
    if len(cut_times) >= n:
        step = len(cut_times) / n
        return [cut_times[int(i * step)] for i in range(n)]
    # Too few detected cuts (e.g. a slow-paced video) - fall back to evenly
    # spaced samples across the whole duration.
    return [duration * (i + 0.5) / n for i in range(n)]


def analyze_frames_with_claude(frame_paths: list[Path], cut_times: list[float], duration: float, api_key: str) -> dict:
    import anthropic

    avg_shot = duration / max(1, len(cut_times) + 1)
    content = []
    for path in frame_paths:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(path.read_bytes()).decode()},
        })
    content.append({
        "type": "text",
        "text": STYLE_PROMPT.format(avg_shot=avg_shot, n_cuts=len(cut_times), duration=duration, n_frames=len(frame_paths)),
    })

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-5", max_tokens=1024, messages=[{"role": "user", "content": content}]
    )
    raw = next((b.text for b in response.content if b.type == "text"), "")
    items = extract_json_items(raw)
    if not items:
        raise StyleAnalysisError("Claude did not return a usable style description.")
    qualitative = items[0]

    return {
        "avg_shot_seconds": round(avg_shot, 2),
        "cut_count": len(cut_times),
        "duration_seconds": round(duration, 1),
        **qualitative,
    }


def build_style_profile(
    url: str, api_key: str, progress: Optional[ProgressCB] = None
) -> dict:
    """Downloads url, measures its cut pacing, and has Claude describe its
    qualitative style from sampled frames. Saves the result to
    content/_styles/<slug>.json and returns it."""
    def report(msg: str) -> None:
        if progress:
            progress(msg)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        report("Downloading reference video...")
        video_path, title = download_reference_video(url, tmp_dir, progress=report)

        report("Measuring cut pacing...")
        duration = get_duration_seconds(video_path)
        cut_times = detect_cuts(video_path)

        report(f"Detected {len(cut_times)} cuts over {duration:.0f}s - sampling frames...")
        sample_times = _pick_sample_timestamps(cut_times, duration, MAX_FRAMES_FOR_ANALYSIS)
        frames_dir = tmp_dir / "frames"
        frame_paths = extract_sample_frames(video_path, sample_times, frames_dir)
        if not frame_paths:
            raise StyleAnalysisError("Could not extract any sample frames from the reference video.")

        report("Analyzing style with Claude...")
        profile = analyze_frames_with_claude(frame_paths, cut_times, duration, api_key)
        profile["source_title"] = title
        profile["source_url"] = url

    STYLE_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(title)
    profile_path = STYLE_PROFILES_DIR / f"{slug}.json"
    profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    profile["slug"] = slug

    report("Done.")
    return profile
