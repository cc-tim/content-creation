import os
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image, ImageChops

from pipeline.composer.chart import _validate_chart, render_chart

_GOLDEN = Path(__file__).parent.parent / "fixtures" / "chart" / "golden"
W, H = 1280, 720


# ── Validation (E5 precursor) ───────────────────────────────────────────────────
def _v(**kw):
    return {"type": "chart", **kw}


def test_validate_rejects_missing_chart_type():
    with pytest.raises(ValueError, match="chart_type"):
        _validate_chart(_v(data={"value": "5"}), "s1")


def test_validate_rejects_unknown_chart_type():
    with pytest.raises(ValueError, match="unknown chart_type"):
        _validate_chart(_v(chart_type="pie", data={"value": "5"}), "s1")


def test_validate_rejects_missing_data():
    with pytest.raises(ValueError, match="data"):
        _validate_chart(_v(chart_type="stat_big_number"), "s1")


def test_validate_rejects_stat_value_over_8_chars():
    with pytest.raises(ValueError, match="8 chars"):
        _validate_chart(
            _v(chart_type="stat_big_number", data={"value": "123456789", "unit": "x"}),
            "s1",
        )


def test_validate_rejects_bar_shape_mismatch():
    with pytest.raises(ValueError, match="bar"):
        _validate_chart(_v(chart_type="bar", data={"x": ["a", "b"], "y": [1]}), "s1")


def test_validate_rejects_comparison_missing_side():
    with pytest.raises(ValueError, match="comparison"):
        _validate_chart(
            _v(chart_type="comparison", data={"left": {"label": "a", "value": "1"}}),
            "s1",
        )


def test_validate_accepts_valid_stat():
    _validate_chart(
        _v(chart_type="stat_big_number", data={"value": "230,676", "unit": "children"}),
        "s1",
    )


