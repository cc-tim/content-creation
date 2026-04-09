from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pipeline.providers.base import ProviderError, QuotaExhausted
from pipeline.providers.gemini import GeminiImageProvider


def _fake_response(image_bytes: bytes):
    fake_part = MagicMock()
    fake_part.inline_data = MagicMock(data=image_bytes, mime_type="image/png")
    fake_part.text = None

    fake_candidate = MagicMock()
    fake_candidate.content = MagicMock(parts=[fake_part])

    resp = MagicMock()
    resp.candidates = [fake_candidate]
    return resp


def test_gemini_provider_writes_bytes(tmp_path, monkeypatch):
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = _fake_response(b"PNG-DATA")
    monkeypatch.setattr(
        "pipeline.providers.gemini._build_client", lambda key: fake_client
    )

    provider = GeminiImageProvider(api_key="fake")
    out = tmp_path / "g.png"
    result = provider.generate("neon city", out, "1024x1024")

    assert result.provider == "gemini"
    assert out.read_bytes() == b"PNG-DATA"


def test_gemini_provider_maps_quota_error(tmp_path, monkeypatch):
    class _ResourceExhausted(Exception):
        pass

    def boom(*_a, **_k):
        raise _ResourceExhausted("429 quota exceeded")

    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = boom
    monkeypatch.setattr(
        "pipeline.providers.gemini._build_client", lambda key: fake_client
    )

    provider = GeminiImageProvider(api_key="fake")
    with pytest.raises(QuotaExhausted):
        provider.generate("x", tmp_path / "x.png", "1024x1024")


def test_gemini_provider_maps_other_error_to_provider_error(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("network blew up")

    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = boom
    monkeypatch.setattr(
        "pipeline.providers.gemini._build_client", lambda key: fake_client
    )

    provider = GeminiImageProvider(api_key="fake")
    with pytest.raises(ProviderError) as exc_info:
        provider.generate("x", tmp_path / "y.png", "1024x1024")
    # Make sure it's not wrapped as QuotaExhausted (which is a subclass).
    assert not isinstance(exc_info.value, QuotaExhausted)


def test_gemini_provider_raises_when_no_image(tmp_path, monkeypatch):
    fake_resp = MagicMock()
    fake_resp.candidates = []
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = fake_resp
    monkeypatch.setattr(
        "pipeline.providers.gemini._build_client", lambda key: fake_client
    )

    provider = GeminiImageProvider(api_key="fake")
    with pytest.raises(ProviderError):
        provider.generate("x", tmp_path / "z.png", "1024x1024")
