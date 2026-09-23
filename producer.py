"""End-to-end auto-production: one topic in, one finished folder out.

Chains four AI/tool steps that studio.py and shotsource otherwise expose
as separate manual tools:
    1. write a script for the topic (studio.py's script writers)
    2. break that script into a visual shot list (new here)
    3. write platform-specific title/description/tags (new here)
    4. narrate it (studio.py's synthesize_speech) and find matching stock
       media for the shot list (shotsource.pipeline.run_pipeline)

Everything lands in content/<slug>/ - one folder per video, nothing
shared between videos except the on-disk media cache.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Callable, Optional

from json_utils import extract_json_items
from studio import UK_MALE_VOICES, synthesize_speech

APP_DIR = Path(__file__).resolve().parent
CONTENT_ROOT = APP_DIR / "content"

ProgressCB = Callable[[str], None]

SHOTLIST_PROMPT = """You are a video editor picking stock photos for a documentary. Read this narration script and produce a shot list - one entry roughly every 20-25 seconds of spoken narration (assume ~150 spoken words per minute).

Script:
{script}

Each entry must describe something a camera could literally photograph - a physical object, place, person's generic appearance, action, or setting. Stock photo libraries are searched with these exact words, so an entry that isn't a concrete visual scene will return zero results.

Free stock libraries are shallow compared to paid ones - a specific, multi-detail scene ("German flag outside a modern glass office building at dusk") often has no real match and comes back empty. A short, common, generic subject ("office building exterior", "stack of paperwork", "handshake close up") almost always has dozens. When in doubt, describe the single most important, most generic object or scene in the moment - not everything happening in it.

NEVER write:
- Abstract ideas or analysis ("lack of transparency", "investors ignore red flags", "regulatory failure")
- Named real people ("Markus Braun and Oliver Bussmann") - stock libraries won't have them; describe their generic role instead
- Narrative summary or cause-and-effect statements ("meteoric rise fuels investor confidence")
- More than one distinct subject or detail stacked into one description ("German flag outside a modern office building" - pick one: the flag, or the building)

ALWAYS write short, common, easy-to-find scenes (2-6 words), e.g.:
- "stack of financial documents"
- "empty corporate boardroom"
- "businessman signing paperwork"
- "national flag on flagpole"
- "stock market ticker screen"
- "person reviewing spreadsheet"
- "courthouse exterior"
- "handcuffs close up"
- "newspaper front page"

Respond with ONLY a JSON array of short visual descriptions (strings), each 2-6 words, in the same order the script flows. No other text, no markdown fences.
"""

METADATA_PROMPT = """You are a social media manager writing publish-ready metadata for one video.

Channel: {channel}
Topic: {topic}
Script (for context - do not repeat it verbatim):
{script_excerpt}

Write metadata for three platforms. Respond with ONLY a JSON object shaped exactly like this, no other text, no markdown fences:
{{
  "youtube": {{"title": "...", "description": "...", "tags": ["...", "..."]}},
  "instagram": {{"caption": "...", "hashtags": ["...", "..."]}},
  "facebook": {{"text": "...", "hashtags": ["...", "..."]}}
}}

Rules:
- youtube.title: under 100 characters, no clickbait ALL CAPS.
- youtube.description: 2-4 paragraphs, includes a hook in the first line.
- youtube.tags: 8-15 relevant keywords, no # symbols.
- instagram.caption: shorter, punchier, 1-3 short paragraphs, can include 1-2 emoji.
- instagram.hashtags: 8-15 hashtags without the # symbol.
- facebook.text: conversational, 1-2 paragraphs, ends with a question or call to action.
- facebook.hashtags: 3-6 hashtags without the # symbol.
"""


# Duration presets for the Produce page, so a Ollama-technical "target
# words" number never has to be typed by hand - pick a length, the word
# count (and therefore how many distinct topics/sections the script ends
# up covering) follows automatically from studio.py's ~150 spoken
# words/minute pacing and its ~900-word-per-outline-section chunking.
VIDEO_LENGTH_PRESETS = {
    "short": 90,     # ~30-40s of narration -> studio.py plans 1 outline section
    "long": 1500,    # ~10min of narration -> studio.py plans a handful of sections
}
DEFAULT_VIDEO_LENGTH = "long"


def resolve_target_words(length: Optional[str], target_words: Optional[int] = None) -> int:
    """Turns the Produce page's length choice into a word count. An
    explicit target_words (e.g. from an older client, or advanced use)
    always wins; otherwise a known length preset is used, falling back to
    DEFAULT_VIDEO_LENGTH for anything unset or unrecognized."""
    if target_words:
        return int(target_words)
    key = (length or "").strip().lower()
    return VIDEO_LENGTH_PRESETS.get(key, VIDEO_LENGTH_PRESETS[DEFAULT_VIDEO_LENGTH])


def slugify(text: str, limit: int = 50) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[-\s]+", "-", text)
    return text[:limit].rstrip("-") or "video"


def default_style_slug() -> Optional[str]:
    """Auto-applies your most recently saved style profile when none is
    explicitly requested, so the editing-style behavior just works without
    needing a UI to pick one - style_analyzer.py's output stays a backend
    capability, not something exposed as a page control."""
    styles_dir = CONTENT_ROOT / "_styles"
    if not styles_dir.exists():
        return None
    profiles = sorted(styles_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return profiles[0].stem if profiles else None


def unique_slug(base: str) -> str:
    slug = base
    n = 2
    while (CONTENT_ROOT / slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def generate_shot_list(writer, script: str) -> list[str]:
    raw = writer._call_model(SHOTLIST_PROMPT.format(script=script[:6000]), max_tokens=1024)
    items = extract_json_items(raw)
    if not items:
        raise RuntimeError("Model did not return a usable shot list.")
    return [str(item).strip() for item in items if str(item).strip()]


def generate_metadata(writer, topic: str, channel: str, script: str) -> dict:
    raw = writer._call_model(
        METADATA_PROMPT.format(channel=channel, topic=topic, script_excerpt=script[:4000]), max_tokens=1500
    )
    items = extract_json_items(raw)
    if not items:
        raise RuntimeError("Model did not return usable metadata.")
    metadata = items[0]
    for platform in ("youtube", "instagram", "facebook"):
        metadata.setdefault(platform, {})
    return metadata


def format_notes(topic: str, channel: str, metadata: dict) -> str:
    yt = metadata.get("youtube", {})
    ig = metadata.get("instagram", {})
    fb = metadata.get("facebook", {})

    def tag_line(tags) -> str:
        return ", ".join(str(t).lstrip("#") for t in (tags or []))

    return f"""{channel} - {topic}
{"=" * (len(channel) + len(topic) + 3)}

