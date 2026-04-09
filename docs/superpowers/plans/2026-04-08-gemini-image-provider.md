# Gemini Image Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Gemini 2.5 Flash Image ("nano banana") as the primary image-generation provider with automatic fallback to DALL-E 3 when the Gemini free tier is exhausted.

**Architecture:** Introduce a small `ImageProvider` abstraction with a `try_chain()` helper that walks an ordered list of providers, catches quota/rate errors, marks providers on cooldown, and returns the first successful image. `composer/image.py` stops calling OpenAI directly and instead delegates to the chain. Configuration (`PIPELINE_IMAGE_PROVIDERS=gemini,dalle`) controls ordering.

**Tech Stack:** `google-genai` SDK (Gemini), existing `openai` SDK (DALL-E), pydantic-settings, pytest with `respx`/monkeypatch for HTTP stubbing.

**Spec:** `docs/superpowers/specs/2026-04-08-voice-pipeline-gemini-composition-overhaul-design.md` — Feature 3.

---

## File Structure

- **Create:** `src/pipeline/providers/__init__.py` — package marker
- **Create:** `src/pipeline/providers/base.py` — `ImageProvider` ABC, `ProviderResult`, `ProviderError`, `QuotaExhausted`, `try_chain()`
- **Create:** `src/pipeline/providers/dalle.py` — `DalleImageProvider` (moved from `composer/image.py`)
- **Create:** `src/pipeline/providers/gemini.py` — `GeminiImageProvider` using `google-genai` SDK
- **Create:** `tests/unit/test_provider_chain.py` — unit tests for `try_chain()` ordering, cooldowns, error handling
- **Create:** `tests/unit/test_gemini_provider.py` — unit tests for `GeminiImageProvider` (mocked)
- **Modify:** `src/pipeline/config.py` — add `GEMINI_API_KEY`, `IMAGE_PROVIDERS` fields
- **Modify:** `src/pipeline/composer/image.py` — replace `_download_dalle_image` with `providers.try_chain(...)`
- **Modify:** `pyproject.toml` — add `google-genai` dependency
- **Modify:** `uv.lock` — refreshed by `uv sync`

---

## Task 1: Add `google-genai` dependency and config fields

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/pipeline/config.py`
- Test: `tests/unit/test_config.py` (create if missing)

- [ ] **Step 1: Add dependency**

Edit `pyproject.toml` to add `"google-genai>=0.3.0"` to the `dependencies` list.

- [ ] **Step 2: Run `uv sync`**

Run: `uv sync`
Expected: Resolves and installs `google-genai` without conflicts.

- [ ] **Step 3: Write the failing config test**

Add to `tests/unit/test_config.py` (create file if it does not exist):

```python
from pipeline.config import PipelineConfig


def test_gemini_key_from_unprefixed_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")
    monkeypatch.delenv("PIPELINE_GEMINI_API_KEY", raising=False)
    cfg = PipelineConfig()
    assert cfg.gemini_api_key == "fake-gemini-key"


def test_image_providers_default():
    cfg = PipelineConfig()
    assert cfg.image_providers == "gemini,dalle"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: FAIL — `AttributeError: 'PipelineConfig' object has no attribute 'gemini_api_key'`.

- [ ] **Step 5: Add config fields**

Edit `src/pipeline/config.py`. Add to `PipelineConfig`:

```python
from pydantic import AliasChoices, Field

# ... inside PipelineConfig, alongside existing *_api_key fields:
gemini_api_key: str | None = Field(
    default=None,
    validation_alias=AliasChoices("GEMINI_API_KEY", "PIPELINE_GEMINI_API_KEY"),
)
image_providers: str = "gemini,dalle"
```

If `AliasChoices` is already imported, skip the import line.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/pipeline/config.py tests/unit/test_config.py
git commit -m "feat(config): add GEMINI_API_KEY and image_providers settings"
```

---

## Task 2: Provider base types and error hierarchy

**Files:**
- Create: `src/pipeline/providers/__init__.py`
- Create: `src/pipeline/providers/base.py`
- Test: `tests/unit/test_provider_chain.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_provider_chain.py`:

```python
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
    result = try_chain([first, second], prompt="cat", out_path=tmp_path / "a.png", size="1024x1024")
    assert result.provider == "gemini"
    assert first.calls == 1
    assert second.calls == 0


def test_try_chain_falls_back_on_quota(tmp_path):
    first = _StubProvider("gemini", "quota")
    second = _StubProvider("dalle", "ok")
    result = try_chain([first, second], prompt="cat", out_path=tmp_path / "b.png", size="1024x1024")
    assert result.provider == "dalle"
    assert first.calls == 1
    assert second.calls == 1


