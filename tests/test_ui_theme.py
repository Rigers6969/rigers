"""Tests for ui_theme.py's testable logic.

Most of ui_theme.py is Streamlit/HTML rendering, which needs a live
Streamlit script run context to exercise meaningfully. The one piece of
real logic - detecting and embedding a user-supplied background image - is
fully unit-testable without that, so that's what's covered here.
"""
import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ui_theme  # noqa: E402


class TestBackgroundImageCss(unittest.TestCase):
    def setUp(self):
        self._original_path = ui_theme.CUSTOM_BACKGROUND_PATH

    def tearDown(self):
        ui_theme.CUSTOM_BACKGROUND_PATH = self._original_path

    def test_no_file_returns_empty_string(self):
        ui_theme.CUSTOM_BACKGROUND_PATH = Path("/nonexistent/background.jpg")
        self.assertEqual(ui_theme._background_image_css(), "")

    def test_existing_file_embeds_as_base64_data_uri(self, ):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            fake_image_bytes = b"\xff\xd8\xff\xe0fake jpeg bytes"
            path = Path(d) / "background.jpg"
            path.write_bytes(fake_image_bytes)
            ui_theme.CUSTOM_BACKGROUND_PATH = path

            css = ui_theme._background_image_css()
            self.assertIn("background-image: url('data:image/jpeg;base64,", css)
            expected_b64 = base64.b64encode(fake_image_bytes).decode("ascii")
            self.assertIn(expected_b64, css)


if __name__ == "__main__":
    unittest.main()
