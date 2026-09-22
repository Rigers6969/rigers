"""Assembles a finished, uploadable .mp4 from a produced video's voiceover
and found media - the piece the rest of this pipeline never did (it hands
back raw materials, not a video file).

v1, intentionally simple: the audio's total duration is split evenly
across every shot that has at least one kept image (shots with zero
images are skipped, same "even split" approach files/pipeline/stages/cut.py
already uses), each image gets a slow Ken Burns zoom-in for its slice, and
the slices are concatenated and muxed with the voiceover. No per-shot
narration-timing alignment, no transitions beyond hard cuts, no captions -
those are real next steps once this baseline is proven out.
"""
from __future__ import annotations

import csv
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

ProgressCB = Callable[[str], None]

WIDTH, HEIGHT, FPS = 1920, 1080, 30
MAX_ZOOM = 1.15  # 15% zoom-in over the shot's full duration
MIN_SHOT_SECONDS = 1.5  # a shot slice shorter than this looks like a flicker cut


class AssemblyError(RuntimeError):
    pass


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise AssemblyError(
            "ffmpeg/ffprobe not found on PATH. Install ffmpeg (https://ffmpeg.org/download.html) "
            "and make sure it's on your PATH, then try again."
        )


def get_duration_seconds(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise AssemblyError(f"Could not read duration of {path}: {result.stderr.strip()}")
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


def _make_ken_burns_segment(image_path: Path, duration: float, out_path: Path) -> None:
    n_frames = max(1, round(duration * FPS))
    zoom_step = (MAX_ZOOM - 1.0) / n_frames
    vf = (
        f"scale={WIDTH * 2}:{HEIGHT * 2}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH * 2}:{HEIGHT * 2},"
        f"zoompan=z='min(zoom+{zoom_step:.6f},{MAX_ZOOM})':d={n_frames}:s={WIDTH}x{HEIGHT}:fps={FPS},"
        f"format=yuv420p"
    )
    result = subprocess.run(
        ["ffmpeg", "-y", "-loop", "1", "-i", str(image_path), "-t", f"{duration:.3f}",
         "-vf", vf, "-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise AssemblyError(f"ffmpeg failed rendering {image_path.name}: {result.stderr[-1500:]}")


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
    per_shot = max(MIN_SHOT_SECONDS, total_duration / len(shots))

    with tempfile.TemporaryDirectory(dir=video_dir) as tmp:
        tmp_dir = Path(tmp)
        segment_paths: list[Path] = []

        for i, (shot_id, image_path) in enumerate(shots, start=1):
            report(f"Rendering shot {i}/{len(shots)} ({shot_id})...")
            seg_path = tmp_dir / f"seg_{i:03d}.mp4"
            _make_ken_burns_segment(image_path, per_shot, seg_path)
            segment_paths.append(seg_path)

        report("Combining shots...")
        concat_list = tmp_dir / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in segment_paths), encoding="utf-8"
        )
        silent_path = tmp_dir / "silent.mp4"
        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(silent_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise AssemblyError(f"ffmpeg failed combining shots: {result.stderr[-1500:]}")

        report("Adding voiceover...")
        final_path = video_dir / "final.mp4"
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(silent_path), "-i", str(audio_path),
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(final_path)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise AssemblyError(f"ffmpeg failed adding audio: {result.stderr[-1500:]}")

    report("Done.")
    return final_path
