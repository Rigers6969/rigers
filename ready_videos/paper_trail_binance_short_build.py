"""Paper Trail Short: the $6.3B Binance heist. Voice (Kokoro, offline), animated graphics (Pillow), synth music + sfx, ffmpeg."""
import math
import random
import subprocess
import sys

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS, SR = 1080, 1920, 30, 24000
FONTS = "/home/user/rigers/fonts/"
ANTON = FONTS + "Anton-Regular.ttf"
ARCH = FONTS + "ArchivoBlack-Regular.ttf"
INTER = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"
RED, GOLD, ICE, WHITE, GREY = (232, 52, 52), (243, 196, 72), (110, 196, 255), (245, 245, 245), (140, 146, 158)

LINES = [  # (spoken, caption)
    ("Someone just stole six point three billion dollars, from the biggest crypto exchange on Earth.",
     "Someone just stole $6.3 BILLION from the biggest crypto exchange on Earth."),
    ("And it took them about twenty minutes.", "And it took them about 20 MINUTES."),
    ("October twenty ninth. Just after eight p.m. U.T.C. Binance's hot wallets start draining.",
     "October 29. Just after 8 PM UTC. Binance's hot wallets start DRAINING."),
    ("Three hours later. A second wave.", "Three hours later... a SECOND WAVE."),
    ("Binance says it started with one laptop. A single engineer's computer, compromised.",
     "Binance says it started with ONE LAPTOP. A single engineer's computer, compromised."),
    ("Tether and Circle froze nearly three billion dollars.", "Tether and Circle FROZE nearly $3 BILLION."),
    ("But about three point three billion is still out there, moving across about ten blockchains.",
     "But about $3.3 BILLION is still out there, moving across about 10 BLOCKCHAINS."),
    ("Blockchain firm T.R.M. Labs has linked the attack to North Korea's Trader Traitor group. No government has confirmed it yet.",
     "Blockchain firm TRM Labs has linked the attack to NORTH KOREA's TraderTraitor group. No government has CONFIRMED it yet."),
    ("The old record? Bybit, twenty twenty five. About one point five billion. This is four times bigger.",
     "The old record? Bybit, 2025. About $1.5 BILLION. This is 4X BIGGER."),
    ("Binance says it will cover users' losses.", "Binance says it will COVER users' losses."),
    ("So where is the missing three point three billion going? Follow for part two.",
     "So where is the missing $3.3 BILLION going? Follow for PART 2."),
]
GAP = 0.12

font_cache = {}


def F(path, size):
    key = (path, size)
    if key not in font_cache:
        font_cache[key] = ImageFont.truetype(path, size)
    return font_cache[key]


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def clamp(x):
    return max(0.0, min(1.0, x))


# ---------------- audio ----------------
def make_voice():
    from kokoro_onnx import Kokoro
    k = Kokoro("kokoro.onnx", "voices.bin")
    parts, starts, t = [], [], 0.35
    lead = np.zeros(int(SR * 0.35), dtype=np.float32)
    parts.append(lead)
    for spoken, _ in LINES:
        s, sr = k.create(spoken, voice="am_michael", speed=1.12, lang="en-us")
        assert sr == SR
        s = s.astype(np.float32)
        # trim silence at both ends
        idx = np.where(np.abs(s) > 0.01)[0]
        s = s[max(0, idx[0] - 200): idx[-1] + 400]
        starts.append((t, t + len(s) / SR))
        parts.append(s)
        parts.append(np.zeros(int(SR * GAP), dtype=np.float32))
        t += len(s) / SR + GAP
    parts.append(np.zeros(int(SR * 1.2), dtype=np.float32))
    v = np.concatenate(parts)
    v = v / (np.abs(v).max() + 1e-9) * 0.9
    return v, starts


