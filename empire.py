"""The Wayne Factory - turn a long YouTube video into short vertical clips.

Pipeline: yt-dlp download -> Whisper transcription (isolated subprocess)
-> LLM analysis (Ollama local or Claude API) -> ffmpeg slicing to 9:16 clips.

Run with: streamlit run empire.py
Requires ffmpeg on PATH. For the Ollama engine, Ollama must be running
locally (e.g. `ollama serve`) with a model pulled (e.g. `ollama pull llama3`).
For the Claude engine, provide an Anthropic API key.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import streamlit as st

from json_utils import extract_json_items

APP_DIR = Path(__file__).resolve().parent
WHISPER_WORKER = APP_DIR / "_whisper_worker.py"
OUTPUT_DIR = APP_DIR / "output_clips"
TRANSCRIPTS_DIR = APP_DIR / "transcripts"

DEFAULT_MIN_CLIP_SECONDS = 15
DEFAULT_MAX_CLIP_SECONDS = 90
DEFAULT_CHUNK_SECONDS = 600
DEFAULT_CHUNK_OVERLAP_SECONDS = 30

ProgressCB = Callable[[str], None]


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class ClipCandidate:
    start: float
    end: float
    title: str = ""
    hook: str = ""
    score: float = 0.0

    @property
    def duration(self) -> float:
        return self.end - self.start

    def is_valid(self, min_duration: float, max_duration: float) -> tuple[bool, str]:
        if self.end <= self.start:
            return False, f"end ({self.end:.1f}) <= start ({self.start:.1f})"
        dur = self.duration
        if dur < min_duration:
            return False, f"duration {dur:.1f}s below minimum {min_duration:.0f}s"
        if dur > max_duration:
            return False, f"duration {dur:.1f}s above maximum {max_duration:.0f}s"
        if not self.title and not self.hook:
            return False, "missing both title and hook"
        return True, "ok"


def slugify(text: str, max_len: int = 40) -> str:
    text = re.sub(r"[^\w\s-]", "", text or "").strip().lower()
    text = re.sub(r"[-\s]+", "-", text)
    return text[:max_len] or "clip"


VIRAL_PROMPT_TEMPLATE = """You are a viral short-form video editor. Below is a transcript excerpt with timestamps in seconds. The timestamps are ABSOLUTE - measured from the start of the whole video, not from the start of this excerpt.

Find up to 5 moments in this excerpt that would work as standalone vertical short-form clips ({min_dur:.0f} to {max_dur:.0f} seconds long). Look for a strong hook, a self-contained story or point, a surprising or emotional beat, or concrete actionable advice. Skip filler, small talk, and anything that needs earlier context to make sense.

Respond with ONLY a JSON array - no prose, no markdown code fences, no explanation. Each element must be an object with exactly these fields:
- "start": number, absolute start time in seconds
- "end": number, absolute end time in seconds (must be {min_dur:.0f} to {max_dur:.0f} seconds after "start")
- "title": short punchy title, 10 words or fewer
- "hook": the on-screen hook text for the first second of the clip
- "score": number from 0 to 100 rating how viral this moment is

If nothing in this excerpt qualifies, respond with exactly: []

