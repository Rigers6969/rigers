"""Tests for web_server.py's /api/stats endpoint using Flask's test client.
Mocks analytics.py's fetch functions - no real credentials or network
needed. Also confirms the static frontend files are actually served."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import web_server  # noqa: E402
from analytics import StatsFetchError  # noqa: E402


class TestApiStats(unittest.TestCase):
    def setUp(self):
        self.client = web_server.app.test_client()
        # Isolate these tests from any real config.json that might exist on
        # disk (e.g. one a developer created locally) - they test the
        # env-var fallback path specifically.
        self._original_config_path = web_server.CONFIG_PATH
        web_server.CONFIG_PATH = Path("/nonexistent/config.json")

    def tearDown(self):
        web_server.CONFIG_PATH = self._original_config_path

    @patch.dict("os.environ", {}, clear=True)
    def test_no_credentials_configured(self):
        resp = self.client.get("/api/stats")
        data = resp.get_json()
        self.assertIsNone(data["youtube"])
        self.assertTrue(any("YouTube not configured" in e for e in data["errors"]))

    def test_unexpected_config_error_still_returns_json_not_html(self):
        # Regression: api_stats() used to only catch RuntimeError around
        # load_config(), so any other exception type (e.g. a real-world
        # UnicodeDecodeError from a BOM'd config.json) fell through
        # uncaught and Flask returned its default HTML error page. The
        # frontend's fetch() then failed with a confusing
        # "Unexpected token '<'" JSON-parse error instead of a real message.
        with patch("web_server.load_config", side_effect=ValueError("boom")):
            resp = self.client.get("/api/stats")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content_type, "application/json")
        data = resp.get_json()
        self.assertTrue(any("boom" in e for e in data["errors"]))

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

    @patch.dict("os.environ", {"YOUTUBE_CHANNEL_ID": "UC123", "YOUTUBE_API_KEY": "bad"}, clear=True)
    @patch("web_server.fetch_youtube_stats")
    def test_youtube_error_reported_not_raised(self, mock_fetch):
        mock_fetch.side_effect = StatsFetchError("API key not valid")
        resp = self.client.get("/api/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsNone(data["youtube"])
        self.assertTrue(any("API key not valid" in e for e in data["errors"]))


class TestLoadConfig(unittest.TestCase):
    def setUp(self):
        self._original_config_path = web_server.CONFIG_PATH

    def tearDown(self):
        web_server.CONFIG_PATH = self._original_config_path

    @patch.dict("os.environ", {}, clear=True)
    def test_reads_values_from_config_file(self):
        with tempfile.TemporaryDirectory() as d:
            config_path = Path(d) / "config.json"
            config_path.write_text(json.dumps({
                "YOUTUBE_CHANNEL_ID": "UC123",
                "YOUTUBE_API_KEY": "key123",
                "IG_USER_ID": "17841",
                "IG_ACCESS_TOKEN": "tok123",
            }))
            web_server.CONFIG_PATH = config_path

            config = web_server.load_config()

            self.assertEqual(config["YOUTUBE_CHANNEL_ID"], "UC123")
            self.assertEqual(config["YOUTUBE_API_KEY"], "key123")

    @patch.dict("os.environ", {}, clear=True)
    def test_strips_whitespace_from_file_values(self):
        # A trailing newline/space from copy-pasting into the file is a
        # common, silent source of "invalid credentials" - it must not
        # survive into the value actually sent to the API.
        with tempfile.TemporaryDirectory() as d:
            config_path = Path(d) / "config.json"
            config_path.write_text(json.dumps({"YOUTUBE_API_KEY": "  key123\n"}))
            web_server.CONFIG_PATH = config_path

            config = web_server.load_config()

            self.assertEqual(config["YOUTUBE_API_KEY"], "key123")

    @patch.dict("os.environ", {"YOUTUBE_CHANNEL_ID": "UCfromenv"}, clear=True)
    def test_falls_back_to_env_var_when_missing_from_file(self):
        with tempfile.TemporaryDirectory() as d:
            config_path = Path(d) / "config.json"
            config_path.write_text(json.dumps({"YOUTUBE_API_KEY": "key123"}))
            web_server.CONFIG_PATH = config_path

            config = web_server.load_config()

            self.assertEqual(config["YOUTUBE_CHANNEL_ID"], "UCfromenv")
            self.assertEqual(config["YOUTUBE_API_KEY"], "key123")

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_file_falls_back_entirely_to_env(self):
        web_server.CONFIG_PATH = Path("/nonexistent/config.json")
        config = web_server.load_config()
        self.assertEqual(config["YOUTUBE_CHANNEL_ID"], "")

    @patch.dict("os.environ", {}, clear=True)
    def test_invalid_json_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as d:
            config_path = Path(d) / "config.json"
            config_path.write_text("{not valid json")
            web_server.CONFIG_PATH = config_path

            with self.assertRaises(RuntimeError) as ctx:
                web_server.load_config()
            self.assertIn("not valid JSON", str(ctx.exception))

    @patch.dict("os.environ", {}, clear=True)
    def test_utf8_bom_does_not_break_parsing(self):
        # Regression: a user's config.json (written via PowerShell's
        # Set-Content, a common source of this on Windows) had a byte-order
        # mark. Plain utf-8 decoding raises UnicodeDecodeError on that,
        # which wasn't being caught - it fell through as an unhandled
        # exception, and Flask returned its default HTML error page instead
        # of JSON, breaking the frontend's fetch() with a confusing
        # "Unexpected token '<'" parse error instead of a real message.
        with tempfile.TemporaryDirectory() as d:
            config_path = Path(d) / "config.json"
            content = json.dumps({"YOUTUBE_CHANNEL_ID": "UC123", "YOUTUBE_API_KEY": "key123"})
            config_path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))  # UTF-8 BOM prefix
            web_server.CONFIG_PATH = config_path

            config = web_server.load_config()

            self.assertEqual(config["YOUTUBE_CHANNEL_ID"], "UC123")

    @patch.dict("os.environ", {}, clear=True)
    def test_non_object_json_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as d:
            config_path = Path(d) / "config.json"
            config_path.write_text("[1, 2, 3]")
            web_server.CONFIG_PATH = config_path

            with self.assertRaises(RuntimeError) as ctx:
                web_server.load_config()
            self.assertIn("JSON object", str(ctx.exception))


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
