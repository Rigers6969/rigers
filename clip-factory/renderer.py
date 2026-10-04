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
import styles

OUT_W, OUT_H = 1080, 1920  # the layout is planned at this size (captions, logo, emojis)
OUT_SIZES = {"1080": (1080, 1920), "1440": (1440, 2560), "2160": (2160, 3840)}  # what the clip is made in
LAYOUTS = ("crop", "fit", "podcast", "gameplay", "post")
POST_TOP = 130  # text post layout: where the video starts (clear of the apps' top bar)
GAME_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
CAPTION_STYLES = ("hormozi", "beast", "highlight", "box", "iman", "story", "simple", "none", "pop")  # pop = old name of hormozi
CAPTION_POSITIONS = ("middle", "low")
MUSIC_EXTS = {".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac"}

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


def media_duration(path: Path) -> float:
    """Length in seconds of any audio or video file (0 if unknown)."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                             capture_output=True, text=True, timeout=60).stdout.strip()
        return float(out or 0)
    except (subprocess.SubprocessError, ValueError, OSError):
        return 0.0


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


def caption_anchor(layout: str, position: str) -> tuple[int, int, int]:
    """(x, y, ASS alignment) where the captions sit."""
    if layout in ("podcast", "gameplay") or position == "middle":
        return OUT_W // 2, OUT_H // 2, 5
    if layout == "fit":
        return OUT_W // 2, OUT_H - round(OUT_H * 0.19), 2
    return OUT_W // 2, OUT_H - round(OUT_H * 0.27), 2


def build_ass(words: list[dict], title: str, duration: float, layout: str, caption_style: str, out_path: Path,
              position: str = "middle", post: dict | None = None) -> None:
    """words are already shifted so 0 = the start of the clip.
    post (text post layout): {"paragraphs", "ending", "text_top"} - shown instead of the title and captions."""
    cap_align = 2  # bottom centre
    if position == "middle" and layout not in ("podcast", "gameplay"):
        cap_align, cap_margin = 5, 0  # the middle of the screen
        title_margin = round(OUT_H * (0.15 if layout == "fit" else 0.10))
    elif layout in ("podcast", "gameplay"):
        cap_align, cap_margin = 5, 0  # right on the seam between the two halves
        title_margin = round(OUT_H * 0.05)
    elif layout == "fit":
        cap_margin = round(OUT_H * 0.19)  # lower blurred band, under the picture
        title_margin = round(OUT_H * 0.15)  # upper blurred band, above the picture
    else:
        cap_margin = round(OUT_H * 0.27)  # lower third - clear of the platform's own buttons/description
        title_margin = round(OUT_H * 0.10)
    font_title, font_simple = styles.FONTS["xbold"][0], styles.FONTS["xbold"][0]
    lines = [f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font_simple},{styles.em("xbold", 70)},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,6,3,{cap_align},60,60,{cap_margin},1
Style: Title,{font_title},{styles.em("xbold", 54)},&H00000000,&H000000FF,&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,0,0,3,18,0,8,90,90,{title_margin},1
{styles.styles_block()}
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""]
    if layout == "post":
        if post:
            lines += styles.post_events(post["paragraphs"], post.get("ending", ""), duration, post["text_top"], round(OUT_H * 0.83))
        out_path.write_text("".join(lines), encoding="utf-8")
        return
    if title:
        lines.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(duration)},Title,,0,0,0,,{_ass_text(title)}\n")

    style = styles.ALIASES.get(caption_style, caption_style)
    if style in styles.STYLES:
        x, y, an = caption_anchor(layout, position)
        # story: a centred block, in the clip's half for the gameplay layout
        area = (round(OUT_H * 0.08), round(OUT_H * 0.46)) if layout == "gameplay" else (round(OUT_H * 0.28), round(OUT_H * 0.72))
        lines += styles.events(style, words, duration, x, y, an, area)
    elif style == "simple":
        groups = group_words(words, 4, 26)
        for g, group in enumerate(groups):
            g_start = group[0]["start"]
            next_start = groups[g + 1][0]["start"] if g + 1 < len(groups) else duration
            # stay up through short pauses so captions don't flicker
            g_end = max(min(next_start, group[-1]["end"] + 0.6, duration), g_start + 0.2)
            text = " ".join(_ass_text(w["text"]) for w in group)
            lines.append(f"Dialogue: 0,{_ass_time(g_start)},{_ass_time(g_end)},Caption,,0,0,0,,{text}\n")
    out_path.write_text("".join(lines), encoding="utf-8")


def _video_filter(layout: str, ass_name: str | None, wm: dict | None = None, wm_input: int = 1,
                  pops: list | None = None, fonts: str = "", W: int = OUT_W, H: int = OUT_H, video_h: int = 0) -> str:
    """wm: {"size": share of the width, "opacity": 0-1, "y": centre as share of the height} - input wm_input is the logo.
    pops: [(input, start, end, x, y)] emoji pictures. The gameplay layout's second video is input 1."""
    subs = (f",subtitles={ass_name}" + (f":fontsdir={fonts}" if fonts else "")) if ass_name else ""
    chain = _base_filter(layout, W, H, video_h)[: -len("[v]")] + "[b0]"
    k = W / OUT_W  # 2 for 4K: logo and emojis grow with the picture (the captions scale by themselves)
    cur = "b0"
    if wm:
        w = max(40, int(W * wm["size"])) // 2 * 2
        chain += (f";[{wm_input}:v]scale={w}:-1,format=rgba,colorchannelmixer=aa={wm['opacity']:.2f}[wm];"
                  f"[{cur}][wm]overlay=x=(W-w)/2:y=H*{wm['y']:.3f}-h/2[b1]")
        cur = "b1"
    for n, (idx, a, b, x, y) in enumerate(pops or []):
        # pops in (grows from 60% in 0.15 s), then fades out
        e = int(230 * k) // 2 * 2
        chain += (f";[{idx}:v]format=rgba,scale={e}:{e},fade=t=in:st={a:.2f}:d=0.15:alpha=1,"
                  f"fade=t=out:st={max(a, b - 0.2):.2f}:d=0.2:alpha=1[e{n}];"
                  f"[{cur}][e{n}]overlay=x={int(x * k)}:y={int(y * k)}:enable='between(t,{a:.2f},{b:.2f})'[p{n}]")
        cur = f"p{n}"
    # captions last, on top of everything, so nothing hides what's said
    return chain + f";[{cur}]format=yuv420p{subs}[v]"


