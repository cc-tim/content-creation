from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pipeline.voices.base import VoiceProfile
from pipeline.voices.cosy_engine import CosyVoiceEngine


def test_cosy_engine_requires_reference(tmp_path):
    profile = VoiceProfile(
        id="tim-zhtw",
        engine="cosyvoice",
        locale="zh-TW",
        params={},
    )
    with pytest.raises(ValueError):
        CosyVoiceEngine().synthesize("你好", tmp_path / "out.wav", profile)


def test_cosy_engine_invokes_model(tmp_path, monkeypatch):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF-stub")

    profile = VoiceProfile(
        id="tim-zhtw",
        engine="cosyvoice",
        locale="zh-TW",
        params={},
        reference_path=ref,
        reference_text="大家好",
    )

    fake_model = MagicMock()

    def fake_inference(text, prompt_text, prompt_audio, **_kwargs):
        # CosyVoice yields one or more result dicts with a `tts_speech` tensor
        yield {"tts_speech": MagicMock()}

    fake_model.inference_zero_shot.side_effect = fake_inference
    fake_save = MagicMock()

    monkeypatch.setattr(
        "pipeline.voices.cosy_engine._load_model",
        lambda: fake_model,
    )
    monkeypatch.setattr(
        "pipeline.voices.cosy_engine._load_audio",
        lambda path: (MagicMock(), 16000),
    )
    monkeypatch.setattr(
        "pipeline.voices.cosy_engine._save_tensor",
        fake_save,
    )

    out = tmp_path / "out.wav"
    result = CosyVoiceEngine().synthesize("你好世界", out, profile)

    assert result == out
    fake_model.inference_zero_shot.assert_called_once()
    fake_save.assert_called_once()
