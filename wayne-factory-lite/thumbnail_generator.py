"""Generates a thumbnail/cover image from a video's title - the same
"viral" visual language (bold headline, gold highlight word, glow
background, red accent tag) hand-built once for a specific video, now
generalized so Produce/Edit can make one for any video automatically,
in either a YouTube (16:9) or Instagram/Reels/Shorts (9:16) shape.

Pure Pillow (already a project dependency) - deliberately not
Playwright/a browser, since that needs a separate browser-install step
this app doesn't otherwise require.

Fonts (fonts/Anton-Regular.ttf, fonts/ArchivoBlack-Regular.ttf) are real
Google Fonts under the OFL license (fonts/OFL.txt) - free for commercial
use, bundled in the repo so this doesn't depend on what's installed on
any given machine.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

APP_DIR = Path(__file__).resolve().parent
FONTS_DIR = APP_DIR / "fonts"
HEADLINE_FONT_PATH = FONTS_DIR / "Anton-Regular.ttf"
TAG_FONT_PATH = FONTS_DIR / "ArchivoBlack-Regular.ttf"

# YouTube's recommended thumbnail size, and the standard Instagram/Reels/
# TikTok/YouTube Shorts vertical cover size.
ASPECTS = {
    "16:9": (1280, 720),
    "9:16": (1080, 1920),
}
DEFAULT_ASPECT = "16:9"

BG_DARK = (7, 9, 18)
GOLD = (255, 210, 63)
RED = (255, 59, 59)
WHITE = (255, 255, 255)
DIM = (150, 155, 172)


class ThumbnailError(RuntimeError):
    pass


def _require_fonts() -> None:
    missing = [p.name for p in (HEADLINE_FONT_PATH, TAG_FONT_PATH) if not p.exists()]
    if missing:
        raise ThumbnailError(f"Missing font file(s) in fonts/: {', '.join(missing)}")


def _glow_layer(size: tuple[int, int], color: tuple[int, int, int], center: tuple[int, int], radius: int, alpha: int) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x, y = center
    draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=(*color, alpha))
    return layer.filter(ImageFilter.GaussianBlur(max(1, int(radius / 2.2))))


def _draw_background(width: int, height: int) -> Image.Image:
    img = Image.new("RGBA", (width, height), (*BG_DARK, 255))
    glow_radius = int(width * 0.3)
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow.alpha_composite(_glow_layer((width, height), (70, 100, 255), (int(width * 0.82), int(height * 0.22)), glow_radius, 120))
    glow.alpha_composite(_glow_layer((width, height), (255, 60, 60), (int(width * 0.14), int(height * 0.92)), int(glow_radius * 0.85), 85))
    return Image.alpha_composite(img, glow)


def _draw_spark(img: Image.Image, center: tuple[int, int], scale: float = 1.0) -> None:
    """Abstract AI/neural spark icon - deliberately not a real company's
    logo or a person's likeness, to stay clear of trademark/likeness
    issues on an auto-generated image nobody reviews before it's drawn."""
    cx, cy = center
    r_glow = int(150 * scale)
    glow = _glow_layer(img.size, (90, 140, 255), center, r_glow, 160)
    img.alpha_composite(glow)
    draw = ImageDraw.Draw(img)

    spoke_len = 95 * scale
    for angle_deg in (0, 45, 90, 135, 180, 225, 270, 315):
        rad = math.radians(angle_deg)
        x1, y1 = cx + 28 * scale * math.cos(rad), cy + 28 * scale * math.sin(rad)
        x2, y2 = cx + spoke_len * math.cos(rad), cy + spoke_len * math.sin(rad)
        draw.line([(x1, y1), (x2, y2)], fill=(190, 210, 255), width=max(2, int(3 * scale)))
        dot_r = 5 * scale
        draw.ellipse([x2 - dot_r, y2 - dot_r, x2 + dot_r, y2 + dot_r], fill=WHITE)

    star_r = 42 * scale
    star_pts = []
    for i in range(8):
        angle = math.pi / 4 * i
        rad_len = star_r if i % 2 == 0 else star_r * 0.32
        star_pts.append((cx + rad_len * math.cos(angle - math.pi / 2), cy + rad_len * math.sin(angle - math.pi / 2)))
    draw.polygon(star_pts, fill=WHITE)


