"""Drawn illustrations for a story, for when no photos can be downloaded.

    python illustrate.py radium_girls OUT_DIR

Writes scene_01.png, scene_02.png ... (one per scene that wants a picture). photo_short.py
uses them with:  --offline-images OUT_DIR --no-grade
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

APP = Path(__file__).resolve().parent
IW, IH = 1400, 1260
GREEN = (150, 255, 110)
CREAM = (238, 226, 198)
INK = (10, 12, 16)
ANTON = str(APP / "fonts" / "Anton-Regular.ttf")
ARCH = str(APP / "fonts" / "ArchivoBlack-Regular.ttf")


def F(path, size):
    return ImageFont.truetype(path, size)


def gradient(top, bottom, w=IW, h=IH):
    t = np.linspace(0, 1, h)[:, None, None]
    arr = np.array(top)[None, None, :] * (1 - t) + np.array(bottom)[None, None, :] * t
    return np.repeat(arr, w, axis=1).astype(np.float32)


def add(base: np.ndarray, layer: Image.Image, glow: float = 0.0, radius: int = 30, sharp: float = 1.0) -> np.ndarray:
    """Adds a drawn layer (black = nothing) to the picture, with an optional soft glow around it."""
    arr = np.asarray(layer, dtype=np.float32)
    out = base + arr * sharp
    if glow:
        for r, k in ((radius, glow), (radius * 3, glow * 0.6)):
            out += np.asarray(layer.filter(ImageFilter.GaussianBlur(r)), dtype=np.float32) * k
    return out


def over(base: np.ndarray, layer: Image.Image) -> np.ndarray:
    """Paints an RGBA layer on top (normal paint, not light)."""
    rgba = np.asarray(layer, dtype=np.float32)
    a = rgba[..., 3:4] / 255
    return base * (1 - a) + rgba[..., :3] * a


def blank(mode="RGB"):
    return Image.new(mode, (IW, IH), (0, 0, 0, 0) if mode == "RGBA" else (0, 0, 0))


def finish(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def woman(d: ImageDraw.ImageDraw, cx: float, by: float, s: float, fill, outline=None, width=0, turn=0.0):
    """1920s woman, head and shoulders, bob haircut. by = bottom of shoulders, s = scale."""
    d.ellipse([cx - 210 * s, by - 170 * s, cx + 210 * s, by + 260 * s], fill=fill, outline=outline, width=width)   # shoulders
    d.rectangle([cx - 48 * s, by - 250 * s, cx + 48 * s, by - 120 * s], fill=fill)                                    # neck
    hx = cx + turn * 30 * s
    d.ellipse([hx - 110 * s, by - 470 * s, hx + 110 * s, by - 210 * s], fill=fill, outline=outline, width=width)    # head
    d.chord([hx - 135 * s, by - 500 * s, hx + 135 * s, by - 250 * s], 170, 370, fill=fill, outline=outline, width=width)  # bob hair
    d.ellipse([hx - 140 * s, by - 420 * s, hx - 60 * s, by - 270 * s], fill=fill)
    d.ellipse([hx + 60 * s, by - 420 * s, hx + 140 * s, by - 270 * s], fill=fill)


def woman_glow(cx, by, s, turn=0.0, width=8) -> Image.Image:
    """Clean glowing outline of a woman() silhouette (no inner lines)."""
    m = Image.new("L", (IW, IH), 0)
    woman(ImageDraw.Draw(m), cx, by, s, 255, turn=turn)
    edge = np.asarray(m.filter(ImageFilter.MaxFilter(width * 2 + 1)), dtype=np.int16) - np.asarray(m, dtype=np.int16)
    e = Image.fromarray(np.clip(edge, 0, 255).astype(np.uint8))
    return Image.merge("RGB", [e.point(lambda v, c=c: v * c // 255) for c in GREEN])


def watch_face(d: ImageDraw.ImageDraw, cx, cy, r, glow_nums=True, painted=12):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=GREEN if glow_nums else CREAM, width=max(4, int(r * 0.05)))
    f = F(ANTON, int(r * 0.26))
    for k in range(1, 13):
        if k > painted:
            continue
        a = math.radians(k * 30 - 90)
        d.text((cx + math.cos(a) * r * 0.76, cy + math.sin(a) * r * 0.76), str(k), font=f, fill=GREEN, anchor="mm")
    d.line([(cx, cy), (cx + r * 0.45 * math.cos(math.radians(-60)), cy + r * 0.45 * math.sin(math.radians(-60)))], fill=GREEN, width=int(r * 0.05))
    d.line([(cx, cy), (cx + r * 0.65 * math.cos(math.radians(40)), cy + r * 0.65 * math.sin(math.radians(40)))], fill=GREEN, width=int(r * 0.035))
    d.ellipse([cx - r * 0.05, cy - r * 0.05, cx + r * 0.05, cy + r * 0.05], fill=GREEN)


def specks(layer: Image.Image, n: int, box, seed: int, color=GREEN, size=(2, 6)):
    d = ImageDraw.Draw(layer)
    r = random.Random(seed)
    for _ in range(n):
        x, y = r.uniform(box[0], box[2]), r.uniform(box[1], box[3])
        s = r.uniform(*size)
        d.ellipse([x - s, y - s, x + s, y + s], fill=tuple(int(c * r.uniform(0.4, 1)) for c in color))


# ------------------------------------------------------------------ scenes

def s_glowing_women():
    base = gradient((6, 10, 14), (2, 4, 6))
    sil = blank("RGBA")
    d = ImageDraw.Draw(sil)
    glow = blank()
    g = ImageDraw.Draw(glow)
    arr = np.zeros((IH, IW, 3), np.float32)
    for cx, by, s, t in ((330, 1260, 1.05, -0.3), (1070, 1260, 1.05, 0.3), (700, 1290, 1.3, 0)):
        woman(d, cx, by, s, (14, 18, 20, 255), turn=t)
        arr = np.maximum(arr, np.asarray(woman_glow(cx, by, s, t, 4), np.float32))
    base = over(base, sil)
    glow = Image.fromarray(arr.astype(np.uint8))
    specks(glow, 260, (60, 200, 1340, 1240), 3)
    return finish(add(base, glow, glow=0.9, radius=14))


def s_factory():
    base = gradient((10, 16, 26), (4, 6, 9))
    sky = blank()
    specks(sky, 160, (0, 0, IW, 560), 9, color=(200, 210, 230), size=(1, 2.5))
    base = add(base, sky)
    b = blank("RGBA")
    d = ImageDraw.Draw(b)
    d.rectangle([160, 520, 1240, 1260], fill=(22, 20, 22, 255))
    d.polygon([(160, 520), (700, 380), (1240, 520)], fill=(26, 22, 24, 255))
    d.rectangle([1050, 180, 1140, 520], fill=(20, 18, 20, 255))
    d.rectangle([200, 260, 270, 560], fill=(20, 18, 20, 255))
    base = over(base, b)
    win = blank()
    w = ImageDraw.Draw(win)
    r = random.Random(4)
    for row in range(3):
        for col in range(7):
            x, y = 220 + col * 145, 600 + row * 190
            lit = r.random() < 0.8
            w.rectangle([x, y, x + 90, y + 130], fill=GREEN if lit else (30, 40, 30))
            w.line([(x + 45, y), (x + 45, y + 130)], fill=(0, 0, 0), width=6)
            w.line([(x, y + 65), (x + 90, y + 65)], fill=(0, 0, 0), width=6)
    base = add(base, win, glow=0.7, radius=24, sharp=0.75)
    smoke = blank()
    specks(smoke, 90, (1000, 40, 1250, 200), 5, color=(70, 80, 90), size=(10, 30))
    return finish(add(base, smoke.filter(ImageFilter.GaussianBlur(12)), sharp=0.6))


def s_undark_ad():
    paper = gradient((232, 220, 190), (210, 194, 160))
    rng = np.random.default_rng(2)
    paper += rng.normal(0, 6, paper.shape[:2])[..., None]
    img = finish(paper)
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, IW - 40, IH - 40], outline=(60, 40, 30), width=8)
    d.rectangle([62, 62, IW - 62, IH - 62], outline=(60, 40, 30), width=3)
    d.text((IW // 2, 210), "UNDARK", font=F(ANTON, 230), fill=(40, 28, 22), anchor="mm")
    d.text((IW // 2, 350), "SHINES IN THE DARK", font=F(ARCH, 56), fill=(130, 40, 30), anchor="mm")
    d.ellipse([IW // 2 - 330, 430, IW // 2 + 330, 1090], fill=(16, 18, 20))
    arr = np.asarray(img, dtype=np.float32)
    dial = blank()
    watch_face(ImageDraw.Draw(dial), IW // 2, 760, 280)
    arr = add(arr, dial, glow=0.8, radius=12)
    img = finish(arr)
    d = ImageDraw.Draw(img)
    d.text((IW // 2, 1160), "Radium paint · glows for years", font=F(ARCH, 40), fill=(40, 28, 22), anchor="mm")
    return img


def s_brush_lips():
    base = gradient((24, 10, 12), (6, 4, 5))
    lips = blank("RGBA")
    d = ImageDraw.Draw(lips)
    cx, cy = 560, 640
    d.chord([cx - 330, cy - 170, cx + 330, cy + 60], 180, 360, fill=(170, 30, 40, 255))
    d.chord([cx - 330, cy - 60, cx + 330, cy + 220], 0, 180, fill=(150, 24, 34, 255))
    d.ellipse([cx - 250, cy - 40, cx + 250, cy + 40], fill=(40, 6, 10, 255))
    base = over(base, lips)
    brush = blank("RGBA")
    b = ImageDraw.Draw(brush)
    b.line([(1350, 120), (cx + 290, cy - 10)], fill=(150, 100, 60, 255), width=34)
    b.line([(cx + 360, cy - 40), (cx + 300, cy - 8)], fill=(200, 200, 200, 255), width=40)
    base = over(base, brush)
    tip = blank()
    t = ImageDraw.Draw(tip)
    t.polygon([(cx + 300, cy - 30), (cx + 300, cy + 14), (cx + 200, cy - 6)], fill=GREEN)
    specks(tip, 60, (cx + 120, cy - 120, cx + 420, cy + 120), 8)
    return finish(add(base, tip, glow=1.0, radius=18))


def s_painting_dial():
    base = gradient((8, 12, 10), (3, 4, 4))
    dial = blank()
    d = ImageDraw.Draw(dial)
    watch_face(d, 700, 640, 470, painted=9)
    base = add(base, dial, glow=0.9, radius=16)
    brush = blank("RGBA")
    b = ImageDraw.Draw(brush)
    b.line([(1320, 1240), (980, 560)], fill=(140, 96, 58, 255), width=30)
    b.line([(990, 580), (960, 520)], fill=(200, 200, 200, 255), width=36)
    base = over(base, brush)
    tip = blank()
    ImageDraw.Draw(tip).polygon([(948, 530), (972, 520), (930, 450)], fill=GREEN)
    hand = blank("RGBA")
    ImageDraw.Draw(hand).ellipse([1120, 900, 1460, 1300], fill=(22, 26, 24, 255))
    base = over(base, hand)
    return finish(add(base, tip, glow=1.2, radius=14))


def s_glowing_smile():
    base = gradient((10, 8, 14), (3, 3, 5))
    face = blank("RGBA")
    d = ImageDraw.Draw(face)
    woman(d, 700, 1500, 2.6, (20, 18, 22, 255))
    base = over(base, face)
    teeth = blank()
    t = ImageDraw.Draw(teeth)
    cx, cy = 700, 700
    t.chord([cx - 170, cy - 100, cx + 170, cy + 110], 0, 180, outline=(190, 40, 60), width=12)
    for k in range(-3, 4):
        x = cx + k * 40
        t.rounded_rectangle([x - 17, cy + 8, x + 17, cy + 62 - abs(k) * 7], 7, fill=GREEN)
    return finish(add(base, teeth, glow=1.1, radius=16))


def s_xray_jaw():
    base = gradient((8, 14, 26), (2, 4, 10))
    x = blank()
    d = ImageDraw.Draw(x)
    bone = (170, 200, 230)
    cx = 700
    d.ellipse([cx - 380, 120, cx + 380, 900], outline=bone, width=22)                    # skull
    d.ellipse([cx - 260, 430, cx - 90, 600], outline=bone, width=18)                     # eyes
    d.ellipse([cx + 90, 430, cx + 260, 600], outline=bone, width=18)
    d.polygon([(cx, 620), (cx - 50, 730), (cx + 50, 730)], outline=bone)
    d.line([(cx, 620), (cx - 50, 730), (cx + 50, 730), (cx, 620)], fill=bone, width=12)
    d.arc([cx - 330, 600, cx + 330, 1160], 10, 170, fill=bone, width=26)                # jaw
    for k in range(-5, 6):
        tx = cx + k * 46
        if k in (-3, 1, 2, 4):
            continue  # missing teeth
        d.rounded_rectangle([tx - 18, 800, tx + 18, 870], 6, outline=bone, width=8)
    for k, pts in enumerate([[(cx - 180, 1010), (cx - 140, 960), (cx - 160, 900), (cx - 120, 860)],
                             [(cx + 150, 1040), (cx + 190, 980), (cx + 160, 930)],
                             [(cx - 20, 1100), (cx + 20, 1050), (cx - 10, 990)]]):
        d.line(pts, fill=(255, 90, 90), width=9)
    base = add(base, x.filter(ImageFilter.GaussianBlur(2)), glow=0.5, radius=10)
    rot = blank()
    ImageDraw.Draw(rot).ellipse([cx - 230, 920, cx + 30, 1120], fill=(80, 140, 60))
    base = add(base, rot.filter(ImageFilter.GaussianBlur(30)), sharp=0.8)
    rng = np.random.default_rng(5)
    return finish(base + rng.normal(0, 7, base.shape[:2])[..., None])


def s_court():
    base = gradient((30, 22, 16), (8, 6, 5))
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    for x in range(100, IW, 230):  # wood panels
        d.rectangle([x, 0, x + 200, 760], outline=(60, 44, 30, 255), width=6)
    d.rectangle([0, 760, IW, IH], fill=(40, 28, 20, 255))
    # scales of justice
    cx = 700
    gold = (220, 180, 90, 255)
    d.rectangle([cx - 12, 170, cx + 12, 640], fill=gold)
    d.rectangle([cx - 140, 630, cx + 140, 660], fill=gold)
    d.line([(cx - 330, 260), (cx + 330, 220)], fill=gold, width=16)
    for sx, sy in ((cx - 320, 262), (cx + 320, 222)):
        d.line([(sx, sy), (sx - 90, sy + 210)], fill=gold, width=5)
        d.line([(sx, sy), (sx + 90, sy + 210)], fill=gold, width=5)
        d.chord([sx - 120, sy + 150, sx + 120, sy + 280], 0, 180, fill=gold)
    # gavel
    d.rounded_rectangle([860, 880, 1140, 960], 18, fill=(90, 54, 30, 255))
    d.line([(1000, 960), (1200, 1150)], fill=(110, 70, 40, 255), width=30)
    d.ellipse([820, 1110, 1160, 1170], fill=(70, 44, 26, 255))
    base = over(base, l)
    lamp = blank()
    ImageDraw.Draw(lamp).ellipse([cx - 500, -200, cx + 500, 500], fill=(90, 70, 40))
    base = add(base, lamp.filter(ImageFilter.GaussianBlur(120)), sharp=0.6)
    year = blank()
    ImageDraw.Draw(year).text((260, 1040), "1928", font=F(ANTON, 140), fill=(120, 90, 50))
    return finish(add(base, year, sharp=0.7))


def s_deathbed():
    base = gradient((14, 18, 26), (5, 6, 9))
    win = blank()
    w = ImageDraw.Draw(win)
    w.rectangle([900, 120, 1240, 560], fill=(120, 140, 170))
    base = add(base, win, glow=0.5, radius=50, sharp=0.5)
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    d.line([(1070, 120), (1070, 560)], fill=(10, 12, 16, 255), width=14)
    d.line([(900, 340), (1240, 340)], fill=(10, 12, 16, 255), width=14)
    d.rectangle([120, 760, 1060, 900], fill=(200, 196, 186, 255))          # bed
    d.rectangle([100, 560, 150, 1100], fill=(40, 34, 30, 255))              # headboard
    d.rectangle([120, 900, 1060, 960], fill=(60, 50, 44, 255))
    d.ellipse([170, 660, 330, 790], fill=(225, 220, 210, 255))              # pillow
    d.ellipse([200, 640, 320, 760], fill=(18, 18, 22, 255))                 # head
    d.chord([300, 700, 1040, 830], 180, 360, fill=(170, 166, 156, 255))     # blanket
    for x, s in ((1180, 0.85), (1330, 0.8)):                                # people standing
        woman(d, x, 1260, s, (12, 14, 18, 255))
    base = over(base, l)
    glow = blank()
    ImageDraw.Draw(glow).ellipse([215, 680, 305, 730], fill=(40, 80, 34))
    return finish(add(base, glow, glow=0.6, radius=20))


def trefoil(d: ImageDraw.ImageDraw, cx, cy, r, color, bg):
    for k in range(3):
        a = -90 + k * 120
        d.pieslice([cx - r, cy - r, cx + r, cy + r], a - 30, a + 30, fill=color)
    d.ellipse([cx - r * 0.3, cy - r * 0.3, cx + r * 0.3, cy + r * 0.3], fill=bg)
    d.ellipse([cx - r * 0.18, cy - r * 0.18, cx + r * 0.18, cy + r * 0.18], fill=color)


def s_safety():
    base = gradient((24, 22, 10), (8, 8, 4))
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    d.polygon([(700, 110), (1220, 1010), (180, 1010)], fill=(240, 200, 40, 255))
    d.polygon([(700, 190), (1140, 965), (260, 965)], outline=(16, 16, 16, 255))
    d.line([(700, 190), (1140, 965), (260, 965), (700, 190)], fill=(16, 16, 16, 255), width=26)
    trefoil(d, 700, 700, 210, (16, 16, 16, 255), (240, 200, 40, 255))
    d.text((700, 1120), "WORKER SAFETY", font=F(ANTON, 120), fill=(240, 200, 40, 255), anchor="mm")
    return finish(over(base, l))


def s_final():
    base = gradient((6, 10, 10), (2, 3, 3))
    l = blank()
    d = ImageDraw.Draw(l)
    watch_face(d, 700, 400, 290)
    base = add(base, l, glow=0.9, radius=16)
    sil = blank("RGBA")
    woman(ImageDraw.Draw(sil), 700, 1560, 1.5, (8, 10, 10, 255))
    base = over(base, sil)
    return finish(add(base, woman_glow(700, 1560, 1.5, width=4), glow=0.6, radius=10))


STORIES = {
    "radium_girls": {1: s_glowing_women, 2: s_factory, 3: s_undark_ad, 4: s_brush_lips, 5: s_painting_dial, 6: s_glowing_smile,
                     7: s_xray_jaw, 9: s_court, 10: s_deathbed, 11: s_safety, 13: s_final},
}


if __name__ == "__main__":
    name, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for n, fn in STORIES[name].items():
        fn().save(out / f"scene_{n:02d}.png")
        print("drew scene", n)
