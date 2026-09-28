"""Turns an OpenStreetMap export (.osm) of Babrru into one Roblox Script
(BabrruMap.server.lua): every real road (with its real name, width class
and surface), every real building footprint, zebra crossings, stop signs,
traffic lights, bus stops, the river, water, woods, and name labels for
real shops/schools/churches.

    python tools/osm_to_babrru.py data/babrru.osm BabrruMap.server.lua

All geometry is computed here, so the in-game part (babrru_builder.lua,
appended to the output) only has to create parts from flat number lists.

Map data (c) OpenStreetMap contributors, ODbL - the game shows that
credit on a sign next to the spawn point.
"""
from __future__ import annotations

import json
import math
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

SCALE = 2.5  # studs per real meter - real street widths fit the game's cars at this scale
FLOOR = 3.0  # meters per building floor

TOOLS_DIR = Path(__file__).resolve().parent

# -- styles -----------------------------------------------------------
# name, rgb, material, collide, transparency, reflectance, shadow, folder, lit-at-night
STYLE_DEFS = [
    ("Asphalt", (48, 48, 52), "Asphalt", 1, 0, 0, 0, "Roads", 0),
    ("Concrete", (150, 150, 146), "Concrete", 1, 0, 0, 0, "Roads", 0),
    ("Cobbles", (120, 112, 104), "Cobblestone", 1, 0, 0, 0, "Roads", 0),
    ("Dirt", (125, 105, 80), "Ground", 1, 0, 0, 0, "Roads", 0),
    ("Path", (165, 160, 150), "Pavement", 1, 0, 0, 0, "Roads", 0),
    ("Marking", (235, 235, 228), "SmoothPlastic", 0, 0, 0, 0, "Markings", 0),
    ("Water", (45, 95, 125), "Glass", 0, 0.15, 0.3, 0, "Water", 0),
    ("Plaster", (236, 228, 210), "Plaster", 1, 0, 0, 1, "Buildings", 0),
    ("Brick", (160, 72, 50), "Brick", 1, 0, 0, 1, "Buildings", 0),
    ("Window", (255, 214, 140), "Glass", 0, 0.35, 0, 0, "Buildings", 1),
    ("WindowDark", (30, 38, 52), "Glass", 0, 0, 0.1, 0, "Buildings", 0),
    ("Canopy", (225, 225, 228), "Metal", 1, 0, 0, 1, "Buildings", 0),
    ("Trunk", (95, 70, 50), "Wood", 1, 0, 0, 1, "Trees", 0),
    ("Leaves", (50, 125, 50), "LeafyGrass", 0, 0, 0, 1, "Trees", 0),
    ("ShelterGlass", (180, 210, 225), "Glass", 1, 0.5, 0, 0, "StreetFurniture", 0),
    ("ShelterFrame", (60, 62, 68), "Metal", 1, 0, 0, 1, "StreetFurniture", 0),
    ("SignalBox", (30, 30, 32), "Metal", 1, 0, 0, 1, "StreetFurniture", 0),
    ("SignalRed", (255, 40, 30), "Neon", 0, 0, 0, 0, "StreetFurniture", 0),
    ("SignalYellow", (255, 190, 30), "Neon", 0, 0.6, 0, 0, "StreetFurniture", 0),
    ("SignalGreen", (40, 255, 90), "Neon", 0, 0.6, 0, 0, "StreetFurniture", 0),
    ("Pitch", (60, 140, 60), "Grass", 1, 0, 0, 0, "Roads", 0),
]
# Albanian suburbs: lots of pastel/cream plaster and unfinished red brick.
FACADE_COLORS = [
    (236, 228, 210), (245, 240, 232), (222, 206, 176), (240, 214, 160), (232, 190, 150),
    (200, 214, 222), (214, 226, 200), (238, 200, 196), (190, 190, 185), (250, 250, 246),
]
STYLES = []  # expanded list incl. one plaster style per facade color
STYLE_INDEX = {}

ROOF_TILE_COLORS = [(170, 72, 48), (158, 64, 44), (182, 88, 58), (140, 58, 42)]
ROOF_PITCH_DEG = 28

NAMED_COLORS = {
    "white": (245, 245, 242), "black": (35, 35, 38), "grey": (150, 150, 150), "gray": (150, 150, 150),
    "lightgrey": (200, 200, 198), "lightgray": (200, 200, 198), "darkgrey": (90, 90, 92), "darkgray": (90, 90, 92),
    "red": (175, 55, 45), "darkred": (130, 40, 35), "maroon": (120, 35, 30), "brown": (120, 80, 55),
    "orange": (235, 140, 60), "yellow": (240, 210, 110), "beige": (225, 210, 180), "cream": (240, 230, 205),
    "tan": (210, 180, 140), "pink": (235, 180, 185), "blue": (90, 130, 190), "lightblue": (170, 200, 225),
    "green": (110, 160, 100), "lightgreen": (175, 210, 160), "terracotta": (170, 72, 48), "silver": (190, 192, 196),
}


