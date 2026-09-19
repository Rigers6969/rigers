"""Unit tests for The Wayne Factory's analysis and slicing logic.

These exercise the code paths that were previously failing silently
("no valid viral moments") by mocking LLM responses directly - no
network, no Ollama, no Anthropic key required. Requires ffmpeg on PATH
for the slicing tests (they self-skip if it's missing).
"""
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import empire  # noqa: E402
from empire import (  # noqa: E402
    BaseViralAnalyzer,
    ClipCandidate,
    OllamaViralAnalyzer,
    extract_json_items,
    save_transcript,
    slice_clip,
    slugify,
)

SEGMENTS = [
    {"start": 0.0, "end": 5.0, "text": "Welcome back to the channel."},
    {"start": 5.0, "end": 40.0, "text": "Here's a wild story about the time I lost everything."},
    {"start": 40.0, "end": 90.0, "text": "And that is how I rebuilt from scratch."},
    {"start": 90.0, "end": 95.0, "text": "Thanks for watching, see you next time."},
]


class ScriptedAnalyzer(BaseViralAnalyzer):
    """Analyzer whose _call_model returns a canned sequence of responses."""

    def __init__(self, responses, **kwargs):
        super().__init__(**kwargs)
        self._responses = list(responses)

    def _call_model(self, prompt: str) -> str:
        if not self._responses:
            return "[]"
        return self._responses.pop(0)


class TestExtractJsonItems(unittest.TestCase):
    def test_bare_array(self):
        self.assertEqual(extract_json_items('[{"start": 1, "end": 2}]'), [{"start": 1, "end": 2}])

    def test_markdown_fenced(self):
        raw = '```json\n[{"start": 1, "end": 2}]\n```'
        self.assertEqual(extract_json_items(raw), [{"start": 1, "end": 2}])

    def test_prose_wrapped(self):
        raw = 'Sure, here are the clips:\n[{"start": 1, "end": 2}]\nHope that helps!'
        self.assertEqual(extract_json_items(raw), [{"start": 1, "end": 2}])

    def test_object_wrapping_array(self):
        raw = '{"clips": [{"start": 1, "end": 2}]}'
        self.assertEqual(extract_json_items(raw), [{"start": 1, "end": 2}])

    def test_multi_key_object_with_nested_list_is_not_unwrapped(self):
        # Regression: a multi-field object (e.g. a brand kit with several
        # scalar fields plus a "hashtags" list) must come back as the object
        # itself, not have its unrelated nested list returned instead.
        raw = json.dumps({"title": "x", "hook": "y", "tags": ["#a", "#b"]})
        self.assertEqual(extract_json_items(raw), [{"title": "x", "hook": "y", "tags": ["#a", "#b"]}])

    def test_single_object_no_array(self):
        raw = '{"start": 1, "end": 2}'
        self.assertEqual(extract_json_items(raw), [{"start": 1, "end": 2}])

    def test_trailing_comma_repaired(self):
        raw = '[{"start": 1, "end": 2},]'
        self.assertEqual(extract_json_items(raw), [{"start": 1, "end": 2}])

    def test_empty_array(self):
        self.assertEqual(extract_json_items("[]"), [])

    def test_garbage_returns_none(self):
        self.assertIsNone(extract_json_items("I cannot find any viral moments in this transcript."))

    def test_empty_string_returns_none(self):
        self.assertIsNone(extract_json_items(""))


class TestOllamaTimeout(unittest.TestCase):
    def test_default_timeout_is_generous_not_the_old_180s(self):
        # Regression: a user hit "ReadTimeout ... (read timeout=180)" on a
        # chunk that was still legitimately generating, not stuck - local CPU
        # inference speed varies a lot by hardware/chunk size, so 180s was too
        # tight a default. Assert the default actually changed, not just that
        # the parameter exists (a no-op refactor would still pass a weaker check).
        analyzer = OllamaViralAnalyzer()
        self.assertGreaterEqual(analyzer.request_timeout, 600)

    def test_custom_timeout_is_passed_to_the_http_call(self):
        import unittest.mock as mock

        analyzer = OllamaViralAnalyzer(request_timeout=42)
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"response": "[]"}
            mock_post.return_value.raise_for_status.return_value = None
            analyzer._call_model("some prompt")
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["timeout"], 42)


