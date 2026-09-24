"""Post-production edits on an already-assembled video: add background
music and/or burn in styled captions, without touching the script,
shots, metadata, voiceover, media, or re-running Produce at all.

Always rebuilds from video_dir/final.mp4 (the pristine output of
video_assembler.assemble_video) into video_dir/final_edited.mp4, so
re-applying with different options never stacks on top of a previous
edit - toggling captions off and re-applying genuinely removes them.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional

from video_assembler import HEIGHT, WIDTH, AssemblyError, _require_ffmpeg, _run_ffmpeg, get_video_dimensions

ProgressCB = Callable[[str], None]

APP_DIR = Path(__file__).resolve().parent
MUSIC_LIBRARY_DIR = APP_DIR / "content" / "_music"

# ASS colours are &HAABBGGRR (alpha, blue, green, red), not RGB - these
# are pre-converted so the values in code stay boring hex, not math.
CAPTION_STYLES = {
    "bold-white": {
        "label": "Bold White",
        "fontname": "Arial",
        "fontsize": 72,
        "primary": "&H00FFFFFF",       # white fill
        "outline_color": "&H00000000",  # black outline
        "bold": -1,
        "outline": 4,
        "shadow": 1,
        "alignment": 2,  # ASS: bottom-center
        "margin_v": 90,
    },
    "gold-highlight": {
        "label": "Gold Highlight",
        "fontname": "Arial",
        "fontsize": 72,
        "primary": "&H004BA2C9",  # the site's #c9a24b gold, in ASS BGR order
        "outline_color": "&H00000000",
        "bold": -1,
        "outline": 4,
        "shadow": 1,
        "alignment": 2,
        "margin_v": 90,
    },
    "short-center": {
        "label": "Centered (Shorts)",
        "fontname": "Arial",
        # No fixed fontsize - Shorts are 9:16 (1080x1920) while a fixed
        # pixel size tuned for 16:9 would read too small (relative to the
        # taller canvas) or too big (relative to the narrower one), so
        # this scales with the real video's width instead - see
        # build_ass_subtitles's fontsize_ratio fallback.
        "fontsize_ratio": 0.075,
        "primary": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "bold": -1,
        "outline": 5,
        "shadow": 1,
        "alignment": 5,  # ASS: middle-center
        "margin_v": 0,
    },
}
DEFAULT_CAPTION_STYLE = "bold-white"


def list_music_library() -> list[str]:
    if not MUSIC_LIBRARY_DIR.exists():
        return []
    return sorted(
        p.name for p in MUSIC_LIBRARY_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")
    )


def transcribe_words(audio_path: Path, model_size: str = "base", progress: Optional[ProgressCB] = None) -> list[dict]:
    """Real word-level timestamps via faster-whisper, run in-process
    (this already runs inside jobs.py's own background thread, unlike
    the Streamlit app's _whisper_worker.py subprocess)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise AssemblyError(
            "faster-whisper is not installed - run: pip install faster-whisper"
        ) from exc

    if progress:
        progress(f"Loading Whisper model '{model_size}'...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    if progress:
        progress("Transcribing voiceover for captions...")
    segments_iter, _info = model.transcribe(
        str(audio_path), beam_size=5, vad_filter=True, word_timestamps=True
    )

    words: list[dict] = []
    for seg in segments_iter:
        for w in (seg.words or []):
            text = (w.word or "").strip()
            if text:
                words.append({"start": w.start, "end": w.end, "text": text})
    return words


def _group_words_into_captions(words: list[dict], max_words: int = 5, max_chars: int = 28) -> list[dict]:
    """Groups word-level timestamps into short on-screen caption chunks,
    each timed to when those words are actually spoken - reads far better
    than one subtitle card per full sentence."""
    captions: list[dict] = []
    current: list[dict] = []
    for w in words:
        current.append(w)
        text = " ".join(x["text"] for x in current)
        if len(current) >= max_words or len(text) >= max_chars:
            captions.append({"start": current[0]["start"], "end": current[-1]["end"], "text": text})
            current = []
    if current:
        captions.append({"start": current[0]["start"], "end": current[-1]["end"], "text": " ".join(x["text"] for x in current)})
    return captions


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def build_ass_subtitles(
    captions: list[dict], out_path: Path, style_name: str, width: int = WIDTH, height: int = HEIGHT,
) -> None:
    """width/height should be the real dimensions of the video these
    captions are burned into - PlayResX/Y (and short-center's fontsize,
    which has no fixed value) have to match the actual canvas, not just
    the 16:9 default, or a 9:16 short gets captions sized/positioned for
    the wrong resolution."""
    style = CAPTION_STYLES.get(style_name, CAPTION_STYLES[DEFAULT_CAPTION_STYLE])
    fontsize = style.get("fontsize") or round(width * style.get("fontsize_ratio", 0.0667))
    alignment = style.get("alignment", 2)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{style['fontname']},{fontsize},{style['primary']},&H000000FF,{style['outline_color']},&H00000000,{style['bold']},0,0,0,100,100,0,0,1,{style['outline']},{style['shadow']},{alignment},60,60,{style['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for cap in captions:
        text = cap["text"].upper().replace("\n", " ").strip()
        if not text:
            continue
        lines.append(f"Dialogue: 0,{_ass_time(cap['start'])},{_ass_time(cap['end'])},Caption,,0,0,0,,{text}\n")
    out_path.write_text("".join(lines), encoding="utf-8")


def _ffmpeg_subtitle_path_arg(ass_path: Path) -> str:
    """ffmpeg's subtitles filter takes its file path as a filter option
    value, where ':' and '\\' need their own escaping (a Windows drive
    letter like D:\\... breaks the filter's own option-separator syntax
    otherwise) - this is ffmpeg's own documented workaround, not a guess."""
    posix_like = str(ass_path).replace("\\", "/")
    escaped = posix_like.replace(":", "\\:")
    return escaped


def apply_edits(
    video_dir: Path,
    add_captions: bool = False,
    caption_style: str = DEFAULT_CAPTION_STYLE,
    whisper_model: str = "base",
    music_path: Optional[Path] = None,
    music_volume_db: float = -18.0,
    progress: Optional[ProgressCB] = None,
) -> Path:
    """Always starts fresh from video_dir/final.mp4 and writes
    video_dir/final_edited.mp4 - never edits final.mp4 itself, so it
    stays a clean base to re-derive from on the next Apply."""
    def report(msg: str) -> None:
        if progress:
            progress(msg)

    _require_ffmpeg()
    base_path = video_dir / "final.mp4"
    if not base_path.exists():
        raise AssemblyError("No final.mp4 yet - assemble the video first.")

    out_path = video_dir / "final_edited.mp4"

    if not add_captions and not music_path:
        shutil.copyfile(base_path, out_path)
        report("Done.")
        return out_path

    work_dir = video_dir / "_edit_tmp"
    work_dir.mkdir(exist_ok=True)
    current_input = base_path

    try:
        if add_captions:
            voiceover_path = video_dir / "voiceover.mp3"
            if not voiceover_path.exists():
                raise AssemblyError("No voiceover.mp3 to transcribe for captions.")
            words = transcribe_words(voiceover_path, whisper_model, progress)
            if not words:
                report("No speech detected for captions - skipping captions.")
            else:
                captions = _group_words_into_captions(words)
                ass_path = work_dir / "captions.ass"
                real_width, real_height = get_video_dimensions(base_path)
                build_ass_subtitles(captions, ass_path, caption_style, width=real_width, height=real_height)

                report("Burning in captions...")
                captioned_path = work_dir / "captioned.mp4"
                subtitle_arg = _ffmpeg_subtitle_path_arg(ass_path)
                _run_ffmpeg(
                    ["ffmpeg", "-y", "-i", str(current_input),
                     "-vf", f"subtitles='{subtitle_arg}'",
                     "-c:a", "copy", str(captioned_path)],
                    timeout=300, error_prefix="ffmpeg failed burning in captions",
                )
                current_input = captioned_path

        if music_path:
            report("Mixing in background music...")
            mixed_path = work_dir / "mixed.mp4"
            volume_factor = 10 ** (music_volume_db / 20)
            _run_ffmpeg(
                ["ffmpeg", "-y", "-i", str(current_input),
                 "-stream_loop", "-1", "-i", str(music_path),
                 "-filter_complex",
                 f"[1:a]volume={volume_factor:.4f}[music];"
                 "[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                 "-map", "0:v", "-map", "[aout]",
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
                 str(mixed_path)],
                timeout=300, error_prefix="ffmpeg failed mixing in music",
            )
            current_input = mixed_path

        shutil.copyfile(current_input, out_path)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    report("Done.")
    return out_path
