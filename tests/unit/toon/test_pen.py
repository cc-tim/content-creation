import numpy as np

from toon.cairo_compat import cairo
from toon.engine.palette import GHOST_INK, PAPER
from toon.engine.paper import composite
from toon.engine.pen import LINE_A, Pen


def _surface(w=400, h=300):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    return s, cairo.Context(s)


def _stroke(boil=3, px=1.0, ghost=False):
    s, c = _surface()
    Pen(c, boil, px=px, ghost=ghost).stroke([(40, 150), (360, 140)], "line")
    return bytes(s.get_data())


def test_same_key_and_boil_is_byte_identical():
    assert _stroke(boil=3) == _stroke(boil=3)


def test_boil_changes_the_line():
    assert _stroke(boil=3) != _stroke(boil=4)


def test_line_width_scales_linearly_with_px():
    s, c = _surface()
    assert Pen(c, 0, zoom=1.0, px=1.0).w == LINE_A["w"]
    assert abs(Pen(c, 0, zoom=1.0, px=2 / 3).w - LINE_A["w"] * 2 / 3) < 1e-12


def test_ghost_pen_never_draws_dark_ink():
    s, c = _surface()
    Pen(c, 1, ghost=True).stroke([(40, 150), (360, 140)], "g")
    a = np.frombuffer(s.get_data(), np.uint8).reshape(300, 400, 4)
    opaque = a[a[..., 3] == 255][:, :3]  # BGRA, premultiplied (opaque → exact colour)
    assert opaque.size and opaque.min() >= int(min(GHOST_INK) * 255) - 3


def test_composite_blank_is_paper_and_deterministic():
    s, _ = _surface(64, 36)
    a = composite(s, 64, 36, 0.10)
    b = composite(s, 64, 36, 0.10)
    assert a.shape == (36, 64, 4) and a.dtype == np.uint8 and (a[..., 3] == 255).all()
    assert np.array_equal(a, b)
    rgb = a[..., [2, 1, 0]].reshape(-1, 3)
    assert (rgb <= np.array(PAPER) * 255 + 1).all() and (rgb >= np.array(PAPER) * 255 * 0.94).all()


# -- boil modes (Task 9b): full (today's), soft (default: no-boil drawing + per-drawing shimmer),
# -- still (no-boil drawing, no shimmer) --

def test_pen_defaults_to_full_mode_and_default_shimmer():
    s, c = _surface()
    p = Pen(c, 0)
    assert p.mode == "full"
    assert p.shimmer == 0.3


def _closed_stroke(boil, mode, shimmer=0.3):
    s, c = _surface()
    Pen(c, boil, mode=mode, shimmer=shimmer).stroke(
        [(40, 60), (360, 90), (300, 260), (80, 230)], "loop", closed=True)
    return np.frombuffer(bytes(s.get_data()), np.uint8).astype(np.int16)


def _mean_abs_diff(a, b):
    return float(np.abs(a - b).mean())


def test_still_mode_ignores_boil():
    assert np.array_equal(_closed_stroke(0, "still"), _closed_stroke(5, "still"))


def test_full_mode_boil_changes_the_line_unchanged_from_today():
    assert not np.array_equal(_closed_stroke(0, "full"), _closed_stroke(5, "full"))


def test_soft_mode_shimmers_less_than_full_boil():
    full_diff = _mean_abs_diff(_closed_stroke(0, "full"), _closed_stroke(5, "full"))
    soft_diff = _mean_abs_diff(_closed_stroke(0, "soft"), _closed_stroke(5, "soft"))
    assert 0 < soft_diff < full_diff
