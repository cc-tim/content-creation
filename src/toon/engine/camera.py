"""3D camera projection: perspective transformation, orbit controls."""
from __future__ import annotations

import math

import numpy as np

from toon.engine.mathx import UP, V, unit


class Cam:
    def __init__(self, pos, target, focal, width, height, shift=(0.0, 0.0)):
        self.pos = pos
        self.f = unit(target - pos)
        self.r = unit(np.cross(self.f, UP))
        self.u = np.cross(self.r, self.f)
        self.focal, self.shift = focal, shift
        self.width, self.height = width, height

    def depth(self, p):
        return float(np.dot(p - self.pos, self.f))

    def p(self, p):
        d = p - self.pos
        z = np.dot(d, self.f)
        return (self.width / 2 + self.shift[0] + self.focal * np.dot(d, self.r) / z,
                self.height / 2 + self.shift[1] - self.focal * np.dot(d, self.u) / z)

    def scale(self, p):
        return self.focal / self.depth(p)

    def sdir(self, w):  # world direction -> screen direction (orthographic, y down)
        return float(np.dot(w, self.r)), float(-np.dot(w, self.u))

    def toward(self, at):
        return unit(self.pos - at)


def orbit(az, el, dist, target, focal, width=1920, height=1080, shift=(0.0, 0.0)):
    """Camera on a sphere around target. `focal` is in 1080p pixels and scales with height."""
    a, e = math.radians(az), math.radians(el)
    pos = target + dist * V(math.sin(a) * math.cos(e), math.sin(e), math.cos(a) * math.cos(e))
    return Cam(pos, target, focal * height / 1080, width, height, shift)
