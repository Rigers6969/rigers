"""Word-by-word transcription with faster-whisper, on the CPU.

Transcripts are cached in cache/ (keyed by the file's path, size, date and
the Whisper model), so making a second batch of clips from the same video
skips straight to finding moments.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

APP_DIR = Path(__file__).resolve().parent
CACHE_DIR = APP_DIR / "cache"

ProgressCB = Callable[[str, float], None]  # (message, percent 0-100)


class TranscriptionError(Exception):
    pass


class Cancelled(Exception):
    pass


def _cache_path(video: Path, model_size: str) -> Path:
    st = video.stat()
    key = f"{video.resolve()}|{st.st_size}|{int(st.st_mtime)}|{model_size}"
    return CACHE_DIR / f"{hashlib.sha1(key.encode()).hexdigest()[:16]}.json"


def _fmt_time(seconds: float) -> str:
    seconds = int(max(0, seconds))
    return f"{seconds // 60}:{seconds % 60:02d}" if seconds < 3600 else f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


_models: dict = {}
_models_lock = threading.Lock()


def _model(model_size: str, report=None):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError("faster-whisper isn't installed - run: pip install -r requirements.txt") from exc
    with _models_lock:
        if model_size not in _models:
            if report:
                report(f"Loading the Whisper '{model_size}' model (the very first time it downloads, ~150-500 MB)...", 0)
            threads = max(2, (os.cpu_count() or 4) // 2)  # physical cores - faster than hyper-threads here
            _models[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8", cpu_threads=threads)
        return _models[model_size]


def local_words(audio: Path, model_size: str = "base", report=None, cancelled: Callable[[], bool] = lambda: False) -> list[dict]:
    """Word timings for one audio/video file, on this PC (no cache)."""
    model = _model(model_size, report)
    try:
        segments, info = model.transcribe(str(audio), beam_size=5, vad_filter=True, word_timestamps=True)
    except Exception as exc:
        raise TranscriptionError(f"Whisper couldn't read this file's audio: {exc}") from exc
    total = float(info.duration or 0) or 1.0
    began = time.time()
    words: list[dict] = []
    for seg in segments:
        if cancelled():
            raise Cancelled()
        for w in seg.words or []:
            text = (w.word or "").strip()
            if text:
                words.append({"start": round(w.start, 3), "end": round(w.end, 3), "text": text})
        if report:
            elapsed = time.time() - began
            eta = elapsed / max(seg.end, 1) * (total - seg.end)
            report(f"Transcribing on this PC: {_fmt_time(seg.end)} of {_fmt_time(total)} (about {_fmt_time(eta)} left)",
                   min(99.0, seg.end / total * 100))
    return words


def cached_words(video: Path, key: str) -> Optional[list[dict]]:
    path = _cache_path(video, key)
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (json.JSONDecodeError, OSError):
        return None


def save_cache(video: Path, key: str, words: list[dict]) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    _cache_path(video, key).write_text(json.dumps(words), encoding="utf-8")


def transcribe(
    video: Path, model_size: str = "base", progress: Optional[ProgressCB] = None,
    cancelled: Callable[[], bool] = lambda: False,
) -> list[dict]:
    """[{start, end, text}] for every spoken word, in seconds (cached)."""
    def report(msg, pct):
        if progress:
            progress(msg, pct)

    words = cached_words(video, model_size)
    if words:
        report("Using the saved transcript from last time.", 100)
        return words
    words = local_words(video, model_size, report, cancelled)
    if not words:
        raise TranscriptionError("No speech was found in this video - clips are cut around what's said, so it needs talking.")
    save_cache(video, model_size, words)
    report("Transcript done.", 100)
    return words
