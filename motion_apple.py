"""Paper Trail Short: the man who sold 10% of Apple for $800 (animated with motion.py)."""
import math
import random

import skia

from motion import (BLUE, GOLD, GREEN, GREY, INK, RED, WHITE, clamp, coin, draw_on, fade, in_out, lerp, money_str, out_back,
                    out_cubic, out_elastic, paint, person, pop, prog, rrect, text)

SLUG = "paper-trail-apple-800-short"
CHANNEL = "Paper Trail"
BRAND = "PAPER TRAIL"
ACCENT = GOLD

TITLE = "THE WORST $800 DEAL IN HISTORY"

LINES = [
    ("In nineteen seventy-six, this man owned ten percent of Apple.", "In 1976, this man owned 10% of APPLE."),
    ("Twelve days later, he sold it. For eight hundred dollars.", "12 DAYS later, he SOLD it. For $800."),
    ("His name is Ronald Wayne. He started Apple, with Steve Jobs and Steve Wozniak.",
     "His name is RONALD WAYNE. He started Apple with Steve Jobs and Steve Wozniak."),
    ("He even drew the company's first logo, and wrote the contract.", "He even drew the first LOGO, and wrote the CONTRACT."),
    ("But he was scared. If Apple went into debt, he could lose his house.",
     "But he was SCARED. If Apple went into DEBT, he could lose his HOUSE."),
    ("So he walked away.", "So he WALKED AWAY."),
    ("Then Apple became the first American company worth one trillion dollars.",
     "Then Apple became the first American company worth $1 TRILLION."),
    ("His ten percent? Worth hundreds of billions today.", "His 10%? Worth HUNDREDS OF BILLIONS today."),
    ("And he says, he doesn't regret it.", "And he says he doesn't REGRET it."),
    ("Would you have sold?", "Would YOU have SOLD?"),
]

SFX = {
    0: [(0.2, "pop")],
    1: [(0.05, "pop")] + [(0.08 * i + 0.1, "tick") for i in range(11)] + [(1.55, "ching"), (1.9, "stamp")],
    2: [(0.05, "pop"), (0.35, "pop"), (1.9, "whoosh"), (2.25, "pop"), (2.6, "pop")],
    3: [(0.05, "whoosh"), (1.2, "whoosh"), (2.4, "pop")],
    4: [(0.1, "pop"), (2.0, "boom"), (2.4, "stamp")],
    5: [(0.2, "whoosh")],
    6: [(0.2, "pop"), (0.6, "pop"), (1.0, "pop"), (1.4, "pop"), (1.8, "pop"), (2.4, "riser"), (3.3, "ching")],
    7: [(0.1, "pop"), (0.7, "stamp"), (1.3, "boom")],
    8: [(0.05, "pop"), (0.7, "whoosh")],
    9: [(0.05, "boom"), (0.35, "pop"), (0.55, "pop")],
}


def pie(c, cx, cy, r, t, slice_t, k):
    """A pie chart that draws itself; the 10% slice pops out."""
    ring = skia.Path()
    ring.addCircle(cx, cy, r)
    a = out_cubic(prog(t, 0.0, 0.45))
    c.drawCircle(cx, cy, r * a, paint((34, 40, 58)))
    draw_on(c, ring, prog(t, 0.0, 0.5), paint(GREY, 0.7, stroke=8))
    s = out_back(prog(t, slice_t, 0.45))
    if s > 0:
        mid = math.radians(-90 + 18)
        ox, oy = math.cos(mid) * 46 * s, math.sin(mid) * 46 * s
        sl = skia.Path()
        sl.moveTo(cx + ox, cy + oy)
        sl.arcTo(skia.Rect.MakeXYWH(cx - r + ox, cy - r + oy, 2 * r, 2 * r), -90, 36 * min(1, s), False)
        sl.close()
        c.drawPath(sl, paint(GOLD, 0.55, blur=26))
        c.drawPath(sl, paint(GOLD))
        lx, ly = cx + math.cos(mid) * (r + 120), cy + math.sin(mid) * (r + 120)
        text(c, "10%", lx, ly, 120, GOLD, scale=out_back(prog(t, slice_t + 0.25, 0.4)), glow=0.6)