--- YOUTUBE ---
Title: {yt.get("title", "")}

Description:
{yt.get("description", "")}

Tags: {tag_line(yt.get("tags"))}

--- INSTAGRAM ---
Caption:
{ig.get("caption", "")}

Hashtags: {" ".join("#" + t.lstrip("#") for t in (ig.get("hashtags") or []))}

--- FACEBOOK ---
Post text:
{fb.get("text", "")}

Hashtags: {" ".join("#" + t.lstrip("#") for t in (fb.get("hashtags") or []))}
"""


def produce_video(
    topic: str,
    channel: str,
    writer,
    voice: str = "en-GB-RyanNeural",
    target_words: int = 1500,
    style_slug: Optional[str] = None,
    progress: Optional[ProgressCB] = None,
) -> dict:
    """Runs the whole chain and writes everything to content/<slug>/.
    Returns a summary dict the API layer can hand back to the frontend.

    style_slug, if given, names a profile saved under content/_styles/ by
    style_analyzer.py - its measured pacing (from a real reference video)
    is used for the final assembly step instead of a flat, uniform cut
    rhythm."""
    if voice not in UK_MALE_VOICES.values():
        voice = "en-GB-RyanNeural"

    style = None
    effective_style_slug = style_slug or default_style_slug()
    if effective_style_slug:
        style_path = CONTENT_ROOT / "_styles" / f"{effective_style_slug}.json"
        if style_path.exists():
            style = json.loads(style_path.read_text(encoding="utf-8"))

    def report(msg: str) -> None:
        if progress:
            progress(msg)

    CONTENT_ROOT.mkdir(exist_ok=True)
    slug = unique_slug(slugify(f"{topic}"))
    video_dir = CONTENT_ROOT / slug
    video_dir.mkdir(parents=True)
    media_dir = video_dir / "media"

    report("Writing script...")
    script = writer.generate_script(topic, target_words=target_words, progress=lambda m: report(f"Script: {m}"))
    (video_dir / "script.txt").write_text(script, encoding="utf-8")

    report("Planning shots...")
    shots = generate_shot_list(writer, script)
    (video_dir / "shots.json").write_text(json.dumps(shots, indent=2), encoding="utf-8")

    report("Writing YouTube/Instagram/Facebook metadata...")
    metadata = generate_metadata(writer, topic, channel, script)
    (video_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (video_dir / "notes.txt").write_text(format_notes(topic, channel, metadata), encoding="utf-8")

    report("Generating voiceover...")
    audio_path = video_dir / "voiceover.mp3"
    synthesize_speech(script, voice, audio_path, progress=lambda m: report(f"Voiceover: {m}"))

    report(f"Searching stock media for {len(shots)} shot(s) - this can take a while...")
    from shotsource.pipeline import run_pipeline

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("\n".join(shots))
        shots_path = f.name
    try:
        manifest_path = run_pipeline(
            shots_path, output_dir_override=str(media_dir), progress=lambda m: report(f"Media: {m}")
        )
    finally:
        Path(shots_path).unlink(missing_ok=True)

    kept = 0
    if manifest_path.exists():
        kept = max(0, sum(1 for _ in manifest_path.open(encoding="utf-8")) - 1)  # minus header row

    video_error = None
    if kept > 0:
        report("Assembling final video...")
        try:
            from video_assembler import AssemblyError, assemble_video

            assemble_video(video_dir, progress=lambda m: report(f"Video: {m}"), style=style)
        except Exception as exc:
            # Script/voiceover/metadata are still real, useful output even if
            # assembly fails (e.g. ffmpeg missing) - don't fail the whole run.
            video_error = str(exc)
    else:
        video_error = "No media was kept, so there's nothing to build a video from."

    report("Writing Obsidian note...")
    from obsidian_export import update_index, write_video_note

    write_video_note(video_dir, slug, topic, channel, script, shots, metadata)
    update_index(CONTENT_ROOT)

    report("Done.")
    return {
        "slug": slug,
        "topic": topic,
        "channel": channel,
        "shots": len(shots),
        "media_kept": kept,
        "word_count": len(script.split()),
        "video_error": video_error,
    }
