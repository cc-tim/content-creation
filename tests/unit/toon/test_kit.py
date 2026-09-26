from pathlib import Path

import numpy as np
import pytest

import toon
from toon.cairo_compat import cairo
from toon.engine.camera import orbit
from toon.engine.mathx import V
from toon.engine.pen import Pen
from toon.kit.graphics import anger_mark, bubble, bubble_layout, check_pill, speed_lines, x_card
from toon.kit.icons import ICONS, draw_icon
from toon.kit.props import idea_bulb, plate_stack
from toon.kit.sets import build_set

V0_ICONS = {"dishes", "bang", "bulb", "check", "cross", "laptop", "phone"}


def _canvas(w=480, h=270):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    c = cairo.Context(s)
    return s, c, Pen(c, 1, px=h / 1080), Pen(c, 1, px=h / 1080, ghost=True)


def _ink(s) -> int:
    return int((np.frombuffer(s.get_data(), np.uint8)[3::4] > 0).sum())


def test_icon_registry_has_the_v0_icons():
    assert V0_ICONS <= set(ICONS)


def test_bubble_layout_pins_the_dishes_bang_bubble():
    """Ruling R10: the [dishes, bang] bubble reproduces the tryout's hand-placed speech() exactly
    (330x170 box, SCN 280-302) -- dishes centred at (0.38w, 0.62h) with its native size 124 (at
    this box's reference height of 170), bang anchored off (0.80w, 0.52h) with the size the
    tryout's bar/dot geometry least-squares-fits onto `toon.kit.icons.bang`'s own center+size
    parameterisation."""
    w, h = 330.0, 170.0
    (dishes_c, dishes_size), (bang_c, bang_size) = bubble_layout(["dishes", "bang"], w, h)
    assert dishes_c == pytest.approx((0.38 * w, 0.62 * h))
    assert dishes_size == pytest.approx(124.0)
    assert bang_c == pytest.approx((0.80 * w, 0.52 * h))
    assert bang_size == pytest.approx(267 / 301 * h)


def test_bubble_layout_falls_back_to_even_spacing_for_unlisted_icons():
    w, h = 330.0, 170.0
    (c0, s0), (c1, s1) = bubble_layout(["check", "cross"], w, h)
    assert c0 == pytest.approx((w * (0.1 + 0.8 * 0.25), h * 0.55))
    assert c1 == pytest.approx((w * (0.1 + 0.8 * 0.75), h * 0.55))
    assert s0 == pytest.approx(s1) == pytest.approx(h * 0.6)


def test_unknown_icon_is_a_wordless_error():
    _, _, pen, _ = _canvas()
    with pytest.raises(ValueError, match="not an icon"):
        draw_icon(pen, "Dishes. Now.", (10, 10), 40, "k")


def test_engine_and_kit_draw_no_text():
    root = Path(toon.__file__).parent
    for f in [*root.glob("engine/*.py"), *root.glob("kit/*.py")]:
        src = f.read_text()
        assert "show_text" not in src and "text_path" not in src, f


@pytest.mark.parametrize("draw", [
    lambda p: bubble(p, (40, 40, 200, 110), (60, 200), ["dishes", "bang"]),
    lambda p: anger_mark(p, (100, 100), 30),
    lambda p: x_card(p, 150, 60, "bulb"),
    lambda p: check_pill(p, 150, 60, "laptop"),
    lambda p: speed_lines(p, (240, 135), 40),
])
def test_each_graphic_draws_ink(draw):
    s, _, pen, _ = _canvas()
    draw(pen)
    assert _ink(s) > 200


def test_bulb_out_differs_from_on_and_smokes():
    cam = orbit(0, 0, 60, V(0, 0, 0), 60 * 150, 480, 270)
    s1, _, p1, _ = _canvas()
    idea_bulb(p1, cam, V(0, 0, 0), 1.0, "on")
    s2, _, p2, _ = _canvas()
    idea_bulb(p2, cam, V(0, 0, 0), 0.0, "out", smoke_age=0.6)
    assert bytes(s1.get_data()) != bytes(s2.get_data())


def test_plate_stack_count_changes_ink():
    cam = orbit(-28, 13, 22, V(0.1, 2.5, 0.5), 3500, 480, 270)
    a, _, pa, _ = _canvas()
    plate_stack(pa, cam, 6)
    b, _, pb, _ = _canvas()
    plate_stack(pb, cam, 3)
    assert _ink(a) > _ink(b)


def test_set_layers():
    _, _, pen, gp = _canvas()
    cam = orbit(-35, 12, 22, V(0.2, 2.9, 0.2), 3300, 480, 270)
    office = build_set("office", pen, gp, cam, 0.0, door=0.0)
    assert (len(office.back), len(office.low), len(office.mid), len(office.high)) == (3, 5, 1, 2)
    kitchen = build_set("kitchen", pen, gp, cam, 0.0)
    assert (len(kitchen.back), len(kitchen.low), len(kitchen.mid), len(kitchen.high)) == (1, 0, 2, 0)
