"""Paper Trail Short: the $340 million typo (Mizuho, Tokyo, 2005), animated with motion.py.

Facts: on 8 Dec 2005 a Mizuho Securities trader meant to sell 1 J-Com share at 610,000 yen and entered
610,000 shares at 1 yen - about 40 times the 14,500 shares J-Com had. The cancel order failed in the
Tokyo Stock Exchange's system. Mizuho lost about 40 billion yen (~$340 million then). One individual
trader reportedly made about 2 billion yen (~$17 million). In 2009 a court ordered the exchange to pay
Mizuho about 10.7 billion yen - roughly a quarter of the loss (upheld in 2015).
"""
import math
import random

import skia

from motion import (GOLD, GREEN, GREY, INK, RED, WHITE, clamp, coin, draw_on, in_out, lerp, money_str, out_back,
                    out_cubic, out_elastic, paint, person, pop, prog, rrect, text)

SLUG = "paper-trail-340-million-typo-short"
CHANNEL = "Paper Trail"
BRAND = "PAPER TRAIL"
ACCENT = GOLD
TITLE = "THE $340 MILLION TYPO"
W_ = 1080

LINES = [
    ("One typo cost this bank three hundred and forty million dollars.", "One TYPO cost this bank $340 MILLION."),
    ("Tokyo, two thousand five. A trader wanted to sell one share, for six hundred and ten thousand yen.",
     "Tokyo, 2005. A trader wanted to sell 1 SHARE for 610,000 YEN."),
    ("Instead, he typed: six hundred and ten thousand shares, for one yen each.",
     "Instead, he typed: 610,000 SHARES, for 1 YEN each."),
    ("That's forty times more shares than the company even had.", "That's 40X more shares than the company even HAD."),
    ("He tried to cancel. The system wouldn't let him.", "He tried to CANCEL. The system wouldn't let him."),
    ("Traders everywhere jumped in, and bought.", "Traders everywhere jumped in, and BOUGHT."),
    ("One young trader reportedly made seventeen million dollars, in minutes.",
     "One young trader reportedly made $17 MILLION, in minutes."),
    ("The bank lost three hundred and forty million.", "The bank lost $340 MILLION."),
    ("Years later, a court made the stock exchange pay back about a quarter.",
     "Years later, a court made the stock exchange pay back about a QUARTER."),
    ("All because of...", "All because of..."),
]

SFX = {
    0: [(0.3, "boom")],
    1: [(0.1, "pop"), (0.9, "pop")],
    2: [(0.1 + 0.09 * i, "tick") for i in range(14)] + [(1.7, "stamp")],
    3: [(0.2, "pop"), (0.9, "riser"), (1.0, "boom")],
    4: [(0.3, "tick"), (0.7, "tick"), (1.1, "tick"), (1.5, "stamp")],
    5: [(0.1, "whoosh"), (0.5, "pop"), (0.8, "pop"), (1.1, "pop")],
    6: [(0.2, "pop"), (0.9, "ching")],
    7: [(0.1, "boom")],
    8: [(0.2, "stamp"), (1.6, "pop")],
    9: [(0.1, "pop")],
}


# ---------------------------------------------------------------- props

def monitor(c, x, y, w, h, fn, glitch=0.0):
    c.save()
    c.translate(x + glitch * math.sin(glitch * 97), y)
    rrect(c, -w / 2 - 22, -h / 2 - 22, w + 44, h + 44, 26, paint((40, 44, 56)))
    rrect(c, -w / 2, -h / 2, w, h, 12, paint((10, 16, 24)))
    c.drawRect(skia.Rect.MakeXYWH(-40, h / 2 + 22, 80, 70), paint((40, 44, 56)))
    rrect(c, -150, h / 2 + 88, 300, 26, 10, paint((40, 44, 56)))
    fn()
    c.restore()


