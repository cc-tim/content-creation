"""Body rig: skeleton constants, IK, and pose blending/placement (no globals).

Ported from RIG (rig_r4.py) 411-415 (body constants), 426-447 (Pose), 465 (DISCRETE),
490-534 (ik3, rig), and SCN (scene_lioness.py) 68-88 (placed, mix). The desk/set constants
(DESK_Y, LAP_BASE, HINGE, ...), POSES, TRACK, pose_at, and laptop_state stay in the throwaway
tryout; they move to kit/props.py in a later task. `rig()` now requires `root` explicitly
instead of falling back to a module-level HIP global.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from toon.engine.mathx import V, lerp, rotX, rotY, unit

TORSO, HEAD_R, NECK = 1.1, 1.0, 0.95
UPPER, FORE, THIGH, SHIN = 0.62, 0.56, 0.55, 0.56
HIP_SIT = V(0, 1.4, 0)
HIP_STAND = V(0, 1.1, 0)


@dataclass
class Pose:
    lean: float = 15.0
    head_tilt: float = 8.0
    head_turn: float = 0.0
    hand_l: tuple = (0.2, 2.25, 1.18)
    hand_r: tuple = (-0.22, 2.25, 1.16)
    foot_l: tuple = (0.3, 0.9, 0.62)
    foot_r: tuple = (-0.3, 0.92, 0.58)
    typing: float = 1.0
    tapping: float = 0.0
    tremble: float = 0.0
    brow: float = 0.0
    worried: float = 0.0
    hair: float = 0.0
    sweat: float = 0.0
    shock: float = 0.0
    kick: float = 0.0
    eyes: str = "dot"
    mouth: str = "flat"
    phone: str = "desk"


DISCRETE = ("eyes", "mouth", "phone")


def ik3(s, t, a, b, pole):
    dv = t - s
    d = float(np.linalg.norm(dv))
    dn = dv / (d or 1)
    d = min(max(d, abs(a - b) + 1e-3), a + b - 1e-3)
    al = math.acos(min(max((a * a + d * d - b * b) / (2 * a * d), -1), 1))
    pv = pole - s
    perp = unit(pv - np.dot(pv, dn) * dn)
    return s + a * (math.cos(al) * dn + math.sin(al) * perp), s + dn * d


def rig(pose, t, root, yaw=0.0):
    hip = root
    trem = pose.tremble * math.sin(t * 83) * 1.6
    breath = math.sin(t * 2 * math.pi * 0.3) * 0.8
    Ry = rotY(yaw)
    Rb = Ry @ rotX(pose.lean + breath + trem)
    top = hip + Rb @ V(0, TORSO, 0)
    Rh = Rb @ rotX(pose.head_tilt) @ rotY(pose.head_turn)
    head = top + Rh @ V(0, NECK, 0)

    def hand(base, ph):
        p = V(*base)
        p[1] += pose.typing * math.sin(t * 2 * math.pi * 6 + ph) * 0.035
        p[2] += pose.tapping * max(0.0, math.sin(t * 2 * math.pi * 3 + ph)) * -0.07
        p[0] += pose.tremble * math.sin(t * 71 + ph) * 0.03
        return p

    arms = {}
    for side, sx, base, ph in (("l", 1, pose.hand_l, 0.0), ("r", -1, pose.hand_r, 1.9)):
        sh = top + Rb @ V(0.42 * sx, -0.14, 0)
        e, h = ik3(sh, hand(base, ph), UPPER, FORE, sh + Rb @ V(1.0 * sx, -1.0, -0.4))
        arms[side] = (sh, e, h)
    legs = {}
    for side, sx, base, ph in (("l", 1, pose.foot_l, 0.0), ("r", -1, pose.foot_r, 2.6)):
        hp = hip + Rb @ V(0.26 * sx, -0.02, 0)
        f = V(*base)
        f[2] += pose.kick * math.sin(t * 2 * math.pi * 1.6 + ph) * 0.18
        f[1] += pose.kick * max(0.0, math.sin(t * 2 * math.pi * 1.6 + ph)) * 0.1
        k, ft = ik3(hp, f, THIGH, SHIN, hp + Ry @ V(0, 0.6, 1.5))
        legs[side] = (hp, k, ft)
    return dict(Rb=Rb, Rh=Rh, top=top, head=head, arms=arms, legs=legs, hip=hip)


def mix(a, b, k):
    """Blend two poses (continuous fields lerp, discrete fields switch at k=0.5)."""
    out = {}
    for f in a.__dict__:
        va, vb = getattr(a, f), getattr(b, f)
        if f in DISCRETE:
            out[f] = vb if k > 0.5 else va
        elif isinstance(va, tuple):
            out[f] = tuple(lerp(x, y, k) for x, y in zip(va, vb, strict=False))
        else:
            out[f] = lerp(va, vb, k)
    return Pose(**out)


def placed(pose, root, yaw, hip0):
    """Pose targets authored relative to hip0 facing +z -> world, for a character at root/yaw."""
    Ry = rotY(yaw)
    kw = {k: tuple(root + Ry @ (V(*getattr(pose, k)) - hip0)) for k in ("hand_l", "hand_r", "foot_l", "foot_r")}
    return replace(pose, **kw)
