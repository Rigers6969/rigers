"""Tests for analytics.py's stat-fetching. Mocks requests.get so these run
offline - no real API key or access token needed."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

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

    @patch("analytics.requests.get")
    def test_detailed_error_preferred_over_generic_http_error(self, mock_get):
        # Regression: fetch_youtube_stats used to call resp.raise_for_status()
        # before reading the JSON body, so a 400 with a perfectly descriptive
        # Google error message got replaced by requests' generic "400 Client
        # Error: Bad Request for url: ..." - exactly what a user reported
        # seeing, which told them nothing about the actual cause.
        response = MagicMock()
        response.status_code = 400
        response.json.return_value = {
            "error": {"message": "API key not valid. Please pass a valid API key."}
        }
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "400 Client Error: Bad Request for url: ..."
        )
        mock_get.return_value = response

        with self.assertRaises(StatsFetchError) as ctx:
            fetch_youtube_stats("UC123", "bad-key")
        self.assertIn("API key not valid", str(ctx.exception))
        self.assertNotIn("400 Client Error", str(ctx.exception))


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

    @patch("analytics.requests.get")
    def test_non_json_response_falls_back_to_http_error(self, mock_get):
        # A response that isn't JSON at all (e.g. an HTML error page from a
        # proxy) has no error detail to extract - this should still surface
        # something useful instead of crashing on response.json().
        response = MagicMock()
        response.status_code = 502
        response.json.side_effect = ValueError("not JSON")
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "502 Server Error: Bad Gateway for url: ..."
        )
        mock_get.return_value = response

        with self.assertRaises(requests.exceptions.HTTPError):
            fetch_instagram_stats("178414000", "bad-token")


if __name__ == "__main__":
    unittest.main()
