"""Unattended, scheduled video production - set a channel + a daily time
window (e.g. "The Archive, 14:00-16:00") and this app produces videos
for it on its own for the whole window: it invents a topic itself
(steered away from ones already covered, via producer.py's
generate_topic_idea/list_covered_topics), produces the video, then
invents another, until the window closes.

This only runs while python web_server.py is itself running on your
machine - it can't power your PC on, and it doesn't touch your screen,
mouse, or keyboard (that's a fundamentally different, much riskier kind
of automation - see the chat this was built from). It's exactly the
same production pipeline the Produce page's own button calls, just
triggered by a clock instead of a click.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from producer import generate_topic_idea, list_covered_topics, produce_video, resolve_target_words

ProgressCB = Callable[[str], None]

APP_DIR = Path(__file__).resolve().parent
SCHEDULE_PATH = APP_DIR / "schedule.json"
TIMEZONE = ZoneInfo("Europe/Tirane")
TICK_SECONDS = 60
MAX_CONSECUTIVE_FAILURES = 3
FAILURE_BACKOFF_SECONDS = 30

_last_run_date: dict[str, str] = {}
_lock = threading.Lock()


def load_schedule() -> list[dict]:
    if not SCHEDULE_PATH.exists():
        return []
    try:
        data = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data.get("entries", []) if isinstance(data, dict) else []


def save_schedule(entries: list[dict]) -> None:
    SCHEDULE_PATH.write_text(json.dumps({"entries": entries}, indent=2), encoding="utf-8")


def new_entry_id() -> str:
    return uuid.uuid4().hex[:12]


def _window_end_datetime(entry: dict) -> datetime:
    now = datetime.now(TIMEZONE)
    hour, minute = (int(x) for x in entry["end"].split(":"))
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def run_scheduled_window(entry: dict, progress: Optional[ProgressCB] = None) -> dict:
    """Produces videos for `entry`'s channel back-to-back until the
    window's end time, inventing a new topic each time. Returns a
    summary dict; a single video's failure doesn't end the window (a
    bad topic or a transient model hiccup shouldn't waste the rest of
    the window), but MAX_CONSECUTIVE_FAILURES in a row does - that
    pattern means something's actually broken (Ollama/Claude/ffmpeg not
    reachable), and retrying every video until the window closes would
    just spam identical failures."""
    from studio_api import make_writer

    def report(msg: str) -> None:
        if progress:
            progress(msg)

    writer = make_writer(entry.get("engine", "ollama"), entry)
    channel = entry["channel"]
    end_dt = _window_end_datetime(entry)

    results = []
    consecutive_failures = 0
    i = 0
    while datetime.now(TIMEZONE) < end_dt:
        i += 1
        try:
            avoid = list_covered_topics(channel) + [r["topic"] for r in results]
            report(f"Video {i}: coming up with a topic...")
            topic = generate_topic_idea(writer, channel, avoid_topics=avoid)
            report(f'Video {i}: "{topic}"')

            result = produce_video(
                topic, channel, writer,
                voice=entry.get("voice", "en-GB-RyanNeural"),
                target_words=resolve_target_words(entry.get("length")),
                length=entry.get("length"),
                progress=lambda m, i=i: report(f"Video {i}: {m}"),
            )
            result["topic"] = topic
            results.append(result)
            consecutive_failures = 0
        except Exception as exc:
            consecutive_failures += 1
            report(f"Video {i} failed: {exc}")
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                report(f"Stopping early - {MAX_CONSECUTIVE_FAILURES} failures in a row "
                       "(check Ollama/Claude API/ffmpeg are actually working).")
                break
            time.sleep(FAILURE_BACKOFF_SECONDS)

    report(f"Window done - produced {len(results)} video(s).")
    return {"channel": channel, "videos": results}


def _start_window_job(entry: dict) -> None:
    from jobs import set_progress, start_job

    def task(job_id: str):
        return run_scheduled_window(entry, progress=lambda m: set_progress(job_id, m))

    start_job(task)


def _tick() -> None:
    now = datetime.now(TIMEZONE)
    today_str = now.date().isoformat()
    current = now.strftime("%H:%M")

    for entry in load_schedule():
        if not entry.get("enabled") or not entry.get("channel") or not entry.get("start") or not entry.get("end"):
            continue
        if not (entry["start"] <= current < entry["end"]):
            continue
        entry_id = entry["id"]
        with _lock:
            if _last_run_date.get(entry_id) == today_str:
                continue
            _last_run_date[entry_id] = today_str
        _start_window_job(entry)


def _loop() -> None:
    while True:
        try:
            _tick()
        except Exception:
            pass  # one bad tick (e.g. a malformed schedule.json) shouldn't kill the whole scheduler thread
        time.sleep(TICK_SECONDS)


def start_scheduler_thread() -> None:
    threading.Thread(target=_loop, daemon=True).start()