def s1(c, t, d, k):
    t = t + 0.75  # the hook frame must already show the picture: start this scene mid-animation
    pie(c, 690, 700, 250, t, 0.55, k)
    pop(c, 300, 1270, prog(t, 0.0, 0.45), lambda: person(c, 300, 1270, 1.15, rim=GOLD))
    tag = prog(t, 0.95, 0.35)
    pop(c, 690, 1032, tag, lambda: (rrect(c, 690 - 250, 990, 500, 84, 18, paint(INK, 0.9)),
                                     rrect(c, 690 - 250, 990, 500, 84, 18, paint(GOLD, 1, stroke=4)),
                                     text(c, "APPLE · 1976", 690, 1032, 58, WHITE, face="archivo")))


def s2(c, t, d, k):
    def calendar():
        rrect(c, 330, 330, 420, 440, 30, paint((236, 232, 222)))
        rrect(c, 330, 330, 420, 110, 30, paint(RED))
        c.drawRect(skia.Rect.MakeXYWH(330, 400, 420, 40), paint(RED))
        text(c, "APRIL 1976", 540, 386, 50, WHITE, face="archivo", shadow=False)
        n = 1 + int(11 * out_cubic(prog(t, 0.1, 0.9)))
        flip = 1 - 0.25 * abs(math.sin(prog(t, 0.1, 0.9) * math.pi * 11))
        c.save()
        c.translate(540, 610)
        c.scale(1, flip if t < 1.05 else 1)
        text(c, str(n), 0, 0, 230, INK, shadow=False)
        c.restore()
        text(c, "DAYS", 540, 735, 34, (90, 90, 96), face="archivo", shadow=False)
    pop(c, 540, 550, prog(t, 0.0, 0.4), calendar)
    m = prog(t, 1.5, 0.35)
    if m > 0:
        s = lerp(2.6, 1.0, out_cubic(m))
        text(c, "$800", 540, 1010, 230, GREEN, scale=s, a=min(1, m * 3), glow=0.7)
        rng = random.Random(3)
        for i in range(14):  # coins burst out
            ang, sp = rng.uniform(-math.pi, 0), rng.uniform(500, 1100)
            tt = max(0.0, t - 1.5)
            x = 540 + math.cos(ang) * sp * tt
            y = 1000 + math.sin(ang) * sp * tt + 1400 * tt * tt
            if tt > 0 and y < 1400:
                coin(c, x, y, 34, a=clamp(1.6 - tt), spin=tt * 9 + i)
    st = prog(t, 1.9, 0.25)
    if st > 0:
        c.save()
        c.translate(560, 560)
        c.rotate(-14)
        sc = lerp(2.2, 1.0, out_cubic(st))
        c.scale(sc, sc)
        rrect(c, -230, -80, 460, 160, 20, paint(RED, min(1, st * 2), stroke=14))
        text(c, "SOLD", 0, 0, 130, RED, a=min(1, st * 2), shadow=False)
        c.restore()


def s3(c, t, d, k):
    side = prog(t, 1.85, 0.5)
    if side > 0:
        x1 = lerp(-200, 230, out_cubic(side))
        x2 = lerp(W_ + 200, 850, out_cubic(side))
        person(c, x1, 1220, 0.88, rgb=(40, 50, 74), hair=(20, 22, 30))
        person(c, x2, 1220, 0.88, rgb=(40, 50, 74), hair=(60, 40, 30))
        for x, name, at in ((230, "STEVE JOBS", 2.2), (850, "STEVE WOZNIAK", 2.55)):
            pop(c, x, 1268, prog(t, at, 0.35), lambda x=x, name=name: (rrect(c, x - 165, 1240, 330, 58, 14, paint(INK, 0.9)),
                                                                      text(c, name, x, 1269, 34, GREY, face="archivo")))
    pop(c, 540, 1180, prog(t, 0.0, 0.45), lambda: person(c, 540, 1180, 1.1, rgb=(30, 36, 52), rim=GOLD))
    pop(c, 540, 1225, prog(t, 0.35, 0.4), lambda: (rrect(c, 540 - 210, 1190, 420, 74, 16, paint(GOLD)),
                                                   text(c, "RONALD WAYNE", 540, 1227, 46, INK, face="archivo", shadow=False)))
    pop(c, 540, 330, prog(t, 1.6, 0.4), lambda: text(c, "APPLE'S 3 FOUNDERS", 540, 330, 80, WHITE))


