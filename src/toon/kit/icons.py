"""Wordless icon library: dirty dishes, an alert, a dead bulb, an X, a check, a laptop, a phone.

`dishes` and `bang` are split out of SCN (scene_lioness.py) 291-299 and 300-302 -- the wordless
body of `speech()` -- and reparameterised as `fn(pen, center, size, key)` instead of being laid
out inside a fixed speech-bubble box. `bulb` is split out of SCN 320-326 (the dead mini bulb
inside `x_card_bulb`). `check` takes its shape from RIG (rig_r4.py) 1170-1173's laptop-screen
checkmark. `cross`, `laptop`, and `phone` are new minimal wordless glyphs (no plan-code
original) drawn to the same doodle proportions as the ported icons.
"""
from __future__ import annotations

import math
from collections.abc import Callable

from toon.engine.mathx import circle_pts
from toon.engine.palette import BLUE, BULB_OFF, GREEN, RED
from toon.engine.pen import Pen


def dishes(pen, center, size, key):
    """Four dirty plates + suds bubbles (SCN 291-299), centred on `center`, scaled by size/124."""
    k = size / 124
    cx, cy = center
    for i in range(4):
        c = (cx, cy - i * 16 * k)
        outer = circle_pts(c, 0, 22, rx=62 * k, ry=17 * k)
        pen.fill(outer, "white", f"{key}pl{i}")
        pen.stroke(outer, f"{key}pl{i}", closed=True, wk=0.55)
        pen.stroke(circle_pts(c, 0, 18, rx=38 * k, ry=10 * k), f"{key}pr{i}", closed=True, wk=0.3, color=BLUE)
    for i, (dx, dy, r) in enumerate(((-70, -64, 12), (-48, -84, 8), (58, -70, 10))):
        pen.stroke(circle_pts((cx + dx * k, cy + dy * k), r * k, 12), f"{key}suds{i}", closed=True, wk=0.35,
                   color=(0.55, 0.7, 0.85))


def bang(pen, center, size, key):
    """The red '!' (SCN 300-302): a tapered bar over a dot."""
    x, y = center
    pen.stroke([(x, y - 0.38 * size), (x - 4 * pen.px, y + 0.08 * size)], key + "ex", wk=1.3, color=RED)
    pen.solid(circle_pts((x - 5 * pen.px, y + 0.3 * size), 8 * pen.px, 10), RED)


def bulb(pen, center, size, key):
    """The mini dead bulb (SCN 320-326): glass + base only -- no glow or rays, it is off."""
    c, r = center, size * 0.2
    glass = circle_pts(c, r, 20)
    pen.fill(glass, BULB_OFF, key)
    pen.stroke(glass, key, closed=True, wk=0.55)
    base = [(c[0] - r * 0.45, c[1] + r * 1.05), (c[0] + r * 0.45, c[1] + r * 1.05),
            (c[0] + r * 0.4, c[1] + r * 1.6), (c[0] - r * 0.4, c[1] + r * 1.6)]
    pen.fill(base, "metal", key + "b")
    pen.edges(base, key + "b", wk=0.45)


def cross(pen, center, size, key):
    """Two red diagonal strokes: a wordless 'no' (the same red X the ✗ card draws over its icon)."""
    x, y = center
    m = size * 0.35
    pen.stroke([(x - m, y - m), (x + m, y + m)], key + "1", wk=1.0, color=RED)
    pen.stroke([(x + m, y - m), (x - m, y + m)], key + "2", wk=1.0, color=RED)


def check(pen, center, size, key):
    """A green three-point check stroke (shape from RIG 1170-1173's laptop-screen checkmark)."""
    x, y = center
    pts = [(x - 0.36 * size, y - 0.02 * size), (x - 0.12 * size, y + 0.22 * size), (x + 0.4 * size, y - 0.3 * size)]
    pen.stroke(pts, key, wk=0.45, color=GREEN)


def _rrect(x, y, w, h, r, n=6):
    """A minimal rounded-rect outline, private to this module.

    Mirrors `graphics.rrect`'s corner-arc construction without importing it, so `icons.py` has
    no dependency on `kit/graphics.py` (which itself imports `draw_icon` from here).
    """
    pts = []
    for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
        pts += [(cx + r * math.cos(math.radians(a0 + 90 * i / n)), cy + r * math.sin(math.radians(a0 + 90 * i / n)))
                for i in range(n + 1)]
    return pts


def laptop_icon(pen, center, size, key):
    """A minimal laptop outline: a screen rectangle over a base bar."""
    x, y = center
    w, h = size * 0.7, size * 0.46
    screen = [(x - w / 2, y - h), (x + w / 2, y - h), (x + w / 2, y), (x - w / 2, y)]
    pen.stroke(screen, key + "s", closed=True, wk=0.6)
    base = [(x - w * 0.62, y + size * 0.08), (x + w * 0.62, y + size * 0.08),
            (x + w * 0.5, y + size * 0.18), (x - w * 0.5, y + size * 0.18)]
    pen.stroke(base, key + "b", closed=True, wk=0.6)


def phone_icon(pen, center, size, key):
    """A minimal phone: a rounded rect with a home-button dot."""
    x, y = center
    w, h = size * 0.5, size * 0.9
    body = _rrect(x - w / 2, y - h / 2, w, h, size * 0.12)
    pen.stroke(body, key, closed=True, wk=0.6)
    pen.solid(circle_pts((x, y + h * 0.32), size * 0.05, 10))


ICONS: dict[str, Callable[[Pen, tuple, float, str], None]] = {
    "dishes": dishes, "bang": bang, "bulb": bulb, "cross": cross, "check": check,
    "laptop": laptop_icon, "phone": phone_icon,
}


def draw_icon(pen, name, center, size, key):
    if name not in ICONS:
        raise ValueError(f"{name!r} is not an icon; animation is wordless — use one of {sorted(ICONS)}")
    ICONS[name](pen, center, size, key)
