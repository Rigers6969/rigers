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


STORIES = {
    "radium_girls": {1: s_glowing_women, 2: s_factory, 3: s_undark_ad, 4: s_brush_lips, 5: s_painting_dial, 6: s_glowing_smile,
                     7: s_xray_jaw, 9: s_court, 10: s_deathbed, 11: s_safety, 13: s_final},
    "eiffel_tower": {1: s_tower_night, 2: s_con_man, 3: s_rust_tower, 4: s_letter, 5: s_meeting, 6: s_dealer, 7: s_bribe,
                     8: s_cash, 9: s_train, 10: s_head_in_hands, 11: s_escape, 12: s_alcatraz, 13: s_tower_end},
}


if __name__ == "__main__":
    name, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for n, fn in STORIES[name].items():
        fn().save(out / f"scene_{n:02d}.png")
        print("drew scene", n)
