from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pipeline.voices.base import VoiceProfile
from pipeline.voices.edge_engine import EdgeEngine


def test_edge_engine_invokes_edge_tts(tmp_path):
    profile = VoiceProfile(
        id="zh-TW-default-f",
        engine="edge",
        locale="zh-TW",
        params={"voice": "zh-TW-HsiaoChenNeural"},
    )
    out = tmp_path / "narration.mp3"

    async def fake_save(self, path):
        Path(path).write_bytes(b"FAKE-MP3")

    with patch("pipeline.voices.edge_engine.edge_tts.Communicate") as fake_class:
        instance = fake_class.return_value
        instance.save = fake_save.__get__(instance, type(instance))
        result = EdgeEngine().synthesize("你好", out, profile)

    assert result == out
    assert out.read_bytes() == b"FAKE-MP3"
    fake_class.assert_called_once()
    # First positional arg is the text, second is the voice.
    args, kwargs = fake_class.call_args
    assert args[0] == "你好"
    assert args[1] == "zh-TW-HsiaoChenNeural"


_LEGACY_WSS_URL = (
    "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1"
    "?TrustedClientToken=6A5AA1D4EAFF4E9FB37E23D68491D6F4"
)


def _synthesize_with_fake_communicate(tmp_path):
    profile = VoiceProfile(
        id="zh-TW-default-f",
        engine="edge",
        locale="zh-TW",
        params={"voice": "zh-TW-HsiaoChenNeural"},
    )

    async def fake_save(self, path):
        Path(path).write_bytes(b"FAKE-MP3")

    with patch("pipeline.voices.edge_engine.edge_tts.Communicate") as fake_class:
        instance = fake_class.return_value
        instance.save = fake_save.__get__(instance, type(instance))
        EdgeEngine().synthesize("你好", tmp_path / "n.mp3", profile)


def test_edge_engine_moves_synthesis_off_the_legacy_bing_host(tmp_path, monkeypatch):
    """speech.platform.bing.com answers synthesis with 403 since Oct 2026 (rany2/edge-tts#490)."""
    import edge_tts.communicate

    monkeypatch.setattr(edge_tts.communicate, "WSS_URL", _LEGACY_WSS_URL)

    _synthesize_with_fake_communicate(tmp_path)

    url = edge_tts.communicate.WSS_URL
    assert url.startswith("wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1?")
    assert "Ocp-Apim-Subscription-Key=6A5AA1D4EAFF4E9FB37E23D68491D6F4" in url


def test_edge_engine_leaves_a_fixed_upstream_endpoint_alone(tmp_path, monkeypatch):
    """Once an edge-tts release ships its own endpoint, the override must step aside."""
    import edge_tts.communicate

    upstream = "wss://speech.example.invalid/v2?Ocp-Apim-Subscription-Key=abc"
    monkeypatch.setattr(edge_tts.communicate, "WSS_URL", upstream)

    _synthesize_with_fake_communicate(tmp_path)

    assert edge_tts.communicate.WSS_URL == upstream
