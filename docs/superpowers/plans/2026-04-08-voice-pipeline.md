# Voice Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a voice-profile system so `/produce` can pick between edge-tts default voices and user-recorded clones (CosyVoice2), with a simple CLI to manage voices.

**Architecture:** A `VoiceEngine` ABC abstracts TTS backends. `EdgeEngine` wraps the existing `edge-tts` call; `CosyVoiceEngine` runs CosyVoice2 zero-shot cloning from a local reference sample. A `VoiceRegistry` reads `voices/registry.json` (metadata) and resolves `voice_id → engine + params`. The `tts` stage asks the registry for an engine given `ctx.voice_id` and calls `engine.synthesize(text, out, locale)`.

**Tech Stack:** existing `edge-tts` (edge backend), `torch` + `torchaudio` + FunAudioLLM/CosyVoice (clone backend), Typer (CLI), pytest with monkeypatch for backend stubbing.

**Spec:** `docs/superpowers/specs/2026-04-08-voice-pipeline-gemini-composition-overhaul-design.md` — Feature 2.

---

## File Structure

- **Create:** `src/pipeline/voices/__init__.py`
- **Create:** `src/pipeline/voices/base.py` — `VoiceProfile` dataclass, `VoiceEngine` ABC, `VoiceNotFound`
- **Create:** `src/pipeline/voices/edge_engine.py` — `EdgeEngine` (wraps existing `generate_edge_tts`)
- **Create:** `src/pipeline/voices/cosy_engine.py` — `CosyVoiceEngine` (lazy-loaded)
- **Create:** `src/pipeline/voices/registry.py` — `VoiceRegistry.load/save/add/remove/resolve`
- **Create:** `voices/registry.json` — initial registry with built-in edge voices
- **Create:** `voices/edge/.gitkeep`, `voices/cloned/.gitkeep` — directory placeholders
- **Create:** `scripts/install_cosyvoice.sh` — clone + install script for CosyVoice2
- **Create:** `scripts/record_voice.md` — human recording guide (zh-TW sample script + tips)
- **Create:** `src/pipeline/cli_voice.py` — `voice list/add/remove/test` subcommands
- **Create:** `tests/unit/test_voice_registry.py`
- **Create:** `tests/unit/test_edge_engine.py`
- **Create:** `tests/unit/test_voice_cli.py`
- **Modify:** `src/pipeline/stages/tts.py` — use `VoiceRegistry` instead of calling `generate_edge_tts` directly
- **Modify:** `src/pipeline/stages/base.py` — add `voice_id: str | None` to `PipelineContext`
- **Modify:** `src/pipeline/cli.py` — add `--voice` flag to `produce`; wire `voice` subcommand
- **Modify:** `src/pipeline/config.py` — add `voices_dir: Path = Path("voices")`
- **Modify:** `pyproject.toml` — add `torch`, `torchaudio` as optional `[project.optional-dependencies] cosyvoice`
- **Modify:** `.claude/commands/produce.md` — document `--voice` flag and recording workflow
- **Modify:** `tests/unit/test_tts.py` — update for new `VoiceRegistry` path

---

## Task 1: `VoiceProfile` + `VoiceEngine` base types

**Files:**
- Create: `src/pipeline/voices/__init__.py`
- Create: `src/pipeline/voices/base.py`
- Test: `tests/unit/test_voice_registry.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_voice_registry.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.voices.base import VoiceEngine, VoiceProfile


def test_voice_profile_from_dict_minimum():
    profile = VoiceProfile.from_dict(
        {
            "id": "zh-TW-default-f",
            "engine": "edge",
            "locale": "zh-TW",
            "params": {"voice": "zh-TW-HsiaoChenNeural"},
        }
    )
    assert profile.id == "zh-TW-default-f"
    assert profile.engine == "edge"
    assert profile.locale == "zh-TW"
    assert profile.params == {"voice": "zh-TW-HsiaoChenNeural"}
    assert profile.reference_path is None


def test_voice_profile_with_reference(tmp_path):
    ref = tmp_path / "sample.wav"
    ref.write_bytes(b"RIFFWAVE-stub")
    profile = VoiceProfile.from_dict(
        {
            "id": "tim-zhtw",
            "engine": "cosyvoice",
            "locale": "zh-TW",
            "reference": str(ref),
            "reference_text": "大家好",
            "params": {},
        }
    )
    assert profile.reference_path == ref
    assert profile.reference_text == "大家好"


def test_voice_engine_is_abstract():
    with pytest.raises(TypeError):
        VoiceEngine()  # type: ignore[abstract]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_voice_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.voices'`.

