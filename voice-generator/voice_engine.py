"""The voice engine - copied from the main app's studio.py so this folder
runs on its own. Narrates text with Microsoft's free neural voices
(edge-tts); long texts are split into parts and joined with ffmpeg.
"""
from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

TTS_MAX_CHARS = 3000

VOICES = {
    "Ryan (British, male)": "en-GB-RyanNeural",
    "Thomas (British, male)": "en-GB-ThomasNeural",
}

ProgressCB = Callable[[str], None]


class VoiceSynthesisError(RuntimeError):
    pass


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
            # shutil.move, not Path.replace()/os.replace() - the temp dir
            # (tempfile.TemporaryDirectory) lands on the OS temp drive, which
            # on Windows is commonly C: even when the project lives on D:.
            # os.replace() maps to Windows' MoveFileEx without the
            # copy-allowed flag, so it hard-fails with WinError 17 on a
            # cross-drive move; shutil.move() falls back to copy+delete when
            # a same-volume rename isn't possible.
            shutil.move(str(part_paths[0]), str(output_path))
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
