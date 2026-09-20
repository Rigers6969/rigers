"""Instagram thumbnail generator for Paper Trail (true-crime/fraud channel).

Plain black "text card" style: bold white centered headline + smaller
subtext, muted gray "PAPER TRAIL" brand label in the bottom corner.

Optionally takes a real photo of the case's subject via --photo: it's
used as a full-bleed, grayscale, cover-fit background with a dark
gradient behind the text so the white text stays readable. Without
--photo, the background is solid black, exactly as before.

Outputs two sizes from the same inputs:
  - thumbnail_square.png    (1080x1080, feed post)
  - thumbnail_vertical.png  (1080x1920, Stories/Reels cover)
"""
from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

SQUARE_SIZE = (1080, 1080)
VERTICAL_SIZE = (1080, 1920)

WHITE = (255, 255, 255, 255)
BLACK = (0, 0, 0, 255)
MUTED_GRAY = (150, 150, 150, 255)

# Bold sans-serif candidates, in priority order. The first one found on the
# system is used; if none are installed, Pillow's DejaVu Sans Bold (bundled
# with Pillow itself) is the guaranteed-available fallback.
BOLD_FONT_CANDIDATES = [
    "Montserrat-Black.ttf",
    "Montserrat-ExtraBold.ttf",
    "Inter-Black.ttf",
    "Inter-ExtraBold.ttf",
    "Helvetica-Bold.ttf",
    "HelveticaNeue-Bold.ttf",
    "Arial Bold.ttf",
    "Arial-Bold.ttf",
    "DejaVuSans-Bold.ttf",
]

FONT_SEARCH_DIRS = [
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path.home() / ".fonts",
    Path.home() / "Library/Fonts",
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts"),
    Path("C:/Windows/Fonts"),
]


def _find_font_file(candidates: list[str]) -> str | None:
    for name in candidates:
        for base_dir in FONT_SEARCH_DIRS:
            if not base_dir.exists():
                continue
            for match in base_dir.rglob(name):
                return str(match)
    return None


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    font_path = _find_font_file(BOLD_FONT_CANDIDATES)
    if font_path:
        return ImageFont.truetype(font_path, size)
    # Pillow ships DejaVuSans-Bold as a package resource; load_default(size=)
    # falls back to it and always works with zero external dependencies.
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        # Older Pillow without the size kwarg - load_default() is tiny, so
        # try one more explicit path guess before giving up gracefully.
        return ImageFont.load_default()