- [ ] **Step 3: Implement the base types**

Create `src/pipeline/voices/__init__.py` (empty).

Create `src/pipeline/voices/base.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class VoiceNotFound(LookupError):
    """Raised when a requested voice_id does not exist in the registry."""


@dataclass
class VoiceProfile:
    id: str
    engine: str  # "edge" | "cosyvoice"
    locale: str
    params: dict[str, Any] = field(default_factory=dict)
    reference_path: Path | None = None
    reference_text: str | None = None
    display_name: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VoiceProfile":
        ref = data.get("reference")
        return cls(
            id=data["id"],
            engine=data["engine"],
            locale=data["locale"],
            params=dict(data.get("params") or {}),
            reference_path=Path(ref) if ref else None,
            reference_text=data.get("reference_text"),
            display_name=data.get("display_name"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "engine": self.engine,
            "locale": self.locale,
            "params": dict(self.params),
        }
        if self.reference_path is not None:
            out["reference"] = str(self.reference_path)
        if self.reference_text is not None:
            out["reference_text"] = self.reference_text
        if self.display_name is not None:
            out["display_name"] = self.display_name
        return out


class VoiceEngine(ABC):
    """Turns narration text into a WAV/MP3 file using a specific backend."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def synthesize(self, text: str, out_path: Path, profile: VoiceProfile) -> Path:
        """Write audio for `text` to `out_path`. Returns the final path."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_voice_registry.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/voices/__init__.py src/pipeline/voices/base.py tests/unit/test_voice_registry.py
git commit -m "feat(voices): add VoiceProfile and VoiceEngine base types"
```

---

## Task 2: `EdgeEngine` wraps existing edge-tts call

**Files:**
- Create: `src/pipeline/voices/edge_engine.py`
- Test: `tests/unit/test_edge_engine.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_edge_engine.py`:

```python
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

    async_stub = AsyncMock()

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_edge_engine.py -v`
Expected: FAIL — missing module.

- [ ] **Step 3: Implement `EdgeEngine`**

Create `src/pipeline/voices/edge_engine.py`:

```python
from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts

from pipeline.voices.base import VoiceEngine, VoiceProfile


class EdgeEngine(VoiceEngine):
    @property
    def name(self) -> str:
        return "edge"

    def synthesize(self, text: str, out_path: Path, profile: VoiceProfile) -> Path:
        voice = profile.params.get("voice")
        if not voice:
            raise ValueError(f"edge voice profile {profile.id} is missing params.voice")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(self._run(text, voice, out_path))
        return out_path

    @staticmethod
    async def _run(text: str, voice: str, out_path: Path) -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_edge_engine.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/voices/edge_engine.py tests/unit/test_edge_engine.py
git commit -m "feat(voices): add EdgeEngine backend"
```

---

## Task 3: `VoiceRegistry` load / resolve / mutate

**Files:**
- Create: `src/pipeline/voices/registry.py`
- Create: `voices/registry.json`
- Create: `voices/edge/.gitkeep`, `voices/cloned/.gitkeep`
- Modify: `src/pipeline/config.py` (add `voices_dir`)
- Test: `tests/unit/test_voice_registry.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_voice_registry.py`:

