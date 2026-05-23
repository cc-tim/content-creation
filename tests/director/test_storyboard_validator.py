from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from pipeline.storyboard import Scene, Storyboard


def _scene(scene_id: str, visual: dict) -> Scene:
    return Scene(
        id=scene_id,
        section="hook",
        narration="test narration",
        narration_est_sec=5,
        visual=visual,
    )


def _errors(issues: list[object]) -> list[object]:
    return [issue for issue in issues if issue.severity == "error"]


def _noise_image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.effect_noise((96, 96), 80).convert("RGB").save(path)
    return path


def test_article_image_path_must_exist(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {"type": "article_image", "path": "source/missing.jpg"}),
    ])

    issues = validate_storyboard(sb, tmp_path)

    assert any(
        issue.severity == "error"
        and issue.scene_id == "s1"
        and issue.field == "visual.path"
        and "not found" in issue.issue
        for issue in issues
    )


def test_article_image_rejects_non_image_magic_bytes(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    bad = tmp_path / "source" / "image.jpg"
    bad.parent.mkdir(parents=True)
    bad.write_text("<html>not an image</html>", encoding="utf-8")
    sb = Storyboard(scenes=[
        _scene("s1", {"type": "article_image", "path": "source/image.jpg"}),
    ])

    issues = validate_storyboard(sb, tmp_path)

    assert any(
        issue.severity == "error"
        and issue.field == "visual.path"
        and "valid image" in issue.issue
        for issue in issues
    )


def test_article_image_accepts_project_relative_real_image(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    _noise_image(tmp_path / "source" / "image.png")
    sb = Storyboard(scenes=[
        _scene("s1", {"type": "image", "path": "source/image.png"}),
    ])

    issues = validate_storyboard(sb, tmp_path)

    assert _errors(issues) == []


def test_slide_requires_renderable_content_but_accepts_rich_slide_shape(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {"type": "slide", "title": "Title", "bullets": ["One"]}),
        _scene("s2", {"type": "slide", "text": "Quoted line", "layout": "quote"}),
        _scene("s3", {"type": "slide", "background": "#111111"}),
    ])

    issues = validate_storyboard(sb, tmp_path)

    assert not any(issue.scene_id == "s1" and issue.severity == "error" for issue in issues)
    assert not any(issue.scene_id == "s2" and issue.severity == "error" for issue in issues)
    assert any(
        issue.scene_id == "s3"
        and issue.severity == "error"
        and issue.field == "visual"
        for issue in issues
    )


def test_generated_image_style_words_are_warnings_not_blockers(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene(
            "s1",
            {
                "type": "generated_image",
                "prompt": "warm watercolor sketch of a parent kneeling beside a toddler",
            },
        ),
    ])

    issues = validate_storyboard(sb, tmp_path)

    assert _errors(issues) == []
    assert any(
        issue.severity == "warn"
        and issue.scene_id == "s1"
        and issue.field == "visual.prompt"
        and "style" in issue.issue
        for issue in issues
    )


def test_clip_timestamps_must_be_numeric_and_ordered(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {"type": "clip", "source": "primary", "start_sec": 10, "end_sec": 8}),
        _scene("s2", {"type": "still_frame", "source": "primary", "timestamp_sec": "bad"}),
    ])

    issues = validate_storyboard(sb, tmp_path)

    assert any(issue.scene_id == "s1" and issue.field == "visual.end_sec" for issue in issues)
    assert any(issue.scene_id == "s2" and issue.field == "visual.timestamp_sec" for issue in issues)


def test_clip_accepts_existing_file_path_without_primary_source(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    clip = tmp_path / "assets" / "clip.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"fake video")
    sb = Storyboard(scenes=[
        _scene("s1", {"type": "clip", "path": "assets/clip.mp4", "start_sec": 0, "end_sec": 1}),
    ])

    issues = validate_storyboard(sb, tmp_path)

    assert _errors(issues) == []


def test_scene_filter_validates_only_requested_scene(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {"type": "unknown_type"}),
        _scene("s2", {"type": "text_card", "text": "Valid text"}),
    ])

    assert _errors(validate_storyboard(sb, tmp_path, scene_ids={"s2"})) == []


