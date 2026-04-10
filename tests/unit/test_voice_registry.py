from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.voices.base import VoiceEngine, VoiceProfile


def test_voice_profile_from_dict_minimum():
    profile = VoiceProfile.from_dict(
        {
            "id": "zh-TW-default-f",
            "engine": "edge",
            "locale": "zh-TW",
            "params": {"voice": "zh-TW-HsiaoChenNeural"},
        }
    )
    assert profile.id == "zh-TW-default-f"
    assert profile.engine == "edge"
    assert profile.locale == "zh-TW"
    assert profile.params == {"voice": "zh-TW-HsiaoChenNeural"}
    assert profile.reference_path is None


def test_voice_profile_with_reference(tmp_path):
    ref = tmp_path / "sample.wav"
    ref.write_bytes(b"RIFFWAVE-stub")
    profile = VoiceProfile.from_dict(
        {
            "id": "tim-zhtw",
            "engine": "cosyvoice",
            "locale": "zh-TW",
            "reference": str(ref),
            "reference_text": "大家好",
            "params": {},
        }
    )
    assert profile.reference_path == ref
    assert profile.reference_text == "大家好"


def test_voice_engine_is_abstract():
    with pytest.raises(TypeError):
        VoiceEngine()  # type: ignore[abstract]