Transcript excerpt:
{transcript}
"""


# --------------------------------------------------------------------------
# Analyzer base class
# --------------------------------------------------------------------------

class BaseViralAnalyzer:
    """Chunks a transcript, prompts an LLM per chunk, and validates results.

    Subclasses only need to implement `_call_model(prompt) -> str`.
    """

    def __init__(
        self,
        min_duration: float = DEFAULT_MIN_CLIP_SECONDS,
        max_duration: float = DEFAULT_MAX_CLIP_SECONDS,
        chunk_seconds: float = DEFAULT_CHUNK_SECONDS,
        chunk_overlap_seconds: float = DEFAULT_CHUNK_OVERLAP_SECONDS,
        progress_cb: Optional[ProgressCB] = None,
    ):
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.chunk_seconds = chunk_seconds
        self.chunk_overlap_seconds = chunk_overlap_seconds
        self.progress_cb = progress_cb or (lambda msg: None)

    def _call_model(self, prompt: str) -> str:
        raise NotImplementedError

    def _chunk_segments(self, segments: list[dict]) -> list[list[dict]]:
        if not segments:
            return []
        chunks: list[list[dict]] = []
        window_start = segments[0]["start"]
        current: list[dict] = []
        for seg in segments:
            current.append(seg)
            if seg["end"] - window_start >= self.chunk_seconds:
                chunks.append(current)
                overlap_from = seg["end"] - self.chunk_overlap_seconds
                current = [s for s in current if s["end"] >= overlap_from]
                window_start = current[0]["start"] if current else seg["end"]
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _format_chunk_text(chunk_segments: list[dict]) -> str:
        return "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text'].strip()}" for s in chunk_segments)

    def _build_prompt(self, chunk_text: str) -> str:
        return VIRAL_PROMPT_TEMPLATE.format(
            min_dur=self.min_duration, max_dur=self.max_duration, transcript=chunk_text
        )

    def analyze(self, segments: list[dict]) -> list[ClipCandidate]:
        chunks = self._chunk_segments(segments)
        n_chunks = len(chunks)
        if n_chunks == 0:
            self.progress_cb("No transcript segments to analyze.")
            return []

        all_valid: list[ClipCandidate] = []
        total_raw_items = 0
        total_call_failures = 0
        total_parse_failures = 0
        rejection_reasons: dict[str, int] = {}

        for i, chunk_segments in enumerate(chunks, start=1):
            prompt = self._build_prompt(self._format_chunk_text(chunk_segments))

            try:
                raw_response = self._call_model(prompt)
            except Exception as exc:
                total_call_failures += 1
                self.progress_cb(
                    f"Chunk {i}/{n_chunks}: model call failed - {type(exc).__name__}: {exc}"
                )
                continue

            items = extract_json_items(raw_response)
            if items is None:
                total_parse_failures += 1
                preview = raw_response[:200].replace("\n", " ")
                self.progress_cb(
                    f"Chunk {i}/{n_chunks}: model returned 0 item(s), 0 passed validation "
                    f"(response was not valid JSON; first 200 chars: {preview!r})"
                )
                continue

            total_raw_items += len(items)
            valid_in_chunk: list[ClipCandidate] = []
            for item in items:
                if not isinstance(item, dict):
                    rejection_reasons["item was not a JSON object"] = (
                        rejection_reasons.get("item was not a JSON object", 0) + 1
                    )
                    continue
                try:
                    candidate = ClipCandidate(
                        start=float(item["start"]),
                        end=float(item["end"]),
                        title=str(item.get("title", ""))[:120],
                        hook=str(item.get("hook", item.get("caption", "")))[:280],
                        score=float(item.get("score", item.get("virality_score", 0)) or 0),
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    reason = f"malformed item ({exc})"
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                    continue

                ok, reason = candidate.is_valid(self.min_duration, self.max_duration)
                if ok:
                    valid_in_chunk.append(candidate)
                else:
                    rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

            all_valid.extend(valid_in_chunk)
            self.progress_cb(
                f"Chunk {i}/{n_chunks}: model returned {len(items)} item(s), "
                f"{len(valid_in_chunk)} passed validation"
            )

        if not all_valid:
            if total_call_failures == n_chunks:
                self.progress_cb(
                    f"FINAL: the model could not be reached/called successfully for any of the "
                    f"{n_chunks} chunk(s) - this is an API/connection problem (bad API key, wrong "
                    "model name, network issue, or an incompatible SDK version), not a JSON or "
                    "duration problem. See the 'model call failed' line(s) above for the exact error."
                )
            elif total_raw_items == 0:
                self.progress_cb(
                    "FINAL: zero parseable items across all chunks - this is a JSON "
                    "parsing/formatting problem (the model isn't returning valid JSON), not a "
                    f"duration/content problem. {total_parse_failures} chunk(s) failed to parse, "
                    f"{total_call_failures} chunk(s) failed to call the model at all."
                )
            else:
                top_reasons = sorted(rejection_reasons.items(), key=lambda kv: -kv[1])[:5]
                reasons_summary = ", ".join(f"{reason} x{count}" for reason, count in top_reasons)
                self.progress_cb(
                    f"FINAL: model returned {total_raw_items} item(s) across {n_chunks} chunk(s) "
                    "but none passed validation - this is a duration/format mismatch, not a JSON "
                    f"parsing problem. Top rejection reasons: {reasons_summary}"
                )
        else:
            self.progress_cb(f"FINAL: {len(all_valid)} valid clip candidate(s) found across {n_chunks} chunk(s).")

        all_valid.sort(key=lambda c: c.score, reverse=True)
        return all_valid


class OllamaViralAnalyzer(BaseViralAnalyzer):
    def __init__(self, model: str = "llama3", host: str = "http://localhost:11434", **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.host = host.rstrip("/")

    def _call_model(self, prompt: str) -> str:
        import requests

        resp = requests.post(
            f"{self.host}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "format": "json",  # forces syntactically valid JSON output
                "stream": False,
                "options": {"temperature": 0.4},
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")


class ClaudeViralAnalyzer(BaseViralAnalyzer):
    """Uses output_config json_schema so the response is guaranteed valid JSON -
    this removes the JSON-parsing failure mode entirely for this engine."""

    OUTPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "clips": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "number"},
                        "end": {"type": "number"},
                        "title": {"type": "string"},
                        "hook": {"type": "string"},
                        "score": {"type": "number"},
                    },
                    "required": ["start", "end", "title", "hook", "score"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["clips"],
        "additionalProperties": False,
    }

    def __init__(self, api_key: str, model: str = "claude-sonnet-5", **kwargs):
        super().__init__(**kwargs)
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def _call_model(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": self.OUTPUT_SCHEMA}},
        )
        return next(block.text for block in response.content if block.type == "text")


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------

def download_video(url: str, output_dir: Path, progress_cb: ProgressCB) -> tuple[Path, dict]:
    import yt_dlp

    output_dir.mkdir(parents=True, exist_ok=True)

    def hook(d):
        if d.get("status") == "downloading":
            pct = (d.get("_percent_str") or "").strip()
            progress_cb(f"Downloading: {pct}")
        elif d.get("status") == "finished":
            progress_cb("Download finished, post-processing...")

    ydl_opts = {
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        raise RuntimeError(f"yt-dlp failed to download '{url}': {exc}") from exc

    video_id = info["id"]
    candidates = sorted(output_dir.glob(f"{video_id}.*"))
    if not candidates:
        raise RuntimeError(f"yt-dlp reported success but no output file was found for id {video_id}")
    mp4_candidates = [p for p in candidates if p.suffix == ".mp4"]
    final_path = mp4_candidates[0] if mp4_candidates else candidates[0]
    return final_path, info


# --------------------------------------------------------------------------
# Transcription (isolated subprocess)
# --------------------------------------------------------------------------

def transcribe_video(video_path: Path, model_size: str, progress_cb: ProgressCB) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="wayne_whisper_") as d:
        out_json = Path(d) / "transcript.json"
        cmd = [sys.executable, str(WHISPER_WORKER), str(video_path), model_size, str(out_json)]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line:
                progress_cb(f"[whisper] {line}")
        proc.wait()
        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"Whisper subprocess failed (exit {proc.returncode}):\n{stderr[-2000:]}")
        with open(out_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["segments"]


def save_transcript(info: dict, segments: list[dict]) -> Path:
    """Persists the full transcript text to TRANSCRIPTS_DIR so channel_agent.py
    can analyze real video content when generating a brand kit - otherwise the
    transcript only lives in a temp dir that's deleted when the pipeline ends."""
    TRANSCRIPTS_DIR.mkdir(exist_ok=True)
    title = info.get("title") or info.get("id") or "video"
    video_id = info.get("id", "")
    out_path = TRANSCRIPTS_DIR / f"{slugify(title)}_{video_id}.txt"
    text = "\n".join(seg["text"].strip() for seg in segments if seg.get("text"))
    out_path.write_text(text, encoding="utf-8")
    return out_path