W_ = 1080


def s4(c, t, d, k):
    def sheet(x, y, w, h, rot):
        c.save()
        c.translate(x, y)
        c.rotate(rot)
        rrect(c, -w / 2, -h / 2, w, h, 10, paint((238, 230, 210)))
        c.restore()
    a = out_cubic(prog(t, 0.0, 0.5))
    lx = lerp(-400, 360, a)
    sheet(lx, 700, 520, 660, -4)
    ink = paint((60, 44, 30), 1, stroke=7)
    c.save()
    c.translate(lx, 700)
    c.rotate(-4)
    tree = skia.Path()
    tree.moveTo(-40, 230)
    tree.lineTo(-30, 20)          # trunk
    tree.moveTo(30, 230)
    tree.lineTo(20, 20)
    for i in range(9):            # leafy canopy loops
        ang = i / 9 * 2 * math.pi
        tree.addCircle(math.cos(ang) * 120, -90 + math.sin(ang) * 80, 70)
    man = skia.Path()
    man.addCircle(130, 150, 26)   # Newton under the tree, reading
    man.moveTo(130, 176)
    man.lineTo(110, 240)
    man.moveTo(110, 240)
    man.lineTo(170, 240)
    man.moveTo(118, 200)
    man.lineTo(80, 215)
    draw_on(c, tree, prog(t, 0.3, 1.2), ink)
    draw_on(c, man, prog(t, 1.3, 0.5), ink)
    ap = prog(t, 1.6, 0.6)
    if ap > 0:
        c.drawCircle(60, lerp(-60, 120, out_cubic(ap)), 18, paint(RED))
    c.restore()
    b = out_cubic(prog(t, 1.2, 0.5))
    text(c, "THE FIRST LOGO", lx, 1080, 52, GOLD, a=a * (1 - b), face="archivo")
    if b > 0:
        rx = lerp(W_ + 400, 790, b)
        sheet(rx, 720, 400, 540, 5)
        c.save()
        c.translate(rx, 720)
        c.rotate(5)
        text(c, "AGREEMENT", 0, -200, 44, INK, face="archivo", shadow=False)
        lines = skia.Path()
        for i in range(8):
            y = -130 + i * 34
            lines.moveTo(-150, y)
            lines.lineTo(150 - (i % 3) * 40, y)
        draw_on(c, lines, prog(t, 1.4, 0.9), paint((110, 100, 90), 1, stroke=6))
        sig = skia.Path()
        sig.moveTo(-120, 200)
        sig.cubicTo(-80, 130, -40, 260, 0, 190)
        sig.cubicTo(40, 130, 60, 250, 130, 180)
        draw_on(c, sig, prog(t, 2.35, 0.45), paint((30, 60, 160), 1, stroke=7))
        c.restore()
        text(c, "THE CONTRACT", rx, 1080, 52, GOLD, a=b, face="archivo")


def house(c, x, y, s, tint=0.0, shake=0.0):
    c.save()
    c.translate(x + shake * math.sin(shake * 90), y)
    c.scale(s, s)
    wall = (lerp(220, 200, tint), lerp(206, 70, tint), lerp(180, 70, tint))
    rrect(c, -220, -200, 440, 300, 10, paint(wall))
    roof = skia.Path()
    roof.moveTo(-270, -190)
    roof.lineTo(0, -400)
    roof.lineTo(270, -190)
    roof.close()
    c.drawPath(roof, paint((150, 60, 50)))
    rrect(c, -50, -40, 100, 140, 8, paint((80, 50, 34)))
    for wx in (-150, 90):
        rrect(c, wx, -140, 60, 60, 6, paint(GOLD))
    c.restore()


