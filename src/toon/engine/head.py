"""Sphere-projected chibi head: face features and hair.

Ported from RIG (rig_r4.py) 535-1009 (lift, the hair-cap functions, ell, draw_head,
_head_effects, fringe_z, _draw_bun, draw_hair, draw_hair_layer). The module-level FACE/HAIR/BODY
globals are gone: `draw_head(pen, cam, rg, pose, t, look)` builds its face dict from
`look.face` merged over `FACE_DEFAULT`, and threads `hair = look.hair` through to the hair
helpers instead of reading a global. `_h` is `hsign` here (toon.engine.mathx).
"""
from __future__ import annotations

import math

import numpy as np

from toon.engine.look import FACE_DEFAULT, HAIR_DEFAULT
from toon.engine.mathx import UP, V, circle_pts, hsign, smooth, unit
from toon.engine.palette import BLUSH, BUZZ
from toon.engine.rig import HEAD_R


def lift(x, y, s=1.0):
    return V(x, y, math.sqrt(max(1 - x * x - y * y, 0.0))) * s


def hair_cap(line, bumps=()):
    """Hairline (forehead y, temple y, nape y) + bumps -> (cap axis, cos half-angle, side lift k, bumps).
    A bump (amp, x, y, sigma) at the front-sphere point (x, y) adds hair (amp > 0) or removes it."""
    fy, sy, by = line
    front, back = 180 - math.degrees(math.asin(fy)), math.degrees(math.asin(by))
    phi, alpha = (front + back) / 2, (front - back) / 2
    h = V(0, math.sin(math.radians(phi)), -math.cos(math.radians(phi)))
    ca = math.cos(math.radians(alpha))
    k = (sy * math.sin(math.radians(phi)) - ca) / (1 - sy * sy)
    bl = tuple((a, tuple(lift(x, y) if x * x + y * y < 1 else unit(V(x, y, 0.0))), sg) for a, x, y, sg in bumps)
    return h, ca, k, bl


def hair_f(n, cap):  # >= 0 inside the hair
    h, ca, k, bl = cap
    f = n @ h - ca - k * n[..., 0] ** 2
    for a, c, sg in bl:
        f = f + a * np.exp(-np.sum((n - np.array(c)) ** 2, axis=-1) / (sg * sg))
    return f


_HAIRLINE: dict = {}


def hairline_local(cap, n=180):
    """Hairline points in head-local coords; index 0 = nape, n/2 = forehead centre."""
    key = repr((np.round(cap[0], 6).tolist(), round(cap[1], 6), round(cap[2], 6), cap[3]))
    if key not in _HAIRLINE:
        h = cap[0]
        e1 = unit(np.cross(h, V(1, 0, 0)))
        e2 = np.cross(h, e1)
        psi = np.linspace(0, 2 * math.pi, n, endpoint=False)
        d = np.cos(psi)[:, None] * e1 + np.sin(psi)[:, None] * e2
        lo, hi = np.zeros(n), np.full(n, math.pi)
        for _ in range(28):
            g = (lo + hi) / 2
            inside = hair_f(np.cos(g)[:, None] * h + np.sin(g)[:, None] * d, cap) >= 0
            lo, hi = np.where(inside, g, lo), np.where(inside, hi, g)
        g = (lo + hi) / 2
        _HAIRLINE[key] = np.cos(g)[:, None] * h + np.sin(g)[:, None] * d
    return _HAIRLINE[key]


def ell(cx, cy, rx, ry, n=18, s=1.0):
    return [lift(cx + rx * math.cos(a), cy + ry * math.sin(a), s) for a in np.linspace(0, 2 * math.pi, n, endpoint=False)]


