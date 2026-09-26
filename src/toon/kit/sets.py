"""The two ghosted sets: office (desk, chair, wall, rug, lamp) and kitchen (counter, cabinets).

Ported from SCN (scene_lioness.py) 361-397 (office_wall, desk_items -> build_set("office")) and
401-434 (kitchen_back, counter, faucet_water -> build_set("kitchen")), plus RIG (rig_r4.py)
1108-1129 (draw_desk_top, draw_desk_leg, draw_chair) and 1262-1279 (draw_lamp, draw_rug). These
set-dressing helpers (the wall, rug, lamp, chair, desk, kitchen back, counter, faucet) are room
furniture tied to one specific layout, so -- unlike the reusable props in `kit/props.py` -- they
live here, private to `build_set`.

Every function here draws in camera/world space, so none of its literal numbers are pixel
sizes; per the task ruling those are left alone (only `kit/graphics.py` and `kit/icons.py`
scale literal pixel constants by `pen.px`).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from toon.engine.mathx import V, circle_pts, rotX
from toon.kit.props import (
    DESK_X,
    DESK_Y,
    DESK_Z0,
    DESK_Z1,
    LAMP_AT,
    LAP_BASE,
    MUG_AT,
    draw_box,
    laptop,
    mug,
)

WALL_Z = -2.4
DOOR = (-3.9, -2.6)  # x range on the back wall
KZ = 1.7  # kitchen back wall (character faces +z, the counter is in front)


@dataclass
class SetLayers:
    back: list = field(default_factory=list)   # ghosted background callables, drawn first
    low: list = field(default_factory=list)    # (depth, fn) sorted with characters' lower parts
    mid: list = field(default_factory=list)    # callables between low and high (desk top, counter)
    high: list = field(default_factory=list)   # (depth, fn) sorted with characters' upper parts


SET_KINDS = ("office", "kitchen")


# ---- office furniture ----
def office_wall(gp, cam, door_open):
    p = cam.p
    gp.stroke([p(V(-6, 0, WALL_Z)), p(V(6, 0, WALL_Z))], "floorline")
    x0, x1 = DOOR
    frame_ = [V(x0, 0, WALL_Z), V(x0, 3.5, WALL_Z), V(x1, 3.5, WALL_Z), V(x1, 0, WALL_Z)]
    gp.edges([p(q) for q in frame_], "doorframe", closed=False)
    a = math.radians(70 * door_open)  # leaf swings into the room
    e = V(x0 + (x1 - x0) * math.cos(a), 0, WALL_Z + (x1 - x0) * math.sin(a))
    leaf = [V(x0, 0, WALL_Z), V(x0, 3.4, WALL_Z), e + V(0, 3.4, 0), e]
    gp.fill([p(q) for q in leaf], "wood", "leaf")
    gp.edges([p(q) for q in leaf], "leaf")
    if door_open < 0.2:
        gp.stroke([p(V(x1 - 0.25, 1.7, WALL_Z + 0.01)), p(V(x1 - 0.1, 1.7, WALL_Z + 0.01))], "knob")
    win = [V(1.4, 2.2, WALL_Z), V(3.4, 2.2, WALL_Z), V(3.4, 3.9, WALL_Z), V(1.4, 3.9, WALL_Z)]
    gp.edges([p(q) for q in win], "window")
    gp.stroke([p(V(2.4, 2.2, WALL_Z)), p(V(2.4, 3.9, WALL_Z))], "winmull")
    gp.stroke([p(V(-1.8, 3.1, WALL_Z)), p(V(0.2, 3.1, WALL_Z))], "shelf")
    for i, (x, hh) in enumerate(((-1.6, 0.5), (-1.4, 0.6), (-1.2, 0.45), (-0.5, 0.35))):
        gp.edges([p(V(x, 3.1, WALL_Z)), p(V(x, 3.1 + hh, WALL_Z)), p(V(x + 0.17, 3.1 + hh, WALL_Z)),
                  p(V(x + 0.17, 3.1, WALL_Z))], f"book{i}", closed=False)


def draw_rug(pen, cam):
    ring = [cam.p(V(0.1 + 2.7 * math.cos(a), 0.0, 0.6 + 2.2 * math.sin(a)))
            for a in np.linspace(0, 2 * math.pi, 48, endpoint=False)]
    pen.fill(ring, "rug", "rug")
    pen.stroke(ring, "rug", closed=True, wk=0.6)
    inner = [cam.p(V(0.1 + 2.3 * math.cos(a), 0.0, 0.6 + 1.85 * math.sin(a)))
             for a in np.linspace(0, 2 * math.pi, 48, endpoint=False)]
    pen.stroke(inner, "rug2", closed=True, wk=0.3)


def draw_lamp(pen, cam):
    s, b = cam.scale(LAMP_AT), cam.p(LAMP_AT)
    pen.fill(circle_pts(b, 0, 16, rx=0.45 * s, ry=0.1 * s), "ink", "lampbase")
    pen.stroke([b, (b[0], b[1] - 3.4 * s)], "lamppole", wk=0.8)
    shade = [(b[0] - 0.35 * s, b[1] - 4.1 * s), (b[0] + 0.35 * s, b[1] - 4.1 * s), (b[0] + 0.6 * s, b[1] - 3.4 * s),
             (b[0] - 0.6 * s, b[1] - 3.4 * s)]
    pen.fill(shade, "shade", "shade")
    pen.edges(shade, "shade")


def draw_desk_top(pen, cam):
    draw_box(pen, cam, V(0, DESK_Y - 0.06, (DESK_Z0 + DESK_Z1) / 2), (DESK_X, 0.06, (DESK_Z1 - DESK_Z0) / 2),
             np.eye(3), "wood", "desk")


def draw_desk_leg(pen, cam, x, z, key):
    pen.stroke([cam.p(V(x, DESK_Y - 0.12, z)), cam.p(V(x, 0, z))], key, wk=1.15)


def draw_chair(pen, cam):
    base = V(0, 0.12, -0.12)
    for i in range(5):
        a = math.radians(90 + i * 72)
        tip = base + V(0.62 * math.cos(a), 0, 0.62 * math.sin(a))
        pen.stroke([cam.p(base), cam.p(tip)], f"chairleg{i}", wk=0.8)
        wp, r = cam.p(tip + V(0, -0.06, 0)), 0.07 * cam.scale(tip)
        pen.solid(circle_pts(wp, r, 12))
    pen.stroke([cam.p(base), cam.p(V(0, 1.2, -0.12))], "chairstem", wk=1.1)
    draw_box(pen, cam, V(0, 1.25, -0.12), (0.62, 0.06, 0.5), np.eye(3), "chair", "seat")
    draw_box(pen, cam, V(0, 1.95, -0.66), (0.58, 0.55, 0.05), rotX(-8), "chair", "back")


# ---- kitchen furniture ----
def kitchen_back(gp, cam):
    p = cam.p
    gp.stroke([p(V(-5, 0, KZ)), p(V(5, 0, KZ))], "kfloor")
    win = [V(-0.9, 2.5, KZ), V(0.9, 2.5, KZ), V(0.9, 4.0, KZ), V(-0.9, 4.0, KZ)]
    gp.edges([p(q) for q in win], "kwin")
    gp.stroke([p(V(0, 2.5, KZ)), p(V(0, 4.0, KZ))], "kwinm")
    for i, x in enumerate((-2.4, 1.3)):
        cab = [V(x, 3.4, KZ), V(x + 1.1, 3.4, KZ), V(x + 1.1, 4.8, KZ), V(x, 4.8, KZ)]
        gp.edges([p(q) for q in cab], f"cab{i}")
        gp.stroke([p(V(x + 0.55, 3.5, KZ)), p(V(x + 0.55, 3.8, KZ))], f"cabk{i}")


def counter(gp, cam):
    draw_box(gp, cam, V(0, 0.8, 1.2), (2.3, 0.8, 0.45), np.eye(3), "wood", "counter")
    p = cam.p
    sink = [V(-0.6, 1.61, 0.95), V(0.6, 1.61, 0.95), V(0.6, 1.61, 1.45), V(-0.6, 1.61, 1.45)]
    gp.edges([p(q) for q in sink], "sink")


def faucet_water(pen, cam, t):
    p = cam.p
    fau = [V(0, 1.62, 1.52), V(0, 2.25, 1.52), V(0, 2.35, 1.35), V(0, 2.2, 1.2)]
    pen.stroke([p(q) for q in fau], "faucet", wk=0.9)
    for i in range(3):
        pen.stroke([p(V(-0.03 + 0.03 * i, 2.18, 1.2)), p(V(-0.03 + 0.03 * i, 1.7, 1.2))], f"water{i}", wk=0.3,
                   color=(0.55, 0.7, 0.85))
    for i, (x, z, r) in enumerate(((-0.35, 1.1, 0.09), (-0.2, 1.3, 0.06), (0.3, 1.05, 0.08), (0.42, 1.3, 0.05),
                                   (0.12, 0.98, 0.05))):
        c, s = p(V(x, 1.7 + 0.03 * math.sin(t * 5 + i), z)), cam.scale(V(x, 1.7, z))
        pen.stroke(circle_pts(c, r * s, 12), f"soap{i}", closed=True, wk=0.35, color=(0.55, 0.7, 0.85))


def build_set(kind, pen, gp, cam, t, door=0.0):
    if kind == "office":
        back = [lambda: office_wall(gp, cam, door), lambda: draw_rug(gp, cam), lambda: draw_lamp(gp, cam)]
        low = [(cam.depth(V(0, 1.3, -0.35)), lambda: draw_chair(gp, cam))]
        for i, (x, z) in enumerate(((-DESK_X + 0.15, DESK_Z0 + 0.1), (DESK_X - 0.15, DESK_Z0 + 0.1),
                                    (-DESK_X + 0.15, DESK_Z1 - 0.1), (DESK_X - 0.15, DESK_Z1 - 0.1))):
            low.append((cam.depth(V(x, 1, z)), lambda x=x, z=z, i=i: draw_desk_leg(gp, cam, x, z, f"dleg{i}")))
        mid = [lambda: draw_desk_top(gp, cam)]
        high = [(cam.depth(LAP_BASE[0]), lambda: laptop(pen, cam, t)),
                (cam.depth(MUG_AT), lambda: mug(gp, cam))]
        return SetLayers(back=back, low=low, mid=mid, high=high)
    if kind == "kitchen":
        back = [lambda: kitchen_back(gp, cam)]
        mid = [lambda: counter(gp, cam), lambda: faucet_water(pen, cam, t)]
        return SetLayers(back=back, mid=mid)
    raise ValueError(f"{kind!r} is not a set kind; use one of {SET_KINDS}")
