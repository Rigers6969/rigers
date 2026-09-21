"""Psychology Voiceover Generator - standalone companion app for The Wayne Factory.

Deliberately a SEPARATE app/process, same as channel_agent.py. Run it on its
own:

    streamlit run voice_generator.py --server.port 8503

It writes a long-form (default ~10,000 word) spoken-word script on a
psychology topic using the same dual-engine pattern as branding.py (Ollama
local or Claude API), then narrates it in a British male voice using
Microsoft Edge's free neural TTS (via the `edge-tts` package - no API key
needed) and stitches the resulting audio parts into a single file with
ffmpeg, since a script this long has to be synthesized in chunks.
"""
from __future__ import annotations

import env_config  # noqa: F401  (loads .env before any os.environ.get default below)

import asyncio
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import streamlit as st

import ui_theme

APP_DIR = Path(__file__).resolve().parent
VOICEOVER_OUTPUT_DIR = APP_DIR / "voiceover_output"

DEFAULT_TARGET_WORDS = 10_000
MIN_TARGET_WORDS = 500
MAX_TARGET_WORDS = 20_000
WORDS_PER_SECTION = 900
MAX_SECTIONS = 40
TTS_MAX_CHARS = 3000

# British male neural voices offered by Microsoft Edge's TTS service.
UK_MALE_VOICES = {
    "Ryan (British, male)": "en-GB-RyanNeural",
    "Thomas (British, male)": "en-GB-ThomasNeural",
}

ProgressCB = Callable[[str], None]


class ScriptGenerationError(RuntimeError):
    pass


class VoiceSynthesisError(RuntimeError):
    pass


@dataclass
class VoiceoverResult:
    script: str
    word_count: int
    audio_path: Path


def _word_count(text: str) -> int:
    return len(text.split())


# --------------------------------------------------------------------------
# Script writing - same pattern as BaseBrandGenerator/BaseViralAnalyzer:
# subclasses implement _call_model only. A 10,000-word script is far beyond
# any single LLM call's reliable output length, so the script is planned as
# an outline and then written section by section, each one continuing from
# the tail of the last, until the target word count is reached.
# --------------------------------------------------------------------------

OUTLINE_PROMPT_TEMPLATE = """You are a psychology educator planning a long-form spoken-word script for a voiceover video.

Topic: "{topic}"

Produce a numbered outline of exactly {num_sections} sections that together give a thorough, well-organized tour of this topic for a general audience - covering distinct sub-themes, concepts, or angles with a logical progression (no repetition between sections).

Respond with ONLY the outline, one short section title per line, formatted as "1. Title", "2. Title", etc. No other prose.
"""

SECTION_PROMPT_TEMPLATE = """You are writing section {index} of {total} of a long-form spoken-word script about psychology.

Topic: "{topic}"

Full outline:
{outline}

This section's focus: "{section_title}"

Previously written script (tail end, for continuity - do not repeat or summarize it, just continue naturally from it):
{tail}

Write this section as natural spoken narration for a voiceover: plain prose only, no headings, no stage directions, no markdown, no bullet points. Use a warm, clear, explanatory tone aimed at a general audience. Aim for about {words_per_section} words. Continue directly from where the previous section left off - do not reintroduce the overall topic or greet the listener again unless this is section 1.
"""


