"""Shorts repurposing: turns one finished long video into several
vertical 9:16 clips (YouTube Shorts / Reels / TikTok) with burned-in
word-by-word captions and a title, so one production run yields 3-4
extra uploads.

How clips are chosen: the voiceover is transcribed with word timestamps
(the voiceover is the final video's audio from 0:00, so its times line
up exactly), split into sentences, and the writer model picks the most
gripping self-contained stretches of 20-55 seconds. If the model's
answer is unusable, clips are spread evenly through the video instead -
Shorts still get made, just less cleverly chosen.

How they look: the 16:9 video sits in the middle of a 1080x1920 frame
over a blurred, zoomed copy of itself (nothing gets cropped off), the
title sits in the top band, captions in the lower band.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable, Optional

from json_utils import extract_json_items
from video_assembler import AssemblyError, _require_ffmpeg, _run_ffmpeg, get_duration_seconds, get_video_dimensions
from video_editor import _ass_time, _ffmpeg_subtitle_path_arg, _group_words_into_captions, transcribe_words

ProgressCB = Callable[[str], None]

OUT_W, OUT_H = 1080, 1920
MIN_SECONDS, MAX_SECONDS = 20.0, 55.0  # under a minute: plays everywhere (Shorts, Reels, TikTok)
DEFAULT_COUNT = 4
SHORTS_DIRNAME = "shorts"

PICK_PROMPT = """You are an editor cutting viral YouTube Shorts from a longer documentary.

Below is the documentary's narration, split into numbered sentences with their start times in seconds.

Pick up to {count} separate clips. Each clip:
- is a run of consecutive sentences, {min_s:.0f} to {max_s:.0f} seconds long,
- makes sense on its own to someone who hasn't seen the full video,
- starts with a hook - a surprising fact, a question, or a dramatic moment - not a slow intro,
- does not overlap any other clip.

Also give each clip a short, punchy on-screen title (max 6 words).

Respond with ONLY a JSON array like:
[{{"start": 12, "end": 19, "title": "The Night Everything Changed"}}]
where "start" and "end" are sentence NUMBERS (inclusive). No other text.