def test_visual_decisions_carry_confidence_rationale_and_validation(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import visual_decisions_for_storyboard

    sb = Storyboard(scenes=[
        _scene(
            "s1",
            {
                "type": "text_card",
                "text": "",
                "confidence": "low",
                "rationale": "No source image is available.",
            },
        ),
    ])

    [decision] = visual_decisions_for_storyboard(sb, tmp_path)

    assert decision["scene_id"] == "s1"
    assert decision["visual_type"] == "text_card"
    assert decision["confidence"] == "low"
    assert decision["rationale"] == "No source image is available."
    assert decision["issues"][0]["severity"] == "error"


def test_validation_exception_formats_errors(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import raise_for_validation_errors

    sb = Storyboard(scenes=[
        _scene("s1", {"type": "definitely_not_supported"}),
    ])

    with pytest.raises(ValueError, match="s1 visual.type"):
        raise_for_validation_errors(sb, tmp_path)


# ── chart visual: schema validation ────────────────────────────────────────


def test_chart_missing_chart_type_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[_scene("s1", {"type": "chart"})])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("chart_type" in i.issue for i in errs)
    assert all(i.scene_id == "s1" for i in errs)


def test_chart_unknown_chart_type_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[_scene("s1", {"type": "chart", "chart_type": "lne"})])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("unknown chart_type" in i.issue and "lne" in i.issue for i in errs)


def test_chart_missing_data_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {"type": "chart", "chart_type": "bar"}),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("missing 'data'" in i.issue for i in errs)


def test_chart_stat_big_number_value_too_long_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "stat_big_number",
            "data": {"value": "12,345,678,901"},
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("> 8 chars" in i.issue for i in errs)


def test_chart_bar_uneven_xy_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "bar",
            "data": {"x": ["a", "b"], "y": [1]},
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("equal-length" in i.issue for i in errs)


def test_chart_comparison_missing_side_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "comparison",
            "data": {"left": {"label": "L", "value": "1"}},  # right missing
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("right" in i.issue and "label" in i.issue for i in errs)


def test_chart_line_malformed_points_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "line",
            "data": {"points": [{"x": 1990}]},  # missing y
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("points[0] must be {x, y}" in i.issue for i in errs)


def test_chart_line_malformed_markers_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "line",
            "data": {
                "points": [{"x": 1990, "y": 100}, {"x": 2000, "y": 50}],
                "markers": [{"label": "no x"}],  # missing x
            },
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("marker[0]" in i.issue for i in errs)


def test_chart_animate_unsupported_variant_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "timeline",
            "data": [{"year": 1990, "label": "a"}],
            "animate": {"enabled": True},
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("no animated" in i.issue for i in errs)


def test_chart_animate_unknown_easing_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "bar",
            "data": {"x": ["a"], "y": [1]},
            "animate": {"enabled": True, "easing": "bouncy"},
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any("unknown easing" in i.issue and "bouncy" in i.issue for i in errs)


def test_chart_animate_reveal_exceeds_duration_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    # Scene est duration = 5s; reveal_duration_sec = 6.0s > 5 - 0.5 = 4.5
    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "bar",
            "data": {"x": ["a"], "y": [1]},
            "animate": {"enabled": True, "reveal_duration_sec": 6.0},
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any(
        "reveal_duration_sec=6.0" in i.issue and "hold_tail" in i.issue
        for i in errs
    )


def test_chart_valid_returns_no_issues(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {
            "type": "chart",
            "chart_type": "line",
            "data": {
                "points": [{"x": 1990, "y": 100}, {"x": 2000, "y": 50}],
                "markers": [{"x": 1995, "label": "regulation"}],
            },
            "animate": {"enabled": True, "reveal_duration_sec": 3.0},
        }),
    ])
    issues = validate_storyboard(sb, tmp_path)
    assert _errors(issues) == []


# ── existing-branch smoke tests (lock current behavior) ────────────────────


def test_rich_slide_empty_text_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[_scene("s1", {"type": "rich_slide"})])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any(i.field == "visual.text" for i in errs)


def test_text_card_empty_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[_scene("s1", {"type": "text_card", "text": ""})])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any(i.field == "visual.text" for i in errs)


def test_still_frame_missing_source_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[
        _scene("s1", {"type": "still_frame", "timestamp_sec": 1.0}),
    ])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any(i.field == "visual.source" for i in errs)


def test_namecard_missing_name_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[_scene("s1", {"type": "namecard"})])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any(i.field == "visual.name" for i in errs)


def test_map_missing_query_is_error(tmp_path: Path) -> None:
    from pipeline.director.storyboard_validator import validate_storyboard

    sb = Storyboard(scenes=[_scene("s1", {"type": "map"})])
    issues = validate_storyboard(sb, tmp_path)
    errs = _errors(issues)
    assert any(i.field == "visual.query" for i in errs)
