"""Tests for the hard-reject checks and scoring math in shotsource.quality.

Uses synthetic in-memory images (no network, no real photos) so these run
anywhere opencv/numpy/imagehash/Pillow are installed.
"""
import sys
import unittest
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shotsource.config import HardRejectConfig, ScoringWeights  # noqa: E402
from shotsource.quality import (  # noqa: E402
    ImageInfo,
    combine_scores,
    has_watermark_band,
    has_watermark_keyword,
    hard_reject_reason,
    resolution_score,
    sharpness_score,
    sharpness_variance,
)


def _make_info(width: int, height: int, gray: np.ndarray = None, seed: int = 0) -> ImageInfo:
    if gray is None:
        rng = np.random.RandomState(seed)
        gray = rng.randint(0, 256, size=(height, width), dtype=np.uint8)
    pil_image = Image.fromarray(gray)
    return ImageInfo(width=width, height=height, gray=gray, phash=imagehash.phash(pil_image))


class TestHardRejectResolutionAndAspect(unittest.TestCase):
    def setUp(self):
        self.config = HardRejectConfig()

    def test_below_min_width_is_rejected(self):
        info = _make_info(1000, 600)
        reason = hard_reject_reason(info, "a photo", self.config, [])
        self.assertIsNotNone(reason)
        self.assertIn("width", reason)

    def test_min_width_exactly_at_threshold_passes_width_check(self):
        info = _make_info(1920, 1000, seed=1)
        reason = hard_reject_reason(info, "a photo", self.config, [])
        # 1920/1000 = 1.92, within [1.2, 2.4], so this should pass entirely
        # unless the random noise happens to look like a watermark band.
        self.assertIsNone(reason)

    def test_aspect_ratio_too_narrow_is_rejected(self):
        # 1920x1920 -> aspect 1.0, below the 1.2 minimum
        info = _make_info(1920, 1920, seed=2)
        reason = hard_reject_reason(info, "a photo", self.config, [])
        self.assertIsNotNone(reason)
        self.assertIn("aspect ratio", reason)

    def test_aspect_ratio_too_wide_is_rejected(self):
        # 3000x1000 -> aspect 3.0, above the 2.4 maximum
        info = _make_info(3000, 1000, seed=3)
        reason = hard_reject_reason(info, "a photo", self.config, [])
        self.assertIsNotNone(reason)
        self.assertIn("aspect ratio", reason)


class TestWatermarkKeyword(unittest.TestCase):
    def test_matches_case_insensitively(self):
        self.assertTrue(has_watermark_keyword("Photo via SHUTTERSTOCK preview", ["shutterstock"]))

    def test_no_match_on_clean_title(self):
        self.assertFalse(has_watermark_keyword("a candlelit dinner table", ["shutterstock", "getty"]))

    def test_keyword_check_triggers_hard_reject(self):
        # The keyword list itself lives in config.default.yaml, not in the
        # HardRejectConfig dataclass default - supply one explicitly here.
        config = HardRejectConfig(watermark_keywords=["getty"])
        info = _make_info(1920, 1000, seed=4)
        reason = hard_reject_reason(info, "Getty Images stock photo", config, [])
        self.assertIsNotNone(reason)
        self.assertIn("watermark keyword", reason)


class TestWatermarkBandHeuristic(unittest.TestCase):
    def test_uniform_noise_does_not_trigger(self):
        rng = np.random.RandomState(5)
        gray = rng.randint(0, 256, size=(1000, 1920), dtype=np.uint8)
        self.assertFalse(has_watermark_band(gray, multiplier=2.5))

    def test_dense_band_triggers(self):
        gray = np.full((1000, 1920), 110, dtype=np.uint8)  # flat, low-edge background
        # Punch a dense high-contrast checkerboard band into the middle,
        # simulating a text/logo watermark strip. Blocky (10px) squares so
        # Canny's blur doesn't average them away like single-pixel noise would.
        ys, xs = np.indices((200, 1920))
        checker = (((ys // 10) + (xs // 10)) % 2) * 255
        gray[400:600, :] = checker.astype(np.uint8)
        self.assertTrue(has_watermark_band(gray, multiplier=2.5))


class TestDuplicateDetection(unittest.TestCase):
    def test_identical_image_is_flagged_as_duplicate(self):
        config = HardRejectConfig()
        info_a = _make_info(1920, 1000, seed=7)
        info_b = _make_info(1920, 1000, gray=info_a.gray.copy())
        reason = hard_reject_reason(info_b, "a photo", config, [info_a.phash])
        self.assertIsNotNone(reason)
        self.assertIn("duplicate", reason)

    def test_distinct_images_are_not_flagged(self):
        config = HardRejectConfig()
        info_a = _make_info(1920, 1000, seed=8)
        info_b = _make_info(1920, 1000, seed=9)
        reason = hard_reject_reason(info_b, "a photo", config, [info_a.phash])
        self.assertIsNone(reason)


class TestSharpness(unittest.TestCase):
    def test_uniform_image_has_near_zero_variance(self):
        flat = np.full((500, 500), 128, dtype=np.uint8)
        self.assertAlmostEqual(sharpness_variance(flat), 0.0, places=3)

    def test_noisy_image_has_higher_variance_than_flat(self):
        rng = np.random.RandomState(10)
        noisy = rng.randint(0, 256, size=(500, 500), dtype=np.uint8)
        flat = np.full((500, 500), 128, dtype=np.uint8)
        self.assertGreater(sharpness_variance(noisy), sharpness_variance(flat))


class TestScoringMath(unittest.TestCase):
    def test_resolution_score_caps_at_one(self):
        self.assertEqual(resolution_score(7680, 3840), 1.0)

    def test_resolution_score_scales_linearly_below_reference(self):
        self.assertAlmostEqual(resolution_score(1920, 3840), 0.5)

    def test_sharpness_score_caps_at_one(self):
        self.assertEqual(sharpness_score(10000, 800), 1.0)

    def test_combine_scores_uses_weights(self):
        weights = ScoringWeights(resolution=0.5, sharpness=0.25, caption_similarity=0.25)
        score = combine_scores(1.0, 0.0, 0.0, weights)
        self.assertAlmostEqual(score, 0.5)


if __name__ == "__main__":
    unittest.main()