def music_and_sfx(n, starts):
    t = np.arange(n) / SR
    rng = np.random.default_rng(7)
    out = np.zeros(n, dtype=np.float32)
    # dark drone: A1 + E2 with slow wobble
    drone = 0.5 * np.sin(2 * np.pi * 55 * t) + 0.3 * np.sin(2 * np.pi * 82.4 * t + 0.4 * np.sin(2 * np.pi * 0.2 * t))
    drone += 0.15 * np.sin(2 * np.pi * 110 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.11 * t))
    out += 0.10 * drone
    # pulse, 100 bpm
    beat = 60 / 100
    kick_len = int(SR * 0.25)
    kt = np.arange(kick_len) / SR
    kick = np.sin(2 * np.pi * (45 + 80 * np.exp(-kt * 25)) * kt) * np.exp(-kt * 12)
    hat_len = int(SR * 0.04)
    hat = rng.standard_normal(hat_len) * np.exp(-np.arange(hat_len) / SR * 120)
    hat = np.diff(hat, prepend=0)
    b = 0.0
    i = 0
    while b < n / SR - 1:
        s = int(b * SR)
        e = min(n, s + kick_len)
        out[s:e] += 0.35 * kick[: e - s]
        hs = int((b + beat / 2) * SR)
        he = min(n, hs + hat_len)
        if hs < n:
            out[hs:he] += 0.05 * hat[: he - hs]
        b += beat
        i += 1
    # ticking clock during line 2
    a, z = starts[1]
    for k in range(int((z - a + 0.6) / 0.25)):
        s = int((a + k * 0.25) * SR)
        L = int(SR * 0.015)
        if s + L < n:
            out[s:s + L] += 0.25 * np.sin(2 * np.pi * 2400 * np.arange(L) / SR) * np.exp(-np.arange(L) / SR * 300)

    def whoosh(at, dur=0.45, amp=0.18):
        s = int(max(0, at - dur * 0.7) * SR)
        L = int(dur * SR)
        if s + L >= n:
            return
        noise = rng.standard_normal(L)
        env = np.sin(np.pi * np.arange(L) / L) ** 2
        # crude rising band: diff of running mean
        k = np.cumsum(noise)
        sm = (k[8:] - k[:-8]) / 8
        sm = np.concatenate([sm, np.zeros(8)])
        sig = noise - sm
        out[s:s + L] += amp * sig * env

    def boom(at, amp=0.6):
        s = int(at * SR)
        L = int(SR * 1.2)
        if s + L >= n:
            return
        tt = np.arange(L) / SR
        sig = np.sin(2 * np.pi * (38 + 60 * np.exp(-tt * 8)) * tt) * np.exp(-tt * 3.5)
        sig += 0.3 * rng.standard_normal(L) * np.exp(-tt * 20)
        out[s:s + L] += amp * sig

    for a, _ in starts[1:]:
        whoosh(a)
    boom(starts[0][0] + 1.25)
    boom(starts[8][0] + (starts[8][1] - starts[8][0]) * 0.8, 0.5)
    boom(starts[5][0] + 0.9, 0.35)
    # fade in/out
    fi = int(SR * 0.5)
    out[:fi] *= np.linspace(0, 1, fi)
    fo = int(SR * 1.0)
    out[-fo:] *= np.linspace(1, 0, fo)
    return out


# ---------------- visuals ----------------
def make_background():
    bg = Image.new("RGB", (W, H), (7, 9, 13))
    d = ImageDraw.Draw(bg)
    for y in range(0, H, 64):  # ledger lines: the "paper trail"
        d.line([(0, y), (W, y)], fill=(16, 20, 28), width=2)
    for x in range(0, W, 64):
        d.line([(x, 0), (x, H)], fill=(12, 15, 21), width=1)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W / 2 - 520, 420, W / 2 + 520, 1340], fill=(70, 14, 14))
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    bg = Image.fromarray(np.clip(np.asarray(bg, dtype=np.int16) + np.asarray(glow, dtype=np.int16), 0, 255).astype(np.uint8))
    # vignette
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.7)) ** 2)
    vig = np.clip(1.15 - r * 0.75, 0.25, 1.0)[..., None]
    arr = (np.asarray(bg, dtype=np.float32) * vig).astype(np.uint8)
    bg = Image.fromarray(arr)
    d = ImageDraw.Draw(bg)
    # top brand bar
    d.rounded_rectangle([60, 120, 360, 184], 14, fill=RED)
    d.text((210, 152), "PAPER TRAIL", font=F(ARCH, 34), fill=WHITE, anchor="mm")
    d.text((390, 152), "BREAKING  ·  30 OCT 2026", font=F(INTER, 30), fill=GREY, anchor="lm")
    return bg


