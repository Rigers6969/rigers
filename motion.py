"""Motion-graphics Shorts: real animation (things pop, slide, draw themselves, count, bounce),
smooth scene transitions, word-by-word captions, music and sound effects on every move.

A story module (for example motion_apple.py) gives:
  LINES  = [(spoken text, caption text), ...]              one scene per line
  SCENES = [function(c, t, d, k), ...]                     draws scene i; t = seconds into the scene, d = scene length
  SFX    = {scene index: [(seconds into scene, "pop" | "whoosh" | "ching" | "boom" | "tick" | "stamp" | "riser"), ...]}
  BRAND, ACCENT, SLUG, UPLOAD (title / description / tags / pinned), CHANNEL

    python motion.py motion_apple            (needs: pip install skia-python)
"""
from __future__ import annotations

import importlib
import json
import math
import multiprocessing as mp
import random
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import skia

APP = Path(__file__).resolve().parent
W, H, FPS, SR = 1080, 1920, 30, 24000
FONT_FILES = {"anton": APP / "fonts" / "Anton-Regular.ttf", "archivo": APP / "fonts" / "ArchivoBlack-Regular.ttf"}
_typefaces: dict = {}

# ---------------------------------------------------------------- colours + easing

WHITE, INK = (245, 244, 238), (8, 10, 16)
GOLD, GREEN, RED, BLUE, GREY = (243, 196, 72), (92, 222, 140), (236, 72, 72), (110, 170, 255), (140, 148, 162)


def col(rgb, a=1.0) -> int:
    return skia.Color(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(255 * max(0.0, min(1.0, a))))


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def prog(t, start, dur):
    """0..1 progress of an animation that starts at `start` seconds and lasts `dur`."""
    return clamp((t - start) / dur) if dur > 0 else float(t >= start)


def out_cubic(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def in_out(x):
    x = clamp(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def out_back(x, s=1.9):
    x = clamp(x)
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


def out_elastic(x):
    x = clamp(x)
    if x in (0, 1):
        return x
    return 2 ** (-10 * x) * math.sin((x * 10 - 0.75) * (2 * math.pi) / 3) + 1


def lerp(a, b, x):
    return a + (b - a) * x


# ---------------------------------------------------------------- drawing helpers

def paint(rgb=WHITE, a=1.0, stroke=0.0, blur=0.0, cap_round=True) -> skia.Paint:
    p = skia.Paint(AntiAlias=True, Color=col(rgb, a))
    if stroke:
        p.setStyle(skia.Paint.kStroke_Style)
        p.setStrokeWidth(stroke)
        if cap_round:
            p.setStrokeCap(skia.Paint.kRound_Cap)
            p.setStrokeJoin(skia.Paint.kRound_Join)
    if blur:
        p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, blur))
    return p


def font(name: str, size: float) -> skia.Font:
    if name not in _typefaces:
        _typefaces[name] = skia.Typeface.MakeFromFile(str(FONT_FILES[name]))
    f = skia.Font(_typefaces[name], size)
    f.setEdging(skia.Font.Edging.kAntiAlias)
    return f


def text(c, s, x, y, size, rgb=WHITE, a=1.0, face="anton", align="center", scale=1.0, glow=0.0, shadow=True):
    """Text with its visual centre at (x, y)."""
    if a <= 0 or not s:
        return
    f = font(face, size)
    w = f.measureText(s)
    bounds = skia.Rect()
    f.measureText(s, bounds=bounds)
    dx = {"center": -w / 2, "left": 0, "right": -w}[align]
    dy = -(bounds.top() + bounds.bottom()) / 2
    c.save()
    c.translate(x, y)
    c.scale(scale, scale)
    if shadow:
        c.drawString(s, dx + 4, dy + 6, f, paint(INK, 0.55 * a, blur=6))
    if glow:
        c.drawString(s, dx, dy, f, paint(rgb, glow * a, blur=18))
    c.drawString(s, dx, dy, f, paint(rgb, a))
    c.restore()


def text_width(s, size, face="anton"):
    return font(face, size).measureText(s)


def pop(c, x, y, x_prog, fn):
    """Scale-pop a group around (x, y): fn() draws it at its normal size."""
    s = out_back(x_prog)
    if s <= 0.001:
        return
    c.save()
    c.translate(x, y)
    c.scale(s, s)
    c.translate(-x, -y)
    fn()
    c.restore()


