"""Paper Trail Short: why Costco's hot dog still costs $1.50 (animated with motion.py).

Built on what viral money Shorts do: the first frame IS the hook (picture + claim, no intro), a
"you think X - the truth is Y" twist, short lines, and a last frame that matches the first so it loops.
"""
import math
import random

import skia

from motion import (BLUE, GOLD, GREEN, GREY, INK, RED, WHITE, clamp, draw_on, in_out, lerp, out_back, out_cubic,
                    out_elastic, paint, person, pop, prog, rrect, text)

SLUG = "paper-trail-costco-hot-dog-short"
CHANNEL = "Paper Trail"
BRAND = "PAPER TRAIL"
ACCENT = GOLD
W_ = 1080

LINES = [
    ("This hot dog has cost a dollar fifty since nineteen eighty-five.", "This hot dog has cost $1.50 since 1985."),
    ("With inflation, it should cost over four dollars.", "With inflation, it should cost over $4."),
    ("So why hasn't Costco raised the price?", "So why hasn't COSTCO raised the price?"),
    ("When the boss wanted to raise it, the founder reportedly told him: if you raise the hot dog, I will kill you.",
     "When the boss wanted to raise it, the founder reportedly said: \"If you raise the HOT DOG, I will KILL you.\""),
    ("So Costco built its own hot dog factories.", "So Costco built its own hot dog FACTORIES."),
    ("It even switched from Pepsi to Coke, to keep the price.", "It even switched from PEPSI to COKE, to keep the price."),
    ("Because the hot dog isn't the product. You are.", "Because the hot dog isn't the product. YOU ARE."),
    ("About half of Costco's profit comes from membership fees.", "About HALF of Costco's profit comes from MEMBERSHIP FEES."),
    ("The cheap hot dog keeps you coming back, and paying every year.", "The cheap hot dog keeps you coming back, and PAYING every year."),
    ("And that's why, today, it still costs...", "And that's why, today, it still costs..."),
]

SFX = {
    0: [(0.6, "pop")],
    1: [(0.1, "pop")] + [(0.3 + 0.1 * i, "tick") for i in range(8)] + [(1.2, "stamp")],
    2: [(0.05, "boom")],
    3: [(0.1, "pop"), (0.35, "pop"), (2.6, "stamp"), (3.0, "boom")],
    4: [(0.1, "pop"), (0.6, "whoosh")],
    5: [(0.2, "whoosh"), (1.0, "whoosh"), (1.5, "pop")],
    6: [(0.4, "whoosh"), (1.4, "boom")],
    7: [(0.1, "pop"), (0.8, "stamp"), (1.6, "ching")],
    8: [(0.2, "whoosh"), (1.2, "pop"), (2.0, "ching")],
    9: [(0.1, "pop")],
}


# ---------------------------------------------------------------- props

def hot_dog(c, x, y, s, wiggle=0.0):
    c.save()
    c.translate(x, y)
    c.scale(s, s)
    c.rotate(wiggle)
    rrect(c, -300, -40, 600, 150, 75, paint((214, 160, 92)))               # bun bottom
    rrect(c, -330, -80, 660, 110, 55, paint((178, 64, 44)))                # sausage
    rrect(c, -330, -80, 660, 40, 20, paint((214, 96, 70), 0.6))            # shine
    rrect(c, -300, -150, 600, 120, 60, paint((232, 182, 110)))             # bun top
    rrect(c, -260, -146, 520, 30, 15, paint((246, 214, 160), 0.7))
    m = skia.Path()
    m.moveTo(-280, -30)
    for i in range(14):
        m.lineTo(-280 + (i + 1) * 40, -30 + (20 if i % 2 == 0 else -20))
    c.drawPath(m, paint((250, 206, 40), 1, stroke=16))                    # mustard
    c.restore()


def soda(c, x, y, s):
    c.save()
    c.translate(x, y)
    c.scale(s, s)
    cup = skia.Path()
    cup.moveTo(-90, -160)
    cup.lineTo(90, -160)
    cup.lineTo(70, 160)
    cup.lineTo(-70, 160)
    cup.close()
    c.drawPath(cup, paint((220, 50, 56)))
    rrect(c, -100, -190, 200, 36, 12, paint((240, 240, 240)))
    c.drawLine(20, -190, 60, -320, paint((240, 240, 240), 1, stroke=16))
    c.drawRect(skia.Rect.MakeXYWH(-80, -40, 160, 50), paint(WHITE, 0.9))
    c.restore()