```python
import json

from pipeline.voices.base import VoiceNotFound
from pipeline.voices.edge_engine import EdgeEngine
from pipeline.voices.registry import VoiceRegistry


def _seed_registry(tmp_path) -> VoiceRegistry:
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    (voices_dir / "registry.json").write_text(
        json.dumps(
            {
                "voices": [
                    {
                        "id": "zh-TW-default-f",
                        "engine": "edge",
                        "locale": "zh-TW",
                        "params": {"voice": "zh-TW-HsiaoChenNeural"},
                        "display_name": "HsiaoChen (default)",
                    }
                ]
            }
        )
    )
    return VoiceRegistry(voices_dir)


def test_registry_lists_built_in_voice(tmp_path):
    registry = _seed_registry(tmp_path)
    profiles = registry.list()
    assert [p.id for p in profiles] == ["zh-TW-default-f"]


def test_registry_resolve_returns_engine_and_profile(tmp_path):
    registry = _seed_registry(tmp_path)
    engine, profile = registry.resolve("zh-TW-default-f")
    assert isinstance(engine, EdgeEngine)
    assert profile.locale == "zh-TW"


def test_registry_resolve_missing_raises(tmp_path):
    registry = _seed_registry(tmp_path)
    try:
        registry.resolve("nonexistent")
    except VoiceNotFound:
        return
    raise AssertionError("expected VoiceNotFound")


def test_registry_default_by_locale(tmp_path):
    registry = _seed_registry(tmp_path)
    engine, profile = registry.default_for_locale("zh-TW")
    assert profile.id == "zh-TW-default-f"


def test_registry_add_and_save(tmp_path):
    registry = _seed_registry(tmp_path)
    added = registry.add(
        {
            "id": "tim-zhtw",
            "engine": "cosyvoice",
            "locale": "zh-TW",
            "params": {},
            "reference": str(tmp_path / "voices" / "cloned" / "tim.wav"),
            "reference_text": "測試",
            "display_name": "Tim (clone)",
        }
    )
    assert added.id == "tim-zhtw"
    registry.save()

    # Re-load from disk to prove it persisted.
    reloaded = VoiceRegistry(tmp_path / "voices")
    assert any(p.id == "tim-zhtw" for p in reloaded.list())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_voice_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.voices.registry'`.

- [ ] **Step 3: Implement the registry**

Create `src/pipeline/voices/registry.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from pipeline.voices.base import VoiceEngine, VoiceNotFound, VoiceProfile
from pipeline.voices.edge_engine import EdgeEngine


class VoiceRegistry:
    """On-disk catalog of voice profiles keyed by id."""

    def __init__(self, voices_dir: Path):
        self._dir = Path(voices_dir)
        self._path = self._dir / "registry.json"
        self._profiles: dict[str, VoiceProfile] = {}
        self._load()

    # ---- loading / saving ----
    def _load(self) -> None:
        if not self._path.exists():
            return
        data = json.loads(self._path.read_text())
        for entry in data.get("voices", []):
            profile = VoiceProfile.from_dict(entry)
            self._profiles[profile.id] = profile

    def save(self) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {"voices": [p.to_dict() for p in self._profiles.values()]},
                indent=2,
                ensure_ascii=False,
            )
        )
        return self._path

    # ---- queries ----
    def list(self) -> list[VoiceProfile]:
        return list(self._profiles.values())

    def get(self, voice_id: str) -> VoiceProfile:
        if voice_id not in self._profiles:
            raise VoiceNotFound(f"voice '{voice_id}' not in registry")
        return self._profiles[voice_id]

    def default_for_locale(self, locale: str) -> tuple[VoiceEngine, VoiceProfile]:
        for profile in self._profiles.values():
            if profile.locale == locale and profile.id.endswith("default-f"):
                return self._engine_for(profile), profile
        for profile in self._profiles.values():
            if profile.locale == locale:
                return self._engine_for(profile), profile
        raise VoiceNotFound(f"no default voice for locale {locale}")

    def resolve(self, voice_id: str) -> tuple[VoiceEngine, VoiceProfile]:
        profile = self.get(voice_id)
        return self._engine_for(profile), profile

    # ---- mutation ----
    def add(self, entry: dict) -> VoiceProfile:
        profile = VoiceProfile.from_dict(entry)
        self._profiles[profile.id] = profile
        return profile

    def remove(self, voice_id: str) -> None:
        if voice_id not in self._profiles:
            raise VoiceNotFound(f"voice '{voice_id}' not in registry")
        del self._profiles[voice_id]

    # ---- engine factory ----
    @staticmethod
    def _engine_for(profile: VoiceProfile) -> VoiceEngine:
        if profile.engine == "edge":
            return EdgeEngine()
        if profile.engine == "cosyvoice":
            from pipeline.voices.cosy_engine import CosyVoiceEngine

            return CosyVoiceEngine()
        raise VoiceNotFound(f"unknown engine '{profile.engine}' for voice {profile.id}")
```

Also modify `src/pipeline/config.py` to add a `voices_dir` field:

