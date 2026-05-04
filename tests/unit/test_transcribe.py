from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from pipeline.transcribe import transcribe_audio


def test_transcribe_audio_posts_multipart_to_whisper_endpoint(tmp_path: Path):
    src = tmp_path / "s9.wav"
    src.write_bytes(b"RIFF....WAVEfmt ")  # placeholder bytes

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"text": "你好世界"}
    fake_response.raise_for_status = MagicMock()

    with patch("pipeline.transcribe.httpx.post", return_value=fake_response) as mock_post:
        result = transcribe_audio(src, language="zh", api_key="sk-test")

    assert result == "你好世界"
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.openai.com/v1/audio/transcriptions"
    headers = kwargs["headers"]
    assert headers["Authorization"] == "Bearer sk-test"
    # Payload includes the model + language + the file as multipart.
    assert kwargs["data"]["model"] == "whisper-1"
    assert kwargs["data"]["language"] == "zh"
    files = kwargs["files"]
    assert "file" in files


def test_transcribe_audio_raises_on_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        transcribe_audio(tmp_path / "missing.wav", language="zh", api_key="sk-test")


def test_transcribe_audio_raises_on_empty_api_key(tmp_path: Path):
    src = tmp_path / "s9.wav"
    src.write_bytes(b"x")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        transcribe_audio(src, language="zh", api_key="")


def test_transcribe_audio_propagates_http_errors(tmp_path: Path):
    src = tmp_path / "s9.wav"
    src.write_bytes(b"x")

    fake_response = MagicMock()
    fake_response.raise_for_status.side_effect = RuntimeError("401 Unauthorized")

    with patch("pipeline.transcribe.httpx.post", return_value=fake_response):
        with pytest.raises(RuntimeError, match="401"):
            transcribe_audio(src, language="zh", api_key="sk-test")
