"""ImageProvider backed by ~/.claude/bin/gen-image.py.

Handles key rotation, prompt caching, and tier selection automatically.
This is the preferred provider — use it instead of Gemini or DALL-E directly.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pipeline.providers.base import ImageProvider, ProviderError, ProviderResult

_GEN_IMAGE_BIN = Path.home() / ".claude" / "bin" / "gen-image.py"

_DALLE_SIZE_TO_GEN = {
    "1024x1024": "square",
    "1792x1024": "landscape",
    "1024x1792": "portrait",
}


class GenImageProvider(ImageProvider):
    """Wraps gen-image.py: fal.ai (Flux) + OpenAI with automatic key rotation."""

    def __init__(self, tier: str = "draft") -> None:
        self._tier = tier

    @property
    def name(self) -> str:
        return f"gen-image({self._tier})"

    def generate(
        self,
        prompt: str,
        out_path: Path,
        size: str,
        reference_image: Path | None = None,
    ) -> ProviderResult:
        if not _GEN_IMAGE_BIN.exists():
            raise ProviderError(f"gen-image.py not found at {_GEN_IMAGE_BIN}")

        gen_size = _DALLE_SIZE_TO_GEN.get(size, "landscape")

        cmd = [
            "python3",
            str(_GEN_IMAGE_BIN),
            prompt,
            "--tier", self._tier,
            "--size", gen_size,
            "--output", str(out_path),
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderError("gen-image.py timed out") from exc

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "exhausted" in stderr.lower() or "no keys" in stderr.lower():
                from pipeline.providers.base import QuotaExhausted
                raise QuotaExhausted(f"gen-image quota: {stderr}")
            raise ProviderError(f"gen-image.py failed: {stderr or result.stdout.strip()}")

        # The script may have written to a cache path and printed it; copy if needed
        printed_path = result.stdout.strip().splitlines()[-1]  # last line is the path
        if printed_path and printed_path != str(out_path):
            src = Path(printed_path)
            if src.exists() and src != out_path:
                shutil.copy2(src, out_path)

        if not out_path.exists():
            raise ProviderError(f"gen-image.py ran but output not found at {out_path}")

        return ProviderResult(path=out_path, provider=self.name)
