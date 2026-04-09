from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.providers.base import (
    ImageProvider,
    ProviderError,
    ProviderResult,
    QuotaExhausted,
    try_chain,
)


class _StubProvider(ImageProvider):
    def __init__(self, name: str, behavior: str):
        self._name = name
        self._behavior = behavior
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    def generate(self, prompt: str, out_path: Path, size: str) -> ProviderResult:
        self.calls += 1
        if self._behavior == "ok":
            out_path.write_bytes(b"fake-bytes")
            return ProviderResult(path=out_path, provider=self._name)
        if self._behavior == "quota":
            raise QuotaExhausted(f"{self._name} quota")
        raise ProviderError(f"{self._name} boom")


def test_try_chain_returns_first_success(tmp_path):
    first = _StubProvider("gemini", "ok")
    second = _StubProvider("dalle", "ok")
    result = try_chain(
        [first, second],
        prompt="cat",
        out_path=tmp_path / "a.png",
        size="1024x1024",
    )
    assert result.provider == "gemini"
    assert first.calls == 1
    assert second.calls == 0


def test_try_chain_falls_back_on_quota(tmp_path):
    first = _StubProvider("gemini", "quota")
    second = _StubProvider("dalle", "ok")
    result = try_chain(
        [first, second],
        prompt="cat",
        out_path=tmp_path / "b.png",
        size="1024x1024",
    )
    assert result.provider == "dalle"
    assert first.calls == 1
    assert second.calls == 1


def test_try_chain_raises_when_all_fail(tmp_path):
    first = _StubProvider("gemini", "quota")
    second = _StubProvider("dalle", "error")
    with pytest.raises(ProviderError):
        try_chain(
            [first, second],
            prompt="cat",
            out_path=tmp_path / "c.png",
            size="1024x1024",
        )


def test_try_chain_raises_on_empty_provider_list(tmp_path):
    with pytest.raises(ProviderError):
        try_chain(
            [],
            prompt="cat",
            out_path=tmp_path / "d.png",
            size="1024x1024",
        )
