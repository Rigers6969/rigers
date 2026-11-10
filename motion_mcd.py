"""Paper Trail Short: McDonald's is really a real-estate company (animated with motion.py).

Facts: in the 1950s Ray Kroc's franchising earned little. His finance chief Harry Sonneborn set up a company
that bought or leased the land under restaurants and rented it to the franchisees, so the rent came on top of
the fees - and a franchisee who stopped paying could lose the restaurant. Sonneborn is quoted as saying they
were not in the hamburger business but in real estate. Today McDonald's earns billions a year in rent from franchisees.
"""
import math
import random

import skia

from motion import (GOLD, GREEN, GREY, INK, RED, WHITE, clamp, coin, draw_on, in_out, lerp, money_str, out_back,
                    out_cubic, out_elastic, paint, person, pop, prog, rrect, text)

SLUG = "paper-trail-mcdonalds-real-estate-short"
CHANNEL = "Paper Trail"
BRAND = "PAPER TRAIL"
ACCENT = GOLD
TITLE = "McDONALD'S ISN'T A BURGER COMPANY"
W_ = 1080

LINES = [
    ("McDonald's doesn't really make its money from burgers.", "McDonald's doesn't really make its money from BURGERS."),
    ("In the nineteen fifties, Ray Kroc was selling franchises, and barely making money.",
     "In the 1950s, RAY KROC was selling franchises, and barely making money."),
    ("Then his finance guy, Harry Sonneborn, had an idea.", "Then his finance guy, HARRY SONNEBORN, had an IDEA."),
    ("Buy the land under every restaurant.", "Buy the LAND under every restaurant."),
    ("Then rent it to the owner.", "Then RENT it to the owner."),
    ("If they stop paying, they lose the restaurant.", "If they stop paying, they LOSE the restaurant."),
    ("He reportedly said: we're not in the hamburger business. We're in real estate.",
     "He reportedly said: \"We're not in the HAMBURGER business. We're in REAL ESTATE.\""),
    ("Today, owners pay McDonald's billions in rent, every single year.", "Today, owners pay McDonald's BILLIONS in RENT, every single year."),
    ("The burgers bring you in. The land makes the money.", "The burgers bring you in. The LAND makes the MONEY."),
    ("So McDonald's doesn't really make its money from...", "So McDonald's doesn't really make its money from..."),
]

SFX = {
    0: [(0.4, "stamp")],
    1: [(0.1, "pop"), (0.6, "pop")],
    2: [(0.1, "pop"), (0.8, "ching")],
    3: [(0.1, "whoosh"), (0.5, "pop"), (0.7, "pop"), (0.9, "pop")],
    4: [(0.2, "pop"), (0.8, "tick"), (1.0, "tick"), (1.2, "tick")],
    5: [(0.3, "boom")],
    6: [(0.3, "pop"), (2.0, "stamp")],
    7: [(0.1, "riser"), (0.2, "pop"), (1.4, "ching")],
    8: [(0.2, "whoosh"), (1.0, "pop")],
    9: [(0.4, "stamp")],
}


def burger(c, x, y, s):
    c.save()
    c.translate(x, y)
    c.scale(s, s)
    top = skia.Path()
    top.addArc(skia.Rect.MakeXYWH(-230, -230, 460, 300), 180, 180)
    top.close()
    c.drawPath(top, paint((226, 156, 70)))
    for sx, sy in ((-120, -150), (-40, -175), (60, -160), (140, -135), (0, -120)):
        c.drawOval(skia.Rect.MakeXYWH(sx - 10, sy - 5, 20, 10), paint((250, 236, 200)))
    rrect(c, -245, -90, 490, 40, 20, paint((100, 190, 60)))          # lettuce
    rrect(c, -235, -55, 470, 34, 10, paint((240, 196, 40)))          # cheese
    rrect(c, -230, -25, 460, 70, 30, paint((110, 60, 34)))           # patty
    rrect(c, -230, 45, 460, 80, 34, paint((214, 146, 64)))           # bun bottom
    c.restore()


def house(c, x, y, s, colr=(60, 66, 84)):
    c.save()
    c.translate(x, y)
    c.scale(s, s)
    c.drawRect(skia.Rect.MakeXYWH(-120, -100, 240, 160), paint(colr))
    roof = skia.Path()
    roof.moveTo(-150, -95)
    roof.lineTo(0, -200)
    roof.lineTo(150, -95)
    roof.close()
    c.drawPath(roof, paint((180, 40, 44)))
    rrect(c, -30, -10, 60, 70, 6, paint(GOLD))
    c.restore()


