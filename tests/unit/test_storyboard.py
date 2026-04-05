from pathlib import Path

from pipeline.storyboard import Scene, Storyboard


def test_storyboard_load_from_fixture():
    path = Path(__file__).parent.parent / "fixtures" / "sample_storyboard.json"
    sb = Storyboard.load(path)
    assert sb.version == 1
    assert sb.format == "standard"
    assert sb.aspect_ratio == "16:9"
    assert len(sb.scenes) == 3
    assert sb.scenes[0].id == "s1"
    assert sb.scenes[0].section == "hook"
    assert sb.scenes[1].visual["type"] == "map"


def test_storyboard_round_trip(tmp_path):
    path = Path(__file__).parent.parent / "fixtures" / "sample_storyboard.json"
    sb = Storyboard.load(path)
    out = tmp_path / "storyboard.json"
    sb.save(out)
    loaded = Storyboard.load(out)
    assert len(loaded.scenes) == len(sb.scenes)
    assert loaded.scenes[0].narration == sb.scenes[0].narration
    assert loaded.aspect_ratio == sb.aspect_ratio


def test_derive_script():
    sb = Storyboard(
        scenes=[
            Scene(
                id="s1",
                section="hook",
                narration="第一句旁白。",
                narration_est_sec=5,
                pause_after_sec=2,
            ),
            Scene(id="s2", section="context", narration="第二句旁白。", narration_est_sec=8),
        ]
    )
    script = sb.derive_script()
    assert "[HOOK]" in script
    assert "[CONTEXT]" in script
    assert "第一句旁白。" in script
    assert "第二句旁白。" in script
    assert "[PAUSE:2s]" in script
    # Should NOT contain visual or overlay data
    assert "clip" not in script.lower()
    assert "overlay" not in script.lower()


def test_swap_visual():
    sb = Storyboard(
        scenes=[
            Scene(
                id="s1",
                section="hook",
                narration="test",
                narration_est_sec=5,
                visual={"type": "clip", "source": "primary", "start_sec": 0, "end_sec": 15},
            ),
        ]
    )
    new_visual = {
        "type": "generated_image",
        "prompt": "chase scene",
        "style": "cinematic",
    }
    result = sb.swap_visual("s1", new_visual)
    assert result is True
    assert sb.scenes[0].visual["type"] == "generated_image"


def test_swap_visual_nonexistent():
    sb = Storyboard(scenes=[])
    assert sb.swap_visual("s99", {"type": "text_card"}) is False


def test_estimated_duration():
    sb = Storyboard(
        scenes=[
            Scene(
                id="s1", section="hook", narration="test", narration_est_sec=5, pause_after_sec=2
            ),
            Scene(
                id="s2", section="context", narration="test", narration_est_sec=8, pause_after_sec=0
            ),
        ]
    )
    assert sb.estimated_duration_sec() == 15.0


def test_get_scene():
    sb = Storyboard(
        scenes=[
            Scene(id="s1", section="hook", narration="test", narration_est_sec=5),
            Scene(id="s2", section="context", narration="test2", narration_est_sec=8),
        ]
    )
    assert sb.get_scene("s1") is not None
    assert sb.get_scene("s1").section == "hook"
    assert sb.get_scene("s99") is None
