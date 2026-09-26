"""Props: the idea bulb, plates, laptop, mug, and the desk/set-anchor constants.

Ported from RIG (rig_r4.py) 411-422 (the desk/set constants), 1087-1107 (BOX_FACES, draw_box),
1130-1145 + 1156-1180 (draw_laptop -> laptop; screen_icons now takes the wordless screen state
as an explicit `state` parameter instead of reading it off the tryout's global `laptop_state(t)`
function), 1222-1242 (draw_mug -> mug, dropping the tryout's dead `tilt = cam.sdir(UP)` local).
Also ports SCN (scene_lioness.py) 133-191 (smoke_wisp, bulb -> idea_bulb) and 436-449 (plate,
plate_stack -- generalised to take an explicit `key` prefix instead of a hardcoded "stack").

`draw_box`, `laptop`, `mug`, `plate`, `plate_stack`, `smoke_wisp` and `idea_bulb` all draw in
camera/world space (`cam.p`/`cam.scale`), so none of their literal numbers are pixel sizes --
per the task ruling, those are left alone.
"""
from __future__ import annotations

import math

import numpy as np

from toon.engine.mathx import UP, V, circle_pts, hull, lerp, rotX
from toon.engine.palette import BLUE, BULB_OFF, BULB_ON, GREEN, RED, SMOKE
from toon.kit.graphics import glow

# ---- desk/set constants (RIG 411-422; world units, head radius = 1) ----
DESK_Y, DESK_Z0, DESK_Z1, DESK_X = 2.1, 0.75, 2.2, 2.2
LAP_BASE = (V(0, DESK_Y + 0.035, 1.33), V(0.46, 0.035, 0.38))
HINGE = V(0, DESK_Y + 0.07, 1.72)
LID_TILT = 16.0
MUG_AT = V(1.35, DESK_Y, 1.0)
LAMP_AT = V(3.4, 0, 3.4)


# ---- boxes (RIG 1087-1107) ----
BOX_FACES = ((0, 1, 3, 2, V(-1, 0, 0)), (4, 6, 7, 5, V(1, 0, 0)), (0, 4, 5, 1, V(0, -1, 0)),
             (2, 3, 7, 6, V(0, 1, 0)), (0, 2, 6, 4, V(0, 0, -1)), (1, 5, 7, 3, V(0, 0, 1)))


def draw_box(pen, cam, center, half, M, role, key, wk=1.0):
    corners = [center + M @ V(half[0] * (1 if i & 4 else -1), half[1] * (1 if i & 2 else -1), half[2] * (1 if i & 1 else -1))
               for i in range(8)]
    p2 = [cam.p(c) for c in corners]
    count = {}
    for a, b, c, d, nrm in BOX_FACES:
        fc = (corners[a] + corners[c] + corners[b] + corners[d]) / 4
        if np.dot(M @ nrm, cam.pos - fc) > 0:
            for e in ((a, b), (b, c), (c, d), (d, a)):
                k = tuple(sorted(e))
                count[k] = count.get(k, 0) + 1
    pen.fill(hull(p2), role, key)
    for (a, b), n in sorted(count.items()):
        pen.stroke([p2[a], p2[b]], f"{key}/{a}{b}", wk=wk * (1.0 if n == 1 else 0.55))
    return corners


# ---- laptop (RIG 1130-1145, 1156-1180) ----
def laptop(pen, cam, t, screen="working"):
    c0, half = LAP_BASE
    draw_box(pen, cam, c0, tuple(half), np.eye(3), "metal", "lapbase", wk=0.8)
    M = rotX(LID_TILT)
    lid_c = HINGE + M @ V(0, 0.52, 0)
    draw_box(pen, cam, lid_c, (0.46, 0.52, 0.025), M, "metal", "lid", wk=0.8)
    n = M @ V(0, 0, -1)
    if np.dot(n, cam.pos - lid_c) <= 0:
        return

    def sp(x, y):
        return cam.p(lid_c + M @ V(-x * 0.4, y * 0.44, -0.03))

    quad = [sp(-1, -1), sp(1, -1), sp(1, 1), sp(-1, 1)]
    pen.fill(quad, "screen", "screen")
    screen_icons(pen, sp, t, screen)


