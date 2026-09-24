"""Reviews a produced video's script, title, and photos, and feeds what
it finds back into future productions on the same channel.

Honest mechanism, since "Ollama learns" is easy to overstate: Ollama has
no memory between calls, so nothing here is model fine-tuning. What
actually happens is each review distills a few short, concrete lessons
("open with a concrete stat, not a vague statement"), those get saved
per channel, and producer.py prepends the recent ones into the prompts
for the *next* video's script/shot-list/metadata - in-context steering,
not weight updates. It's real and it works, just not literally
"learning" in the way the phrase usually implies.

Visual review uses a real vision model (llava, via Ollama's own
/api/generate "images" field - see ollama.readthedocs.io/en/api) to
actually look at a sample of the chosen photos, not just re-read the
media pipeline's own match scores - those scores already existed when
the photos were picked, so re-reading them wouldn't catch anything new.
"""
from __future__ import annotations

import base64
import csv
import json
import re
from pathlib import Path
from typing import Callable, Optional

import requests

from json_utils import extract_json_items
from producer import CONTENT_ROOT

ProgressCB = Callable[[str], None]

LESSONS_DIR = CONTENT_ROOT / "_lessons"
MAX_LESSONS_KEPT = 40
MAX_SHOTS_REVIEWED = 8  # caps review time on a long documentary's many shots
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_VISION_MODEL = "llava"

TEXT_REVIEW_PROMPT = """You are a blunt, expert YouTube content critic. Your only goal is making future videos on this channel more likely to actually perform well - not being polite.

Topic: "{topic}"
YouTube title: "{title}"
YouTube description: "{description}"

Script (first 3000 characters):
{script_excerpt}

Rate honestly - a 10 means genuinely excellent, not "good enough for a first draft". Respond with ONLY a JSON object shaped exactly like this, no other text, no markdown fences:
{{
  "script_rating": <1-10>,
  "script_notes": "<2-3 sentences - what's actually working and what's weak, specifically, not generic praise>",
  "title_rating": <1-10>,
  "title_notes": "<1-2 sentences - is this title actually clickable, or flat/generic>",
  "lessons": ["<one short, specific, actionable instruction for the next video>", "..."]
}}

Each lesson must be concrete enough to actually change how the next script or title gets written (e.g. "Open with a specific number or scene, not a general statement about the topic") - not vague encouragement.
"""

VISUAL_REVIEW_PROMPT = """You are reviewing one photo chosen for a documentary video's shot list.

The shot was supposed to show: "{shot_description}"

Look at the image. Does it actually, visually match that description? Is it a real, sharp, professional-looking photo, or does it look irrelevant, low-quality, watermarked, cartoonish, or like a poor stock-photo match?

Respond with ONLY a JSON object, no other text: {{"match_rating": <1-10>, "note": "<one blunt sentence>"}}
"""


def _slugify_channel(channel: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", channel.lower()).strip("-") or "channel"


def _lessons_path(channel: str) -> Path:
    return LESSONS_DIR / f"{_slugify_channel(channel)}.json"


def load_recent_lessons(channel: str, limit: int = 8) -> list[str]:
    """Used by producer.py to steer the next video's prompts away from
    repeating recent, specific mistakes on this channel."""
    path = _lessons_path(channel)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return (data.get("lessons") or [])[-limit:]


def _append_lessons(channel: str, new_lessons: list[str]) -> None:
    if not new_lessons:
        return
    path = _lessons_path(channel)
    existing = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8")).get("lessons", [])
        except (json.JSONDecodeError, OSError):
            existing = []
    combined = (existing + [str(l).strip() for l in new_lessons if str(l).strip()])[-MAX_LESSONS_KEPT:]
    LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"lessons": combined}, indent=2), encoding="utf-8")


def format_guidance(lessons: list[str]) -> str:
    """Turns a lessons list into the block producer.py/studio.py splice
    into their prompts - empty string (not raised) when there's nothing
    yet, since the very first video on a channel has no history."""
    if not lessons:
        return ""
    bullets = "\n".join(f"- {l}" for l in lessons)
    return f"\nFeedback from past videos on this channel - apply these, don't repeat these mistakes:\n{bullets}\n"