def parse_color(value):
    """OSM colour tag (name or #rrggbb) -> rgb, or None."""
    if not value:
        return None
    v = value.strip().lower().replace(" ", "")
    if v.startswith("#") and len(v) in (4, 7):
        if len(v) == 4:
            v = "#" + "".join(ch * 2 for ch in v[1:])
        try:
            return tuple(int(v[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            return None
    return NAMED_COLORS.get(v)


def color_style(rgb, kind):
    """A style for an arbitrary wall/roof colour, created on first use."""
    key = f"{kind}_{rgb[0]}_{rgb[1]}_{rgb[2]}"
    if key not in STYLE_INDEX:
        STYLE_INDEX[key] = len(STYLES) + 1
        if kind == "wall":
            STYLES.append(("Building", rgb, "Plaster", 1, 0, 0, 1, "Buildings", 0))
        else:
            STYLES.append(("Roof", rgb, "Slate", 1, 0, 0, 1, "Buildings", 0))
    return key


def build_styles():
    for d in STYLE_DEFS:
        STYLE_INDEX[d[0]] = len(STYLES) + 1
        STYLES.append(d)
    for i, rgb in enumerate(FACADE_COLORS):
        name = f"Facade{i}"
        STYLE_INDEX[name] = len(STYLES) + 1
        STYLES.append(("Building", rgb, "Plaster", 1, 0, 0, 1, "Buildings", 0))


# -- road classes -----------------------------------------------------
# default width (m), draw height (top of surface, studs; higher classes on top at junctions), lamps, center line, edge lines
ROAD_CLASSES = {
    "trunk": (12, 0.46, True, True, True),
    "trunk_link": (6, 0.45, True, False, True),
    "primary": (11, 0.46, True, True, True),
    "secondary": (9, 0.45, True, True, True),
    "tertiary": (8, 0.44, True, True, False),
    "unclassified": (6, 0.43, False, False, False),
    "residential": (6, 0.43, False, False, False),
    "living_street": (5, 0.42, False, False, False),
    "service": (4, 0.41, False, False, False),
    "track": (3.5, 0.40, False, False, False),
    "pedestrian": (4, 0.39, False, False, False),
    "footway": (2, 0.38, False, False, False),
    "path": (1.8, 0.38, False, False, False),
    "steps": (2, 0.38, False, False, False),
    "cycleway": (2, 0.38, False, False, False),
}
CAR_ROADS = {"trunk", "trunk_link", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service", "track"}
PATHS = {"pedestrian", "footway", "path", "steps", "cycleway"}
ROAD_THICK = 0.6

DIRT_SURFACES = {"unpaved", "gravel", "compacted", "dirt", "ground", "fine_gravel", "earth", "mud", "sand", "dirtq", "grass"}


def rd(v, places=None):
    """Rounds for compact output: 0.1 for big numbers, 0.01 for small."""
    if places is None:
        places = 1 if abs(v) >= 10 else 2
    r = round(v, places)
    text = f"{r:.{places}f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


class Out:
    def __init__(self):
        self.roofs = []  # WedgeParts, same 8-number layout as boxes
        self.boxes = []
        self.wedges = []
        self.balls = []
        self.lamps = []
        self.signs = []
        self.labels = []

    def box(self, style, cx, cy, cz, sx, sy, sz, yaw_deg):
        self.boxes.extend([STYLE_INDEX[style], cx, cy, cz, sx, sy, sz, yaw_deg])


def yaw_for(dx, dz):
    """Yaw (degrees) for CFrame.Angles(0, yaw, 0) so a part's local X axis
    points along (dx, dz): Angles(0, t, 0) maps X to (cos t, 0, -sin t)."""
    return math.degrees(math.atan2(-dz, dx))


def gabled_roof(out, style, cx, cz, lu, lv, c, s, wall_top):
    """A pitched roof on a rectangular building: two WedgeParts leaning
    against each other along the ridge (which runs along the longer side).
    A WedgePart is full height at its +Z face and slopes down to -Z, so
    each one's +Z face sits on the ridge."""
    if lu >= lv:
        rx, rz, length, width = c, s, lu, lv
    else:
        rx, rz, length, width = -s, c, lv, lu
    overhang = 0.3 * SCALE
    half = width / 2 + overhang
    rise = math.tan(math.radians(ROOF_PITCH_DEG)) * (width / 2)
    # For CFrame.Angles(0, t, 0) with local X along (rx, rz), local Z is (-rz, rx).
    zx, zz = -rz, rx
    y = wall_top + rise / 2
    for sign in (1, -1):
        # this half's local X is sign*(rx, rz), so its +Z is sign*(zx, zz),
        # and it sits on the opposite side of the ridge from where +Z points
        px, pz = cx - sign * zx * half / 2, cz - sign * zz * half / 2
        out.roofs.extend([STYLE_INDEX[style], px, y, pz, length + 2 * overhang, rise, half, yaw_for(sign * rx, sign * rz)])
    return rise


def seg_box(out, style, a, b, width, y_top, thick, extend=0.0):
    """A flat box along a->b (x, z in studs), top at y_top."""
    dx, dz = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dz)
    if length < 0.05:
        return
    # Roblox caps parts at 2048 studs; split very long stretches.
    pieces = max(1, math.ceil(length / 1000))
    ux, uz = dx / length, dz / length
    for k in range(pieces):
        s0, s1 = length * k / pieces, length * (k + 1) / pieces
        e0 = extend if k == 0 else 0
        e1 = extend if k == pieces - 1 else 0
        mid = (s0 - e0 + s1 + e1) / 2
        out.box(style, a[0] + ux * mid, y_top - thick / 2, a[1] + uz * mid, (s1 - s0) + e0 + e1, thick, width, yaw_for(dx, dz))


# -- triangles as wedge pairs -----------------------------------------
def sub(p, q): return (p[0] - q[0], p[1] - q[1], p[2] - q[2])
def add(p, q): return (p[0] + q[0], p[1] + q[1], p[2] + q[2])
def mul(p, s): return (p[0] * s, p[1] * s, p[2] * s)
def dot(p, q): return p[0] * q[0] + p[1] * q[1] + p[2] * q[2]
def cross(p, q): return (p[1] * q[2] - p[2] * q[1], p[2] * q[0] - p[0] * q[2], p[0] * q[1] - p[1] * q[0])
def unit(p):
    m = math.sqrt(dot(p, p))
    return (p[0] / m, p[1] / m, p[2] / m)


def triangle_wedges(a, b, c, thickness):
    """Two WedgeParts that exactly fill triangle abc (3D points), with the
    given thickness perpendicular to it (the widely used Roblox
    draw-triangle method). Returns [(pos, right, up, size)] for
    CFrame.fromMatrix(pos, right, up)."""
    ab, ac, bc = sub(b, a), sub(c, a), sub(c, b)
    abd, acd, bcd = dot(ab, ab), dot(ac, ac), dot(bc, bc)
    if abd > acd and abd > bcd:
        c, a = a, c
    elif acd > bcd and acd > abd:
        a, b = b, a
    ab, ac, bc = sub(b, a), sub(c, a), sub(c, b)
    right = unit(cross(ac, ab))
    up = unit(cross(bc, right))
    back = unit(bc)
    height = abs(dot(ab, up))
    w1 = (mul(add(a, b), 0.5), right, up, (thickness, height, abs(dot(ab, back))))
    w2 = (mul(add(a, c), 0.5), mul(right, -1), up, (thickness, height, abs(dot(ac, back))))
    return [w1, w2]


def add_prism(out, style, tri2d, y_bottom, height):
    """A triangle-shaped column from y_bottom up by `height`."""
    y_mid = y_bottom + height / 2
    pts = [(p[0], y_mid, p[1]) for p in tri2d]
    if abs(cross(sub(pts[1], pts[0]), sub(pts[2], pts[0]))[1]) < 0.05:
        return  # degenerate sliver
    for pos, right, up, size in triangle_wedges(pts[0], pts[1], pts[2], height):
        if size[1] < 0.02 or size[2] < 0.02:
            continue
        out.wedges.extend([STYLE_INDEX[style], *pos, *right, *up, *size])


def polygon_area(ring):
    return sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1] for i in range(len(ring))) / 2


def clean_ring(ring):
    out = []
    for p in ring:
        if not out or math.dist(out[-1], p) > 0.05:
            out.append(p)
    if len(out) > 1 and math.dist(out[0], out[-1]) <= 0.05:
        out.pop()
    # drop collinear points
    changed = True
    while changed and len(out) > 3:
        changed = False
        for i in range(len(out)):
            a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
            if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < 0.01:
                out.pop(i)
                changed = True
                break
    return out


def triangulate(ring):
    """Ear clipping. Returns triangles; falls back to a fan if the ring is
    self-intersecting."""
    pts = list(ring)
    if polygon_area(pts) < 0:
        pts.reverse()
    idx = list(range(len(pts)))
    tris = []

    def is_convex(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 1e-9

    def inside(p, a, b, c):
        d1 = (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])
        d2 = (p[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (p[1] - c[1])
        d3 = (p[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (p[1] - a[1])
        neg = d1 < 0 or d2 < 0 or d3 < 0
        pos = d1 > 0 or d2 > 0 or d3 > 0
        return not (neg and pos)

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if not is_convex(a, b, c):
                continue
            if any(inside(pts[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((a, b, c))
            idx.pop(k)
            break
        else:
            # no ear found (bad geometry): fan the rest
            for k in range(1, len(idx) - 1):
                tris.append((pts[idx[0]], pts[idx[k]], pts[idx[k + 1]]))
            return tris
    if len(idx) == 3:
        tris.append((pts[idx[0]], pts[idx[1]], pts[idx[2]]))
    return tris


def min_area_rect(ring):
    best = None
    for i in range(len(ring)):
        ex, ez = ring[(i + 1) % len(ring)][0] - ring[i][0], ring[(i + 1) % len(ring)][1] - ring[i][1]
        if ex == 0 and ez == 0:
            continue
        ang = math.atan2(ez, ex)
        c, s = math.cos(ang), math.sin(ang)
        # coordinates along (c, s) and across (-s, c)
        us = [p[0] * c + p[1] * s for p in ring]
        vs = [-p[0] * s + p[1] * c for p in ring]
        area = (max(us) - min(us)) * (max(vs) - min(vs))
        if best is None or area < best[0]:
            u_mid, v_mid = (max(us) + min(us)) / 2, (max(vs) + min(vs)) / 2
            cx, cz = u_mid * c - v_mid * s, u_mid * s + v_mid * c
            best = (area, cx, cz, max(us) - min(us), max(vs) - min(vs), c, s)
    return best


def point_in_poly(p, ring):
    x, z = p
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, zi = ring[i]
        xj, zj = ring[j]
        if (zi > z) != (zj > z) and x < (xj - xi) * (z - zi) / (zj - zi + 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def dist_to_seg(p, a, b):
    dx, dz = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dz * dz
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dz) / L))
    return math.hypot(p[0] - a[0] - dx * t, p[1] - a[1] - dz * t)


class Grid:
    """Spatial hash for 'is this spot free' checks."""

    def __init__(self, cell=80):
        self.cell = cell
        self.items = defaultdict(list)

    def add(self, minx, minz, maxx, maxz, item):
        c = self.cell
        for gx in range(int(minx // c), int(maxx // c) + 1):
            for gz in range(int(minz // c), int(maxz // c) + 1):
                self.items[(gx, gz)].append(item)

    def near(self, x, z):
        return self.items.get((int(x // self.cell), int(z // self.cell)), [])


def main(osm_path, out_path):
    build_styles()
    root = ET.parse(osm_path).getroot()
    bounds = root.find("bounds").attrib
    lat0 = (float(bounds["minlat"]) + float(bounds["maxlat"])) / 2
    lon0 = (float(bounds["minlon"]) + float(bounds["maxlon"])) / 2
    m_lat = 111320.0
    m_lon = 111320.0 * math.cos(math.radians(lat0))

    def project(lat, lon):
        return ((lon - lon0) * m_lon * SCALE, -(lat - lat0) * m_lat * SCALE)

    nodes, node_tags = {}, {}
    for n in root.findall("node"):
        nodes[n.get("id")] = project(float(n.get("lat")), float(n.get("lon")))
        tags = {t.get("k"): t.get("v") for t in n.findall("tag")}
        if tags:
            node_tags[n.get("id")] = tags
    ways = {}
    for w in root.findall("way"):
        ways[w.get("id")] = ({t.get("k"): t.get("v") for t in w.findall("tag")}, [r.get("ref") for r in w.findall("nd") if r.get("ref") in nodes])

    min_x, max_x = project(0, float(bounds["minlon"]))[0], project(0, float(bounds["maxlon"]))[0]
    min_z, max_z = project(float(bounds["maxlat"]), 0)[1], project(float(bounds["minlat"]), 0)[1]

    out = Out()
    S = SCALE

    # ---- roads -------------------------------------------------------
    roads = []  # (way_id, tags, refs, width_studs, top, cls)
    for wid, (tags, refs) in ways.items():
        cls = tags.get("highway")
        if cls not in ROAD_CLASSES or len(refs) < 2 or tags.get("area") == "yes":
            continue
        width_m, top, *_ = ROAD_CLASSES[cls]
        try:
            if "width" in tags:
                width_m = float(tags["width"].replace("m", "").strip())
            elif "lanes" in tags and cls in CAR_ROADS:
                width_m = max(3.0, float(tags["lanes"]) * 3.3)
            elif tags.get("oneway") == "yes" and cls in ("trunk", "primary", "secondary"):
                width_m = 7.0
        except ValueError:
            pass
        roads.append((wid, tags, refs, width_m * S, top, cls))

    # junctions: nodes on 2+ car roads (or on the same road twice)
    node_roads = defaultdict(set)
    node_width = defaultdict(float)
    for wid, tags, refs, w, top, cls in roads:
        if cls not in CAR_ROADS:
            continue
        for r in refs:
            node_roads[r].add(wid)
            node_width[r] = max(node_width[r], w)
    junction = {r for r, ws in node_roads.items() if len(ws) >= 2}

    def clearance(ref):
        return node_width[ref] / 2 + 2 * S if ref in junction else 0.0

    road_segments = []  # for placement checks: (a, b, half_width)
    road_lines = []  # x1 z1 x2 z2 width streetIndex - for the minimap and street names
    street_names = []
    street_index = {}
    marking_count = 0
    for wid, tags, refs, w, top, cls in roads:
        surface = tags.get("surface", "")
        if cls in PATHS:
            style = "Dirt" if surface in DIRT_SURFACES else "Path"
        elif surface in DIRT_SURFACES or cls == "track":
            style = "Dirt"
        elif surface == "concrete":
            style = "Concrete"
        elif surface in ("paving_stones", "sett", "cobblestone"):
            style = "Cobbles"
        else:
            style = "Asphalt"
        pts = [nodes[r] for r in refs]
        name = tags.get("name")
        name_i = 0
        if name and cls in CAR_ROADS:
            if name not in street_index:
                street_names.append(name)
                street_index[name] = len(street_names)
            name_i = street_index[name]
        for a, b in zip(pts, pts[1:]):
            # Extending each piece by half the width fills the gaps at bends.
            seg_box(out, style, a, b, w, top, ROAD_THICK, extend=w / 2)
            road_segments.append((a, b, w / 2))
            if cls in CAR_ROADS:
                road_lines.extend([a[0], a[1], b[0], b[1], w, name_i])

        _, _, lamps, center, edges = ROAD_CLASSES[cls]
        if style != "Asphalt" or cls not in CAR_ROADS:
            continue
        mark_top = top + 0.03
        two_way_center = center and w >= 6 * S
        # Walk the whole road so dashes keep their rhythm across bends.
        cum = [0.0]
        for a, b in zip(pts, pts[1:]):
            cum.append(cum[-1] + math.dist(a, b))
        total = cum[-1]
        blocked = [(cum[i], clearance(refs[i])) for i in range(len(refs)) if refs[i] in junction]

        def clear_at(d, margin=0.0):
            return all(abs(d - jd) > jc + margin for jd, jc in blocked)

        def point_at(d):
            for i in range(len(pts) - 1):
                if cum[i] <= d <= cum[i + 1]:
                    t = (d - cum[i]) / max(cum[i + 1] - cum[i], 1e-9)
                    a, b = pts[i], pts[i + 1]
                    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), i
            return pts[-1], len(pts) - 2

        if two_way_center:
            dash, gap = 3 * S, 9 * S
            d = gap / 2
            while d + dash <= total:
                (p0, i0), (p1, i1) = point_at(d), point_at(d + dash)
                if i0 == i1 and clear_at(d + dash / 2, dash / 2):
                    seg_box(out, "Marking", p0, p1, 0.15 * S, mark_top, 0.05)
                    marking_count += 1
                d += dash + gap
        if edges:
            for i, (a, b) in enumerate(zip(pts, pts[1:])):
                L = math.dist(a, b)
                t0 = clearance(refs[i])
                t1 = L - clearance(refs[i + 1])
                if t1 - t0 < 2 * S:
                    continue
                ux, uz = (b[0] - a[0]) / L, (b[1] - a[1]) / L
                rx, rz = -uz, ux
                for side in (-1, 1):
                    off = side * (w / 2 - 0.4 * S)
                    p0 = (a[0] + ux * t0 + rx * off, a[1] + uz * t0 + rz * off)
                    p1 = (a[0] + ux * t1 + rx * off, a[1] + uz * t1 + rz * off)
                    seg_box(out, "Marking", p0, p1, 0.12 * S, mark_top, 0.05)
                    marking_count += 1

    road_grid = Grid()
    for a, b, hw in road_segments:
        road_grid.add(min(a[0], b[0]) - hw, min(a[1], b[1]) - hw, max(a[0], b[0]) + hw, max(a[1], b[1]) + hw, (a, b, hw))

    def on_road(p, margin=0.0):
        return any(dist_to_seg(p, a, b) < hw + margin for a, b, hw in road_grid.near(*p))

    # ---- buildings ---------------------------------------------------
    # Per-building corrections (floors, colours, roof) - e.g. matched from
    # the user's satellite / Street View screenshots - keyed by OSM way id.
    overrides_path = Path(osm_path).with_name("babrru_overrides.json")
    overrides = {}
    if overrides_path.exists():
        overrides = json.loads(overrides_path.read_text(encoding="utf-8")).get("buildings", {})

    building_grid = Grid()
    rect_count = poly_count = pitched_count = 0
    for wid, (tags, refs) in ways.items():
        if "building" not in tags or len(refs) < 4:
            continue
        if wid in overrides:
            tags = {**tags, **{k: str(v) for k, v in overrides[wid].items() if not k.startswith("_")}}
        ring = clean_ring([nodes[r] for r in refs])
        if len(ring) < 3:
            continue
        area = abs(polygon_area(ring))
        if area < 4 * S * S:
            continue
        kind = tags["building"]
        seed = int(wid) % 1000003
        levels = None
        try:
            if "building:levels" in tags:
                levels = float(tags["building:levels"])
            elif "height" in tags:
                levels = float(tags["height"].replace("m", "")) / FLOOR
        except ValueError:
            pass
        if levels is None:
            if kind in ("house", "semidetached_house", "detached", "garage", "shed", "construction"):
                levels = 1 + seed % 2
            elif kind in ("apartments", "school", "commercial", "retail", "hospital", "clinic", "office"):
                levels = 3 + seed % 3
            else:
                levels = 2 + seed % 3  # typical Babrru: 2-4 floors
        height = max(levels, 1) * FLOOR * S

        xs, zs = [p[0] for p in ring], [p[1] for p in ring]
        building_grid.add(min(xs), min(zs), max(xs), max(zs), ring)

        if kind == "roof":
            # Open canopy (fuel stations): a roof on posts.
            rect = min_area_rect(ring)
            _, cx, cz, lu, lv, c, s = rect
            roof_y = 5 * S
            out.box("Canopy", cx, roof_y, cz, lu, 0.5 * S, lv, yaw_for(c, s))
            for su in (-0.4, 0.4):
                for sv in (-0.4, 0.4):
                    px = cx + c * su * lu - s * sv * lv
                    pz = cz + s * su * lu + c * sv * lv
                    out.box("ShelterFrame", px, roof_y / 2, pz, 0.3 * S, roof_y, 0.3 * S, 0)
            continue

        wall_rgb = parse_color(tags.get("building:colour"))
        if wall_rgb:
            style = color_style(wall_rgb, "wall")
        else:
            style = "Brick" if seed % 100 < 22 else f"Facade{seed % len(FACADE_COLORS)}"
        rect = min_area_rect(ring)
        if rect and area / rect[0] >= 0.9:
            _, cx, cz, lu, lv, c, s = rect
            yaw = yaw_for(c, s)
            # (window bands are added in-game from each building box)
            out.box(style, cx, height / 2, cz, lu, height, lv, yaw)
            rect_count += 1

            # Roof: the mapped roof shape if there is one; otherwise about
            # half the small houses get a pitched red-tile roof, as in Babrru.
            shape = tags.get("roof:shape")
            if shape:
                pitched = shape not in ("flat", "skillion")
            else:
                small_house = kind in ("yes", "house", "residential", "detached", "semidetached_house") and levels <= 3 and area <= 250 * S * S
                pitched = small_house and seed % 100 >= 50
            if pitched:
                roof_rgb = parse_color(tags.get("roof:colour")) or ROOF_TILE_COLORS[seed % len(ROOF_TILE_COLORS)]
                gabled_roof(out, color_style(roof_rgb, "roof"), cx, cz, lu, lv, c, s, height)
                pitched_count += 1
        else:
            for tri in triangulate(ring):
                add_prism(out, style, tri, 0.0, height)
            poly_count += 1

    def in_building(p, margin=0.0):
        for ring in building_grid.near(*p):
            if point_in_poly(p, ring):
                return True
            if margin and any(dist_to_seg(p, ring[i], ring[(i + 1) % len(ring)]) < margin for i in range(len(ring))):
                return True
        return False

    # ---- water -------------------------------------------------------
    water_polys = 0
    def water_ring(ring):
        nonlocal water_polys
        ring = clean_ring(ring)
        if len(ring) >= 3:
            for tri in triangulate(ring):
                add_prism(out, "Water", tri, 0.02, 0.2)
            water_polys += 1

    for wid, (tags, refs) in ways.items():
        if tags.get("natural") == "water" and len(refs) >= 4 and refs[0] == refs[-1]:
            water_ring([nodes[r] for r in refs])
        ww = tags.get("waterway")
        if ww in ("river", "canal", "stream", "ditch", "drain"):
            wm = {"river": 10, "canal": 5, "stream": 3, "ditch": 1.5, "drain": 1.5}[ww]
            pts = [nodes[r] for r in refs]
            for a, b in zip(pts, pts[1:]):
                seg_box(out, "Water", a, b, wm * S, 0.22, 0.2, extend=wm * S / 2)

    # multipolygon relations (water / woods): join their outer ways into rings
    def relation_rings(rel):
        members = [m.get("ref") for m in rel.findall("member") if m.get("type") == "way" and m.get("role") in ("outer", "")]
        chains = [list(ways[m][1]) for m in members if m in ways and len(ways[m][1]) >= 2]
        rings = []
        while chains:
            ring = chains.pop(0)
            grew = True
            while ring[0] != ring[-1] and grew:
                grew = False
                for i, ch in enumerate(chains):
                    if ch[0] == ring[-1]:
                        ring += ch[1:]
                    elif ch[-1] == ring[-1]:
                        ring += ch[::-1][1:]
                    elif ch[-1] == ring[0]:
                        ring = ch[:-1] + ring
                    elif ch[0] == ring[0]:
                        ring = ch[::-1][:-1] + ring
                    else:
                        continue
                    chains.pop(i)
                    grew = True
                    break
            if ring[0] == ring[-1] and len(ring) >= 4:
                rings.append([nodes[r] for r in ring])
        return rings

    wood_rings = []
    for rel in root.findall("relation"):
        rtags = {t.get("k"): t.get("v") for t in rel.findall("tag")}
        if rtags.get("type") != "multipolygon":
            continue
        if rtags.get("natural") == "water" or rtags.get("waterway") == "riverbank":
            for ring in relation_rings(rel):
                water_ring(ring)
        elif rtags.get("natural") in ("wood", "scrub") or rtags.get("landuse") in ("forest", "orchard"):
            wood_rings.extend((ring, rtags.get("natural") or rtags.get("landuse")) for ring in relation_rings(rel))

    # ---- sports pitches ------------------------------------------------
    for wid, (tags, refs) in ways.items():
        if tags.get("leisure") == "pitch" and len(refs) >= 4:
            ring = clean_ring([nodes[r] for r in refs])
            rect = min_area_rect(ring) if len(ring) >= 3 else None
            if rect and abs(polygon_area(ring)) / rect[0] >= 0.85:
                _, cx, cz, lu, lv, c, s = rect
                out.box("Pitch", cx, 0.06, cz, lu, 0.12, lv, yaw_for(c, s))

    # ---- trees in woods / scrub / orchards ----------------------------
    for wid, (tags, refs) in ways.items():
        kind = tags.get("natural") or tags.get("landuse")
        if kind in ("wood", "scrub", "forest", "orchard") and len(refs) >= 4 and refs[0] == refs[-1]:
            wood_rings.append(([nodes[r] for r in refs], kind))
    tree_count = 0
    TREE_LIMIT = 1500
    for ring, kind in wood_rings:
        spacing = {"wood": 9, "forest": 9, "scrub": 13, "orchard": 7}.get(kind, 10) * S
        xs, zs = [p[0] for p in ring], [p[1] for p in ring]
        seedk = 0
        x = min(xs)
        while x < max(xs) and tree_count < TREE_LIMIT:
            z = min(zs)
            while z < max(zs) and tree_count < TREE_LIMIT:
                seedk += 1
                jx = x + ((seedk * 7919) % 100 / 100 - 0.5) * spacing * 0.6
                jz = z + ((seedk * 104729) % 100 / 100 - 0.5) * spacing * 0.6
                p = (jx, jz)
                if point_in_poly(p, ring) and not on_road(p, 1 * S) and not in_building(p, 1 * S):
                    small = kind in ("scrub", "orchard")
                    trunk_h = (2.0 if small else 3.5 + (seedk % 5) * 0.4) * S
                    # (the trunk is added in-game under each tree top)
                    d = (2.2 if small else 3.5 + (seedk % 7) * 0.3) * S
                    out.balls.extend([STYLE_INDEX["Leaves"], jx, trunk_h + d * 0.3, jz, d])
                    tree_count += 1
                z += spacing
            x += spacing

    # ---- things on roads: crossings, stop signs, lights, bus stops -----
    def road_dir_at(ref):
        """Direction and width of the car road through this node."""
        best = None
        for wid, tags, refs, w, top, cls in roads:
            if cls not in CAR_ROADS or ref not in refs:
                continue
            i = refs.index(ref)
            a = nodes[refs[max(i - 1, 0)]]
            b = nodes[refs[min(i + 1, len(refs) - 1)]]
            if math.dist(a, b) < 0.01:
                continue
            cand = ((b[0] - a[0]) / math.dist(a, b), (b[1] - a[1]) / math.dist(a, b), w, top, tags)
            if best is None or w > best[2]:
                best = cand
        return best

    crossings = stops = signals = bus_stops = 0
    for ref, tags in node_tags.items():
        hw = tags.get("highway")
        if hw not in ("crossing", "stop", "traffic_signals", "bus_stop"):
            continue
        info = road_dir_at(ref)
        px, pz = nodes[ref]
        if not info and hw == "bus_stop":
            # Mapped beside the road: use the nearest road within 25 m.
            near = None
            for a, b, hwid in road_segments:
                d = dist_to_seg((px, pz), a, b)
                if d < 25 * S and math.dist(a, b) > 0.01 and (near is None or d < near[0]):
                    near = (d, a, b, hwid)
            if near:
                _, a, b, hwid = near
                L = math.dist(a, b)
                ux, uz = (b[0] - a[0]) / L, (b[1] - a[1]) / L
                # which side of the road the stop is on
                side = 1 if (px - a[0]) * (-uz) + (pz - a[1]) * ux >= 0 else -1
                t = max(0, min(1, ((px - a[0]) * (b[0] - a[0]) + (pz - a[1]) * (b[1] - a[1])) / (L * L)))
                px, pz = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                if side < 0:
                    ux, uz = -ux, -uz
                info = (ux, uz, hwid * 2, 0.43, {})
        if not info:
            continue
        ux, uz, w, top, rtags = info
        rx, rz = -uz, ux
        if hw == "crossing":
            stripe = 0.5 * S
            lat = -w / 2 + stripe
            while lat <= w / 2 - stripe / 2:
                cx, cz = px + rx * lat, pz + rz * lat
                out.box("Marking", cx, top + 0.035, cz, 3 * S, 0.05, stripe, yaw_for(ux, uz))
                lat += 2 * stripe
            crossings += 1
        elif hw == "stop":
            sx, sz = px + rx * (w / 2 + 0.8 * S), pz + rz * (w / 2 + 0.8 * S)
            if not in_building((sx, sz)):
                out.signs.append(("stop", sx, sz, yaw_for(rx, rz), "STOP"))
                stops += 1
        elif hw == "traffic_signals":
            sx, sz = px + rx * (w / 2 + 0.8 * S), pz + rz * (w / 2 + 0.8 * S)
            pole_h = 4.5 * S
            out.box("ShelterFrame", sx, pole_h / 2, sz, 0.2 * S, pole_h, 0.2 * S, 0)
            box_y = pole_h - 0.6 * S
            out.box("SignalBox", sx, box_y, sz, 0.35 * S, 1.2 * S, 0.35 * S, yaw_for(ux, uz))
            for k, style in enumerate(("SignalRed", "SignalYellow", "SignalGreen")):
                out.box(style, sx - ux * 0.2 * S, box_y + (0.35 - 0.35 * k) * S, sz - uz * 0.2 * S, 0.06 * S, 0.25 * S, 0.25 * S, yaw_for(ux, uz))
            signals += 1
        elif hw == "bus_stop":
            off = w / 2 + 1.6 * S
            sx, sz = px + rx * off, pz + rz * off
            if in_building((sx, sz), 1 * S):
                continue
            yaw = yaw_for(ux, uz)
            out.box("ShelterFrame", sx, 2.5 * S, sz, 3.2 * S, 0.12 * S, 1.4 * S, yaw)  # roof
            bx, bz = sx + rx * 0.65 * S, sz + rz * 0.65 * S
            out.box("ShelterGlass", bx, 1.25 * S, bz, 3.0 * S, 2.4 * S, 0.06 * S, yaw)  # back wall
            out.box("ShelterFrame", sx + rx * 0.3 * S, 0.45 * S, sz + rz * 0.3 * S, 2.4 * S, 0.1 * S, 0.45 * S, yaw)  # bench
            out.signs.append(("bus", sx - ux * 1.9 * S, sz - uz * 1.9 * S, yaw_for(rx, rz), "BUS"))
            bus_stops += 1

    # ---- street lamps along the main roads -----------------------------
    for wid, tags, refs, w, top, cls in roads:
        if not ROAD_CLASSES[cls][2]:
            continue
        pts = [nodes[r] for r in refs]
        side = 1
        carry = 12 * S
        for i, (a, b) in enumerate(zip(pts, pts[1:])):
            L = math.dist(a, b)
            if L < 0.01:
                continue
            ux, uz = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            rx, rz = -uz, ux
            d = carry
            while d < L:
                near_junction = (d < clearance(refs[i]) + 2 * S) or (L - d < clearance(refs[i + 1]) + 2 * S)
                off = side * (w / 2 + 0.9 * S)
                p = (a[0] + ux * d + rx * off, a[1] + uz * d + rz * off)
                if not near_junction and not in_building(p, 0.5 * S) and not on_road(p, 0.2 * S):
                    out.lamps.extend([p[0], p[1], -rx * side, -rz * side])
                side = -side
                d += 35 * S
            carry = d - L

    # ---- street name signs ---------------------------------------------
    placed_names = []
    for wid, tags, refs, w, top, cls in roads:
        name = tags.get("name")
        if not name or cls not in CAR_ROADS:
            continue
        pts = [nodes[r] for r in refs]
        total = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
        if total < 50 * S:
            continue
        # one sign per road, and not right next to another sign for the same street
        target, run = total * 0.3, 0.0
        for a, b in zip(pts, pts[1:]):
            L = math.dist(a, b)
            if run + L >= target and L > 0.01:
                t = (target - run) / L
                ux, uz = (b[0] - a[0]) / L, (b[1] - a[1]) / L
                rx, rz = -uz, ux
                p = (a[0] + (b[0] - a[0]) * t + rx * (w / 2 + 1.2 * S), a[1] + (b[1] - a[1]) * t + rz * (w / 2 + 1.2 * S))
                if not in_building(p) and not on_road(p) and all(n != name or math.dist(p, q) > 150 * S for n, q in placed_names):
                    out.signs.append(("street", p[0], p[1], yaw_for(ux, uz), name))
                    placed_names.append((name, p))
                break
            run += L

    # ---- name labels for real places -------------------------------------
    label_keys = ("amenity", "shop", "leisure", "tourism", "office", "craft", "healthcare")
    for ref, tags in node_tags.items():
        name = tags.get("name")
        if not name:
            continue
        x, z = nodes[ref]
        if tags.get("place") in ("quarter", "village", "suburb", "hamlet", "neighbourhood"):
            out.labels.append((x, 60 * S, z, name, 1))
        elif any(k in tags for k in label_keys):
            out.labels.append((x, 6 * S, z, name, 0))
    for wid, (tags, refs) in ways.items():
        name = tags.get("name")
        if not name or "highway" in tags or len(refs) < 3:
            continue
        if "building" in tags or any(k in tags for k in label_keys):
            ring = [nodes[r] for r in refs]
            cx = sum(p[0] for p in ring) / len(ring)
            cz = sum(p[1] for p in ring) / len(ring)
            out.labels.append((cx, 18 * S, cz, name, 0))

    # ---- spawn: the widest paved road point nearest the middle -------------
    best = None
    for wid, tags, refs, w, top, cls in roads:
        if cls not in ("secondary", "tertiary", "trunk", "primary"):
            continue
        for i in range(len(refs) - 1):
            a, b = nodes[refs[i]], nodes[refs[i + 1]]
            if math.dist(a, b) < 20 * S:
                continue
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            score = math.hypot(*mid)
            if best is None or score < best[0]:
                best = (score, mid, yaw_for(b[0] - a[0], b[1] - a[1]), a, b, w)
    _, spawn, spawn_yaw, sa, sb, sw = best
    L = math.dist(sa, sb)
    rx, rz = -(sb[1] - sa[1]) / L, (sb[0] - sa[0]) / L
    credit = (spawn[0] + rx * (sw / 2 + 1.5 * S), spawn[1] + rz * (sw / 2 + 1.5 * S))
    out.signs.append(("credit", credit[0], credit[1], spawn_yaw, "Map data (c) OpenStreetMap contributors"))

    summary = (f"{len(roads)} roads, {rect_count + poly_count} buildings ({pitched_count} with pitched roofs), {crossings} crossings, {stops} stop signs, "
               f"{signals} traffic lights, {bus_stops} bus stops, {tree_count} trees, {len(out.lamps) // 4} street lamps, "
               f"{len(placed_names)} street signs, {len(out.labels)} place names")

    # ---- write -------------------------------------------------------------
    def lua_str(s):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'

    def numstr(vals, per_line, precise=()):
        items = []
        for i in range(0, len(vals), per_line):
            row = vals[i:i + per_line]
            items.append(" ".join(
                (rd(v, 3) if j in precise else rd(v)) if isinstance(v, float) else str(v)
                for j, v in enumerate(row)))
        return "\n".join(items)

    style_rows = ",\n\t\t".join(
        "{ " + ", ".join([lua_str(s[0]), str(s[1][0]), str(s[1][1]), str(s[1][2]), lua_str(s[2]), str(s[3]), rd(s[4]), rd(s[5]), str(s[6]), lua_str(s[7]), str(s[8]),
                          "1" if s[0] in ("Building", "Brick") else "0"]) + " }"
        for s in STYLES
    )
    signs = ",\n\t\t".join("{ " + ", ".join([lua_str(k), rd(x), rd(z), rd(y), lua_str(t)]) + " }" for k, x, z, y, t in out.signs)
    labels = ",\n\t\t".join("{ " + ", ".join([rd(x), rd(y), rd(z), lua_str(t), str(big)]) + " }" for x, y, z, t, big in out.labels)

    header = f'''--[[
	BabrruMap - ONE Script in ServerScriptService. Builds Babrru (Kamëz,
	Albania) from real OpenStreetMap data: every road with its real name
	and surface, every building's real outline, zebra crossings, stop
	signs, traffic lights, bus stops, the Tirana river, woods, street
	lamps, and name labels for real shops, schools and the church.

	Generated by tools/osm_to_babrru.py - don't hand-edit the MAP data;
	re-run the converter on a fresh OpenStreetMap export instead.
	Scale: {SCALE} studs = 1 real meter. Everything is rebuilt on each
	Play and disappears on Stop - that's normal.

	Contains: {summary}.

	Map data (c) OpenStreetMap contributors, available under the Open
	Database License (ODbL) - the game shows this credit on a sign by the
	spawn point.
]]

local MAP = {{
	scale = {SCALE},
	summary = {lua_str(summary)},
	bounds = {{ {rd(min_x)}, {rd(max_x)}, {rd(min_z)}, {rd(max_z)} }},
	spawn = {{ {rd(spawn[0])}, {rd(spawn[1])}, {rd(spawn_yaw)} }},
	-- name, r, g, b, material, collide, transparency, reflectance, shadow, folder, lit at night, is a building
	styles = {{
		{style_rows},
	}},
	signs = {{
		{signs},
	}},
	labels = {{
		{labels},
	}},
	boxes = [[
{numstr(out.boxes, 8)}
]],
	roofs = [[
{numstr(out.roofs, 8)}
]],
	-- Car-road centerlines for the minimap / street names:
	-- x1 z1 x2 z2 width streetIndex (0 = unnamed), and the street names.
	roadlines = [[
{numstr([round(v) for v in road_lines], 6)}
]],
	streets = {{ {", ".join(lua_str(n) for n in street_names)} }},
	wedges = [[
{numstr(out.wedges, 13, precise=(4, 5, 6, 7, 8, 9))}
]],
	balls = [[
{numstr(out.balls, 5)}
]],
	lamps = [[
{numstr(out.lamps, 4)}
]],
}}
'''
    builder = (TOOLS_DIR / "babrru_builder.lua").read_text(encoding="utf-8")
    source = header + builder
    Path(out_path).write_text(source, encoding="utf-8")
    # The same script as a Roblox model file: right-click ServerScriptService
    # -> Insert from File, no huge copy/paste needed.
    assert "]]>" not in source
    rbxmx = (
        '<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" version="4">\n'
        '\t<Item class="Script" referent="RBXBABRRU0">\n'
        '\t\t<Properties>\n'
        '\t\t\t<string name="Name">BabrruMap</string>\n'
        '\t\t\t<bool name="Disabled">false</bool>\n'
        f'\t\t\t<ProtectedString name="Source"><![CDATA[{source}]]></ProtectedString>\n'
        '\t\t</Properties>\n'
        '\t</Item>\n'
        '</roblox>\n'
    )
    Path(out_path).with_suffix("").with_suffix(".rbxmx").write_text(rbxmx, encoding="utf-8")
    parts = len(out.roofs) // 8 + len(out.boxes) // 8 + len(out.wedges) // 13 + 2 * len(out.balls) // 5 + 3 * len(out.lamps) // 4 + 2 * len(out.signs) + len(out.labels) + 2 * rect_count
    print(summary)
    print(f"markings: {marking_count}; parts ~{parts}; wedges {len(out.wedges) // 13}; file {Path(out_path).stat().st_size / 1024:.0f} KB")
    return out


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
