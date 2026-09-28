from pathlib import Path

import pytest

from pipeline.composer import base
from pipeline.composer.overlay_rules import _TEXT_VISUALS
from pipeline.director.storyboard_validator import (
    _validate_scene,
    format_visual_decision_table,
    validate_storyboard,
    validation_errors,
    visual_decisions_for_storyboard,
)
from pipeline.errors import SceneRenderError
from pipeline.storyboard import Scene, Storyboard


def _scene(visual, narration="One. Two.", est=13.0):
    return Scene(id="s1", section="content", narration=narration, narration_est_sec=est, visual=visual)


def test_toon_is_a_visual_type_that_keeps_subtitles():
    assert "toon" in base.VISUAL_TYPES and "toon" not in _TEXT_VISUALS


def test_render_scene_dispatches_to_toon(tmp_path, monkeypatch):
    calls = {}

    def fake_clip(scene, bank, out, duration, width, height, workers=None):
        calls.update(id=scene.id, duration=duration, size=(width, height))
        Path(out).write_bytes(b"x")
        return Path(out)

    monkeypatch.setattr("toon.render.render_clip", fake_clip)
    out = base.render_scene({"id": "s1", "narration": "One.", "visual": {"type": "toon", "scene": "001-lioness-dishes"}},
                            13.0, "16:9", tmp_path)
    assert out.exists() and calls == {"id": "001-lioness-dishes", "duration": 13.0, "size": (1280, 720)}


def test_render_scene_toon_with_a_shorter_duration_cuts_instead_of_raising(tmp_path, monkeypatch):
    # R15: the render path must agree with the validator — a narration/duration shorter than
    # 001's last shot start (9.7s) is a cut, not a SceneRenderError (design spec §5).
    calls = {}

    def fake_clip(scene, bank, out, duration, width, height, workers=None):
        calls.update(id=scene.id, duration=duration, size=(width, height))
        Path(out).write_bytes(b"x")
        return Path(out)

    monkeypatch.setattr("toon.render.render_clip", fake_clip)
    out = base.render_scene({"id": "s1", "narration": "One.", "visual": {"type": "toon", "scene": "001-lioness-dishes"}},
                            8.0, "16:9", tmp_path)
    assert out.exists() and calls["duration"] == 8.0


def test_unknown_scene_is_a_scene_render_error_not_a_black_screen(tmp_path):
    with pytest.raises(SceneRenderError, match="toon"):
        base.render_scene({"id": "s1", "visual": {"type": "toon", "scene": "nope"}}, 5.0, "16:9", tmp_path)


def test_vertical_is_refused_in_v0(tmp_path):
    with pytest.raises(SceneRenderError, match="16:9"):
        base.render_scene({"id": "s1", "visual": {"type": "toon", "scene": "001-lioness-dishes"}}, 5.0, "9:16", tmp_path)


def test_validator_accepts_001_and_rejects_words(tmp_path):
    assert _validate_scene(_scene({"type": "toon", "scene": "001-lioness-dishes"}), tmp_path) == []
    bad = {"type": "toon", "cast": {"tim": "tim"}, "shots": [{
        "at": 0.0, "set": "office", "camera": "two_shot",
        "place": {"tim": {"spot": "desk_seat", "pose": "sit_typing"}},
        "beats": [{"at": 1.0, "show": {"bubble": ["Dishes. Now."], "from": "tim"}}]}]}
    (issue,) = _validate_scene(_scene(bad), tmp_path)
    assert issue.severity == "error" and "wordless" in issue.issue


def test_validator_warns_when_narration_is_shorter_than_the_scene(tmp_path):
    (issue,) = _validate_scene(_scene({"type": "toon", "scene": "001-lioness-dishes"}, est=8.0), tmp_path)
    assert issue.severity == "warn" and "cut" in issue.issue


def test_toon_warning_is_picked_up_by_the_warn_severity_collector(tmp_path):
    # R16: Severity = Literal["error", "warn"] (storyboard_validator.py:13), and
    # format_visual_decision_table collects warnings via `issue.get("severity") == "warn"`
    # (~line 165). A toon "warning" issue would silently vanish from that collection; "warn"
    # must actually be picked up end to end, not just satisfy _validate_toon's own unit test.
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="One. Two.", narration_est_sec=8.0,
              visual={"type": "toon", "scene": "001-lioness-dishes"}),
    ])

    [decision] = visual_decisions_for_storyboard(sb, tmp_path)
    assert decision["issues"][0]["severity"] == "warn"

    table = format_visual_decision_table(sb, tmp_path)
    assert "Validation warnings: 1" in table


def test_validator_refuses_toon_in_a_vertical_storyboard(tmp_path):
    # compose always renders scene visuals as 16:9 and _fit_to_canvas would silently
    # center-crop the 16:9 toon clip to 9:16 — the review gate must block it instead.
    def sb(aspect):
        return Storyboard(aspect_ratio=aspect, scenes=[
            Scene(id="s1", section="content", narration="One. Two.", narration_est_sec=13.0,
                  visual={"type": "toon", "scene": "001-lioness-dishes"}),
        ])

    errors = validation_errors(validate_storyboard(sb("9:16"), tmp_path))
    assert [(e.scene_id, e.field) for e in errors] == [("s1", "visual.type")]
    assert "16:9" in errors[0].issue and "9:16" in errors[0].issue
    assert validate_storyboard(sb("16:9"), tmp_path) == []


def test_render_scene_toon_missing_ffmpeg_is_a_scene_render_error(tmp_path, monkeypatch):
    """render_clip launches ffmpeg via subprocess.Popen before its own try block, so a missing
    ffmpeg binary raises a bare FileNotFoundError rather than ToonRenderError. The adapter's
    `except Exception` must still catch it and surface a SceneRenderError, never a black screen.
    """

    def fake_clip(scene, bank, out, duration, width, height, workers=None):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr("toon.render.render_clip", fake_clip)
    with pytest.raises(SceneRenderError, match="toon"):
        base.render_scene({"id": "s1", "visual": {"type": "toon", "scene": "001-lioness-dishes"}}, 13.0, "16:9", tmp_path)
