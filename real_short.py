"""Real-footage Shorts: real stock video clips (Pexels / Pixabay), fast cuts, zoom punches, colour grade,
bold captions, a deep voice and the hook on screen from the first frame.

    python real_short.py stories/real_blockbuster.json

A story file has short spoken lines, each with 1-3 search words for clips:
    {"slug", "title", "scenes": [{"say": "...", "cap": "... KEY WORDS ...", "clips": ["video rental store", "vhs tapes"]}], "upload": {...}}

Needs the free Pexels and/or Pixabay key (TOP G -> Autopilot -> "Stock video & photos"). The finished Short
lands in content/<slug>/ and shows up in My videos.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parent
W, H, SR = 1080, 1920, 24000
CUT = 1.7          # a new shot about every 1.7 s
GAP = 0.05


def say(msg: str) -> None:
    print(msg, flush=True)


def word_timings(lines: list[str], starts: list[tuple[float, float]]) -> list[dict]:
    """Each caption word with its time, spread over its spoken line by length (good enough for captions)."""
    out = []
    for text, (a, z) in zip(lines, starts):
        words = text.split()
        weights = [len(re.sub(r"\W", "", w)) + 2 for w in words]
        t = a
        for w, wt in zip(words, weights):
            d = (z - a) * wt / sum(weights)
            out.append({"word": w, "text": w, "start": round(t, 3), "end": round(t + d, 3)})
            t += d
    return out


def pick_clips(queries: list[str], n: int, used: set, offline: Path | None, cache: Path) -> list[Path]:
    """n different clips for one line, from its search words (or from local test clips)."""
    if offline:
        files = sorted(offline.glob("*.mp4"))
        return [files[(len(used) + i) % len(files)] for i in range(n)] if files else []
    from shotsource import video_clips

    found = []
    for q in queries:
        try:
            for clip in video_clips.search(q, portrait=True) or video_clips.search(q, portrait=False):
                if clip["id"] not in used:
                    found.append(clip)
        except Exception as exc:
            say(f"     clip search failed for '{q}': {exc}")
    picked, paths = [], []
    for clip in found:  # take the top results, alternating between the search words
        if len(picked) >= n:
            break
        if clip["id"] in {c["id"] for c in picked}:
            continue
        picked.append(clip)
    for clip in picked:
        try:
            paths.append(video_clips.download(clip, cache))
            used.add(clip["id"])
        except Exception as exc:
            say(f"     download failed: {exc}")
    return paths


def title_png(title: str, path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    f = ImageFont.truetype(str(APP / "fonts" / "Anton-Regular.ttf"), 64)
    tw = int(ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(title, font=f))
    img = Image.new("RGBA", (min(W - 40, tw + 70), 104), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, img.width - 1, 103], 22, fill=(243, 196, 72, 255))
    d.text((img.width // 2, 54), title, font=f, fill=(10, 10, 14, 255), anchor="mm")
    img.save(path)


def build(story_path: Path, voice: str = "en-US-ChristopherNeural", rate: str = "+8%", grade: str = "money_gold",
          offline_clips: Path | None = None) -> Path:
    sys.path.insert(0, str(APP))
    from motion import soundtrack
    from photo_short import trim, voice_lines
    from video_assembler import _make_clip_segment, get_duration_seconds
    from video_editor import apply_edits, caption_options, load_look

    story = json.loads(Path(story_path).read_text(encoding="utf-8"))
    out = APP / "content" / story["slug"]
    out.mkdir(parents=True, exist_ok=True)
    scenes = story["scenes"]

    say("1/5  Recording the voice...")
    voices = [trim(v) for v in voice_lines([s["say"] for s in scenes], voice, rate)]
    parts, starts, t = [np.zeros(int(SR * 0.05), np.float32)], [], 0.05
    for v in voices:
        starts.append((t, t + len(v) / SR))
        parts += [v, np.zeros(int(SR * GAP), np.float32)]
        t += len(v) / SR + GAP
    parts.append(np.zeros(int(SR * 0.2), np.float32))
    vo = np.concatenate(parts)
    vo = vo / (np.abs(vo).max() + 1e-9) * 0.9
    dur = len(vo) / SR

    say("2/5  Finding real video clips...")
    used: set = set()
    cache = APP / ".shotsource_cache" / "clips"
    plan = []  # (clip path, seconds)
    cut_times = []
    for i, sc in enumerate(scenes):
        a = starts[i][0] - (0.05 if i == 0 else GAP)
        b = starts[i + 1][0] - GAP if i + 1 < len(scenes) else dur
        n = max(1, round((b - a) / CUT))
        clips = pick_clips(sc.get("clips") or [sc["say"]], n, used, offline_clips, cache)
        if not clips and plan:
            clips = [plan[-1][0]]
        if not clips:
            raise SystemExit(f"No clips found for line {i + 1} ('{sc['say'][:40]}'). Check the Pexels/Pixabay keys.")
        piece = (b - a) / n
        for j in range(n):
            plan.append((clips[j % len(clips)], piece))
            if j:  # cuts inside a line (a new line already gets its own whoosh)
                cut_times.append((i, j * piece))
        say(f"     line {i + 1}/{len(scenes)}: {n} shot(s)")

    say(f"3/5  Cutting {len(plan)} shots...")
    from concurrent.futures import ThreadPoolExecutor
    import os

    with tempfile.TemporaryDirectory(dir=out) as tmp:
        tmp = Path(tmp)
        segs = [tmp / f"s{k:03d}.mp4" for k in range(len(plan))]
        rng = random.Random(7)

        def cut(k):
            clip, d = plan[k]
            try:
                length = get_duration_seconds(clip)
            except Exception:
                length = d
            off = rng.uniform(0, max(0.0, length - d - 0.2)) if length > d + 0.5 else 0.0
            _make_clip_segment(clip, d, segs[k], offset=off, width=W, height=H)

        with ThreadPoolExecutor(max_workers=max(1, min(6, (os.cpu_count() or 2) // 2))) as pool:
            list(pool.map(cut, range(len(plan))))
        lst = tmp / "list.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in segs), encoding="utf-8")
        silent = tmp / "silent.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                        str(silent)], check=True)

        say("4/5  Music, sound effects, voice...")
        sfx = {i: [] for i in range(len(scenes))}
        for i, off in cut_times:  # a whoosh on every cut
            sfx[i].append((off + 0.1, "whoosh"))
        sfx[0].append((0.05, "boom"))
        music = soundtrack(len(vo), starts, sfx)
        mix = vo + 0.55 * music
        mix = mix / (np.abs(mix).max() + 1e-9) * 0.95
        wav = tmp / "mix.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((mix * 32767).astype(np.int16).tobytes())
        vo_wav = tmp / "vo.wav"
        with wave.open(str(vo_wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((vo * 32767).astype(np.int16).tobytes())
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(vo_wav), str(out / "voiceover.mp3")], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav), "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-shortest", str(out / "final.mp4")], check=True)

    say("5/5  Colour grade, zoom punches, captions, title...")
    look = load_look()
    styles = {o["id"] for o in caption_options()}
    style = next((s for s in ("hormozi", "beast", look["caption_style"]) if s in styles), look["caption_style"])
    words = word_timings([s.get("cap", s["say"]) for s in scenes], starts)
    apply_edits(out, add_captions=True, caption_style=style, caption_size="l", zooms=True, graphics=False,
                grade=grade, known_words=words, progress=lambda m: say(f"     {m}"))
    edited = out / "final_edited.mp4"
    png = out / "_title.png"
    title_png(story["title"], png)
    titled = out / "_titled.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(edited), "-i", str(png), "-filter_complex",
                    "[0:v][1:v]overlay=(W-w)/2:200[v]", "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "faster",
                    "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                    "-movflags", "+faststart", str(titled)], check=True)
    titled.replace(edited)
    png.unlink(missing_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.6", "-i", str(edited), "-frames:v", "1",
                    str(out / "thumb_1.jpg")])
    up = story["upload"]
    (out / "metadata.json").write_text(json.dumps({"youtube": {"title": up["title"], "description": up["description"],
                                                               "tags": up["tags"]}}, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "notes.txt").write_text(f"{story.get('channel', 'Paper Trail')} - {up['title']}\n", encoding="utf-8")
    (out / "UPLOAD.txt").write_text(
        f"TITLE\n{up['title']}\n\nDESCRIPTION\n{up['description']}\n\nTAGS\n{', '.join(up['tags'])}\n\n"
        f"PINNED COMMENT\n{up.get('pinned', '')}\n\nWHEN YOU UPLOAD\n- Altered or synthetic content: YES (AI voice).\n"
        "- Made for kids: No.\n- Stock clips: Pexels / Pixabay licence (free to use, no credit required).\n", encoding="utf-8")
    say(f"\nDONE: {edited}\nUpload text: {out / 'UPLOAD.txt'}")
    return edited


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("--voice", default="en-US-ChristopherNeural")
    ap.add_argument("--grade", default="money_gold")
    ap.add_argument("--offline-clips", type=Path, help="test with local .mp4 clips instead of Pexels/Pixabay")
    a = ap.parse_args()
    build(Path(a.story), a.voice, grade=a.grade, offline_clips=a.offline_clips)
