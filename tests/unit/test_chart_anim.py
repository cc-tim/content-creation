import os
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

from pipeline.composer.chart import _draw_header, _palette, _render_line
from pipeline.composer.chart_anim import (
    DEFAULT_REVEAL_FRACTION,
    DEFAULT_REVEAL_MAX_SEC,
    EASING,
    HOLD_TAIL_MIN_SEC,
    _animate_line_frame,
    _count_up_value,
    _progress_ease_out_cubic,
    _progress_linear,
    _resolve_easing,
    _resolve_reveal_duration,
)

_GOLDEN_ANIM = Path(__file__).parent.parent / "fixtures" / "chart_anim" / "golden"
W, H = 1280, 720


# ── Easing ─────────────────────────────────────────────────────────────────────
def test_progress_linear_endpoints():
    assert _progress_linear(0.0) == 0.0
    assert _progress_linear(1.0) == 1.0


def test_progress_ease_out_cubic_endpoints():
    assert _progress_ease_out_cubic(0.0) == 0.0
    assert _progress_ease_out_cubic(1.0) == 1.0


def test_progress_ease_out_cubic_is_front_loaded():
    assert _progress_ease_out_cubic(0.5) > 0.5


def test_easing_registry_contains_both():
    assert set(EASING.keys()) == {"linear", "ease_out_cubic"}


# ── _resolve_easing ────────────────────────────────────────────────────────────
def test_resolve_easing_defaults_to_ease_out_cubic():
    fn = _resolve_easing({"animate": {"enabled": True}})
    assert fn(0.5) > 0.5


def test_resolve_easing_explicit_linear():
    fn = _resolve_easing({"animate": {"enabled": True, "easing": "linear"}})
    assert fn(0.5) == 0.5


def test_resolve_easing_rejects_unknown():
    with pytest.raises(ValueError, match="unknown easing"):
        _resolve_easing({"animate": {"enabled": True, "easing": "bounce"}})


# ── _resolve_reveal_duration ───────────────────────────────────────────────────
def test_resolve_reveal_duration_uses_explicit_value():
    visual = {"animate": {"enabled": True, "reveal_duration_sec": 3.0}}
    assert _resolve_reveal_duration(visual, duration_sec=8.0) == 3.0


def test_resolve_reveal_duration_defaults_to_fraction_of_scene():
    visual = {"animate": {"enabled": True}}
    assert _resolve_reveal_duration(visual, duration_sec=8.0) == pytest.approx(4.8)


def test_resolve_reveal_duration_caps_at_default_max():
    visual = {"animate": {"enabled": True}}
    assert _resolve_reveal_duration(visual, duration_sec=20.0) == DEFAULT_REVEAL_MAX_SEC


# ── _count_up_value ────────────────────────────────────────────────────────────
def test_count_up_value_plain_integer():
    text, ok = _count_up_value("42", progress=0.5)
    assert ok is True
    assert text == "21"


def test_count_up_value_preserves_thousands_separator():
    text, ok = _count_up_value("230,676", progress=1.0)
    assert ok is True
    assert text == "230,676"


def test_count_up_value_progress_zero_is_zero_formatted():
    text, ok = _count_up_value("230,676", progress=0.0)
    assert ok is True
    assert text == "000,000"


def test_count_up_value_with_units_preserves_units():
    text, ok = _count_up_value("$1.1B", progress=1.0)
    assert ok is True
    assert text == "$1.1B"


def test_count_up_value_no_digits_returns_unparsed_flag():
    text, ok = _count_up_value("N/A", progress=0.5)
    assert ok is False
    assert text == "N/A"


# ── Module constants ───────────────────────────────────────────────────────────
def test_hold_tail_default():
    assert HOLD_TAIL_MIN_SEC == 0.5


def test_default_reveal_constants():
    assert DEFAULT_REVEAL_FRACTION == 0.6
    assert DEFAULT_REVEAL_MAX_SEC == 5.0


# ── Frame-generator purity + sampled-frame goldens ─────────────────────────────
_LINE_VISUAL = {
    "type": "chart", "chart_type": "line", "ai_background": False,
    "title": "US ER visits per year", "source_credit": "AAP, 1990-2014",
    "animate": {"enabled": True, "reveal_duration_sec": 4.0, "easing": "ease_out_cubic"},
    "data": {
        "points": [
            {"x": 1990, "y": 20650},
            {"x": 1999, "y": 8800},
            {"x": 2007, "y": 3200},
            {"x": 2014, "y": 2001},
        ],
        "markers": [
            {"x": 1982, "label": "First medical study"},
            {"x": 1995, "label": "Voluntary standard"},
            {"x": 1997, "label": "ASTM F977"},
            {"x": 2001, "label": "AAP ban call"},
            {"x": 2004, "label": "Canada bans"},
            {"x": 2010, "label": "CPSC mandatory"},
        ],
    },
}


def _line_base_bg(width=W, height=H):
    """Build the base bg the orchestrator hands to the frame generator: paper +
    header drawn. The frame generator paints the data layer on a copy.
    """
    pal = _palette({})
    bg = Image.new("RGB", (width, height), pal["paper"])
    draw = ImageDraw.Draw(bg)
    top = _draw_header(draw, _LINE_VISUAL, width, height, pal)
    _render_line(draw, _LINE_VISUAL, width, height, pal, top)
    return bg, pal, top


def _assert_anim_golden(image, name: str) -> None:
    golden = _GOLDEN_ANIM / f"{name}.png"
    if os.environ.get("UPDATE_GOLDENS"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        image.save(golden)
        return
    assert golden.exists(), f"missing golden {golden}; run with UPDATE_GOLDENS=1"
    diff = ImageChops.difference(image, Image.open(golden).convert("RGB"))
    assert diff.getbbox() is None, f"{name} render drifted from golden"


def test_animate_line_frame_is_pure():
    base, pal, top = _line_base_bg()
    a = _animate_line_frame(0.5, _LINE_VISUAL, base, W, H, pal, top)
    b = _animate_line_frame(0.5, _LINE_VISUAL, base, W, H, pal, top)
    diff = ImageChops.difference(a, b)
    assert diff.getbbox() is None, "line frame generator is non-deterministic"


def test_golden_line_progress_00():
    base, pal, top = _line_base_bg()
    img = _animate_line_frame(0.0, _LINE_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "line_p00")


def test_golden_line_progress_05():
    base, pal, top = _line_base_bg()
    img = _animate_line_frame(0.5, _LINE_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "line_p05")


def test_golden_line_progress_10():
    base, pal, top = _line_base_bg()
    img = _animate_line_frame(1.0, _LINE_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "line_p10")
