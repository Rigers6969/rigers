"""Draws the logo, banner and watermark for both channels.
Run:  python make_kits.py   (needs: pip install pillow)
Fonts: ../fonts (Anton, Archivo Black - SIL Open Font License, free for commercial use)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = HERE.parent / "fonts"
ANTON, ARCHIVO = str(FONTS / "Anton-Regular.ttf"), str(FONTS / "ArchivoBlack-Regular.ttf")


def font(path, size):
    return ImageFont.truetype(path, size)


def centered(draw, xy_center, text, fnt, fill, spacing=0):
    box = draw.textbbox((0, 0), text, font=fnt)
    w, h = box[2] - box[0], box[3] - box[1]
    draw.text((xy_center[0] - w / 2 - box[0], xy_center[1] - h / 2 - box[1]), text, font=fnt, fill=fill)


def overlay(base):
    """A transparent layer to draw see-through things on (ImageDraw doesn't blend by itself)."""
    return Image.new("RGBA", base.size, (0, 0, 0, 0))


def glow(base, layer, radius):
    blurred = layer.filter(ImageFilter.GaussianBlur(radius))
    base.alpha_composite(blurred)
    base.alpha_composite(layer)


# ---------------- The Forgotten Lab ----------------
NAVY, PAPER, GLOW = (12, 22, 38, 255), (242, 230, 201, 255), (79, 240, 192, 255)


def flask_layer(size, cx, cy, s, liquid=True):
    """An Erlenmeyer flask with glowing liquid, scaled by s around (cx, cy)."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    neck_w, neck_h, body_w, body_h = 0.22 * s, 0.32 * s, 0.86 * s, 0.6 * s
    top = cy - (neck_h + body_h) / 2
    outline = [(cx - neck_w / 2, top), (cx + neck_w / 2, top), (cx + neck_w / 2, top + neck_h),
               (cx + body_w / 2, top + neck_h + body_h), (cx - body_w / 2, top + neck_h + body_h), (cx - neck_w / 2, top + neck_h)]
    if liquid:
        lvl = top + neck_h + body_h * 0.42
        frac = (lvl - (top + neck_h)) / body_h
        half = neck_w / 2 + (body_w - neck_w) / 2 * frac
        d.polygon([(cx - half, lvl), (cx + half, lvl), (cx + body_w / 2, top + neck_h + body_h), (cx - body_w / 2, top + neck_h + body_h)], fill=GLOW)
        for bx, by, br in ((-0.12, 0.78, 0.035), (0.08, 0.7, 0.025), (0.0, 0.86, 0.02), (0.18, 0.84, 0.03)):
            x, y, r = cx + bx * s, top + by * (neck_h + body_h), br * s
            d.ellipse((x - r, y - r, x + r, y + r), fill=(12, 22, 38, 200))
    d.line(outline + [outline[0]], fill=PAPER, width=max(3, int(0.045 * s)), joint="curve")
    lip = 0.07 * s
    d.line([(cx - neck_w / 2 - lip, top), (cx + neck_w / 2 + lip, top)], fill=PAPER, width=max(3, int(0.05 * s)))
    return layer


def forgotten_lab(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    # logo 800x800 (YouTube shows it as a circle)
    img = Image.new("RGBA", (800, 800), NAVY)
    rings = overlay(img)
    for r, a in ((360, 70), (300, 40)):
        ImageDraw.Draw(rings).ellipse((400 - r, 400 - r, 400 + r, 400 + r), outline=(79, 240, 192, a), width=4)
    img.alpha_composite(rings)
    d = ImageDraw.Draw(img)
    glow(img, flask_layer((800, 800), 400, 380, 470), 18)
    centered(d, (400, 668), "FORGOTTEN LAB", font(ANTON, 64), PAPER)
    img.convert("RGB").save(out / "logo_800x800.png")
    # watermark 150x150 (bottom-right of every video, "subscribe" button)
    wm = Image.new("RGBA", (150, 150), (0, 0, 0, 0))
    ImageDraw.Draw(wm).ellipse((4, 4, 146, 146), fill=NAVY)
    glow(wm, flask_layer((150, 150), 75, 75, 92), 4)
    wm.save(out / "watermark_150x150.png")
    # banner 2560x1440 - everything important inside the 1546x423 middle (visible on phones)
    W, H = 2560, 1440
    bn = Image.new("RGBA", (W, H), NAVY)
    grid = overlay(bn)
    g = ImageDraw.Draw(grid)
    for x in range(0, W, 64):
        g.line([(x, 0), (x, H)], fill=(255, 255, 255, 14))
    for y in range(0, H, 64):
        g.line([(0, y), (W, y)], fill=(255, 255, 255, 14))
    bn.alpha_composite(grid)
    for x, y, s in ((300, 420, 260), (2260, 1020, 300), (2200, 380, 180), (420, 1050, 200)):
        faint = flask_layer((W, H), x, y, s)
        faint.putalpha(faint.getchannel("A").point(lambda v: v * 22 // 100))
        bn.alpha_composite(faint)
    # phones only show the middle 1546x423 (y 508-931): logo + all text sit inside it
    glow(bn, flask_layer((W, H), 690, 715, 330), 22)
    d = ImageDraw.Draw(bn)
    centered(d, (1400, 650), "THE FORGOTTEN LAB", font(ANTON, 150), PAPER)
    centered(d, (1400, 775), "THE TRUE STORIES SCIENCE FORGOT", font(ARCHIVO, 44), GLOW)
    centered(d, (1400, 860), "NEW STORY EVERY TUESDAY & FRIDAY", font(ARCHIVO, 30), (190, 180, 160, 255))
    bn.convert("RGB").save(out / "banner_2560x1440.png")


# ---------------- Hot Mic Moments ----------------
INK, HOT, GOLD, WHITE = (11, 11, 15, 255), (255, 59, 48, 255), (255, 212, 0, 255), (255, 255, 255, 255)


def mic_layer(size, cx, cy, s, color=WHITE):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    hw, hh = 0.36 * s, 0.56 * s
    top = cy - 0.5 * s
    d.rounded_rectangle((cx - hw / 2, top, cx + hw / 2, top + hh), radius=hw / 2, fill=color)
    for i in range(1, 5):  # grille
        y = top + hh * i / 5.2
        d.line([(cx - hw / 2 + 0.05 * s, y), (cx + hw / 2 - 0.05 * s, y)], fill=(0, 0, 0, 90), width=max(2, int(0.02 * s)))
    w = max(3, int(0.05 * s))
    d.arc((cx - 0.3 * s, top + 0.12 * s, cx + 0.3 * s, top + hh + 0.14 * s), start=0, end=180, fill=color, width=w)
    d.line([(cx, top + hh + 0.14 * s), (cx, top + hh + 0.3 * s)], fill=color, width=w)
    d.rounded_rectangle((cx - 0.17 * s, top + hh + 0.29 * s, cx + 0.17 * s, top + hh + 0.35 * s), radius=0.03 * s, fill=color)
    return layer


def hot_mic(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (800, 800), INK)
    d = ImageDraw.Draw(img)
    halo = Image.new("RGBA", (800, 800), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((150, 110, 650, 610), fill=HOT)
    glow(img, halo, 40)
    glow(img, mic_layer((800, 800), 400, 380, 420), 6)
    centered(d, (400, 690), "HOT MIC", font(ANTON, 96), GOLD)
    img.convert("RGB").save(out / "logo_800x800.png")
    wm = Image.new("RGBA", (150, 150), (0, 0, 0, 0))
    ImageDraw.Draw(wm).ellipse((4, 4, 146, 146), fill=HOT)
    wm.alpha_composite(mic_layer((150, 150), 75, 82, 100))
    wm.save(out / "watermark_150x150.png")
    W, H = 2560, 1440
    bn = Image.new("RGBA", (W, H), INK)
    d = ImageDraw.Draw(bn)
    for i, (x, y, r) in enumerate(((250, 300, 420), (2300, 1150, 520), (2200, 250, 260))):
        blob = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(blob).ellipse((x - r, y - r, x + r, y + r), fill=(HOT[0], HOT[1], HOT[2], 70 if i else 90))
        bn.alpha_composite(blob.filter(ImageFilter.GaussianBlur(120)))
    halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((700 - 175, 715 - 175, 700 + 175, 715 + 175), fill=HOT)
    glow(bn, halo, 50)
    glow(bn, mic_layer((W, H), 700, 720, 270), 8)
    d = ImageDraw.Draw(bn)
    centered(d, (1440, 650), "HOT MIC MOMENTS", font(ANTON, 140), WHITE)
    centered(d, (1440, 770), "THE BEST MOMENTS FROM THE BIGGEST PODCASTS", font(ARCHIVO, 36), GOLD)
    centered(d, (1440, 860), "NEW CLIPS EVERY DAY", font(ARCHIVO, 30), (170, 170, 170, 255))
    bn.convert("RGB").save(out / "banner_2560x1440.png")


if __name__ == "__main__":
    forgotten_lab(HERE / "the-forgotten-lab")
    hot_mic(HERE / "hot-mic-moments")
    print("Done - see the-forgotten-lab/ and hot-mic-moments/")