def _wrap_headline(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for w in words:
        trial = " ".join(current + [w])
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current.append(w)
        else:
            lines.append(" ".join(current))
            current = [w]
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(" ".join(current))
    return lines[:max_lines]


def generate_thumbnail(
    headline: str,
    kicker: str = "",
    tag: str = "",
    brand: str = "",
    aspect: str = DEFAULT_ASPECT,
    out_path: Optional[Path] = None,
) -> Image.Image:
    """Builds one thumbnail/cover image. `aspect` is "16:9" (YouTube,
    1280x720) or "9:16" (Instagram/Reels/Shorts, 1080x1920). `headline` is
    the big bold text (its last line is highlighted gold); `kicker` is
    small text above it; `tag` is an optional red pill of text near the
    bottom; `brand` is a small corner label (e.g. the channel name)."""
    if not headline.strip():
        raise ThumbnailError("headline must not be empty")
    if aspect not in ASPECTS:
        raise ThumbnailError(f"Unknown aspect {aspect!r} - use one of {list(ASPECTS)}.")
    _require_fonts()

    width, height = ASPECTS[aspect]
    is_vertical = aspect == "9:16"

    img = _draw_background(width, height)
    spark_center = (int(width * 0.80), int(height * (0.16 if is_vertical else 0.30)))
    _draw_spark(img, spark_center, scale=width / 1280 * (0.9 if is_vertical else 1.15))
    draw = ImageDraw.Draw(img)

    # Font sizes scale with canvas width so both shapes read the same way
    # relative to their own frame, not literally the same pixel size.
    headline_size = int(width * (0.10 if is_vertical else 0.072))
    kicker_size = int(width * 0.026)
    tag_size = int(width * 0.030)
    brand_size = int(width * 0.017)

    headline_font = ImageFont.truetype(str(HEADLINE_FONT_PATH), headline_size)
    kicker_font = ImageFont.truetype(str(TAG_FONT_PATH), kicker_size)
    tag_font = ImageFont.truetype(str(TAG_FONT_PATH), tag_size)
    brand_font = ImageFont.truetype(str(TAG_FONT_PATH), brand_size)

    left_margin = int(width * 0.052)
    max_text_width = int(width * (0.88 if is_vertical else 0.547))
    # Vertical covers have far more height to spend, so the text block
    # starts lower (clear of the spark icon above it) instead of at the
    # very top like the horizontal shape does.
    y = int(height * (0.30 if is_vertical else 0.122))

    if kicker:
        draw.text((left_margin, y), kicker.upper(), font=kicker_font, fill=GOLD)
        y += int(kicker_size * 2.0)

    max_lines = 6 if is_vertical else 4
    lines = _wrap_headline(headline.upper(), headline_font, max_text_width, draw, max_lines)
    for i, line in enumerate(lines):
        color = GOLD if i == len(lines) - 1 else WHITE
        draw.text((left_margin, y), line, font=headline_font, fill=color)
        bbox = draw.textbbox((left_margin, y), line, font=headline_font)
        y = bbox[3] + int(headline_size * 0.05)

    if tag:
        # Directly below the headline, not pinned to the bottom edge - a
        # short headline previously left a large dead gap above a
        # bottom-pinned tag, worst on the tall 9:16 canvas.
        tag_text = tag.upper()
        bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
        pad_x, pad_y = int(tag_size * 0.75), int(tag_size * 0.44)
        tag_w = (bbox[2] - bbox[0]) + pad_x * 2
        tag_h = (bbox[3] - bbox[1]) + pad_y * 2
        tag_x = left_margin
        tag_y = y + int(headline_size * 0.3)
        draw.rounded_rectangle([tag_x, tag_y, tag_x + tag_w, tag_y + tag_h], radius=8, fill=RED)
        draw.text((tag_x + pad_x, tag_y + pad_y - bbox[1]), tag_text, font=tag_font, fill=WHITE)

    if brand:
        brand_text = brand.upper()
        bbox = draw.textbbox((0, 0), brand_text, font=brand_font)
        draw.text((width - int(width * 0.031) - (bbox[2] - bbox[0]), height - int(height * 0.058)), brand_text, font=brand_font, fill=DIM)

    final = img.convert("RGB")
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        final.save(out_path, "JPEG", quality=92, optimize=True)
    return final
