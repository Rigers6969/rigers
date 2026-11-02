"""Viral Analyzer: learn WHY a video went viral, then make an original video with the same formula.

1. analyze(url)   downloads the video, writes down every word with its time (Whisper), measures the cuts,
                  and asks the AI writer to explain the formula: hook type, structure, pace, tricks, ending.
2. make_version() asks the AI to write a NEW story (your topic, your words) that follows that formula,
                  then photo_short.py builds it with free Wikipedia photos -> it shows up in My videos.

It never copies the other creator's words, facts or footage - copying those gets a channel demonetized
("reused content") and can bring a copyright strike. Only the pattern is reused.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "viral"
STORIES_DIR = APP_DIR / "stories"
ProgressCB = Callable[[str], None]

_lock = threading.Lock()
_status: dict = {"running": False, "kind": None, "message": "", "error": None, "result": None, "started": None}


class ViralError(RuntimeError):
    pass


# ---------------------------------------------------------------- measuring

def _vid_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{6,})", url or "")
    if not m:
        raise ViralError("That doesn't look like a YouTube link. Copy it from the Share button.")
    return m.group(1)


def _sentences(words: list[dict]) -> list[dict]:
    """Groups Whisper words into timed sentences."""
    out, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[.!?]$", w["word"].strip()) or len(cur) >= 28:
            out.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": " ".join(x["word"].strip() for x in cur)})
            cur = []
    if cur:
        out.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": " ".join(x["word"].strip() for x in cur)})
    return out


def measure(words: list[dict], cuts: list[float], duration: float, width: int = 0, height: int = 0) -> dict:
    """Numbers that explain retention: length, speaking speed, cut speed, the hook, the ending."""
    sents = _sentences(words)
    n = len(words)
    hook_words = [w["word"].strip() for w in words if w["start"] < 3.0]
    first = sents[0]["text"] if sents else ""
    last = sents[-1]["text"] if sents else ""
    first_set = {re.sub(r"\W", "", x.lower()) for x in first.split()} - {""}
    last_set = {re.sub(r"\W", "", x.lower()) for x in last.split()} - {""}
    overlap = len(first_set & last_set) / max(1, min(len(first_set), len(last_set)))
    return {
        "duration": round(duration, 1),
        "short": bool(height > width) or duration <= 180,
        "words": n,
        "words_per_sec": round(n / duration, 2) if duration else 0,
        "cuts": len(cuts),
        "sec_per_cut": round(duration / (len(cuts) + 1), 1) if duration else 0,
        "first_word_at": round(words[0]["start"], 2) if words else None,
        "hook_3s": " ".join(hook_words),
        "first_sentence": first,
        "last_sentence": last,
        "hook_is_question": first.strip().endswith("?"),
        "hook_has_number": bool(re.search(r"\d", first)),
        "loop_guess": overlap >= 0.3 or bool(re.search(r"(because|but|and|so)\W*\.{0,3}$", last.lower())),
    }


def _download(url: str, folder: Path, progress: ProgressCB) -> tuple[Path, dict]:
    import yt_dlp

    from style_analyzer import download_reference_video

    meta = {}
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as y:
            info = y.extract_info(url, download=False)
        meta = {k: info.get(k) for k in ("title", "channel", "view_count", "like_count", "comment_count", "upload_date",
                                          "duration", "width", "height")}
    except Exception:
        pass
    path, title = download_reference_video(url, folder, progress)
    meta.setdefault("title", title)
    return path, meta


def _transcribe(video: Path, progress: ProgressCB) -> list[dict]:
    from video_editor import transcribe_words

    wav = video.with_suffix(".wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-ac", "1", "-ar", "16000", str(wav)],
                   check=True, timeout=300)
    words = transcribe_words(wav, "base", progress)
    return [{"word": str(w.get("word", "")), "start": float(w.get("start", 0)), "end": float(w.get("end", 0))} for w in words]


# ---------------------------------------------------------------- the AI part

FORMULA_PROMPT = """You study why YouTube videos go viral. Below is a video's transcript with timings, and measurements.

TITLE: {title}
CHANNEL: {channel}   VIEWS: {views}
MEASURED: {duration}s long, {words_per_sec} words per second, a new shot every {sec_per_cut}s, first word at {first_word_at}s.
FIRST 3 SECONDS: "{hook_3s}"
LAST SENTENCE: "{last_sentence}"

TRANSCRIPT:
{transcript}