def ctext(d, xy, text, font, fill, anchor="mm", stroke=0, sfill=(0, 0, 0)):
    d.text(xy, text, font=font, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=sfill)


def money(v):
    return f"${v:.1f}B"


def scene(idx, p, lt, d, img):
    """p = progress 0..1 through the line, lt = seconds into the line."""
    cx = W // 2
    if idx == 0:  # counter
        v = 6.3 * ease(lt / 1.25)
        shake = 0
        if 1.25 < lt < 1.6:
            shake = int(14 * math.sin(lt * 90) * (1.6 - lt) / 0.35)
        ctext(d, (cx + shake, 760), money(v), F(ANTON, 300), RED, stroke=6, sfill=(40, 0, 0))
        a = clamp((lt - 1.3) / 0.3)
        if a > 0:
            ctext(d, (cx, 960), "STOLEN", F(ARCH, 110), tuple(int(c * a) for c in WHITE))
            ctext(d, (cx, 1060), "from the world's biggest crypto exchange", F(INTER, 40), tuple(int(c * a) for c in GREY))
    elif idx == 1:  # stopwatch
        r = 300
        box = [cx - r, 820 - r, cx + r, 820 + r]
        d.ellipse(box, outline=(50, 56, 66), width=22)
        frac = ease(p * 1.15)
        d.arc(box, -90, -90 + 360 * frac, fill=RED, width=22)
        mins = int(20 * frac)
        secs = int((20 * frac - mins) * 60) if mins < 20 else 0
        ctext(d, (cx, 800), f"{mins:02d}:{secs:02d}", F(ANTON, 190), WHITE)
        ctext(d, (cx, 935), "MINUTES", F(ARCH, 48), GREY)
    elif idx in (2, 3):  # timeline + draining wallet
        y = 560
        d.line([(110, y), (970, y)], fill=(60, 66, 78), width=8)
        marks = [(250, "20:05 UTC", "WAVE 1"), (760, "23:05 UTC", "WAVE 2")]
        for k, (x, t1, t2) in enumerate(marks):
            on = idx == 2 and k == 0 or idx == 3
            pulse = 1 + 0.15 * math.sin(lt * 8) if (k == 0 and idx == 2) or (k == 1 and idx == 3) else 1
            col = RED if on else (60, 66, 78)
            rr = 22 * pulse
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=col)
            ctext(d, (x, y - 70), t1, F(ARCH, 40), WHITE if on else GREY)
            ctext(d, (x, y + 70), t2, F(INTER, 34), RED if on else GREY)
        ctext(d, (cx, 400), "29 OCTOBER 2026", F(INTER, 34), GREY)
        # wallet
        wx0, wy0, wx1, wy1 = cx - 230, 720, cx + 230, 1090
        d.rounded_rectangle([wx0, wy0, wx1, wy1], 36, outline=WHITE, width=10)
        level = 1 - (ease(p) * 0.55 if idx == 2 else 0.55 + ease(p) * 0.4)
        top = wy1 - 14 - (wy1 - wy0 - 28) * level
        d.rounded_rectangle([wx0 + 14, top, wx1 - 14, wy1 - 14], 24, fill=(int(232 * 0.85), 52, 52))
        ctext(d, (cx, (wy0 + wy1) // 2), "HOT WALLET", F(ARCH, 50), WHITE, stroke=3)
        ctext(d, (cx, 1050), f"{int(level * 100)}%", F(ANTON, 50), WHITE)
    elif idx == 4:  # laptop
        a = ease(lt / 0.5)
        sw, sh = 560, 360
        x0, y0 = cx - sw // 2, 600
        d.rounded_rectangle([x0, y0, x0 + sw, y0 + sh], 22, outline=WHITE, width=12, fill=(14, 18, 26))
        d.polygon([(x0 - 80, y0 + sh + 18), (x0 + sw + 80, y0 + sh + 18), (x0 + sw + 40, y0 + sh + 64), (x0 - 40, y0 + sh + 64)], fill=WHITE)
        if p > 0.45:
            blink = (int(lt * 4) % 2) == 0
            col = RED if blink else (150, 30, 30)
            tri = [(cx, y0 + 70), (cx - 110, y0 + 270), (cx + 110, y0 + 270)]
            d.polygon(tri, fill=col)
            ctext(d, (cx, y0 + 205), "!", F(ANTON, 140), WHITE)
            ctext(d, (cx, 1150), "COMPROMISED", F(ARCH, 84), RED)
        else:
            for k in range(6):
                ww = random.Random(k + int(lt * 6)).randint(150, 440)
                d.rectangle([x0 + 50, y0 + 50 + k * 45, x0 + 50 + ww, y0 + 70 + k * 45], fill=(40, 120, 70))
            ctext(d, (cx, 1150), "1 LAPTOP", F(ARCH, 84), tuple(int(c * a) for c in WHITE))
        ctext(d, (cx, 1240), "source: Binance (early findings)", F(INTER, 32), GREY)
    elif idx in (5, 6):  # frozen vs missing bar
        bx0, bx1, by0, by1 = 110, 970, 640, 800
        d.rounded_rectangle([bx0, by0, bx1, by1], 24, fill=RED)
        ctext(d, (cx, 580), "$6.3B TAKEN", F(ARCH, 54), WHITE)
        frozen_w = (bx1 - bx0) * (3.0 / 6.3)
        f = ease(lt / 0.9) if idx == 5 else 1
        if f > 0:
            d.rounded_rectangle([bx0, by0, bx0 + frozen_w * f, by1], 24, fill=ICE)
        if idx == 5:
            ctext(d, (bx0 + frozen_w / 2, 900), "FROZEN", F(ARCH, 62), ICE)
            ctext(d, (bx0 + frozen_w / 2, 975), "~$3B", F(ANTON, 90), WHITE)
            ctext(d, (cx, 1130), "Tether ~$1.57B  ·  Circle ~$0.8B", F(INTER, 38), GREY)
        else:
            ctext(d, (bx0 + frozen_w / 2, 900), "FROZEN ~$3B", F(ARCH, 40), ICE)
            mx = bx0 + frozen_w + (bx1 - bx0 - frozen_w) / 2
            pulse = 1 + 0.06 * math.sin(lt * 7)
            ctext(d, (mx, 905), "MISSING", F(ARCH, int(58 * pulse)), RED)
            ctext(d, (mx, 985), "~$3.3B", F(ANTON, int(92 * pulse)), WHITE)
            # 10 chain nodes with moving coins
            nodes = [(cx + 360 * math.cos(2 * math.pi * k / 10 + 0.3), 1215 + 115 * math.sin(2 * math.pi * k / 10 + 0.3)) for k in range(10)]
            shown = int(clamp(p * 1.6) * 10)
            for k in range(shown):
                a1, a2 = nodes[k], nodes[(k + 3) % 10]
                d.line([a1, a2], fill=(80, 30, 30), width=3)
                q = (lt * 0.8 + k * 0.17) % 1
                px, py = a1[0] + (a2[0] - a1[0]) * q, a1[1] + (a2[1] - a1[1]) * q
                d.ellipse([px - 9, py - 9, px + 9, py + 9], fill=GOLD)
            for k in range(shown):
                x, y = nodes[k]
                d.ellipse([x - 22, y - 22, x + 22, y + 22], fill=(26, 30, 40), outline=RED, width=5)
            ctext(d, (cx, 1215), f"{shown} CHAINS", F(ARCH, 44), WHITE)
    elif idx == 7:  # attribution card
        a = ease(lt / 0.5)
        x0, y0, x1, y1 = 100, 520, 980, 1110
        d.rounded_rectangle([x0, y0, x1, y1], 30, fill=(18, 22, 30), outline=(60, 66, 78), width=4)
        ctext(d, (cx, 600), "LINKED TO", F(INTER, 40), GREY)
        ctext(d, (cx, 720), "TRADERTRAITOR", F(ANTON, 130), tuple(int(c * a) for c in RED))
        ctext(d, (cx, 830), "North Korea-linked hacker group", F(INTER, 40), WHITE)
        ctext(d, (cx, 900), "according to TRM Labs", F(INTER, 34), GREY)
        if p > 0.62:
            s = ease((p - 0.62) / 0.12)
            stamp = Image.new("RGBA", (700, 170), (0, 0, 0, 0))
            sd = ImageDraw.Draw(stamp)
            sd.rounded_rectangle([6, 6, 694, 164], 18, outline=GOLD, width=10)
            sd.text((350, 88), "NOT CONFIRMED", font=F(ARCH, 74), fill=GOLD, anchor="mm")
            sz = 1.6 - 0.6 * s
            stamp = stamp.resize((int(700 * sz), int(170 * sz))).rotate(-8, expand=True)
            alpha = stamp.split()[3].point(lambda v: int(v * s))
            stamp.putalpha(alpha)
            img.paste(stamp, (cx - stamp.width // 2, 1020 - stamp.height // 2), stamp)
    elif idx == 8:  # record comparison
        base = 1150
        g1 = ease(clamp((p - 0.15) / 0.3))
        g2 = ease(clamp((p - 0.55) / 0.3))
        hmax = 560
        h1, h2 = hmax * 1.5 / 6.3 * g1, hmax * g2
        d.rectangle([200, base - h1, 460, base], fill=(90, 96, 110))
        d.rectangle([620, base - h2, 880, base], fill=RED)
        ctext(d, (330, base + 50), "BYBIT 2025", F(ARCH, 40), GREY)
        ctext(d, (750, base + 50), "BINANCE 2026", F(ARCH, 40), WHITE)
        if g1 > 0:
            ctext(d, (330, base - h1 - 50), "$1.5B", F(ANTON, 70), WHITE)
        if g2 > 0:
            ctext(d, (750, base - h2 - 50), "$6.3B", F(ANTON, 70), WHITE)
        if p > 0.82:
            s = ease((p - 0.82) / 0.1)
            ctext(d, (330, 640), "4X", F(ANTON, int(60 + 140 * s)), GOLD, stroke=5)
        ctext(d, (cx, 470), "BIGGEST CRYPTO HEIST EVER", F(ARCH, 50), WHITE)
    elif idx == 9:  # shield
        a = ease(lt / 0.5)
        sx, sy, s = cx, 800, 260 * (0.8 + 0.2 * a)
        shield = [(sx - s, sy - s), (sx + s, sy - s), (sx + s, sy), (sx, sy + s * 1.25), (sx - s, sy)]
        d.polygon(shield, fill=(20, 60, 40), outline=(90, 220, 140))
        d.line(shield + [shield[0]], fill=(90, 220, 140), width=12)
        d.line([(sx - s * 0.45, sy), (sx - s * 0.1, sy + s * 0.35), (sx + s * 0.5, sy - s * 0.4)], fill=WHITE, width=30)
        ctext(d, (cx, 1200), "$6.34B SET ASIDE", F(ARCH, 64), (90, 220, 140))
        ctext(d, (cx, 1270), "to cover users, says Binance", F(INTER, 36), GREY)
    elif idx == 10:  # question
        pulse = 1 + 0.08 * math.sin(lt * 6)
        ctext(d, (cx, 760), "?", F(ANTON, int(520 * pulse)), RED, stroke=6, sfill=(40, 0, 0))
        ctext(d, (cx, 1060), "WHERE IS THE $3.3B?", F(ARCH, 64), WHITE)
        if p > 0.6:
            ctext(d, (cx, 1160), "FOLLOW FOR PART 2  →", F(ARCH, 52), GOLD)


KEY = ("$", "BILLION", "MINUTES", "DRAINING", "SECOND", "WAVE", "ONE", "LAPTOP", "FROZE", "BLOCKCHAINS", "NORTH", "KOREA",
       "CONFIRMED", "4X", "BIGGER", "COVER", "PART", "2", "10", "20", "29")


def chunks(caption, n=3):
    words = caption.split()
    out, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= n or w.endswith((".", "?", ",")):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def draw_caption(img, words, age):
    d = ImageDraw.Draw(img)
    font = F(ANTON, 104)
    s = 0.85 + 0.15 * ease(age / 0.12)
    font = F(ANTON, int(104 * s))
    space = d.textlength(" ", font=font)
    widths = [d.textlength(w.upper(), font=font) for w in words]
    total = sum(widths) + space * (len(words) - 1)
    lines = [[]]
    if total > W - 120:
        half = len(words) // 2 + (len(words) % 2)
        lines = [list(range(half)), list(range(half, len(words)))]
    else:
        lines = [list(range(len(words)))]
    y = 1500 - (len(lines) - 1) * 60
    for ln in lines:
        lw = sum(widths[i] for i in ln) + space * (len(ln) - 1)
        x = (W - lw) / 2
        for i in ln:
            w = words[i]
            hot = any(k in w.upper().strip(".,?'") for k in KEY) and (w.isupper() or any(ch.isdigit() for ch in w) or "$" in w)
            d.text((x, y), w.upper(), font=font, fill=GOLD if hot else WHITE, stroke_width=8, stroke_fill=(0, 0, 0), anchor="ls")
            x += widths[i] + space
        y += 120


def main():
    voice, starts = make_voice()
    n = len(voice)
    bed = music_and_sfx(n, starts)
    mix = voice + 0.55 * bed
    mix = mix / (np.abs(mix).max() + 1e-9) * 0.95
    sf.write("audio.wav", mix, SR)
    dur = n / SR
    print("duration", round(dur, 2))

    # caption timing: chunks spread over each line by character weight
    caps = []
    for (a, z), (_, cap) in zip(starts, LINES):
        ch = chunks(cap)
        weights = [sum(len(w) for w in c) + 2 for c in ch]
        tot = sum(weights)
        t = a
        for c, wgt in zip(ch, weights):
            L = (z - a) * wgt / tot
            caps.append((t, t + L, c))
            t += L

    bg = make_background()
    nframes = int(dur * FPS)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                           "-i", "-", "-i", "audio.wav", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", "short.mp4"], stdin=subprocess.PIPE)
    for f in range(nframes):
        t = f / FPS
        img = bg.copy()
        d = ImageDraw.Draw(img)
        # which line
        idx = 0
        for i, (a, z) in enumerate(starts):
            if t >= a - 0.08:
                idx = i
        a, z = starts[idx]
        nxt = starts[idx + 1][0] if idx + 1 < len(starts) else dur
        lt = max(0.0, t - a)
        p = clamp(lt / max(0.1, nxt - a))
        scene(idx, p, lt, d, img)
        # scene-in flash
        if 0 <= t - a < 0.12 and idx > 0:
            k = 1 - (t - a) / 0.12
            img = Image.blend(img, Image.new("RGB", (W, H), (255, 255, 255)), 0.18 * k)
        for (c0, c1, words) in caps:
            if c0 <= t < c1:
                draw_caption(img, words, t - c0)
                break
        # progress bar
        d = ImageDraw.Draw(img)
        d.rectangle([0, H - 14, int(W * t / dur), H], fill=RED)
        ff.stdin.write(img.tobytes())
        if f % 300 == 0:
            print("frame", f, "/", nframes, flush=True)
    ff.stdin.close()
    ff.wait()
    print("done")


if __name__ == "__main__":
    main()