def draw_head(pen, cam, rg, pose, t, look):
    F = {**FACE_DEFAULT, **look.face}
    hair = look.hair
    C, Rh = rg["head"], rg["Rh"]
    c2 = cam.p(C)
    r2 = HEAD_R * cam.scale(C)
    tow = cam.toward(C)

    def scr(w):
        d = cam.sdir(w)
        return (c2[0] + r2 * d[0], c2[1] + r2 * d[1])

    def runs(local_pts, thresh=0.08):
        out, cur = [], []
        for lp in local_pts:
            w = Rh @ lp
            if np.dot(unit(w), tow) > thresh:
                cur.append(scr(w))
            elif cur:
                out.append(cur)
                cur = []
        if cur:
            out.append(cur)
        return out

    def visible(lp, thresh=0.12):
        return np.dot(unit(Rh @ lp), tow) > thresh

    def blob(local_pts, color=None):
        if visible(sum(local_pts) / len(local_pts)):
            pen.solid([scr(Rh @ p) for p in local_pts], color)

    ex0, ey, es = F["eye_x"], F["eye_y"], F["eye_s"]
    gr = F["glasses_r"]
    # ears: flat cut-out circles, behind the skull unless they face us
    ears_front = []
    if F["ear"]:
        for side in (1, -1):
            ew = Rh @ unit(V(side, F["ear_y"] if F["ear_y"] is not None else ey - 0.02, -0.08))
            pts = circle_pts(scr(ew), F["ear_r"] * r2, 18, rx=F["ear_r"] * r2 * 0.8)
            facing = float(np.dot(ew, tow))
            if facing > 0.3:
                ears_front.append((pts, side))
            elif facing > -0.6:
                pen.fill(pts, F["skin"] or "skin", f"ear{side}")
                pen.stroke(pts, f"ear{side}", closed=True, wk=0.6)
    # skull
    skull = circle_pts(c2, r2, 64)
    if F["jaw"]:
        roll = math.atan2(*cam.sdir(Rh @ UP)[::-1])
        skull = []
        for a in np.linspace(0, 2 * math.pi, 72, endpoint=False):
            dn = abs(math.degrees(math.atan2(math.sin(a - roll), math.cos(a - roll))))  # 0 = up, 180 = chin
            rr = r2 * (1 + F["jaw"] * math.exp(-((dn - 128) / 38) ** 2))
            skull.append((c2[0] + rr * math.cos(a), c2[1] + rr * math.sin(a)))
    if F["mane"]:  # spiky mane ring behind the skull
        roll_m = math.atan2(*cam.sdir(Rh @ UP)[::-1])
        mane = []
        for a in np.linspace(0, 2 * math.pi, 96, endpoint=False):
            ph = ((a - roll_m) / math.radians(F["mane"].get("deg", 24))) % 1.0
            rr = r2 * (F["mane"].get("r", 1.3) + F["mane"].get("spike", 0.22) * (1 - abs(2 * ph - 1)))
            mane.append((c2[0] + rr * math.cos(a), c2[1] + rr * math.sin(a)))
        pen.fill(mane, F["mane"]["color"], "mane")
        pen.stroke(mane, "mane", closed=True, wk=0.9)
    if F["animal_ears"]:  # round ears on top, half hidden by the skull
        roll_e = math.atan2(*cam.sdir(Rh @ UP)[::-1])
        for sd in (1, -1):
            a = roll_e + sd * math.radians(42)
            ec = (c2[0] + r2 * 1.02 * math.cos(a), c2[1] + r2 * 1.02 * math.sin(a))
            outer = circle_pts(ec, 0.3 * r2, 18)
            pen.fill(outer, F["animal_ears"]["color"], f"aear{sd}")
            pen.stroke(outer, f"aear{sd}", closed=True, wk=0.8)
            pen.solid(circle_pts(ec, 0.15 * r2, 14), F["animal_ears"]["inner"])
    bun = hair.get("bun")
    bun_behind = bool(bun) and np.dot(unit(Rh @ V(*bun[:3])), tow) < 0.25
    if bun_behind:
        _draw_bun(pen, cam, c2, r2, Rh, hair)
    pen.fill(skull, F["skin"] or "skin", "head")
    pen.stroke(skull, "head", closed=True, wk=1.1)
    for pts, side in ears_front:
        pen.fill(pts, F["skin"] or "skin", f"ear{side}")
        pen.stroke(pts, f"ear{side}", closed=True, wk=0.55)
    # lenses filled (glare) go under the face features
    if F["glasses_fill"] == "glare":
        for side in (1, -1):
            lens = ell(ex0 * side, ey, gr, gr, 24, 1.02)
            if visible(lift(ex0 * side, ey)):
                pts = [scr(Rh @ p) for p in lens]
                pen.solid(pts, (0.86, 0.90, 0.94))
                for i, (a, b) in enumerate((((-0.1, -0.02), (0.02, 0.12)), ((-0.02, -0.1), (0.1, 0.03)))):
                    st = [lift(ex0 * side + a[0] * gr / 0.19, ey + a[1] * gr / 0.19, 1.02),
                          lift(ex0 * side + b[0] * gr / 0.19, ey + b[1] * gr / 0.19, 1.02)]
                    pen.stroke([scr(Rh @ p) for p in st], f"glare{side}{i}", wk=0.35, color=(1, 1, 1), amp_k=0.3)
    # eyes
    mode = {"dot": F["eye"], "wide": "wide", "closed": "arc"}.get(pose.eyes, F["eye"])
    for side in (1, -1):
        ex = ex0 * side
        if mode == "dot":
            blob(ell(ex, ey, 0.045 * es, 0.05 * es))
        elif mode == "oval":
            blob(ell(ex, ey, 0.075 * es, 0.105 * es))
        elif mode == "oval_hi":
            blob(ell(ex, ey, 0.085 * es, 0.12 * es))
            blob(ell(ex + 0.028 * es, ey + 0.04 * es, 0.028 * es, 0.028 * es, 10), (1, 1, 1))
        elif mode == "big_hi":
            blob(ell(ex, ey, 0.11 * es, 0.145 * es, 22))
            blob(ell(ex + 0.035 * es, ey + 0.05 * es, 0.04 * es, 0.04 * es, 10), (1, 1, 1))
            blob(ell(ex - 0.03 * es, ey - 0.055 * es, 0.017 * es, 0.017 * es, 8), (1, 1, 1))
        elif mode == "bean":
            blob(ell(ex, ey, 0.1 * es, 0.058 * es))
        elif mode == "almond":  # small, narrow: flatter top, rounder bottom
            pts = [lift(ex + 0.075 * es * math.cos(a), ey + (0.028 if math.sin(a) > 0 else 0.05) * es * math.sin(a))
                   for a in np.linspace(0, 2 * math.pi, 20, endpoint=False)]
            blob(pts)
        elif mode == "ring" or mode == "wide":
            rr = 0.085 * es if mode == "ring" else 0.13
            if visible(lift(ex, ey)):
                ring = [scr(Rh @ p) for p in ell(ex, ey, rr, rr, 22)]
                pen.fill(ring, "white", f"eyew{side}")
                pen.stroke(ring, f"eyew{side}", closed=True, wk=0.42)
            blob(ell(ex - 0.012 * side, ey - 0.012, 0.04, 0.04, 10))
        elif mode == "half":  # sleepy: lower half of an oval under a lid line
            if visible(lift(ex, ey)):
                lower = [lift(ex + 0.085 * es * math.cos(a), ey - 0.01 + 0.085 * es * math.sin(a))
                         for a in np.linspace(math.pi, 2 * math.pi, 10)]
                pen.solid([scr(Rh @ p) for p in lower])
                lid = [lift(ex + dx, ey - 0.005) for dx in np.linspace(-0.11 * es, 0.11 * es, 5)]
                pen.stroke([scr(Rh @ p) for p in lid], f"lid{side}", wk=0.5)
        elif mode == "arc":
            arc = [lift(ex + 0.09 * es * math.cos(a), ey - 0.03 + 0.07 * es * math.sin(a)) for a in np.linspace(0.15, math.pi - 0.15, 10)]
            for r_ in runs(arc):
                pen.stroke(r_, f"eyec{side}", wk=0.55)
        if F["lid"] and mode in ("almond", "dot", "bean", "oval"):
            lid = [lift(ex + dx, ey + 0.06 * es + 0.012 * (1 - (dx / 0.1) ** 2)) for dx in np.linspace(-0.09, 0.1, 6)]
            for r_ in runs(lid):
                pen.stroke(r_, f"lidl{side}", wk=0.3)
        if F["bags"]:
            bag = [lift(ex + 0.07 * math.cos(a), ey - 0.1 + 0.03 * math.sin(a)) for a in np.linspace(-2.6, -0.5, 6)]
            for r_ in runs(bag):
                pen.stroke(r_, f"bag{side}", wk=0.28, color=(0.55, 0.52, 0.5))
        # brows
        style = F["brow"]
        if style != "none":
            by = ey + F["brow_dy"] + 0.09 * pose.brow + (0.08 if style == "high" else 0)
            tilt = 0.05 * pose.worried
            half = F["brow_half"] or {"arc": 0.1, "short": 0.06, "thick": 0.1, "high": 0.1, "straight": 0.12}[style]
            arch = {"arc": 0.02, "short": 0.0, "thick": 0.015, "high": 0.03, "straight": 0.004}[style]
            wk = F["brow_wk"] or {"arc": 0.5, "short": 0.8, "thick": 0.95, "high": 0.4, "straight": 0.6}[style]
            brow = [lift(ex + dx, by + (tilt if dx * side < 0 else -tilt * 0.3) + arch * (1 - (dx / half) ** 2)
                         + F["brow_tilt"] * dx * side)
                    for dx in np.linspace(-half, half, 6)]
            for r_ in runs(brow):
                pen.stroke(r_, f"brow{side}", wk=wk)
        # blush
        if F["blush"] == "strokes":
            for i in range(3):
                bx = 0.5 * side + (i - 1) * 0.06
                st = [lift(bx - 0.025, F["blush_y"] - 0.04), lift(bx + 0.025, F["blush_y"] + 0.04)]
                if visible(st[0], 0.2):
                    pen.stroke([scr(Rh @ p) for p in st], f"blush{side}{i}", wk=0.32, color=BLUSH, amp_k=0.4)
        elif F["blush"] == "oval":
            pts = ell(0.52 * side, F["blush_y"], 0.1, 0.055, 16)
            if visible(lift(0.52 * side, F["blush_y"]), 0.2):
                pen.c.set_source_rgba(*BLUSH, 0.45)
                pen.poly([scr(Rh @ p) for p in pts])
                pen.c.fill()
    if F["lashes"] and mode in ("oval", "oval_hi", "dot", "big_hi"):
        for side in (1, -1):
            ex = ex0 * side
            for i, dx in enumerate((0.05, 0.085)):
                st = [lift(ex + dx * side, ey + 0.09 * es), lift(ex + (dx + 0.04) * side, ey + 0.14 * es)]
                if visible(st[0]):
                    pen.stroke([scr(Rh @ p) for p in st], f"lash{side}{i}", wk=0.35)
    if F["muzzle"]:  # animal muzzle: cream patch, nose, whiskers
        mz = ell(0.0, -0.3, 0.3, 0.2, 22)
        if visible(lift(0, -0.3)):
            pts = [scr(Rh @ p) for p in mz]
            pen.fill(pts, (0.97, 0.93, 0.84), "muzzle")
            pen.stroke(pts, "muzzle", closed=True, wk=0.5)
            blob([lift(-0.08, -0.13), lift(0.08, -0.13), lift(0.0, -0.23)], (0.35, 0.22, 0.2))
            for sd in (1, -1):
                for i, dy in enumerate((-0.02, -0.08)):
                    a, b = scr(Rh @ lift(0.2 * sd, -0.28 + dy)), scr(Rh @ lift(0.34 * sd, -0.27 + dy * 1.4))
                    d = (b[0] - a[0], b[1] - a[1])
                    pen.stroke([a, (a[0] + d[0] * 2.4, a[1] + d[1] * 2.4)], f"whisk{sd}{i}", wk=0.3)
    # nose
    if F["nose"] == "dot":
        blob(ell(0.0, (ey + F["mouth_y"]) / 2 + 0.02, 0.025, 0.022, 10))
    elif F["nose"] == "button":  # small rounded tip
        ny = (ey + F["mouth_y"]) / 2 - 0.02
        tip = [lift(0.055 * math.cos(a), ny + 0.035 * math.sin(a)) for a in np.linspace(math.pi * 1.05, math.pi * 1.95, 7)]
        for r_ in runs(tip):
            pen.stroke(r_, "nose", wk=0.42)
    elif F["nose"] == "nostrils":
        ny = (ey + F["mouth_y"]) / 2 - 0.03
        for sd in (1, -1):
            blob(ell(0.045 * sd, ny, 0.02, 0.013, 8))
        tip = [lift(0.07 * math.cos(a), ny + 0.03 + 0.03 * math.sin(a)) for a in np.linspace(math.pi * 1.1, math.pi * 1.9, 6)]
        for r_ in runs(tip):
            pen.stroke(r_, "nose", wk=0.35)
    elif F["nose"] == "hook":
        ny = (ey + F["mouth_y"]) / 2
        hook = [lift(0.0, ny + 0.07), lift(0.05, ny - 0.03), lift(0.0, ny - 0.05)]
        for r_ in runs(hook):
            pen.stroke(r_, "nose", wk=0.45)
    # mouth
    m = pose.mouth
    if F.get("smile"):  # face has a separate resting mouth and smile
        style = {"smile": F["smile"], "flat": F["mouth"]}.get(m, m)
    else:
        style = {"smile": F["mouth"], "flat": "line" if F["mouth"] not in ("cat", "smirk") else F["mouth"]}.get(m, m)
    my = F["mouth_y"]
    if style == "o":
        blob(ell(0.0, my - 0.04, 0.075, 0.1, 16))
    elif style in ("grin", "open"):
        wdt = 0.12 if style == "grin" else 0.075
        dep = 0.12 if style == "grin" else 0.07
        mouth = [lift(x, my + 0.02) for x in np.linspace(-wdt, wdt, 6)] + \
                [lift(wdt * math.cos(a), my + 0.02 - dep * math.sin(a)) for a in np.linspace(0.15, math.pi - 0.15, 10)]
        if visible(lift(0, my)):
            pts = [scr(Rh @ p) for p in mouth]
            pen.solid(pts)
            if style == "grin":
                blob(ell(0.0, my - 0.07, 0.055, 0.03, 12), (0.86, 0.45, 0.45))
    else:
        if style == "smile":
            ml = [lift(x, my + 0.03 - 0.08 * (1 - (x / 0.12) ** 2)) for x in np.linspace(-0.12, 0.12, 9)]
        elif style == "wide":
            ml = [lift(x, my + 0.03 - 0.09 * (1 - (x / 0.17) ** 2)) for x in np.linspace(-0.17, 0.17, 11)]
        elif style == "tiny":
            ml = [lift(x, my + 0.02 - 0.04 * (1 - (x / 0.06) ** 2)) for x in np.linspace(-0.06, 0.06, 7)]
        elif style == "cat":
            ml = [lift(x, my - 0.04 * abs(math.sin(math.pi * x / 0.11))) for x in np.linspace(-0.11, 0.11, 13)]
        elif style == "smirk":
            ml = [lift(x, my - 0.02 + 0.05 * max(0.0, x / 0.1) ** 2) for x in np.linspace(-0.08, 0.11, 8)]
        elif style == "wavy":
            ml = [lift(x, my - 0.02 + 0.025 * math.sin(x * 60)) for x in np.linspace(-0.11, 0.11, 11)]
        else:  # line
            ml = [lift(x, my - 0.02) for x in np.linspace(-0.08, 0.08, 5)]
        for r_ in runs(ml):
            pen.stroke(r_, "mouth", wk=0.5)
        if F["lips"] and style == "line":
            lip = [lift(x, my - 0.07 + 0.025 * (x / 0.06) ** 2) for x in np.linspace(-0.06, 0.06, 6)]
            for r_ in runs(lip):
                pen.stroke(r_, "lip", wk=0.3)
    # hair (spiky, pick A)
    draw_hair(pen, cam, C, c2, r2, Rh, tow, pose, t, hair)
    if not F["glasses"]:
        return _head_effects(pen, pose, c2, r2)
    # glasses (pick 1: round), just proud of the sphere
    grx, gry, gwk = F["glasses_rx"] or gr, F["glasses_ry"] or gr, F["glasses_wk"]

    def rim_pt(ex, a):
        sa = math.sin(a)
        y = gry * (abs(sa) ** (1 - F["glasses_flat"]) if sa > 0 else sa)
        return lift(ex + grx * math.cos(a), ey + y, 1.02)

    for side in (1, -1):
        ex = ex0 * side
        rr = runs([rim_pt(ex, a) for a in np.linspace(0, 2 * math.pi, 32, endpoint=False)], 0.02)
        if len(rr) == 1 and len(rr[0]) == 32:
            pen.stroke(rr[0], f"rim{side}", closed=True, wk=gwk)
        else:
            for i, r_ in enumerate(rr):
                pen.stroke(r_, f"rim{side}{i}", wk=gwk)
        if F["temple"] != "none":
            a0 = math.degrees(math.asin(min(ex0 + grx, 0.99)))
            a1 = 92 if F["temple"] == "full" else a0 + 12
            temple = [V(side * math.sin(math.radians(a)), ey + 0.02, math.cos(math.radians(a))) * 1.0
                      for a in np.linspace(a0, a1, 10)]
            for i, r_ in enumerate(runs(temple, 0.03)):
                pen.stroke(r_, f"temple{side}{i}", wk=gwk * 0.85)
    bx = ex0 - grx
    bridge = [lift(x, ey + 0.02 + 0.03 * (1 - (x / bx) ** 2), 1.02) for x in np.linspace(-bx, bx, 6)]
    for r_ in runs(bridge, 0.02):
        pen.stroke(r_, "bridge", wk=gwk * 0.85)
    return _head_effects(pen, pose, c2, r2)


