"""Tests for the psychology voiceover script writer and TTS text splitting.

Fully offline - no network, no Ollama, no Anthropic key, no ffmpeg required.
The LLM call is scripted, same pattern as tests/test_branding.py.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voice_generator import (  # noqa: E402
    BaseScriptWriter,
    ScriptGenerationError,
    UK_MALE_VOICES,
    _split_for_tts,
    _word_count,
)


class ScriptedWriter(BaseScriptWriter):
    """Returns canned outline/section text so the section-writing loop can
    be exercised without a real model. `section_words` controls how many
    words each section's canned text contains, so tests can control exactly
    how many sections the target word count should take."""

    def __init__(self, outline_lines: list[str], section_words: int = 100):
        self.outline_lines = outline_lines
        self.section_words = section_words
        self.prompts: list[str] = []

    def _call_model(self, prompt: str, max_tokens: int) -> str:
        self.prompts.append(prompt)
        if "Produce a numbered outline" in prompt:
            return "\n".join(f"{i + 1}. {line}" for i, line in enumerate(self.outline_lines))
        return " ".join(["word"] * self.section_words)


class TestOutlineParsing(unittest.TestCase):
    def test_parses_numbered_lines(self):
        writer = ScriptedWriter(["Intro to bias", "Anchoring", "Confirmation bias"])
        outline = writer.generate_outline("cognitive biases", 3)
        self.assertEqual(outline, ["Intro to bias", "Anchoring", "Confirmation bias"])

    def test_truncates_to_requested_section_count(self):
        writer = ScriptedWriter(["A", "B", "C", "D"])
        outline = writer.generate_outline("topic", 2)
        self.assertEqual(outline, ["A", "B"])

    def test_empty_outline_raises(self):
        writer = ScriptedWriter([])
        with self.assertRaises(ScriptGenerationError):
            writer.generate_outline("topic", 3)


class TestScriptGeneration(unittest.TestCase):
    def test_stops_once_target_word_count_is_reached(self):
        # 5 sections of 100 words each = 500 words; target 450 should stop
        # after the 5th section pushes the running total past it, not sooner.
        writer = ScriptedWriter(["S1", "S2", "S3", "S4", "S5"], section_words=100)
        script = writer.generate_script("topic", target_words=450)
        self.assertGreaterEqual(_word_count(script), 450)
        self.assertEqual(_word_count(script), 500)

    def test_extends_past_outline_when_target_not_yet_met(self):
        # Only 2 outline sections (200 words) but a 350-word target - the
        # writer must keep generating extra sections beyond the outline.
        writer = ScriptedWriter(["S1", "S2"], section_words=100)
        script = writer.generate_script("topic", target_words=350)
        self.assertGreaterEqual(_word_count(script), 350)

    def test_empty_topic_raises(self):
        writer = ScriptedWriter(["S1"])
        with self.assertRaises(ValueError):
            writer.generate_script("   ", target_words=500)

    def test_non_positive_target_raises(self):
        writer = ScriptedWriter(["S1"])
        with self.assertRaises(ValueError):
            writer.generate_script("topic", target_words=0)

    def test_continuity_prompt_includes_previous_section_tail(self):
        writer = ScriptedWriter(["S1", "S2"], section_words=50)
        writer.generate_script("topic", target_words=100)
        section_prompts = [p for p in writer.prompts if "Previously written script" in p]
        self.assertEqual(len(section_prompts), 2)
        self.assertIn("this is the start of the script", section_prompts[0])
        self.assertIn("word word", section_prompts[1])


class TestTtsSplitting(unittest.TestCase):
    def test_short_text_is_a_single_chunk(self):
        chunks = _split_for_tts("Hello there.\n\nA second paragraph.", max_chars=3000)
        self.assertEqual(chunks, ["Hello there.\n\nA second paragraph."])

    def test_splits_on_paragraph_boundaries_when_over_limit(self):
        para_a = "A" * 50
        para_b = "B" * 50
        chunks = _split_for_tts(f"{para_a}\n\n{para_b}", max_chars=60)
        self.assertEqual(chunks, [para_a, para_b])
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 60)

    def test_splits_oversized_paragraph_on_sentence_boundaries(self):
        long_paragraph = "This is one sentence. " * 20
        chunks = _split_for_tts(long_paragraph, max_chars=100)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 100)
        self.assertEqual(" ".join(chunks).replace("  ", " ").strip(), long_paragraph.strip())

    def test_empty_text_yields_no_chunks(self):
        self.assertEqual(_split_for_tts(""), [])


class TestVoiceOptions(unittest.TestCase):
    def test_all_configured_voices_are_british(self):
        for voice_id in UK_MALE_VOICES.values():
            self.assertTrue(voice_id.startswith("en-GB-"))


if __name__ == "__main__":
    unittest.main()
