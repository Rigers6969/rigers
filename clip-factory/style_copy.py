"""Copy the style of a video you like: give a link (YouTube, Instagram, TikTok...) or the file, and the settings
are set to make clips like it.

What is read:
  - its length (-> clip length) and how fast it cuts (fast cutting -> zoom punch-ins on big moments)
  - pictures from it: where the captions sit, their colours (yellow key word -> Hormozi, green -> Karaoke,
    purple box -> Box), a hook title box at the top, split screen, blurred bands (whole picture), a black page
    with text (text post)
  - when an AI that can see pictures is set up (a free Gemini key is best), the AI looks at the pictures too and
    picks the closest style - that's much better than the built-in guess.
"""
from __future__ import annotations

import base64
import io
import json
import re
import subprocess
from pathlib import Path

from PIL import Image

import ai
import downloader
import renderer
import trends

APP_DIR = Path(__file__).resolve().parent
WORK = APP_DIR / "cache" / "style"
FRACTIONS = (0.12, 0.28, 0.44, 0.6, 0.76, 0.92)

PROMPT = """These are {n} frames, in order, from one short vertical video (a viral clip, {dur:.0f} seconds long, \
{cuts:.1f} scene cuts per 10 seconds). I want to make new clips edited exactly like it. Look at how it is EDITED \
(captions, layout, effects), not at what it is about.

Pick the closest option for each:
- layout: "crop" (the video fills the whole screen), "fit" (the whole picture in the middle with a blurred copy \
above and below), "podcast" (split screen: two people, one above the other), "gameplay" (the clip on top and \
gameplay like Minecraft/GTA/Subway Surfers below), "post" (a black page: the video at the top and a paragraph of \
text under it)
- captions: "hormozi" (bold ALL CAPS sans-serif with a black outline, 2-3 words, one word yellow or green), \
"beast" (comic/cartoon font, 1-2 huge tilted words in colour), "highlight" (karaoke: a few words, the spoken one \
changes colour), "box" (the spoken word sits in a coloured box), "iman" (calm lowercase white text, no colours), \
"story" (big slanted key words mixed with small words, stacked, maybe underlined), "simple" (plain white \
subtitles), "none" (no captions)
- caption_position: "middle" or "low" (lower third)
- caption_size: "s", "m", "l" or "xl" compared with the screen width
- emojis: true if emojis pop up on screen
- hook_title: true if a title/hook text stays at the top
- zoom_punches: true if the picture zooms in suddenly on moments
- kind: "stream" (streamer/Twitch/Kick clip), "podcast" (people talking at mics) or "other"
- style: one short sentence describing the editing style in simple English
Answer ONLY with JSON: {{"layout": "", "captions": "", "caption_position": "", "caption_size": "", "emojis": false, \
"hook_title": false, "zoom_punches": false, "kind": "", "style": ""}}"""


class StyleError(Exception):
    pass


def fetch(url: str, cookies: str = "") -> Path:
    """Downloads the example video (720p is plenty to read a style)."""
    try:
        import yt_dlp
    except ImportError as exc:
        raise StyleError("yt-dlp isn't installed - close the app and double-click start.bat again.") from exc
    WORK.mkdir(parents=True, exist_ok=True)
    for old in WORK.glob("example*"):
        old.unlink(missing_ok=True)
    opts = {
        "format": "bv*[height<=720]+ba/b[height<=720]/b", "merge_output_format": "mp4",
        "outtmpl": str(WORK / "example.%(ext)s"), "noplaylist": True, "quiet": True, "no_warnings": True,
        "noprogress": True, "socket_timeout": 30, "retries": 3, "logger": downloader._QuietLogger(),
    }
    if downloader.js_runtimes():
        opts["js_runtimes"] = downloader.js_runtimes()
    attempts = [opts]
    target = downloader._impersonate_target()
    if target:
        attempts.append(dict(opts, impersonate=target))
    if cookies in downloader.COOKIE_BROWSERS:
        attempts.append(dict(attempts[-1], cookiesfrombrowser=(cookies,)))
    last = None
    for o in attempts:
        try:
            with yt_dlp.YoutubeDL(o) as ydl:
                info = ydl.extract_info(url, download=True)
                if info and info.get("_type") == "playlist":
                    info = next((e for e in info.get("entries") or [] if e), None)
            got = sorted(WORK.glob("example.*"), key=lambda p: p.stat().st_size, reverse=True)
            if got:
                return got[0]
        except Exception as exc:
            last = exc
            if not downloader._blocked(exc) and "login" not in str(exc).lower():
                break
    msg = trends.clean_error(last) if last else "nothing to download at that link"
    if re.search(r"instagram", url, re.I) and not cookies:
        msg += " - Instagram often needs your login: pick your browser under 'Download with my login' and try again, or upload the video instead."
    raise StyleError(f"Couldn't download the example video: {msg}")


