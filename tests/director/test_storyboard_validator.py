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
