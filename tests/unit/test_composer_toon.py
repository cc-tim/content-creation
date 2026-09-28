from pathlib import Path

import pytest

from pipeline.composer import base
from pipeline.composer.overlay_rules import _TEXT_VISUALS
from pipeline.director.storyboard_validator import _validate_scene
from pipeline.errors import SceneRenderError
from pipeline.storyboard import Scene


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
    assert issue.severity == "warning" and "cut" in issue.issue


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