class TestClipCandidateValidation(unittest.TestCase):
    def test_valid(self):
        c = ClipCandidate(start=10, end=40, title="A story", hook="You won't believe this")
        ok, reason = c.is_valid(15, 90)
        self.assertTrue(ok, reason)

    def test_too_short(self):
        c = ClipCandidate(start=10, end=15, title="A story")
        ok, reason = c.is_valid(15, 90)
        self.assertFalse(ok)
        self.assertIn("below minimum", reason)

    def test_too_long(self):
        c = ClipCandidate(start=0, end=200, title="A story")
        ok, reason = c.is_valid(15, 90)
        self.assertFalse(ok)
        self.assertIn("above maximum", reason)

    def test_end_before_start(self):
        c = ClipCandidate(start=50, end=40, title="A story")
        ok, reason = c.is_valid(15, 90)
        self.assertFalse(ok)

    def test_missing_title_and_hook(self):
        c = ClipCandidate(start=10, end=40)
        ok, reason = c.is_valid(15, 90)
        self.assertFalse(ok)
        self.assertIn("missing", reason)


class TestAnalyzerDiagnostics(unittest.TestCase):
    def test_all_valid_clips_pass_through(self):
        response = json.dumps([
            {"start": 5.0, "end": 40.0, "title": "Lost everything", "hook": "I lost it all", "score": 90},
        ])
        logs = []
        analyzer = ScriptedAnalyzer([response], chunk_seconds=1000, progress_cb=logs.append)
        results = analyzer.analyze(SEGMENTS)
        self.assertEqual(len(results), 1)
        self.assertTrue(any("FINAL: 1 valid clip" in line for line in logs))

    def test_zero_parseable_items_flagged_as_json_problem(self):
        logs = []
        analyzer = ScriptedAnalyzer(
            ["Sorry, I can't help with that."], chunk_seconds=1000, progress_cb=logs.append
        )
        results = analyzer.analyze(SEGMENTS)
        self.assertEqual(results, [])
        self.assertTrue(any("JSON parsing/formatting problem" in line for line in logs))

    def test_items_returned_but_invalid_flagged_as_validation_problem(self):
        # duration way too short for every item -> parses fine, fails validation
        response = json.dumps([
            {"start": 5.0, "end": 6.0, "title": "Too short", "hook": "x", "score": 50},
        ])
        logs = []
        analyzer = ScriptedAnalyzer(
            [response], chunk_seconds=1000, min_duration=15, max_duration=90, progress_cb=logs.append
        )
        results = analyzer.analyze(SEGMENTS)
        self.assertEqual(results, [])
        self.assertTrue(any("duration/format mismatch, not a JSON parsing problem" in line for line in logs))

    def test_model_call_exception_is_caught_and_logged(self):
        class FailingAnalyzer(BaseViralAnalyzer):
            def _call_model(self, prompt):
                raise ConnectionError("connection refused")

        logs = []
        analyzer = FailingAnalyzer(chunk_seconds=1000, progress_cb=logs.append)
        results = analyzer.analyze(SEGMENTS)
        self.assertEqual(results, [])
        self.assertTrue(any("model call failed - ConnectionError: connection refused" in line for line in logs))

    def test_all_chunks_failing_to_call_is_flagged_as_api_problem_not_json_problem(self):
        # Regression test: when every chunk fails at the API-call level (bad key,
        # wrong model, network issue), the FINAL summary must say so - it must not
        # claim a "JSON parsing/formatting problem", since the model was never
        # actually reached.
        class AuthFailingAnalyzer(BaseViralAnalyzer):
            def _call_model(self, prompt):
                raise PermissionError("401 authentication_error: invalid x-api-key")

        logs = []
        analyzer = AuthFailingAnalyzer(chunk_seconds=1000, progress_cb=logs.append)
        results = analyzer.analyze(SEGMENTS)
        self.assertEqual(results, [])
        final_lines = [line for line in logs if line.startswith("FINAL:")]
        self.assertEqual(len(final_lines), 1)
        self.assertIn("API/connection problem", final_lines[0])
        self.assertNotIn("JSON parsing/formatting problem", final_lines[0])


class TestSlugify(unittest.TestCase):
    def test_strips_unsafe_characters(self):
        self.assertEqual(slugify('He said "wow"! / really?'), "he-said-wow-really")

    def test_empty_falls_back(self):
        self.assertEqual(slugify(""), "clip")


