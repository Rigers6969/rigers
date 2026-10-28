"""Click-worthy documentary thumbnails made from the video's own footage.

Instead of text on a plain background, every thumbnail is built on the most
striking picture from the video (sharp, high contrast, colourful), graded
dark and cinematic, with 2-4 huge words that make people curious. Three
looks are made for every video so you can pick one on the Review page:

  impact - the photo full screen, giant text on the left (second line in
           yellow), a red circle and arrow on the most interesting spot
  split  - dark panel with the text on the left, the photo cut in at an angle
  stamp  - the photo with a red rubber-stamp word (FRAUD, COLLAPSE...) and a
           big number at the top

Texts come from the script writer when one is given (different from the
title, built for curiosity), otherwise from the title itself.
"""
from __future__ import annotations

import csv
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Optional

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

APP_DIR = Path(__file__).resolve().parent
W, H = 1280, 720
YELLOW = (255, 214, 10)
RED = (232, 30, 37)
WHITE = (255, 255, 255)
STOP = set("""a an the and or of to in on for with at by from as is are was were be been it its this that how why what
who when where which into about after before over his her their they he she we you your our just than then so did does""".split())
STAMPS = [("fraud", "FRAUD"), ("ponzi", "PONZI"), ("scam", "SCAM"), ("bankrupt", "BANKRUPT"), ("collapse", "COLLAPSED"),
          ("prison", "GUILTY"), ("sentenced", "GUILTY"), ("war", "WAR"), ("lost", "LOST"), ("secret", "SECRET"),
          ("mystery", "UNSOLVED"), ("discover", "DISCOVERED"), ("dead", "DEAD"), ("died", "DEAD")]

TEXT_PROMPT = """You make YouTube thumbnails for the documentary channel "{channel}".
Video title: {title}
Topic: {topic}

Write 3 thumbnail texts. Each is 2-4 words, ALL CAPS, makes people curious, and does NOT repeat the title.
Good examples: "$70 BILLION GONE", "HE KNEW EVERYTHING", "NOBODY NOTICED", "THE LAST MEMO".
Use only facts from the title/topic. Answer with JSON only: ["TEXT ONE", "TEXT TWO", "TEXT THREE"]"""


def _font(size: int, name: str = "Anton-Regular.ttf") -> ImageFont.FreeTypeFont:
    for f in (APP_DIR / "fonts" / name, APP_DIR / "clip-factory" / "fonts" / name, APP_DIR / "fonts" / "Anton-Regular.ttf"):
        if f.exists():
            return ImageFont.truetype(str(f), size)
    return ImageFont.load_default()


# ---------- picking the picture ----------