def _base_filter(layout: str, W: int = OUT_W, H: int = OUT_H, video_h: int = 0) -> str:
    subs = ""
    if layout == "post":
        # black page, the video across the top (video_h tall at 1080 wide), the text goes underneath
        k = W / OUT_W
        vh, top = max(2, round(video_h * k) // 2 * 2), round(POST_TOP * k) // 2 * 2
        return (
            f"[0:v]scale={W}:{vh}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{vh},setsar=1[vid];"
            f"color=c=black:s={W}x{H}:r=30[page];[page][vid]overlay=0:{top}:shortest=1,format=yuv420p[v]"
        )
    if layout == "gameplay":
        half = H // 2
        return (
            # the clip on top, the gameplay (input 1, already looped and muted) underneath; stop with the clip
            f"[0:v]scale={W}:{half}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{half},setsar=1[top];"
            f"[1:v]scale={W}:{half}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{half},setsar=1,fps=30[bottom];"
            f"[top][bottom]vstack=inputs=2:shortest=1,format=yuv420p[v]"
        )
    if layout == "podcast":
        half = H // 2
        return (
            f"[0:v]split=2[l][r];"
            f"[l]crop=iw/2:ih:0:0,scale={W}:{half}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{half},setsar=1[top];"
            f"[r]crop=iw/2:ih:iw/2:0,scale={W}:{half}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{half},setsar=1[bottom];"
            f"[top][bottom]vstack=inputs=2,format=yuv420p{subs}[v]"
        )
    if layout == "fit":
        return (
            # the blur is done on a small copy - much faster on a CPU, looks the same
            f"[0:v]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=10:2,"
            f"scale={W}:{H},setsar=1[bg];"
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,setsar=1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p{subs}[v]"
        )
    return (
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={W}:{H},setsar=1,format=yuv420p{subs}[v]"
    )


def _audio_filter(mute: list[tuple[float, float]], music_input: int | None = None, music_volume: float = 0.18,
                  duration: float = 0.0) -> str:
    """Silences the given (start, end) stretches - the "bleep" - and mixes in background music that gets
    quieter whenever someone speaks (ducking). Output label [a] (or nothing to change)."""
    if not mute and music_input is None:
        return ""
    speech = "[0:a:0]"
    out = ""
    if mute:
        when = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in mute)
        out += f";[0:a:0]volume=enable='{when}':volume=0" + ("[sp]" if music_input is not None else "[a]")
        speech = "[sp]"
    if music_input is not None:
        fade_out = max(0.0, duration - 1.2)
        out += (f";{speech}asplit=2[s1][s2];"
                f"[{music_input}:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={music_volume:.2f},"
                f"afade=t=in:d=0.6,afade=t=out:st={fade_out:.2f}:d=1.2[mu];"
                f"[mu][s2]sidechaincompress=threshold=0.03:ratio=8:attack=15:release=350[duck];"
                f"[s1][duck]amix=inputs=2:duration=first:normalize=0[a]")
    return out


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
    watermark: dict | None = None, gameplay: dict | None = None, caption_words: list[dict] | None = None,
    caption_pos: str = "middle", emojis: bool = False, music: dict | None = None, size: str = "1080",
    post: dict | None = None,
) -> int:
    """words: the whole video's words - the ones inside start..end are used.
    bleep: mute swear words and show them as F*** in the captions.
    size: "1080", "1440" or "2160" (4K) - the width of the finished clip, e.g. 4K = 2160x3840.
    post: the text post layout's text, {"paragraphs": [...], "ending": "..."} (key phrases in **stars**).
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
    if caption_words is not None:  # translated captions: shown instead; the bleeping above still follows the real audio
        clip_words = [
            {"start": max(0.0, w["start"] - start), "end": min(duration, w["end"] - start), "text": w["text"]}
            for w in caption_words if w["start"] >= start - 0.05 and w["start"] < end
        ]
    video_h = 0
    if layout == "post":  # the video keeps its shape across the top; the story text goes under it
        try:
            src = probe(source)
            video_h = round(OUT_W * src["height"] / max(1, src["width"]))
        except RenderError:
            video_h = 608
        video_h = max(400, min(video_h, round(OUT_H * 0.42)))
        post = dict(post or {"paragraphs": [title] if title else []}, text_top=POST_TOP + video_h + 64)
        emojis = False
    ass_name = None
    if title or caption_style != "none" or layout == "post":
        # ffmpeg runs inside the output folder and gets just the file name:
        # Windows paths (C:\...) break ffmpeg's subtitles filter otherwise
        ass_name = out_path.stem + ".ass"
        build_ass(clip_words, title, duration, layout, caption_style, out_dir / ass_name, caption_pos, post)
    tmp_name = out_path.stem + ".part.mp4"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source.resolve()),
    ]
    if layout == "gameplay":
        if not gameplay:
            raise RenderError("The gameplay layout needs a gameplay video - add one under Layout.")
        # looped forever from a random point; only its picture is used (the clip's sound stays)
        cmd += ["-stream_loop", "-1", "-ss", f"{gameplay.get('offset', 0):.2f}", "-i", str(Path(gameplay["path"]).resolve())]
    n_in = 2 if layout == "gameplay" else 1
    wm_input = n_in
    if watermark:  # a still logo: overlay repeats its one frame for the whole clip
        cmd += ["-i", str(Path(watermark["path"]).resolve())]
        n_in += 1
    pops = []
    if emojis and caption_style != "none":
        x, y, an = caption_anchor(layout, caption_pos)
        top = y - (420 if an == 5 else 560)  # above the captions
        if styles.ALIASES.get(caption_style, caption_style) == "story":
            top = int(OUT_H * (0.02 if layout == "gameplay" else 0.17))
        for a, b, code in styles.emoji_moments(clip_words, duration):
            cmd += ["-loop", "1", "-t", f"{duration:.3f}", "-i", str((styles.EMOJI_DIR / f"{code}.png").resolve())]
            pops.append((n_in, a, b, OUT_W // 2 - 115, max(20, top)))
            n_in += 1
    music_input = None
    if music and has_audio:  # background music: looped from a random point, ducked under the voices
        cmd += ["-stream_loop", "-1", "-ss", f"{music.get('offset', 0):.2f}", "-i", str(Path(music["path"]).resolve())]
        music_input = n_in
        n_in += 1
    audio = _audio_filter(mute if has_audio else [], music_input, music.get("volume", 0.18) if music else 0.18, duration)
    cmd += [
        "-filter_complex", _video_filter(layout, ass_name, watermark, wm_input, pops, styles.fonts_dir_for(out_dir) if ass_name else "",
                                         *OUT_SIZES.get(size, OUT_SIZES["1080"]), video_h)
        + audio, "-map", "[v]", "-t", f"{duration:.3f}",
    ]
    if has_audio:
        cmd += ["-map", "[a]" if audio else "0:a:0", "-c:a", "aac", "-b:a", "160k", "-ar", "44100"]
    big = size in ("1440", "2160")
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-r", "30", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-f", "mp4", tmp_name]
    try:
        _run(cmd, out_dir, cancelled, timeout=max(900 if big else 600, duration * (120 if big else 30)))
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