Explain the FORMULA (the pattern, not the content) as ONLY a JSON object, no other text:
{{
  "hook_type": "short name, e.g. shocking claim / question to viewer / number reveal / 'this man...' / mid-action",
  "hook_why": "one sentence: why the first 3 seconds stop the scroll",
  "structure": ["beat 1 (0-3s): ...", "beat 2: ...", "... 4 to 8 beats, each one short"],
  "retention_tricks": ["3 to 6 concrete tricks, e.g. open loop, numbers on screen, a twist at 70%, short sentences"],
  "ending_type": "loop / cliffhanger / punchline / call to action / question",
  "why_viral": "two sentences in simple English",
  "title_pattern": "the title as a reusable template, e.g. 'The Man Who ___ … Twice'",
  "best_for": "which kinds of topics this formula fits"
}}"""

VERSION_PROMPT = """Write an ORIGINAL YouTube Short script for the channel "{channel}" about: {topic}

Follow this proven FORMULA, but use completely new words, facts and topic (never copy the original video):
- Hook type: {hook_type} ({hook_why})
- Structure: {structure}
- Tricks to use: {tricks}
- Ending: {ending_type}
- Title template: {title_pattern}
- Length: about {target_words} spoken words in total, in {n_scenes} short lines (one picture per line).

Rules: only true, well-known facts; say who claims anything uncertain; simple English; short punchy sentences; no "follow" line at the end;
numbers spelled out in "say" (for the voice) but written as digits in "cap" (the captions); put 1-3 KEY WORDS per caption in CAPITALS.
For each line, name 1-2 English Wikipedia page titles that will have a fitting free photo.