def land(c, x, y, w, a=1.0, label=True):
    rrect(c, x - w / 2, y, w, 70, 10, paint((80, 140, 70), a))
    for i in range(int(w / 40)):
        c.drawLine(x - w / 2 + 20 + i * 40, y + 10, x - w / 2 + 30 + i * 40, y + 60, paint((60, 110, 54), a, stroke=4))
    if label:
        text(c, "LAND", x, y + 36, 40, WHITE, a=a, face="archivo", shadow=False)


def s1(c, t, d, k):
    burger(c, 540, 820, 1.25 + 0.03 * math.sin(t * 3))
    st = clamp(t / 0.25 + 1)  # already there on the first frame
    c.save()
    c.translate(540, 1150)
    c.rotate(-8)
    rrect(c, -330, -80, 660, 160, 20, paint(RED, st, stroke=14))
    text(c, "NOT BURGERS", 0, 0, 110, RED, a=st, shadow=False)
    c.restore()


def s2(c, t, d, k):
    pop(c, 540, 1240, prog(t, 0.0, 0.4), lambda: person(c, 540, 1240, 1.1, rgb=(36, 42, 60), rim=GOLD, hair=(200, 200, 205)))
    pop(c, 540, 1290, prog(t, 0.3, 0.3), lambda: (rrect(c, 540 - 170, 1255, 340, 70, 16, paint(GOLD)),
                                                  text(c, "RAY KROC", 540, 1290, 44, INK, face="archivo", shadow=False)))
    tag = prog(t, 0.5, 0.3)
    pop(c, 540, 420, tag, lambda: (rrect(c, 540 - 200, 380, 400, 80, 16, paint(INK, 0.9)),
                                   text(c, "1950s", 540, 420, 56, WHITE, face="archivo")))
    v = out_back(prog(t, 0.9, 0.4))
    text(c, "BARELY ANY PROFIT", 540, 620, 78, RED, scale=v, glow=0.3)
    if v > 0:
        coin(c, 540, 760, 22, spin=t * 5)


def s3(c, t, d, k):
    pop(c, 540, 1240, prog(t, 0.0, 0.4), lambda: person(c, 540, 1240, 1.1, rgb=(36, 42, 60), rim=GREEN))
    pop(c, 540, 1290, prog(t, 0.3, 0.3), lambda: (rrect(c, 540 - 230, 1255, 460, 70, 16, paint(GREEN)),
                                                  text(c, "HARRY SONNEBORN", 540, 1290, 40, INK, face="archivo", shadow=False)))
    b = out_elastic(prog(t, 0.7, 0.8))
    c.save()
    c.translate(540, 560)
    c.scale(b, b)
    c.drawCircle(0, 0, 150, paint(GOLD, 0.35, blur=40))
    c.drawCircle(0, -20, 110, paint(GOLD))
    rrect(c, -50, 80, 100, 60, 10, paint((150, 150, 160)))
    text(c, "IDEA", 0, -20, 60, INK, shadow=False)
    c.restore()


def s4(c, t, d, k):
    for i, x in enumerate((240, 540, 840)):
        a = out_back(prog(t, 0.3 + i * 0.2, 0.4))
        if a > 0:
            land(c, x, 1000, 260, a)
            house(c, x, 1000 - 60, 0.9 * a)
    st = prog(t, 1.0, 0.25)
    if st > 0:
        c.save()
        c.translate(540, 520)
        c.rotate(-6)
        c.scale(lerp(2, 1, out_cubic(st)), lerp(2, 1, out_cubic(st)))
        rrect(c, -300, -75, 600, 150, 18, paint(GOLD, min(1, st * 2), stroke=12))
        text(c, "OWN THE LAND", 0, 0, 96, GOLD, a=min(1, st * 2), shadow=False)
        c.restore()


def s5(c, t, d, k):
    land(c, 540, 1060, 600)
    house(c, 540, 1000, 1.4)
    pop(c, 780, 600, prog(t, 0.2, 0.4), lambda: (rrect(c, 780 - 200, 520, 400, 160, 20, paint((236, 232, 222))),
                                                 text(c, "RENT DUE", 780, 570, 54, RED, shadow=False),
                                                 text(c, "EVERY MONTH", 780, 640, 40, INK, face="archivo", shadow=False)))
    for i in range(6):
        tt = t - 0.6 - i * 0.18
        if tt > 0:
            x = lerp(540, 300, clamp(tt / 0.6))
            y = lerp(980, 640, clamp(tt / 0.6)) - 160 * math.sin(math.pi * clamp(tt / 0.6))
            coin(c, x, y, 30, a=clamp(1.6 - tt * 1.5), spin=tt * 8)
    text(c, "→ McDONALD'S", 300, 560, 46, GOLD, face="archivo", a=out_cubic(prog(t, 0.6, 0.3)))


