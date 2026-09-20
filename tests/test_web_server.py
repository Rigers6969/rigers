"""Tests for web_server.py's /api/stats endpoint using Flask's test client.
Mocks analytics.py's fetch functions - no real credentials or network
needed. Also confirms the static frontend files are actually served."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import web_server  # noqa: E402
from analytics import StatsFetchError  # noqa: E402


class TestApiStats(unittest.TestCase):
    def setUp(self):
        self.client = web_server.app.test_client()

    @patch.dict("os.environ", {}, clear=True)
    def test_no_credentials_configured(self):
        resp = self.client.get("/api/stats")
        data = resp.get_json()
        self.assertIsNone(data["youtube"])
        self.assertIsNone(data["instagram"])
        self.assertTrue(any("YouTube not configured" in e for e in data["errors"]))
        self.assertTrue(any("Instagram not configured" in e for e in data["errors"]))

    @patch.dict("os.environ", {"YOUTUBE_CHANNEL_ID": "UC123", "YOUTUBE_API_KEY": "key"}, clear=True)
    @patch("web_server.fetch_youtube_stats")
    def test_youtube_success(self, mock_fetch):
        mock_fetch.return_value = {
            "channel_title": "Wayne Factory", "subscriber_count": 100,
            "subscriber_count_hidden": False, "view_count": 5000, "video_count": 10,
        }
        resp = self.client.get("/api/stats")
        data = resp.get_json()
        self.assertEqual(data["youtube"]["subscriber_count"], 100)
        self.assertIsNone(data["instagram"])

    @patch.dict("os.environ", {"YOUTUBE_CHANNEL_ID": "UC123", "YOUTUBE_API_KEY": "bad"}, clear=True)
    @patch("web_server.fetch_youtube_stats")
    def test_youtube_error_reported_not_raised(self, mock_fetch):
        mock_fetch.side_effect = StatsFetchError("API key not valid")
        resp = self.client.get("/api/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsNone(data["youtube"])
        self.assertTrue(any("API key not valid" in e for e in data["errors"]))

    @patch.dict("os.environ", {"IG_USER_ID": "17841", "IG_ACCESS_TOKEN": "tok"}, clear=True)
    @patch("web_server.fetch_instagram_stats")
    def test_instagram_success(self, mock_fetch):
        mock_fetch.return_value = {"username": "wayne", "followers_count": 200, "media_count": 5}
        resp = self.client.get("/api/stats")
        data = resp.get_json()
        self.assertEqual(data["instagram"]["followers_count"], 200)
        self.assertIsNone(data["youtube"])


class TestStaticFrontend(unittest.TestCase):
    def setUp(self):
        self.client = web_server.app.test_client()

    def test_index_served(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"<html", resp.data.lower())

    def test_script_js_served(self):
        resp = self.client.get("/script.js")
        self.assertEqual(resp.status_code, 200)

    def test_style_css_served(self):
        resp = self.client.get("/style.css")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
