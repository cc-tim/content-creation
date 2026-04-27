from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.voices.base import VoiceProfile


def _profile(reference_id: str = "test-ref-123") -> VoiceProfile:
    return VoiceProfile(
        id="tim-zhtw-fish",
        engine="fish_audio",
        locale="zh-TW",
        params={"reference_id": reference_id},
    )


def test_fish_audio_engine_name():
    from pipeline.voices.fish_audio_engine import FishAudioEngine

    engine = FishAudioEngine(api_key="test-key")
    assert engine.name == "fish_audio"


def test_synthesize_writes_audio_bytes(tmp_path: Path):
    from pipeline.voices.fish_audio_engine import FishAudioEngine

    fake_audio = b"fake-mp3-bytes"
    mock_response = MagicMock()
    mock_response.content = fake_audio
    mock_response.raise_for_status = MagicMock()

    out = tmp_path / "segment_000.mp3"
    with patch("pipeline.voices.fish_audio_engine.httpx.post", return_value=mock_response):
        FishAudioEngine(api_key="sk-test").synthesize("你好世界", out, _profile())

    assert out.read_bytes() == fake_audio


def test_synthesize_sends_correct_request(tmp_path: Path):
    from pipeline.voices.fish_audio_engine import FishAudioEngine

    mock_response = MagicMock()
    mock_response.content = b"audio"
    mock_response.raise_for_status = MagicMock()

    with patch("pipeline.voices.fish_audio_engine.httpx.post", return_value=mock_response) as mock_post:
        FishAudioEngine(api_key="sk-test").synthesize("你好", tmp_path / "out.mp3", _profile("ref-abc"))

    call_kwargs = mock_post.call_args
    assert call_kwargs.args[0] == "https://api.fish.audio/v1/tts"
    assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer sk-test"
    body = call_kwargs.kwargs["json"]
    assert body["text"] == "你好"
    assert body["reference_id"] == "ref-abc"
    assert body["format"] == "mp3"


def test_synthesize_raises_on_missing_reference_id(tmp_path: Path):
    from pipeline.voices.fish_audio_engine import FishAudioEngine

    profile = VoiceProfile(id="bad", engine="fish_audio", locale="zh-TW", params={})
    with pytest.raises(ValueError, match="reference_id"):
        FishAudioEngine(api_key="sk-test").synthesize("text", tmp_path / "out.mp3", profile)


def test_synthesize_creates_parent_dir(tmp_path: Path):
    from pipeline.voices.fish_audio_engine import FishAudioEngine

    mock_response = MagicMock()
    mock_response.content = b"audio"
    mock_response.raise_for_status = MagicMock()

    nested = tmp_path / "audio" / "segment_000.mp3"
    with patch("pipeline.voices.fish_audio_engine.httpx.post", return_value=mock_response):
        FishAudioEngine(api_key="sk-test").synthesize("text", nested, _profile())

    assert nested.exists()


def test_registry_returns_fish_audio_engine(tmp_path: Path, monkeypatch):
    from pipeline.voices.fish_audio_engine import FishAudioEngine
    from pipeline.voices.registry import VoiceRegistry

    registry_data = {
        "voices": [
            {
                "id": "tim-fish-default-f",
                "engine": "fish_audio",
                "locale": "zh-TW",
                "params": {"reference_id": "abc123"},
            }
        ]
    }
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    (voices_dir / "registry.json").write_text(json.dumps(registry_data))

    monkeypatch.setenv("PIPELINE_FISH_AUDIO_API_KEY", "sk-fish-test")

    reg = VoiceRegistry(voices_dir)
    engine, profile = reg.resolve("tim-fish-default-f")

    assert isinstance(engine, FishAudioEngine)
    assert profile.params["reference_id"] == "abc123"