Sentences:
{sentences}
"""


def split_sentences(words: list[dict]) -> list[dict]:
    """Groups word timestamps into sentences: {start, end, text}."""
    sentences, current = [], []
    for w in words:
        current.append(w)
        if w["text"].rstrip('"\')').endswith((".", "!", "?")):
            sentences.append({"start": current[0]["start"], "end": current[-1]["end"], "text": " ".join(x["text"] for x in current)})
            current = []
    if current:
        sentences.append({"start": current[0]["start"], "end": current[-1]["end"], "text": " ".join(x["text"] for x in current)})
    return sentences


def _fit_window(sentences: list[dict], first: int, last: int) -> Optional[tuple[int, int]]:
    """Grows/shrinks a sentence range until it lasts MIN..MAX seconds.
    Returns None if no range starting at `first` can."""
    last = max(first, min(last, len(sentences) - 1))
    while last + 1 < len(sentences) and sentences[last]["end"] - sentences[first]["start"] < MIN_SECONDS:
        last += 1
    while last > first and sentences[last]["end"] - sentences[first]["start"] > MAX_SECONDS:
        last -= 1
    duration = sentences[last]["end"] - sentences[first]["start"]
    if duration < MIN_SECONDS or duration > MAX_SECONDS:
        return None
    return first, last


def _overlaps(a: tuple[int, int], chosen: list[dict]) -> bool:
    return any(not (a[1] < c["first"] or a[0] > c["last"]) for c in chosen)


def pick_clips_with_model(writer, sentences: list[dict], count: int) -> list[dict]:
    numbered = "\n".join(f"{i + 1}. [{s['start']:.0f}s] {s['text']}" for i, s in enumerate(sentences))
    raw = writer._call_model(
        PICK_PROMPT.format(count=count, min_s=MIN_SECONDS, max_s=MAX_SECONDS, sentences=numbered),
        max_tokens=600,
    )
    items = extract_json_items(raw) or []
    chosen: list[dict] = []
    for item in items:
        try:
            first, last = int(item["start"]) - 1, int(item["end"]) - 1
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= first < len(sentences)):
            continue
        window = _fit_window(sentences, first, last)
        if window and not _overlaps(window, chosen):
            title = str(item.get("title") or "").strip().strip('"')[:60]
            chosen.append({"first": window[0], "last": window[1], "title": title})
        if len(chosen) >= count:
            break
    return chosen


def pick_clips_evenly(sentences: list[dict], count: int) -> list[dict]:
    """Fallback: clips spread through the video, skipping the very start
    (usually a slow intro)."""
    chosen: list[dict] = []
    if not sentences:
        return chosen
    total = sentences[-1]["end"]
    for k in range(count):
        target = total * (0.08 + 0.84 * k / max(count, 1))
        first = next((i for i, s in enumerate(sentences) if s["start"] >= target), None)
        if first is None:
            continue
        window = _fit_window(sentences, first, first)
        if window and not _overlaps(window, chosen):
            chosen.append({"first": window[0], "last": window[1], "title": ""})
    return chosen


def _ass_text(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def build_short_ass(captions: list[dict], title: str, duration: float, out_path: Path) -> None:
    """Captions in the lower blurred band, title in the top band - both
    clear of the 16:9 video sitting in the middle of the frame."""
    caption_size = round(OUT_W * 0.075)
    title_size = round(OUT_W * 0.068)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,{caption_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,1,2,70,70,{round(OUT_H * 0.2)},1
Style: Title,Arial,{title_size},&H004BD2FF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,1,8,70,70,{round(OUT_H * 0.14)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    if title:
        lines.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(duration)},Title,,0,0,0,,{_ass_text(title).upper()}\n")
    for cap in captions:
        text = _ass_text(cap["text"]).upper()
        if text:
            lines.append(f"Dialogue: 0,{_ass_time(cap['start'])},{_ass_time(cap['end'])},Caption,,0,0,0,,{text}\n")
    out_path.write_text("".join(lines), encoding="utf-8")


def render_short(source: Path, start: float, duration: float, ass_path: Path, out_path: Path) -> None:
    subs = _ffmpeg_subtitle_path_arg(ass_path)
    graph = (
        f"[0:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},boxblur=25:2[bg];"
        f"[0:v]scale={OUT_W}:-2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,subtitles='{subs}'[v]"
    )
    _run_ffmpeg(
        ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
         "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out_path)],
        timeout=600, error_prefix="ffmpeg failed rendering a Short",
    )


def make_shorts(
    video_dir: Path, writer=None, count: int = DEFAULT_COUNT, whisper_model: str = "base",
    progress: Optional[ProgressCB] = None,
) -> list[dict]:
    """Cuts video_dir's finished long video into up to `count` vertical
    Shorts in video_dir/shorts/, and writes shorts/shorts.json describing
    them. Returns that list: [{file, start, end, title, text}]."""
    def report(msg: str) -> None:
        if progress:
            progress(msg)

    _require_ffmpeg()
    source = video_dir / "final_edited.mp4"
    if not source.exists():
        source = video_dir / "final.mp4"
    if not source.exists():
        raise AssemblyError("No finished video yet - produce or assemble it first.")
    width, height = get_video_dimensions(source)
    if height > width:
        raise AssemblyError("This video is already vertical - it's a Short itself.")
    voiceover = video_dir / "voiceover.mp3"
    if not voiceover.exists():
        raise AssemblyError("No voiceover.mp3 to transcribe.")

    words = transcribe_words(voiceover, whisper_model, progress)
    sentences = split_sentences(words)
    if not sentences:
        raise AssemblyError("No speech found in the voiceover.")
    video_length = get_duration_seconds(source)

    clips: list[dict] = []
    if writer is not None:
        report("Picking the best moments...")
        try:
            clips = pick_clips_with_model(writer, sentences, count)
        except Exception as exc:
            report(f"Couldn't ask the writer model ({exc}) - spreading clips evenly instead.")
    if not clips:
        clips = pick_clips_evenly(sentences, count)
    if not clips:
        raise AssemblyError(f"The video is too short to cut {MIN_SECONDS:.0f}-{MAX_SECONDS:.0f} second Shorts from.")
    clips.sort(key=lambda c: c["first"])

    # Without a model-picked title, fall back to the video's own title.
    video_title = ""
    metadata_path = video_dir / "metadata.json"
    if metadata_path.exists():
        try:
            video_title = (json.loads(metadata_path.read_text(encoding="utf-8")).get("youtube") or {}).get("title", "")
        except (json.JSONDecodeError, OSError):
            pass

    out_dir = video_dir / SHORTS_DIRNAME
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir()
    work_dir = out_dir / "_tmp"
    work_dir.mkdir()

    results = []
    try:
        for n, clip in enumerate(clips, start=1):
            # a little air before the first word and after the last
            start = max(0.0, sentences[clip["first"]]["start"] - 0.25)
            end = min(video_length, sentences[clip["last"]]["end"] + 0.6)
            duration = end - start
            clip_words = [
                {"start": w["start"] - start, "end": w["end"] - start, "text": w["text"]}
                for w in words if w["start"] >= start and w["end"] <= end
            ]
            text = " ".join(s["text"] for s in sentences[clip["first"]:clip["last"] + 1])
            title = clip["title"] or (f"{video_title} - Part {n}" if video_title else " ".join(sentences[clip["first"]]["text"].split()[:6]))

            report(f"Rendering Short {n}/{len(clips)} ({duration:.0f}s)...")
            ass_path = work_dir / f"short_{n}.ass"
            build_short_ass(_group_words_into_captions(clip_words, max_words=3, max_chars=18), title, duration, ass_path)
            out_path = out_dir / f"short_{n}.mp4"
            render_short(source, start, duration, ass_path, out_path)
            results.append({"file": out_path.name, "start": round(start, 2), "end": round(end, 2), "title": title, "text": text})
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    (out_dir / "shorts.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    report(f"Done - {len(results)} Shorts made.")
    return results


def load_shorts(video_dir: Path) -> list[dict]:
    path = video_dir / SHORTS_DIRNAME / "shorts.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
