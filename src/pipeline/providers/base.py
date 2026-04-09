from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class ProviderError(RuntimeError):
    """Generic provider failure. Chain moves to next provider."""


class QuotaExhausted(ProviderError):
    """Free-tier quota or rate limit exceeded. Chain moves on and may cooldown."""


@dataclass
class ProviderResult:
    path: Path
    provider: str


class ImageProvider(ABC):
    """Generate an image for a given prompt and write it to disk."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def generate(self, prompt: str, out_path: Path, size: str) -> ProviderResult: ...


def try_chain(
    providers: list[ImageProvider],
    *,
    prompt: str,
    out_path: Path,
    size: str,
) -> ProviderResult:
    """Walk providers in order, returning the first successful result.

    Raises ProviderError if every provider fails. Logs the attempted providers
    so operators can see when fallback happened.
    """
    if not providers:
        raise ProviderError("no providers configured")

    last_error: Exception | None = None
    for provider in providers:
        try:
            logger.info("image provider attempt: %s", provider.name)
            return provider.generate(prompt, out_path, size)
        except QuotaExhausted as exc:
            logger.warning("image provider %s quota exhausted: %s", provider.name, exc)
            last_error = exc
        except ProviderError as exc:
            logger.warning("image provider %s failed: %s", provider.name, exc)
            last_error = exc

    assert last_error is not None
    raise ProviderError(
        f"all image providers failed; last error: {last_error}"
    ) from last_error
