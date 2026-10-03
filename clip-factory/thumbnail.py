"""Thumbnails for every clip: the best frame + the hook in big letters.

  clip_001_cover.jpg  1080x1920  for YouTube Shorts, Instagram Reels and Facebook Reels covers
  clip_001_thumb.jpg  1280x720   for YouTube videos, Facebook posts, anything wide
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

APP_DIR = Path(__file__).resolve().parent
FONT_PATHS = [APP_DIR / "fonts" / "Anton-Regular.ttf", APP_DIR.parent / "fonts" / "Anton-Regular.ttf"]
YELLOW, WHITE, BLACK = (255, 212, 0), (255, 255, 255), (0, 0, 0)
DANGLING = {"after", "for", "with", "when", "to", "of", "on", "by", "from", "in", "at", "and", "but", "or", "the", "a", "an",
            "his", "her", "their", "my", "your", "our", "while", "before", "because", "about", "into", "as", "if", "so"}
BREAKS = {"after", "when", "because", "while", "before", "for", "with", "as", "if", "then", "and", "but", "until", "since", "so"}


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_PATHS:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size=size)


def hook_words(title: str, max_words: int = 5) -> str:
    """'He Turned Down $1 Million for This Reason' -> 'HE TURNED DOWN $1 MILLION'."""
    words = [w for w in re.findall(r"[\w$%'!?.,-]+", title or "") if w.strip(".,-")]
    if len(words) > max_words:  # too long: cut at a natural break ("... after", "... when") if there is one
        cut = next((i for i in range(2, max_words + 1) if words[i].lower().strip("!?.,") in BREAKS), None)
        if cut:
            words = words[:cut]
    words = words[:max_words]
    while len(words) > 2 and words[-1].lower().strip("!?.,") in DANGLING:  # never end on "after", "for"...
        words.pop()
    text = " ".join(words).strip(" ,.-")
    return text.upper() or "WATCH THIS"


def _highlight(words: list[str]) -> int:
    """The word to paint yellow: a number/money word, else the longest one."""
    for i, w in enumerate(words):
        if re.search(r"[\d$%]", w):
            return i
    return max(range(len(words)), key=lambda i: len(words[i].strip("!?.,"))) if words else -1


def best_frame(video: Path, start: float, end: float) -> Image.Image:
    """The most typical, sharp frame of start..end (ffmpeg's thumbnail filter), as a PIL image."""
    dur = max(1.0, end - start)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "frame.png"
        for vf, extra in ((f"fps=2,scale=1280:-2,thumbnail={max(2, int(dur * 2))}", ["-t", f"{dur:.2f}"]), ("scale=1280:-2", [])):
            seek = start if extra else start + dur / 2
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{seek:.2f}", *extra, "-i", str(video),
                            "-vf", vf, "-frames:v", "1", str(out)], capture_output=True, timeout=120)
            if out.exists():
                return Image.open(out).convert("RGB")
    raise RuntimeError("couldn't read a frame from the video")


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    scale = max(w / img.width, h / img.height)
    img = img.resize((max(w, round(img.width * scale)), max(h, round(img.height * scale))), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def _wrap(words: list[str], font, max_w: int, draw) -> list[list[int]]:
    lines, cur = [], []
    for i, w in enumerate(words):
        test = " ".join(words[j] for j in cur + [i])
        if cur and draw.textlength(test, font=font) > max_w:
            lines.append(cur)
            cur = [i]
        else:
            cur.append(i)
    if cur:
        lines.append(cur)
    return lines


def _layout(text: str, max_w: int, max_h: int, max_lines: int, start: int, draw):
    words = text.split()
    size = start
    while size > 30:
        font = _font(size)
        lines = _wrap(words, font, max_w, draw)
        line_h = int(size * 1.08)
        if len(lines) <= max_lines and line_h * len(lines) <= max_h and \
                all(draw.textlength(" ".join(words[j] for j in ln), font=font) <= max_w for ln in lines):
            return words, lines, font, line_h
        size -= 6
    font = _font(30)
    return words, _wrap(words, font, max_w, draw), font, 33


def _draw_text(img: Image.Image, text: str, box: tuple[int, int, int, int], max_lines: int, start: int, align: str) -> None:
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(img)
    words, lines, font, line_h = _layout(text, x1 - x0, y1 - y0, max_lines, start, d)
    hi = _highlight(words)
    stroke = max(3, font.size // 11)
    space = d.textlength(" ", font=font)
    y = y0 + ((y1 - y0) - line_h * len(lines)) // 2
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    for pass_ in ("shadow", "text"):
        yy = y
        for ln in lines:
            lw = d.textlength(" ".join(words[j] for j in ln), font=font)
            x = x0 + ((x1 - x0) - lw) / 2 if align == "center" else x0
            for j in ln:
                if pass_ == "shadow":
                    sd.text((x + stroke, yy + stroke * 1.5), words[j], font=font, fill=(0, 0, 0, 170))
                else:
                    d.text((x, yy), words[j], font=font, fill=YELLOW if j == hi else WHITE, stroke_width=stroke, stroke_fill=BLACK)
                x += d.textlength(words[j], font=font) + space
            yy += line_h
        if pass_ == "shadow":
            img.paste(Image.alpha_composite(img.convert("RGBA"), shadow.filter(ImageFilter.GaussianBlur(stroke))).convert("RGB"))
            d = ImageDraw.Draw(img)


def _fade(img: Image.Image, direction: str, strength: int = 200) -> Image.Image:
    """Darkens one side so white letters stay readable on any picture."""
    w, h = img.size
    grad = Image.new("L", (256, 1) if direction == "left" else (1, 256))
    for i in range(256):
        v = int(strength * (1 - i / 255) ** 1.6)
        grad.putpixel((i, 0) if direction == "left" else (0, i), v)
    mask = grad.resize((w, h))
    dark = Image.new("RGB", (w, h), BLACK)
    return Image.composite(dark, img, mask)


def make(video: Path, start: float, end: float, title: str, cover_out: Path, thumb_out: Path,
         frame: Image.Image | None = None) -> None:
    text = hook_words(title)
    frame = frame or best_frame(video, start, end)
    # vertical cover: text in the upper middle - Shorts/Reels put buttons and captions over the bottom third
    v = _cover(frame, 1080, 1920)
    v = Image.blend(v, Image.new("RGB", v.size, BLACK), 0.15)
    v = _fade(v, "top", 210)
    _draw_text(v, text, (70, 260, 1010, 1000), 4, 190, "center")
    v.save(cover_out, quality=90)
    # wide thumbnail: text on the left, picture on the right
    t = _cover(frame, 1280, 720)
    t = _fade(t, "left", 225)
    _draw_text(t, text, (50, 60, 760, 660), 3, 150, "left")
    t.save(thumb_out, quality=90)
