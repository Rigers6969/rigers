"""Make a finished YouTube Short from a story file, with real photos from Wikipedia.

    python photo_short.py stories/radium_girls.json

What it does:
  1. Downloads photos used on the Wikipedia pages named in the story. Only free ones
     (public domain or Creative Commons) are used, and their credits go in the description.
  2. Reads every line with a natural voice (edge-tts, already used by Wayne Factory).
  3. Builds the video: moving photos, big captions, number pop-ups, music and sound effects.
  4. Saves it in content/<slug>/ so it shows up in Autopilot -> My videos (play / download).
"""
from __future__ import annotations

import argparse
import asyncio
import html
import io
import json
import math
import random
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

APP = Path(__file__).resolve().parent
W, H, FPS, SR = 1080, 1920, 30, 24000
UA = "WayneFactory/1.0 (personal YouTube tool; photo_short.py)"
FREE = re.compile(r"public domain|^pd|cc0|cc[- ]by", re.I)
SKIP_NAMES = re.compile(r"\.svg$|logo|icon|symbol|flag_of|commons-|wiki|question_book|edit-clear|padlock|ambox|crystal", re.I)

FONT_DIR = APP / "fonts"
ANTON = str(FONT_DIR / "Anton-Regular.ttf")
ARCH = str(FONT_DIR / "ArchivoBlack-Regular.ttf")
_fonts: dict = {}


