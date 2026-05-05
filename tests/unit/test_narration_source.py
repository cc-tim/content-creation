from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.storyboard import NarrationSource, Scene, Storyboard


def test_narration_source_edge_engine_with_voice():
    ns = NarrationSource.from_dict({"engine": "edge", "voice": "zh-tw-default-f"})
    assert ns.engine == "edge"
    assert ns.voice == "zh-tw-default-f"
    assert ns.file is None


def test_narration_source_fish_audio_engine_with_voice():
    ns = NarrationSource.from_dict({"engine": "fish_audio", "voice": "fish-jingjing"})
    assert ns.engine == "fish_audio"
    assert ns.voice == "fish-jingjing"


def test_narration_source_prerecorded_with_file():
    ns = NarrationSource.from_dict({
        "engine": "prerecorded",
        "file": "narration_overrides/s9.wav",
    })
    assert ns.engine == "prerecorded"
    assert ns.file == "narration_overrides/s9.wav"
    assert ns.voice is None


def test_narration_source_to_dict_omits_none_fields():
    ns = NarrationSource(engine="edge", voice="zh-tw-default-f", file=None)
    out = ns.to_dict()
    assert out == {"engine": "edge", "voice": "zh-tw-default-f"}
    assert "file" not in out


def test_narration_source_to_dict_prerecorded_omits_voice():
    ns = NarrationSource(engine="prerecorded", voice=None, file="narration_overrides/s9.wav")
    out = ns.to_dict()
    assert out == {"engine": "prerecorded", "file": "narration_overrides/s9.wav"}
    assert "voice" not in out


def test_narration_source_rejects_unknown_engine():
    with pytest.raises(ValueError, match="Unknown narration engine"):
        NarrationSource(engine="elevenlabs", voice=None, file=None)


def test_narration_source_prerecorded_requires_file():
    """An engine='prerecorded' source without a file is invalid."""
    with pytest.raises(ValueError, match="prerecorded.*requires.*file"):
        NarrationSource(engine="prerecorded", voice=None, file=None)


def test_narration_source_tts_engine_requires_voice():
    """Engines edge/fish_audio require a voice (registry voice_id)."""
    with pytest.raises(ValueError, match="requires.*voice"):
        NarrationSource(engine="edge", voice=None, file=None)

def _minimal_scene_dict(scene_id: str) -> dict:
    return {
        "id": scene_id,
        "section": "content",
        "narration": f"narration for {scene_id}",
        "narration_est_sec": 1.0,
    }


def test_scene_defaults_narration_source_to_none():
    s = Scene(id="s1", section="content", narration="hi", narration_est_sec=1.0)
    assert s.narration_source is None


def test_scene_from_dict_without_narration_source():
    """Existing scenes (no narration_source key) still parse and produce None."""
    s = Scene.from_dict(_minimal_scene_dict("s1"))
    assert s.narration_source is None


def test_scene_from_dict_with_narration_source():
    data = _minimal_scene_dict("s9")
    data["narration_source"] = {"engine": "prerecorded", "file": "narration_overrides/s9.wav"}
    s = Scene.from_dict(data)
    assert s.narration_source is not None
    assert s.narration_source.engine == "prerecorded"
    assert s.narration_source.file == "narration_overrides/s9.wav"


def test_scene_to_dict_omits_narration_source_when_none():
    s = Scene(id="s1", section="content", narration="hi", narration_est_sec=1.0)
    out = s.to_dict()
    assert "narration_source" not in out


def test_scene_to_dict_includes_narration_source_when_set():
    from pipeline.storyboard import NarrationSource
    s = Scene(
        id="s9", section="content", narration="hi", narration_est_sec=1.0,
        narration_source=NarrationSource(engine="edge", voice="zh-tw-default-f"),
    )
    out = s.to_dict()
    assert out["narration_source"] == {"engine": "edge", "voice": "zh-tw-default-f"}


def test_storyboard_round_trip_with_narration_source(tmp_path: Path):
    from pipeline.storyboard import NarrationSource
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
        Scene(
            id="s9", section="content", narration="b", narration_est_sec=1.0,
            narration_source=NarrationSource(
                engine="prerecorded",
                file="narration_overrides/s9.wav",
            ),
        ),
    ])
    p = tmp_path / "sb.json"
    sb.save(p)
    loaded = Storyboard.load(p)
    assert loaded.scenes[0].narration_source is None
    assert loaded.scenes[1].narration_source is not None
    assert loaded.scenes[1].narration_source.engine == "prerecorded"
    assert loaded.scenes[1].narration_source.file == "narration_overrides/s9.wav"