def candidate_images(video_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for manifest in (video_dir / "media").rglob("*.csv") if (video_dir / "media").exists() else []:
        try:
            with manifest.open(encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    p = Path(row.get("local_path") or "")
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") and p.exists():
                        paths.append(p)
        except (OSError, csv.Error, KeyError):
            continue
    if not paths and (video_dir / "media").exists():
        paths = [p for p in (video_dir / "media").rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    if not paths:  # fall back to frames from the finished video
        video = next((video_dir / n for n in ("final_edited.mp4", "final.mp4") if (video_dir / n).exists()), None)
        if video:
            out = video_dir / "_thumb_frames"
            out.mkdir(exist_ok=True)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", "fps=1/20,scale=1280:-2",
                            "-frames:v", "12", str(out / "f%02d.jpg")], timeout=300)
            paths = sorted(out.glob("f*.jpg"))
    return list(dict.fromkeys(paths))[:60]


def image_score(img: Image.Image) -> float:
    """Sharp, high-contrast, colourful pictures make the best thumbnails."""
    small = img.convert("RGB").resize((160, 90))
    gray = small.convert("L")
    px = list(gray.getdata())
    mean = sum(px) / len(px)
    contrast = (sum((p - mean) ** 2 for p in px) / len(px)) ** 0.5
    edges = sum(gray.filter(ImageFilter.FIND_EDGES).getdata()) / len(px)
    sat = sum(small.convert("HSV").getchannel("S").getdata()) / len(px)
    too_dark_or_bright = abs(mean - 115) / 115
    return contrast * 0.9 + edges * 1.2 + sat * 0.25 - too_dark_or_bright * 25


def best_images(video_dir: Path, n: int = 3) -> list[Image.Image]:
    scored = []
    for p in candidate_images(video_dir):
        try:
            img = Image.open(p)
            img.load()
            if img.width < 480:
                continue
            scored.append((image_score(img), img.convert("RGB")))
        except Exception:
            continue
    scored.sort(key=lambda x: -x[0])
    return [img for _, img in scored[:n]]


def focus_point(img: Image.Image) -> tuple[float, float]:
    """Where the eye goes: the busiest area (edges), as 0..1 coordinates."""
    g = img.convert("L").resize((64, 36)).filter(ImageFilter.FIND_EDGES).filter(ImageFilter.GaussianBlur(3))
    best, bx, by = -1, 32, 18
    for y in range(6, 30):
        for x in range(8, 56):
            v = g.getpixel((x, y))
            if v > best:
                best, bx, by = v, x, y
    return bx / 64, by / 36


# ---------- texts ----------

def texts_from_title(title: str) -> list[str]:
    money = re.search(r"\$\s?[\d.,]+\s?(?:billion|million|trillion|[bmk])?", title, re.I)
    words = [w for w in re.findall(r"[A-Za-z0-9$']+", title) if w.lower() not in STOP]
    out = []
    if money:
        out.append((money.group(0).replace(" ", " ") + " GONE").upper())
    if words:
        out.append(" ".join(words[:3]).upper())
        out.append(" ".join(words[-3:]).upper())
    out.append("NOBODY SAW IT COMING")
    return list(dict.fromkeys(out))[:3]


def make_texts(title: str, topic: str, channel: str, writer=None) -> list[str]:
    if writer is not None:
        try:
            raw = writer._call_model(TEXT_PROMPT.format(channel=channel, title=title, topic=topic), max_tokens=200)
            m = re.search(r"\[.*\]", raw or "", re.S)
            items = [str(x).strip().upper() for x in json.loads(m.group(0))] if m else []
            items = [t for t in items if 1 <= len(t.split()) <= 5]
            if len(items) >= 2:
                return (items + texts_from_title(title))[:3]
        except Exception:
            pass
    return texts_from_title(title)


def stamp_word(title: str, topic: str) -> str:
    t = (title + " " + topic).lower()
    return next((word for key, word in STAMPS if key in t), "EXPOSED")


# ---------- drawing helpers ----------

def _cover(img: Image.Image, w: int, h: int, focus: tuple[float, float] = (0.5, 0.5)) -> Image.Image:
    scale = max(w / img.width, h / img.height)
    im = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1), Image.LANCZOS)
    x = int(min(max(0, focus[0] * im.width - w / 2), im.width - w))
    y = int(min(max(0, focus[1] * im.height - h / 2), im.height - h))
    return im.crop((x, y, x + w, y + h))


def grade(img: Image.Image) -> Image.Image:
    """Cinematic: more contrast, a little less colour, teal shadows / warm highlights, dark edges."""
    img = ImageEnhance.Contrast(img).enhance(1.25)
    img = ImageEnhance.Color(img).enhance(0.9)
    r, g, b = img.split()
    r = r.point(lambda v: min(255, int(v * 1.06 + 4)))
    b = b.point(lambda v: min(255, int(v * 0.92 + 14)))
    img = Image.merge("RGB", (r, g, b))
    vign = Image.new("L", img.size, 0)
    ImageDraw.Draw(vign).ellipse([-img.width * 0.25, -img.height * 0.3, img.width * 1.25, img.height * 1.3], fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(120))
    return Image.composite(img, Image.new("RGB", img.size, (0, 0, 0)), vign.point(lambda v: 70 + v * 185 // 255))


def _fit_font(text: str, max_w: int, start: int, name: str = "Anton-Regular.ttf") -> ImageFont.FreeTypeFont:
    size = start
    while size > 40:
        f = _font(size, name)
        if f.getlength(text) <= max_w:
            return f
        size -= 6
    return _font(40, name)


def _split_lines(text: str) -> list[str]:
    words = text.split()
    if len(words) <= 2:
        return [" ".join(words)]
    cut = math.ceil(len(words) / 2)
    return [" ".join(words[:cut]), " ".join(words[cut:])]


def _outlined(d: ImageDraw.ImageDraw, xy, text, font, fill, stroke=10, anchor="la"):
    x, y = xy
    d.text((x + 8, y + 10), text, font=font, fill=(0, 0, 0, 170), anchor=anchor, stroke_width=stroke, stroke_fill=(0, 0, 0, 170))
    d.text((x, y), text, font=font, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=(0, 0, 0))


def _arrow(d: ImageDraw.ImageDraw, start, end, width=16, color=RED):
    d.line([start, end], fill=color, width=width)
    ang = math.atan2(end[1] - start[1], end[0] - start[0])
    head = 46
    pts = [end, (end[0] - head * math.cos(ang - 0.5), end[1] - head * math.sin(ang - 0.5)),
           (end[0] - head * math.cos(ang + 0.5), end[1] - head * math.sin(ang + 0.5))]
    d.polygon(pts, fill=color)


# ---------- the three looks ----------

def style_impact(photo: Image.Image, text: str) -> Image.Image:
    fx, fy = focus_point(photo)
    base = grade(_cover(photo, W, H, (min(0.75, fx + 0.15), fy)))
    shade = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shade).rectangle([0, 0, int(W * 0.5), H], fill=235)
    shade = shade.filter(ImageFilter.GaussianBlur(110))
    base = Image.composite(Image.new("RGB", (W, H)), base, shade)
    im = base.convert("RGBA")
    d = ImageDraw.Draw(im)
    lines = _split_lines(text)
    y = H // 2 - (len(lines) * 150) // 2
    for i, line in enumerate(lines):
        f = _fit_font(line, int(W * 0.56), 170)
        _outlined(d, (56, y), line, f, YELLOW if i == len(lines) - 1 else WHITE)
        y += f.size + 6
    cx, cy = int(W * 0.72), int(H * 0.45)
    fx2, fy2 = focus_point(base)
    if fx2 > 0.55:
        cx, cy = int(fx2 * W), int(fy2 * H)
    r = 120
    cy = min(cy, H - r - 110)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=RED, width=14)
    _arrow(d, (cx - r - 170, cy + r + 70), (cx - r * 0.78, cy + r * 0.6))
    return im.convert("RGB")


