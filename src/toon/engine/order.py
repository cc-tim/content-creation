"""Depth-sort a character's parts and paint them far to near.

Ported from SCN (scene_lioness.py) 89-119. `character_parts` no longer mutates module globals
per character (RIG's `cast()` swapped FACE/HAIR/BODY before each part); each part closure
instead carries the `Look` it was built with, so multiple characters can be depth-sorted and
painted together without leaking state between them.
"""
from dataclasses import dataclass, field

from toon.engine.body import draw_arm, draw_leg, draw_torso
from toon.engine.head import draw_head
from toon.engine.mathx import V
from toon.engine.rig import TORSO, placed, rig


@dataclass
class CharParts:
    low: list = field(default_factory=list)   # legs + torso
    high: list = field(default_factory=list)  # head + arms + held props


def character_parts(pen, cam, look, pose, root, yaw, t, hip0, extra=None):
    wp = placed(pose, root, yaw, hip0)
    rg = rig(wp, t, root=root, yaw=yaw)
    td = cam.depth(root + rg["Rb"] @ V(0, TORSO / 2, 0))
    low = [(cam.depth(rg["legs"][s][1]), lambda s=s: draw_leg(pen, cam, rg, s)) for s in "lr"]
    low.append((td, lambda: draw_torso(pen, cam, rg, look)))
    high = [(min(cam.depth(rg["head"]), td - 0.01), lambda: draw_head(pen, cam, rg, wp, t, look))]
    for s in "lr":
        sh, _, h = rg["arms"][s]
        d = cam.depth((sh + h) / 2)
        if h[1] > rg["head"][1] - 0.3:  # hands at the face: chibi arms tuck behind the big head
            d = max(d, cam.depth(rg["head"]) + 0.02)
        high.append((d, lambda s=s: draw_arm(pen, cam, rg, s)))
    if extra:
        high += extra(rg)
    return CharParts(low, high), rg


def run(items):
    for _, fn in sorted(items, key=lambda x: -x[0]):
        fn()