def _top_image_per_shot(manifest_path: Path) -> list[tuple[str, str, Path]]:
    """[(shot_id, shot_description, image_path), ...] - each shot's
    best-ranked surviving image, in manifest order."""
    best_rank: dict[str, int] = {}
    best_row: dict[str, dict] = {}
    order: list[str] = []
    with manifest_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            shot_id = row["shot_id"]
            rank = int(row["rank"])
            if shot_id not in best_rank:
                order.append(shot_id)
            if shot_id not in best_rank or rank < best_rank[shot_id]:
                best_rank[shot_id] = rank
                best_row[shot_id] = row
    return [(sid, best_row[sid]["shot_description"], Path(best_row[sid]["local_path"])) for sid in order]


def _sample_shots(shots: list, limit: int) -> list:
    """Evenly spread the sample across the whole video, not just the
    opening shots, so a long documentary's review isn't blind to
    everything after its first minute."""
    if len(shots) <= limit:
        return shots
    step = len(shots) / limit
    return [shots[int(i * step)] for i in range(limit)]


def _b64_image(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode("ascii")


def _call_ollama_vision(
    prompt: str, image_path: Path, host: str, model: str = DEFAULT_VISION_MODEL, timeout: float = 120,
) -> str:
    resp = requests.post(
        f"{host.rstrip('/')}/api/generate",
        json={
            "model": model, "prompt": prompt, "images": [_b64_image(image_path)],
            "stream": False, "options": {"temperature": 0.3},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


def review_video(
    video_dir: Path, writer, channel: str, topic: str,
    ollama_host: str = DEFAULT_OLLAMA_HOST, vision_model: str = DEFAULT_VISION_MODEL,
    progress: Optional[ProgressCB] = None,
) -> Optional[dict]:
    """Reviews video_dir's script/title/photos, saves review.json in it,
    and appends any lessons to this channel's running file. Returns the
    review dict, or None if there's not yet enough produced (script.txt
    /metadata.json) to review."""
    def report(msg: str) -> None:
        if progress:
            progress(msg)

    script_path = video_dir / "script.txt"
    metadata_path = video_dir / "metadata.json"
    if not script_path.exists() or not metadata_path.exists():
        return None

    script = script_path.read_text(encoding="utf-8")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    yt = metadata.get("youtube", {})

    report("Reviewing script and title...")
    text_prompt = TEXT_REVIEW_PROMPT.format(
        topic=topic, title=yt.get("title", ""), description=yt.get("description", ""), script_excerpt=script[:3000],
    )
    text_review: dict = {}
    try:
        raw = writer._call_model(text_prompt, max_tokens=800)
        items = extract_json_items(raw)
        if items:
            text_review = items[0]
    except Exception as exc:
        report(f"Script/title review failed: {exc}")

    weak_shots: list[str] = []
    visual_ratings: list[float] = []
    manifest_path = video_dir / "media" / "manifest.csv"
    if manifest_path.exists():
        sample = _sample_shots(_top_image_per_shot(manifest_path), MAX_SHOTS_REVIEWED)
        for i, (shot_id, description, image_path) in enumerate(sample, start=1):
            if not image_path.exists():
                continue
            report(f"Reviewing photo {i}/{len(sample)}...")
            try:
                raw_v = _call_ollama_vision(
                    VISUAL_REVIEW_PROMPT.format(shot_description=description), image_path, ollama_host, vision_model,
                )
                v_items = extract_json_items(raw_v)
                if v_items:
                    rating = v_items[0].get("match_rating")
                    if isinstance(rating, (int, float)):
                        visual_ratings.append(rating)
                        if rating <= 5:
                            weak_shots.append(f"{shot_id} (\"{description}\"): {v_items[0].get('note', '')}")
            except Exception as exc:
                report(f"Photo review failed for {shot_id}: {exc}")

    lessons = [str(l).strip() for l in (text_review.get("lessons") or []) if str(l).strip()]
    if weak_shots:
        lessons.append(
            "Recent shot descriptions produced weak photo matches - write shot descriptions as short, "
            "literal, generic scenes a stock photo library would actually have, per the shot-list rules."
        )

    review = {
        "script_rating": text_review.get("script_rating"),
        "script_notes": text_review.get("script_notes", ""),
        "title_rating": text_review.get("title_rating"),
        "title_notes": text_review.get("title_notes", ""),
        "visual_rating": round(sum(visual_ratings) / len(visual_ratings), 1) if visual_ratings else None,
        "weak_shots": weak_shots,
        "lessons": lessons,
    }
    (video_dir / "review.json").write_text(json.dumps(review, indent=2), encoding="utf-8")
    _append_lessons(channel, lessons)

    report("Review complete.")
    return review