class TestSaveTranscript(unittest.TestCase):
    def test_writes_joined_segment_text_to_transcripts_dir(self):
        with tempfile.TemporaryDirectory() as d:
            original_dir = empire.TRANSCRIPTS_DIR
            empire.TRANSCRIPTS_DIR = Path(d)
            try:
                path = save_transcript({"title": "My Video!", "id": "abc123"}, SEGMENTS)
                self.assertTrue(path.exists())
                text = path.read_text(encoding="utf-8")
                self.assertIn("Welcome back to the channel.", text)
                self.assertIn("Thanks for watching, see you next time.", text)
                self.assertIn("abc123", path.name)
            finally:
                empire.TRANSCRIPTS_DIR = original_dir

    def test_skips_empty_segment_text(self):
        with tempfile.TemporaryDirectory() as d:
            original_dir = empire.TRANSCRIPTS_DIR
            empire.TRANSCRIPTS_DIR = Path(d)
            try:
                segments = [{"start": 0, "end": 1, "text": ""}, {"start": 1, "end": 2, "text": "real text"}]
                path = save_transcript({"title": "x", "id": "y"}, segments)
                self.assertEqual(path.read_text(encoding="utf-8"), "real text")
            finally:
                empire.TRANSCRIPTS_DIR = original_dir


class TestTranscribeVideoStderrDeadlock(unittest.TestCase):
    def test_heavy_stderr_output_does_not_hang(self):
        # Regression test for a real deadlock: transcribe_video used to open
        # stdout and stderr as two separate pipes but only drain stdout in its
        # read loop. If the child writes enough to stderr (noisy library
        # warnings, which faster-whisper's dependencies produce plenty of) to
        # fill the OS pipe buffer before stdout closes, the child blocks on
        # its next stderr write and the whole subprocess hangs forever - this
        # is exactly what a user reported as "whisper running for 2 hours at
        # 80%" on a short video with a small model, which should take minutes.
        # A fake worker script that floods stderr past any reasonable pipe
        # buffer size reproduces the exact condition that triggered it.
        with tempfile.TemporaryDirectory() as d:
            fake_worker = Path(d) / "fake_worker.py"
            fake_worker.write_text(
                "import sys, json\n"
                "out_path = sys.argv[3]\n"
                "for i in range(20000):\n"
                "    print('warning: noisy dependency output line %d' % i, file=sys.stderr)\n"
                "print('PROGRESS 1.0/1.0 (100%)', flush=True)\n"
                "with open(out_path, 'w') as f:\n"
                "    json.dump({'language': 'en', 'duration': 1.0, "
                "'segments': [{'start': 0.0, 'end': 1.0, 'text': 'hello'}]}, f)\n"
            )
            original_worker = empire.WHISPER_WORKER
            empire.WHISPER_WORKER = fake_worker
            result = {}
            error = {}

            def run():
                try:
                    result["segments"] = empire.transcribe_video(Path("fake_video.mp4"), "base", lambda msg: None)
                except Exception as exc:  # pragma: no cover - surfaced via assertion below
                    error["exc"] = exc

            try:
                thread = threading.Thread(target=run, daemon=True)
                thread.start()
                thread.join(timeout=15)
                self.assertFalse(thread.is_alive(), "transcribe_video hung - the stderr-pipe deadlock has regressed")
                self.assertNotIn("exc", error, f"transcribe_video raised: {error.get('exc')}")
                self.assertEqual(result.get("segments"), [{"start": 0.0, "end": 1.0, "text": "hello"}])
            finally:
                empire.WHISPER_WORKER = original_worker


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not on PATH")
class TestSliceClip(unittest.TestCase):
    def test_produces_playable_9x16_mp4(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            source = tmp / "source.mp4"
            # Synthetic 16:9 landscape test video, no network required.
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=5",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
                    "-c:v", "libx264", "-c:a", "aac", str(source),
                ],
                check=True, capture_output=True,
            )
            candidate = ClipCandidate(start=1.0, end=3.0, title="Test Clip", hook="hook")
            out_path = tmp / "clip.mp4"
            slice_clip(source, candidate, out_path, video_duration=5.0)

            self.assertTrue(out_path.exists())
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=width,height,duration",
                    "-of", "json", str(out_path),
                ],
                check=True, capture_output=True, text=True,
            )
            info = json.loads(probe.stdout)["streams"][0]
            self.assertEqual(int(info["width"]), 1080)
            self.assertEqual(int(info["height"]), 1920)
            self.assertAlmostEqual(float(info["duration"]), 2.0, delta=0.5)


if __name__ == "__main__":
    unittest.main()
