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
"""
from __future__ import annotations

import math

import numpy as np

from toon.cairo_compat import cairo
from toon.engine.mathx import circle_pts, e_back, hsign
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


def rrect(x, y, w, h, r, n=6):
    pts = []
    for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
        pts += [(cx + r * math.cos(math.radians(a0 + 90 * k / n)), cy + r * math.sin(math.radians(a0 + 90 * k / n)))
                for k in range(n + 1)]
    return pts


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


def bubble(pen, box, tail_to, icons, key="speech"):
    """A speech-bubble body + tail (SCN 280-289) with wordless icons spaced evenly across it."""
    x, y, w, h = box
    body = rrect(x, y, w, h, 28 * pen.px)
    tb = (x + w * 0.22, y + h - 2 * pen.px)
    tail = [(tb[0] - 24 * pen.px, tb[1]), tail_to, (tb[0] + 24 * pen.px, tb[1])]
    pen.fill(tail, "white", key + "t")
    pen.fill(body, "white", key)
    pen.stroke(body, key, closed=True, wk=0.8)
    pen.stroke(tail, key + "t", wk=0.8)
    n = len(icons)
    for i, name in enumerate(icons):
        c = (x + w * (0.1 + 0.8 * (i + 0.5) / n), y + h * 0.55)
        draw_icon(pen, name, c, h * 0.6, f"{key}ic{i}")


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