def _head_effects(pen, pose, c2, r2):
    head_px = (c2, r2)
    if pose.sweat > 0.3:
        sx, sy = c2[0] - r2 * 0.95, c2[1] - r2 * 0.35
        k = r2 * 0.12
        drop = [(sx, sy - k * 1.4)] + [(sx + k * math.cos(a), sy + k * math.sin(a)) for a in np.linspace(-0.3, math.pi + 0.3, 10)]
        pen.fill(drop, (0.70, 0.80, 0.88), "sweat")
        pen.stroke(drop, "sweat", closed=True, wk=0.35)
    if pose.shock > 0.3:  # shock lines around the head
        for i, a in enumerate((-150, -125, -100, -80, -55, -30)):
            ra = math.radians(a)
            p0 = (c2[0] + math.cos(ra) * r2 * 1.35, c2[1] + math.sin(ra) * r2 * 1.35)
            p1 = (c2[0] + math.cos(ra) * r2 * 1.6, c2[1] + math.sin(ra) * r2 * 1.6)
            pen.stroke([p0, p1], f"shock{i}", wk=0.55)
    return head_px


def fringe_z(style, idx, n=180):
    """Fringe tooth length (head radii) at hairline sample idx (n/2 = forehead centre)."""
    if style == "saw":
        ph = (idx % 8) / 8.0
        return 0.1 * (1 - abs(2 * ph - 1))
    if style == "clumps":  # irregular clumps, bigger at the front
        edges = [0, 11, 24, 33, 47, 58, 70, 81, 95, 104, 117, 128, 141, 152, 166, 180]
        k = next(i for i in range(len(edges) - 1) if edges[i] <= idx < edges[i + 1])
        ph = (idx - edges[k]) / (edges[k + 1] - edges[k])
        front = 1.0 - min(abs(idx - n / 2) / (n / 2), 1.0)
        return (0.06 + 0.1 * front) * (0.7 + 0.5 * abs(hsign(k * 7 + 3))) * (1 - abs(2 * ph - 1)) ** 0.8
    if style == "swoop":  # teeth lean one way, lengthening into a lock on one side
        ph = (idx % 13) / 13.0
        side = min(max((idx - n * 0.3) / (n * 0.45), 0.0), 1.0)
        return (0.05 + 0.13 * side) * (ph ** 1.5)
    if style == "straight":  # nearly straight, two small notches
        notch = max(0.0, 1 - abs(idx - 82) / 4) + max(0.0, 1 - abs(idx - 101) / 4)
        return 0.02 + 0.07 * notch
    return 0.0