class BaseScriptWriter:
    def _call_model(self, prompt: str, max_tokens: int) -> str:
        raise NotImplementedError

    def generate_outline(self, topic: str, num_sections: int) -> list[str]:
        prompt = OUTLINE_PROMPT_TEMPLATE.format(topic=topic, num_sections=num_sections)
        raw = self._call_model(prompt, max_tokens=1024)
        lines = [re.sub(r"^\s*\d+[\.\)]\s*", "", line).strip() for line in raw.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            raise ScriptGenerationError("Model returned no outline sections")
        return lines[:num_sections]

    def generate_script(
        self, topic: str, target_words: int = DEFAULT_TARGET_WORDS, progress: Optional[ProgressCB] = None
    ) -> str:
        """Writes a spoken-word psychology script of roughly `target_words` words
        on `topic`, section by section, and returns the joined text."""
        if not topic.strip():
            raise ValueError("topic must not be empty")
        if target_words <= 0:
            raise ValueError("target_words must be positive")

        num_sections = max(1, min(MAX_SECTIONS, round(target_words / WORDS_PER_SECTION)))
        if progress:
            progress(f"Planning {num_sections} sections...")
        outline = self.generate_outline(topic, num_sections)
        outline_text = "\n".join(f"{i + 1}. {title}" for i, title in enumerate(outline))

        sections: list[str] = []
        total_words = 0
        section_titles = list(outline)
        index = 0
        # Walk the outline first; if it runs out before the target word count
        # is hit, keep asking for further related sections rather than
        # stopping short - the outline is a plan, not a hard cap.
        while total_words < target_words and index < MAX_SECTIONS * 2:
            index += 1
            if index <= len(section_titles):
                section_title = section_titles[index - 1]
            else:
                section_title = f"A further, related psychological insight about {topic} not yet covered"

            tail = " ".join(sections[-1].split()[-120:]) if sections else "(this is the start of the script)"
            prompt = SECTION_PROMPT_TEMPLATE.format(
                index=index,
                total=max(index, len(section_titles)),
                topic=topic,
                outline=outline_text,
                section_title=section_title,
                tail=tail,
                words_per_section=WORDS_PER_SECTION,
            )
            if progress:
                progress(f"Writing section {index} ({total_words}/{target_words} words so far)...")
            text = self._call_model(prompt, max_tokens=2048).strip()
            if not text:
                raise ScriptGenerationError(f"Model returned an empty section {index}")
            sections.append(text)
            total_words += _word_count(text)

        return "\n\n".join(sections)


class OllamaScriptWriter(BaseScriptWriter):
    def __init__(self, model: str = "llama3", host: str = "http://localhost:11434", request_timeout: float = 600):
        self.model = model
        self.host = host.rstrip("/")
        self.request_timeout = request_timeout

    def _call_model(self, prompt: str, max_tokens: int) -> str:
        import requests

        resp = requests.post(
            f"{self.host}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": max_tokens},
            },
            timeout=self.request_timeout,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")


class ClaudeScriptWriter(BaseScriptWriter):
    def __init__(self, api_key: str, model: str = "claude-sonnet-5"):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def _call_model(self, prompt: str, max_tokens: int) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return next(block.text for block in response.content if block.type == "text")


# --------------------------------------------------------------------------
# Text-to-speech - Microsoft Edge's free neural voices via edge-tts. No
# account or API key needed, just outbound internet access. The service has
# no documented hard length limit, but a single multi-minute request is
# fragile in practice, so the script is split into chunks, each synthesized
# separately, then stitched into one file with ffmpeg (already a hard
# dependency of this project - see empire.py).
# --------------------------------------------------------------------------

