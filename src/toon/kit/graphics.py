"""Explainer graphics: speech bubbles, ✗ cards, a check pill, anger marks, speed lines, glow.

Ported from SCN (scene_lioness.py) 122-131 (glow), 238-248 (speed_lines), 259-279 (rrect,
popped), 280-289 (bubble, formerly `speech`'s body+tail), 305-314 (anger_mark), 315-331
(x_card, formerly `x_card_bulb`). `bubble`'s icon layout is generalised, per the task brief, to
evenly space any list of wordless icons across the bubble instead of the original's hardcoded
dishes-stack-plus-bang. `check_pill` has no plan-code original (ruling R3): it is a new minimal
wordless pill -- a check-circle plus an icon, no text.

Every literal pixel size ported here (the bubble corner, the tail width, the ✗ card size and
corner, the pill height) is scaled by `pen.px` so it stays proportioned at any render
resolution; sizes derived from a caller-supplied box (`w`, `h`) are left alone.

`rrect` itself is a neutral geometry helper and lives in `toon.engine.mathx` next to
`circle_pts`/`hull`; it is imported here and re-exported as `graphics.rrect`, which is its
documented home in the kit's interface.

Px contract (ruling R5): every size/box this module's functions take is expected in FINAL
render pixels -- callers pre-scale their own 1080p literals by `pen.px` before calling in (see
`bubble` below for the concrete example).
"""
from __future__ import annotations

import math

import numpy as np

from toon.cairo_compat import cairo
from toon.engine.mathx import circle_pts, e_back, hsign, rrect
from toon.engine.palette import GREEN, ORANGE, RED
from toon.kit.icons import draw_icon

GLOW_COLORS = {"warm": (0.99, 0.84, 0.52), "cool": (0.8, 0.84, 0.9)}


def glow(ctx, center, radius, color=GLOW_COLORS["warm"], alpha=0.42):
    if alpha <= 0.005:
        return
    g = cairo.RadialGradient(center[0], center[1], radius * 0.1, center[0], center[1], radius)
    g.add_color_stop_rgba(0, *color, alpha)
    g.add_color_stop_rgba(1, *color, 0.0)
    ctx.set_source(g)
    ctx.arc(center[0], center[1], radius, 0, 2 * math.pi)
    ctx.fill()


def speed_lines(pen, center, inner, n=34, key="speed", grow=1.0):
    if grow <= 0.02:
        return
    for i in range(n):
        a = 2 * math.pi * i / n + 0.05 * hsign(i * 7)
        r0 = inner * (1 + 0.25 * abs(hsign(i * 13 + 1)))
        r1 = r0 + inner * (0.35 + 0.5 * abs(hsign(i * 3 + 5))) * grow
        pen.stroke([(center[0] + math.cos(a) * r0, center[1] + math.sin(a) * r0),
                    (center[0] + math.cos(a) * r1, center[1] + math.sin(a) * r1)], f"{key}{i}", wk=0.4, color=ORANGE)


def popped(ctx, pivot, k, draw):
    """Pop-in: scale from 0.55 with a little overshoot around pivot; k = 0..1 progress."""
    if k <= 0:
        return
    sc = 0.55 + 0.45 * e_back(min(k, 1.0))
    ctx.save()
    ctx.translate(*pivot)
    ctx.scale(sc, sc)
    ctx.translate(-pivot[0], -pivot[1])
    draw()
    ctx.restore()


def anger_mark(pen, c, r, key="anger"):
    """Manga 'vein' mark: four little arcs around a centre (universal, wordless)."""
    for i in range(4):
        a0 = math.radians(45 + i * 90)
        cc = (c[0] + math.cos(a0) * r * 0.75, c[1] + math.sin(a0) * r * 0.75)
        arc = [(cc[0] + r * 0.55 * math.cos(a0 + math.pi + d), cc[1] + r * 0.55 * math.sin(a0 + math.pi + d))
               for d in np.linspace(-0.9, 0.9, 6)]
        pen.stroke(arc, f"{key}{i}", wk=0.7, color=RED)


