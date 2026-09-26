import numpy as np

from toon.cairo_compat import cairo
from toon.engine.camera import orbit
from toon.engine.head import hair_cap, hairline_local
from toon.engine.look import Look
from toon.engine.mathx import V
from toon.engine.order import character_parts, run
from toon.engine.pen import Pen
from toon.engine.rig import HIP_STAND, Pose, ik3, mix, placed

STAND = Pose(lean=0, head_tilt=0, typing=0, hand_l=(0.55, 1.02, 0.08), hand_r=(-0.55, 1.02, 0.08),
             foot_l=(0.25, 0.05, 0.05), foot_r=(-0.25, 0.05, 0.05))


def test_ik_reaches_and_clamps():
    s = V(0, 0, 0)
    e, h = ik3(s, V(0.5, 0, 0), 0.62, 0.56, V(0, 1, 0))
    assert np.allclose(h, V(0.5, 0, 0)) and abs(np.linalg.norm(e - s) - 0.62) < 1e-9
    _, h = ik3(s, V(5, 0, 0), 0.62, 0.56, V(0, 1, 0))
    assert np.linalg.norm(h - s) <= 0.62 + 0.56


def test_placed_rotates_targets_about_root():
    w = placed(Pose(hand_l=(0.5, 2.5, 1.0)), V(2, 1.4, 0), 90.0, V(0, 1.4, 0))
    assert np.allclose(w.hand_l, (3.0, 2.5, -0.5))


def test_mix_blends_continuous_and_switches_discrete():
    a, b = Pose(lean=0, eyes="dot"), Pose(lean=10, eyes="wide")
    assert mix(a, b, 0.4).lean == 4 and mix(a, b, 0.4).eyes == "dot"
    assert mix(a, b, 0.6).eyes == "wide"


def test_hairline_is_cached():
    cap = hair_cap((0.7, 0.3, -0.2))
    assert hairline_local(cap) is hairline_local(cap)


def _render(look: Look) -> bytes:
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 320, 320)
    c = cairo.Context(s)
    cam = orbit(20, 5, 60, V(0, 2.1, 0), 60 * 62, 320, 320)
    parts, _ = character_parts(Pen(c, 2, zoom=0.55), cam, look, STAND, HIP_STAND, 0.0, 0.0, HIP_STAND)
    run(parts.low + parts.high)
    return bytes(s.get_data())


def test_character_render_is_deterministic():
    look = Look(face={}, hair={}, body={})
    assert _render(look) == _render(look)


def test_looks_do_not_leak_between_characters():
    plain = Look(face={}, hair={}, body={})
    before = _render(plain)
    _render(Look(face={"glasses": False, "mane": {"color": (0.6, 0.4, 0.2)}}, hair={"none": True}, body={}))
    assert _render(plain) == before