def _wrap_text_to_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    start_size: int,
    min_size: int,
    bold: bool = True,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Shrinks font size until the wrapped text fits within max_width/max_height."""
    size = start_size
    while size >= min_size:
        font = _load_font(size)
        lines = _wrap_text_to_width(draw, text, font, max_width)
        line_height = font.getbbox("Ag")[3] - font.getbbox("Ag")[1]
        line_spacing = int(line_height * 1.25)
        total_height = line_spacing * len(lines)
        widest = max(draw.textlength(line, font=font) for line in lines)
        if total_height <= max_height and widest <= max_width:
            return font, lines
        size -= 4
    # Fall back to the smallest size regardless of fit, rather than crashing.
    font = _load_font(min_size)
    return font, _wrap_text_to_width(draw, text, font, max_width)


def _draw_centered_multiline(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    center_x: int,
    center_y: int,
    fill: tuple[int, int, int, int],
    line_spacing_mult: float = 1.25,
) -> int:
    """Draws vertically-centered, horizontally-centered lines; returns total block height."""
    bbox = font.getbbox("Ag")
    line_height = bbox[3] - bbox[1]
    line_spacing = int(line_height * line_spacing_mult)
    total_height = line_spacing * len(lines)
    y = center_y - total_height // 2
    for line in lines:
        width = draw.textlength(line, font=font)
        draw.text((center_x - width / 2, y), line, font=font, fill=fill)
        y += line_spacing
    return total_height


def _cover_fit_grayscale(photo_path: str, size: tuple[int, int]) -> Image.Image:
    """Crops+scales the photo to fill `size` (cover-fit, centered, no
    stretching), then converts to grayscale."""
    img = Image.open(photo_path)
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")

    target_w, target_h = size
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        # Source is relatively wider - crop the sides.
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    else:
        # Source is relatively taller - crop top/bottom.
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        img = img.crop((0, top, src_w, top + new_h))

    img = img.resize(size, Image.LANCZOS)
    img = ImageOps.grayscale(img).convert("RGB")
    return img


def _add_gradient_overlay(base: Image.Image, text_zone_top_frac: float) -> Image.Image:
    """Overlays a black gradient: transparent above text_zone_top_frac,
    fading to solid black by the bottom, so text sitting in that zone
    stays readable over any photo."""
    width, height = base.size
    gradient = Image.new("L", (1, height), 0)
    fade_start = int(height * text_zone_top_frac)

    for y in range(height):
        if y < fade_start:
            alpha = 0
        else:
            progress = (y - fade_start) / max(height - fade_start, 1)
            alpha = int(min(progress * 1.6, 1.0) * 235)
        gradient.putpixel((0, y), alpha)

    gradient = gradient.resize((width, height))
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    overlay.putalpha(gradient)

    base_rgba = base.convert("RGBA")
    return Image.alpha_composite(base_rgba, overlay)


def generate_thumbnail(
    headline: str,
    subtext: str,
    size: tuple[int, int],
    photo_path: str | None = None,
) -> Image.Image:
    width, height = size

    if photo_path:
        canvas = _cover_fit_grayscale(photo_path, size)
        canvas = canvas.convert("RGBA")
        # Text sits in the lower ~45% of the frame - fade the gradient in
        # starting a bit above that so it's dark and solid behind the text,
        # transparent (full photo visible) above it.
        canvas = _add_gradient_overlay(canvas, text_zone_top_frac=0.5)
    else:
        canvas = Image.new("RGBA", size, BLACK)

    draw = ImageDraw.Draw(canvas)

    margin_x = int(width * 0.10)
    max_text_width = width - 2 * margin_x

    headline_start_size = int(width * 0.13)
    headline_min_size = int(width * 0.05)
    subtext_start_size = int(width * 0.045)
    subtext_min_size = int(width * 0.025)

    headline_max_height = int(height * 0.32)
    headline_font, headline_lines = _fit_text(
        draw, headline.upper(), max_text_width, headline_max_height, headline_start_size, headline_min_size
    )

    subtext_max_height = int(height * 0.14)
    subtext_font, subtext_lines = _fit_text(
        draw, subtext, max_text_width, subtext_max_height, subtext_start_size, subtext_min_size
    )

    center_x = width // 2
    gap = int(height * 0.025)

    hb = headline_font.getbbox("Ag")
    headline_line_height = int((hb[3] - hb[1]) * 1.25)
    headline_block_height = headline_line_height * len(headline_lines)

    sb = subtext_font.getbbox("Ag")
    subtext_line_height = int((sb[3] - sb[1]) * 1.25)
    subtext_block_height = subtext_line_height * len(subtext_lines)

    total_block_height = headline_block_height + gap + subtext_block_height
    block_center_y = int(height * 0.52)
    headline_center_y = block_center_y - total_block_height // 2 + headline_block_height // 2

    _draw_centered_multiline(draw, headline_lines, headline_font, center_x, headline_center_y, WHITE)

    subtext_center_y = headline_center_y + headline_block_height // 2 + gap + subtext_block_height // 2
    _draw_centered_multiline(draw, subtext_lines, subtext_font, center_x, subtext_center_y, WHITE)

    label_font_size = int(width * 0.022)
    label_font = _load_font(label_font_size)
    label_text = "PAPER TRAIL"
    label_width = draw.textlength(label_text, font=label_font)
    label_margin = int(width * 0.045)
    label_x = width - label_margin - label_width
    label_y = height - label_margin - label_font_size
    draw.text((label_x, label_y), label_text, font=label_font, fill=MUTED_GRAY)

    return canvas.convert("RGB")


def main():
    parser = argparse.ArgumentParser(description="Generate Paper Trail Instagram thumbnails.")
    parser.add_argument("--headline", required=True, help="Big bold headline text.")
    parser.add_argument("--subtext", required=True, help="Smaller line underneath the headline.")
    parser.add_argument(
        "--photo",
        default=None,
        help="Optional path to a photo of the case's subject, used as a grayscale cover-fit background.",
    )
    parser.add_argument("--out-square", default="thumbnail_square.png", help="Output path for the 1080x1080 square.")
    parser.add_argument("--out-vertical", default="thumbnail_vertical.png", help="Output path for the 1080x1920 vertical.")
    args = parser.parse_args()

    square = generate_thumbnail(args.headline, args.subtext, SQUARE_SIZE, args.photo)
    square.save(args.out_square)
    print(f"Saved {args.out_square}")

    vertical = generate_thumbnail(args.headline, args.subtext, VERTICAL_SIZE, args.photo)
    vertical.save(args.out_vertical)
    print(f"Saved {args.out_vertical}")


if __name__ == "__main__":
    main()
