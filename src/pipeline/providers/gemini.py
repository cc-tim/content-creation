from __future__ import annotations

from pathlib import Path

from pipeline.providers.base import (
    ImageProvider,
    ProviderError,
    ProviderResult,
    QuotaExhausted,
)


def _build_client(api_key: str):
    # Lazy import so the dependency is only required when the provider is used.
    from google import genai

    return genai.Client(api_key=api_key)


def _is_quota_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("quota", "rate limit", "resource_exhausted", "429")
    )


class GeminiImageProvider(ImageProvider):
    MODEL = "gemini-2.5-flash-image"

    def __init__(self, api_key: str):
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "gemini"

    def generate(
        self,
        prompt: str,
        out_path: Path,
        size: str,
        reference_image: Path | None = None,
    ) -> ProviderResult:
        from google.genai import types

        client = _build_client(self._api_key)
        contents: list = [prompt]
        if reference_image is not None and reference_image.exists():
            mime = "image/png" if reference_image.suffix.lower() == ".png" else "image/jpeg"
            contents.append(
                types.Part.from_bytes(
                    data=reference_image.read_bytes(), mime_type=mime
                )
            )
        try:
            response = client.models.generate_content(
                model=self.MODEL,
                contents=contents if len(contents) > 1 else prompt,
            )
        except Exception as exc:  # google-genai raises many subtypes; normalize here
            if _is_quota_error(exc):
                raise QuotaExhausted(f"gemini quota: {exc}") from exc
            raise ProviderError(f"gemini error: {exc}") from exc

        image_bytes = _extract_image_bytes(response)
        if image_bytes is None:
            raise ProviderError("gemini returned no inline image data")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(image_bytes)
        return ProviderResult(path=out_path, provider=self.name)


def _extract_image_bytes(response) -> bytes | None:
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if content is None:
            continue
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                return inline.data
    return None
