"""Assembles a finished, uploadable .mp4 from a produced video's voiceover
and found media - the piece the rest of this pipeline never did (it hands
back raw materials, not a video file).

v1, intentionally simple: the audio's total duration is split evenly
across every shot that has at least one kept image (shots with zero
images are skipped, same "even split" approach files/pipeline/stages/cut.py
already uses), each image gets a slow Ken Burns zoom for its slice, and
the slices are concatenated and muxed with the voiceover. If there are
too few images for the runtime (each would be held longer than
MAX_SHOT_SECONDS), the found images are cycled instead, alternating
zoom-in/zoom-out on repeats, rather than holding one static photo for
the whole video. No per-shot narration-timing alignment, no transitions
beyond hard cuts, no captions - those are real next steps once this
baseline is proven out.
"""
from __future__ import annotations

import csv
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

ProgressCB = Callable[[str], None]

WIDTH, HEIGHT, FPS = 1920, 1080, 30
MAX_ZOOM = 1.15  # 15% zoom over a segment's full duration
MIN_SHOT_SECONDS = 1.5  # a shot slice shorter than this looks like a flicker cut
MAX_SHOT_SECONDS = 12.0  # never hold one static image longer than this, however few were found


class AssemblyError(RuntimeError):
    pass


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise AssemblyError(
            "ffmpeg/ffprobe not found on PATH. Install ffmpeg (https://ffmpeg.org/download.html) "
            "and make sure it's on your PATH, then try again."
        )