def ticket(c, line1, line2, colr, a=1.0, strike=0.0):
    text(c, "ORDER", -300, -130, 40, GREY, a=a, face="archivo", align="left", shadow=False)
    text(c, line1, 0, -30, 96, colr, a=a, shadow=False)
    text(c, line2, 0, 90, 84, colr, a=a, shadow=False)
    if strike > 0:
        p = skia.Path()
        p.moveTo(-330, 30)
        p.lineTo(330, 0)
        draw_on(c, p, strike, paint(RED, 1, stroke=14))


def key(c, x, y, label, pressed=0.0, colr=(52, 56, 70)):
    dy = 10 * pressed
    rrect(c, x - 62, y - 56 + 14, 124, 112, 18, paint((20, 22, 28)))
    rrect(c, x - 62, y - 56 + dy, 124, 112, 18, paint(colr))
    text(c, label, x, y + dy, 58, WHITE, shadow=False)


# ---------------------------------------------------------------- scenes

def s1(c, t, d, k):
    g = 14 * max(0.0, math.sin(t * 30)) * (1 - prog(t, 0.2, 0.6))
    monitor(c, 540, 760, 760, 420, lambda: ticket(c, "SELL 610,000", "FOR ¥1 EACH", RED), glitch=g)
    blink = 0.6 + 0.4 * abs(math.sin(t * 6))
    rrect(c, 540 - 330, 480, 660, 8, 4, paint(RED, blink))
    text(c, "-$340,000,000", 540, 1170, 120, RED, glow=0.7, scale=1 + 0.05 * math.sin(t * 5))


def s2(c, t, d, k):
    sun = out_cubic(prog(t, 0.0, 0.5))
    c.drawCircle(540, 640, 230 * sun, paint((220, 50, 56)))
    rng = random.Random(3)
    x = 0
    while x < W_:  # Tokyo skyline
        w, h = rng.randint(60, 140), rng.randint(140, 420)
        c.drawRect(skia.Rect.MakeXYWH(x, 900 - h, w, h + 40), paint((18, 20, 28)))
        x += w + 6
    c.drawRect(skia.Rect.MakeXYWH(0, 930, W_, 400), paint((12, 14, 20)))
    pop(c, 540, 400, prog(t, 0.0, 0.35), lambda: (rrect(c, 540 - 200, 362, 400, 80, 16, paint(INK, 0.9)),
                                                  text(c, "TOKYO · 2005", 540, 402, 52, WHITE, face="archivo")))
    def tk():
        rrect(c, 540 - 380, 980, 760, 300, 24, paint((236, 240, 236)))
        text(c, "WANTED:", 540, 1040, 40, (60, 120, 70), face="archivo", shadow=False)
        text(c, "SELL 1 SHARE", 540, 1120, 84, (30, 110, 60), shadow=False)
        text(c, "FOR ¥610,000", 540, 1220, 74, (30, 110, 60), shadow=False)
    pop(c, 540, 1130, prog(t, 0.9, 0.4), tk)


def s3(c, t, d, k):
    typed = int(clamp((t - 0.1) / 1.3) * 14)
    line1 = "SELL 610,000"[: min(12, typed)]
    line2 = "FOR ¥1 EACH"[: max(0, typed - 3)] if typed > 3 else ""
    cursor = "|" if int(t * 4) % 2 == 0 else " "
    monitor(c, 540, 560, 760, 420, lambda: ticket(c, line1 + (cursor if typed < 12 else ""), line2, RED))
    for i, lab in enumerate("610000"):
        x = 160 + i * 152
        pressed = max(0.0, 1 - abs(t - (0.15 + i * 0.2)) * 8)
        key(c, x, 1080, lab, pressed, colr=(160, 40, 44) if pressed > 0.3 else (52, 56, 70))
    st = prog(t, 1.7, 0.25)
    if st > 0:
        c.save()
        c.translate(540, 1270)
        c.rotate(-7)
        c.scale(lerp(2, 1, out_cubic(st)), lerp(2, 1, out_cubic(st)))
        rrect(c, -230, -70, 460, 140, 18, paint(RED, min(1, st * 2), stroke=12))
        text(c, "OOPS.", 0, 0, 110, RED, a=min(1, st * 2), shadow=False)
        c.restore()