def price_tag(c, x, y, s, label, rot=0.0, colr=GOLD, txt=INK):
    c.save()
    c.translate(x, y)
    c.rotate(rot)
    c.scale(s, s)
    c.drawLine(0, -170, 0, -95, paint(GREY, 1, stroke=5))
    tag = skia.Path()
    tag.moveTo(-150, -60)
    tag.lineTo(-60, -110)
    tag.lineTo(150, -110)
    tag.lineTo(150, 110)
    tag.lineTo(-60, 110)
    tag.lineTo(-150, 60)
    tag.close()
    c.save()
    c.rotate(90)
    c.drawPath(tag, paint(colr, 0.45, blur=22))
    c.drawPath(tag, paint(colr))
    c.restore()
    c.drawCircle(0, -78, 14, paint(INK))
    text(c, label, 0, 30, 104, txt, shadow=False)
    c.restore()


def opening(c, t):
    """Scene 1 and the last scene look the same, so the Short loops without a cut."""
    hot_dog(c, 470, 820, 1.0, wiggle=1.5 * math.sin(t * 2.4))
    soda(c, 860, 760, 0.95)
    price_tag(c, 760, 470, 1.25, "$1.50", rot=8 * math.sin(t * 2.8))


# ---------------------------------------------------------------- scenes

def s1(c, t, d, k):
    opening(c, t)
    pop(c, 470, 1080, prog(t, 0.6, 0.4), lambda: (rrect(c, 470 - 210, 1040, 420, 84, 18, paint(INK, 0.9)),
                                                  rrect(c, 470 - 210, 1040, 420, 84, 18, paint(GOLD, 1, stroke=4)),
                                                  text(c, "SINCE 1985", 470, 1082, 58, WHITE, face="archivo")))


def s2(c, t, d, k):
    base = 1150
    c.drawLine(140, base, 940, base, paint(GREY, 0.8, stroke=6))
    g1 = out_back(prog(t, 0.1, 0.4), 1.2)
    rrect(c, 230, base - 220 * g1, 220, 220 * g1, 14, paint(GOLD))
    text(c, "$1.50", 340, base - 220 * g1 - 60, 80, GOLD, a=g1)
    text(c, "1985", 340, base + 50, 44, GREY, face="archivo")
    g2 = in_out(prog(t, 0.3, 0.9))
    hgt = 220 + (540 - 220) * g2
    rrect(c, 630, base - hgt, 220, hgt, 14, paint(RED))
    val = 1.50 + (4.0 - 1.50) * g2
    lbl = "$4+" if g2 >= 1 else f"${val:.2f}"
    text(c, lbl, 740, base - hgt - 70, 110 if g2 >= 1 else 90, RED, glow=0.5 if g2 >= 1 else 0)
    text(c, "TODAY", 740, base + 50, 44, GREY, face="archivo")
    st = prog(t, 1.2, 0.25)
    if st > 0:
        c.save()
        c.translate(540, 330)
        c.rotate(-8)
        sc = lerp(2.0, 1.0, out_cubic(st))
        c.scale(sc, sc)
        rrect(c, -330, -70, 660, 140, 18, paint(GOLD, min(1, st * 2), stroke=12))
        text(c, "STILL $1.50", 0, 0, 104, GOLD, a=min(1, st * 2), shadow=False)
        c.restore()


def s3(c, t, d, k):
    shake = 10 * math.sin(t * 40) * (1 - prog(t, 0, 0.6))
    hot_dog(c, 540 + shake, 1050, 0.75)
    text(c, "?", 540, 560, 460, GOLD, scale=out_elastic(prog(t, 0.0, 0.8)), glow=0.6)
    text(c, "WHY?", 540, 1260, 70, WHITE, face="archivo", a=out_cubic(prog(t, 0.4, 0.3)))


def bubble(c, x, y, w, h, lines, a):
    if a <= 0:
        return
    p = paint(WHITE)
    rrect(c, x - w / 2, y - h / 2, w, h, 40, p)
    tail = skia.Path()
    tail.moveTo(x + w * 0.18, y + h / 2 - 4)
    tail.lineTo(x + w * 0.32, y + h / 2 + 70)
    tail.lineTo(x + w * 0.02, y + h / 2 - 4)
    tail.close()
    c.drawPath(tail, p)
    for i, (ln, colr) in enumerate(lines):
        text(c, ln, x, y - (len(lines) - 1) * 46 + i * 92, 78, colr, shadow=False)