def s5(c, t, d, k):
    hit = prog(t, 2.0, 0.6)
    shake = 12 * (1 - hit) if 0 < hit < 1 else 0
    pop(c, 540, 1000, prog(t, 0.0, 0.45), lambda: house(c, 540, 1000, 1.1, tint=out_cubic(hit), shake=shake))
    chart = skia.Path()
    chart.moveTo(120, 330)
    pts = [(220, 300), (300, 420), (390, 380), (470, 520), (560, 470), (640, 640), (700, 700)]
    for p in pts:
        chart.lineTo(*p)
    draw_on(c, chart, prog(t, 0.9, 1.1), paint(RED, 1, stroke=16))
    if prog(t, 0.9, 1.1) >= 1:
        head = skia.Path()
        head.moveTo(700, 700)
        head.lineTo(640, 690)
        head.lineTo(690, 640)
        head.close()
        c.drawPath(head, paint(RED))
    text(c, "DEBT", 300, 260, 90, RED, scale=out_back(prog(t, 0.9, 0.4)), glow=0.4)
    if hit > 0:
        crack = skia.Path()
        crack.moveTo(540, 800)
        crack.lineTo(510, 880)
        crack.lineTo(560, 940)
        crack.lineTo(520, 1030)
        draw_on(c, crack, hit, paint(INK, 1, stroke=8))
    pop(c, 540, 1240, prog(t, 2.4, 0.35), lambda: (rrect(c, 540 - 300, 1200, 600, 80, 16, paint(RED)),
                                                   text(c, "PERSONALLY LIABLE", 540, 1240, 50, WHITE, face="archivo", shadow=False)))


def s6(c, t, d, k):
    x = lerp(540, 1400, in_out(prog(t, 0.15, max(1.0, d - 0.1))))
    bob = abs(math.sin(t * 9)) * 18
    for i in range(int(prog(t, 0.15, d) * 8)):  # footprints
        fx = 540 + i * 110
        c.drawRoundRect(skia.Rect.MakeXYWH(fx - 22, 1250 + (i % 2) * 34, 44, 22), 11, 11, paint(GREY, 0.5))
    person(c, x, 1220 - bob, 1.05, rgb=(30, 36, 52), rim=GREY, rim_a=0.7)
    text(c, "GOODBYE, APPLE", 540, 420, 90, WHITE, a=out_cubic(prog(t, 0.1, 0.4)))


def s7(c, t, d, k):
    base_y, x0 = 1180, 150
    axis = skia.Path()
    axis.moveTo(x0, 360)
    axis.lineTo(x0, base_y)
    axis.lineTo(950, base_y)
    draw_on(c, axis, prog(t, 0.0, 0.4), paint(GREY, 0.8, stroke=6))
    heights = [16, 30, 70, 210, 640]
    for i, hgt in enumerate(heights):
        g = out_back(prog(t, 0.2 + i * 0.4, 0.5), 1.2)
        if g <= 0:
            continue
        x = 220 + i * 150
        hh = hgt * g
        last = i == len(heights) - 1
        if last:
            c.drawRect(skia.Rect.MakeXYWH(x - 8, base_y - hh - 8, 136, hh + 8), paint(GOLD, 0.5, blur=30))
        rrect(c, x, base_y - hh, 120, hh, 10, paint(GOLD if last else BLUE))
    text(c, "1976", 280, base_y + 50, 40, GREY, face="archivo", a=out_cubic(prog(t, 0.2, 0.3)))
    text(c, "2018", 880, base_y + 50, 40, GOLD, face="archivo", a=out_cubic(prog(t, 1.8, 0.3)))
    v = prog(t, 2.2, 1.1)
    if v > 0:
        val = 1e12 * in_out(v)
        text(c, money_str(val), 540, 300, 96, GOLD, glow=0.5 if v >= 1 else 0.2, scale=1.0 + 0.08 * out_elastic(prog(t, 3.3, 0.6)) - 0.08 * (t >= 3.3))
    rng = random.Random(9)
    if t > 3.3:
        for i in range(24):  # money rain
            x = rng.uniform(80, 1000)
            y = -60 + (t - 3.3) * rng.uniform(600, 1100) - rng.uniform(0, 300)
            coin(c, x, y, 26, spin=t * 6 + i)