def s4(c, t, d, k):
    base = 1180
    c.drawLine(120, base, 960, base, paint(GREY, 0.8, stroke=6))
    g1 = out_back(prog(t, 0.1, 0.4), 1.2)
    h1 = 26 * g1
    rrect(c, 200, base - h1, 240, max(1, h1), 6, paint(GREEN))
    text(c, "14,500", 320, base - h1 - 50, 64, GREEN, a=g1)
    text(c, "SHARES THAT EXISTED", 320, base + 50, 30, GREY, face="archivo")
    g2 = in_out(prog(t, 0.5, 0.6))
    h2 = 780 * g2
    rrect(c, 640, base - h2, 240, max(1, h2), 10, paint(RED))
    if g2 > 0:
        text(c, f"{int(610000 * g2):,}", 760, base - h2 - 50, 64, RED)
    text(c, "SHARES HE SOLD", 760, base + 50, 30, GREY, face="archivo")
    text(c, "40X", 330, 620, 230, GOLD, scale=out_elastic(prog(t, 1.0, 0.8)), glow=0.6)


def s5(c, t, d, k):
    hits = [0.3, 0.7, 1.1]
    pressed = max([max(0.0, 1 - abs(t - h) * 9) for h in hits] + [0])
    def btn():
        rrect(c, 540 - 280, 560 + 12 * pressed, 560, 200, 40, paint((150, 30, 34)))
        rrect(c, 540 - 280, 540 + 12 * pressed, 560, 200, 40, paint(RED))
        text(c, "CANCEL", 540, 640 + 12 * pressed, 110, WHITE, shadow=False)
    pop(c, 540, 640, prog(t, 0.0, 0.35), btn)
    for i, h in enumerate(hits):
        a = prog(t, h, 0.12) * (1 - prog(t, h + 0.25, 0.2))
        if a > 0:
            text(c, "ERROR", 300 + i * 240, 960 + (i % 2) * 90, 76, RED, a=a, glow=0.5, scale=1.1)
    st = prog(t, 1.5, 0.25)
    if st > 0:
        text(c, "DENIED", 540, 1180, 120, RED, a=min(1, st * 2), scale=lerp(2, 1, out_cubic(st)), glow=0.4)


def s6(c, t, d, k):
    chart = skia.Path()
    pts = [(120, 480), (240, 470), (330, 500), (420, 560), (480, 900), (560, 1000), (650, 960), (760, 980), (900, 1000)]
    chart.moveTo(*pts[0])
    for p in pts[1:]:
        chart.lineTo(*p)
    draw_on(c, chart, prog(t, 0.0, 0.8), paint(RED, 1, stroke=14))
    rng = random.Random(6)
    for i in range(12):
        at = 0.4 + i * 0.09
        a = prog(t, at, 0.15)
        if a > 0:
            x, y = rng.randint(120, 960), rng.randint(400, 1250)
            pop(c, x, y, a, lambda x=x, y=y: (rrect(c, x - 90, y - 40, 180, 80, 40, paint(GREEN)),
                                              text(c, "BUY", x, y, 50, INK, shadow=False)))


def s7(c, t, d, k):
    pop(c, 540, 1240, prog(t, 0.0, 0.4), lambda: person(c, 540, 1240, 1.15, rgb=(36, 42, 60), rim=GREEN, hair=(20, 20, 26)))
    rrect(c, 300, 1060, 480, 40, 10, paint((70, 76, 92)))   # desk
    v = in_out(prog(t, 0.3, 1.0))
    text(c, money_str(17_000_000 * v), 540, 420, 120, GREEN, glow=0.5 if v >= 1 else 0.2)
    text(c, "IN MINUTES", 540, 540, 52, WHITE, face="archivo", a=out_cubic(prog(t, 0.9, 0.3)))
    rng = random.Random(2)
    if t > 0.9:
        for i in range(16):
            x = rng.uniform(80, 1000)
            y = 620 + (t - 0.9) * rng.uniform(400, 900) - rng.uniform(0, 200)
            if y < 1000:
                coin(c, x, y, 28, spin=t * 7 + i)