def font(path: str, size: int):
    key = (path, size)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(path, size)
    return _fonts[key]


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def say(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------- photos

def _plain(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def page_images(title: str, session) -> list[dict]:
    """Free-to-use photos on one English Wikipedia page, in the page's own order."""
    r = session.get("https://en.wikipedia.org/w/api.php", timeout=30, params={
        "action": "query", "format": "json", "generator": "images", "titles": title, "gimlimit": "60",
        "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": "1600"})
    r.raise_for_status()
    pages = (r.json().get("query") or {}).get("pages") or {}
    out = []
    for p in pages.values():
        name = p.get("title", "")
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        lic = _plain((meta.get("LicenseShortName") or {}).get("value", ""))
        if SKIP_NAMES.search(name) or info.get("mime") not in ("image/jpeg", "image/png"):
            continue
        if str((meta.get("NonFree") or {}).get("value", "")).lower() == "true" or not FREE.search(lic):
            continue
        if min(info.get("width", 0), info.get("height", 0)) < 400:
            continue
        out.append({"name": name, "url": info.get("thumburl") or info.get("url"), "license": lic,
                    "artist": _plain((meta.get("Artist") or {}).get("value", "")) or "unknown",
                    "page": info.get("descriptionurl", ""), "w": info.get("width"), "h": info.get("height")})
    return out


def pick_photos(scenes: list[dict], folder: Path, offline: Path | None) -> tuple[list, list]:
    """One photo (or None) per scene, plus the credits list."""
    folder.mkdir(parents=True, exist_ok=True)
    if offline:  # local pictures instead of Wikipedia: scene_01.png, scene_02.jpg ... (missing number = no picture)
        def local(i):
            hits = [p for p in offline.glob(f"scene_{i + 1:02d}.*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
            return Image.open(hits[0]).convert("RGB") if hits else None
        return [local(i) if sc.get("img") else None for i, sc in enumerate(scenes)], []
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = UA
    cache: dict[str, list] = {}
    used: set[str] = set()
    photos, credits = [], []
    for i, sc in enumerate(scenes):
        want = sc.get("img")
        if not want:
            photos.append(None)
            continue
        cands = []
        for page in want.get("pages", []):
            if page not in cache:
                try:
                    cache[page] = page_images(page, s)
                    say(f"  {len(cache[page])} free photos on '{page}'")
                except Exception as exc:
                    say(f"  could not read '{page}': {exc}")
                    cache[page] = []
            cands += [c for c in cache[page] if c["name"] not in used]
        words = [w.lower() for w in want.get("want", [])]
        best = max(cands, key=lambda c: sum(w in c["name"].lower() for w in words), default=None)
        if best and words and not any(w in best["name"].lower() for w in words) and not want.get("any", True):
            best = None
        img = None
        if best:
            try:
                r = s.get(best["url"], timeout=60)
                r.raise_for_status()
                img = Image.open(io.BytesIO(r.content)).convert("RGB")
                img.save(folder / f"scene_{i + 1:02d}.jpg", quality=92)
                used.add(best["name"])
                credits.append(best)
                say(f"  scene {i + 1}: {best['name']}")
            except Exception as exc:
                say(f"  scene {i + 1}: download failed ({exc})")
        photos.append(img)
    return photos, credits


# ---------------------------------------------------------------- voice

def _decode(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768


def voice_lines(texts: list[str], voice: str, rate: str) -> list[np.ndarray]:
    if voice.startswith("kokoro:"):  # offline voice (used for testing)
        from kokoro_onnx import Kokoro
        k = Kokoro(str(APP / "kokoro.onnx"), str(APP / "voices.bin"))
        return [k.create(t, voice=voice.split(":", 1)[1], speed=1.1, lang="en-us")[0].astype(np.float32) for t in texts]
    import edge_tts
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, t in enumerate(texts):
            p = Path(tmp) / f"l{i}.mp3"
            for attempt in range(3):
                try:
                    asyncio.run(edge_tts.Communicate(t, voice, rate=rate).save(str(p)))
                    break
                except Exception:
                    if attempt == 2:
                        raise
            out.append(_decode(p))
            say(f"  voice {i + 1}/{len(texts)}")
    return out


def trim(s: np.ndarray) -> np.ndarray:
    idx = np.where(np.abs(s) > 0.01)[0]
    return s[max(0, idx[0] - 240): idx[-1] + 480] if len(idx) else s


# ---------------------------------------------------------------- music + sfx

def soundtrack(n: int, starts: list, scenes: list, seed: int = 3) -> np.ndarray:
    t = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    out = np.zeros(n, dtype=np.float32)
    out += 0.07 * (np.sin(2 * np.pi * 55 * t) + 0.6 * np.sin(2 * np.pi * 82.41 * t)) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.07 * t))
    # slow music box in A minor
    notes = [440, 523.25, 659.25, 587.33, 493.88, 523.25, 440, 392, 349.23, 440, 523.25, 493.88]
    step, k = 0.62, 0
    L = int(SR * 1.6)
    tt = np.arange(L) / SR
    while k * step < n / SR - 1.6:
        f = notes[k % len(notes)]
        tone = (np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(2 * np.pi * 2 * f * tt) + 0.12 * np.sin(2 * np.pi * 3.01 * f * tt)) * np.exp(-tt * 3.2)
        s = int(k * step * SR)
        out[s:s + L] += 0.045 * tone[: max(0, min(L, n - s))]
        k += 1

    def whoosh(at: float, amp: float = 0.12) -> None:
        dur = 0.4
        s, L = int(max(0, at - 0.28) * SR), int(dur * SR)
        if s + L < n:
            noise = rng.standard_normal(L)
            out[s:s + L] += amp * (noise - np.convolve(noise, np.ones(10) / 10, "same")) * np.sin(np.pi * np.arange(L) / L) ** 2

    def boom(at: float, amp: float = 0.45) -> None:
        s, L = int(at * SR), int(SR * 1.1)
        if s + L < n:
            q = np.arange(L) / SR
            out[s:s + L] += amp * (np.sin(2 * np.pi * (40 + 55 * np.exp(-q * 8)) * q) * np.exp(-q * 3.5) + 0.25 * rng.standard_normal(L) * np.exp(-q * 25))

    for i, (a, z) in enumerate(starts):
        if i:
            whoosh(a)
        fx = scenes[i].get("fx") or {}
        if fx.get("type") == "stamp":
            for j in range(len(fx["words"])):
                boom(a + (z - a) * (0.12 + 0.8 * j / len(fx["words"])), 0.3)
        elif fx.get("type") in ("big", "count"):
            boom(a + 0.15, 0.4)
    fi, fo = int(SR * 0.6), int(SR * 1.2)
    out[:fi] *= np.linspace(0, 1, fi)
    out[-fo:] *= np.linspace(1, 0, fo)
    return out


# ---------------------------------------------------------------- pictures

def grade(img: Image.Image, tint: tuple) -> Image.Image:
    """Old-film look: a bit less colour, more contrast, a tint in the shadows."""
    g = ImageOps.autocontrast(img.convert("L"), cutoff=1)
    col = ImageOps.colorize(g, black=(6, 8, 10), white=(250, 246, 236), mid=tint)
    return Image.blend(col, img, 0.25)


BAND_Y, BAND_H = 300, 980


def prepare(photo: Image.Image | None, tint: tuple | None) -> dict | None:
    if photo is None:
        return None
    ph = grade(photo, tint) if tint else photo
    # big version for the moving shot (cover the band with 15% to spare)
    scale = max(W * 1.18 / ph.width, BAND_H * 1.18 / ph.height)
    big = ph.resize((int(ph.width * scale), int(ph.height * scale)), Image.LANCZOS)
    bgs = max(W / ph.width, H / ph.height)
    bg = ph.resize((int(ph.width * bgs) + 2, int(ph.height * bgs) + 2)).crop((0, 0, W, H)).filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (0, 0, 0)), 0.62)
    return {"big": big, "bg": bg}


def band_mask() -> Image.Image:
    m = Image.new("L", (W, BAND_H), 255)
    d = ImageDraw.Draw(m)
    fade = 140
    for y in range(fade):
        v = int(255 * (y / fade) ** 1.5)
        d.line([(0, y), (W, y)], fill=v)
        d.line([(0, BAND_H - 1 - y), (W, BAND_H - 1 - y)], fill=v)
    return m


def grain_tiles(k: int = 6) -> list:
    rng = np.random.default_rng(1)
    return [Image.fromarray(rng.integers(0, 255, (H // 2, W // 2), dtype=np.uint8)).resize((W, H)) for _ in range(k)]


def vignette() -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W * 0.8)) ** 2 + ((yy - H / 2) / (H * 0.72)) ** 2)
    return Image.fromarray((np.clip(1.1 - r * 0.7, 0.3, 1.0) * 255).astype(np.uint8))


def text(d, xy, s, f, fill, anchor="mm", stroke=0, sfill=(0, 0, 0)):
    d.text(xy, s, font=f, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=sfill)


def draw_fx(img: Image.Image, fx: dict, p: float, lt: float, accent: tuple) -> None:
    if not fx:
        return
    d = ImageDraw.Draw(img, "RGBA")
    kind = fx.get("type")
    cy = BAND_Y + BAND_H // 2
    if kind == "tag":
        a = ease(lt / 0.4)
        x = int(-500 + 560 * a)
        tw = d.textlength(fx["text"], font=font(ARCH, 40))
        d.rectangle([x, BAND_Y + 90, x + tw + 50, BAND_Y + 160], fill=(8, 10, 12, 220))
        d.rectangle([x, BAND_Y + 90, x + 10, BAND_Y + 160], fill=accent)
        text(d, (x + 30, BAND_Y + 125), fx["text"], font(ARCH, 40), (245, 245, 240), anchor="lm")
    elif kind == "stamp":
        words = fx["words"]
        for j, w in enumerate(words):
            t0 = 0.12 + 0.8 * j / len(words)
            if p < t0:
                break
            s = ease((p - t0) / 0.05)
            size = int(150 * (1.6 - 0.6 * s))
            y = cy - 230 + j * 230
            d.rectangle([150, y - 95, W - 150, y + 95], fill=(0, 0, 0, int(170 * s)))
            text(d, (W // 2, y), w, font(ANTON, size), accent if j == len(words) - 1 else (250, 248, 240), stroke=6)
    elif kind in ("big", "count"):
        a = ease(lt / 0.35)
        d.rectangle([0, BAND_Y, W, BAND_Y + BAND_H], fill=(0, 0, 0, int(120 * a)))
        if kind == "count":
            v = int(fx["to"] * ease(lt / 1.4))
            main = f"{fx.get('prefix', '')}{v:,}{fx.get('suffix', '')}"
        else:
            main = fx["text"]
        size = int(fx.get("size", 230) * (1.25 - 0.25 * a))
        text(d, (W // 2, cy - 30), main, font(ANTON, size), accent, stroke=7, sfill=(0, 0, 0))
        if fx.get("sub"):
            text(d, (W // 2, cy + fx.get("size", 230) * 0.62), fx["sub"], font(ARCH, 50), (245, 245, 240, int(255 * a)), stroke=4)


def chunks(caption: str, n: int = 3) -> list:
    out, cur = [], []
    for w in caption.split():
        cur.append(w)
        if len(cur) >= n or w.endswith((".", "?", ",", "!")):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def draw_caption(img: Image.Image, words: list, age: float, accent: tuple) -> None:
    d = ImageDraw.Draw(img)
    f = font(ANTON, int(108 * (0.86 + 0.14 * ease(age / 0.12))))
    sp = d.textlength(" ", font=f)
    ws = [d.textlength(w.upper(), font=f) for w in words]
    rows = [list(range(len(words)))]
    if sum(ws) + sp * (len(words) - 1) > W - 110:
        h = (len(words) + 1) // 2
        rows = [list(range(h)), list(range(h, len(words)))]
    y = 1475 - (len(rows) - 1) * 62
    for row in rows:
        x = (W - sum(ws[i] for i in row) - sp * (len(row) - 1)) / 2
        for i in row:
            w = words[i]
            hot = w.strip(".,?!'\"").isupper() and len(w.strip(".,?!'\"")) > 1 or any(c.isdigit() for c in w)
            d.text((x, y), w.upper(), font=f, fill=accent if hot else (250, 250, 245), stroke_width=9, stroke_fill=(0, 0, 0), anchor="ls")
            x += ws[i] + sp
        y += 124


# ---------------------------------------------------------------- main

def build(story_path: Path, offline: Path | None = None, voice: str | None = None, no_grade: bool = False) -> Path:
    story = json.loads(story_path.read_text(encoding="utf-8"))
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is missing. Open PowerShell, type:  winget install Gyan.FFmpeg  then close it and try again.")
    slug = story["slug"]
    out_dir = APP / "content" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    scenes = story["scenes"]
    accent = tuple(story.get("accent", [150, 255, 110]))
    tint = tuple(story.get("tint", [70, 96, 84]))

    say("1/4  Getting photos from Wikipedia...")
    photos, credits = pick_photos(scenes, out_dir / "photos", offline)
    say(f"     {sum(p is not None for p in photos)} of {sum(1 for s in scenes if s.get('img'))} scenes have a photo")

    say("2/4  Recording the voice...")
    lines = [trim(v) for v in voice_lines([s["say"] for s in scenes], voice or story.get("voice", "en-US-AndrewNeural"),
                                           story.get("rate", "+6%"))]
    gap, lead = 0.14, 0.3
    parts, starts, t = [np.zeros(int(SR * lead), np.float32)], [], lead
    for v in lines:
        starts.append((t, t + len(v) / SR))
        parts += [v, np.zeros(int(SR * gap), np.float32)]
        t += len(v) / SR + gap
    parts.append(np.zeros(int(SR * 1.0), np.float32))
    vo = np.concatenate(parts)
    vo = vo / (np.abs(vo).max() + 1e-9) * 0.9
    mix = vo + soundtrack(len(vo), starts, scenes)
    mix = mix / (np.abs(mix).max() + 1e-9) * 0.95
    wav = out_dir / "audio.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    dur = len(vo) / SR

    caps = []
    for (a, z), sc in zip(starts, scenes):
        ch = chunks(sc.get("cap", sc["say"]))
        wts = [sum(len(x) for x in c) + 2 for c in ch]
        tt = a
        for c, wt in zip(ch, wts):
            caps.append((tt, tt + (z - a) * wt / sum(wts), c))
            tt += (z - a) * wt / sum(wts)

    say(f"3/4  Building the video ({dur:.0f} seconds)...")
    prepped = [prepare(p, None if no_grade else tint) for p in photos]
    plain_bg = Image.new("RGB", (W, H), (8, 10, 12))
    mask, grains, vig = band_mask(), grain_tiles(), vignette()
    black = Image.new("RGB", (W, H), (0, 0, 0))
    silent = out_dir / "video_silent.mp4"
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                           "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", str(silent)],
                          stdin=subprocess.PIPE)
    nframes = int(dur * FPS)
    last_photo = None
    for fno in range(nframes):
        t = fno / FPS
        i = max([k for k, (a, _) in enumerate(starts) if t >= a - 0.1] or [0])
        a, _ = starts[i]
        end = starts[i + 1][0] if i + 1 < len(starts) else dur
        lt, p = max(0.0, t - a), clamp((t - a) / max(0.1, end - a))
        sc = scenes[i]
        pr = prepped[i] or (last_photo if sc.get("keep_photo") else None)
        if prepped[i]:
            last_photo = prepped[i]
        if pr:
            frame = pr["bg"].copy()
            big = pr["big"]
            z = 1.0 + 0.12 * (p if i % 2 == 0 else 1 - p)  # slow zoom in / out
            cw = min(big.width, big.height * W / BAND_H) * 0.86 / z
            chh = cw * BAND_H / W
            pan = (p - 0.5) * (big.width - cw) * 0.5 * (1 if i % 3 else -1)
            x0 = (big.width - cw) / 2 + pan
            y0 = (big.height - chh) / 2
            shot = big.resize((W, BAND_H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + chh))
            frame.paste(shot, (0, BAND_Y), mask)
        else:
            frame = plain_bg.copy()
            dd = ImageDraw.Draw(frame)
            for y in range(0, H, 64):
                dd.line([(0, y), (W, y)], fill=(15, 18, 22), width=2)
        if i == 0 and lt < 2.5:  # radium glow pulse on the hook
            glow = Image.new("RGB", (W, H), accent)
            frame = Image.blend(frame, glow, 0.10 * (0.5 + 0.5 * math.sin(lt * 5)) * (1 - lt / 2.5))
        draw_fx(frame, sc.get("fx"), p, lt, accent)
        frame = Image.composite(frame, black, vig)
        frame = Image.blend(frame, Image.merge("RGB", [grains[fno % len(grains)]] * 3), 0.045)
        d = ImageDraw.Draw(frame)
        d.rounded_rectangle([60, 130, 60 + 24 + d.textlength(story["brand"], font=font(ARCH, 32)) + 24, 190], 12, fill=(12, 14, 16), outline=accent, width=3)
        d.text((84, 160), story["brand"], font=font(ARCH, 32), fill=accent, anchor="lm")
        if 0 <= t - a < 0.1 and i:
            frame = Image.blend(frame, Image.new("RGB", (W, H), (255, 255, 255)), 0.15 * (1 - (t - a) / 0.1))
        for c0, c1, words in caps:
            if c0 <= t < c1:
                draw_caption(frame, words, t - c0, accent)
                break
        d = ImageDraw.Draw(frame)
        d.rectangle([0, H - 12, int(W * t / dur), H], fill=accent)
        ff.stdin.write(frame.tobytes())
        if fno % 150 == 0:
            say(f"     {int(100 * fno / nframes)}%")
        if fno == int(1.2 * FPS):
            frame.save(out_dir / "thumb_1.jpg", quality=92)
    ff.stdin.close()
    ff.wait()

    say("4/4  Adding the sound...")
    final = out_dir / "final.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav), "-c:v", "copy",
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
                    "-movflags", "+faststart", str(final)], check=True)
    silent.unlink(missing_ok=True)
    wav.unlink(missing_ok=True)

    up = story["upload"]
    credit_lines = [f"- {c['name'].replace('File:', '')} by {c['artist']} ({c['license']}) {c['page']}" for c in credits]
    desc = up["description"] + ("\n\nPhotos (Wikimedia Commons):\n" + "\n".join(credit_lines) if credit_lines else "")
    (out_dir / "metadata.json").write_text(json.dumps({"youtube": {"title": up["title"], "description": desc, "tags": up["tags"]}},
                                                      indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "notes.txt").write_text(f"{story['channel']} - {up['title']}\n", encoding="utf-8")
    (out_dir / "UPLOAD.txt").write_text(
        f"TITLE\n{up['title']}\n\nDESCRIPTION\n{desc}\n\nTAGS\n{', '.join(up['tags'])}\n\nPINNED COMMENT\n{up.get('pinned', '')}\n\n"
        "WHEN YOU UPLOAD\n- Altered or synthetic content: YES (the voice is AI). It does not stop monetization.\n"
        "- Made for kids: No.\n- Keep the photo credits in the description.\n", encoding="utf-8")
    say(f"\nDONE: {final}\nUpload text: {out_dir / 'UPLOAD.txt'}")
    return final


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("--offline-images", type=Path, help="test with local pictures instead of Wikipedia")
    ap.add_argument("--voice", help="edge-tts voice, e.g. en-US-AndrewNeural")
    ap.add_argument("--no-grade", action="store_true", help="keep the pictures' own colours (for drawn pictures)")
    a = ap.parse_args()
    build(Path(a.story), a.offline_images, a.voice, a.no_grade)
