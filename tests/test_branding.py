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
    prepare_content_for_prompt,
    render_instagram_profile_pic,
    render_logo,
    render_youtube_banner,
    save_brand_assets,
)

VALID_BRAND_RESPONSE = json.dumps({
    "channel_name": "The Wayne Factory",
    "logo_text": "WF",
    "tagline": "Clips that hit different",
    "primary_color": "#1A1A2E",
    "secondary_color": "#16213E",
    "accent_color": "#E94560",
    "youtube_description": "Short clips from long videos, cut for maximum impact.",
    "youtube_tags": ["shorts", "viral", "clips"],
    "instagram_bio": "Viral moments, daily.",
    "instagram_hashtags": ["#shorts", "#viral", "#clips"],
})


class ScriptedBrandGenerator(BaseBrandGenerator):
    def __init__(self, response: str):
        self._response = response

    def _call_model(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self._response


class TestBrandGeneration(unittest.TestCase):
    def test_valid_response_produces_brand_kit(self):
        gen = ScriptedBrandGenerator(VALID_BRAND_RESPONSE)
        brand = gen.generate("transcript excerpts about viral short-form clips", channel_name="The Wayne Factory")
        self.assertEqual(brand.logo_text, "WF")
        self.assertEqual(brand.primary_color, "#1A1A2E")
        self.assertIn("#shorts", brand.instagram_hashtags)
        self.assertIn("shorts", brand.youtube_tags)

    def test_channel_name_hint_overrides_model_output(self):
        # Even if the model's JSON echoes back a different name, the hint the
        # caller supplied wins - it's the one thing the caller controls exactly.
        response = json.loads(VALID_BRAND_RESPONSE)
        response["channel_name"] = "Some Other Name"
        gen = ScriptedBrandGenerator(json.dumps(response))
        brand = gen.generate("content", channel_name="My Real Channel")
        self.assertEqual(brand.channel_name, "My Real Channel")

    def test_no_channel_name_hint_uses_model_suggestion(self):
        gen = ScriptedBrandGenerator(VALID_BRAND_RESPONSE)
        brand = gen.generate("transcript excerpts about viral short-form clips")
        self.assertEqual(brand.channel_name, "The Wayne Factory")

    def test_no_hint_prompts_model_to_invent_a_name(self):
        gen = ScriptedBrandGenerator(VALID_BRAND_RESPONSE)
        gen.generate("some transcript content")
        self.assertIn("invent one", gen.last_prompt)

    def test_hint_given_prompts_model_to_keep_it_fixed(self):
        gen = ScriptedBrandGenerator(VALID_BRAND_RESPONSE)
        gen.generate("some transcript content", channel_name="My Real Channel")
        self.assertIn('"My Real Channel"', gen.last_prompt)

    def test_markdown_fenced_response_still_parses(self):
        gen = ScriptedBrandGenerator(f"```json\n{VALID_BRAND_RESPONSE}\n```")
        brand = gen.generate("content", channel_name="The Wayne Factory")
        self.assertEqual(brand.logo_text, "WF")

    def test_garbage_response_raises_clear_error(self):
        gen = ScriptedBrandGenerator("I'm not able to help with that request.")
        with self.assertRaises(BrandGenerationError) as ctx:
            gen.generate("content", channel_name="The Wayne Factory")
        self.assertIn("no parseable JSON", str(ctx.exception))

    def test_invalid_hex_color_raises_clear_error(self):
        bad = json.loads(VALID_BRAND_RESPONSE)
        bad["primary_color"] = "not-a-color"
        gen = ScriptedBrandGenerator(json.dumps(bad))
        with self.assertRaises(BrandGenerationError):
            gen.generate("content", channel_name="The Wayne Factory")

    def test_missing_field_raises_clear_error(self):
        bad = json.loads(VALID_BRAND_RESPONSE)
        del bad["instagram_bio"]
        gen = ScriptedBrandGenerator(json.dumps(bad))
        with self.assertRaises(BrandGenerationError):
            gen.generate("content", channel_name="The Wayne Factory")


class TestPrepareContentForPrompt(unittest.TestCase):
    def test_empty_list_returns_empty_string(self):
        self.assertEqual(prepare_content_for_prompt([]), "")

    def test_single_text_passed_through_when_short(self):
        self.assertEqual(prepare_content_for_prompt(["hello world"]), "hello world")

    def test_multiple_texts_joined_with_separator(self):
        result = prepare_content_for_prompt(["video one content", "video two content"])
        self.assertIn("video one content", result)
        self.assertIn("video two content", result)
        self.assertIn("---", result)

    def test_long_text_truncated_to_budget(self):
        long_text = "word " * 10000
        result = prepare_content_for_prompt([long_text], max_total_chars=1000)
        self.assertLessEqual(len(result), 1050)
        self.assertIn("[...truncated]", result)

    def test_budget_split_evenly_across_multiple_videos(self):
        texts = ["a" * 5000, "b" * 5000]
        result = prepare_content_for_prompt(texts, max_total_chars=2000)
        self.assertIn("a" * 900, result)
        self.assertIn("b" * 900, result)


class TestRendering(unittest.TestCase):
    def setUp(self):
        gen = ScriptedBrandGenerator(VALID_BRAND_RESPONSE)
        self.brand = gen.generate("content", channel_name="The Wayne Factory")

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