def s8(c, t, d, k):
    shake = 10 * math.sin(t * 50) * (1 - prog(t, 0, 0.6))
    c.save()
    c.translate(shake, 0)
    f = (48, 54, 70)
    roof = skia.Path()
    roof.moveTo(240, 700)
    roof.lineTo(540, 520)
    roof.lineTo(840, 700)
    roof.close()
    c.drawPath(roof, paint(f))
    c.drawRect(skia.Rect.MakeXYWH(260, 700, 560, 40), paint(f))
    for i in range(5):
        c.drawRect(skia.Rect.MakeXYWH(300 + i * 110, 760, 50, 280), paint(f))
    c.drawRect(skia.Rect.MakeXYWH(240, 1040, 600, 50), paint(f))
    text(c, "BANK", 540, 650, 50, GREY, face="archivo", shadow=False)
    crack = skia.Path()
    crack.moveTo(540, 700)
    crack.lineTo(500, 820)
    crack.lineTo(580, 920)
    crack.lineTo(520, 1060)
    draw_on(c, crack, prog(t, 0.1, 0.5), paint(RED, 1, stroke=10))
    c.restore()
    text(c, "-$340,000,000", 540, 1220, 116, RED, scale=lerp(1.8, 1, out_cubic(prog(t, 0.1, 0.3))), glow=0.6)


def s9(c, t, d, k):
    cx, cy, r = 540, 830, 250
    c.drawCircle(cx, cy, r * out_cubic(prog(t, 0.0, 0.4)), paint((50, 58, 80)))
    q = out_cubic(prog(t, 0.6, 0.6))
    if q > 0:
        p = skia.Path()
        p.moveTo(cx, cy)
        p.arcTo(skia.Rect.MakeXYWH(cx - r, cy - r, 2 * r, 2 * r), -90, 94 * q, False)
        p.close()
        c.drawPath(p, paint(GREEN, 0.5, blur=20))
        c.drawPath(p, paint(GREEN))
    st = prog(t, 0.2, 0.25)
    if st > 0:
        c.save()
        c.translate(540, 430)
        c.rotate(-6)
        c.scale(lerp(2, 1, out_cubic(st)), lerp(2, 1, out_cubic(st)))
        rrect(c, -260, -70, 520, 140, 18, paint(GOLD, min(1, st * 2), stroke=12))
        text(c, "COURT RULING", 0, 0, 84, GOLD, a=min(1, st * 2), shadow=False)
        c.restore()
    text(c, "~25% PAID BACK", 540, 1190, 80, GREEN, a=out_cubic(prog(t, 1.4, 0.3)), face="archivo")


def s10(c, t, d, k):
    s1(c, t, d, k)


SCENES = [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10]

UPLOAD = {
    "title": "The $340 Million Typo ⌨️ #shorts",
    "description": ("In December 2005, a trader at Mizuho Securities meant to sell 1 share of J-Com for 610,000 yen - and typed "
                    "610,000 shares for 1 yen. That was about 40 times more shares than the company had. The cancel order failed, "
                    "traders bought everything, and Mizuho lost about $340 million. A court later ordered the Tokyo Stock "
                    "Exchange to pay back roughly a quarter.\n\n"
                    "Read more: https://en.wikipedia.org/wiki/Mizuho_Securities#J-Com_incident\n\n"
                    "#money #finance #stocks #typo #papertrail"),
    "tags": ["mizuho", "fat finger", "typo", "stock market", "trading mistake", "money", "finance", "japan", "paper trail"],
    "pinned": "What's the most expensive mistake YOU ever made? 😅👇",
}
