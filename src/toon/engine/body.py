"""Torso, arms, legs.

Ported from RIG (rig_r4.py) 1010-1064 (draw_torso, draw_arm, draw_leg). `draw_torso` builds its
body dict from `look.body` merged over `BODY_DEFAULT` instead of reading a module-level BODY
global. `draw_arm` drops its `pose, t` parameters and the phone-in-hand hook (props are a later
task's concern) since it no longer needs to animate a held phone here.
"""
from __future__ import annotations

import math

import numpy as np

from toon.engine.look import BODY_DEFAULT
from toon.engine.mathx import V, circle_pts, hull
from toon.engine.rig import TORSO


def draw_torso(pen, cam, rg, look):
    body = {**BODY_DEFAULT, **look.body}
    Rb = rg["Rb"]
    ring = []
    for y, rx, rz in ((TORSO - 0.08, 0.46, 0.3), (-0.06, 0.56, 0.36)):
        for a in np.linspace(0, 2 * math.pi, 20, endpoint=False):
            ring.append(cam.p(rg["hip"] + Rb @ V(rx * math.cos(a), y, rz * math.sin(a))))
    hl = hull(ring)
    pen.fill(hl, body["shirt"], "torso")
    pen.stroke(hl, "torso", closed=True)
    if body.get("apron") and np.dot(Rb @ V(0, 0, 1), cam.toward(rg["hip"])) > 0.15:
        ap = [cam.p(rg["hip"] + Rb @ V(x, y, z)) for x, y, z in
              ((-0.3, TORSO - 0.3, 0.33), (0.3, TORSO - 0.3, 0.33), (0.38, -0.05, 0.4), (-0.38, -0.05, 0.4))]
        pen.fill(ap, "white", "apron")
        pen.stroke(ap, "apron", closed=True, wk=0.6)
    if body["hood"]:  # hood rolled round the neck + a flap down the back, drawstrings in front
        HIPc = rg["hip"]
        tow = cam.toward(HIPc + Rb @ V(0, TORSO, 0))
        collar = hull([cam.p(HIPc + Rb @ V(0.55 * math.cos(a), TORSO - 0.02 + 0.05 * math.sin(a) ** 2, 0.42 * math.sin(a)))
                       for a in np.linspace(0, 2 * math.pi, 24, endpoint=False)])
        pen.fill(collar, body["shirt"], "hood")
        pen.stroke(collar, "hood", closed=True, wk=0.8)
        if np.dot(Rb @ V(0, 0, -1), tow) > 0.2:
            flap = [cam.p(HIPc + Rb @ V(x, y, -0.38)) for x, y in
                    ((-0.42, TORSO - 0.05), (0.42, TORSO - 0.05), (0.2, TORSO - 0.55), (0.0, TORSO - 0.62), (-0.2, TORSO - 0.55))]
            pen.fill(flap, body["shirt"], "hoodflap")
            pen.stroke(flap, "hoodflap", closed=True, wk=0.7)
        if np.dot(Rb @ V(0, 0, 1), tow) > 0.2:
            for sd in (1, -1):
                a, b = HIPc + Rb @ V(0.13 * sd, TORSO - 0.15, 0.36), HIPc + Rb @ V(0.14 * sd, TORSO - 0.5, 0.38)
                pen.stroke([cam.p(a), cam.p(b)], f"string{sd}", wk=0.35, color=(0.9, 0.9, 0.88))


def draw_arm(pen, cam, rg, side):
    sh, e, h = rg["arms"][side]
    pen.stroke([cam.p(sh), cam.p(e), cam.p(h)], f"arm{side}", wk=0.85)
    hp, r = cam.p(h), 0.12 * cam.scale(h)
    pen.fill(circle_pts(hp, r, 16), "skin", f"hand{side}")
    pen.stroke(circle_pts(hp, r, 16), f"hand{side}", closed=True, wk=0.55)


def draw_leg(pen, cam, rg, side):
    hp, k, f = rg["legs"][side]
    pen.stroke([cam.p(hp), cam.p(k), cam.p(f)], f"leg{side}", wk=0.85)
    fwd = cam.sdir(rg["Rb"] @ V(0, 0, 1))
    fp = cam.p(f + rg["Rb"] @ V(0, 0, 0.08))
    s = cam.scale(f)
    rot = math.atan2(fwd[1], fwd[0]) if math.hypot(*fwd) > 0.3 else 0.0
    rx = 0.1 + 0.08 * min(1.0, math.hypot(*fwd))
    shoe = circle_pts(fp, 0, 16, rx=rx * s, ry=0.075 * s, rot=rot)
    pen.fill(shoe, "ink", f"shoe{side}")
    pen.stroke(shoe, f"shoe{side}", closed=True, wk=0.5)
