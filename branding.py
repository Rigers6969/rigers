"""Channel brand kit generation for The Wayne Factory.

Generates a logo, YouTube banner, and Instagram profile picture locally with
Pillow (no image-generation API/key needed), plus text assets (channel
description, Instagram bio, hashtags) via the same LLM-call architecture as
BaseViralAnalyzer: call the model, extract JSON robustly, validate, and
surface a clear error if either step fails.

This does NOT create the YouTube channel or Instagram account - both
platforms require a human to do that manually (account creation can't be
automated per their Terms of Service). This only generates the assets you
upload once those accounts exist.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from json_utils import extract_json_items

BRAND_SCHEMA = {
    "type": "object",
    "properties": {
        "channel_name": {"type": "string"},
        "logo_text": {"type": "string"},
        "tagline": {"type": "string"},
        "primary_color": {"type": "string"},
        "secondary_color": {"type": "string"},
        "accent_color": {"type": "string"},
        "youtube_description": {"type": "string"},
        "youtube_tags": {"type": "array", "items": {"type": "string"}},
        "instagram_bio": {"type": "string"},
        "instagram_hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "channel_name", "logo_text", "tagline", "primary_color", "secondary_color", "accent_color",
        "youtube_description", "youtube_tags", "instagram_bio", "instagram_hashtags",
    ],
    "additionalProperties": False,
}

BRAND_PROMPT_TEMPLATE = """You are a brand designer and YouTube/Instagram content strategist. Analyze the content below and design a complete brand kit for a short-form video channel built from it.

{name_instruction}

Content to analyze:
{content}

Respond with ONLY a JSON object (no prose, no markdown fences) with exactly these fields:
- "channel_name": {name_field_instruction}
- "logo_text": 1 to 3 characters or a short word to display in a circular logo (e.g. initials)
- "tagline": a punchy tagline, 6 words or fewer, reflecting the actual content's themes
- "primary_color": a hex color code, e.g. "#1A1A2E"
- "secondary_color": a hex color code that complements primary_color for a gradient
- "accent_color": a hex color code for text/highlights that contrasts strongly against primary_color
- "youtube_description": a 2-3 sentence YouTube channel description based on the content's actual themes
- "youtube_tags": an array of 10 to 15 plain keyword tags (no # symbol) relevant to this content, for YouTube's video/channel tags field
- "instagram_bio": an Instagram bio, 150 characters or fewer
- "instagram_hashtags": an array of 5 to 10 relevant hashtags, each starting with #
"""

MAX_CONTENT_CHARS_TOTAL = 12000


def prepare_content_for_prompt(texts: list[str], max_total_chars: int = MAX_CONTENT_CHARS_TOTAL) -> str:
    """Joins one or more transcript/description texts into a single prompt-sized
    string, giving each an even share of the character budget so a brand kit
    built from several videos isn't dominated by whichever came first."""
    texts = [t for t in texts if t and t.strip()]
    if not texts:
        return ""
    budget_per_text = max(max_total_chars // len(texts), 500)
    parts = []
    for text in texts:
        text = text.strip()
        if len(text) > budget_per_text:
            text = text[:budget_per_text] + " [...truncated]"
        parts.append(text)
    return "\n\n---\n\n".join(parts)


class BrandGenerationError(RuntimeError):
    pass


@dataclass
class BrandKit:
    channel_name: str
    logo_text: str
    tagline: str
    primary_color: str
    secondary_color: str
    accent_color: str
    youtube_description: str
    instagram_bio: str
    youtube_tags: list[str] = field(default_factory=list)
    instagram_hashtags: list[str] = field(default_factory=list)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = str(hex_color).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"invalid hex color: {hex_color!r}")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


# --------------------------------------------------------------------------
# Generators - same pattern as BaseViralAnalyzer: subclasses implement
# _call_model only, and extract_json_items() absorbs the same messy-JSON
# failure modes (markdown fences, prose wrapping, object-wrapped payloads).
# --------------------------------------------------------------------------

class BaseBrandGenerator:
    def _call_model(self, prompt: str) -> str:
        raise NotImplementedError

    def generate(self, content: str, channel_name: Optional[str] = None) -> BrandKit:
        """Analyzes `content` (a niche description, or real transcript text from
        one or more videos - see prepare_content_for_prompt) and generates a full
        brand kit. If `channel_name` is omitted, the model invents one from the
        content's actual themes instead of requiring the caller to supply one."""
        if channel_name:
            name_instruction = f'The channel name is fixed: "{channel_name}". Do not change it.'
            name_field_instruction = f'must be exactly "{channel_name}"'
        else:
            name_instruction = "No channel name has been chosen yet - invent one based on the content's actual themes."
            name_field_instruction = "a catchy channel name you invent based on the content, 4 words or fewer"

        prompt = BRAND_PROMPT_TEMPLATE.format(
            name_instruction=name_instruction, name_field_instruction=name_field_instruction, content=content
        )
        raw = self._call_model(prompt)

        items = extract_json_items(raw)
        if not items:
            preview = raw[:300].replace("\n", " ")
            raise BrandGenerationError(
                f"Brand generator returned no parseable JSON (first 300 chars: {preview!r})"
            )
        data = items[0]
        if not isinstance(data, dict):
            raise BrandGenerationError("Brand generator response was not a JSON object")

        try:
            for color_key in ("primary_color", "secondary_color", "accent_color"):
                _hex_to_rgb(data[color_key])
            return BrandKit(
                channel_name=channel_name or str(data["channel_name"])[:60],
                logo_text=str(data["logo_text"])[:6],
                tagline=str(data["tagline"])[:60],
                primary_color=str(data["primary_color"]),
                secondary_color=str(data["secondary_color"]),
                accent_color=str(data["accent_color"]),
                youtube_description=str(data["youtube_description"])[:1000],
                instagram_bio=str(data["instagram_bio"])[:150],
                youtube_tags=[str(t) for t in data.get("youtube_tags", [])][:20],
                instagram_hashtags=[str(h) for h in data.get("instagram_hashtags", [])][:15],
            )
        except (KeyError, ValueError) as exc:
            raise BrandGenerationError(f"Brand generator returned incomplete/invalid data: {exc}") from exc


class OllamaBrandGenerator(BaseBrandGenerator):
    def __init__(self, model: str = "llama3", host: str = "http://localhost:11434", request_timeout: float = 600):
        self.model = model
        self.host = host.rstrip("/")
        # See OllamaViralAnalyzer's request_timeout in empire.py: local CPU
        # inference time varies a lot by hardware, so a short fixed timeout
        # can abort a call that's still legitimately generating.
        self.request_timeout = request_timeout

    def _call_model(self, prompt: str) -> str:
        import requests

        resp = requests.post(
            f"{self.host}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.6},
            },
            timeout=self.request_timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")


class ClaudeBrandGenerator(BaseBrandGenerator):
    def __init__(self, api_key: str, model: str = "claude-sonnet-5"):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def _call_model(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": BRAND_SCHEMA}},
        )
        return next(block.text for block in response.content if block.type == "text")


# --------------------------------------------------------------------------
# Rendering (Pillow only - no external image-gen API/key required)
# --------------------------------------------------------------------------

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # common on Linux
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arialbd.ttf"),  # Windows
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",  # macOS
    "DejaVuSans-Bold.ttf",
    "arialbd.ttf",
]


