from __future__ import annotations

import pytest

from pipeline.storyboard import NarrationSource


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
