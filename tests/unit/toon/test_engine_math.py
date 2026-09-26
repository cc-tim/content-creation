import math

from toon.cairo_compat import cairo
from toon.engine.camera import orbit
from toon.engine.mathx import V, e_back, hull, noise1, smooth


def test_cairo_loads_and_draws():
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4)
    c = cairo.Context(s)
    c.set_source_rgb(1, 0, 0)
    c.paint()
    assert bytes(s.get_data())[:4] == b"\x00\x00\xff\xff"


def test_orbit_centres_target_and_scales_focal_with_height():
    t = V(0.1, 2.0, 0.3)
    for w, h in ((1920, 1080), (1280, 720)):
        cam = orbit(-35, 12, 22, t, 3300, w, h)
        x, y = cam.p(t)
        assert abs(x - w / 2) < 1e-6 and abs(y - h / 2) < 1e-6
        assert math.isclose(cam.scale(t), 3300 * (h / 1080) / 22, rel_tol=1e-9)


def test_noise_is_deterministic_and_bounded():
    a = [noise1(x * 0.37, 1234) for x in range(200)]
    assert a == [noise1(x * 0.37, 1234) for x in range(200)]
    assert max(abs(v) for v in a) <= 1.0


def test_hull_drops_inner_point():
    assert sorted(hull([(0, 0), (1, 0), (1, 1), (0, 1), (0.5, 0.5)])) == [(0, 0), (0, 1), (1, 0), (1, 1)]


def test_easing_endpoints():
    for f in (smooth, e_back):
        assert abs(f(0.0)) < 1e-9 and abs(f(1.0) - 1) < 1e-9
