"""Tests for analytics.py's stat-fetching. Mocks requests.get so these run
offline - no real API key or access token needed."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analytics import StatsFetchError, fetch_instagram_stats, fetch_youtube_stats  # noqa: E402


class TestFetchYoutubeStats(unittest.TestCase):
    @patch("analytics.requests.get")
    def test_normal_channel(self, mock_get):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "items": [{
                "snippet": {"title": "The Wayne Factory"},
                "statistics": {
                    "subscriberCount": "12345", "viewCount": "6789000",
                    "videoCount": "42", "hiddenSubscriberCount": False,
                },
            }]
        }
        mock_get.return_value = response

        stats = fetch_youtube_stats("UC123", "fake-key")

        self.assertEqual(stats["channel_title"], "The Wayne Factory")
        self.assertEqual(stats["subscriber_count"], 12345)
        self.assertFalse(stats["subscriber_count_hidden"])
        self.assertEqual(stats["view_count"], 6789000)
        self.assertEqual(stats["video_count"], 42)

    @patch("analytics.requests.get")
    def test_hidden_subscriber_count(self, mock_get):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "items": [{
                "snippet": {"title": "Secretive Channel"},
                "statistics": {
                    "viewCount": "100", "videoCount": "1", "hiddenSubscriberCount": True,
                },
            }]
        }
        mock_get.return_value = response

        stats = fetch_youtube_stats("UC123", "fake-key")

        self.assertIsNone(stats["subscriber_count"])
        self.assertTrue(stats["subscriber_count_hidden"])

    @patch("analytics.requests.get")
    def test_no_channel_found_raises(self, mock_get):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"items": []}
        mock_get.return_value = response

        with self.assertRaises(StatsFetchError):
            fetch_youtube_stats("UC_nonexistent", "fake-key")

    @patch("analytics.requests.get")
    def test_api_error_raises(self, mock_get):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"error": {"message": "API key not valid"}}
        mock_get.return_value = response

        with self.assertRaises(StatsFetchError) as ctx:
            fetch_youtube_stats("UC123", "bad-key")
        self.assertIn("API key not valid", str(ctx.exception))


class TestFetchInstagramStats(unittest.TestCase):
    @patch("analytics.requests.get")
    def test_normal_account(self, mock_get):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"username": "waynefactory", "followers_count": 5000, "media_count": 87}
        mock_get.return_value = response

        stats = fetch_instagram_stats("178414000", "fake-token")

        self.assertEqual(stats["username"], "waynefactory")
        self.assertEqual(stats["followers_count"], 5000)
        self.assertEqual(stats["media_count"], 87)

    @patch("analytics.requests.get")
    def test_api_error_raises(self, mock_get):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"error": {"message": "Invalid OAuth access token"}}
        mock_get.return_value = response

        with self.assertRaises(StatsFetchError) as ctx:
            fetch_instagram_stats("178414000", "bad-token")
        self.assertIn("Invalid OAuth access token", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