def test_try_chain_raises_when_all_fail(tmp_path):
    first = _StubProvider("gemini", "quota")
    second = _StubProvider("dalle", "error")
    with pytest.raises(ProviderError):
        try_chain([first, second], prompt="cat", out_path=tmp_path / "c.png", size="1024x1024")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_provider_chain.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.providers'`.

- [ ] **Step 3: Create providers package**

Create `src/pipeline/providers/__init__.py` with empty content.

Create `src/pipeline/providers/base.py`:

```python
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
    def generate(self, prompt: str, out_path: Path, size: str) -> ProviderResult:
        ...


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
    raise ProviderError(f"all image providers failed; last error: {last_error}") from last_error
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_provider_chain.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/providers/__init__.py src/pipeline/providers/base.py tests/unit/test_provider_chain.py
git commit -m "feat(providers): add ImageProvider base + try_chain helper"
```

---

## Task 3: Move DALL-E 3 into a provider class

**Files:**
- Create: `src/pipeline/providers/dalle.py`
- Test: `tests/unit/test_provider_chain.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_provider_chain.py`:

```python
from unittest.mock import MagicMock

from pipeline.providers.dalle import DalleImageProvider


def test_dalle_provider_writes_file(tmp_path, monkeypatch):
    # Stub the openai client so no real network call happens.
    fake_client = MagicMock()
    fake_client.images.generate.return_value = MagicMock(
        data=[MagicMock(url="https://example/img.png")]
    )
    monkeypatch.setattr(
        "pipeline.providers.dalle._build_client", lambda key: fake_client
    )
    monkeypatch.setattr(
        "pipeline.providers.dalle._download", lambda url, path: path.write_bytes(b"png-bytes")
    )

    provider = DalleImageProvider(api_key="fake")
    out = tmp_path / "dalle.png"
    result = provider.generate("a cat", out, "1024x1024")

    assert result.provider == "dalle"
    assert out.read_bytes() == b"png-bytes"
    fake_client.images.generate.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_provider_chain.py::test_dalle_provider_writes_file -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.providers.dalle'`.

- [ ] **Step 3: Implement the DALL-E provider**

Create `src/pipeline/providers/dalle.py`:

