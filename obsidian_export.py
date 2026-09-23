"""Exports each produced video as a real Obsidian note, so content/ can
be opened directly as an Obsidian vault - one note per video (script,
shot list, platform metadata, embedded voiceover/video/thumbnail) plus a
running index note linking all of them.

Obsidian needs nothing but a folder of markdown files - no new
dependency, no server changes, no plugin. Point Obsidian's "Open folder
as vault" at this app's content/ folder and every produced video shows
up as a linked note, its audio/video/thumbnail playable right in the
note via Obsidian's built-in embed syntax.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _slug_tag(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "untagged"


def _yaml_tag_list(tags: list[str]) -> str:
    return "\n" + "\n".join(f"  - {t}" for t in tags)


def _frontmatter(slug: str, title: str, topic: str, channel: str, tags: list[str]) -> str:
    # Basic quote-escaping - titles/topics are free text and could contain
    # a literal double-quote, which would otherwise break the YAML string.
    def q(s: str) -> str:
        return s.replace('"', '\\"')

    return "\n".join([
        "---",
        f'title: "{q(title)}"',
        f'topic: "{q(topic)}"',
        f'channel: "{q(channel)}"',
        f"slug: {slug}",
        f"created: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        f"tags:{_yaml_tag_list(tags)}",
        "---",
        "",
    ])


def write_video_note(
    video_dir: Path,
    slug: str,
    topic: str,
    channel: str,
    script: str,
    shots: list[str],
    metadata: dict,
) -> Path:
    """Writes/overwrites video_dir/<slug>.md. Safe to call again later -
    e.g. after the Edit page adds music/captions or a thumbnail - since
    it always rebuilds the note fresh from what's currently in
    video_dir, rather than editing an existing note in place."""
    yt = metadata.get("youtube") or {}
    ig = metadata.get("instagram") or {}
    fb = metadata.get("facebook") or {}

    tags = ["paper-trail-video", _slug_tag(channel), _slug_tag(topic)]
    parts = [_frontmatter(slug, yt.get("title") or topic, topic, channel, tags)]
    parts.append(f"# {yt.get('title') or topic}\n")

    # Media embeds first - Obsidian renders ![[file]] as an inline,
    # playable audio/video player or image, right in the note. Prefers
    # the edited video/thumbnail over the base ones when they exist.
    if (video_dir / "thumbnail.jpg").exists():
        parts.append("![[thumbnail.jpg]]\n")
    if (video_dir / "final_edited.mp4").exists():
        parts.append("![[final_edited.mp4]]\n")
    elif (video_dir / "final.mp4").exists():
        parts.append("![[final.mp4]]\n")
    elif (video_dir / "voiceover.mp3").exists():
        parts.append("![[voiceover.mp3]]\n")

    parts.append("## YouTube\n")
    parts.append(f"**Title:** {yt.get('title', '')}\n")
    if yt.get("description"):
        parts.append(f"{yt['description']}\n")
    if yt.get("tags"):
        parts.append(f"**Tags:** {', '.join(yt['tags'])}\n")

    if ig.get("caption") or ig.get("hashtags"):
        parts.append("## Instagram\n")
        if ig.get("caption"):
            parts.append(f"{ig['caption']}\n")
        if ig.get("hashtags"):
            parts.append(" ".join(f"#{t.lstrip('#')}" for t in ig["hashtags"]) + "\n")

    if fb.get("text") or fb.get("hashtags"):
        parts.append("## Facebook\n")
        if fb.get("text"):
            parts.append(f"{fb['text']}\n")
        if fb.get("hashtags"):
            parts.append(" ".join(f"#{t.lstrip('#')}" for t in fb["hashtags"]) + "\n")

    if shots:
        parts.append("## Shot List\n")
        parts.extend(f"{i}. {shot}" for i, shot in enumerate(shots, start=1))
        parts.append("")

    parts.append("## Script\n")
    parts.append(script.strip() + "\n")

    note_path = video_dir / f"{slug}.md"
    note_path.write_text("\n".join(parts), encoding="utf-8")
    return note_path


def refresh_video_note(video_dir: Path) -> Optional[Path]:
    """Rebuilds a video's note from whatever's currently on disk in
    video_dir - used after the Edit page adds music/captions or a
    thumbnail, so the note's media embed picks up final_edited.mp4 or
    thumbnail.jpg instead of staying stuck on what existed at Produce
    time. Topic/channel aren't stored as their own file, so they're
    parsed back out of notes.txt's own "{channel} - {topic}" header
    line (written by producer.py's format_notes()) rather than guessed."""
    slug = video_dir.name
    script_path = video_dir / "script.txt"
    shots_path = video_dir / "shots.json"
    metadata_path = video_dir / "metadata.json"
    notes_path = video_dir / "notes.txt"
    if not script_path.exists() or not metadata_path.exists():
        return None

    script = script_path.read_text(encoding="utf-8")
    shots = json.loads(shots_path.read_text(encoding="utf-8")) if shots_path.exists() else []
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    channel, topic = "Paper Trail", slug
    if notes_path.exists():
        first_line = notes_path.read_text(encoding="utf-8").splitlines()[0]
        if " - " in first_line:
            channel, topic = first_line.split(" - ", 1)

    return write_video_note(video_dir, slug, topic, channel, script, shots, metadata)


def update_index(content_root: Path) -> Optional[Path]:
    """Rewrites content/Index.md from scratch by scanning every video
    folder for its own note - always consistent with what's actually on
    disk, no drift between the index and reality."""
    if not content_root.exists():
        return None

    entries = []
    for entry in sorted(content_root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        note_path = entry / f"{entry.name}.md"
        if not note_path.exists():
            continue

        title = entry.name
        metadata_path = entry / "metadata.json"
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                title = (metadata.get("youtube") or {}).get("title") or entry.name
            except (json.JSONDecodeError, OSError):
                pass
        entries.append(f"- [[{entry.name}|{title}]]")

    lines = ["---", 'title: "Paper Trail - Video Index"', "---", "", "# Paper Trail Videos", ""]
    lines.extend(entries or ["*No videos produced yet.*"])

    index_path = content_root / "Index.md"
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return index_path
