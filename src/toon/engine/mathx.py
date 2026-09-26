"""Tiny math: 3D vectors, rotations, interpolation, easing, noise, convex hull, 2D shapes."""
from __future__ import annotations

import math

import numpy as np


def V(x, y, z):
    return np.array((x, y, z), float)


UP = V(0, 1, 0)


def unit(a):
    n = np.linalg.norm(a)
    return a / n if n > 1e-9 else a


def rotX(d):
    c, s = math.cos(math.radians(d)), math.sin(math.radians(d))
    return np.array(((1, 0, 0), (0, c, -s), (0, s, c)))


def rotY(d):
    c, s = math.cos(math.radians(d)), math.sin(math.radians(d))
    return np.array(((c, 0, s), (0, 1, 0), (-s, 0, c)))


def lerp(a, b, k):
    return a + (b - a) * k


def lerp2(p, q, k):
    return (lerp(p[0], q[0], k), lerp(p[1], q[1], k))


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def e_out(x):
    return 1 - (1 - x) ** 3


def e_back(x):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def e_lin(x):
    return x


def hsign(n):
    n &= 0xFFFFFFFF
    n = (((n >> 16) ^ n) * 0x45D9F3B) & 0xFFFFFFFF
    n = (((n >> 16) ^ n) * 0x45D9F3B) & 0xFFFFFFFF
    n = (n >> 16) ^ n
    return n / 0xFFFFFFFF * 2 - 1


def noise1(x, seed):
    i = math.floor(x)
    f = x - i
    a, b = hsign(seed + i * 374761393), hsign(seed + (i + 1) * 374761393)
    return a + (b - a) * f * f * (3 - 2 * f)


def hull(pts):
    pts = sorted(set((round(x, 2), round(y, 2)) for x, y in pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def circle_pts(c, r, n=40, rx=None, ry=None, rot=0.0):
    rx, ry = rx or r, ry or r
    cr, sr = math.cos(rot), math.sin(rot)
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        x, y = rx * math.cos(a), ry * math.sin(a)
        out.append((c[0] + x * cr - y * sr, c[1] + x * sr + y * cr))
    return out


def rrect(x, y, w, h, r, n=6):
    """A rounded rectangle's outline, as a flat list of points (four n-segment corner arcs).

    Ported from SCN (scene_lioness.py) 259-264. A neutral geometry helper -- shared by
    `toon.kit.graphics` (which re-exports it as `graphics.rrect`, its documented home per the
    kit's interface) and `toon.kit.icons`, so the two kit modules don't duplicate it or need to
    import from each other.
    """
    pts = []
    for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
        pts += [(cx + r * math.cos(math.radians(a0 + 90 * k / n)), cy + r * math.sin(math.radians(a0 + 90 * k / n)))
                for k in range(n + 1)]
    return pts


EASES = {"linear": e_lin, "smooth": smooth, "out": e_out, "back": e_back}
