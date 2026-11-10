"""Paper Trail Short: the retired couple who beat the lottery - legally (animated with motion.py).

Facts: Jerry and Marge Selbee ran a convenience store in Evart, Michigan. Around 2003 Jerry noticed that in
Michigan's Winfall game, when the jackpot passed its cap and nobody won, the money "rolled down" to the smaller
prizes, so in those draws a ticket was worth more than it cost. They bought large numbers of tickets in roll-down
weeks (later in Massachusetts' Cash WinFall too). Over about nine years they won roughly $26 million in prizes,
around $8 million profit before taxes. It was legal; the games were later ended.
"""
import math
import random

import skia

from motion import (BLUE, GOLD, GREEN, GREY, INK, RED, WHITE, clamp, coin, draw_on, in_out, lerp, money_str, out_back,
                    out_cubic, out_elastic, paint, person, pop, prog, rrect, text)

SLUG = "paper-trail-lottery-couple-short"
CHANNEL = "Paper Trail"
BRAND = "PAPER TRAIL"
ACCENT = GOLD
TITLE = "THE COUPLE WHO BEAT THE LOTTERY"
W_ = 1080

LINES = [
    ("This retired couple won twenty-six million dollars from the lottery. Legally.",
     "This retired couple won $26 MILLION from the lottery. LEGALLY."),
    ("Jerry Selbee ran a little store in a small town in Michigan.", "JERRY SELBEE ran a little store in a small town in Michigan."),
    ("One day, he read the rules of a game called Winfall.", "One day, he read the RULES of a game called WINFALL."),
    ("When the jackpot got too big and nobody won, the money rolled down to the smaller prizes.",
     "When the jackpot got too big and nobody won, the money ROLLED DOWN to the smaller prizes."),
    ("In those weeks, a two dollar ticket was worth more than two dollars.", "In those weeks, a $2 ticket was worth MORE than $2."),
    ("So he tested it. And he won.", "So he TESTED it. And he WON."),
    ("Then he and his wife Marge bought tickets by the thousands.", "Then he and his wife MARGE bought tickets by the THOUSANDS."),
    ("Over nine years: about twenty-six million in prizes. Around eight million in profit.",
     "Over 9 years: about $26 MILLION in prizes. Around $8 MILLION profit."),
    ("No cheating. Just math.", "No cheating. Just MATH."),
    ("And that's how this retired couple...", "And that's how this retired couple..."),
]

SFX = {
    0: [(0.4, "ching")],
    1: [(0.1, "pop"), (0.6, "pop")],
    2: [(0.1, "pop"), (0.9, "pop")],
    3: [(0.2, "whoosh")] + [(0.9 + 0.12 * i, "tick") for i in range(6)],
    4: [(0.3, "pop"), (1.2, "stamp")],
    5: [(0.2, "tick"), (0.5, "tick"), (0.9, "ching")],
    6: [(0.1 + 0.08 * i, "pop") for i in range(10)],
    7: [(0.1, "riser"), (0.3, "pop"), (1.8, "ching")],
    8: [(0.2, "stamp")],
    9: [(0.4, "ching")],
}


def ticket(c, x, y, s, rot=0.0, a=1.0, label="WINFALL"):
    c.save()
    c.translate(x, y)
    c.rotate(rot)
    c.scale(s, s)
    rrect(c, -150, -80, 300, 160, 14, paint((246, 240, 220), a))
    rrect(c, -150, -80, 300, 46, 14, paint(RED, a))
    c.drawRect(skia.Rect.MakeXYWH(-150, -50, 300, 16), paint(RED, a))
    text(c, label, 0, -57, 30, WHITE, a=a, face="archivo", shadow=False)
    for i, n in enumerate((7, 14, 22, 31, 38, 45)):
        cx = -110 + i * 44
        c.drawCircle(cx, 20, 18, paint(GOLD, a))
        text(c, str(n), cx, 20, 20, INK, a=a, face="archivo", shadow=False)
    c.restore()


def couple(c, x, y, s, rim=GOLD):
    person(c, x - 140 * s, y, 0.9 * s, rgb=(40, 46, 64), rim=rim, hair=(220, 220, 225))
    person(c, x + 140 * s, y, 0.85 * s, rgb=(48, 40, 58), rim=rim, hair=(230, 230, 235))


