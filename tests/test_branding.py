"""Tests for the brand kit generator and Pillow-based asset rendering.

Fully offline - no network, no Ollama, no Anthropic key required. The LLM
call is scripted, same pattern as tests/test_empire.py's ScriptedAnalyzer.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from branding import (  # noqa: E402
    BaseBrandGenerator,
    BrandGenerationError,
    BrandKit,
    render_instagram_profile_pic,
    render_logo,
    render_youtube_banner,
    save_brand_assets,
)

VALID_BRAND_RESPONSE = json.dumps({
    "logo_text": "WF",
    "tagline": "Clips that hit different",
    "primary_color": "#1A1A2E",
    "secondary_color": "#16213E",
    "accent_color": "#E94560",
    "youtube_description": "Short clips from long videos, cut for maximum impact.",
    "instagram_bio": "Viral moments, daily.",
    "hashtags": ["#shorts", "#viral", "#clips"],
})


class ScriptedBrandGenerator(BaseBrandGenerator):
    def __init__(self, response: str):
        self._response = response

    def _call_model(self, prompt: str) -> str:
        return self._response


class TestBrandGeneration(unittest.TestCase):
    def test_valid_response_produces_brand_kit(self):
        gen = ScriptedBrandGenerator(VALID_BRAND_RESPONSE)
        brand = gen.generate("The Wayne Factory", "viral short-form clips")
        self.assertEqual(brand.logo_text, "WF")
        self.assertEqual(brand.primary_color, "#1A1A2E")
        self.assertIn("#shorts", brand.hashtags)

    def test_markdown_fenced_response_still_parses(self):
        gen = ScriptedBrandGenerator(f"```json\n{VALID_BRAND_RESPONSE}\n```")
        brand = gen.generate("The Wayne Factory", "viral short-form clips")
        self.assertEqual(brand.logo_text, "WF")

    def test_garbage_response_raises_clear_error(self):
        gen = ScriptedBrandGenerator("I'm not able to help with that request.")
        with self.assertRaises(BrandGenerationError) as ctx:
            gen.generate("The Wayne Factory", "viral short-form clips")
        self.assertIn("no parseable JSON", str(ctx.exception))

    def test_invalid_hex_color_raises_clear_error(self):
        bad = json.loads(VALID_BRAND_RESPONSE)
        bad["primary_color"] = "not-a-color"
        gen = ScriptedBrandGenerator(json.dumps(bad))
        with self.assertRaises(BrandGenerationError):
            gen.generate("The Wayne Factory", "viral short-form clips")

    def test_missing_field_raises_clear_error(self):
        bad = json.loads(VALID_BRAND_RESPONSE)
        del bad["instagram_bio"]
        gen = ScriptedBrandGenerator(json.dumps(bad))
        with self.assertRaises(BrandGenerationError):
            gen.generate("The Wayne Factory", "viral short-form clips")


class TestRendering(unittest.TestCase):
    def setUp(self):
        gen = ScriptedBrandGenerator(VALID_BRAND_RESPONSE)
        self.brand = gen.generate("The Wayne Factory", "viral short-form clips")

    def test_logo_is_square_rgb(self):
        img = render_logo(self.brand, size=256)
        self.assertEqual(img.size, (256, 256))
        self.assertEqual(img.mode, "RGB")

    def test_youtube_banner_is_correct_size(self):
        img = render_youtube_banner(self.brand)
        self.assertEqual(img.size, (2560, 1440))

    def test_instagram_profile_pic_is_correct_size(self):
        img = render_instagram_profile_pic(self.brand, size=1080)
        self.assertEqual(img.size, (1080, 1080))

    def test_save_brand_assets_writes_all_three_files(self):
        with tempfile.TemporaryDirectory() as d:
            paths = save_brand_assets(self.brand, Path(d))
            self.assertEqual(set(paths.keys()), {"logo", "youtube_banner", "instagram_profile"})
            for path in paths.values():
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
