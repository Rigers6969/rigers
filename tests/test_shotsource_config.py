"""Tests for shotsource's YAML config loading and deep-merge."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shotsource.config import load_config  # noqa: E402


class TestLoadConfig(unittest.TestCase):
    def test_defaults_load_with_no_override(self):
        config = load_config()
        self.assertEqual(config.top_n_per_shot, 5)
        self.assertEqual(config.quality.hard_reject.min_width_px, 1920)
        self.assertEqual(config.quality.hard_reject.aspect_ratio_min, 1.2)
        self.assertEqual(config.quality.hard_reject.aspect_ratio_max, 2.4)
        self.assertIn("openverse", config.sources)
        self.assertTrue(config.sources["openverse"].enabled)
        self.assertIn("pixabay", config.sources)
        self.assertIn("unsplash", config.sources)
        self.assertEqual(config.sources["pixabay"].api_key_env, "PIXABAY_API_KEY")
        self.assertEqual(config.sources["unsplash"].api_key_env, "UNSPLASH_ACCESS_KEY")

    def test_override_changes_only_specified_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            override_path = Path(tmp) / "override.yaml"
            override_path.write_text(
                "top_n_per_shot: 3\n"
                "quality:\n"
                "  hard_reject:\n"
                "    min_width_px: 1280\n",
                encoding="utf-8",
            )
            config = load_config(str(override_path))
            self.assertEqual(config.top_n_per_shot, 3)
            self.assertEqual(config.quality.hard_reject.min_width_px, 1280)
            # Untouched values still come from the packaged defaults.
            self.assertEqual(config.quality.hard_reject.aspect_ratio_max, 2.4)
            self.assertEqual(config.quality.scoring.weights.caption_similarity, 0.4)

    def test_source_override_disables_a_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            override_path = Path(tmp) / "override.yaml"
            override_path.write_text(
                "sources:\n  pexels:\n    enabled: false\n",
                encoding="utf-8",
            )
            config = load_config(str(override_path))
            self.assertFalse(config.sources["pexels"].enabled)
            self.assertTrue(config.sources["openverse"].enabled)


if __name__ == "__main__":
    unittest.main()