def s1(c, t, d, k):
    couple(c, 540, 1290, 1.0)
    text(c, "$26,000,000", 540, 470, 130, GREEN, glow=0.6, scale=1 + 0.03 * math.sin(t * 4))
    c.save()
    c.translate(540, 640)
    c.rotate(-6)
    rrect(c, -210, -60, 420, 120, 16, paint(GOLD, 1, stroke=10))
    text(c, "LEGALLY", 0, 0, 80, GOLD, shadow=False)
    c.restore()
    for i in range(8):
        ticket(c, 120 + i * 120, 770 + 20 * math.sin(t * 2 + i), 0.42, rot=-15 + i * 4)


def s2(c, t, d, k):
    def store():
        rrect(c, 240, 520, 600, 420, 14, paint((60, 66, 84)))
        rrect(c, 220, 470, 640, 90, 14, paint(RED))
        text(c, "PARTY STORE", 540, 515, 54, WHITE, face="archivo", shadow=False)
        rrect(c, 300, 620, 220, 160, 8, paint(GOLD, 0.8))
        rrect(c, 580, 640, 200, 300, 8, paint((40, 44, 56)))
    pop(c, 540, 700, prog(t, 0.0, 0.4), store)
    pop(c, 540, 1250, prog(t, 0.4, 0.4), lambda: person(c, 540, 1250, 0.95, rgb=(40, 46, 64), rim=GOLD, hair=(220, 220, 225)))
    pop(c, 540, 380, prog(t, 0.6, 0.3), lambda: (rrect(c, 540 - 220, 342, 440, 76, 16, paint(INK, 0.9)),
                                                 text(c, "EVART, MICHIGAN", 540, 380, 46, WHITE, face="archivo")))


def s3(c, t, d, k):
    def paper():
        rrect(c, 260, 380, 560, 760, 12, paint((236, 232, 222)))
        text(c, "WINFALL RULES", 540, 450, 54, INK, shadow=False)
        for i in range(10):
            y = 530 + i * 56
            c.drawLine(310, y, 770 - (i % 3) * 70, y, paint((140, 130, 120), 1, stroke=6))
    pop(c, 540, 760, prog(t, 0.0, 0.4), paper)
    hl = prog(t, 0.9, 0.5)
    if hl > 0:
        rrect(c, 300, 742, 470 * hl, 52, 6, paint(GOLD, 0.55))
        text(c, "ROLL-DOWN", 540, 768, 44, RED, a=hl, face="archivo", shadow=False)
    c.drawCircle(lerp(820, 600, out_cubic(prog(t, 0.6, 0.6))), lerp(1100, 800, out_cubic(prog(t, 0.6, 0.6))), 70,
                 paint(WHITE, 0.25 * prog(t, 0.6, 0.3), stroke=12))


def s4(c, t, d, k):
    big = 1 - 0.55 * in_out(prog(t, 0.8, 1.0))
    rrect(c, 340, 380, 400, 180 * big + 40, 20, paint(GOLD))
    text(c, "JACKPOT", 540, 420, 50, INK, face="archivo", shadow=False)
    text(c, "NO WINNER", 540, 620, 56, RED, a=out_cubic(prog(t, 0.3, 0.3)), face="archivo")
    for i in range(6):  # money pours down into the small prizes
        tt = t - 0.9 - i * 0.12
        if tt > 0:
            x = lerp(540, 200 + i * 136, clamp(tt / 0.7))
            y = lerp(560, 1060, clamp(tt / 0.7))
            coin(c, x, y, 30, spin=tt * 9)
    for i in range(4):
        rrect(c, 140 + i * 220, 1100, 180, 140, 14, paint(GREEN, 0.25 + 0.6 * prog(t, 1.4 + i * 0.1, 0.4)))
        text(c, "SMALL PRIZE", 230 + i * 220, 1170, 26, WHITE, face="archivo", shadow=False)


def s5(c, t, d, k):
    ticket(c, 300, 760, 1.2, rot=-4)
    text(c, "COST", 300, 560, 48, GREY, face="archivo")
    text(c, "$2", 300, 980, 110, WHITE)
    v = in_out(prog(t, 0.3, 0.8))
    text(c, "WORTH", 790, 560, 48, GREY, face="archivo")
    text(c, "MORE", 790, 720, 120, GREEN, glow=0.4 * v, scale=0.6 + 0.4 * v, a=v)
    text(c, "THAN $2", 790, 840, 70, GREEN, a=v)
    st = prog(t, 1.2, 0.25)
    if st > 0:
        c.save()
        c.translate(540, 1170)
        c.rotate(-6)
        c.scale(lerp(2, 1, out_cubic(st)), lerp(2, 1, out_cubic(st)))
        rrect(c, -330, -70, 660, 140, 18, paint(GOLD, min(1, st * 2), stroke=12))
        text(c, "THE MATH WINS", 0, 0, 92, GOLD, a=min(1, st * 2), shadow=False)
        c.restore()