def screen_icons(pen, sp, t, state):
    """Wordless screen: rows of grey 'text' bars, green checks as work completes, a progress bar."""

    def P(X, Y):
        return sp(X - 1, 1 - Y)

    rows = ((1.1, True), (0.8, True), (1.25, True), (0.9, False))
    shown = rows[:1 + int(t * 1.6) % 4] if state == "working" else rows
    for i, (ln, done) in enumerate(shown):
        y = 0.4 + i * 0.3
        pen.stroke([P(0.42, y), P(0.42 + ln, y)], f"sbar{i}", wk=0.9, color=(0.72, 0.72, 0.7), amp_k=0.3)
        if done or state == "ok":
            pen.stroke([P(0.14, y), P(0.2, y + 0.06), P(0.3, y - 0.08)], f"scheck{i}", wk=0.45, color=GREEN)
        elif state == "error":
            pen.stroke([P(0.15, y - 0.06), P(0.28, y + 0.05)], f"sx{i}a", wk=0.45, color=RED)
            pen.stroke([P(0.28, y - 0.06), P(0.15, y + 0.05)], f"sx{i}b", wk=0.45, color=RED)
    prog = min(1.0, 0.25 + t * 0.2) if state == "working" else 1.0
    pen.stroke([P(0.14, 1.72), P(1.86, 1.72)], "sprog0", wk=0.9, color=(0.85, 0.85, 0.83), amp_k=0.2)
    pen.stroke([P(0.14, 1.72), P(0.14 + 1.72 * prog, 1.72)], "sprog1", wk=0.9,
               color=RED if state == "error" else GREEN, amp_k=0.2)


# ---- mug (RIG 1222-1242) ----
def mug(pen, cam):
    s = cam.scale(MUG_AT)
    b = cam.p(MUG_AT)
    w, h = 0.15 * s, 0.34 * s
    top_ry = 0.04 * s + 0.05 * s * abs(np.dot(cam.f, UP)) * 2
    hd = cam.sdir(V(1, 0, 0))
    behind = np.dot(V(1, 0, 0), cam.toward(MUG_AT)) < 0
    handle = [(b[0] + hd[0] * w * 0.95, b[1] - h * 0.75), (b[0] + hd[0] * w * 1.7, b[1] - h * 0.62),
              (b[0] + hd[0] * w * 1.6, b[1] - h * 0.3), (b[0] + hd[0] * w * 0.95, b[1] - h * 0.25)]
    if behind:
        pen.stroke(handle, "mughandle", wk=0.7)
    body = [(b[0] - w, b[1] - h), (b[0] - w, b[1]), (b[0] + w, b[1]), (b[0] + w, b[1] - h)]
    pen.fill(body + circle_pts((b[0], b[1] - h), w, 12, rx=w, ry=top_ry)[6:], "mug", "mug")
    pen.edges(body, "mug", closed=False)
    pen.stroke(circle_pts((b[0], b[1] - h), 0, 20, rx=w, ry=top_ry), "mugtop", closed=True, wk=0.7)
    if not behind:
        pen.stroke(handle, "mughandle", wk=0.7)


# ---- the idea bulb + its smoke (SCN 133-191) ----
def smoke_wisp(pen, base, s, age, key):
    """A snuffed-out wisp: thin curls rising and thinning out (age in seconds since it went out)."""
    fade = max(0.0, 1 - age / 2.4)
    if fade <= 0:
        return
    for j, (ph, dx) in enumerate(((0.0, 0.0), (2.3, 0.12), (4.1, -0.1))):
        L = min(1.7, 0.35 + age * 1.1) * s * (1 - 0.18 * j)
        pts = []
        for i in range(14):
            v = i / 13
            x = base[0] + dx * s + math.sin(v * 5.5 + ph + age * 2.2) * 0.13 * s * (0.3 + v)
            pts.append((x, base[1] - v * L))
        pen.stroke(pts, f"{key}{j}", wk=0.55 - 0.1 * j, color=SMOKE, alpha=0.85 * fade, amp_k=0.5)