def _load_font(size: int) -> ImageFont.ImageFont:
    for candidate in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _gradient_background(size: tuple[int, int], color_a: tuple[int, int, int], color_b: tuple[int, int, int]) -> Image.Image:
    w, h = size
    base = Image.new("RGB", size, color_a)
    top = Image.new("RGB", size, color_b)
    mask = Image.new("L", size)
    mask.putdata([int(255 * (y / max(h - 1, 1))) for y in range(h) for _ in range(w)])
    base.paste(top, (0, 0), mask)
    return base


def _centered_text(draw: ImageDraw.ImageDraw, box_center: tuple[float, float], text: str, font: ImageFont.ImageFont, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    cx, cy = box_center
    draw.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), text, font=font, fill=fill)


def render_logo(brand: BrandKit, size: int = 512) -> Image.Image:
    primary = _hex_to_rgb(brand.primary_color)
    secondary = _hex_to_rgb(brand.secondary_color)
    accent = _hex_to_rgb(brand.accent_color)
    img = _gradient_background((size, size), primary, secondary)
    draw = ImageDraw.Draw(img)
    font = _load_font(int(size * 0.4))
    _centered_text(draw, (size / 2, size / 2), brand.logo_text, font, accent)
    return img


def render_youtube_banner(brand: BrandKit, size: tuple[int, int] = (2560, 1440)) -> Image.Image:
    primary = _hex_to_rgb(brand.primary_color)
    secondary = _hex_to_rgb(brand.secondary_color)
    accent = _hex_to_rgb(brand.accent_color)
    img = _gradient_background(size, primary, secondary)
    draw = ImageDraw.Draw(img)
    w, h = size
    # Keep text within the ~1546x423 "safe area" YouTube guarantees is
    # visible across TV/desktop/mobile, centered on the banner.
    title_font = _load_font(int(h * 0.09))
    tagline_font = _load_font(int(h * 0.035))
    _centered_text(draw, (w / 2, h / 2 - h * 0.06), brand.channel_name, title_font, accent)
    _centered_text(draw, (w / 2, h / 2 + h * 0.06), brand.tagline, tagline_font, accent)
    return img


def render_instagram_profile_pic(brand: BrandKit, size: int = 1080) -> Image.Image:
    return render_logo(brand, size=size)


def save_brand_assets(brand: BrandKit, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    logo_path = output_dir / "logo.png"
    render_logo(brand).save(logo_path)
    paths["logo"] = logo_path

    banner_path = output_dir / "youtube_banner.png"
    render_youtube_banner(brand).save(banner_path)
    paths["youtube_banner"] = banner_path

    profile_path = output_dir / "instagram_profile.png"
    render_instagram_profile_pic(brand).save(profile_path)
    paths["instagram_profile"] = profile_path

    return paths
