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


def test_storyboard_roundtrips_title_and_description():
    sb = Storyboard.from_dict({
        "version": 1,
        "format": "standard",
        "target_duration_sec": 720,
        "aspect_ratio": "16:9",
        "title": "アメリカの大学研究：子供の癇癪",
        "description": "ブリガム・ヤング大学の研究者による2021年の研究…",
        "scenes": [],
    })

    assert sb.title == "アメリカの大学研究：子供の癇癪"
    assert sb.description.startswith("ブリガム・ヤング大学")

    data = sb.to_dict()
    assert data["title"] == sb.title
    assert data["description"] == sb.description


def test_storyboard_without_title_description_roundtrips():
    sb = Storyboard.from_dict({
        "version": 1,
        "format": "standard",
        "target_duration_sec": 720,
        "aspect_ratio": "16:9",
        "scenes": [],
    })

    assert sb.title is None
    assert sb.description is None
    data = sb.to_dict()
    # Absent fields should NOT be emitted when None (to keep existing files stable)
    assert "title" not in data
    assert "description" not in data


def test_scene_narration_en_optional():
    from pipeline.storyboard import Scene

    s = Scene(
        id="s1",
        section="hook",
        narration="你好",
        narration_est_sec=2.0,
        visual={"type": "text_card", "text": "hi"},
    )
    assert s.narration_en is None


def test_scene_narration_en_roundtrips():
    import pathlib
    import tempfile

    from pipeline.storyboard import Scene, Storyboard

    s = Scene(
        id="s1",
        section="hook",
        narration="你好",
        narration_est_sec=2.0,
        visual={"type": "text_card", "text": "hi"},
        narration_en="Hello",
    )
    sb = Storyboard(scenes=[s])
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "sb.json"
        sb.save(p)
        sb2 = Storyboard.load(p)
    assert sb2.scenes[0].narration_en == "Hello"
