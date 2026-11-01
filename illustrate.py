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
        k = r.uniform(0.4, 1)
        d.ellipse([x - s, y - s, x + s, y + s], fill=tuple(int(c * k) for c in color))


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

# ------------------------------------------------------------------ Paper Trail: the man who sold the Eiffel Tower

GOLD = (243, 196, 72)
NIGHT = ((12, 16, 30), (4, 5, 9))


def tower(d: ImageDraw.ImageDraw, cx, base_y, h, color, width=6):
    """Eiffel Tower line drawing: curved legs, 2 platforms, lattice, spire."""
    top = base_y - h
    def half(sign):
        pts = []
        for k in range(41):
            t = k / 40
            y = base_y - t * h * 0.86
            x = cx + sign * (h * 0.36 * (1 - t) ** 2.2 + h * 0.018)
            pts.append((x, y))
        return pts
    L, R = half(-1), half(1)
    d.line(L, fill=color, width=width)
    d.line(R, fill=color, width=width)
    # arch between the legs
    d.arc([cx - h * 0.2, base_y - h * 0.2, cx + h * 0.2, base_y + h * 0.1], 180, 360, fill=color, width=width)
    for frac, wscale in ((0.2, 1.15), (0.5, 1.1)):
        i = int(frac * 40)
        (x1, y), (x2, _) = L[i], R[i]
        d.rectangle([x1 - h * 0.03 * wscale, y - h * 0.025, x2 + h * 0.03 * wscale, y], outline=color, width=width)
    for k in range(2, 39, 2):  # lattice
        d.line([L[k], R[k + 2]], fill=color, width=max(1, width // 3))
        d.line([R[k], L[k + 2]], fill=color, width=max(1, width // 3))
    d.line([(cx, base_y - h * 0.86), (cx, top)], fill=color, width=width)
    d.rectangle([cx - h * 0.02, base_y - h * 0.9, cx + h * 0.02, base_y - h * 0.86], fill=color)


def man(d: ImageDraw.ImageDraw, cx, by, s, fill, hat=True):
    """1920s man, head and shoulders, fedora."""
    d.ellipse([cx - 230 * s, by - 160 * s, cx + 230 * s, by + 260 * s], fill=fill)
    d.polygon([(cx - 60 * s, by - 150 * s), (cx, by - 20 * s), (cx + 60 * s, by - 150 * s)], fill=fill)
    d.rectangle([cx - 50 * s, by - 250 * s, cx + 50 * s, by - 120 * s], fill=fill)
    d.ellipse([cx - 105 * s, by - 450 * s, cx + 105 * s, by - 200 * s], fill=fill)
    if hat:
        d.ellipse([cx - 190 * s, by - 420 * s, cx + 190 * s, by - 370 * s], fill=fill)
        d.rounded_rectangle([cx - 115 * s, by - 540 * s, cx + 115 * s, by - 395 * s], int(30 * s), fill=fill)


def outline_of(draw_fn, color, width=4) -> Image.Image:
    m = Image.new("L", (IW, IH), 0)
    draw_fn(ImageDraw.Draw(m))
    edge = np.asarray(m.filter(ImageFilter.MaxFilter(width * 2 + 1)), dtype=np.int16) - np.asarray(m, dtype=np.int16)
    e = Image.fromarray(np.clip(edge, 0, 255).astype(np.uint8))
    return Image.merge("RGB", [e.point(lambda v, c=c: v * c // 255) for c in color])


def city(layer_draw, y, seed=1, fill=(10, 12, 18, 255)):
    r = random.Random(seed)
    x = 0
    while x < IW:
        w = r.randint(60, 150)
        h = r.randint(60, 200)
        layer_draw.rectangle([x, y - h, x + w, IH], fill=fill)
        if r.random() < 0.5:
            layer_draw.polygon([(x, y - h), (x + w / 2, y - h - 40), (x + w, y - h)], fill=fill)
        x += w


def s_tower_night():
    base = gradient(*NIGHT)
    sky = blank()
    specks(sky, 150, (0, 0, IW, 700), 4, color=(210, 215, 235), size=(1, 2.4))
    base = add(base, sky)
    moon = blank()
    ImageDraw.Draw(moon).ellipse([1060, 120, 1220, 280], fill=(230, 226, 210))
    base = add(base, moon, glow=0.4, radius=40)
    t = blank()
    tower(ImageDraw.Draw(t), 700, 1130, 1040, GOLD, 7)
    base = add(base, t, glow=0.7, radius=14)
    c = blank("RGBA")
    city(ImageDraw.Draw(c), 1150, 2)
    return finish(over(base, c))


def s_con_man():
    base = gradient((30, 20, 14), (6, 5, 4))
    lamp = blank()
    ImageDraw.Draw(lamp).ellipse([300, -300, 1100, 500], fill=(120, 90, 40))
    base = add(base, lamp.filter(ImageFilter.GaussianBlur(120)), sharp=0.7)
    sil = blank("RGBA")
    man(ImageDraw.Draw(sil), 700, 1180, 1.6, (10, 9, 8, 255))
    base = over(base, sil)
    rim = outline_of(lambda d: man(d, 700, 1180, 1.6, 255), GOLD, 3)
    smoke = blank()
    specks(smoke, 40, (880, 200, 1200, 600), 6, color=(90, 90, 90), size=(12, 34))
    base = add(base, smoke.filter(ImageFilter.GaussianBlur(18)), sharp=0.5)
    return finish(add(base, rim, glow=0.5, radius=10))


def s_rust_tower():
    paper = gradient((226, 214, 186), (200, 184, 150))
    paper += np.random.default_rng(3).normal(0, 6, paper.shape[:2])[..., None]
    img = finish(paper)
    d = ImageDraw.Draw(img)
    d.text((IW // 2, 120), "PARIS · 1925", font=F(ARCH, 64), fill=(40, 30, 24), anchor="mm")
    d.line([(100, 180), (IW - 100, 180)], fill=(40, 30, 24), width=5)
    tower(d, 520, 1180, 930, (70, 50, 36), 6)
    for k, (x, y) in enumerate([(430, 900), (600, 760), (500, 520), (640, 1040), (380, 1080)]):
        d.ellipse([x - 40, y - 26, x + 40, y + 26], fill=(150, 70, 30))
    d.text((1000, 420), "RUSTING", font=F(ANTON, 120), fill=(150, 40, 30), anchor="mm")
    d.text((1000, 560), "COSTLY TO", font=F(ANTON, 90), fill=(40, 30, 24), anchor="mm")
    d.text((1000, 660), "REPAINT", font=F(ANTON, 90), fill=(40, 30, 24), anchor="mm")
    d.text((1000, 800), "?", font=F(ANTON, 200), fill=(150, 40, 30), anchor="mm")
    return img


def s_letter():
    base = gradient((24, 18, 14), (8, 6, 5))
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    d.polygon([(260, 150), (1150, 120), (1180, 1180), (230, 1200)], fill=(236, 226, 200, 255))
    d.text((705, 250), "MINISTRY OF POSTS", font=F(ARCH, 52), fill=(30, 26, 22, 255), anchor="mm")
    d.text((705, 320), "AND TELEGRAPHS", font=F(ARCH, 40), fill=(30, 26, 22, 255), anchor="mm")
    for k in range(9):
        y = 450 + k * 62
        d.line([(330, y), (1080 - (k % 3) * 90, y)], fill=(90, 84, 78, 255), width=8)
    d.text((705, 1040), "CONFIDENTIAL", font=F(ANTON, 90), fill=(160, 30, 30, 255), anchor="mm")
    base = over(base, l)
    seal = blank("RGBA")
    s = ImageDraw.Draw(seal)
    s.ellipse([920, 860, 1120, 1060], fill=(150, 20, 24, 255))
    s.ellipse([960, 900, 1080, 1020], outline=(200, 60, 60, 255), width=8)
    base = over(base, seal)
    return finish(base)


def s_meeting():
    base = gradient((34, 24, 16), (8, 6, 5))
    chand = blank()
    c = ImageDraw.Draw(chand)
    for k in range(-3, 4):
        c.ellipse([700 + k * 70 - 14, 210 - 14, 700 + k * 70 + 14, 210 + 14], fill=GOLD)
    c.arc([470, 120, 930, 300], 0, 180, fill=GOLD, width=6)
    base = add(base, chand, glow=0.9, radius=26)
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    for k, x in enumerate((230, 470, 930, 1170)):
        man(d, x, 1000, 0.75, (12, 10, 9, 255))
    man(d, 700, 900, 0.95, (6, 5, 5, 255))
    d.rectangle([0, 980, IW, IH], fill=(60, 38, 24, 255))
    d.rectangle([0, 980, IW, 1000], fill=(90, 60, 36, 255))
    d.rectangle([560, 1020, 840, 1100], fill=(236, 226, 200, 255))
    base = over(base, l)
    return finish(base)


def s_dealer():
    base = gradient((20, 24, 30), (6, 7, 9))
    sil = blank("RGBA")
    man(ImageDraw.Draw(sil), 520, 1260, 1.35, (12, 13, 15, 255))
    base = over(base, sil)
    base = add(base, outline_of(lambda d: man(d, 520, 1260, 1.35, 255), (200, 200, 210), 3), glow=0.3, radius=8)
    wife = blank("RGBA")
    woman(ImageDraw.Draw(wife), 1110, 1260, 1.0, (24, 20, 22, 255), turn=-0.6)
    base = over(base, wife)
    base = add(base, woman_glow(1110, 1260, 1.0, turn=-0.6, width=3).point(lambda v: v), sharp=0.0)
    q = blank()
    ImageDraw.Draw(q).text((1160, 520), "?", font=F(ANTON, 260), fill=(200, 60, 60), anchor="mm")
    return finish(add(base, q, glow=0.5, radius=14))


def s_bribe():
    base = gradient((16, 12, 10), (4, 3, 3))
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    d.rectangle([0, 0, IW, 520], fill=(58, 36, 22, 255))       # table top seen from below
    d.rectangle([0, 500, IW, 540], fill=(30, 20, 12, 255))
    d.rounded_rectangle([60, 740, 640, 880], 60, fill=(28, 26, 30, 255))     # sleeve left
    d.ellipse([560, 720, 760, 900], fill=(200, 160, 130, 255))                # hand
    d.rounded_rectangle([1340 - 580, 760, 1400, 900], 60, fill=(20, 20, 24, 255))
    d.ellipse([660, 740, 860, 910], fill=(190, 150, 120, 255))
    d.polygon([(600, 760), (900, 720), (930, 860), (630, 900)], fill=(236, 226, 200, 255))  # envelope
    d.line([(600, 760), (765, 835), (900, 720)], fill=(170, 160, 140, 255), width=6)
    base = over(base, l)
    glow = blank()
    ImageDraw.Draw(glow).ellipse([520, 640, 1000, 980], fill=(110, 80, 30))
    return finish(add(base, glow.filter(ImageFilter.GaussianBlur(90)), sharp=0.8))


def s_cash():
    base = gradient((20, 16, 12), (5, 4, 3))
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    d.rounded_rectangle([170, 520, 1230, 1180], 40, fill=(70, 44, 26, 255))
    d.rounded_rectangle([200, 550, 1200, 1150], 30, fill=(40, 26, 16, 255))
    d.polygon([(170, 520), (1230, 520), (1150, 160), (250, 160)], fill=(84, 54, 32, 255))  # open lid
    d.rounded_rectangle([600, 120, 800, 170], 20, outline=(30, 20, 12, 255), width=16)
    r = random.Random(5)
    for row in range(4):
        for col in range(5):
            x, y = 240 + col * 190, 600 + row * 130 + r.randint(-6, 6)
            d.rounded_rectangle([x, y, x + 170, y + 110], 8, fill=(196, 170, 110, 255), outline=(120, 96, 50, 255), width=4)
            d.rectangle([x, y + 44, x + 170, y + 66], fill=(150, 40, 40, 255))
            d.text((x + 85, y + 26), "1000 F", font=F(ARCH, 22), fill=(80, 60, 30, 255), anchor="mm")
    base = over(base, l)
    glow = blank()
    ImageDraw.Draw(glow).ellipse([300, 500, 1100, 1200], fill=(120, 96, 40))
    return finish(add(base, glow.filter(ImageFilter.GaussianBlur(120)), sharp=0.6))


def s_train():
    base = gradient((40, 30, 44), (10, 8, 14))
    sun = blank()
    ImageDraw.Draw(sun).ellipse([540, 420, 860, 740], fill=(200, 110, 70))
    base = add(base, sun, glow=0.6, radius=60)
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    d.rectangle([0, 900, IW, IH], fill=(14, 12, 16, 255))
    d.rectangle([0, 880, IW, 900], fill=(30, 26, 30, 255))
    y = 880
    d.rectangle([700, y - 260, 1400, y - 40], fill=(16, 14, 18, 255))      # carriages
    d.rectangle([180, y - 220, 640, y - 40], fill=(16, 14, 18, 255))       # engine
    d.rectangle([520, y - 330, 640, y - 220], fill=(16, 14, 18, 255))      # cab
    d.rectangle([250, y - 320, 310, y - 220], fill=(16, 14, 18, 255))      # chimney
    d.polygon([(140, y - 40), (180, y - 140), (180, y - 40)], fill=(16, 14, 18, 255))
    for x in (250, 400, 560, 780, 960, 1140, 1320):
        d.ellipse([x - 50, y - 90, x + 50, y + 10], fill=(10, 9, 12, 255))
    base = over(base, l)
    win = blank()
    w = ImageDraw.Draw(win)
    for x in range(740, 1400, 110):
        w.rectangle([x, y - 220, x + 70, y - 160], fill=GOLD)
    base = add(base, win, glow=0.5, radius=14)
    smoke = blank()
    specks(smoke, 50, (0, 120, 400, 560), 3, color=(120, 110, 120), size=(25, 70))
    base = add(base, smoke.filter(ImageFilter.GaussianBlur(26)), sharp=0.6)
    sign = blank()
    ImageDraw.Draw(sign).text((1060, 200), "VIENNA →", font=F(ANTON, 110), fill=GOLD, anchor="mm")
    return finish(add(base, sign, glow=0.4, radius=10))


def s_head_in_hands():
    base = gradient((18, 22, 30), (5, 6, 8))
    rain = blank()
    r = random.Random(11)
    rd = ImageDraw.Draw(rain)
    for _ in range(220):
        x, y = r.uniform(0, IW), r.uniform(0, IH)
        rd.line([(x, y), (x - 14, y + 60)], fill=(70, 80, 100), width=2)
    base = add(base, rain, sharp=0.8)
    sil = blank("RGBA")
    man(ImageDraw.Draw(sil), 700, 1300, 1.7, (10, 11, 14, 255))
    base = over(base, sil)
    base = add(base, outline_of(lambda d: man(d, 700, 1300, 1.7, 255), (150, 170, 210), 3), glow=0.4, radius=10)
    paper = blank("RGBA")
    pd = ImageDraw.Draw(paper)
    pd.polygon([(980, 1080), (1320, 1040), (1350, 1220), (1000, 1240)], fill=(220, 210, 186, 255))
    pd.text((1165, 1140), "SOLD", font=F(ANTON, 80), fill=(150, 30, 30, 255), anchor="mm")
    t = blank()
    ImageDraw.Draw(t).text((700, 170), "TOO ASHAMED TO TELL", font=F(ANTON, 90), fill=(200, 205, 215), anchor="mm")
    return finish(add(over(base, paper), t, sharp=0.9))


def s_escape():
    base = gradient((8, 10, 16), (2, 3, 5))
    beam = blank()
    ImageDraw.Draw(beam).polygon([(1400, 0), (1100, 0), (300, 1260), (1000, 1260)], fill=(80, 84, 90))
    base = add(base, beam.filter(ImageFilter.GaussianBlur(30)), sharp=0.8)
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    city(d, 1260, 7, fill=(6, 7, 10, 255))
    f = (5, 5, 7, 255)  # running man with hat and coat
    cx, cy = 640, 760
    d.ellipse([cx - 60, cy - 250, cx + 60, cy - 130], fill=f)
    d.ellipse([cx - 100, cy - 225, cx + 100, cy - 195], fill=f)
    d.rounded_rectangle([cx - 60, cy - 300, cx + 60, cy - 205], 14, fill=f)
    d.polygon([(cx - 70, cy - 130), (cx + 80, cy - 140), (cx + 130, cy + 160), (cx - 150, cy + 170)], fill=f)
    d.line([(cx - 20, cy + 150), (cx - 210, cy + 380)], fill=f, width=50)
    d.line([(cx + 60, cy + 150), (cx + 230, cy + 300), (cx + 200, cy + 420)], fill=f, width=50)
    d.line([(cx + 50, cy - 90), (cx + 230, cy + 20)], fill=f, width=42)
    d.line([(cx - 40, cy - 90), (cx - 220, cy - 10)], fill=f, width=42)
    base = over(base, l)
    whistle = blank()
    ImageDraw.Draw(whistle).text((1100, 260), "POLICE!", font=F(ANTON, 120), fill=(220, 60, 60), anchor="mm")
    return finish(add(base, whistle, glow=0.5, radius=12))


def s_alcatraz():
    base = gradient((14, 20, 34), (4, 6, 10))
    beam = blank()
    ImageDraw.Draw(beam).polygon([(960, 470), (980, 470), (1400, 60), (1400, 260)], fill=(150, 150, 130))
    base = add(base, beam.filter(ImageFilter.GaussianBlur(16)), sharp=0.6)
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    d.polygon([(0, 900), (200, 760), (500, 720), (900, 690), (1200, 760), (1400, 820), (1400, 1000), (0, 1000)], fill=(14, 16, 20, 255))
    d.rectangle([380, 560, 1020, 740], fill=(20, 22, 28, 255))
    d.rectangle([940, 440, 1000, 740], fill=(20, 22, 28, 255))
    d.rectangle([0, 1000, IW, IH], fill=(8, 14, 24, 255))
    base = over(base, l)
    win = blank()
    w = ImageDraw.Draw(win)
    for row in range(3):
        for col in range(14):
            w.rectangle([400 + col * 44, 590 + row * 46, 420 + col * 44, 616 + row * 46], fill=(220, 190, 110) if (row + col) % 3 else (40, 40, 40))
    base = add(base, win, glow=0.4, radius=8, sharp=0.8)
    ref = blank()
    for k in range(40):
        y = 1020 + k * 6
        ImageDraw.Draw(ref).line([(400 + (k * 37) % 200, y), (1000 - (k * 23) % 200, y)], fill=(60, 54, 34), width=2)
    base = add(base, ref, sharp=0.7)
    t = blank()
    ImageDraw.Draw(t).text((700, 220), "ALCATRAZ", font=F(ANTON, 130), fill=(200, 200, 210), anchor="mm")
    return finish(add(base, t, sharp=0.9))


def s_tower_end():
    base = gradient((18, 10, 10), (4, 3, 3))
    t = blank()
    tower(ImageDraw.Draw(t), 700, 1200, 1100, GOLD, 7)
    base = add(base, t, glow=0.6, radius=14)
    tag = blank("RGBA")
    d = ImageDraw.Draw(tag)
    d.rounded_rectangle([880, 760, 1260, 900], 16, fill=(236, 226, 200, 255))
    d.text((1070, 830), "SOLD", font=F(ANTON, 100), fill=(170, 30, 30, 255), anchor="mm")
    d.line([(880, 830), (760, 760)], fill=(236, 226, 200, 255), width=5)
    tag = tag.rotate(8, center=(1070, 830))
    return finish(over(base, tag))


# ------------------------------------------------------------------ Paper Trail: Poyais, the country that never existed

PARCH = ((232, 216, 178), (198, 176, 132))
BROWN = (70, 48, 30)


def parchment(seed=1):
    p = gradient(*PARCH)
    p += np.random.default_rng(seed).normal(0, 7, p.shape[:2])[..., None]
    yy, xx = np.mgrid[0:IH, 0:IW]
    r = np.sqrt(((xx - IW / 2) / (IW * 0.7)) ** 2 + ((yy - IH / 2) / (IH * 0.7)) ** 2)
    return p * np.clip(1.15 - r * 0.45, 0.55, 1)[..., None]


def coastline(d, pts, fill=None, outline=BROWN, width=6):
    if fill:
        d.polygon(pts, fill=fill)
    d.line(pts + [pts[0]], fill=outline, width=width, joint="curve")


def blob(cx, cy, rx, ry, seed, n=40, rough=0.18):
    r = random.Random(seed)
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        f = 1 + r.uniform(-rough, rough)
        pts.append((cx + math.cos(a) * rx * f, cy + math.sin(a) * ry * f))
    return pts


def s_map(stamp=True):
    def fn():
        img = finish(parchment(2))
        d = ImageDraw.Draw(img)
        coastline(d, blob(520, 640, 420, 330, 4), fill=(206, 186, 140))
        for k in range(6):  # sea lines
            y = 180 + k * 190
            d.arc([960, y, 1360, y + 80], 200, 340, fill=(120, 100, 70), width=4)
        d.text((520, 640), "POYAIS", font=F(ANTON, 150), fill=BROWN, anchor="mm")
        d.text((520, 760), "St. Joseph (capital)", font=F(ARCH, 34), fill=BROWN, anchor="mm")
        d.ellipse([500, 790, 540, 830], fill=(150, 30, 30))
        d.text((1150, 1120), "N", font=F(ANTON, 80), fill=BROWN, anchor="mm")
        d.polygon([(1150, 960), (1120, 1070), (1180, 1070)], fill=BROWN)
        if stamp:
            st = Image.new("RGBA", (760, 220), (0, 0, 0, 0))
            sd = ImageDraw.Draw(st)
            sd.rounded_rectangle([8, 8, 752, 212], 20, outline=(170, 20, 24, 255), width=14)
            sd.text((380, 112), "DOES NOT EXIST", font=F(ANTON, 120), fill=(170, 20, 24, 255), anchor="mm")
            st = st.rotate(-12, expand=True)
            img.paste(st, (440, 820), st)
        return img
    return fn


def s_general():
    base = gradient((40, 20, 18), (8, 5, 5))
    sil = blank("RGBA")
    d = ImageDraw.Draw(sil)
    man(d, 700, 1200, 1.6, (16, 18, 34, 255), hat=False)
    d.chord([700 - 240, 1200 - 820, 700 + 240, 1200 - 560], 180, 360, fill=(16, 18, 34, 255))  # bicorne
    d.polygon([(700 - 260, 1200 - 690), (700 + 260, 1200 - 690), (700, 1200 - 630)], fill=(16, 18, 34, 255))
    base = over(base, sil)
    g = blank()
    gd = ImageDraw.Draw(g)
    for sx in (-1, 1):  # epaulettes
        x = 700 + sx * 250
        gd.ellipse([x - 90, 1000, x + 90, 1060], fill=GOLD)
        for k in range(7):
            gd.line([(x - 80 + k * 26, 1050), (x - 80 + k * 26, 1110)], fill=GOLD, width=6)
    for k in range(3):
        gd.ellipse([600 + k * 70, 1150, 650 + k * 70, 1200], fill=GOLD)
    for k in range(4):
        gd.ellipse([690, 1080 + k * 50, 710, 1100 + k * 50], fill=GOLD)
    base = add(base, g, glow=0.5, radius=10)
    return finish(add(base, outline_of(lambda dd: man(dd, 700, 1200, 1.6, 255, hat=False), GOLD, 3), glow=0.3, radius=8))


def s_crown():
    base = gradient((44, 16, 22), (10, 4, 6))
    g = blank()
    d = ImageDraw.Draw(g)
    cx, cy = 700, 560
    d.polygon([(cx - 300, cy + 160), (cx - 330, cy - 120), (cx - 170, cy + 20), (cx, cy - 200), (cx + 170, cy + 20),
               (cx + 330, cy - 120), (cx + 300, cy + 160)], fill=GOLD)
    d.rectangle([cx - 300, cy + 160, cx + 300, cy + 230], fill=(220, 170, 60))
    for x, col in ((cx - 180, (200, 40, 50)), (cx, (60, 120, 220)), (cx + 180, (40, 160, 90))):
        d.ellipse([x - 32, cy + 168, x + 32, cy + 222], fill=col)
    for x, y in ((cx - 330, cy - 120), (cx, cy - 200), (cx + 330, cy - 120)):
        d.ellipse([x - 26, y - 26, x + 26, y + 26], fill=(255, 240, 200))
    base = add(base, g, glow=0.5, radius=24)
    t = blank()
    td = ImageDraw.Draw(t)
    td.text((700, 940), "THE RULER OF", font=F(ARCH, 64), fill=(230, 220, 200), anchor="mm")
    td.text((700, 1070), "POYAIS", font=F(ANTON, 170), fill=GOLD, anchor="mm")
    return finish(add(base, t, glow=0.3, radius=10))


def s_guidebook():
    base = gradient((30, 22, 16), (8, 6, 4))
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    d.polygon([(120, 260), (700, 300), (700, 1120), (100, 1080)], fill=(236, 222, 190, 255))
    d.polygon([(700, 300), (1280, 260), (1300, 1080), (700, 1120)], fill=(228, 212, 178, 255))
    d.line([(700, 300), (700, 1120)], fill=(150, 120, 90, 255), width=6)
    ink = (60, 44, 30, 255)
    d.text((400, 360), "A SKETCH OF", font=F(ARCH, 34), fill=ink, anchor="mm")
    d.text((400, 420), "POYAIS", font=F(ANTON, 90), fill=ink, anchor="mm")
    for k in range(8):
        y = 520 + k * 55
        d.line([(180, y), (640 - (k % 3) * 60, y)], fill=(130, 110, 90, 255), width=6)
    # the dream city on the right page
    d.rectangle([780, 760, 1220, 900], outline=ink, width=5)
    d.chord([900, 560, 1100, 800], 180, 360, outline=ink, width=5)        # cathedral dome
    d.line([(1000, 560), (1000, 500)], fill=ink, width=5)
    d.line([(980, 520), (1020, 520)], fill=ink, width=5)
    for x in range(800, 1210, 60):
        d.rectangle([x, 800, x + 30, 860], outline=ink, width=3)
    d.text((1000, 960), "CATHEDRAL · OPERA · BANK", font=F(ARCH, 30), fill=ink, anchor="mm")
    base = over(base, l)
    gold = blank()
    specks(gold, 40, (800, 990, 1220, 1060), 4, color=GOLD, size=(5, 12))
    return finish(add(base, gold, glow=0.6, radius=8))


def s_bond():
    img = finish(parchment(5))
    d = ImageDraw.Draw(img)
    d.rectangle([70, 70, IW - 70, IH - 70], outline=BROWN, width=10)
    d.rectangle([100, 100, IW - 100, IH - 100], outline=BROWN, width=3)
    d.text((IW // 2, 250), "POYAIS LOAN", font=F(ANTON, 150), fill=BROWN, anchor="mm")
    d.text((IW // 2, 380), "LONDON · 1822", font=F(ARCH, 50), fill=BROWN, anchor="mm")
    d.text((IW // 2, 640), "£200,000", font=F(ANTON, 260), fill=(150, 30, 30), anchor="mm")
    for k in range(4):
        y = 860 + k * 55
        d.line([(260, y), (IW - 260, y)], fill=(140, 115, 85), width=5)
    d.ellipse([IW - 330, 940, IW - 150, 1120], outline=(150, 30, 30), width=10)
    d.text((IW - 240, 1030), "SEAL", font=F(ARCH, 34), fill=(150, 30, 30), anchor="mm")
    return img


def s_banknote():
    base = gradient((20, 26, 22), (6, 8, 7))
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    for k, (dx, dy, rot) in enumerate(((-60, 80, -8), (40, -40, 5), (0, 0, 0))):
        note = Image.new("RGBA", (1100, 560), (0, 0, 0, 0))
        n = ImageDraw.Draw(note)
        n.rounded_rectangle([0, 0, 1099, 559], 20, fill=(206, 214, 184, 255), outline=(50, 80, 60, 255), width=10)
        n.rounded_rectangle([30, 30, 1069, 529], 14, outline=(50, 80, 60, 255), width=4)
        n.text((550, 120), "BANK OF POYAIS", font=F(ANTON, 90), fill=(40, 70, 50, 255), anchor="mm")
        n.ellipse([90, 200, 330, 440], outline=(40, 70, 50, 255), width=8)
        n.text((210, 320), "1", font=F(ANTON, 160), fill=(40, 70, 50, 255), anchor="mm")
        n.text((700, 300), "ONE DOLLAR", font=F(ANTON, 110), fill=(40, 70, 50, 255), anchor="mm")
        n.text((700, 430), "Payable to the bearer", font=F(ARCH, 36), fill=(60, 90, 70, 255), anchor="mm")
        note = note.rotate(rot, expand=True)
        l.paste(note, (150 + dx, 350 + dy), note)
    base = over(base, l)
    return finish(base)


def s_ship():
    base = gradient((70, 60, 90), (240, 150, 90), h=IH)
    sun = blank()
    ImageDraw.Draw(sun).ellipse([840, 520, 1100, 780], fill=(255, 220, 160))
    base = add(base, sun, glow=0.5, radius=50)
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    d.rectangle([0, 760, IW, IH], fill=(30, 40, 70, 255))
    for k in range(30):
        y = 790 + k * 16
        d.line([(random.Random(k).randint(0, 600), y), (random.Random(k + 50).randint(700, IW), y)], fill=(60, 70, 100, 255), width=3)
    f = (14, 12, 18, 255)
    d.polygon([(260, 760), (900, 760), (840, 860), (320, 860)], fill=f)         # hull
    for x, h in ((420, 520), (600, 600), (760, 480)):
        d.rectangle([x - 8, 760 - h, x + 8, 760], fill=f)
        d.polygon([(x - 120, 760 - h + 60), (x + 120, 760 - h + 60), (x + 100, 760 - h + 260), (x - 100, 760 - h + 260)], fill=f)
        d.polygon([(x - 140, 760 - h + 290), (x + 140, 760 - h + 290), (x + 120, 760 - h * 0.25), (x - 120, 760 - h * 0.25)], fill=f)
    d.line([(260, 760), (120, 600)], fill=f, width=8)
    base = over(base, l)
    return finish(base)


def s_jungle():
    base = gradient((40, 60, 50), (10, 16, 12))
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    d.rectangle([0, 980, IW, IH], fill=(170, 150, 110, 255))      # beach
    d.rectangle([0, 900, IW, 990], fill=(50, 80, 100, 255))       # sea
    r = random.Random(3)
    for x in range(-50, IW + 100, 120):   # dense jungle
        h = r.randint(300, 520)
        d.ellipse([x - 140, 900 - h, x + 140, 900 - h + 420], fill=(16 + r.randint(0, 20), 50 + r.randint(0, 30), 24, 255))
    def palm(x, y, s):
        d.line([(x, y), (x + 30 * s, y - 380 * s)], fill=(40, 30, 20, 255), width=int(24 * s))
        for a in range(0, 360, 45):
            ax = x + 30 * s + math.cos(math.radians(a)) * 220 * s
            ay = y - 380 * s + math.sin(math.radians(a)) * 90 * s + 40 * s
            d.line([(x + 30 * s, y - 380 * s), (ax, ay)], fill=(14, 40, 18, 255), width=int(26 * s))
    palm(200, 1150, 1.3)
    palm(1180, 1180, 1.5)
    base = over(base, l)
    t = blank()
    ImageDraw.Draw(t).text((700, 230), "NO CITY.", font=F(ANTON, 170), fill=(240, 236, 220), anchor="mm")
    return finish(add(base, t, sharp=0.95))


def s_graves():
    base = gradient((16, 20, 30), (4, 5, 8))
    moon = blank()
    ImageDraw.Draw(moon).ellipse([980, 140, 1160, 320], fill=(220, 220, 210))
    base = add(base, moon, glow=0.4, radius=40)
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    d.polygon([(0, 900), (500, 840), (900, 860), (IW, 820), (IW, IH), (0, IH)], fill=(14, 16, 18, 255))
    r = random.Random(8)
    for k in range(14):
        x = 80 + k * 95 + r.randint(-20, 20)
        y = 900 + (k % 3) * 90 + r.randint(-10, 10)
        s = 0.7 + (k % 3) * 0.25
        d.rectangle([x - 8 * s, y - 120 * s, x + 8 * s, y], fill=(150, 140, 120, 255))
        d.rectangle([x - 45 * s, y - 95 * s, x + 45 * s, y - 80 * s], fill=(150, 140, 120, 255))
    base = over(base, l)
    return finish(base)


def s_france():
    img = finish(parchment(7))
    d = ImageDraw.Draw(img)
    coastline(d, blob(420, 420, 200, 300, 9), fill=(206, 186, 140))     # Britain
    coastline(d, blob(900, 900, 380, 300, 12), fill=(206, 186, 140))    # France
    d.text((420, 420), "LONDON", font=F(ARCH, 48), fill=BROWN, anchor="mm")
    d.text((900, 900), "PARIS", font=F(ANTON, 110), fill=BROWN, anchor="mm")
    for k in range(0, 100, 8):  # dashed route
        t0, t1 = k / 100, (k + 4) / 100
        p = lambda t: (480 + (820 - 480) * t, 470 + (820 - 470) * t - math.sin(math.pi * t) * 160)
        d.line([p(t0), p(t1)], fill=(160, 30, 30), width=10)
    d.polygon([(820, 820), (770, 790), (790, 840)], fill=(160, 30, 30))
    d.text((1000, 300), "AGAIN.", font=F(ANTON, 160), fill=(160, 30, 30), anchor="mm")
    return img


def s_medal():
    base = gradient((60, 14, 20), (14, 4, 6))
    l = blank()
    d = ImageDraw.Draw(l)
    d.polygon([(560, 120), (840, 120), (760, 560), (640, 560)], fill=(30, 60, 130))
    d.polygon([(640, 120), (760, 120), (720, 560), (680, 560)], fill=(200, 40, 40))
    cx, cy = 700, 760
    pts = []
    for k in range(16):
        r = 260 if k % 2 == 0 else 140
        a = math.pi * 2 * k / 16 - math.pi / 2
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    d.polygon(pts, fill=GOLD)
    d.ellipse([cx - 110, cy - 110, cx + 110, cy + 110], fill=(220, 170, 60))
    d.text((cx, cy), "1845", font=F(ANTON, 80), fill=(90, 60, 20), anchor="mm")
    base = add(base, l, glow=0.4, radius=20)
    t = blank()
    ImageDraw.Draw(t).text((700, 1140), "NEVER PUNISHED", font=F(ANTON, 110), fill=(240, 230, 210), anchor="mm")
    return finish(add(base, t, sharp=0.95))


# ------------------------------------------------------------------ Paper Trail: Charles Ponzi

def mustache_man(d, cx, by, s, fill):
    man(d, cx, by, s, fill)


def s_ponzi_portrait():
    base = gradient((36, 26, 16), (8, 6, 4))
    lamp = blank()
    ImageDraw.Draw(lamp).ellipse([250, -200, 1150, 600], fill=(130, 100, 50))
    base = add(base, lamp.filter(ImageFilter.GaussianBlur(130)), sharp=0.7)
    sil = blank("RGBA")
    d = ImageDraw.Draw(sil)
    man(d, 700, 1250, 1.7, (12, 10, 9, 255))
    base = over(base, sil)
    base = add(base, outline_of(lambda dd: man(dd, 700, 1250, 1.7, 255), GOLD, 3), glow=0.5, radius=10)
    g = blank()
    gd = ImageDraw.Draw(g)  # gold watch chain + cane handle
    gd.arc([560, 1080, 840, 1240], 20, 160, fill=GOLD, width=8)
    gd.ellipse([550, 1110, 590, 1150], fill=GOLD)
    return finish(add(base, g, glow=0.6, radius=10))


def s_office():
    base = gradient((24, 30, 40), (6, 7, 10))
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    d.rectangle([120, 260, 1280, 1260], fill=(40, 30, 24, 255))
    d.rectangle([180, 480, 1220, 1050], fill=(200, 170, 110, 255))          # lit shop window
    d.rectangle([180, 480, 1220, 1050], outline=(20, 16, 12, 255), width=14)
    d.line([(700, 480), (700, 1050)], fill=(20, 16, 12, 255), width=14)
    d.rectangle([160, 300, 1240, 440], fill=(20, 40, 30, 255))
    d.text((700, 340), "SECURITIES EXCHANGE CO.", font=F(ARCH, 56), fill=GOLD + (255,), anchor="mm")
    d.text((700, 405), "27 SCHOOL STREET · BOSTON", font=F(ARCH, 30), fill=(220, 210, 180, 255), anchor="mm")
    for k in range(5):
        man(d, 300 + k * 200, 1260, 0.55, (14, 12, 12, 255))
    base = over(base, l)
    glow = blank()
    ImageDraw.Draw(glow).rectangle([180, 480, 1220, 1050], fill=(120, 90, 40))
    return finish(add(base, glow.filter(ImageFilter.GaussianBlur(60)), sharp=0.5))


def coupon(w=760, h=480, rot=0):
    c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(c)
    d.rectangle([0, 0, w - 1, h - 1], fill=(214, 226, 236, 255), outline=(40, 70, 120, 255), width=8)
    for x in range(0, w, 24):  # perforated edge
        d.ellipse([x - 6, -6, x + 6, 6], fill=(0, 0, 0, 0))
        d.ellipse([x - 6, h - 6, x + 6, h + 6], fill=(0, 0, 0, 0))
    d.text((w // 2, h * 0.2), "INTERNATIONAL", font=F(ARCH, int(h * 0.09)), fill=(40, 70, 120, 255), anchor="mm")
    d.text((w // 2, h * 0.36), "REPLY COUPON", font=F(ANTON, int(h * 0.17)), fill=(40, 70, 120, 255), anchor="mm")
    d.ellipse([w * 0.08, h * 0.5, w * 0.36, h * 0.92], outline=(40, 70, 120, 255), width=6)
    d.text((w * 0.22, h * 0.71), "UPU", font=F(ANTON, int(h * 0.11)), fill=(40, 70, 120, 255), anchor="mm")
    for k in range(4):
        d.line([(w * 0.45, h * (0.58 + k * 0.09)), (w * 0.9, h * (0.58 + k * 0.09))], fill=(110, 130, 160, 255), width=5)
    return c.rotate(rot, expand=True)


def s_coupon():
    img = finish(parchment(3))
    d = ImageDraw.Draw(img)
    d.text((300, 160), "EUROPE", font=F(ANTON, 90), fill=BROWN, anchor="mm")
    d.text((1100, 160), "USA", font=F(ANTON, 90), fill=BROWN, anchor="mm")
    d.text((300, 260), "buy cheap", font=F(ARCH, 40), fill=(140, 40, 30), anchor="mm")
    d.text((1100, 260), "swap for more", font=F(ARCH, 40), fill=(40, 110, 50), anchor="mm")
    d.line([(450, 200), (950, 200)], fill=(140, 40, 30), width=10)
    d.polygon([(950, 180), (990, 200), (950, 220)], fill=(140, 40, 30))
    c = coupon(820, 520, -6)
    img.paste(c, (290, 420), c)
    return img


def s_queue():
    base = gradient((70, 80, 100), (20, 22, 28))
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    d.rectangle([0, 1020, IW, IH], fill=(40, 40, 46, 255))
    d.rectangle([1120, 300, 1400, 1020], fill=(36, 30, 26, 255))
    d.rectangle([1170, 520, 1350, 1020], fill=(200, 170, 110, 255))
    for k in range(9):
        x = 1080 - k * 128
        s = 0.44 - k * 0.015
        man(d, x, 1040 - k * 6, s, (18 + k * 3, 18 + k * 3, 22 + k * 3, 255), hat=k % 3 != 1)
        if k % 3 == 1:
            woman(d, x, 1040 - k * 6, s * 0.95, (18 + k * 3, 18 + k * 3, 22 + k * 3, 255))
    base = over(base, l)
    t = blank()
    ImageDraw.Draw(t).text((560, 220), "LINES DOWN THE STREET", font=F(ANTON, 96), fill=(240, 236, 220), anchor="mm")
    return finish(add(base, t, sharp=0.95))


def s_mansion():
    base = gradient((20, 26, 50), (6, 7, 12))
    sky = blank()
    specks(sky, 120, (0, 0, IW, 500), 2, color=(220, 220, 240), size=(1, 2.4))
    base = add(base, sky)
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    f = (16, 16, 22, 255)
    d.rectangle([200, 560, 1200, 1100], fill=f)
    d.polygon([(160, 560), (700, 330), (1240, 560)], fill=f)
    for x in (330, 480, 920, 1070):  # columns
        d.rectangle([x - 18, 640, x + 18, 1100], fill=(40, 40, 50, 255))
    d.rectangle([0, 1100, IW, IH], fill=(10, 20, 14, 255))
    base = over(base, l)
    w = blank()
    wd = ImageDraw.Draw(w)
    for row in range(2):
        for col in range(6):
            x, y = 260 + col * 160, 650 + row * 220
            wd.rectangle([x, y, x + 80, y + 130], fill=GOLD)
    wd.rectangle([640, 900, 760, 1100], fill=(255, 220, 140))
    base = add(base, w, glow=0.5, radius=18, sharp=0.9)
    car = blank("RGBA")
    cd = ImageDraw.Draw(car)
    cd.rounded_rectangle([860, 1080, 1260, 1180], 30, fill=(8, 8, 10, 255))
    cd.rounded_rectangle([940, 1020, 1160, 1100], 20, fill=(8, 8, 10, 255))
    cd.ellipse([890, 1140, 970, 1220], fill=(4, 4, 6, 255))
    cd.ellipse([1150, 1140, 1230, 1220], fill=(4, 4, 6, 255))
    return finish(over(base, car))


def s_pyramid():
    base = gradient((24, 10, 10), (6, 3, 3))
    l = blank()
    d = ImageDraw.Draw(l)
    rows = [1, 2, 4, 8]
    pos = []
    for r, n in enumerate(rows):
        y = 250 + r * 260
        row = []
        for k in range(n):
            x = 700 + (k - (n - 1) / 2) * (1200 / max(n, 1)) * (0.95 if n > 1 else 1)
            row.append((x, y))
        pos.append(row)
    for r in range(1, len(pos)):
        for k, (x, y) in enumerate(pos[r]):
            px, py = pos[r - 1][k // 2]
            d.line([(x, y - 50), (px, py + 50)], fill=(240, 196, 72), width=8)
    for r, row in enumerate(pos):
        for x, y in row:
            rad = 70 - r * 12
            col = GOLD if r == 0 else (220, 70, 60) if r < 3 else (170, 170, 180)
            d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=col)
    d.text((700, 250), "$", font=F(ANTON, 90), fill=(40, 20, 10), anchor="mm")
    base = add(base, l, glow=0.4, radius=14)
    t = blank()
    ImageDraw.Draw(t).text((700, 1170), "NEW MONEY PAYS OLD", font=F(ANTON, 96), fill=(240, 236, 220), anchor="mm")
    return finish(add(base, t, sharp=0.95))


def s_newspaper():
    img = finish(parchment(6))
    d = ImageDraw.Draw(img)
    d.text((IW // 2, 140), "THE MONEY MATH", font=F(ANTON, 130), fill=(30, 26, 22), anchor="mm")
    d.line([(90, 230), (IW - 90, 230)], fill=(30, 26, 22), width=6)
    d.text((IW // 2, 420), "NEEDED:", font=F(ARCH, 60), fill=(30, 26, 22), anchor="mm")
    d.text((IW // 2, 560), "160,000,000", font=F(ANTON, 170), fill=(150, 30, 30), anchor="mm")
    d.text((IW // 2, 700), "coupons", font=F(ARCH, 50), fill=(30, 26, 22), anchor="mm")
    d.text((IW // 2, 860), "IN EXISTENCE:", font=F(ARCH, 60), fill=(30, 26, 22), anchor="mm")
    d.text((IW // 2, 990), "about 27,000", font=F(ANTON, 140), fill=(40, 100, 50), anchor="mm")
    return img


def s_coupon_stack():
    base = gradient((12, 14, 20), (3, 4, 6))
    l = blank("RGBA")
    for k in range(5):
        c = coupon(560, 350, -10 + k * 5)
        l.paste(c, (400 + k * 18, 380 + k * 40 - k * k * 6), c)
    base = over(base, l)
    t = blank()
    td = ImageDraw.Draw(t)
    td.text((700, 160), "NOT EVEN CLOSE", font=F(ANTON, 120), fill=(240, 236, 220), anchor="mm")
    return finish(add(base, t, sharp=0.95))


def s_collapse():
    base = gradient((30, 30, 34), (8, 8, 10))
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    d.rectangle([180, 260, 1220, 1260], fill=(40, 34, 30, 255))
    d.rectangle([300, 520, 1100, 1260], fill=(14, 12, 12, 255))
    d.rectangle([160, 300, 1240, 440], fill=(20, 40, 30, 255))
    d.text((700, 370), "SECURITIES EXCHANGE CO.", font=F(ARCH, 56), fill=(120, 110, 90, 255), anchor="mm")
    sign = Image.new("RGBA", (620, 200), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sign)
    sd.rectangle([0, 0, 619, 199], fill=(200, 30, 30, 255))
    sd.text((310, 100), "CLOSED", font=F(ANTON, 150), fill=(255, 255, 255, 255), anchor="mm")
    sign = sign.rotate(-8, expand=True)
    l.paste(sign, (390, 660), sign)
    r = random.Random(4)
    for _ in range(14):  # papers on the ground
        x, y = r.randint(100, 1300), r.randint(1120, 1240)
        d.polygon([(x, y), (x + 90, y - 12), (x + 100, y + 50), (x + 6, y + 60)], fill=(220, 214, 196, 255))
    return finish(over(base, l))


def s_prison_ship():
    base = gradient((30, 40, 60), (8, 10, 16))
    l = blank("RGBA")
    d = ImageDraw.Draw(l)
    d.rectangle([0, 900, IW, IH], fill=(16, 26, 40, 255))
    f = (10, 10, 14, 255)
    d.polygon([(250, 900), (1150, 900), (1080, 1010), (320, 1010)], fill=f)       # steamship
    d.rectangle([420, 760, 980, 900], fill=f)
    for x in (560, 760):
        d.rectangle([x, 560, x + 90, 760], fill=f)
    base = over(base, l)
    smoke = blank()
    specks(smoke, 40, (480, 300, 900, 560), 7, color=(90, 90, 100), size=(20, 60))
    base = add(base, smoke.filter(ImageFilter.GaussianBlur(24)), sharp=0.6)
    bars = blank("RGBA")
    bd = ImageDraw.Draw(bars)
    for x in range(60, IW, 160):
        bd.rectangle([x, 0, x + 34, IH], fill=(30, 30, 34, 235))
    bd.rectangle([0, 120, IW, 160], fill=(30, 30, 34, 235))
    base = over(base, bars)
    t = blank()
    ImageDraw.Draw(t).text((700, 1150), "DEPORTED · 1934", font=F(ANTON, 100), fill=(240, 236, 220), anchor="mm")
    return finish(add(base, t, sharp=0.95))


def s_pyramid_stamp():
    img = s_pyramid()
    st = Image.new("RGBA", (900, 230), (0, 0, 0, 0))
    sd = ImageDraw.Draw(st)
    sd.rounded_rectangle([8, 8, 892, 222], 20, outline=(243, 196, 72, 255), width=14)
    sd.text((450, 118), "PONZI SCHEME", font=F(ANTON, 140), fill=(243, 196, 72, 255), anchor="mm")
    st = st.rotate(-10, expand=True)
    img.paste(st, (240, 520), st)
    return img


STORIES = {
    "radium_girls": {1: s_glowing_women, 2: s_factory, 3: s_undark_ad, 4: s_brush_lips, 5: s_painting_dial, 6: s_glowing_smile,
                     7: s_xray_jaw, 9: s_court, 10: s_deathbed, 11: s_safety, 13: s_final},
    "eiffel_tower": {1: s_tower_night, 2: s_con_man, 3: s_rust_tower, 4: s_letter, 5: s_meeting, 6: s_dealer, 7: s_bribe,
                     8: s_cash, 9: s_train, 10: s_head_in_hands, 11: s_escape, 12: s_alcatraz, 13: s_tower_end},
    "poyais": {1: s_map(False), 2: s_general, 3: s_crown, 4: s_guidebook, 5: s_bond, 6: s_banknote, 7: s_ship, 8: s_jungle,
               9: s_graves, 10: s_france, 11: s_medal, 12: s_map(True)},
    "ponzi": {1: s_ponzi_portrait, 2: s_office, 3: s_coupon, 4: s_queue, 5: s_mansion, 6: s_pyramid, 7: s_newspaper,
              8: s_coupon_stack, 9: s_collapse, 10: s_prison_ship, 11: s_pyramid_stamp, 12: s_ponzi_portrait},
}


if __name__ == "__main__":
    name, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for n, fn in STORIES[name].items():
        fn().save(out / f"scene_{n:02d}.png")
        print("drew scene", n)
