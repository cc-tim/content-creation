import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from PIL import Image, ImageChops, ImageDraw

from pipeline.composer.chart import _draw_header, _palette, _render_line
from pipeline.composer.chart_anim import (
    DEFAULT_REVEAL_FRACTION,
    DEFAULT_REVEAL_MAX_SEC,
    EASING,
    FPS,
    HOLD_TAIL_MIN_SEC,
    _animate_bar_frame,
    _animate_line_frame,
    _animate_stat_frame,
    _count_up_value,
    _progress_ease_out_cubic,
    _progress_linear,
    _resolve_easing,
    _resolve_reveal_duration,
    render_animated_chart,
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


# ── bar animated variant ───────────────────────────────────────────────────────
_BAR_VISUAL = {
    "type": "chart", "chart_type": "bar", "ai_background": False,
    "title": "Walker injury mechanisms", "source_credit": "AAP",
    "animate": {"enabled": True, "reveal_duration_sec": 4.0, "easing": "ease_out_cubic"},
    "data": {
        "x": ["stair falls", "tip-overs", "burns", "drowning"],
        "y": [74, 13, 6, 4],
        "y_unit": "%",
    },
}


def _bar_base_bg(width=W, height=H):
    pal = _palette({})
    bg = Image.new("RGB", (width, height), pal["paper"])
    draw = ImageDraw.Draw(bg)
    top = _draw_header(draw, _BAR_VISUAL, width, height, pal)
    return bg, pal, top


def test_animate_bar_frame_is_pure():
    base, pal, top = _bar_base_bg()
    a = _animate_bar_frame(0.5, _BAR_VISUAL, base, W, H, pal, top)
    b = _animate_bar_frame(0.5, _BAR_VISUAL, base, W, H, pal, top)
    diff = ImageChops.difference(a, b)
    assert diff.getbbox() is None


def test_golden_bar_progress_00():
    base, pal, top = _bar_base_bg()
    img = _animate_bar_frame(0.0, _BAR_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "bar_p00")


def test_golden_bar_progress_05():
    base, pal, top = _bar_base_bg()
    img = _animate_bar_frame(0.5, _BAR_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "bar_p05")


def test_golden_bar_progress_10():
    base, pal, top = _bar_base_bg()
    img = _animate_bar_frame(1.0, _BAR_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "bar_p10")


# ── stat_big_number animated variant ───────────────────────────────────────────
_STAT_VISUAL = {
    "type": "chart", "chart_type": "stat_big_number", "ai_background": False,
    "title": "Cumulative injuries", "source_credit": "AAP, 2014",
    "animate": {"enabled": True, "reveal_duration_sec": 3.0, "easing": "ease_out_cubic"},
    "data": {"value": "230,676", "unit": "children", "context": "1990-2014"},
}


def _stat_base_bg(width=W, height=H):
    pal = _palette({})
    bg = Image.new("RGB", (width, height), pal["paper"])
    draw = ImageDraw.Draw(bg)
    top = _draw_header(draw, _STAT_VISUAL, width, height, pal)
    return bg, pal, top


def test_animate_stat_frame_is_pure():
    base, pal, top = _stat_base_bg()
    a = _animate_stat_frame(0.5, _STAT_VISUAL, base, W, H, pal, top)
    b = _animate_stat_frame(0.5, _STAT_VISUAL, base, W, H, pal, top)
    diff = ImageChops.difference(a, b)
    assert diff.getbbox() is None


def test_golden_stat_progress_00():
    base, pal, top = _stat_base_bg()
    img = _animate_stat_frame(0.0, _STAT_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "stat_p00")


def test_golden_stat_progress_05():
    base, pal, top = _stat_base_bg()
    img = _animate_stat_frame(0.5, _STAT_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "stat_p05")


def test_golden_stat_progress_10():
    base, pal, top = _stat_base_bg()
    img = _animate_stat_frame(1.0, _STAT_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "stat_p10")


# ── Orchestrator (ffmpeg mocked; no encode in CI) ──────────────────────────────
def test_render_animated_chart_writes_frame_sequence_and_calls_ffmpeg(tmp_path):
    captured: dict[str, Any] = {}

    def fake_ffmpeg(cmd, timeout=600):
        idx = cmd.index("-i")
        pattern = cmd[idx + 1]
        frame_dir = Path(pattern).parent
        captured["frame_count"] = len(list(frame_dir.glob("frame_*.jpg")))
        captured["pattern"] = pattern
        captured["fps_arg"] = cmd[cmd.index("-framerate") + 1]
        Path(cmd[-1]).write_bytes(b"")
        return None

    duration = 4.0
    with patch("pipeline.composer.chart_anim.run_ffmpeg", side_effect=fake_ffmpeg) as ff:
        out = render_animated_chart(
            _LINE_VISUAL, duration_sec=duration, width=W, height=H,
            work_dir=tmp_path, scene_id="s_line", theme={},
        )

    assert ff.call_count == 1, "ffmpeg must be invoked exactly once per scene"
    assert captured["frame_count"] == int(duration * FPS)
    assert captured["pattern"].endswith("frame_%05d.jpg")
    assert captured["fps_arg"] == str(FPS)
    assert out == tmp_path / "s_line_visual.mp4"


def test_render_animated_chart_dispatches_to_correct_generator(tmp_path):
    called: list[str] = []

    def fake_ffmpeg(cmd, timeout=600):
        Path(cmd[-1]).write_bytes(b"")

    def wrap(real):
        def wrapped(*a, **k):
            called.append(real.__name__)
            return real(*a, **k)
        return wrapped

    from pipeline.composer import chart_anim as ca
    with patch("pipeline.composer.chart_anim.run_ffmpeg", side_effect=fake_ffmpeg), \
         patch("pipeline.composer.chart_anim._animate_line_frame",
               side_effect=wrap(ca._animate_line_frame)), \
         patch("pipeline.composer.chart_anim._animate_bar_frame",
               side_effect=wrap(ca._animate_bar_frame)), \
         patch("pipeline.composer.chart_anim._animate_stat_frame",
               side_effect=wrap(ca._animate_stat_frame)):
        render_animated_chart(_BAR_VISUAL, duration_sec=3.0, width=W, height=H,
                               work_dir=tmp_path / "a", scene_id="s_bar", theme={})

    assert "_animate_bar_frame" in called
    assert "_animate_line_frame" not in called
    assert "_animate_stat_frame" not in called


def test_render_animated_chart_holds_final_frame_after_reveal(tmp_path):
    saved_progresses: list[float] = []

    from pipeline.composer import chart_anim as ca
    real_line = ca._animate_line_frame

    def capturing_line(progress, *a, **k):
        saved_progresses.append(progress)
        return real_line(progress, *a, **k)

    def fake_ffmpeg(cmd, timeout=600):
        Path(cmd[-1]).write_bytes(b"")

    visual = {
        **_LINE_VISUAL,
        "animate": {"enabled": True, "reveal_duration_sec": 4.0, "easing": "linear"},
    }
    with patch("pipeline.composer.chart_anim.run_ffmpeg", side_effect=fake_ffmpeg), \
         patch("pipeline.composer.chart_anim._animate_line_frame",
               side_effect=capturing_line):
        render_animated_chart(visual, duration_sec=6.0, width=W, height=H,
                               work_dir=tmp_path, scene_id="s_h", theme={})

    # 6s @ 30fps = 180 total frames. 4s reveal @ 30fps = 120 reveal frames.
    # Orchestrator calls the generator once pre-loop (cache p=1.0) + (reveal_frames - 1)
    # in-loop calls; the remaining 60 hold-tail frames reuse the cached final frame.
    # Total generator calls must be <= reveal_frames (= 120) and strictly less
    # than total_frames (= 180) — that's the "hold-tail reuse" contract.
    assert 1.0 in saved_progresses, "pre-loop cache call (p=1.0) must occur"
    assert len(saved_progresses) <= 120, (
        f"generator called {len(saved_progresses)}x; expected <= 120 "
        f"(reveal_frames); hold-tail caching is not working"
    )
    assert len(saved_progresses) < 180, (
        "generator should NOT be called for every total frame — hold tail "
        "must reuse the cached final frame"
    )
