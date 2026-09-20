"""Tests for shotsource.cache's DiskCache and RateLimiter - no real network
calls, just the caching/timing logic."""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shotsource.cache import DiskCache, RateLimiter  # noqa: E402


class TestDiskCacheJson(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = DiskCache(Path(self.tmp.name), ttl_hours=1)

    def tearDown(self):
        self.tmp.cleanup()

    def test_miss_then_hit(self):
        key = DiskCache.key_for("http://example.com", "{}")
        self.assertIsNone(self.cache.get_json(key))
        self.cache.put_json(key, {"hello": "world"})
        self.assertEqual(self.cache.get_json(key), {"hello": "world"})

    def test_different_params_produce_different_keys(self):
        key_a = DiskCache.key_for("http://example.com", '{"q": "a"}')
        key_b = DiskCache.key_for("http://example.com", '{"q": "b"}')
        self.assertNotEqual(key_a, key_b)

    def test_expired_entry_is_treated_as_a_miss(self):
        cache = DiskCache(Path(self.tmp.name), ttl_hours=0.0000001)  # effectively instant expiry
        key = DiskCache.key_for("http://example.com", "{}")
        cache.put_json(key, {"a": 1})
        time.sleep(0.05)
        self.assertIsNone(cache.get_json(key))

    def test_image_path_is_stable_for_same_url(self):
        path_a = self.cache.image_path_for("http://example.com/photo.jpg")
        path_b = self.cache.image_path_for("http://example.com/photo.jpg")
        self.assertEqual(path_a, path_b)

    def test_image_path_differs_for_different_urls(self):
        path_a = self.cache.image_path_for("http://example.com/a.jpg")
        path_b = self.cache.image_path_for("http://example.com/b.jpg")
        self.assertNotEqual(path_a, path_b)


class TestRateLimiter(unittest.TestCase):
    def test_zero_rpm_means_no_wait(self):
        limiter = RateLimiter(0)
        start = time.monotonic()
        limiter.wait()
        limiter.wait()
        self.assertLess(time.monotonic() - start, 0.05)

    def test_enforces_minimum_interval_between_calls(self):
        # 600 requests/minute = 100ms minimum interval - small enough to
        # keep the test fast but large enough to measure reliably.
        limiter = RateLimiter(600)
        limiter.wait()
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, 0.08)


if __name__ == "__main__":
    unittest.main()