Answer with ONLY a JSON object:
{{
  "title": "max 70 characters, ends with #shorts",
  "description": "2-3 sentences + a 'Read more:' Wikipedia link + 3-5 hashtags",
  "tags": ["8 to 10 tags"],
  "pinned": "a question for the comments",
  "scenes": [
    {{"say": "spoken line", "cap": "caption with KEY WORDS", "pages": ["Wikipedia page"], "want": ["word in a good photo's file name"],
      "fx": null or {{"type": "big", "text": "short number like 65% or 1922", "sub": "2-4 WORDS"}} or {{"type": "stamp", "words": ["ONE", "TWO"]}} or {{"type": "tag", "text": "PLACE · YEAR"}}}}
  ]
}}"""


def _writer():
    import autopilot
    from studio_api import make_writer

    s = autopilot.load_settings()
    return make_writer(s["engine"], s)


def _json(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        raise ViralError("The AI didn't answer in the right format. Try again (or switch the engine to Claude in Autopilot).")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise ViralError(f"The AI's answer was broken JSON ({exc}). Try again.") from exc


def explain(meta: dict, stats: dict, words: list[dict], writer=None) -> dict:
    writer = writer or _writer()
    transcript = "\n".join(f"[{s['start']:.1f}s] {s['text']}" for s in _sentences(words))[:9000]
    raw = writer._call_model(FORMULA_PROMPT.format(title=meta.get("title", ""), channel=meta.get("channel", ""),
                                                   views=meta.get("view_count") or "unknown", transcript=transcript or "(no speech)",
                                                   **stats), 1500)
    f = _json(raw)
    f.setdefault("structure", [])
    f.setdefault("retention_tricks", [])
    return f


def analyze(url: str, progress: ProgressCB = lambda m: None, writer=None) -> dict:
    vid = _vid_id(url)
    DATA_DIR.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        progress("Downloading the video...")
        video, meta = _download(url, Path(tmp), progress)
        progress("Writing down every word (Whisper)...")
        words = _transcribe(video, progress)
        progress("Measuring the cuts...")
        from style_analyzer import detect_cuts, get_duration_seconds

        cuts = detect_cuts(video)
        duration = float(meta.get("duration") or get_duration_seconds(video))
        stats = measure(words, cuts, duration, int(meta.get("width") or 0), int(meta.get("height") or 0))
    progress("Asking the AI why it works...")
    formula = explain(meta, stats, words, writer)
    result = {"id": vid, "url": url, "meta": meta, "stats": stats, "formula": formula,
              "transcript": _sentences(words), "analyzed": datetime.now().isoformat(timespec="minutes")}
    (DATA_DIR / f"{vid}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def history() -> list[dict]:
    out = []
    for p in sorted(DATA_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if DATA_DIR.exists() else []:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def get(vid: str) -> dict:
    p = DATA_DIR / f"{re.sub(r'[^A-Za-z0-9_-]', '', vid)}.json"
    if not p.exists():
        raise ViralError("That analysis wasn't found.")
    return json.loads(p.read_text(encoding="utf-8"))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "video"


BRANDS = {"Paper Trail": ("PAPER TRAIL", [243, 196, 72]), "History": ("HISTORY", [255, 190, 90]),
          "The Forgotten Lab": ("THE FORGOTTEN LAB", [150, 255, 110])}


def write_story(analysis: dict, topic: str, channel: str, writer=None) -> dict:
    """The AI writes an original story file (photo_short.py format) that follows the analysed formula."""
    topic, channel = (topic or "").strip(), (channel or "Paper Trail").strip()
    if len(topic) < 3:
        raise ViralError("Write the topic for your version first.")
    f, st = analysis["formula"], analysis["stats"]
    seconds = min(max(st.get("duration") or 35, 20), 45) if st.get("short", True) else 45  # Shorts: stay short
    target_words = int(seconds * max(2.4, min(3.4, st.get("words_per_sec") or 2.9)))
    n_scenes = max(7, min(12, round(seconds / max(2.5, min(4.0, st.get("sec_per_cut") or 3.0)))))
    writer = writer or _writer()
    raw = writer._call_model(VERSION_PROMPT.format(channel=channel, topic=topic, hook_type=f.get("hook_type", ""),
                                                   hook_why=f.get("hook_why", ""), structure=" | ".join(f.get("structure", [])),
                                                   tricks="; ".join(f.get("retention_tricks", [])), ending_type=f.get("ending_type", ""),
                                                   title_pattern=f.get("title_pattern", ""), target_words=target_words,
                                                   n_scenes=n_scenes), 3000)
    d = _json(raw)
    scenes = []
    for sc in d.get("scenes") or []:
        say = str(sc.get("say", "")).strip()
        if not say:
            continue
        item = {"say": say, "cap": str(sc.get("cap") or say).strip(),
                "img": {"pages": [str(p) for p in (sc.get("pages") or [])][:3], "want": [str(w) for w in (sc.get("want") or [])][:4]}}
        fx = sc.get("fx")
        if isinstance(fx, dict) and fx.get("type") in ("big", "stamp", "tag"):
            if fx["type"] == "stamp":
                fx = {"type": "stamp", "words": [str(w).upper()[:12] for w in (fx.get("words") or [])][:3]} if fx.get("words") else None
            elif fx["type"] == "big":
                fx = {"type": "big", "text": str(fx.get("text", ""))[:8], "sub": str(fx.get("sub", ""))[:28].upper(), "size": 250}
            else:
                fx = {"type": "tag", "text": str(fx.get("text", ""))[:32].upper()}
            if fx:
                item["fx"] = fx
        scenes.append(item)
    if len(scenes) < 4:
        raise ViralError("The AI wrote too few lines. Try again.")
    brand, accent = BRANDS.get(channel, (channel.upper(), [243, 196, 72]))
    title = str(d.get("title") or topic)[:95]
    if "#shorts" not in title.lower():
        title = (title[:86] + " #shorts")
    slug = f"viral-{_slug(topic)}-{int(time.time()) % 100000}"
    story = {"slug": slug, "channel": channel, "brand": brand, "voice": "en-US-AndrewNeural", "rate": "+12%", "gap": 0.06,
             "tail": 0.25 if "loop" in str(f.get("ending_type", "")).lower() else 0.6, "accent": accent, "tint": [96, 86, 70],
             "scenes": scenes, "made_from": analysis.get("url"),
             "upload": {"title": title, "description": str(d.get("description") or ""), "tags": [str(t) for t in d.get("tags") or []][:12],
                        "pinned": str(d.get("pinned") or "")}}
    STORIES_DIR.mkdir(exist_ok=True)
    (STORIES_DIR / f"{slug}.json").write_text(json.dumps(story, indent=2, ensure_ascii=False), encoding="utf-8")
    return story


def make_version(vid: str, topic: str, channel: str, progress: ProgressCB = lambda m: None, writer=None, build=None) -> dict:
    analysis = get(vid)
    progress("Writing your original script with the same formula...")
    story = write_story(analysis, topic, channel, writer)
    progress("Building the video (photos, voice, captions, music)... 3-6 minutes")
    if build is None:
        from photo_short import build
    build(STORIES_DIR / f"{story['slug']}.json")
    return {"slug": story["slug"], "title": story["upload"]["title"], "lines": [s["say"] for s in story["scenes"]]}


# ---------------------------------------------------------------- background jobs (for the page)

def status() -> dict:
    return dict(_status)


def _start(kind: str, fn) -> bool:
    with _lock:
        if _status["running"]:
            return False
        _status.update(running=True, kind=kind, message="Starting...", error=None, result=None, started=time.time())

    def job():
        try:
            _status["result"] = fn(lambda m: _status.update(message=m))
            _status["message"] = "Done."
        except ViralError as exc:
            _status["error"] = str(exc)
        except Exception as exc:
            traceback.print_exc()
            _status["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            _status["running"] = False

    threading.Thread(target=job, daemon=True).start()
    return True


def start_analyze(url: str) -> bool:
    _vid_id(url)  # check the link before starting
    return _start("analyze", lambda p: analyze(url, p))


def start_version(vid: str, topic: str, channel: str) -> bool:
    get(vid)
    if len((topic or "").strip()) < 3:
        raise ViralError("Write the topic for your version first.")
    return _start("version", lambda p: make_version(vid, topic, channel, p))
