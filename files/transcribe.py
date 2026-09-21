"""Transcribe stage — word-level timings from your own voiceover.

Three later stages depend on these timings. Uses whisper if installed;
otherwise tells you the one command to run.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from pipeline import state as st

log = logging.getLogger(__name__)


def run(video_dir: Path, config: dict) -> None:
    video_dir = Path(video_dir)
    s = st.load(video_dir)
    if st.is_done(s, "transcribe"):
        log.info("transcribe: already done, skipping")
        return

    audio = video_dir / "audio" / "vo.wav"
    if not audio.exists():
        raise FileNotFoundError(f"Record your voiceover to {audio} first.")

    out = video_dir / "audio" / "timings.json"
    try:
        import whisper  # type: ignore
    except ImportError:
        raise RuntimeError(
            "whisper not installed. Either `pip install openai-whisper` or run:\n"
            f"  whisper {audio} --model small --word_timestamps True "
            f"--output_format json --output_dir {audio.parent}"
        )

    model = whisper.load_model(config["transcribe"]["model"])
    result = model.transcribe(str(audio), word_timestamps=True)
    words = [
        {"word": w["word"].strip(), "start": w["start"], "end": w["end"]}
        for seg in result["segments"]
        for w in seg.get("words", [])
    ]
    out.write_text(json.dumps(words, indent=2), encoding="utf-8")
    st.mark_done(video_dir, s, "transcribe", words=len(words))