def fade(c, a, fn):
    if a <= 0.001:
        return
    if a >= 0.999:
        fn()
        return
    c.saveLayerAlpha(None, int(255 * a))
    fn()
    c.restore()


def rrect(c, x, y, w, h, r, p):
    c.drawRoundRect(skia.Rect.MakeXYWH(x, y, w, h), r, r, p)


def draw_on(c, path: skia.Path, x, p: skia.Paint):
    """Draws the first x (0..1) of a path, like a pen drawing it."""
    if x <= 0:
        return
    m = skia.PathMeasure(path, False)
    out = skia.Path()
    total = 0.0
    lengths = []
    while True:
        lengths.append(m.getLength())
        total += lengths[-1]
        if not m.nextContour():
            break
    m = skia.PathMeasure(path, False)
    left = total * clamp(x)
    for ln in lengths:
        if left <= 0:
            break
        seg = skia.Path()
        m.getSegment(0, min(ln, left), seg, True)  # getSegment replaces its output, so collect each stroke
        out.addPath(seg)
        left -= ln
        if not m.nextContour():
            break
    c.drawPath(out, p)


def person(c, x, y, s, rgb=(30, 36, 52), rim=None, rim_a=1.0, hair=None):
    """Flat person, head and shoulders; (x, y) = bottom centre."""
    p = paint(rgb)
    body = skia.Path()
    body.moveTo(x - 170 * s, y)
    body.cubicTo(x - 170 * s, y - 150 * s, x - 120 * s, y - 210 * s, x, y - 210 * s)
    body.cubicTo(x + 120 * s, y - 210 * s, x + 170 * s, y - 150 * s, x + 170 * s, y)
    body.close()
    c.drawPath(body, p)
    c.drawRect(skia.Rect.MakeXYWH(x - 30 * s, y - 250 * s, 60 * s, 60 * s), p)
    c.drawCircle(x, y - 320 * s, 92 * s, p)
    if hair:
        hp = skia.Path()
        hp.addArc(skia.Rect.MakeXYWH(x - 86 * s, y - 406 * s, 172 * s, 172 * s), 195, 150)
        c.drawPath(hp, paint(hair, 1, stroke=22 * s))
    if rim:
        rp = paint(rim, rim_a, stroke=6 * s)
        c.drawCircle(x, y - 320 * s, 92 * s, rp)
        c.drawPath(body, rp)


def coin(c, x, y, r, a=1.0, spin=0.0):
    sx = max(0.08, abs(math.cos(spin)))
    c.save()
    c.translate(x, y)
    c.scale(sx, 1)
    c.drawCircle(0, 0, r, paint((200, 150, 40), a))
    c.drawCircle(0, 0, r * 0.82, paint(GOLD, a))
    text(c, "$", 0, 0, r * 1.1, (150, 100, 20), a, shadow=False)
    c.restore()


def money_str(v: float) -> str:
    return "$" + f"{int(round(v)):,}"


# ---------------------------------------------------------------- background, captions, frame

def background(c, t, accent):
    shader = skia.GradientShader.MakeLinear([skia.Point(0, 0), skia.Point(0, H)], [col((16, 20, 34)), col((4, 5, 9))])
    c.drawPaint(skia.Paint(Shader=shader))
    glow = paint(accent, 0.10, blur=220)
    c.drawCircle(W / 2 + 120 * math.sin(t * 0.3), 760 + 60 * math.cos(t * 0.23), 420, glow)
    grid = paint((255, 255, 255), 0.035, stroke=2, cap_round=False)
    off = (t * 18) % 90
    for y in np.arange(-90 + off, H, 90):
        c.drawLine(0, y, W, y, grid)
    rng = random.Random(7)
    for i in range(46):  # floating dust
        px = (rng.random() * W + t * (8 + 14 * rng.random())) % W
        py = (rng.random() * H - t * (10 + 25 * rng.random())) % H
        c.drawCircle(px, py, 1.5 + 2.5 * rng.random(), paint(accent if i % 5 == 0 else WHITE, 0.10 + 0.25 * rng.random()))


