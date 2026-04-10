from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

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