def _cuts_per_10s(path: Path, duration: float) -> float:
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-an", "-vf",
                              "scale=240:-2,select='gt(scene,0.32)',metadata=print", "-f", "null", "-"],
                             capture_output=True, text=True, timeout=300).stderr
    except (OSError, subprocess.TimeoutExpired):
        return 0.0
    return len(re.findall(r"pts_time:", out)) / max(1.0, duration) * 10


def _frames(path: Path, duration: float) -> list[Image.Image]:
    out = []
    for f in FRACTIONS:
        try:
            raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{duration * f:.2f}", "-i", str(path),
                                  "-frames:v", "1", "-vf", "scale=432:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                                 capture_output=True, timeout=60).stdout
            if raw:
                out.append(Image.open(io.BytesIO(raw)).convert("RGB"))
        except (OSError, subprocess.TimeoutExpired):
            continue
    return out


def _measure(im: Image.Image, n: int = 20) -> dict:
    """Per horizontal band (n of them): outlined white text, yellow, green, purple, near-black, edge strength."""
    import numpy as np
    a = np.asarray(im, dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = (r * 3 + g * 6 + b) // 10
    bright, dark = lum > 225, lum < 50
    near_dark = np.zeros_like(dark)
    for dx in (-3, -2, 2, 3):  # white letters with a black outline: white right next to black
        near_dark |= np.roll(dark, dx, axis=1)
    masks = {
        "text": bright & near_dark, "yellow": (r > 200) & (g > 170) & (b < 90), "green": (g > 190) & (r < 140) & (b < 140),
        "purple": (b > 200) & (r > 100) & (r < 190) & (g < 120), "black": lum < 22,
    }
    edges = np.abs(np.diff(lum, axis=1)).astype(np.float32)
    h = a.shape[0]
    out = {k: [] for k in list(masks) + ["edges"]}
    for i in range(n):
        y0, y1 = h * i // n, h * (i + 1) // n
        for k, m in masks.items():
            out[k].append(float(m[y0:y1].mean()))
        out["edges"].append(float(edges[y0:y1].mean()))
    out["white_rows"] = bright.mean(axis=1)
    return out


def guess(frames: list[Image.Image], cuts: float) -> dict:
    """The built-in reading of the frames (used alone without a seeing AI)."""
    import numpy as np
    n = 20
    ms = [_measure(f, n) for f in frames]
    avg = {k: np.mean([m[k] for m in ms], axis=0) for k in ("text", "yellow", "green", "purple", "black", "edges")}
    out = {"zoom_punches": cuts >= 3.0}
    # a black page with the video on top and text below
    if (avg["black"][10:18] > 0.6).sum() >= 5 and (avg["black"][2:7] < 0.5).all() and avg["text"][9:18].sum() > 0.005:
        out.update(layout="post", captions="none")
        return out
    # captions: the band with the most outlined white or coloured text, below the top 15%
    score = avg["text"] + avg["yellow"] * 0.5 + avg["green"] * 0.5
    cap = int(np.argmax(score[3:n - 1])) + 3
    skip = set(range(cap - 1, cap + 2)) if score[cap] >= 0.002 else set()
    # blurred bands above and below a sharp picture (the hook title and the captions don't count)
    def edge(rng):
        vals = [avg["edges"][b] for b in rng if b not in skip]
        return float(np.mean(vals)) if vals else 0.0
    top_e, mid_e, bot_e = edge(range(3, 6)), edge(range(8, 12)), edge(range(14, 18))
    if mid_e > 3.0 and mid_e > 3.0 * max(top_e, bot_e, 0.5):
        out["layout"] = "fit"
    # (split screens are left to the AI that can see: from pictures alone a caption looks like a seam)
    out.setdefault("layout", "crop")
    # hook title: a white box near the top in most frames
    out["hook_title"] = sum(float(m["white_rows"][int(len(m["white_rows"]) * 0.04):int(len(m["white_rows"]) * 0.16)].max()) > 0.25
                            for m in ms) >= max(2, len(ms) // 2)
    if score[cap] < 0.002:
        out["captions"] = "none"
        return out
    out["caption_position"] = "middle" if cap <= 12 else "low"
    near = slice(max(0, cap - 1), min(n, cap + 2))
    # colour in the caption area compared with the rest of the picture (the video itself has colours too)
    yel, grn, pur = (float(avg[k][near].mean() - np.median(avg[k])) * 3 for k in ("yellow", "green", "purple"))
    out["captions"] = "box" if pur > 0.03 else "highlight" if grn > max(yel, 0.004) else "hormozi"
    tall = int((avg["text"][near] > 0.5 * avg["text"][cap]).sum())
    out["caption_size"] = "xl" if tall >= 3 and avg["text"][cap] > 0.05 else "l" if avg["text"][cap] > 0.03 else "m"
    return out


def _jpeg(im: Image.Image, width: int = 432) -> bytes:
    im = im.copy()
    im.thumbnail((width, width * 2))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return buf.getvalue()


CHOICES = {
    "layout": renderer.LAYOUTS, "captions": ("hormozi", "beast", "highlight", "box", "iman", "story", "simple", "none"),
    "caption_position": ("middle", "low"), "caption_size": ("s", "m", "l", "xl"), "kind": ("stream", "podcast", "other"),
}


def read(path: Path) -> dict:
    """The settings that make clips like this video, and what was found (for the page)."""
    try:
        info = renderer.probe(path)
    except renderer.RenderError as exc:
        raise StyleError(f"That isn't a video I can read: {exc}") from exc
    dur = info["duration"] or 30.0
    cuts = _cuts_per_10s(path, dur)
    frames = _frames(path, dur)
    if not frames:
        raise StyleError("Couldn't take pictures from the example video.")
    found = guess(frames, cuts)
    engine = "built-in reading (add a free Gemini key in AI engines for a much better reading)"
    seen = None
    try:
        got = ai.look(ai.load_keys(), PROMPT.format(n=len(frames), dur=dur, cuts=cuts), [_jpeg(f) for f in frames])
    except Exception:
        got = None
    if got:
        raw, who = got
        try:
            m = re.search(r"\{.*\}", raw, re.S)
            seen = json.loads(m.group(0)) if m else None
        except ValueError:
            seen = None
        if isinstance(seen, dict):
            engine = f"{who} looked at the video"
            for k, allowed in CHOICES.items():
                if seen.get(k) in allowed:
                    found[k] = seen[k]
            for k in ("emojis", "hook_title", "zoom_punches"):
                if isinstance(seen.get(k), bool):
                    found[k] = seen[k]
            if cuts >= 4:
                found["zoom_punches"] = True
    # clip length: about as long as the example
    lo = max(5, min(170, int(dur * 0.75)))
    hi = max(lo + 5, min(180, int(dur * 1.25) + 1))
    settings = {
        "layout": found.get("layout", "crop"), "captions": found.get("captions", "hormozi"),
        "capPos": found.get("caption_position", "middle"), "capSize": found.get("caption_size", "m"),
        "showTitle": bool(found.get("hook_title", False)), "minLen": lo, "maxLen": hi,
    }
    if "emojis" in found:  # only an AI that can see tells emojis; otherwise your setting stays
        settings["emojis"] = bool(found["emojis"])
    if found.get("zoom_punches") or seen:  # fast cutting turns zooms on; only the AI turns them off
        settings["zooms"] = bool(found.get("zoom_punches"))
    if found.get("kind") in ("stream", "podcast"):
        settings["kind"] = found["kind"]
    elif found.get("kind") == "other":
        settings["kind"] = ""
    names = {"crop": "Fill screen", "fit": "Whole picture + blurred background", "podcast": "Split screen",
             "gameplay": "Clip on top + gameplay below", "post": "Text post (video on top, text below)",
             "hormozi": "Hormozi", "beast": "MrBeast", "highlight": "Karaoke", "box": "Box", "iman": "Clean",
             "story": "Story", "simple": "Simple white", "none": "No captions"}
    sizes = {"s": "Small", "m": "Normal", "l": "Big", "xl": "Huge"}
    summary = [
        f"Length: {dur:.0f} seconds - your clips will be {lo}-{hi} seconds",
        f"Editing speed: {cuts:.1f} cuts every 10 seconds" + (" (fast - zoom punch-ins on)" if settings.get("zooms") else ""),
        f"Layout: {names[settings['layout']]}",
        "Captions: " + (names[settings["captions"]] if settings["captions"] == "none" else
                        f"{names[settings['captions']]}, {sizes[settings['capSize']]}, "
                        f"{'in the middle' if settings['capPos'] == 'middle' else 'lower third'}"),
        ("" if "emojis" not in settings else f"Emoji pops: {'yes' if settings['emojis'] else 'no'} - ")
        + f"Hook title at the top: {'yes' if settings['showTitle'] else 'no'}",
    ]
    if isinstance(seen, dict) and isinstance(seen.get("style"), str) and seen["style"].strip():
        summary.insert(0, seen["style"].strip()[:200])
    pics = ["data:image/jpeg;base64," + base64.b64encode(_jpeg(f, 216)).decode() for f in frames[1:5]]
    return {"settings": settings, "summary": summary, "engine": engine, "frames": pics}