def _split_for_tts(text: str, max_chars: int = TTS_MAX_CHARS) -> list[str]:
    """Splits `text` into chunks no longer than `max_chars`, breaking on
    paragraph boundaries where possible and falling back to sentence
    boundaries for any single paragraph that's too long on its own."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(para) <= max_chars:
            current = para
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", para):
            candidate = f"{current} {sentence}".strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = sentence
    if current:
        chunks.append(current)
    return chunks


async def _synthesize_chunk(text: str, voice: str, out_path: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_path))


def synthesize_speech(
    text: str, voice: str, output_path: Path, progress: Optional[ProgressCB] = None
) -> Path:
    """Narrates `text` in `voice` (an edge-tts voice id, e.g. "en-GB-RyanNeural")
    and writes the combined audio to `output_path`. Requires ffmpeg on PATH
    when the script is long enough to need more than one chunk."""
    if not text.strip():
        raise VoiceSynthesisError("No script text to synthesize")

    chunks = _split_for_tts(text)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        part_paths = []
        for i, chunk in enumerate(chunks, start=1):
            if progress:
                progress(f"Synthesizing audio part {i}/{len(chunks)}...")
            part_path = tmp_dir / f"part_{i:04d}.mp3"
            try:
                asyncio.run(_synthesize_chunk(chunk, voice, part_path))
            except Exception as exc:
                raise VoiceSynthesisError(f"edge-tts failed on part {i}/{len(chunks)}: {exc}") from exc
            part_paths.append(part_path)

        if len(part_paths) == 1:
            part_paths[0].replace(output_path)
            return output_path

        if progress:
            progress("Combining audio parts with ffmpeg...")
        concat_list = tmp_dir / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in part_paths), encoding="utf-8"
        )
        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(output_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise VoiceSynthesisError(f"ffmpeg failed to combine audio parts: {result.stderr[-2000:]}")

    return output_path


# --------------------------------------------------------------------------
# Streamlit UI
# --------------------------------------------------------------------------

def render_voiceover_tab():
    """Renders the full voiceover UI (sidebar settings + main content).
    Factored out of main() so studio.py can embed this as one tab without
    duplicating the logic - main() below is just this plus the standalone
    page chrome (page config, splash gate, title)."""
    with st.sidebar:
        ui_theme.render_clock_widget()
        st.header("Voice settings")
        voice_label = st.selectbox("Narrator voice", list(UK_MALE_VOICES.keys()))
        voice_id = UK_MALE_VOICES[voice_label]

    script_source = st.radio(
        "Script source", ["Paste my own script", "Generate one with AI"], horizontal=True
    )

    if script_source == "Paste my own script":
        pasted = st.text_area(
            "Paste your script here", height=300, key="voiceover_pasted_script",
            placeholder="Paste the full script text you want narrated...",
        )
        if st.button("Use this script", type="primary", disabled=not pasted.strip()):
            st.session_state["voiceover_script"] = pasted.strip()
            st.session_state.pop("voiceover_audio_path", None)
        topic = "voiceover"
    else:
        with st.sidebar:
            st.header("Script settings")
            engine = st.radio("Script engine", ["Ollama (local)", "Claude API"])
            if engine == "Ollama (local)":
                model = st.selectbox("Ollama model", ["llama3", "phi3"])
                ollama_host = st.text_input("Ollama host", value=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
                anthropic_key = ""
            else:
                model = st.selectbox("Claude model", ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5"])
                anthropic_key = st.text_input(
                    "Anthropic API key", type="password", value=os.environ.get("ANTHROPIC_API_KEY", "")
                )
                ollama_host = ""

        topic = st.text_input(
            "Psychology topic", value="Cognitive biases and how they quietly shape everyday decisions"
        )
        target_words = st.number_input(
            "Target word count",
            min_value=MIN_TARGET_WORDS,
            max_value=MAX_TARGET_WORDS,
            value=DEFAULT_TARGET_WORDS,
            step=500,
            help="~10,000 words narrates to roughly an hour of audio at a natural speaking pace.",
        )

        if st.button("Generate script", type="primary", disabled=not topic.strip()):
            try:
                if engine == "Ollama (local)":
                    writer = OllamaScriptWriter(model=model, host=ollama_host)
                else:
                    if not anthropic_key:
                        raise ScriptGenerationError("Enter an Anthropic API key in the sidebar first.")
                    writer = ClaudeScriptWriter(api_key=anthropic_key, model=model)

                status = st.empty()
                script = writer.generate_script(
                    topic, target_words=int(target_words), progress=lambda msg: status.info(msg)
                )
                status.empty()
                st.session_state["voiceover_script"] = script
                st.session_state.pop("voiceover_audio_path", None)
            except Exception as exc:
                st.error(str(exc))

    script = st.session_state.get("voiceover_script")
    if script:
        st.subheader(f"Script ({_word_count(script):,} words)")
        st.text_area("Script to narrate", value=script, height=300, key="voiceover_script_display")

        if st.button("Generate voiceover", type="primary"):
            try:
                VOICEOVER_OUTPUT_DIR.mkdir(exist_ok=True)
                out_name = re.sub(r"[^\w\s-]", "", topic).strip().lower().replace(" ", "-")[:60] or "voiceover"
                out_path = VOICEOVER_OUTPUT_DIR / f"{out_name}.mp3"

                status = st.empty()
                synthesize_speech(script, voice_id, out_path, progress=lambda msg: status.info(msg))
                status.empty()
                st.session_state["voiceover_audio_path"] = str(out_path)
            except Exception as exc:
                st.error(str(exc))

        audio_path = st.session_state.get("voiceover_audio_path")
        if audio_path and Path(audio_path).exists():
            st.audio(audio_path)
            with open(audio_path, "rb") as f:
                st.download_button("Download voiceover (.mp3)", f.read(), file_name=Path(audio_path).name)


def main():
    st.set_page_config(page_title="Psychology Voiceover Generator", page_icon=":studio_microphone:", layout="wide")

    if not ui_theme.show_splash_gate(app_name="Batman"):
        return

    st.title("Psychology Voiceover Generator")
    st.caption(
        "Writes a long-form psychology script and narrates it in a British male voice. "
        "Runs as its own app, same pattern as channel_agent.py."
    )

    render_voiceover_tab()


if __name__ == "__main__":
    main()