# --------------------------------------------------------------------------
# Slicing
# --------------------------------------------------------------------------

def slice_clip(source_path: Path, candidate: ClipCandidate, output_path: Path, video_duration: Optional[float] = None):
    start = max(candidate.start, 0.0)
    end = candidate.end
    if video_duration is not None:
        end = min(end, video_duration)
    duration = end - start
    if duration <= 0:
        raise RuntimeError(f"Clip '{candidate.title}' has non-positive duration after clamping to video length")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(source_path),
        "-t", str(duration),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for clip '{candidate.title}':\n{result.stderr[-2000:]}")


# --------------------------------------------------------------------------
# Pipeline orchestration
# --------------------------------------------------------------------------

def run_pipeline(
    url: str,
    engine: str,
    model: str,
    ollama_host: str,
    anthropic_key: str,
    min_dur: float,
    max_dur: float,
    whisper_model_size: str,
    progress_cb: ProgressCB,
) -> list[tuple[ClipCandidate, Path]]:
    with tempfile.TemporaryDirectory(prefix="wayne_factory_") as tmpdir:
        tmp = Path(tmpdir)

        progress_cb("Starting download...")
        video_path, info = download_video(url, tmp, progress_cb)
        video_duration = info.get("duration")
        progress_cb(f"Downloaded: {video_path.name} ({video_duration or '?'}s)")

        progress_cb("Starting transcription (isolated subprocess)...")
        segments = transcribe_video(video_path, whisper_model_size, progress_cb)
        progress_cb(f"Transcription complete: {len(segments)} segment(s)")

        transcript_path = save_transcript(info, segments)
        progress_cb(f"Transcript saved: {transcript_path.name} (for Channel Agent's video analysis)")

        progress_cb(f"Starting analysis with {engine}...")
        if engine == "Ollama (local)":
            analyzer: BaseViralAnalyzer = OllamaViralAnalyzer(
                model=model, host=ollama_host, min_duration=min_dur, max_duration=max_dur, progress_cb=progress_cb
            )
        else:
            analyzer = ClaudeViralAnalyzer(
                api_key=anthropic_key, model=model, min_duration=min_dur, max_duration=max_dur, progress_cb=progress_cb
            )
        candidates = analyzer.analyze(segments)

        if not candidates:
            raise RuntimeError(
                "The AI found no valid viral moments in this transcript. "
                "See the diagnostic log above for the specific cause."
            )

        progress_cb(f"Slicing {len(candidates)} clip(s)...")
        OUTPUT_DIR.mkdir(exist_ok=True)
        results: list[tuple[ClipCandidate, Path]] = []
        for idx, candidate in enumerate(candidates, start=1):
            out_path = OUTPUT_DIR / f"clip_{idx:02d}_{slugify(candidate.title)}.mp4"
            slice_clip(video_path, candidate, out_path, video_duration)
            results.append((candidate, out_path))
            progress_cb(f"Clip {idx}/{len(candidates)} sliced: {out_path.name}")

        return results