# Per-icon layout inside a speech bubble (ruling R10): (x_frac of w, y_frac of h, size_frac of
# h) -- each icon's exact anchor and size as the tryout hand-placed it in its one wordless bubble
# (SCN `speech()` 280-302: the dishes stack at `x+0.38w, y+0.62h` with its native size 124 at the
# box's reference height of 170, and the "!" whose bar/dot the tryout drew straight off the box
# (`ex = x+0.8w`; offsets `0.18h`/`0.6h`/`0.78h`) -- least-squares fit onto `bang()`'s own
# center+size parameterisation (`toon.kit.icons.bang`), residual < 0.01h on every offset. Icons
# with no entry fall back to `_BUBBLE_DEFAULT`, the original v0 even-spacing rule, so `bubble()`
# stays generic for any icon list -- it never branches on an icon's name.
#
# An icon listed here also draws with the bare bubble `key` (no per-index suffix): that is what
# `speech()` itself did (both `dishes` and `bang` hand-authored their sub-shape keys, e.g.
# "speechpl0"/"speechex", straight off `key`, never off an icon index), and `Pen`'s hand-drawn
# wobble is seeded from that exact key string (`Pen.seed`) -- an "ic{i}"-suffixed key reproduces
# the right shape at the wrong *wobble phase*, which still shows up as a few-pixel outline diff.
# `dishes`'s and `bang`'s own sub-keys ("pl"/"pr"/"suds" vs "ex") don't collide, so this is safe
# for the ported pair; unlisted/fallback icons keep the "ic{i}" suffix to avoid colliding.
BUBBLE_LAYOUT: dict[str, tuple[float, float, float]] = {
    "dishes": (0.38, 0.62, 124 / 170),
    "bang": (0.80, 0.52, 267 / 301),
}
_BUBBLE_DEFAULT_SIZE = 0.6
_BUBBLE_DEFAULT_Y = 0.55


def bubble_layout(icons: list[str], w: float, h: float) -> list[tuple[tuple[float, float], float]]:
    """The `(center, size)` -- relative to the box's own `(0, 0)`-`(w, h)` -- for each icon."""
    n = len(icons)
    out = []
    for i, name in enumerate(icons):
        x_frac, y_frac, size_frac = BUBBLE_LAYOUT.get(
            name, (0.1 + 0.8 * (i + 0.5) / n, _BUBBLE_DEFAULT_Y, _BUBBLE_DEFAULT_SIZE))
        out.append(((w * x_frac, h * y_frac), h * size_frac))
    return out


def bubble(pen, box, tail_to, icons, key="speech"):
    """A speech-bubble body + tail (SCN 280-289) with wordless icons laid out by `bubble_layout`.

    `box` (x, y, w, h) and `tail_to` are expected in FINAL render pixels (ruling R5): the caller
    scales its own 1080p literals by `pen.px` before calling in -- e.g. the renderer (Task 8)
    passes `(hp.x + 80*px, hp.y - 330*px, 330*px, 170*px)`, not the bare 1080p numbers. `icons`'
    per-icon `size` is then derived from `h`, so it inherits that same final-pixel scale.
    """
    x, y, w, h = box
    body = rrect(x, y, w, h, 28 * pen.px)
    tb = (x + w * 0.22, y + h - 2 * pen.px)
    tail = [(tb[0] - 24 * pen.px, tb[1]), tail_to, (tb[0] + 24 * pen.px, tb[1])]
    pen.fill(tail, "white", key + "t")
    pen.fill(body, "white", key)
    pen.stroke(body, key, closed=True, wk=0.8)
    pen.stroke(tail, key + "t", wk=0.8)
    for i, (name, ((cx, cy), size)) in enumerate(zip(icons, bubble_layout(icons, w, h), strict=True)):
        icon_key = key if name in BUBBLE_LAYOUT else f"{key}ic{i}"
        draw_icon(pen, name, (x + cx, y + cy), size, icon_key)


def x_card(pen, x, y, icon, size=140, key="xcard"):
    """A wordless ✗ card: the given icon crossed out in red (SCN 315-331, generalised)."""
    size = size * pen.px
    body = rrect(x, y, size, size, 22 * pen.px)
    pen.fill(body, "white", key)
    pen.stroke(body, key, closed=True, wk=0.8)
    c = (x + size / 2, y + size * 0.42)
    draw_icon(pen, icon, c, size, key + "b")
    m = size * 0.16
    pen.stroke([(x + m, y + m), (x + size - m, y + size - m)], key + "x1", wk=1.0, color=RED)
    pen.stroke([(x + size - m, y + m), (x + m, y + size - m)], key + "x2", wk=1.0, color=RED)


def check_pill(pen, x, y, icon, key="check"):
    """A minimal wordless status pill: a green check-circle at the left, the icon at the right.

    No plan-code original (ruling R3) -- designed in the same wordless idiom as the ✗ card.
    """
    h = 84 * pen.px
    w = h * 2.5
    body = rrect(x, y, w, h, h / 2, n=8)
    pen.fill(body, "white", key)
    pen.stroke(body, key, closed=True, wk=0.8)
    c, r = (x + h * 0.55, y + h / 2), h * 0.34
    pen.solid(circle_pts(c, r, 20), GREEN)
    tick = [(c[0] - r * 0.45, c[1] + r * 0.02), (c[0] - r * 0.1, c[1] + r * 0.4), (c[0] + r * 0.5, c[1] - r * 0.42)]
    pen.stroke(tick, key + "c", wk=0.55, color=(1, 1, 1))
    draw_icon(pen, icon, (x + w - h * 0.6, y + h / 2), h * 0.75, key + "i")