def _draw_bun(pen, cam, c2, r2, Rh, hair):
    bun = hair["bun"]  # (x, y, z, radius) in head-local units
    bw = Rh @ V(*bun[:3])
    bpts = circle_pts((c2[0] + r2 * cam.sdir(bw)[0], c2[1] + r2 * cam.sdir(bw)[1]), bun[3] * r2, 20)
    col = (hair.get("layers") or [hair])[-1].get("fill", "ink")
    pen.fill(bpts, col, "bun")
    pen.stroke(bpts, "bun", closed=True, wk=0.85)


def draw_hair(pen, cam, C, c2, r2, Rh, tow, pose, t, hair):
    if hair.get("none"):
        return
    for i, layer in enumerate(hair.get("layers") or [hair]):
        draw_hair_layer(pen, cam, C, c2, r2, Rh, tow, pose, t, {**HAIR_DEFAULT, **layer}, f"hair{i}")
    bun = hair.get("bun")
    if bun and np.dot(unit(Rh @ V(*bun[:3])), tow) >= 0.25:
        _draw_bun(pen, cam, c2, r2, Rh, hair)


def draw_hair_layer(pen, cam, C, c2, r2, Rh, tow, pose, t, Hs, key):
    cap = hair_cap(Hs["line"], Hs["bumps"])
    line = hairline_local(cap)
    b_w = [Rh @ b for b in line]
    vis = [np.dot(w, tow) > 0 for w in b_w]
    h_w = Rh @ cap[0]

    def scr(w):
        d = cam.sdir(w)
        return (c2[0] + r2 * d[0], c2[1] + r2 * d[1])

    def in_cap_screen(phi):
        w = math.cos(phi) * cam.r - math.sin(phi) * cam.u
        return hair_f(Rh.T @ w, cap) >= 0

    spike = Hs["spike_len"] + 0.12 * pose.hair
    period = math.radians(Hs["spike_deg"])
    lean = Hs["spike_lean"]
    roll = math.atan2(*cam.sdir(Rh @ UP)[::-1])  # screen angle of the head's up vector

    def sil_arc(pa, pb):
        # choose the direction from pa to pb that runs through the cap
        d = (pb - pa) % (2 * math.pi)
        mids = ((pa + d / 2, d), (pa - (2 * math.pi - d) / 2, -(2 * math.pi - d)))
        span = next((sp for m, sp in mids if in_cap_screen(m)), mids[0][1])
        n = max(8, int(abs(span) / math.radians(1.5)))
        pts = []
        for i in range(n + 1):
            phi = pa + span * i / n
            u = (phi - roll) / period
            k = math.floor(u)
            ph = u - k
            tri = ph / lean if ph < lean else (1 - ph) / (1 - lean)
            amp = 1 + Hs["spike_irr"] * hsign(k * 31 + 5)
            if Hs["top_only"]:
                amp *= smooth((math.cos(phi - roll) - 0.35) / 0.5)
            edge = smooth(min(i, n - i) / (n * 0.12 + 1e-6))
            rr = r2 * (1.0 + spike * amp * tri * edge)
            pts.append((c2[0] + rr * math.cos(phi), c2[1] + rr * math.sin(phi)))
        return pts

    if all(vis) or not any(vis):
        if np.dot(h_w, tow) > 0 or all(vis):
            region = circle_pts(c2, r2 * 1.02, 64) if not all(vis) else [scr(w) for w in b_w]
        else:
            return
    else:
        n = len(vis)
        start = next(i for i in range(n) if not vis[i - 1] and vis[i])
        run = []
        i = start
        while vis[i % n] and len(run) < n:
            run.append(i % n)
            i += 1
        arc = []
        for j, idx in enumerate(run):  # fringe teeth point toward the face
            w = b_w[idx]
            p = scr(w)
            q = scr(unit(w - 0.25 * h_w))
            dx, dy = q[0] - p[0], q[1] - p[1]
            dl = math.hypot(dx, dy) or 1
            z = r2 * Hs["fringe_k"] * fringe_z(Hs["fringe"], idx, n) * smooth(min(j, len(run) - 1 - j) / 5)
            arc.append((p[0] + dx / dl * z, p[1] + dy / dl * z))
        pa = math.atan2(arc[-1][1] - c2[1], arc[-1][0] - c2[0])
        pb = math.atan2(arc[0][1] - c2[1], arc[0][0] - c2[0])
        region = arc + sil_arc(pa, pb)
    fill = {"ink": "ink", "buzz": BUZZ}.get(Hs["fill"], Hs["fill"]) if isinstance(Hs["fill"], str) else Hs["fill"]
    pen.fill(region, fill, key)
    pen.stroke(region, key, closed=True, wk=Hs["wk"])
