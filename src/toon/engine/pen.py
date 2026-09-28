"""The hand-drawn pen: line-A (marker doodle) ink, plus a ghost mode for background sets.

Ported from RIG (rig_r4.py) 189-410, keeping only the marker style (LINE_A). Resolution-aware:
every pixel-space constant (line width, wobble amplitude, overshoot, noise cycle length, fill
offset) scales with `px` so the same seeds/keys draw an identical *proportioned* line at any
render resolution.
"""
from __future__ import annotations

import math
import zlib

from toon.cairo_compat import cairo
from toon.engine.mathx import hsign, lerp, lerp2, noise1
from toon.engine.palette import GHOST_INK, PAPER, ROLE, SKIN

LINE_A = dict(ink=(0.11, 0.10, 0.10), w=7.5, amp=1.7, over=8,
              passes=((1.0, 1.0, 0.0),), taper=0.0, fill="offset")


class Pen:
    def __init__(self, ctx, boil, zoom=1.0, px=1.0, ghost=False, mode="full", shimmer=0.3):
        self.c, self.s, self.boil = ctx, LINE_A, boil
        self.zoom = zoom  # line width follows camera zoom only mildly (a drawing, not a render)
        self.px = px  # line width/wobble/overshoot follow render resolution linearly
        self.ghost = ghost  # ghosted set: faint thin lines, pale fills
        self.mode = mode  # "full": fresh seed every drawing; "soft"/"still": one fixed drawing
        self.shimmer = shimmer  # "soft" only: faint per-drawing shimmer amplitude, 0..1

    def seed(self, key, k=0):
        boil = self.boil if self.mode == "full" else 0
        return (zlib.crc32(key.encode()) * 31 + boil * 7919 + k * 104729) & 0xFFFFFFFF

    @property
    def w(self):
        return self.s["w"] * self.px * self.zoom ** 0.35

    # -- path shaping --
    def _resample(self, pts, closed, spacing=4.0):
        spacing = spacing * self.px
        P = list(pts) + [pts[0]] if closed else list(pts)
        seg = [math.dist(P[i], P[i + 1]) for i in range(len(P) - 1)]
        L = sum(seg)
        if L < 1e-6:
            return [P[0], P[0]], [0.0, 1.0], 0.0
        n = max(4, int(L / spacing))
        out, us, j, acc = [], [], 0, 0.0
        for k in range(n + 1):
            d = L * k / n
            while j < len(seg) - 1 and acc + seg[j] < d:
                acc += seg[j]
                j += 1
            f = 0.0 if seg[j] == 0 else min(max((d - acc) / seg[j], 0.0), 1.0)
            out.append(lerp2(P[j], P[j + 1], f))
            us.append(k / n)
        return out, us, L

    def _shape(self, pts, closed, key, k, amp_k=1.0, over_k=1.0):
        pts, us, L = self._resample(pts, closed)
        if L < 1e-6:
            return pts, us, L
        s = self.seed(key, k)
        over = self.s["over"] * over_k * (0.6 + 0.4 * abs(hsign(s + 3))) * self.px
        if closed:  # hand-drawn loop: start, go round, overshoot past the start
            m = min(len(pts) - 1, int(len(pts) * over / L) + 1)
            pts = pts + pts[1:m + 1]
            us = us + [1 + u for u in us[1:m + 1]]
        else:
            (x0, y0), (x1, y1) = pts[0], pts[min(2, len(pts) - 1)]
            d0 = math.hypot(x1 - x0, y1 - y0) or 1
            (xa, ya), (xb, yb) = pts[-1], pts[max(-3, -len(pts))]
            d1 = math.hypot(xa - xb, ya - yb) or 1
            o0, o1 = over * (0.3 + 0.7 * abs(hsign(s + 5))), over * (0.3 + 0.7 * abs(hsign(s + 7)))
            pts = ([(x0 - (x1 - x0) / d0 * o0, y0 - (y1 - y0) / d0 * o0)] + pts +
                   [(xa + (xa - xb) / d1 * o1, ya + (ya - yb) / d1 * o1)])
            us = [-o0 / L] + us + [1 + o1 / L]
        amp = self.s["amp"] * amp_k * self.px
        cyc = max(1.0, L / (150.0 * self.px))
        dx, dy = hsign(s + 11) * amp * 0.7, hsign(s + 13) * amp * 0.7  # whole-stroke drift
        out = []
        for i, (x, y) in enumerate(pts):
            a, b = pts[max(i - 1, 0)], pts[min(i + 1, len(pts) - 1)]
            tx, ty = b[0] - a[0], b[1] - a[1]
            tl = math.hypot(tx, ty) or 1
            d = amp * (noise1(us[i] * cyc, s) + 0.35 * noise1(us[i] * cyc * 3.7, s + 5))
            out.append((x - ty / tl * d + dx, y + tx / tl * d + dy))
        if self.mode == "soft" and L >= 1e-6:
            sb = (zlib.crc32(key.encode()) * 31 + self.boil * 7919 + k * 104729) & 0xFFFFFFFF
            amp_s = self.s["amp"] * amp_k * self.px * self.shimmer
            res = []
            for i, (x, y) in enumerate(out):
                a, b = out[max(i - 1, 0)], out[min(i + 1, len(out) - 1)]
                tx, ty = b[0] - a[0], b[1] - a[1]
                tl = math.hypot(tx, ty) or 1
                d = amp_s * noise1(us[i] * cyc, sb)
                res.append((x - ty / tl * d, y + tx / tl * d))
            out = res
        return out, us, L

    def _ribbon(self, pts, us, width, key, k, color, alpha):
        n = len(pts)
        if n < 2:
            return
        s = self.seed(key, k + 40)
        taper = self.s["taper"]
        u0, u1 = us[0], us[-1]
        ws = []
        for i in range(n):
            t = (us[i] - u0) / ((u1 - u0) or 1)
            prof = (math.sin(math.pi * min(max(t, 0.0), 1.0)) ** 0.5) if taper else 1.0
            prof = lerp(1.0, max(prof, 0.12), taper)
            ws.append(width * prof * (1 + self.s.get("press", 0.14) * noise1(us[i] * 3.0, s)))
        Lp, Rp = [], []
        for i in range(n):
            a, b = pts[max(i - 1, 0)], pts[min(i + 1, n - 1)]
            tx, ty = b[0] - a[0], b[1] - a[1]
            tl = math.hypot(tx, ty) or 1
            nx, ny = -ty / tl * ws[i] / 2, tx / tl * ws[i] / 2
            Lp.append((pts[i][0] + nx, pts[i][1] + ny))
            Rp.append((pts[i][0] - nx, pts[i][1] - ny))
        c = self.c
        c.set_source_rgba(*color, alpha)
        c.set_fill_rule(cairo.FILL_RULE_WINDING)
        c.move_to(*Lp[0])
        for p in Lp[1:]:
            c.line_to(*p)
        for p in reversed(Rp):
            c.line_to(*p)
        c.close_path()
        c.fill()
        if not taper:  # round caps for the marker
            for i in (0, -1):
                c.arc(pts[i][0], pts[i][1], ws[i] / 2, 0, 2 * math.pi)
                c.fill()

    def stroke(self, pts, key, closed=False, wk=1.0, color=None, amp_k=1.0, alpha=1.0):
        if len(pts) < 2:
            return
        color = color or self.s["ink"]
        if self.ghost:
            color, wk = GHOST_INK, wk * 0.42
        for k, (wm, pass_alpha, extra_amp) in enumerate(self.s["passes"]):
            alpha_k = pass_alpha * alpha
            shaped, us, L = self._shape(pts, closed, key, k, amp_k=amp_k + extra_amp / max(self.s["amp"], 0.1),
                                        over_k=1.0 + 0.6 * k)
            if L < 1e-6:
                continue
            self._ribbon(shaped, us, self.w * wk * wm, key, k, color, alpha_k)

    def edges(self, polyline, key, closed=True, wk=1.0, color=None):
        """Box-like outlines: each edge its own stroke, overshooting the corners (sketchy)."""
        n = len(polyline)
        for i in range(n if closed else n - 1):
            self.stroke([polyline[i], polyline[(i + 1) % n]], f"{key}/e{i}", wk=wk, color=color)

    # -- fills --
    def poly(self, pts):
        c = self.c
        c.move_to(*pts[0])
        for p in pts[1:]:
            c.line_to(*p)
        c.close_path()

    def fill(self, pts, role, key):
        if len(pts) < 3:
            return
        c = self.c
        if self.ghost:  # pale, registered: occludes like paper, reads as line art
            col = ROLE.get(role, PAPER) if isinstance(role, str) else role
            if role == "ink":
                col = self.s["ink"]
            self.poly(pts)
            c.set_source_rgb(*[lerp(a, b, 0.84) for a, b in zip(col, PAPER, strict=False)])
            c.fill()
            return
        # opaque base so fills occlude what is behind them
        base = SKIN if role in ("skin", "white") else PAPER
        if not isinstance(role, str) and sum(role) / 3 < 0.5:  # dark colour: no paper gap from the offset fill
            base = role
        self.poly(pts)
        c.set_source_rgb(*base)
        c.fill()
        if role == "skin":
            return
        if role == "ink":  # hair, shoes, phone
            self.poly(pts)
            c.set_source_rgb(*self.s["ink"])
            c.fill()
            return
        col = ROLE[role] if isinstance(role, str) else role
        s = self.seed(key, 90)
        mx, my = (5 + 1.5 * hsign(s)) * self.px, (-4 + 1.5 * hsign(s + 1)) * self.px
        shaped, _, _ = self._shape(pts, True, key + "/fill", 91, amp_k=1.8, over_k=0)
        self.poly([(x + mx, y + my) for x, y in shaped])
        c.set_source_rgba(*col, 0.93)
        c.fill()

    def solid(self, pts, color=None):
        if len(pts) < 3:
            return
        self.poly(pts)
        self.c.set_source_rgb(*(color or self.s["ink"]))
        self.c.fill()