def s8(c, t, d, k):
    pie(c, 540, 700, 230, t + 2, 0.0, k)
    s = prog(t, 0.6, 0.3)
    if s > 0:
        text(c, "$800", 540, 1040, 120, GREY, a=min(1, s * 2))
        line = skia.Path()
        line.moveTo(400, 1060)
        line.lineTo(680, 1010)
        draw_on(c, line, prog(t, 0.75, 0.25), paint(RED, 1, stroke=14))
    b = prog(t, 1.25, 0.3)
    if b > 0:
        c.drawRect(skia.Rect.MakeXYWH(0, 1120, W_, 220), paint(INK, 0.75 * b))
        text(c, "HUNDREDS OF", 540, 1180, 92, GREEN, scale=lerp(1.8, 1, out_cubic(b)), a=min(1, b * 2), glow=0.6)
        text(c, "BILLIONS", 540, 1285, 120, GREEN, scale=lerp(1.8, 1, out_cubic(prog(t, 1.4, 0.3))), a=min(1, b * 2), glow=0.7)


def s9(c, t, d, k):
    pop(c, 540, 1200, prog(t, 0.0, 0.45), lambda: person(c, 540, 1200, 1.15, rgb=(44, 50, 66), rim=WHITE, rim_a=0.5,
                                                          hair=(220, 220, 225)))
    reveal = in_out(prog(t, 0.5, 0.9))
    if reveal > 0:
        c.save()
        c.clipRect(skia.Rect.MakeXYWH(0, 250, W_ * reveal, 260))
        text(c, "NO REGRETS", 540, 380, 140, GOLD, glow=0.5)
        c.restore()
    tick = skia.Path()
    tick.moveTo(730, 760)
    tick.lineTo(810, 840)
    tick.lineTo(960, 640)
    draw_on(c, tick, prog(t, 1.2, 0.5), paint(GREEN, 1, stroke=26))


def s10(c, t, d, k):
    q = out_elastic(prog(t, 0.0, 0.9))
    text(c, "?", 540, 560, 420, GOLD, scale=q, glow=0.6)
    pulse = 1 + 0.04 * math.sin(t * 8)
    for x, label, colr, at in ((290, "SELL: $800", RED, 0.3), (790, "KEEP 10%", GREEN, 0.5)):
        def btn(x=x, label=label, colr=colr):
            rrect(c, x - 220, 920, 440, 150, 75, paint(colr, 0.35, blur=22))
            rrect(c, x - 220, 920, 440, 150, 75, paint(colr))
            text(c, label, x, 995, 62, WHITE, shadow=False)
        c.save()
        c.translate(x, 995)
        c.scale(pulse, pulse)
        c.translate(-x, -995)
        pop(c, x, 995, prog(t, at, 0.4), btn)
        c.restore()


SCENES = [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10]

UPLOAD = {
    "title": "He Sold 10% of Apple for $800 🍎 #shorts",
    "description": ("In 1976, Ronald Wayne co-founded Apple with Steve Jobs and Steve Wozniak and owned 10% of the company. "
                    "He drew the first logo and wrote the partnership agreement - then, 12 days later, sold his share for $800 "
                    "because he feared being personally liable for the company's debts. He has said he doesn't regret it.\n\n"
                    "Read more: https://en.wikipedia.org/wiki/Ronald_Wayne\n\n#apple #money #business #history #papertrail"),
    "tags": ["ronald wayne", "apple", "steve jobs", "steve wozniak", "money", "business history", "worst decision", "finance",
             "paper trail"],
    "pinned": "Be honest: SELL for $800 or KEEP the 10%? 👇",
}
