"""Explainer graphics: speech bubbles, ✗ cards, a check pill, anger marks, speed lines, glow.

Ported from SCN (scene_lioness.py) 122-131 (glow), 238-248 (speed_lines), 259-279 (rrect,
popped), 280-289 (bubble, formerly `speech`'s body+tail), 305-314 (anger_mark), 315-331
(x_card, formerly `x_card_bulb`). `bubble`'s icon layout is generalised, per the task brief, to
lay out any list of wordless icons across the bubble in order-aware weighted slots (ruling
R11; see `bubble_layout`) instead of the original's hardcoded dishes-stack-plus-bang.
`check_pill` has no plan-code original (ruling R3): it is a new minimal wordless pill -- a
check-circle plus an icon, no text.

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
from dataclasses import dataclass

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


# ---- speech-bubble icon layout: order-aware weighted slots (ruling R11) ---------------------
#
# Icons lay out left to right in LIST ORDER across the bubble's content span `[0.08w, 0.92w]`.
# Each icon gets a slot whose width is proportional to its registry `weight` (default 4 for any
# icon with no entry), and its centre is that slot's centre -- so position depends on where an
# icon sits in the list, not on its name, and two icons (even the same name twice) never land on
# the same spot. Per-icon `y_frac`/`size_frac` (of `h`) place and size it vertically, as before
# ruling R10. `width_per_size` -- the icon's own drawn width per unit of its `size` argument,
# estimated from its drawing code -- clamps `size` so it can never overflow its own slot
# (`size = min(size_frac*h, slot_w / width_per_size)`), so adjacent icons can't overlap either.
# `bubble()` still never branches on an icon's name: all of this is one dict lookup with a
# default, exactly like R10's registry.
#
# `dishes`'s and `bang`'s weights/fractions reproduce the tryout's hand-placed bubble (SCN
# `speech()` 280-302) exactly for `[dishes, bang]`: weight 5 vs 2 over the 0.84w content span
# puts dishes' slot centre at `0.08 + 0.6/2 = 0.38w` and bang's at `0.68 + 0.24/2 = 0.80w` --
# the tryout's own `x+0.38w`/`ex = x+0.8w`. `dishes.width_per_size` (150/124) is its full drawn
# width -- including the three suds bubbles, whose offsets (SCN 297-299) reach a bit further
# left (-82) and less far right (+68) than the plate stack alone (+-62) -- over its native size
# (124, at this box's reference height of 170). `bang.width_per_size` is its bar-plus-dot span:
# the bar's own x is unshifted, its foot is 4px left, and the dot (5px left, radius 8) reaches
# from -13 to +3, an ~16px span; since SCN's bar/dot x-offsets are literal pixels rather than
# scaled by `size` (only their *y* offsets are, `-0.38s`/`+0.08s`/`+0.3s`), this ratio is only
# exact at this box's reference height (170) -- an accepted approximation per the ruling.
@dataclass(frozen=True)
class BubbleIcon:
    weight: float = 4.0
    y_frac: float = 0.55
    size_frac: float = 0.6
    width_per_size: float = 1.0


_BANG_SIZE_FRAC = 267 / 301  # least-squares fit onto bang()'s center+size shape (ruling R10)

BUBBLE_ICONS: dict[str, BubbleIcon] = {
    "dishes": BubbleIcon(weight=5.0, y_frac=0.62, size_frac=124 / 170, width_per_size=150 / 124),
    "bang": BubbleIcon(weight=2.0, y_frac=0.52, size_frac=_BANG_SIZE_FRAC,
                        width_per_size=16 / (_BANG_SIZE_FRAC * 170)),
}
_DEFAULT_ICON = BubbleIcon()
_CONTENT_X0, _CONTENT_X1 = 0.08, 0.92


def bubble_layout(icons: list[str], w: float, h: float) -> list[tuple[tuple[float, float], float]]:
    """The `(center, size)` -- relative to the box's own `(0, 0)`-`(w, h)` -- for each icon, in
    left-to-right weighted slots across the content span (ruling R11)."""
    recipes = [BUBBLE_ICONS.get(name, _DEFAULT_ICON) for name in icons]
    content_w = (_CONTENT_X1 - _CONTENT_X0) * w
    total_weight = sum(r.weight for r in recipes) or 1.0
    out: list[tuple[tuple[float, float], float]] = []
    x = _CONTENT_X0 * w
    for r in recipes:
        slot_w = content_w * r.weight / total_weight
        size = min(r.size_frac * h, slot_w / r.width_per_size)
        out.append(((x + slot_w / 2, r.y_frac * h), size))
        x += slot_w
    return out


def bubble_icon_keys(icons: list[str], key: str) -> list[str]:
    """The draw key for each icon (ruling R11): an icon's FIRST occurrence of its name keeps the
    bare bubble `key`, matching `speech()`'s own hand-authored sub-keys (e.g. "speechpl0",
    "speechex"), so `Pen`'s hand-drawn wobble reproduces the tryout's seed (ruling R10). A name
    repeated later in the list gets `f"{key}ic{i}"` instead, so it doesn't draw with the exact
    same wobble as its earlier occurrence."""
    seen: set[str] = set()
    keys = []
    for i, name in enumerate(icons):
        keys.append(key if name not in seen else f"{key}ic{i}")
        seen.add(name)
    return keys


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
    layout, keys = bubble_layout(icons, w, h), bubble_icon_keys(icons, key)
    for name, ((cx, cy), size), icon_key in zip(icons, layout, keys, strict=True):
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