```python
from pathlib import Path

# Inside PipelineConfig, alongside other path fields:
voices_dir: Path = Path("voices")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_voice_registry.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Seed the repo's voice registry**

Create `voices/registry.json`:

```json
{
  "voices": [
    {
      "id": "zh-TW-default-f",
      "engine": "edge",
      "locale": "zh-TW",
      "params": {"voice": "zh-TW-HsiaoChenNeural"},
      "display_name": "HsiaoChen (edge, default)"
    },
    {
      "id": "zh-TW-default-m",
      "engine": "edge",
      "locale": "zh-TW",
      "params": {"voice": "zh-TW-YunJheNeural"},
      "display_name": "YunJhe (edge)"
    },
    {
      "id": "ja-default-f",
      "engine": "edge",
      "locale": "ja",
      "params": {"voice": "ja-JP-NanamiNeural"},
      "display_name": "Nanami (edge, default)"
    },
    {
      "id": "es-MX-default-f",
      "engine": "edge",
      "locale": "es-MX",
      "params": {"voice": "es-MX-DaliaNeural"},
      "display_name": "Dalia (edge, default)"
    }
  ]
}
```

Create empty placeholders:

```bash
mkdir -p voices/edge voices/cloned
touch voices/edge/.gitkeep voices/cloned/.gitkeep
```

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/voices/registry.py src/pipeline/config.py voices/registry.json voices/edge/.gitkeep voices/cloned/.gitkeep tests/unit/test_voice_registry.py
git commit -m "feat(voices): add VoiceRegistry and seed edge voice catalog"
```

---

## Task 4: CosyVoice installer + engine stub

**Files:**
- Create: `scripts/install_cosyvoice.sh`
- Create: `src/pipeline/voices/cosy_engine.py`
- Modify: `pyproject.toml` (optional deps)
- Test: `tests/unit/test_cosy_engine.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_cosy_engine.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pipeline.voices.base import VoiceProfile
from pipeline.voices.cosy_engine import CosyVoiceEngine


def test_cosy_engine_requires_reference(tmp_path):
    profile = VoiceProfile(
        id="tim-zhtw",
        engine="cosyvoice",
        locale="zh-TW",
        params={},
    )
    with pytest.raises(ValueError):
        CosyVoiceEngine().synthesize("你好", tmp_path / "out.wav", profile)


def test_cosy_engine_invokes_model(tmp_path, monkeypatch):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF-stub")

    profile = VoiceProfile(
        id="tim-zhtw",
        engine="cosyvoice",
        locale="zh-TW",
        params={},
        reference_path=ref,
        reference_text="大家好",
    )

    fake_model = MagicMock()

    def fake_inference(text, prompt_text, prompt_audio, **_kwargs):
        # CosyVoice yields one or more result dicts with a `tts_speech` tensor
        yield {"tts_speech": MagicMock()}

    fake_model.inference_zero_shot.side_effect = fake_inference
    fake_save = MagicMock()

    monkeypatch.setattr(
        "pipeline.voices.cosy_engine._load_model",
        lambda: fake_model,
    )
    monkeypatch.setattr(
        "pipeline.voices.cosy_engine._save_tensor",
        fake_save,
    )

    out = tmp_path / "out.wav"
    result = CosyVoiceEngine().synthesize("你好世界", out, profile)

    assert result == out
    fake_model.inference_zero_shot.assert_called_once()
    fake_save.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cosy_engine.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the engine (lazy-loaded)**

Create `src/pipeline/voices/cosy_engine.py`:

```python
from __future__ import annotations

import logging
from pathlib import Path

from pipeline.voices.base import VoiceEngine, VoiceProfile

logger = logging.getLogger(__name__)

_MODEL = None  # module-level cache to avoid reloading between scenes