def style_split(photo: Image.Image, text: str) -> Image.Image:
    im = Image.new("RGB", (W, H), (10, 10, 14))
    pic = grade(_cover(photo, int(W * 0.66), H, focus_point(photo)))
    mask = Image.new("L", pic.size, 0)
    ImageDraw.Draw(mask).polygon([(120, 0), (pic.width, 0), (pic.width, H), (0, H)], fill=255)
    im.paste(pic, (W - pic.width, 0), mask)
    d = ImageDraw.Draw(im, "RGBA")
    d.polygon([(W - pic.width + 120 - 14, 0), (W - pic.width + 120, 0), (W - pic.width, H), (W - pic.width - 14, H)], fill=RED)
    lines = _split_lines(text)
    y = H // 2 - (len(lines) * 140) // 2
    for i, line in enumerate(lines):
        f = _fit_font(line, int(W * 0.42), 150)
        _outlined(d, (48, y), line, f, RED if i == len(lines) - 1 else WHITE, stroke=6)
        y += f.size + 8
    d.rectangle([48, y + 14, 48 + 220, y + 26], fill=YELLOW)
    return im


def style_stamp(photo: Image.Image, text: str, stamp: str) -> Image.Image:
    base = grade(_cover(photo, W, H, focus_point(photo)))
    base = ImageEnhance.Color(base).enhance(0.55)
    im = base.convert("RGBA")
    d = ImageDraw.Draw(im)
    top = Image.new("L", (W, H), 0)
    ImageDraw.Draw(top).rectangle([0, 0, W, 170], fill=210)
    top = top.filter(ImageFilter.GaussianBlur(60))
    im = Image.composite(Image.new("RGBA", (W, H), (0, 0, 0, 255)), im, top)
    d = ImageDraw.Draw(im)
    f = _fit_font(text, W - 120, 150)
    _outlined(d, (W // 2, 105), text, f, WHITE, stroke=8, anchor="mm")
    sf = _font(190)
    tw, th = int(sf.getlength(stamp)) + 90, 260
    st = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    sd = ImageDraw.Draw(st)
    sd.rounded_rectangle([8, 8, tw - 8, th - 8], radius=22, outline=RED + (240,), width=18)
    sd.text((tw // 2, th // 2), stamp, font=sf, fill=RED + (240,), anchor="mm")
    grain = Image.effect_noise((tw, th), 90).convert("L").point(lambda v: 255 if v > 70 else 120)
    st.putalpha(ImageChops.multiply(st.getchannel("A"), grain))
    st = st.rotate(-12, expand=True, resample=Image.BICUBIC)
    im.alpha_composite(st, (W - st.width - 40, H - st.height - 30))
    return im.convert("RGB")


# ---------- main ----------

def make_thumbnails(video_dir: Path, title: str, topic: str = "", channel: str = "", writer=None) -> list[Path]:
    """Writes thumb_1.jpg (impact), thumb_2.jpg (split), thumb_3.jpg (stamp) and thumbs.json. Returns the paths."""
    photos = best_images(video_dir, 3)
    if not photos:
        return []
    while len(photos) < 3:
        photos.append(photos[0])
    texts = make_texts(title, topic, channel, writer)
    while len(texts) < 3:
        texts.append(texts[0])
    looks = [("impact", style_impact(photos[0], texts[0])), ("split", style_split(photos[1], texts[1])),
             ("stamp", style_stamp(photos[2], texts[2], stamp_word(title, topic)))]
    out = []
    for i, (name, im) in enumerate(looks, 1):
        p = video_dir / f"thumb_{i}.jpg"
        im.save(p, quality=92)
        out.append(p)
    (video_dir / "thumbs.json").write_text(json.dumps(
        [{"file": p.name, "look": n, "text": t} for p, (n, _), t in zip(out, looks, texts)], indent=2), encoding="utf-8")
    return out