def caption_chunks(caption: str, n: int = 3):
    out, cur = [], []
    for w in caption.split():
        cur.append(w)
        if len(cur) >= n or w.endswith((".", "?", ",", "!")):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def word_times(lines, starts):
    """Every caption word with its estimated time (spread over the spoken line by length)."""
    items = []
    for (spoken, cap), (a, z) in zip(lines, starts):
        chunks = caption_chunks(cap)
        words = [w for ch in chunks for w in ch]
        weights = [len(re.sub(r"\W", "", w)) + 2 for w in words]
        tot, tt, k = sum(weights), a, 0
        for ch in chunks:
            block = []
            for w in ch:
                L = (z - a) * weights[k] / tot
                block.append((w, tt, tt + L))
                tt += L
                k += 1
            items.append(block)
    return items


def draw_captions(c, t, blocks, accent):
    for block in blocks:
        if block[0][1] <= t < block[-1][2] + 0.05:
            size = 104
            words = [w.upper() for w, _, _ in block]
            gap = 26
            widths = [text_width(w, size) for w in words]
            total = sum(widths) + gap * (len(words) - 1)
            rows = [list(range(len(words)))]
            if total > W - 120:
                h = (len(words) + 1) // 2
                rows = [list(range(h)), list(range(h, len(words)))]
            y = 1500 - (len(rows) - 1) * 62
            for row in rows:
                rw = sum(widths[i] for i in row) + gap * (len(row) - 1)
                x = (W - rw) / 2
                for i in row:
                    w, a, z = block[i]
                    shown = t >= a - 0.04
                    active = a - 0.04 <= t < z
                    hot = any(ch.isdigit() for ch in w) or (w.strip(".,?!'\"").isupper() and len(w.strip(".,?!'\"")) > 1)
                    if shown:
                        s = 0.7 + 0.3 * out_back(prog(t, a - 0.04, 0.14))
                        if active:
                            s *= 1.08
                        colr = accent if (hot or active) else WHITE
                        cx = x + widths[i] / 2
                        c.save()
                        c.translate(cx, y)
                        c.scale(s, s)
                        f = font("anton", size)
                        bounds = skia.Rect()
                        f.measureText(w.upper(), bounds=bounds)
                        dy = -(bounds.top() + bounds.bottom()) / 2
                        outline = paint(INK, 1, stroke=16)
                        c.drawString(w.upper(), -widths[i] / 2, dy, f, outline)
                        c.drawString(w.upper(), -widths[i] / 2, dy, f, paint(colr))
                        c.restore()
                    x += widths[i] + gap
                y += 124
            return


class Ctx:
    """What a scene function gets as `k`: the accent colour and helpers."""
    def __init__(self, accent):
        self.accent = accent


def render_frame(story, fno, starts, blocks, dur):
    surface = skia.Surface(W, H)
    c = surface.getCanvas()
    t = fno / FPS
    k = Ctx(story.ACCENT)
    background(c, t, story.ACCENT)
    i = max([j for j, (a, _) in enumerate(starts) if t >= a - 0.12] or [0])
    a = starts[i][0] - 0.12
    end = starts[i + 1][0] - 0.12 if i + 1 < len(starts) else dur
    lt, sd = max(0.0, t - a), end - a
    # camera: slow push-in + a little drift; a kick on scene start
    kick = 1 - out_cubic(prog(lt, 0, 0.45))
    z = 1.0 + 0.035 * (lt / max(1.0, sd)) + 0.06 * kick
    c.save()
    c.translate(W / 2, 800)
    c.scale(z, z)
    c.rotate(0.6 * math.sin(t * 0.7))
    c.translate(-W / 2, -800)
    # circle wipe into each new scene
    wipe = prog(lt, 0, 0.32)
    if i > 0 and wipe < 1:
        c.save()
        clip = skia.Path()
        clip.addCircle(W / 2, 800, 40 + 1500 * in_out(wipe))
        c.clipPath(clip, doAntiAlias=True)
        story.SCENES[i](c, lt, sd, k)
        c.restore()
        ring = paint(story.ACCENT, 1 - wipe, stroke=26 * (1 - wipe) + 2)
        c.drawCircle(W / 2, 800, 40 + 1500 * in_out(wipe), ring)
    else:
        story.SCENES[i](c, lt, sd, k)
    c.restore()
    # brand + captions + progress
    bf = font("archivo", 30)
    bw = bf.measureText(story.BRAND)
    rrect(c, 56, 118, bw + 48, 62, 14, paint(INK, 0.85))
    rrect(c, 56, 118, bw + 48, 62, 14, paint(story.ACCENT, 1, stroke=3))
    c.drawString(story.BRAND, 80, 160, bf, paint(story.ACCENT))
    draw_captions(c, t, blocks, story.ACCENT)
    c.drawRect(skia.Rect.MakeXYWH(0, H - 12, W * t / dur, 12), paint(story.ACCENT))
    img = surface.makeImageSnapshot()
    return img.toarray(colorType=skia.ColorType.kRGBA_8888_ColorType)[:, :, :3]