def s6(c, t, d, k):
    for i in range(3):
        a = out_back(prog(t, 0.1 + i * 0.3, 0.35))
        if a > 0:
            ticket(c, 300 + i * 240, 700, 0.9 * a, rot=-8 + i * 8)
    w = prog(t, 0.9, 0.3)
    if w > 0:
        text(c, "WINNER", 540, 1050, 150, GREEN, scale=lerp(1.8, 1, out_cubic(w)), a=min(1, w * 2), glow=0.6)


def s7(c, t, d, k):
    couple(c, 540, 1270, 0.95)
    rng = random.Random(4)
    for i in range(int(prog(t, 0.0, 1.6) * 40)):  # a growing pile of tickets
        x, y = rng.randint(140, 940), rng.randint(380, 900)
        ticket(c, x, y, 0.38, rot=rng.uniform(-30, 30))
    text(c, "THOUSANDS OF TICKETS", 540, 960, 60, GOLD, face="archivo", a=out_cubic(prog(t, 1.0, 0.3)))


def s8(c, t, d, k):
    v = in_out(prog(t, 0.2, 1.4))
    text(c, money_str(26_000_000 * v), 540, 500, 130, GREEN, glow=0.6 if v >= 1 else 0.2)
    text(c, "IN PRIZES · 9 YEARS", 540, 620, 50, WHITE, face="archivo")
    p = out_back(prog(t, 1.6, 0.4))
    if p > 0:
        rrect(c, 540 - 330, 760, 660, 200, 24, paint(INK, 0.9))
        rrect(c, 540 - 330, 760, 660, 200, 24, paint(GOLD, 1, stroke=5))
        text(c, "~$8,000,000 PROFIT", 540, 860, 74, GOLD, scale=p)
    rng = random.Random(8)
    if t > 1.4:
        for i in range(14):
            x = rng.uniform(80, 1000)
            y = 1000 + (t - 1.4) * rng.uniform(200, 500)
            if y < 1300:
                coin(c, x, y, 26, spin=t * 6 + i)


def s9(c, t, d, k):
    rng = random.Random(1)
    for i in range(10):  # floating maths
        sym = rng.choice(["+", "×", "÷", "=", "%", "∑"])
        x, y = rng.randint(120, 960), rng.randint(380, 1200)
        text(c, sym, x, y + 20 * math.sin(t * 2 + i), 80, BLUE, a=0.45)
    st = prog(t, 0.2, 0.25)
    if st > 0:
        c.save()
        c.translate(540, 700)
        c.rotate(-6)
        c.scale(lerp(2, 1, out_cubic(st)), lerp(2, 1, out_cubic(st)))
        rrect(c, -300, -90, 600, 180, 20, paint(GOLD, min(1, st * 2), stroke=14))
        text(c, "JUST MATH", 0, 0, 120, GOLD, a=min(1, st * 2), shadow=False)
        c.restore()
    text(c, "NO CHEATING", 540, 960, 70, GREEN, face="archivo", a=out_cubic(prog(t, 0.5, 0.3)))


def s10(c, t, d, k):
    s1(c, t, d, k)


SCENES = [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10]

UPLOAD = {
    "title": "This Couple Beat the Lottery… Legally 🎟️ #shorts",
    "description": ("Jerry and Marge Selbee, a retired couple from Michigan, noticed that in 'roll-down' weeks of the Winfall "
                    "lottery a ticket was worth more than it cost. Buying in bulk on those draws, they won about $26 million in "
                    "prizes over nine years - around $8 million profit. It was legal; the games were later ended.\n\n"
                    "#lottery #money #math #truestory #papertrail"),
    "tags": ["jerry selbee", "marge selbee", "lottery", "winfall", "lottery loophole", "math", "money", "true story", "paper trail"],
    "pinned": "Would YOU have spotted the loophole? 🤔👇",
}
