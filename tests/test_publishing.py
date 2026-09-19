"""Tests for the YouTube/Instagram publishing helpers.

These mock the network/SDK boundaries (requests, googleapiclient) so they
run offline - they verify the request shapes and control flow are correct,
which is what's actually reviewable without real OAuth credentials or a
live Instagram Business account.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from publishing import post_to_instagram, upload_to_youtube  # noqa: E402


class TestUploadToYoutube(unittest.TestCase):
    def test_missing_video_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            upload_to_youtube(Path("/nonexistent/video.mp4"), "t", "d")

    def test_missing_client_secret_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as d:
            video_path = Path(d) / "clip.mp4"
            video_path.write_bytes(b"fake video bytes")
            with self.assertRaises(FileNotFoundError) as ctx:
                upload_to_youtube(
                    video_path, "Title", "Description",
                    client_secret_path=str(Path(d) / "missing_client_secret.json"),
                    token_path=str(Path(d) / "missing_token.json"),
                )
            self.assertIn("client secret", str(ctx.exception))

    def test_uses_cached_valid_token_and_returns_video_id(self):
        with tempfile.TemporaryDirectory() as d:
            video_path = Path(d) / "clip.mp4"
            video_path.write_bytes(b"fake video bytes")
            token_path = Path(d) / "token.json"
            token_path.write_text("{}")

            fake_creds = MagicMock(valid=True)
            fake_creds.to_json.return_value = "{}"

            with patch(
                "google.oauth2.credentials.Credentials.from_authorized_user_file",
                return_value=fake_creds,
            ), patch("googleapiclient.discovery.build") as mock_build, patch(
                "googleapiclient.http.MediaFileUpload"
            ):
                fake_request = MagicMock()
                fake_request.next_chunk.return_value = (None, {"id": "abc123"})
                mock_youtube = MagicMock()
                mock_youtube.videos.return_value.insert.return_value = fake_request
                mock_build.return_value = mock_youtube

                video_id = upload_to_youtube(
                    video_path, "Title", "Description", tags=["a", "b"],
                    client_secret_path=str(Path(d) / "client_secret.json"),
                    token_path=str(token_path),
                )

            self.assertEqual(video_id, "abc123")
            _, kwargs = mock_youtube.videos.return_value.insert.call_args
            self.assertEqual(kwargs["body"]["snippet"]["title"], "Title")
            self.assertEqual(kwargs["body"]["status"]["privacyStatus"], "private")


class TestPostToInstagram(unittest.TestCase):
    @patch("publishing.time.sleep", return_value=None)
    @patch("publishing.requests.get")
    @patch("publishing.requests.post")
    def test_full_publish_flow(self, mock_post, mock_get, _mock_sleep):
        create_response = MagicMock()
        create_response.json.return_value = {"id": "creation123"}
        create_response.raise_for_status.return_value = None

        publish_response = MagicMock()
        publish_response.json.return_value = {"id": "media456"}
        publish_response.raise_for_status.return_value = None

        mock_post.side_effect = [create_response, publish_response]

        status_response = MagicMock()
        status_response.json.return_value = {"status_code": "FINISHED"}
        status_response.raise_for_status.return_value = None
        mock_get.return_value = status_response

        media_id = post_to_instagram(
            caption="Check this out",
            access_token="token",
            ig_user_id="17841400000000000",
            video_public_url="https://example.com/clip.mp4",
        )

        self.assertEqual(media_id, "media456")
        create_call = mock_post.call_args_list[0]
        self.assertIn("/media", create_call.args[0])
        self.assertEqual(create_call.kwargs["data"]["media_type"], "REELS")

    @patch("publishing.requests.get")
    @patch("publishing.requests.post")
    def test_processing_error_raises(self, mock_post, mock_get):
        create_response = MagicMock()
        create_response.json.return_value = {"id": "creation123"}
        create_response.raise_for_status.return_value = None
        mock_post.return_value = create_response

        status_response = MagicMock()
        status_response.json.return_value = {"status_code": "ERROR"}
        status_response.raise_for_status.return_value = None
        mock_get.return_value = status_response

        with self.assertRaises(RuntimeError):
            post_to_instagram(
                caption="x", access_token="t", ig_user_id="1",
                video_public_url="https://example.com/c.mp4",
            )


if __name__ == "__main__":
    unittest.main()
