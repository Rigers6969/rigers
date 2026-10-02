"""Cutting one vertical 1080x1920 Short out of the long video, with
word-by-word captions (and an optional hook title) burned in.

Layouts:
  crop - fills the whole screen, cut from the centre (best for one person talking)
  fit  - the whole picture, over a blurred copy of itself (best for gameplay, screens)
  podcast - split screen: the left half of the picture on top, the right half below
            (two people sitting side by side, each gets half the vertical screen)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

import policy

OUT_W, OUT_H = 1080, 1920
LAYOUTS = ("crop", "fit", "podcast")
CAPTION_STYLES = ("highlight", "simple", "none")

YELLOW = "&H0000E5FF&"  # ASS colours are BGR


class RenderError(Exception):
    pass


class Cancelled(Exception):
    pass


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise RenderError(f"{tool} isn't installed or isn't on PATH - see the README's 'Install' section.")


def probe(path: Path) -> dict:
    """{duration, width, height, has_audio} - raises RenderError if it isn't a video."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        data = json.loads(out.stdout or "{}")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
        raise RenderError(f"Couldn't read this file: {exc}") from exc
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video" and s.get("width")), None)
    if not video:
        raise RenderError("That file has no video picture in it (or isn't a video at all).")
    try:
        duration = float(data.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "duration": duration, "width": int(video["width"]), "height": int(video["height"]),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def _ass_time(seconds: float) -> str:
    cs = int(round(max(0.0, seconds) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _ass_text(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def group_words(words: list[dict], max_words: int = 3, max_chars: int = 18) -> list[list[dict]]:
    """Short chunks of 1-3 words, never running across the end of a sentence."""
    groups, current = [], []
    for w in words:
        if current and (len(current) >= max_words or len(" ".join(x["text"] for x in current + [w])) > max_chars):
            groups.append(current)
            current = []
        current.append(w)
        if w["text"].rstrip('"\')').endswith((".", "!", "?")):
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def build_ass(words: list[dict], title: str, duration: float, layout: str, caption_style: str, out_path: Path) -> None:
    """words are already shifted so 0 = the start of the clip."""
    cap_align = 2  # bottom centre
    if layout == "podcast":
        cap_align, cap_margin = 5, 0  # right on the seam between the two speakers
        title_margin = round(OUT_H * 0.05)
    elif layout == "fit":
        cap_margin = round(OUT_H * 0.19)  # lower blurred band, under the picture
        title_margin = round(OUT_H * 0.15)  # upper blurred band, above the picture
    else:
        cap_margin = round(OUT_H * 0.27)  # lower third - clear of the platform's own buttons/description
        title_margin = round(OUT_H * 0.10)
    cap_size = round(OUT_W * (0.085 if caption_style == "highlight" else 0.07))
    title_size = round(OUT_W * 0.06)
    lines = [f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,{cap_size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,{cap_align},60,60,{cap_margin},1
Style: Title,Arial,{title_size},&H00000000,&H000000FF,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,16,0,8,90,90,{title_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""]
    if title:
        lines.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(duration)},Title,,0,0,0,,{_ass_text(title)}\n")

    if caption_style != "none":
        groups = group_words(words)
        for g, group in enumerate(groups):
            g_start = group[0]["start"]
            next_start = groups[g + 1][0]["start"] if g + 1 < len(groups) else duration
            # stay up through short pauses so captions don't flicker
            g_end = min(next_start, group[-1]["end"] + 0.6, duration)
            g_end = max(g_end, g_start + 0.2)
            texts = [_ass_text(w["text"]).upper() for w in group]
            if caption_style == "simple":
                lines.append(f"Dialogue: 0,{_ass_time(g_start)},{_ass_time(g_end)},Caption,,0,0,0,,{' '.join(texts)}\n")
                continue
            for k, w in enumerate(group):
                w_start = g_start if k == 0 else w["start"]
                w_end = group[k + 1]["start"] if k + 1 < len(group) else g_end
                if w_end - w_start <= 0.01:
                    continue
                shown = " ".join(
                    f"{{\\c{YELLOW}}}{t}{{\\c&H00FFFFFF&}}" if j == k else t for j, t in enumerate(texts)
                )
                lines.append(f"Dialogue: 0,{_ass_time(w_start)},{_ass_time(w_end)},Caption,,0,0,0,,{shown}\n")
    out_path.write_text("".join(lines), encoding="utf-8")


def _video_filter(layout: str, ass_name: str | None) -> str:
    subs = f",subtitles={ass_name}" if ass_name else ""
    if layout == "podcast":
        half = OUT_H // 2
        return (
            f"[0:v]split=2[l][r];"
            f"[l]crop=iw/2:ih:0:0,scale={OUT_W}:{half}:force_original_aspect_ratio=increase,crop={OUT_W}:{half},setsar=1[top];"
            f"[r]crop=iw/2:ih:iw/2:0,scale={OUT_W}:{half}:force_original_aspect_ratio=increase,crop={OUT_W}:{half},setsar=1[bottom];"
            f"[top][bottom]vstack=inputs=2,format=yuv420p{subs}[v]"
        )
    if layout == "fit":
        return (
            # the blur is done on a small copy - much faster on a CPU, looks the same
            f"[0:v]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=10:2,"
            f"scale={OUT_W}:{OUT_H},setsar=1[bg];"
            f"[0:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,setsar=1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p{subs}[v]"
        )
    return (
        f"[0:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
        f"crop={OUT_W}:{OUT_H},setsar=1,format=yuv420p{subs}[v]"
    )


def _audio_filter(mute: list[tuple[float, float]]) -> str:
    """Silences the given (start, end) stretches - the "bleep"."""
    if not mute:
        return ""
    when = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in mute)
    return f";[0:a:0]volume=enable='{when}':volume=0[a]"


def _run(cmd: list[str], cwd: Path, cancelled: Callable[[], bool], timeout: float) -> None:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            text=True, errors="replace", creationflags=flags)
    began = time.time()
    try:
        while True:
            try:
                _out, err = proc.communicate(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                if cancelled():
                    proc.kill()
                    proc.communicate()
                    raise Cancelled()
                if time.time() - began > timeout:
                    proc.kill()
                    proc.communicate()
                    raise RenderError("ffmpeg took far too long on this clip and was stopped.")
    finally:
        if proc.poll() is None:
            proc.kill()
    if proc.returncode != 0:
        tail = "\n".join((err or "").strip().splitlines()[-6:])
        raise RenderError(f"ffmpeg failed:\n{tail}")


def render_clip(
    source: Path, start: float, end: float, words: list[dict], title: str,
    layout: str, caption_style: str, out_path: Path, poster_path: Path,
    has_audio: bool = True, cancelled: Callable[[], bool] = lambda: False, bleep: bool = False,
) -> int:
    """words: the whole video's words - the ones inside start..end are used.
    bleep: mute swear words and show them as F*** in the captions.
    Returns how many words were bleeped."""
    duration = end - start
    out_dir = out_path.parent
    clip_words = [
        {"start": max(0.0, w["start"] - start), "end": min(duration, w["end"] - start), "text": w["text"]}
        for w in words if w["start"] >= start - 0.05 and w["start"] < end
    ]
    mute = []
    if bleep:
        for w in clip_words:
            if policy.swear_strength(w["text"]):
                mute.append((max(0.0, w["start"] - 0.05), min(duration, w["end"] + 0.05)))
                w["text"] = policy.censor(w["text"])
    ass_name = None
    if title or caption_style != "none":
        # ffmpeg runs inside the output folder and gets just the file name:
        # Windows paths (C:\...) break ffmpeg's subtitles filter otherwise
        ass_name = out_path.stem + ".ass"
        build_ass(clip_words, title, duration, layout, caption_style, out_dir / ass_name)
    tmp_name = out_path.stem + ".part.mp4"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source.resolve()),
        "-filter_complex", _video_filter(layout, ass_name) + _audio_filter(mute if has_audio else []), "-map", "[v]",
    ]
    if has_audio:
        cmd += ["-map", "[a]" if mute else "0:a:0", "-c:a", "aac", "-b:a", "160k", "-ar", "44100"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-r", "30",
            "-movflags", "+faststart", "-f", "mp4", tmp_name]
    try:
        _run(cmd, out_dir, cancelled, timeout=max(600, duration * 30))
        os.replace(out_dir / tmp_name, out_path)  # only a finished file ever gets the real name
    finally:
        for leftover in (out_dir / tmp_name, out_dir / ass_name if ass_name else None):
            if leftover and leftover.exists():
                leftover.unlink()

    # small preview picture for the page
    try:
        _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{min(1.5, duration / 2):.2f}",
              "-i", out_path.name, "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "4", poster_path.name],
             out_dir, lambda: False, timeout=60)
    except RenderError:
        pass
    return len(mute)