def _run_ffmpeg(args: list[str], timeout: float, error_prefix: str) -> subprocess.CompletedProcess:
    """subprocess.run wrapper shared by every ffmpeg/ffprobe call here - a
    hung filter graph (we hit exactly this with an earlier version of the
    zoom-out effect) would otherwise block the background job forever."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise AssemblyError(f"{error_prefix}: timed out after {timeout:.0f}s.")
    if result.returncode != 0:
        raise AssemblyError(f"{error_prefix}: {result.stderr[-1500:]}")
    return result


def get_duration_seconds(path: Path) -> float:
    result = _run_ffmpeg(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        timeout=30, error_prefix=f"Could not read duration of {path}",
    )
    if not result.stdout.strip():
        raise AssemblyError(f"Could not read duration of {path}: empty ffprobe output.")
    return float(result.stdout.strip())


def top_image_per_shot(manifest_path: Path) -> list[tuple[str, Path]]:
    """Returns [(shot_id, image_path), ...] - each shot's best-ranked
    surviving image, in the order shots were first seen in the manifest
    (which follows the original shot list order)."""
    best_rank: dict[str, int] = {}
    best_path: dict[str, Path] = {}
    order: list[str] = []

    with manifest_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            shot_id = row["shot_id"]
            rank = int(row["rank"])
            if shot_id not in best_rank:
                order.append(shot_id)
            if shot_id not in best_rank or rank < best_rank[shot_id]:
                best_rank[shot_id] = rank
                best_path[shot_id] = Path(row["local_path"])

    return [(shot_id, best_path[shot_id]) for shot_id in order]


def _make_ken_burns_segment(image_path: Path, duration: float, out_path: Path, reverse: bool = False) -> None:
    """reverse=True zooms out instead of in - used to give repeated
    occurrences of the same image (when there are fewer images than the
    runtime needs) some visual variety instead of looking like an
    identical clip pasted back to back. Implemented as a zoompan
    expression that starts at MAX_ZOOM and decreases, not ffmpeg's
    `reverse` filter - `reverse` needs to see the input's true EOF before
    it can emit anything, which never arrives with a `-loop 1` image
    input and hangs ffmpeg indefinitely."""
    n_frames = max(1, round(duration * FPS))
    zoom_step = (MAX_ZOOM - 1.0) / n_frames
    if reverse:
        zoom_expr = f"if(eq(on,0),{MAX_ZOOM},max(zoom-{zoom_step:.6f},1.0))"
    else:
        zoom_expr = f"min(zoom+{zoom_step:.6f},{MAX_ZOOM})"
    vf = (
        f"scale={WIDTH * 2}:{HEIGHT * 2}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH * 2}:{HEIGHT * 2},"
        f"zoompan=z='{zoom_expr}':d={n_frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
        f"format=yuv420p"
    )
    _run_ffmpeg(
        ["ffmpeg", "-y", "-loop", "1", "-i", str(image_path), "-t", f"{duration:.3f}",
         "-vf", vf, "-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path)],
        timeout=120, error_prefix=f"ffmpeg failed rendering {image_path.name}",
    )


def assemble_video(video_dir: Path, progress: Optional[ProgressCB] = None) -> Path:
    """Builds video_dir/final.mp4 from video_dir/voiceover.mp3 and the best
    image per shot in video_dir/media/manifest.csv. Raises AssemblyError
    with a clear reason if either input is missing or ffmpeg fails."""
    def report(msg: str) -> None:
        if progress:
            progress(msg)

    _require_ffmpeg()

    audio_path = video_dir / "voiceover.mp3"
    manifest_path = video_dir / "media" / "manifest.csv"
    if not audio_path.exists():
        raise AssemblyError("No voiceover.mp3 - generate the voiceover first.")
    if not manifest_path.exists():
        raise AssemblyError("No media manifest - run the media search first.")

    shots = top_image_per_shot(manifest_path)
    if not shots:
        raise AssemblyError("No shots have any kept media - nothing to build a video from.")

    report("Reading voiceover length...")
    total_duration = get_duration_seconds(audio_path)
    n_found = len(shots)
    natural_per_image = total_duration / n_found

    if natural_per_image <= MAX_SHOT_SECONDS:
        # Enough images that each can just get its natural, even share of
        # the runtime - the common case with decent media coverage.
        segments = [(image_path, natural_per_image, False) for _, image_path in shots]
    else:
        # Too few images for the runtime (e.g. 1 image for a 12-minute
        # video) - holding one static photo for minutes looks broken, so
        # cap every segment at MAX_SHOT_SECONDS and cycle through the
        # images that were found, alternating zoom-in/zoom-out on repeats
        # so it doesn't look like the exact same clip pasted back to back.
        n_segments = max(n_found, math.ceil(total_duration / MAX_SHOT_SECONDS))
        seg_duration = total_duration / n_segments
        report(
            f"Only {n_found} image(s) found for a {total_duration:.0f}s video - "
            f"repeating them across {n_segments} segments (~{seg_duration:.1f}s each) "
            "instead of holding one static image for the whole runtime."
        )
        seen_counts: dict[int, int] = {}
        segments = []
        for i in range(n_segments):
            idx = i % n_found
            occurrence = seen_counts.get(idx, 0)
            seen_counts[idx] = occurrence + 1
            segments.append((shots[idx][1], seg_duration, occurrence % 2 == 1))

    with tempfile.TemporaryDirectory(dir=video_dir) as tmp:
        tmp_dir = Path(tmp)
        segment_paths: list[Path] = []

        for i, (image_path, duration, reverse) in enumerate(segments, start=1):
            report(f"Rendering segment {i}/{len(segments)}...")
            seg_path = tmp_dir / f"seg_{i:03d}.mp4"
            _make_ken_burns_segment(image_path, duration, seg_path, reverse=reverse)
            segment_paths.append(seg_path)

        report("Combining shots...")
        concat_list = tmp_dir / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in segment_paths), encoding="utf-8"
        )
        silent_path = tmp_dir / "silent.mp4"
        _run_ffmpeg(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(silent_path)],
            timeout=60, error_prefix="ffmpeg failed combining shots",
        )

        report("Adding voiceover...")
        final_path = video_dir / "final.mp4"
        _run_ffmpeg(
            ["ffmpeg", "-y", "-i", str(silent_path), "-i", str(audio_path),
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(final_path)],
            timeout=120, error_prefix="ffmpeg failed adding audio",
        )

    report("Done.")
    return final_path