def _load_model():
    """Lazy import + load CosyVoice2. Heavy — cached after first call."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        from cosyvoice.cli.cosyvoice import CosyVoice2  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "CosyVoice2 is not installed. Run scripts/install_cosyvoice.sh first."
        ) from exc
    logger.info("loading CosyVoice2 model (one-time, ~seconds)")
    _MODEL = CosyVoice2("pretrained_models/CosyVoice2-0.5B", load_jit=False)
    return _MODEL


def _save_tensor(tensor, out_path: Path, sample_rate: int = 24000) -> None:
    import torchaudio  # lazy

    torchaudio.save(str(out_path), tensor, sample_rate)


class CosyVoiceEngine(VoiceEngine):
    @property
    def name(self) -> str:
        return "cosyvoice"

    def synthesize(self, text: str, out_path: Path, profile: VoiceProfile) -> Path:
        if profile.reference_path is None:
            raise ValueError(
                f"cosyvoice profile {profile.id} requires a reference audio file"
            )
        if not profile.reference_path.exists():
            raise FileNotFoundError(
                f"reference audio not found for {profile.id}: {profile.reference_path}"
            )

        import torchaudio  # lazy

        model = _load_model()
        prompt_audio, _sr = torchaudio.load(str(profile.reference_path))

        result_tensor = None
        for chunk in model.inference_zero_shot(
            text,
            profile.reference_text or "",
            prompt_audio,
            stream=False,
        ):
            # Concatenate chunks if model streams multiple
            piece = chunk["tts_speech"]
            result_tensor = piece if result_tensor is None else _concat(result_tensor, piece)

        if result_tensor is None:
            raise RuntimeError("CosyVoice2 produced no audio output")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        _save_tensor(result_tensor, out_path)
        return out_path


def _concat(a, b):
    import torch  # lazy

    return torch.cat([a, b], dim=-1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cosy_engine.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Write the installer script**

Create `scripts/install_cosyvoice.sh` and make it executable:

```bash
#!/usr/bin/env bash
# Install CosyVoice2 into a local directory for voice cloning.
# Run once per workstation. Requires ~5 GB disk + a working CUDA or CPU torch.
set -euo pipefail

TARGET="${COSYVOICE_DIR:-$HOME/.local/share/CosyVoice}"
MODEL_DIR="$TARGET/pretrained_models/CosyVoice2-0.5B"

echo "Installing CosyVoice2 to $TARGET"
mkdir -p "$TARGET"

if [ ! -d "$TARGET/.git" ]; then
  git clone --depth 1 https://github.com/FunAudioLLM/CosyVoice.git "$TARGET"
else
  echo "Repo already present; pulling latest"
  (cd "$TARGET" && git pull --ff-only)
fi

cd "$TARGET"

# Install the Python deps that CosyVoice bundles.
uv pip install --python "$(command -v python3)" -r requirements.txt

# Download the 0.5B model weights (Hugging Face mirror).
if [ ! -d "$MODEL_DIR" ]; then
  echo "Downloading CosyVoice2-0.5B weights"
  uv run python3 -c "
from modelscope import snapshot_download
snapshot_download('iic/CosyVoice2-0.5B', local_dir='$MODEL_DIR')
"
fi

echo ""
echo "Done. Add this to your shell rc:"
echo "  export PYTHONPATH=\"$TARGET:$TARGET/third_party/Matcha-TTS:\$PYTHONPATH\""
```

Run: `chmod +x scripts/install_cosyvoice.sh`

- [ ] **Step 6: Mark CosyVoice deps as optional in `pyproject.toml`**

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
cosyvoice = [
    "torch>=2.0.1",
    "torchaudio>=2.0.2",
]
```

The heavy CosyVoice repo itself is installed via the shell script (not pip-installable as a package), so the optional extra only covers the torch pair that the engine imports.

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/voices/cosy_engine.py scripts/install_cosyvoice.sh pyproject.toml tests/unit/test_cosy_engine.py
git commit -m "feat(voices): add CosyVoiceEngine + installer script"
```

---

## Task 5: Refactor `tts` stage to use the registry

**Files:**
- Modify: `src/pipeline/stages/tts.py`
- Modify: `src/pipeline/stages/base.py` (add `voice_id` field)
- Modify: `tests/unit/test_tts.py`

- [ ] **Step 1: Read current files**

Read `src/pipeline/stages/tts.py` and `tests/unit/test_tts.py` to understand the existing shape of `TtsStage` and its tests.

- [ ] **Step 2: Add `voice_id` to `PipelineContext`**

Edit `src/pipeline/stages/base.py`. In the `@dataclass PipelineContext`, add (alongside other optional fields — pick the TTS section):

```python
    # Stage 4: TTS
    narration_path: Path | None = None
    subtitle_path: Path | None = None
    segment_timings: list[dict[str, Any]] | None = None
    voice_id: str | None = None
```

No other change to that file.

- [ ] **Step 3: Write the failing test**

Add to `tests/unit/test_tts.py`:

```python
import asyncio

from pipeline.stages.base import PipelineContext
from pipeline.stages.tts import TtsStage


def test_tts_stage_uses_registry_for_voice_id(tmp_path, monkeypatch):
    work_dir = tmp_path
    storyboard = work_dir / "storyboard.json"
    storyboard.write_text(
        '{"scenes": [{"id": "s1", "section": "hook", '
        '"narration": "你好", "narration_est_sec": 2, "facts_ref": [], '
        '"visual": {"type": "text_card", "text": "hi"}, "overlay": null, "pause_after_sec": 0}], '
        '"theme": {}, "target_duration_sec": 30, "locale": "zh-TW"}'
    )

    # Stub the engine so we never touch the network.
    calls = {"synthesize": 0}

    class _StubEngine:
        @property
        def name(self):
            return "edge"

        def synthesize(self, text, out_path, profile):
            calls["synthesize"] += 1
            out_path.write_bytes(b"FAKE-MP3")
            return out_path

    def fake_resolve(self, voice_id):
        from pipeline.voices.base import VoiceProfile
        return _StubEngine(), VoiceProfile(
            id=voice_id, engine="edge", locale="zh-TW", params={"voice": "x"}
        )

    monkeypatch.setattr(
        "pipeline.voices.registry.VoiceRegistry.resolve", fake_resolve
    )

    ctx = PipelineContext(
        project_id=1,
        source_url="https://example/x",
        locale="zh-TW",
        work_dir=work_dir,
        voice_id="zh-TW-default-f",
        storyboard_path=storyboard,
    )
    asyncio.run(TtsStage().run(ctx))

    assert calls["synthesize"] >= 1
    assert ctx.narration_path is not None
    assert ctx.narration_path.exists()
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_tts.py::test_tts_stage_uses_registry_for_voice_id -v`
Expected: FAIL (either `voice_id` unknown or synthesize not called).

- [ ] **Step 5: Refactor `TtsStage.run`**

Edit `src/pipeline/stages/tts.py`. Replace the block that calls `generate_edge_tts(...)` per scene with:

```python
from pipeline.config import PipelineConfig
from pipeline.voices.registry import VoiceRegistry


class TtsStage(PipelineStage):
    @property
    def name(self) -> str:
        return "tts"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        # ... existing storyboard-load code stays ...

        cfg = PipelineConfig()
        registry = VoiceRegistry(cfg.voices_dir)

        if ctx.voice_id:
            engine, profile = registry.resolve(ctx.voice_id)
        else:
            engine, profile = registry.default_for_locale(ctx.locale)

        # ... for each scene:
        engine.synthesize(scene.narration, scene_mp3_path, profile)

        # ... rest of stage (concatenation, subtitles) unchanged ...
```

Keep every other existing behavior (subtitle generation, segment timings, concatenation). Delete the now-unused import of `generate_edge_tts` if nothing else references it — otherwise leave it.

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_tts.py -v`
Expected: PASS (new test and all prior tests).

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/stages/tts.py src/pipeline/stages/base.py tests/unit/test_tts.py
git commit -m "feat(tts): resolve voice via registry, add voice_id to context"
```

---

## Task 6: CLI — `voice list | add | remove | test`

**Files:**
- Create: `src/pipeline/cli_voice.py`
- Create: `tests/unit/test_voice_cli.py`
- Modify: `src/pipeline/cli.py` (register subcommand)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_voice_cli.py`:

```python
from __future__ import annotations

import json

from typer.testing import CliRunner

from pipeline.cli_voice import voice_app


def _init_voices(tmp_path):
    voices = tmp_path / "voices"
    voices.mkdir()
    (voices / "registry.json").write_text(
        json.dumps(
            {
                "voices": [
                    {
                        "id": "zh-TW-default-f",
                        "engine": "edge",
                        "locale": "zh-TW",
                        "params": {"voice": "zh-TW-HsiaoChenNeural"},
                        "display_name": "HsiaoChen",
                    }
                ]
            }
        )
    )
    return voices


def test_voice_list_shows_registry(tmp_path, monkeypatch):
    voices = _init_voices(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(voice_app, ["list"])
    assert result.exit_code == 0
    assert "zh-TW-default-f" in result.stdout
    assert "HsiaoChen" in result.stdout


def test_voice_add_persists_entry(tmp_path, monkeypatch):
    voices = _init_voices(tmp_path)
    monkeypatch.chdir(tmp_path)
    ref = voices / "cloned" / "tim.wav"
    ref.parent.mkdir(parents=True)
    ref.write_bytes(b"RIFF-stub")

    result = CliRunner().invoke(
        voice_app,
        [
            "add",
            "--id", "tim-zhtw",
            "--engine", "cosyvoice",
            "--locale", "zh-TW",
            "--reference", str(ref),
            "--reference-text", "大家好",
            "--display-name", "Tim",
        ],
    )
    assert result.exit_code == 0, result.stdout

    data = json.loads((voices / "registry.json").read_text())
    ids = [v["id"] for v in data["voices"]]
    assert "tim-zhtw" in ids


def test_voice_remove_deletes_entry(tmp_path, monkeypatch):
    voices = _init_voices(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(voice_app, ["remove", "zh-TW-default-f"])
    assert result.exit_code == 0, result.stdout
    data = json.loads((voices / "registry.json").read_text())
    assert data["voices"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_voice_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: pipeline.cli_voice`.

- [ ] **Step 3: Implement the CLI**

Create `src/pipeline/cli_voice.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from pipeline.config import PipelineConfig
from pipeline.voices.base import VoiceNotFound
from pipeline.voices.registry import VoiceRegistry

voice_app = typer.Typer(help="Manage voice profiles for TTS.")


def _registry() -> VoiceRegistry:
    cfg = PipelineConfig()
    return VoiceRegistry(cfg.voices_dir)


@voice_app.command("list")
def list_voices() -> None:
    """List all voice profiles in the registry."""
    registry = _registry()
    profiles = registry.list()
    if not profiles:
        typer.echo("(no voices configured)")
        raise typer.Exit()
    for p in profiles:
        label = p.display_name or p.id
        typer.echo(f"- {p.id}  [{p.engine}/{p.locale}]  {label}")


@voice_app.command("add")
def add_voice(
    id: str = typer.Option(..., "--id"),
    engine: str = typer.Option(..., "--engine", help="edge | cosyvoice"),
    locale: str = typer.Option(..., "--locale"),
    reference: Optional[Path] = typer.Option(None, "--reference"),
    reference_text: Optional[str] = typer.Option(None, "--reference-text"),
    display_name: Optional[str] = typer.Option(None, "--display-name"),
    param: list[str] = typer.Option([], "--param", help="key=value, repeatable"),
) -> None:
    """Add a new voice profile to the registry."""
    params: dict[str, str] = {}
    for p in param:
        if "=" not in p:
            raise typer.BadParameter(f"--param must be key=value, got {p!r}")
        k, v = p.split("=", 1)
        params[k] = v

    registry = _registry()
    entry = {
        "id": id,
        "engine": engine,
        "locale": locale,
        "params": params,
    }
    if reference is not None:
        entry["reference"] = str(reference)
    if reference_text is not None:
        entry["reference_text"] = reference_text
    if display_name is not None:
        entry["display_name"] = display_name

    registry.add(entry)
    registry.save()
    typer.echo(f"added {id}")


@voice_app.command("remove")
def remove_voice(voice_id: str) -> None:
    """Remove a voice profile from the registry."""
    registry = _registry()
    try:
        registry.remove(voice_id)
    except VoiceNotFound as exc:
        raise typer.BadParameter(str(exc))
    registry.save()
    typer.echo(f"removed {voice_id}")


@voice_app.command("test")
def test_voice(
    voice_id: str,
    text: str = typer.Option("測試一二三", "--text"),
    out: Path = typer.Option(Path("voice_test.mp3"), "--out"),
) -> None:
    """Synthesize a short sample for a voice profile."""
    registry = _registry()
    engine, profile = registry.resolve(voice_id)
    engine.synthesize(text, out, profile)
    typer.echo(f"wrote {out}")
```

- [ ] **Step 4: Register the subcommand in `cli.py`**

Edit `src/pipeline/cli.py`. At the top with other imports add:

```python
from pipeline.cli_voice import voice_app
```

After the main `app = typer.Typer(...)` creation add:

```python
app.add_typer(voice_app, name="voice")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_voice_cli.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Manual smoke test**

Run: `uv run pipeline voice list`
Expected: Lists the 4 seeded edge voices from `voices/registry.json`.

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/cli_voice.py src/pipeline/cli.py tests/unit/test_voice_cli.py
git commit -m "feat(voices): add voice list/add/remove/test CLI"
```

---

## Task 7: Expose `--voice` flag on `produce`

**Files:**
- Modify: `src/pipeline/cli.py`
- Test: manual via `uv run pipeline produce --help`

- [ ] **Step 1: Add the flag**

Edit the `produce` command in `src/pipeline/cli.py`. Add a new parameter:

```python
voice: str | None = typer.Option(
    None, "--voice", help="Voice profile id (see `pipeline voice list`)."
),
```

Inside the command body, after `ctx` is constructed (or before it is first passed to a stage), set:

```python
ctx.voice_id = voice
```

If `produce` builds a fresh `PipelineContext`, pass `voice_id=voice` directly to the constructor instead.

- [ ] **Step 2: Verify help output**

Run: `uv run pipeline produce --help`
Expected: Shows `--voice` option in the help listing.

- [ ] **Step 3: Run the existing CLI tests**

Run: `uv run pytest tests/unit/ -q -k "cli"`
Expected: No regressions.

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/cli.py
git commit -m "feat(cli): add --voice flag to produce command"
```

---

## Task 8: Recording guide + `/produce` skill docs

**Files:**
- Create: `scripts/record_voice.md`
- Modify: `.claude/commands/produce.md`

- [ ] **Step 1: Write the recording guide**

Create `scripts/record_voice.md`:

```markdown
# Recording a voice sample for CosyVoice2

## Target

A single 30–60 second WAV clip that captures your natural narration voice.
This becomes the reference audio for zero-shot cloning.

## Equipment

- Any decent USB mic or headset (Blue Yeti, Shure MV7, AirPods Pro all work).
- A quiet room (no fan, no TV, no AC hum).
- `arecord` on Linux, QuickTime Player on macOS, or Audacity cross-platform.

## Procedure

1. Run `scripts/install_cosyvoice.sh` once per workstation.
2. Pick a unique voice id, e.g. `tim-zhtw`, and prepare an empty file:
   `voices/cloned/tim-zhtw.wav`.
3. Read the script below at your natural cadence. Do not rush.
4. Save the file as **16 kHz mono PCM WAV** (CosyVoice2 will resample internally
   but 16 kHz avoids quality surprises).
5. Register the voice:

   ```bash
   uv run pipeline voice add \
     --id tim-zhtw \
     --engine cosyvoice \
     --locale zh-TW \
     --reference voices/cloned/tim-zhtw.wav \
     --reference-text "大家好，歡迎來到今天的影片。..." \
     --display-name "Tim (zh-TW clone)"
   ```

6. Smoke test:

   ```bash
   uv run pipeline voice test tim-zhtw --text "測試一二三" --out /tmp/tim_test.wav
   ```

## Reference script (zh-TW, ~45 seconds)

> 大家好，歡迎來到今天的影片。今天我想跟各位分享一個非常有趣的研究。
> 在人工智慧快速發展的時代，我們常常聽到像是 GPT、Claude 這些名字。
> 但你知道嗎？讓 AI 真正能夠寫出完整應用程式的關鍵，其實不在於模型本身，
> 而在於整個系統的設計。從規劃、執行到評估，每一個環節都不能少。
> 那麼，接下來就讓我們一起來看看，研究員到底是怎麼做到的？

Use this exact text as `--reference-text` — CosyVoice2 matches the prosody of
the recording to the text, so the two must line up.
```

- [ ] **Step 2: Document `--voice` in the produce skill**

Edit `.claude/commands/produce.md`. Under the **Step 6: Render** section, update the render command to accept an optional voice:

```bash
uv run pipeline produce --url "<URL>" --project-id <ID> --locale <LOCALE> \
  --voice <voice-id-or-omit-for-default> --start-from tts --skip-review
```

And add a new section **"Voice selection"** right after the **Input** section at the top:

```markdown
## Voice selection

- Default: the registry picks the locale default (edge-tts).
- Override with `--voice <id>` to use a cloned voice (e.g. `tim-zhtw`).
- List available voices: `uv run pipeline voice list`.
- To record a new voice, see `scripts/record_voice.md`.
- If the user has not said otherwise, always use the default voice.
```

- [ ] **Step 3: Commit**

```bash
git add scripts/record_voice.md .claude/commands/produce.md
git commit -m "docs(voices): add recording guide and update produce skill"
```

---

## Done criteria

- `uv run pytest tests/unit/test_voice_registry.py tests/unit/test_edge_engine.py tests/unit/test_cosy_engine.py tests/unit/test_voice_cli.py tests/unit/test_tts.py -v` is green.
- `uv run pipeline voice list` prints the 4 seeded edge voices.
- `uv run pipeline produce --help` shows the `--voice` flag.
- `scripts/install_cosyvoice.sh` exists and is executable.
- `.claude/commands/produce.md` documents voice selection.
- No direct call to `generate_edge_tts` remains in `src/pipeline/stages/`.