def idea_bulb(pen, cam, anchor, b, mode="on", smoke_age=0.0, key="bulb"):
    """The idea as a light bulb. b = brightness 0..1; mode on | flicker | out."""
    s, c = cam.scale(anchor), cam.p(anchor)
    r = 0.36 * s
    glow(pen.c, c, r * 2.6, (0.99, 0.88, 0.45), 0.55 * b)
    col = tuple(lerp(a, bb, b) for a, bb in zip(BULB_OFF, BULB_ON, strict=False))
    glass = circle_pts(c, r, 28)
    neck = [(c[0] - r * 0.45, c[1] + r * 0.8), (c[0] + r * 0.45, c[1] + r * 0.8),
            (c[0] + r * 0.32, c[1] + r * 1.25), (c[0] - r * 0.32, c[1] + r * 1.25)]
    pen.fill(neck, col, key + "n")
    pen.fill(glass, col, key)
    pen.stroke(glass, key, closed=True, wk=0.7)
    pen.stroke([neck[0], neck[3]], key + "l", wk=0.6)
    pen.stroke([neck[1], neck[2]], key + "r", wk=0.6)
    base = [(c[0] - r * 0.34, c[1] + r * 1.25), (c[0] + r * 0.34, c[1] + r * 1.25),
            (c[0] + r * 0.3, c[1] + r * 1.7), (c[0] - r * 0.3, c[1] + r * 1.7)]
    pen.fill(base, "metal", key + "b")
    pen.edges(base, key + "b", wk=0.55)
    for i in (1, 2):
        y = c[1] + r * (1.25 + 0.15 * i)
        pen.stroke([(c[0] - r * 0.3, y), (c[0] + r * 0.3, y)], f"{key}t{i}", wk=0.35)
    fil = [(c[0] - r * 0.3, c[1] + r * 0.3), (c[0] - r * 0.15, c[1] - r * 0.15), (c[0], c[1] + r * 0.15),
           (c[0] + r * 0.15, c[1] - r * 0.15), (c[0] + r * 0.3, c[1] + r * 0.3)]
    pen.stroke(fil, key + "f", wk=0.4, color=(0.55, 0.45, 0.3) if b < 0.5 else (0.85, 0.55, 0.15))
    if mode in ("on", "flicker") and b > 0.3:
        for i in range(8):
            if mode == "flicker" and i % 2:
                continue
            a = -math.pi / 2 + (i - 3.5) * 0.42
            ln = 0.15 + 0.45 * b
            p0 = (c[0] + math.cos(a) * r * 1.35, c[1] + math.sin(a) * r * 1.35)
            p1 = (c[0] + math.cos(a) * r * (1.35 + ln), c[1] + math.sin(a) * r * (1.35 + ln))
            pen.stroke([p0, p1], f"{key}ray{i}", wk=0.5, color=(0.9, 0.68, 0.2))
    if mode == "flicker":  # zigzag "bzzt" marks
        for sd in (1, -1):
            zz = [(c[0] + sd * r * (1.3 + 0.18 * k), c[1] - r * (0.2 - 0.3 * (k % 2))) for k in range(4)]
            pen.stroke(zz, f"{key}bz{sd}", wk=0.45)
    if mode == "out":
        smoke_wisp(pen, (c[0], c[1] - r * 1.05), r * 1.6, smoke_age, key + "smoke")


# ---- plates (SCN 436-449) ----
def plate(pen, cam, center, key, tilt=0.35):
    c, s = cam.p(center), cam.scale(center)
    outer = circle_pts(c, 0, 24, rx=0.34 * s, ry=0.34 * s * tilt)
    inner = circle_pts(c, 0, 20, rx=0.22 * s, ry=0.22 * s * tilt)
    pen.fill(outer, "white", key)
    pen.stroke(outer, key, closed=True, wk=0.6)
    pen.stroke(inner, key + "i", closed=True, wk=0.35, color=BLUE)


def plate_stack(pen, cam, count, key="stack"):
    for i in range(count):
        plate(pen, cam, V(1.4, 1.62 + i * 0.07, 1.2), f"{key}{i}")
