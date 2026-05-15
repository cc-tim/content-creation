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
    assert s.narration_alt == {}


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
        narration_alt={"en": "Hello"},
    )
    sb = Storyboard(scenes=[s])
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "sb.json"
        sb.save(p)
        sb2 = Storyboard.load(p)
    assert sb2.scenes[0].narration_alt == {"en": "Hello"}


def test_scene_from_dict_new_shape():
    from pipeline.storyboard import Scene

    scene = Scene.from_dict({
        "id": "s1",
        "section": "hook",
        "beat": "establishes the 600-year design stasis",
        "narration": "西元一千四百四十年……",
        "narration_alt": {"en": "Year 1440..."},
        "narration_est_sec": 8.0,
    })
    assert scene.beat == "establishes the 600-year design stasis"
    assert scene.narration == "西元一千四百四十年……"
    assert scene.narration_alt == {"en": "Year 1440..."}


def test_scene_from_dict_old_shape_folds_narration_en():
    from pipeline.storyboard import Scene

    scene = Scene.from_dict({
        "id": "s1",
        "section": "hook",
        "narration": "西元一千四百四十年……",
        "narration_en": "Year 1440...",
        "narration_est_sec": 8.0,
    })
    assert scene.beat == ""
    assert scene.narration == "西元一千四百四十年……"
    assert scene.narration_alt == {"en": "Year 1440..."}


def test_scene_to_dict_round_trip():
    from pipeline.storyboard import Scene

    data = {
        "id": "s1",
        "section": "hook",
        "beat": "b",
        "narration": "primary",
        "narration_alt": {"en": "secondary"},
        "narration_est_sec": 8.0,
        "facts_ref": [],
        "visual": {},
        "overlay": None,
        "pause_after_sec": 0.5,
    }
    out = Scene.from_dict(data).to_dict()
    assert out["beat"] == "b"
    assert out["narration"] == "primary"
    assert out["narration_alt"] == {"en": "secondary"}
    assert "narration_en" not in out


def test_scene_to_dict_omits_empty_narration_alt():
    from pipeline.storyboard import Scene

    scene = Scene.from_dict({
        "id": "s1", "section": "hook", "narration": "x", "narration_est_sec": 5.0,
    })
    assert "narration_alt" not in scene.to_dict()


def test_scene_narration_for():
    from pipeline.storyboard import Scene

    scene = Scene.from_dict({
        "id": "s1", "section": "hook", "narration": "primary",
        "narration_alt": {"en": "english"}, "narration_est_sec": 5.0,
    })
    assert scene.narration_for("zh-TW", "zh-TW") == "primary"
    assert scene.narration_for("en", "zh-TW") == "english"
    assert scene.narration_for("ja", "zh-TW") == ""


from pipeline.storyboard import Storyboard


def _sb(**over):
    base = {
        "version": 1,
        "primary_locale": "zh-TW",
        "scenes": [
            {"id": "s1", "section": "hook", "beat": "b1", "narration": "主要一",
             "narration_alt": {"en": "primary one"}, "narration_est_sec": 5.0,
             "pause_after_sec": 0.0},
            {"id": "s2", "section": "context", "beat": "b2", "narration": "主要二",
             "narration_alt": {"en": "primary two"}, "narration_est_sec": 5.0,
             "pause_after_sec": 0.0},
        ],
    }
    base.update(over)
    return Storyboard.from_dict(base)


def test_storyboard_primary_locale_round_trip():
    sb = _sb()
    assert sb.primary_locale == "zh-TW"
    assert sb.to_dict()["primary_locale"] == "zh-TW"


def test_storyboard_primary_locale_defaults():
    sb = Storyboard.from_dict({"version": 1, "scenes": []})
    assert sb.primary_locale == "zh-TW"


def test_derive_script_defaults_to_primary():
    script = _sb().derive_script()
    assert "主要一" in script and "主要二" in script
    assert "primary one" not in script


def test_derive_script_secondary_locale():
    script = _sb().derive_script(locale="en")
    assert "primary one" in script and "primary two" in script
    assert "主要一" not in script