def _render_segment(args):
    mod, f0, f1, starts, blocks, dur, out = args
    story = importlib.import_module(mod)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                           "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", out],
                          stdin=subprocess.PIPE)
    for fno in range(f0, f1):
        ff.stdin.write(np.ascontiguousarray(render_frame(story, fno, starts, blocks, dur)).tobytes())
    ff.stdin.close()
    ff.wait()
    return out


# ---------------------------------------------------------------- sound

def soundtrack(n, starts, sfx, seed=5):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / SR
    out = np.zeros(n, np.float32)
    bpm = 96
    beat = 60 / bpm
    bass_notes = [55.0, 55.0, 65.41, 49.0]  # A, A, C, G
    L = int(SR * beat)
    tt = np.arange(L) / SR
    kick = np.sin(2 * np.pi * (45 + 90 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 9)
    hat_len = int(SR * 0.05)
    hat = np.diff(rng.standard_normal(hat_len) * np.exp(-np.arange(hat_len) / SR * 90), prepend=0)
    k = 0
    while k * beat < n / SR - beat:
        s = int(k * beat * SR)
        e = min(n, s + L)
        f = bass_notes[(k // 4) % 4]
        bass = (np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * 2 * f * tt)) * np.minimum(1, tt * 40) * np.exp(-tt * 2.2)
        out[s:e] += 0.16 * bass[: e - s] + 0.42 * kick[: e - s]
        for off in (0.5,):
            hs = int((k + off) * beat * SR)
            if hs + hat_len < n:
                out[hs:hs + hat_len] += 0.06 * hat
        k += 1
    pad = 0.035 * (np.sin(2 * np.pi * 220 * t) + np.sin(2 * np.pi * 261.6 * t) + np.sin(2 * np.pi * 329.6 * t)) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.1 * t))
    out += pad

    def put(at, sig, amp):
        s = int(at * SR)
        if 0 <= s < n:
            e = min(n, s + len(sig))
            out[s:e] += amp * sig[: e - s]

    def env(sec, decay):
        q = np.arange(int(SR * sec)) / SR
        return q, np.exp(-q * decay)

    q, e = env(0.12, 30)
    s_pop = np.sin(2 * np.pi * (600 + 900 * q / 0.12) * q) * e
    q, e = env(0.9, 4)
    s_ching = (np.sin(2 * np.pi * 2093 * q) + 0.7 * np.sin(2 * np.pi * 2637 * q) + 0.5 * np.sin(2 * np.pi * 3136 * q)) * e
    s_ching[: int(SR * 0.03)] += rng.standard_normal(int(SR * 0.03)) * 0.6
    q, e = env(1.2, 3.2)
    s_boom = np.sin(2 * np.pi * (36 + 70 * np.exp(-q * 9)) * q) * e + 0.3 * rng.standard_normal(len(q)) * np.exp(-q * 22)
    q, e = env(0.02, 250)
    s_tick = np.sin(2 * np.pi * 2600 * q) * e
    q, e = env(0.35, 12)
    s_stamp = np.sin(2 * np.pi * (70 + 120 * np.exp(-q * 30)) * q) * e + 0.5 * rng.standard_normal(len(q)) * np.exp(-q * 40)
    Lw = int(SR * 0.42)
    nz = rng.standard_normal(Lw)
    s_whoosh = (nz - np.convolve(nz, np.ones(12) / 12, "same")) * np.sin(np.pi * np.arange(Lw) / Lw) ** 2
    Lr = int(SR * 1.2)
    qr = np.arange(Lr) / SR
    s_riser = (rng.standard_normal(Lr) * 0.5 + np.sin(2 * np.pi * (200 + 900 * qr / 1.2) * qr)) * (qr / 1.2) ** 2
    lib = {"pop": (s_pop, 0.30), "ching": (s_ching, 0.28), "boom": (s_boom, 0.55), "tick": (s_tick, 0.25),
           "stamp": (s_stamp, 0.5), "whoosh": (s_whoosh, 0.16), "riser": (s_riser, 0.16)}
    for i, (a, _) in enumerate(starts):
        if i:
            put(a - 0.12 - 0.15, s_whoosh, 0.16)
        for off, name in sfx.get(i, []):
            sig, amp = lib[name]
            put(a - 0.12 + off - (1.2 if name == "riser" else 0), sig, amp)
    fi, fo = int(SR * 0.3), int(SR * 0.4)
    out[:fi] *= np.linspace(0, 1, fi)
    out[-fo:] *= np.linspace(1, 0, fo)
    return out


