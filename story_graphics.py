"""Animated story graphics that pop up when the narrator says a number.

From the voice-over's word timings (the same Whisper words used for the
captions) it finds the big moments and draws a short animation for each:
  - money    "$618 million" -> a gold counter rolling up from $0
  - percent  "40 percent"   -> the number counting up with a filling bar
  - date     "October 16, 2001" / "in 1999" -> a date stamp that types itself
Each one is drawn with Pillow into a small see-through clip and laid over the
video at the exact second the word is spoken. Graphics are kept at least
MIN_GAP seconds apart so the video never feels busy.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).resolve().parent / "clip-factory" / "fonts"
FPS = 30
MIN_GAP = 9.0
MAX_GRAPHICS = 40
GOLD = (243, 212, 136)
WHITE = (240, 242, 246)
MONTHS = ("january february march april may june july august september october november december").split()
MULT = {"thousand": 1e3, "k": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for f in (FONTS / name, FONTS / "Montserrat-Black.ttf"):
        if f.exists():
            return ImageFont.truetype(str(f), size)
    return ImageFont.load_default()


def _clean(w: str) -> str:
    return w.strip().strip(",.;:!?\"'()").lower()


# ---------- finding the moments ----------

def find_moments(words: list[dict]) -> list[dict]:
    """words: [{"word", "start", "end"}]. Returns [{"kind", "start", "value", "text", "label"}] spaced out."""
    out = []
    n = len(words)
    for i, w in enumerate(words):
        raw = w["word"].strip()
        low = _clean(raw)
        nxt = [_clean(x["word"]) for x in words[i + 1:i + 6]]
        m = re.fullmatch(r"\$?([\d,]+(?:\.\d+)?)(k|m|bn|b)?", low.replace("$", "$"))
        # money: "$618" or "618" followed by "dollars" / "$1.2" + "billion"
        if m and ("$" in raw or (nxt and nxt[0] in ("dollars", "million", "billion") and "dollars" in nxt[:2])):
            num = float(m.group(1).replace(",", ""))
            mult = 1.0
            suffix = {"k": 1e3, "m": 1e6, "bn": 1e9, "b": 1e9}.get(m.group(2) or "", 1.0)
            mult *= suffix
            if nxt and nxt[0] in MULT:
                mult *= MULT[nxt[0]]
            value = num * mult
            if value >= 1000:
                out.append({"kind": "money", "start": w["start"], "value": value, "text": money_text(value),
                            "label": _label(words, i, skip=1 if nxt and nxt[0] in MULT else 0)})
            continue
        # percent: "40%" or "40 percent"
        pm = re.fullmatch(r"([\d.]+)%", low)
        if pm or (re.fullmatch(r"[\d.]+", low) and nxt and nxt[0] in ("percent", "per")):
            try:
                v = float((pm.group(1) if pm else low))
            except ValueError:
                continue
            if 0 < v <= 100:
                out.append({"kind": "percent", "start": w["start"], "value": v, "text": f"{v:g}%",
                            "label": _label(words, i, skip=0 if pm else 1)})
            continue
        # dates: "October 16, 2001" / "in 1999"
        if low in MONTHS:
            day = nxt[0] if nxt and re.fullmatch(r"\d{1,2}(st|nd|rd|th)?", nxt[0]) else None
            year = next((x for x in nxt[:3] if re.fullmatch(r"(1[5-9]\d\d|20[0-4]\d)", x)), None)
            if year:
                text = f"{low.upper()} {re.sub(r'[a-z]', '', day)}, {year}" if day else f"{low.upper()} {year}"
                out.append({"kind": "date", "start": w["start"], "value": 0, "text": text, "label": ""})
            continue
        if re.fullmatch(r"(1[5-9]\d\d|20[0-4]\d)", low) and i and _clean(words[i - 1]["word"]) in ("in", "by", "since", "of"):
            if not (i >= 2 and _clean(words[i - 2]["word"]) in MONTHS) and not (i >= 3 and _clean(words[i - 3]["word"]) in MONTHS):
                out.append({"kind": "date", "start": w["start"], "value": 0, "text": low, "label": ""})
    # keep them apart; when two are close, money beats percent beats date
    picked: list[dict] = []
    for mo in sorted(out, key=lambda x: ({"money": 0, "percent": 1, "date": 2}[x["kind"]], x["start"])):
        if all(abs(mo["start"] - p["start"]) >= MIN_GAP for p in picked):
            picked.append(mo)
    return sorted(picked, key=lambda x: x["start"])[:MAX_GRAPHICS]


def _label(words: list[dict], i: int, skip: int) -> str:
    """The few words right after the number, as a small caption ("LOSS IN ONE QUARTER")."""
    tail = []
    for w in words[i + 1 + skip:i + 7 + skip]:
        c = _clean(w["word"])
        if c in ("dollars", "percent", "per", "cent"):
            continue
        tail.append(c)
        if w["word"].strip()[-1:] in ".,;!?" or len(tail) >= 4:
            break
    return " ".join(tail).upper()[:34]


def money_text(v: float) -> str:
    for size, word in ((1e12, "TRILLION"), (1e9, "BILLION"), (1e6, "MILLION")):
        if v >= size:
            x = v / size
            return f"${x:,.1f} {word}".replace(".0 ", " ")
    return f"${v:,.0f}"


# ---------- drawing ----------

def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def _frames(mo: dict, scale: float, duration: float):
    """Yields RGBA frames (the card only, not the whole video frame)."""
    n = int(duration * FPS)
    big = _font("Anton-Regular.ttf", int(118 * scale))
    small = _font("Montserrat-ExtraBold.ttf", int(26 * scale))
    datef = _font("Montserrat-ExtraBold.ttf", int(44 * scale))
    W, H = int(980 * scale), int(250 * scale)
    if mo["kind"] == "date":
        W, H = int(720 * scale), int(120 * scale)
    for f in range(n):
        t = f / FPS
        a = _ease(t / 0.3) * min(1.0, (duration - t) / 0.35)
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        rise = int((1 - _ease(t / 0.35)) * 30 * scale)
        if mo["kind"] == "date":
            d.rounded_rectangle([0, rise, W - 1, H - 1], radius=int(16 * scale), fill=(8, 10, 14, int(205 * a)))
            d.rectangle([0, rise, int(8 * scale), H - 1], fill=GOLD + (int(255 * a),))
            shown = mo["text"][:max(1, int(len(mo["text"]) * min(1, t / 0.7)))]
            d.text((int(36 * scale), H // 2 + rise // 2), shown, font=datef, fill=WHITE + (int(255 * a),), anchor="lm")
        else:
            k = _ease((t - 0.15) / 1.1)
            if mo["kind"] == "money":
                text = money_text(mo["value"] * k) if k < 1 else mo["text"]
            else:
                text = f"{mo['value'] * k:.0f}%" if k < 1 else mo["text"]
            d.rounded_rectangle([0, rise, W - 1, H - 1], radius=int(22 * scale), fill=(8, 10, 14, int(200 * a)),
                                outline=GOLD + (int(120 * a),), width=max(1, int(2 * scale)))
            d.text((W // 2, int(H * 0.44) + rise), text, font=big, fill=GOLD + (int(255 * a),), anchor="mm")
            if mo["kind"] == "percent":
                bw = int((W - 120 * scale) * k * mo["value"] / 100)
                y = int(H * 0.8) + rise
                d.rounded_rectangle([int(60 * scale), y - 5, W - int(60 * scale), y + 5], radius=5, fill=(255, 255, 255, int(40 * a)))
                d.rounded_rectangle([int(60 * scale), y - 5, int(60 * scale) + bw, y + 5], radius=5, fill=GOLD + (int(255 * a),))
            elif mo["label"]:
                d.text((W // 2, int(H * 0.82) + rise), mo["label"], font=small, fill=WHITE + (int(230 * a),), anchor="mm")
        yield im


def render_clip(mo: dict, out: Path, scale: float, duration: float = 3.2) -> tuple[int, int]:
    frames = list(_frames(mo, scale, duration))
    w, h = frames[0].size
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}",
                             "-r", str(FPS), "-i", "-", "-c:v", "qtrle", str(out)], stdin=subprocess.PIPE)
    for im in frames:
        proc.stdin.write(im.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg could not write a graphic")
    return w, h


def add_graphics(video_in: Path, words: list[dict], video_out: Path, width: int, height: int, work_dir: Path,
                 progress: Optional[Callable[[str], None]] = None) -> int:
    """Lays the graphics over video_in. Returns how many were added (0 = video copied as is)."""
    moments = find_moments(words)
    if not moments:
        return 0
    scale = min(width / 1920, height / 1080) * (1.0 if width >= height else 1.6)
    inputs, chain, cur = [], [], "0:v"
    for k, mo in enumerate(moments):
        if progress:
            progress(f"Drawing graphic {k + 1}/{len(moments)}: {mo['text']}")
        clip = work_dir / f"g{k:02d}.mov"
        w, h = render_clip(mo, clip, scale)
        inputs += ["-itsoffset", f"{mo['start']:.2f}", "-i", str(clip)]
        if mo["kind"] == "date":
            x, y = int(60 * scale), int(height * 0.08)
        else:
            x, y = (width - w) // 2, int(height * (0.1 if width >= height else 0.2))
        chain.append(f"[{cur}][{k + 1}:v]overlay={x}:{y}:eof_action=pass[o{k}]")
        cur = f"o{k}"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_in), *inputs,
                    "-filter_complex", ";".join(chain), "-map", f"[{cur}]", "-map", "0:a?",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "copy",
                    str(video_out)], check=True, timeout=max(600, len(moments) * 120))
    return len(moments)
