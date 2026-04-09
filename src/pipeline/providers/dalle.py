from __future__ import annotations

from pathlib import Path

import httpx
from openai import APIStatusError, OpenAI, RateLimitError

from pipeline.providers.base import (
    ImageProvider,
    ProviderError,
    ProviderResult,
    QuotaExhausted,
)


def _build_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def _download(url: str, out_path: Path) -> None:
    with httpx.Client(timeout=60.0) as client:
        response = client.get(url)
        response.raise_for_status()
        out_path.write_bytes(response.content)


class DalleImageProvider(ImageProvider):
    def __init__(self, api_key: str):
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "dalle"

    def generate(self, prompt: str, out_path: Path, size: str) -> ProviderResult:
        client = _build_client(self._api_key)
        try:
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=size,
                n=1,
            )
        except RateLimitError as exc:
            raise QuotaExhausted(f"dalle rate-limited: {exc}") from exc
        except APIStatusError as exc:
            raise ProviderError(f"dalle api error: {exc}") from exc

        if not response.data or not response.data[0].url:
            raise ProviderError("dalle returned no image url")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        _download(response.data[0].url, out_path)
        return ProviderResult(path=out_path, provider=self.name)