def s4(c, t, d, k):
    pop(c, 250, 1250, prog(t, 0.0, 0.4), lambda: person(c, 250, 1250, 0.95, rgb=(40, 50, 74)))
    pop(c, 830, 1250, prog(t, 0.3, 0.4), lambda: person(c, 830, 1250, 1.05, rgb=(30, 36, 52), rim=GOLD, hair=(210, 210, 215)))
    pop(c, 250, 1300, prog(t, 0.2, 0.3), lambda: text(c, "THE BOSS", 250, 1300, 40, GREY, face="archivo"))
    pop(c, 830, 1300, prog(t, 0.5, 0.3), lambda: text(c, "THE FOUNDER", 830, 1300, 40, GOLD, face="archivo"))
    b = prog(t, 2.0, 0.35)
    pop(c, 560, 560, b, lambda: bubble(c, 560, 560, 860, 330, [("IF YOU RAISE THE", INK), ("HOT DOG,", RED),
                                                                ("I WILL KILL YOU.", INK)], 1))
    text(c, "- reportedly said by co-founder Jim Sinegal", 400, 790, 30, GREY, face="archivo",
         a=out_cubic(prog(t, 2.6, 0.4)))


def s5(c, t, d, k):
    def factory():
        f = (60, 66, 84)
        c.drawRect(skia.Rect.MakeXYWH(140, 520, 800, 380), paint(f))
        saw = skia.Path()
        saw.moveTo(140, 520)
        for i in range(4):
            saw.lineTo(140 + i * 200 + 200, 400)
            saw.lineTo(140 + i * 200 + 200, 520)
        saw.close()
        c.drawPath(saw, paint(f))
        c.drawRect(skia.Rect.MakeXYWH(760, 260, 80, 160), paint(f))
        for i in range(5):
            rrect(c, 190 + i * 150, 600, 90, 90, 10, paint(GOLD, 0.9))
        text(c, "HOT DOG FACTORY", 540, 820, 60, WHITE, face="archivo")
    pop(c, 540, 700, prog(t, 0.0, 0.45), factory)
    rng = random.Random(4)
    for i in range(6):  # smoke
        sy = 240 - ((t * 60 + i * 50) % 260)
        c.drawCircle(800 + 30 * math.sin(t + i), sy, 36 + i * 4, paint((150, 150, 160), 0.25, blur=12))
    c.drawRect(skia.Rect.MakeXYWH(0, 1110, W_, 40), paint((40, 44, 56)))  # conveyor
    for i in range(10):
        c.drawCircle((i * 120 + t * 160) % (W_ + 120) - 60, 1150, 18, paint((70, 76, 92)))
    for i in range(5):
        x = (i * 260 + t * 160) % (W_ + 300) - 150
        hot_dog(c, x, 1060, 0.28)


def can(c, x, y, s, colr, label):
    c.save()
    c.translate(x, y)
    c.scale(s, s)
    rrect(c, -110, -200, 220, 400, 40, paint(colr))
    rrect(c, -110, -200, 220, 40, 20, paint((200, 200, 205)))
    rrect(c, -110, 160, 220, 40, 20, paint((200, 200, 205)))
    rrect(c, -92, -150, 30, 300, 15, paint(WHITE, 0.25))
    c.save()
    c.rotate(-90)
    text(c, label, 0, 10, 92, WHITE, shadow=False)
    c.restore()
    c.restore()


def s6(c, t, d, k):
    out_x = lerp(540, -300, in_out(prog(t, 0.3, 0.6)))
    can(c, out_x, 760, 1.25, (30, 80, 190), "PEPSI")
    in_x = lerp(W_ + 300, 540, out_back(prog(t, 0.55, 0.6), 1.2))
    can(c, in_x, 760, 1.25, (210, 30, 40), "COKE")
    text(c, "CHEAPER DEAL", 540, 1110, 70, GREEN, a=out_cubic(prog(t, 1.5, 0.3)), face="archivo")


def s7(c, t, d, k):
    shrink = 1 - out_cubic(prog(t, 0.2, 0.5))
    if shrink > 0.01:
        hot_dog(c, 540, 820, shrink)
    sp = out_cubic(prog(t, 0.9, 0.5))
    if sp > 0:
        cone = skia.Path()
        cone.moveTo(440, 200)
        cone.lineTo(640, 200)
        cone.lineTo(880, 1260)
        cone.lineTo(200, 1260)
        cone.close()
        c.drawPath(cone, paint((255, 240, 190), 0.18 * sp, blur=30))
        person(c, 540, 1260, 1.25 * (0.6 + 0.4 * out_back(prog(t, 0.9, 0.5))), rgb=(36, 42, 60), rim=GOLD)
    st = prog(t, 1.4, 0.25)
    if st > 0:
        text(c, "YOU ARE", 540, 330, 150, GOLD, scale=lerp(2, 1, out_cubic(st)), a=min(1, st * 2), glow=0.5)
        text(c, "THE PRODUCT", 540, 470, 110, WHITE, scale=lerp(2, 1, out_cubic(prog(t, 1.5, 0.25))), a=min(1, st * 2))