def s6(c, t, d, k):
    hit = prog(t, 0.3, 0.4)
    sh = 12 * math.sin(t * 50) * (1 - hit) if hit < 1 else 0
    land(c, 540, 1060, 600)
    c.save()
    c.translate(sh, 0)
    house(c, 540, 1000, 1.4, colr=(lerp(60, 120, hit), lerp(66, 40, hit), lerp(84, 44, hit)))
    c.restore()
    st = prog(t, 0.3, 0.25)
    if st > 0:
        c.save()
        c.translate(540, 520)
        c.rotate(-8)
        c.scale(lerp(2.2, 1, out_cubic(st)), lerp(2.2, 1, out_cubic(st)))
        rrect(c, -260, -80, 520, 160, 18, paint(RED, min(1, st * 2), stroke=14))
        text(c, "EVICTED", 0, 0, 120, RED, a=min(1, st * 2), shadow=False)
        c.restore()


def s7(c, t, d, k):
    pop(c, 300, 1250, prog(t, 0.0, 0.4), lambda: person(c, 300, 1250, 1.0, rgb=(36, 42, 60), rim=GREEN))
    b = prog(t, 0.3, 0.35)
    def bubble():
        rrect(c, 260, 360, 760, 420, 40, paint(WHITE))
        tail = skia.Path()
        tail.moveTo(380, 770)
        tail.lineTo(320, 880)
        tail.lineTo(470, 770)
        tail.close()
        c.drawPath(tail, paint(WHITE))
        text(c, "WE'RE NOT IN THE", 640, 450, 58, INK, shadow=False)
        text(c, "HAMBURGER", 640, 540, 84, RED, shadow=False)
        text(c, "BUSINESS.", 640, 630, 58, INK, shadow=False)
    pop(c, 640, 570, b, bubble)
    st = prog(t, 2.0, 0.25)
    if st > 0:
        c.save()
        c.translate(660, 900)
        c.rotate(-6)
        c.scale(lerp(2, 1, out_cubic(st)), lerp(2, 1, out_cubic(st)))
        rrect(c, -300, -70, 600, 140, 18, paint(GOLD, min(1, st * 2), stroke=12))
        text(c, "REAL ESTATE.", 0, 0, 92, GOLD, a=min(1, st * 2), shadow=False)
        c.restore()


def s8(c, t, d, k):
    rng = random.Random(5)
    for i in range(18):  # a map full of restaurants
        a = prog(t, 0.1 + i * 0.05, 0.3)
        if a > 0:
            x, y = rng.randint(120, 960), rng.randint(660, 1230)
            pop(c, x, y, a, lambda x=x, y=y: (c.drawCircle(x, y, 26, paint(RED)), c.drawCircle(x, y, 10, paint(WHITE))))
    v = in_out(prog(t, 0.4, 1.0))
    text(c, "BILLIONS", 540, 400, 150, GREEN, glow=0.6 if v >= 1 else 0.2, scale=0.6 + 0.4 * v)
    text(c, "IN RENT · EVERY YEAR", 540, 520, 50, WHITE, face="archivo", a=out_cubic(prog(t, 1.2, 0.3)))


def s9(c, t, d, k):
    sl = in_out(prog(t, 0.1, 0.6))
    burger(c, lerp(540, 300, sl), 800, lerp(1.0, 0.55, sl))
    text(c, "BRINGS YOU IN", 300, 1040, 44, WHITE, face="archivo", a=sl)
    a = out_back(prog(t, 0.8, 0.5))
    if a > 0:
        land(c, 780, 860, 300, a)
        house(c, 780, 800, 0.9 * a)
        text(c, "MAKES THE MONEY", 780, 1040, 44, GOLD, face="archivo", a=min(1, a))
        coin(c, 780, 620, 50 * a, spin=t * 4)


def s10(c, t, d, k):
    s1(c, t, d, k)


SCENES = [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10]

UPLOAD = {
    "title": "McDonald's Isn't Really a Burger Company 🍔 #shorts",
    "description": ("In the 1950s, Ray Kroc's franchising made little money - until his finance chief Harry Sonneborn bought "
                    "the land under the restaurants and rented it to the franchise owners. Sonneborn is quoted as saying "
                    "they were not in the hamburger business, but in real estate. Today franchisees pay McDonald's billions "
                    "in rent every year.\n\n#mcdonalds #business #realestate #money #papertrail"),
    "tags": ["mcdonalds", "real estate", "ray kroc", "harry sonneborn", "business", "money", "franchise", "finance", "paper trail"],
    "pinned": "Did you know this? Which company should I break down next? 👇",
}