```python
from __future__ import annotations

from pathlib import Path

import httpx
from openai import OpenAI, APIStatusError, RateLimitError

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_provider_chain.py -v`
Expected: PASS (all 4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/providers/dalle.py tests/unit/test_provider_chain.py
git commit -m "feat(providers): add DalleImageProvider wrapper"
```

---

## Task 4: Implement Gemini provider

**Files:**
- Create: `src/pipeline/providers/gemini.py`
- Test: `tests/unit/test_gemini_provider.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_gemini_provider.py`:

```python
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
        raise _ResourceExhausted("429 quota")

    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = boom
    monkeypatch.setattr(
        "pipeline.providers.gemini._build_client", lambda key: fake_client
    )

    provider = GeminiImageProvider(api_key="fake")
    with pytest.raises(QuotaExhausted):
        provider.generate("x", tmp_path / "x.png", "1024x1024")


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
        provider.generate("x", tmp_path / "y.png", "1024x1024")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_gemini_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.providers.gemini'`.

- [ ] **Step 3: Implement the Gemini provider**

Create `src/pipeline/providers/gemini.py`:

```python
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
    MODEL = "gemini-2.5-flash-image-preview"

    def __init__(self, api_key: str):
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "gemini"

    def generate(self, prompt: str, out_path: Path, size: str) -> ProviderResult:
        client = _build_client(self._api_key)
        try:
            response = client.models.generate_content(
                model=self.MODEL,
                contents=prompt,
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_gemini_provider.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/providers/gemini.py tests/unit/test_gemini_provider.py
git commit -m "feat(providers): add GeminiImageProvider using google-genai"
```

---

## Task 5: Wire the provider chain into `composer/image.py`

**Files:**
- Modify: `src/pipeline/composer/image.py`
- Test: `tests/unit/test_image_renderer.py`

- [ ] **Step 1: Read existing test file**

Run: `uv run pytest tests/unit/test_image_renderer.py -v`
Note which tests currently pass so you can preserve their behavior.

- [ ] **Step 2: Write the failing test**

Append to `tests/unit/test_image_renderer.py`:

```python
def test_render_generated_image_uses_provider_chain(tmp_path, monkeypatch):
    from pipeline.composer.image import render_generated_image
    from pipeline.providers.base import ProviderResult

    calls = {"chain": 0}

    def fake_chain(providers, *, prompt, out_path, size):
        calls["chain"] += 1
        assert "neon city" in prompt
        out_path.write_bytes(b"png")
        return ProviderResult(path=out_path, provider="gemini")

    monkeypatch.setattr("pipeline.composer.image.try_chain", fake_chain)
    monkeypatch.setattr(
        "pipeline.composer.image._build_providers",
        lambda cfg: ["stub-provider"],
    )

    visual = {"prompt": "neon city skyline"}
    result = render_generated_image(
        visual=visual,
        duration_sec=5.0,
        width=1920,
        height=1080,
        work_dir=tmp_path,
        scene_id="s1",
        theme={"image_style": "flat minimalist"},
    )

    assert result.exists()
    assert calls["chain"] == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_image_renderer.py::test_render_generated_image_uses_provider_chain -v`
Expected: FAIL (either import or attribute error).

- [ ] **Step 4: Refactor `composer/image.py`**

Read the current file first. Then modify `render_generated_image` so it:
- Replaces its local `_download_dalle_image` call with `providers = _build_providers(cfg)` + `try_chain(providers, ...)`
- Falls back to `render_text_card` when `ProviderError` is raised
- Keeps the still-image-to-video FFmpeg step unchanged

Add the helper and imports at the top of `composer/image.py`:

```python
from pipeline.config import PipelineConfig
from pipeline.providers.base import ImageProvider, ProviderError, try_chain
from pipeline.providers.dalle import DalleImageProvider
from pipeline.providers.gemini import GeminiImageProvider


def _build_providers(cfg: PipelineConfig) -> list[ImageProvider]:
    order = [p.strip() for p in cfg.image_providers.split(",") if p.strip()]
    built: list[ImageProvider] = []
    for name in order:
        if name == "gemini" and cfg.gemini_api_key:
            built.append(GeminiImageProvider(api_key=cfg.gemini_api_key))
        elif name == "dalle" and cfg.openai_api_key:
            built.append(DalleImageProvider(api_key=cfg.openai_api_key))
    return built
```

Then inside `render_generated_image`, replace the old DALL-E block with:

```python
cfg = PipelineConfig()
providers = _build_providers(cfg)
if not providers:
    # No keys at all — keep existing text_card fallback.
    return render_text_card(visual, duration_sec, width, height, work_dir, scene_id, theme)

png_path = work_dir / f"{scene_id}_gen.png"
try:
    try_chain(providers, prompt=full_prompt, out_path=png_path, size="1024x1024")
except ProviderError as exc:
    logger.warning("all image providers failed for scene %s: %s", scene_id, exc)
    return render_text_card(visual, duration_sec, width, height, work_dir, scene_id, theme)
```

Remove the old `_download_dalle_image` helper.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_image_renderer.py -v`
Expected: All tests PASS, including the new one.

- [ ] **Step 6: Run the full test suite sanity check**

Run: `uv run pytest tests/unit/ -q`
Expected: No regressions in unrelated modules.

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/composer/image.py tests/unit/test_image_renderer.py
git commit -m "feat(compose): route generated images through provider chain"
```

---

## Task 6: Smoke test against real Gemini (manual, optional)

**Files:**
- None (manual verification only)

- [ ] **Step 1: Confirm the env var is available**

Run: `bash -lc 'echo ${GEMINI_API_KEY:0:6}...'`
Expected: Prints the first 6 characters of the key (non-empty).

- [ ] **Step 2: Generate a single image end to end**

Run:

```bash
uv run python3 -c "
from pathlib import Path
from pipeline.config import PipelineConfig
from pipeline.providers.base import try_chain
from pipeline.providers.gemini import GeminiImageProvider
cfg = PipelineConfig()
assert cfg.gemini_api_key, 'GEMINI_API_KEY not loaded'
out = Path('/tmp/gemini_smoke.png')
result = try_chain(
    [GeminiImageProvider(api_key=cfg.gemini_api_key)],
    prompt='flat minimalist illustration of a robot reading a book',
    out_path=out,
    size='1024x1024',
)
print('wrote', result.path, result.path.stat().st_size, 'bytes via', result.provider)
"
```
Expected: Prints `wrote /tmp/gemini_smoke.png <N> bytes via gemini` with N > 5000.

- [ ] **Step 3: Open the image visually to confirm it's not corrupt**

Run: `xdg-open /tmp/gemini_smoke.png` (or use any image viewer).
Expected: A rendered image appears.

If this smoke test fails, debug the provider before proceeding. No commit — this task is purely a verification checkpoint.

---

## Done criteria

- `uv run pytest tests/unit/test_provider_chain.py tests/unit/test_gemini_provider.py tests/unit/test_image_renderer.py tests/unit/test_config.py -v` is green.
- `render_generated_image` calls Gemini first and falls back to DALL-E on quota errors (verified by unit tests).
- Smoke test in Task 6 produced a real PNG from Gemini.
- No direct references to `openai.images.generate` remain in `src/pipeline/composer/`.