def card(c, x, y, s, rot):
    c.save()
    c.translate(x, y)
    c.rotate(rot)
    c.scale(s, s)
    rrect(c, -300, -190, 600, 380, 34, paint(GOLD, 0.35, blur=30))
    rrect(c, -300, -190, 600, 380, 34, paint((30, 36, 52)))
    rrect(c, -300, -190, 600, 90, 34, paint(GOLD))
    c.drawRect(skia.Rect.MakeXYWH(-300, -130, 600, 30), paint(GOLD))
    text(c, "MEMBER", 0, -142, 54, INK, face="archivo", shadow=False)
    rrect(c, -240, -40, 90, 70, 12, paint((220, 190, 100)))
    text(c, "1234  5678  9012", 30, 100, 44, WHITE, face="archivo", shadow=False)
    c.restore()


def s8(c, t, d, k):
    flip = out_back(prog(t, 0.0, 0.5))
    c.save()
    c.translate(540, 520)
    c.scale(max(0.02, abs(math.cos((1 - flip) * math.pi / 2))), 1)
    c.translate(-540, -520)
    card(c, 540, 520, 1.0, -4)
    c.restore()
    cx, cy, r = 540, 1010, 190
    c.drawCircle(cx, cy, r * out_cubic(prog(t, 0.6, 0.4)), paint((50, 58, 80)))
    sl = out_cubic(prog(t, 0.8, 0.6))
    if sl > 0:
        p = skia.Path()
        p.moveTo(cx, cy)
        p.arcTo(skia.Rect.MakeXYWH(cx - r, cy - r, 2 * r, 2 * r), -90, 180 * sl, False)
        p.close()
        c.drawPath(p, paint(GOLD, 0.5, blur=20))
        c.drawPath(p, paint(GOLD))
    text(c, "~50%", cx + 300, cy - 40, 100, GOLD, scale=out_back(prog(t, 1.5, 0.4)), glow=0.4)
    text(c, "of profit", cx + 300, cy + 40, 40, WHITE, face="archivo", a=out_cubic(prog(t, 1.6, 0.3)))


def s9(c, t, d, k):
    card(c, 540, 760, 0.8, 0)
    r = 400
    ang = t * 160
    ring = skia.Path()
    ring.addArc(skia.Rect.MakeXYWH(540 - r, 760 - r, 2 * r, 2 * r), ang, 300)
    c.drawPath(ring, paint(GREEN, 0.9, stroke=18))
    hx = 540 + r * math.cos(math.radians(ang + 300))
    hy = 760 + r * math.sin(math.radians(ang + 300))
    c.drawCircle(hx, hy, 26, paint(GREEN))
    text(c, "RENEW", 540, 300, 96, GREEN, a=out_cubic(prog(t, 0.6, 0.3)), glow=0.4)
    pop(c, 540, 1240, prog(t, 1.2, 0.35), lambda: (rrect(c, 540 - 280, 1200, 560, 84, 18, paint(INK, 0.9)),
                                                   rrect(c, 540 - 280, 1200, 560, 84, 18, paint(GREEN, 1, stroke=4)),
                                                   text(c, "~90% RENEW", 540, 1242, 58, WHITE, face="archivo")))


def s10(c, t, d, k):
    opening(c, t)


SCENES = [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10]

UPLOAD = {
    "title": "Why This Hot Dog Still Costs $1.50 🌭 #shorts",
    "description": ("Costco's hot dog and soda combo has cost $1.50 since 1985. When a CEO suggested raising it, co-founder "
                    "Jim Sinegal reportedly said: \"If you raise the hot dog, I will kill you.\" Costco built its own hot dog "
                    "plants and switched soda suppliers to keep the price - because the hot dog isn't the product. "
                    "Membership fees are a huge part of Costco's profit, and around 90% of members renew.\n\n"
                    "#costco #business #money #finance #papertrail"),
    "tags": ["costco", "costco hot dog", "1.50 hot dog", "business", "money", "finance", "loss leader", "membership",
             "paper trail"],
    "pinned": "Would you pay $4 for it? Or is $1.50 the reason you go? 👇",
}