# ── Golden-PNG helpers ───────────────────────────────────────────────────────────
def _render_png(visual, tmp_path, scene_id):
    """Render a chart to PNG with the mp4 step mocked out; return the PNG path."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    with patch("pipeline.composer.chart.image_to_video") as itv:
        itv.side_effect = lambda png, out, *a, **k: out
        render_chart(visual, 8.0, W, H, tmp_path, scene_id, theme={})
    png = tmp_path / f"{scene_id}_chart.png"
    assert png.exists()
    return png


def _assert_golden(png_path, name):
    golden = _GOLDEN / f"{name}.png"
    if os.environ.get("UPDATE_GOLDENS"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        Image.open(png_path).save(golden)
        return
    assert golden.exists(), f"missing golden {golden}; run with UPDATE_GOLDENS=1"
    diff = ImageChops.difference(
        Image.open(png_path).convert("RGB"), Image.open(golden).convert("RGB")
    )
    assert diff.getbbox() is None, f"{name} render drifted from golden"


# Real baby-walker datapoints (the demand this sprint answers).
_STAT = {
    "type": "chart", "chart_type": "stat_big_number", "ai_background": False,
    "title": "Cumulative injuries", "source_credit": "AAP, 2014",
    "data": {"value": "230,676", "unit": "children", "context": "1990–2014"},
}
_PROP = {
    "type": "chart", "chart_type": "proportion_blocks", "ai_background": False,
    "title": "Where walker injuries happen", "source_credit": "AAP",
    "data": {"label": "74% stair falls", "ratio": 0.74,
             "secondary_label": "26% other", "secondary_ratio": 0.26},
}
_TIMELINE = {
    "type": "chart", "chart_type": "timeline", "ai_background": False,
    "title": "Two decades of walker injuries",
    "data": [{"year": 1990, "label": "20,650 ER visits"},
             {"year": 2001, "label": "AAP ban call"},
             {"year": 2004, "label": "Canada bans"},
             {"year": 2014, "label": "230k cumulative"}],
}
_BAR = {
    "type": "chart", "chart_type": "bar", "ai_background": False,
    "title": "Walker injury mechanisms", "source_credit": "AAP",
    "data": {"x": ["stair falls", "tip-overs", "burns", "drowning"],
             "y": [74, 13, 6, 4], "y_unit": "%"},
}
_COMPARISON = {
    "type": "chart", "chart_type": "comparison", "ai_background": False,
    "title": "Speed vs. reaction",
    "data": {"left": {"label": "Sit-in walker", "value": "3 ft/s"},
             "right": {"label": "Adult reaction", "value": "0.7 s"}},
}


# ── Determinism smoke test (run before trusting goldens) ─────────────────────────
def test_render_is_deterministic(tmp_path):
    a = _render_png(_STAT, tmp_path / "a", "s1")
    b = _render_png(_STAT, tmp_path / "b", "s1")
    diff = ImageChops.difference(Image.open(a).convert("RGB"), Image.open(b).convert("RGB"))
    assert diff.getbbox() is None, "chart render is non-deterministic on this machine"


# ── Golden tests, one per chart_type ─────────────────────────────────────────────
def test_golden_stat_big_number(tmp_path):
    _assert_golden(_render_png(_STAT, tmp_path, "s13"), "stat_big_number")


def test_golden_proportion_blocks(tmp_path):
    _assert_golden(_render_png(_PROP, tmp_path, "s12"), "proportion_blocks")


def test_golden_timeline(tmp_path):
    _assert_golden(_render_png(_TIMELINE, tmp_path, "s10"), "timeline")


def test_golden_bar(tmp_path):
    _assert_golden(_render_png(_BAR, tmp_path, "s11"), "bar")


def test_golden_comparison(tmp_path):
    _assert_golden(_render_png(_COMPARISON, tmp_path, "s14"), "comparison")


# ── Dispatch + AI-background path ─────────────────────────────────────────────────
def test_render_scene_dispatches_chart(tmp_path):
    from pipeline.composer.base import render_scene

    with patch("pipeline.composer.chart.image_to_video") as itv:
        itv.side_effect = lambda png, out, *a, **k: out
        out = render_scene(
            scene={"id": "s1", "visual": {"type": "chart", "chart_type": "stat_big_number",
                    "ai_background": False, "data": {"value": "42", "unit": "x"}}},
            duration_sec=5.0, aspect_ratio="16:9", work_dir=tmp_path, theme={},
        )
    assert out.name == "s1_visual.mp4"


# ── line (Sprint 2 static substrate for animation) ────────────────────────────
_LINE = {
    "type": "chart", "chart_type": "line", "ai_background": False,
    "title": "US ER visits per year", "source_credit": "AAP, 1990–2014",
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
        "x_axis": "year", "y_axis": "ER visits",
    },
}


def test_validate_rejects_line_missing_points():
    with pytest.raises(ValueError, match="line"):
        _validate_chart(_v(chart_type="line", data={"markers": []}), "s1")


def test_validate_rejects_line_marker_missing_x():
    with pytest.raises(ValueError, match="marker"):
        _validate_chart(
            _v(
                chart_type="line",
                data={
                    "points": [{"x": 1990, "y": 1}, {"x": 2014, "y": 1}],
                    "markers": [{"label": "no x given"}],
                },
            ),
            "s1",
        )


def test_validate_accepts_valid_line():
    _validate_chart(_LINE, "s1")


def test_validate_rejects_reveal_duration_over_limit():
    with pytest.raises(ValueError, match="reveal_duration_sec"):
        _validate_chart(
            _v(chart_type="line", animate={"enabled": True, "reveal_duration_sec": 6.0},
                data={"points": [{"x": 1, "y": 1}, {"x": 2, "y": 2}]}),
            "s1", duration_sec=5.0,
        )


def test_validate_rejects_unknown_easing():
    with pytest.raises(ValueError, match="unknown easing"):
        _validate_chart(
            _v(chart_type="line",
                animate={"enabled": True, "easing": "bounce"},
                data={"points": [{"x": 1, "y": 1}, {"x": 2, "y": 2}]}),
            "s1", duration_sec=10.0,
        )


def test_validate_rejects_animated_variant_not_implemented():
    with pytest.raises(ValueError, match="animated variant"):
        _validate_chart(
            _v(chart_type="proportion_blocks",
                animate={"enabled": True},
                data={"ratio": 0.5}),
            "s1", duration_sec=5.0,
        )


def test_validate_passes_static_without_animate_block():
    _validate_chart(
        _v(chart_type="line",
            data={"points": [{"x": 1, "y": 1}, {"x": 2, "y": 2}]}),
        "s1",
    )


def test_golden_line(tmp_path):
    _assert_golden(_render_png(_LINE, tmp_path, "s_line"), "line")


def test_ai_background_path_calls_provider(tmp_path):
    def fake_chain(providers, prompt, out_path, size):
        Image.new("RGB", (64, 64), (200, 180, 150)).save(out_path)

    with patch("pipeline.composer.chart.try_chain", side_effect=fake_chain) as fc, \
         patch("pipeline.composer.chart.image_to_video") as itv:
        itv.side_effect = lambda png, out, *a, **k: out
        render_chart(
            {"type": "chart", "chart_type": "stat_big_number", "ai_background": True,
             "data": {"value": "42", "unit": "x"}},
            5.0, W, H, tmp_path, "s2", theme={"image_style": "warm sepia"},
        )
    fc.assert_called_once()
    assert (tmp_path / "s2_chart.png").exists()


# ── validate_chart_visual (list-returning, Sprint 4 Task 1) ──────────────────────
def test_validate_chart_visual_returns_empty_list_for_valid_input():
    from pipeline.composer.chart import validate_chart_visual

    visual = {
        "type": "chart",
        "chart_type": "stat_big_number",
        "data": {"value": "230,676"},
    }
    issues = validate_chart_visual(visual, "s1")
    assert issues == []


def test_validate_chart_visual_returns_all_issues_not_just_first():
    from pipeline.composer.chart import validate_chart_visual

    # Two independent issues: too-long stat value AND animate on unsupported variant
    visual = {
        "type": "chart",
        "chart_type": "stat_big_number",
        "data": {"value": "12345678901234"},  # > 8 chars
        "animate": {"enabled": True, "easing": "bogus_easing"},
    }
    issues = validate_chart_visual(visual, "s1", duration_sec=10.0)
    assert len(issues) >= 2
    assert any("> 8 chars" in i for i in issues)
    assert any("easing" in i for i in issues)


def test_validate_chart_visual_returns_issue_strings_not_raises():
    from pipeline.composer.chart import validate_chart_visual

    visual = {"type": "chart"}  # missing chart_type
    # Must NOT raise
    issues = validate_chart_visual(visual, "s1")
    assert len(issues) == 1
    assert "chart_type" in issues[0]