# --------------------------------------------------------------------------
# Streamlit UI
# --------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="The Wayne Factory", page_icon=":bat:", layout="wide")
    st.title("The Wayne Factory")
    st.caption("Turn long YouTube videos into short vertical clips for TikTok/Reels/Shorts.")

    with st.sidebar:
        st.header("Settings")
        engine = st.radio("Analysis engine", ["Ollama (local)", "Claude API"])
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

        whisper_model_size = st.selectbox("Whisper model size", ["tiny", "base", "small", "medium"], index=1)

        st.subheader("Clip length")
        min_dur, max_dur = st.slider("Duration range (seconds)", 5, 180, (DEFAULT_MIN_CLIP_SECONDS, DEFAULT_MAX_CLIP_SECONDS))

    url = st.text_input("YouTube URL")
    run_clicked = st.button("Run pipeline", type="primary", disabled=not url)

    log_lines: list[str] = []
    log_area = st.empty()

    def log(msg: str):
        log_lines.append(msg)
        log_area.code("\n".join(log_lines[-300:]))

    if run_clicked:
        if engine == "Claude API" and not anthropic_key:
            st.error("Enter an Anthropic API key to use the Claude engine.")
        else:
            try:
                with st.spinner("Running pipeline..."):
                    clips = run_pipeline(
                        url, engine, model, ollama_host, anthropic_key, min_dur, max_dur, whisper_model_size, log
                    )
                st.session_state["wayne_clips"] = clips
                st.success(f"Done! {len(clips)} clip(s) generated.")
            except Exception as exc:
                st.session_state["wayne_clips"] = []
                st.error(str(exc))

    # Read results from session_state (not a local var) so they survive the
    # rerun triggered by clicking a download button below.
    clips = st.session_state.get("wayne_clips") or []
    for idx, (candidate, path) in enumerate(clips):
        st.video(str(path))
        st.write(f"**{candidate.title}** - score {candidate.score:.0f} - {candidate.duration:.0f}s")
        with open(path, "rb") as f:
            st.download_button(f"Download {path.name}", f.read(), file_name=path.name, key=f"dl_{idx}")

    if clips:
        st.info(
            "Want to brand the channel or auto-publish these clips to YouTube/Instagram? "
            "That's a separate app - run `streamlit run channel_agent.py` (reads clips from "
            f"{OUTPUT_DIR.name}/)."
        )


if __name__ == "__main__":
    main()