# ---------------------------------------------------------------- build

def build(module: str, voice: str = "en-US-AndrewNeural", rate: str = "+10%", workers: int = 4) -> Path:
    sys.path.insert(0, str(APP))
    story = importlib.import_module(module)
    from photo_short import trim, voice_lines

    out_dir = APP / "content" / story.SLUG
    out_dir.mkdir(parents=True, exist_ok=True)
    print("1/4  Recording the voice...", flush=True)
    lines = [trim(v) for v in voice_lines([s for s, _ in story.LINES], voice, rate)]
    gap, lead = 0.10, 0.25
    parts, starts, t = [np.zeros(int(SR * lead), np.float32)], [], lead
    for v in lines:
        starts.append((t, t + len(v) / SR))
        parts += [v, np.zeros(int(SR * gap), np.float32)]
        t += len(v) / SR + gap
    parts.append(np.zeros(int(SR * 0.35), np.float32))
    vo = np.concatenate(parts)
    vo = vo / (np.abs(vo).max() + 1e-9) * 0.9
    n = len(vo)
    mix = vo + 0.8 * soundtrack(n, starts, story.SFX)
    mix = mix / (np.abs(mix).max() + 1e-9) * 0.95
    wav = out_dir / "audio.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    dur = n / SR
    blocks = word_times(story.LINES, starts)
    nframes = int(dur * FPS)
    print(f"2/4  Animating {nframes} frames ({dur:.1f} s) on {workers} cores...", flush=True)
    cuts = [round(nframes * j / workers) for j in range(workers + 1)]
    segs = [(module, cuts[j], cuts[j + 1], starts, blocks, dur, str(out_dir / f"seg{j}.mp4")) for j in range(workers)]
    with mp.get_context("spawn").Pool(workers) as pool:
        files = pool.map(_render_segment, segs)
    lst = out_dir / "segs.txt"
    lst.write_text("".join(f"file '{Path(f).name}'\n" for f in files), encoding="utf-8")
    print("3/4  Joining + sound...", flush=True)
    final = out_dir / "final.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(wav),
                    "-c:v", "copy", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-shortest", "-movflags", "+faststart", str(final)], check=True)
    for f in files + [str(lst), str(wav)]:
        Path(f).unlink(missing_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.6", "-i", str(final), "-frames:v", "1", str(out_dir / "thumb_1.jpg")])
    up = story.UPLOAD
    (out_dir / "metadata.json").write_text(json.dumps({"youtube": {"title": up["title"], "description": up["description"], "tags": up["tags"]}},
                                                      indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "notes.txt").write_text(f"{story.CHANNEL} - {up['title']}\n", encoding="utf-8")
    (out_dir / "UPLOAD.txt").write_text(
        f"TITLE\n{up['title']}\n\nDESCRIPTION\n{up['description']}\n\nTAGS\n{', '.join(up['tags'])}\n\nPINNED COMMENT\n{up['pinned']}\n\n"
        "WHEN YOU UPLOAD\n- Altered or synthetic content: YES (the voice is AI). It does not stop monetization.\n- Made for kids: No.\n",
        encoding="utf-8")
    print(f"4/4  DONE: {final}", flush=True)
    return final


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("module")
    ap.add_argument("--voice", default="en-US-AndrewNeural")
    ap.add_argument("--rate", default="+10%")
    a = ap.parse_args()
    build(a.module, a.voice, a.rate)
