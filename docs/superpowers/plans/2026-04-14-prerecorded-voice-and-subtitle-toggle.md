# Prerecorded Voice Engine + Subtitle Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `PrerecordedEngine` that uses creator-recorded audio per scene (falling back to Edge-TTS), add a `--subtitles / --no-subtitles` flag on `produce` (default off), add storyboard helper CLIs, and roll back the unreachable CosyVoice engine.

**Architecture:** Reuse the existing `VoiceEngine` abstraction. Extend `synthesize` with an optional `scene_id`. Add `PrerecordedEngine` that looks up `voices/prerecorded/<voice_id>/<scene_id>.{wav,mp3,m4a}`, transcodes to MP3 for concat compatibility, and delegates to a fallback Edge profile when a scene has no recording. Drift detection is a sibling `<scene_id>.txt` snapshot of the narration text — when it differs from the live text, warn but still use the recording. Thread a `burn_subtitles` flag through `PipelineContext` → `ComposeStage`.

**Tech Stack:** existing edge-tts, Typer CLI, pytest with monkeypatch for ffmpeg stubbing, rich tables for storyboard views, structlog.

**Spec:** `docs/superpowers/specs/2026-04-14-prerecorded-voice-and-subtitle-toggle-design.md`.

---

## File Structure

**New:**
- `src/pipeline/voices/prerecorded_engine.py` — `PrerecordedEngine`
- `src/pipeline/cli_storyboard.py` — `storyboard show/recordings/set` Typer group
- `tests/unit/test_prerecorded_engine.py`
- `tests/unit/test_storyboard_cli.py`
- `tests/integration/test_prerecorded_end_to_end.py` — single real-ffmpeg smoke test
- `tests/fixtures/short_narration.wav` — 1s silence, mono 16kHz
- `voices/prerecorded/.gitkeep`

**Modified:**
- `src/pipeline/voices/base.py` — `synthesize` gains `scene_id: str | None = None`
- `src/pipeline/voices/edge_engine.py` — accept and ignore `scene_id`
- `src/pipeline/voices/registry.py` — remove `cosyvoice` branch; add `prerecorded` branch; pass registry handle to `PrerecordedEngine`
- `src/pipeline/stages/tts.py` — pass `scene.id` to `engine.synthesize`
- `src/pipeline/stages/base.py` — add `burn_subtitles: bool = True` to `PipelineContext`
- `src/pipeline/stages/compose.py` — conditional subtitle burn pass; thread `burn_subtitles` into `check_overlay_allowed`
- `src/pipeline/cli.py` — add `--subtitles / --no-subtitles` flag to `produce` (default off); register `storyboard` typer group
- `src/pipeline/cli_voice.py` — accept `engine=prerecorded` with `--recording-dir` and `--fallback-voice` flags; drop cosyvoice mentions
- `pyproject.toml` — delete `[project.optional-dependencies].cosyvoice`
- `CLAUDE.md` — Commands section: add storyboard subcommands + natural-language triggers
- `scripts/record_voice.md` — rewrite for prerecorded workflow
- `tests/unit/test_tts.py` — add case: prerecorded voice with one recording + one missing
- `tests/unit/test_voice_registry.py` — prerecorded branch returns engine; cosyvoice raises
- `tests/unit/test_voice_cli.py` — drop cosyvoice; add prerecorded add path

**Deleted:**
- `src/pipeline/voices/cosy_engine.py`
- `tests/unit/test_cosy_engine.py`
- `scripts/install_cosyvoice.sh`

---

## Task 1: Roll back CosyVoice

**Files:**
- Delete: `src/pipeline/voices/cosy_engine.py`
- Delete: `tests/unit/test_cosy_engine.py`
- Delete: `scripts/install_cosyvoice.sh`
- Modify: `src/pipeline/voices/registry.py` (remove cosyvoice branch)
- Modify: `src/pipeline/cli_voice.py` (help text: `edge | cosyvoice` → `edge`)
- Modify: `pyproject.toml` (drop `cosyvoice` extras)
- Modify: `src/pipeline/voices/base.py` (comment: `"edge" | "cosyvoice"` → `"edge"`)

- [ ] **Step 1: Verify no production voice uses cosyvoice**

Run: `grep -r "cosyvoice" voices/ 2>&1`
Expected: no matches in `voices/registry.json`.

- [ ] **Step 2: Delete CosyVoice files**

```bash
rm src/pipeline/voices/cosy_engine.py
rm tests/unit/test_cosy_engine.py
rm scripts/install_cosyvoice.sh
```

- [ ] **Step 3: Remove cosyvoice branch from registry**

Edit `src/pipeline/voices/registry.py`. Replace the entire `_engine_for` method with:

```python
    @staticmethod
    def _engine_for(profile: VoiceProfile) -> VoiceEngine:
        if profile.engine == "edge":
            return EdgeEngine()
        raise VoiceNotFound(f"unknown engine '{profile.engine}' for voice {profile.id}")
```

(We'll re-add the `prerecorded` branch in Task 5.)

- [ ] **Step 4: Update comments and help text**

In `src/pipeline/voices/base.py` line 16, change:

```python
    engine: str  # "edge" | "cosyvoice"
```

to:

```python
    engine: str  # "edge" | "prerecorded"
```

In `src/pipeline/cli_voice.py` line 36, change:

```python
    engine: str = typer.Option(..., "--engine", help="edge | cosyvoice"),
```

to:

```python
    engine: str = typer.Option(..., "--engine", help="edge | prerecorded"),
```

- [ ] **Step 5: Remove cosyvoice optional deps from `pyproject.toml`**

Delete the block:

```toml
[project.optional-dependencies]
cosyvoice = [
    "torch>=2.0.1",
    "torchaudio>=2.0.2",
]
```

If there are no other entries in `[project.optional-dependencies]`, remove the whole section. If there are other entries, keep the header and delete only the `cosyvoice = [...]` lines.

- [ ] **Step 6: Run test suite**

Run: `uv run pytest tests/unit/ -x -q`
Expected: all remaining tests pass. No references to deleted cosyvoice test file.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore(voices): remove CosyVoice engine + installer

Shelved — requires GPU + CUDA driver we don't have; hosted cloning
is a future option. Keep engine abstraction intact."
```

---

## Task 2: Extend `VoiceEngine.synthesize` with optional `scene_id`

**Files:**
- Modify: `src/pipeline/voices/base.py`
- Modify: `src/pipeline/voices/edge_engine.py`
- Test: `tests/unit/test_voice_registry.py` (add a signature test)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_voice_registry.py`:

```python
from pipeline.voices.edge_engine import EdgeEngine


def test_edge_engine_accepts_optional_scene_id(tmp_path, monkeypatch):
    """EdgeEngine ignores scene_id but must not reject it."""
    called = {}

    def fake_save(self, path):
        called["path"] = path
        Path(path).write_bytes(b"fake-mp3")

    async def fake_run(cls, text, voice, out_path):
        out_path.write_bytes(b"fake-mp3")

    monkeypatch.setattr(EdgeEngine, "_run", classmethod(fake_run))

    profile = VoiceProfile(
        id="t",
        engine="edge",
        locale="zh-TW",
        params={"voice": "zh-TW-HsiaoChenNeural"},
    )
    out = tmp_path / "a.mp3"
    # Must not raise:
    EdgeEngine().synthesize("你好", out, profile, scene_id="scene_001")
    assert out.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_voice_registry.py::test_edge_engine_accepts_optional_scene_id -v`
Expected: FAIL — `synthesize()` got unexpected keyword `scene_id`.

- [ ] **Step 3: Update `VoiceEngine` ABC signature**

In `src/pipeline/voices/base.py`, replace the abstract method:

```python
    @abstractmethod
    def synthesize(
        self,
        text: str,
        out_path: Path,
        profile: VoiceProfile,
        scene_id: str | None = None,
    ) -> Path:
        """Write audio for `text` to `out_path`. Returns the final path.

        `scene_id` is the storyboard scene identifier, passed down by TtsStage.
        Engines that key off scene identity (e.g. PrerecordedEngine) use it;
        others ignore it.
        """
```

- [ ] **Step 4: Update `EdgeEngine` signature**

In `src/pipeline/voices/edge_engine.py`, replace the `synthesize` method:

```python
    def synthesize(
        self,
        text: str,
        out_path: Path,
        profile: VoiceProfile,
        scene_id: str | None = None,
    ) -> Path:
        _ = scene_id  # unused: edge voices are scene-agnostic
        voice = profile.params.get("voice")
        if not voice:
            raise ValueError(f"edge voice profile {profile.id} is missing params.voice")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(self._run(text, voice, out_path))
        return out_path
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_voice_registry.py -v`
Expected: all tests PASS including the new one.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/voices/base.py src/pipeline/voices/edge_engine.py tests/unit/test_voice_registry.py
git commit -m "refactor(voices): add optional scene_id to VoiceEngine.synthesize"
```

---

## Task 3: Add `burn_subtitles` to `PipelineContext`

**Files:**
- Modify: `src/pipeline/stages/base.py`

- [ ] **Step 1: Add field to `PipelineContext`**

In `src/pipeline/stages/base.py`, find the `# Stage 5: Compose` section (around line 42). Replace:

```python
    # Stage 5: Compose
    final_video_path: Path | None = None
```

with:

```python
    # Stage 5: Compose
    final_video_path: Path | None = None
    burn_subtitles: bool = True
```

- [ ] **Step 2: Verify tests still pass**

Run: `uv run pytest tests/unit/ -x -q`
Expected: all existing tests PASS. The new field has a default, so no existing construction sites break.

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/stages/base.py
git commit -m "feat(pipeline): add burn_subtitles flag to PipelineContext"
```

---

## Task 4: Implement `PrerecordedEngine`

**Files:**
- Create: `src/pipeline/voices/prerecorded_engine.py`
- Create: `tests/unit/test_prerecorded_engine.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_prerecorded_engine.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pipeline.voices.base import VoiceProfile
from pipeline.voices.prerecorded_engine import PrerecordedEngine


def _mk_profile(tmp_path: Path, fallback: str | None = "zh-TW-default-f") -> VoiceProfile:
    rec_dir = tmp_path / "rec"
    rec_dir.mkdir()
    params = {"recording_dir": str(rec_dir)}
    if fallback is not None:
        params["fallback_voice_id"] = fallback
    return VoiceProfile(
        id="tim-zhtw",
        engine="prerecorded",
        locale="zh-TW",
        params=params,
    )


class _FakeFallbackEngine:
    @property
    def name(self) -> str:
        return "edge"

    def synthesize(self, text, out_path, profile, scene_id=None):
        Path(out_path).write_bytes(b"fallback-mp3")
        self.last = (text, out_path, profile.id, scene_id)
        return out_path


class _FakeRegistry:
    def __init__(self, fallback_profile: VoiceProfile):
        self._fallback_profile = fallback_profile
        self._fallback_engine = _FakeFallbackEngine()

    def resolve(self, voice_id):
        return self._fallback_engine, self._fallback_profile

    def default_for_locale(self, locale):
        return self._fallback_engine, self._fallback_profile


def _fallback_profile():
    return VoiceProfile(
        id="zh-TW-default-f",
        engine="edge",
        locale="zh-TW",
        params={"voice": "zh-TW-HsiaoChenNeural"},
    )


def test_requires_scene_id(tmp_path):
    engine = PrerecordedEngine(registry=_FakeRegistry(_fallback_profile()))
    with pytest.raises(ValueError, match="scene_id"):
        engine.synthesize("你好", tmp_path / "out.mp3", _mk_profile(tmp_path), scene_id=None)


def test_missing_recording_delegates_to_fallback(tmp_path):
    reg = _FakeRegistry(_fallback_profile())
    engine = PrerecordedEngine(registry=reg)
    out = tmp_path / "out.mp3"
    engine.synthesize("你好", out, _mk_profile(tmp_path), scene_id="scene_001")
    assert out.read_bytes() == b"fallback-mp3"
    assert reg._fallback_engine.last[3] == "scene_001"


def test_missing_fallback_voice_id_uses_default_for_locale(tmp_path):
    fb_prof = _fallback_profile()
    reg = _FakeRegistry(fb_prof)
    called = {}
    orig = reg.default_for_locale

    def spy(locale):
        called["locale"] = locale
        return orig(locale)

    reg.default_for_locale = spy

    engine = PrerecordedEngine(registry=reg)
    out = tmp_path / "out.mp3"
    engine.synthesize(
        "你好", out, _mk_profile(tmp_path, fallback=None), scene_id="scene_001"
    )
    assert called["locale"] == "zh-TW"


def test_found_recording_transcodes_and_writes_snapshot(tmp_path, monkeypatch):
    profile = _mk_profile(tmp_path)
    rec_dir = Path(profile.params["recording_dir"])
    (rec_dir / "scene_001.wav").write_bytes(b"RIFF-stub")

    fake_transcode = MagicMock()
    monkeypatch.setattr(
        "pipeline.voices.prerecorded_engine._transcode_to_mp3",
        fake_transcode,
    )

    engine = PrerecordedEngine(registry=_FakeRegistry(_fallback_profile()))
    out = tmp_path / "out.mp3"
    engine.synthesize("你好", out, profile, scene_id="scene_001")

    fake_transcode.assert_called_once()
    src_arg, dst_arg = fake_transcode.call_args[0]
    assert src_arg == rec_dir / "scene_001.wav"
    assert dst_arg == out
    assert (rec_dir / "scene_001.txt").read_text(encoding="utf-8").strip() == "你好"


def test_found_recording_with_matching_snapshot_no_warning(tmp_path, monkeypatch, caplog):
    import logging

    profile = _mk_profile(tmp_path)
    rec_dir = Path(profile.params["recording_dir"])
    (rec_dir / "scene_001.wav").write_bytes(b"RIFF-stub")
    (rec_dir / "scene_001.txt").write_text("你好\n", encoding="utf-8")

    monkeypatch.setattr(
        "pipeline.voices.prerecorded_engine._transcode_to_mp3",
        lambda src, dst: dst.write_bytes(b"mp3"),
    )

    caplog.set_level(logging.WARNING)
    engine = PrerecordedEngine(registry=_FakeRegistry(_fallback_profile()))
    engine.synthesize("你好", tmp_path / "out.mp3", profile, scene_id="scene_001")
    assert "stale_recording" not in caplog.text


def test_found_recording_with_drifted_snapshot_emits_warning(
    tmp_path, monkeypatch, caplog
):
    import logging

    profile = _mk_profile(tmp_path)
    rec_dir = Path(profile.params["recording_dir"])
    (rec_dir / "scene_001.wav").write_bytes(b"RIFF-stub")
    (rec_dir / "scene_001.txt").write_text("原始文字", encoding="utf-8")

    monkeypatch.setattr(
        "pipeline.voices.prerecorded_engine._transcode_to_mp3",
        lambda src, dst: dst.write_bytes(b"mp3"),
    )

    caplog.set_level(logging.WARNING)
    engine = PrerecordedEngine(registry=_FakeRegistry(_fallback_profile()))
    engine.synthesize("新文字", tmp_path / "out.mp3", profile, scene_id="scene_001")
    assert "stale_recording" in caplog.text


def test_missing_recording_dir_param_raises(tmp_path):
    profile = VoiceProfile(
        id="tim-zhtw",
        engine="prerecorded",
        locale="zh-TW",
        params={},  # missing recording_dir
    )
    engine = PrerecordedEngine(registry=_FakeRegistry(_fallback_profile()))
    with pytest.raises(ValueError, match="recording_dir"):
        engine.synthesize("你好", tmp_path / "out.mp3", profile, scene_id="scene_001")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_prerecorded_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.voices.prerecorded_engine'`.

- [ ] **Step 3: Implement the engine**

Create `src/pipeline/voices/prerecorded_engine.py`:

```python
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from pipeline.voices.base import VoiceEngine, VoiceProfile

if TYPE_CHECKING:
    from pipeline.voices.registry import VoiceRegistry

logger = logging.getLogger(__name__)

_SUPPORTED_EXTS = (".wav", ".mp3", ".m4a")


def _transcode_to_mp3(src: Path, dst: Path) -> None:
    """Transcode any ffmpeg-readable audio to MP3 at dst."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(dst),
        ],
        check=True,
        capture_output=True,
    )


def _find_recording(recording_dir: Path, scene_id: str) -> Path | None:
    for ext in _SUPPORTED_EXTS:
        candidate = recording_dir / f"{scene_id}{ext}"
        if candidate.exists():
            return candidate
    return None


class PrerecordedEngine(VoiceEngine):
    """Looks up scene-keyed recordings; falls back to another voice on miss."""

    def __init__(self, registry: "VoiceRegistry"):
        self._registry = registry

    @property
    def name(self) -> str:
        return "prerecorded"

    def synthesize(
        self,
        text: str,
        out_path: Path,
        profile: VoiceProfile,
        scene_id: str | None = None,
    ) -> Path:
        if scene_id is None:
            raise ValueError(
                "PrerecordedEngine requires scene_id; invoke via TtsStage"
            )

        recording_dir_str = profile.params.get("recording_dir")
        if not recording_dir_str:
            raise ValueError(
                f"prerecorded profile {profile.id} missing params.recording_dir"
            )
        recording_dir = Path(recording_dir_str)

        src = _find_recording(recording_dir, scene_id)

        if src is not None:
            self._handle_snapshot(recording_dir, scene_id, text)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            _transcode_to_mp3(src, out_path)
            logger.info(
                "prerecorded.used",
                extra={"scene_id": scene_id, "src": str(src)},
            )
            return out_path

        fallback_engine, fallback_profile = self._resolve_fallback(profile)
        logger.info(
            "prerecorded.fallback",
            extra={
                "scene_id": scene_id,
                "fallback_voice_id": fallback_profile.id,
            },
        )
        return fallback_engine.synthesize(text, out_path, fallback_profile, scene_id=scene_id)

    def _handle_snapshot(
        self, recording_dir: Path, scene_id: str, live_text: str
    ) -> None:
        snapshot_path = recording_dir / f"{scene_id}.txt"
        if not snapshot_path.exists():
            snapshot_path.write_text(live_text, encoding="utf-8")
            return
        recorded = snapshot_path.read_text(encoding="utf-8").strip()
        if recorded != live_text.strip():
            logger.warning(
                "prerecorded.stale_recording",
                extra={
                    "scene_id": scene_id,
                    "recorded_text": recorded,
                    "live_text": live_text,
                },
            )

    def _resolve_fallback(
        self, profile: VoiceProfile
    ) -> tuple[VoiceEngine, VoiceProfile]:
        fallback_id = profile.params.get("fallback_voice_id")
        if fallback_id:
            return self._registry.resolve(fallback_id)
        return self._registry.default_for_locale(profile.locale)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_prerecorded_engine.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/voices/prerecorded_engine.py tests/unit/test_prerecorded_engine.py
git commit -m "feat(voices): add PrerecordedEngine with Edge fallback"
```

---

## Task 5: Wire `PrerecordedEngine` into the registry

**Files:**
- Modify: `src/pipeline/voices/registry.py`
- Modify: `tests/unit/test_voice_registry.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_voice_registry.py`:

```python
def test_registry_resolves_prerecorded_engine(tmp_path):
    from pipeline.voices.prerecorded_engine import PrerecordedEngine
    from pipeline.voices.registry import VoiceRegistry

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        '{"voices": [{"id": "tim-zhtw", "engine": "prerecorded", '
        '"locale": "zh-TW", "params": {"recording_dir": "r"}}, '
        '{"id": "zh-TW-default-f", "engine": "edge", "locale": "zh-TW", '
        '"params": {"voice": "zh-TW-HsiaoChenNeural"}}]}',
        encoding="utf-8",
    )
    registry = VoiceRegistry(tmp_path)
    engine, profile = registry.resolve("tim-zhtw")
    assert isinstance(engine, PrerecordedEngine)
    assert profile.id == "tim-zhtw"


def test_registry_rejects_cosyvoice_engine(tmp_path):
    from pipeline.voices.base import VoiceNotFound
    from pipeline.voices.registry import VoiceRegistry

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        '{"voices": [{"id": "gone", "engine": "cosyvoice", '
        '"locale": "zh-TW", "params": {}}]}',
        encoding="utf-8",
    )
    registry = VoiceRegistry(tmp_path)
    with pytest.raises(VoiceNotFound, match="unknown engine 'cosyvoice'"):
        registry.resolve("gone")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_voice_registry.py::test_registry_resolves_prerecorded_engine -v`
Expected: FAIL — registry raises `VoiceNotFound` because `prerecorded` is unknown.

- [ ] **Step 3: Add prerecorded branch to registry**

In `src/pipeline/voices/registry.py`, replace the `_engine_for` static method with an instance method that has access to `self`:

```python
    def _engine_for(self, profile: VoiceProfile) -> VoiceEngine:
        if profile.engine == "edge":
            return EdgeEngine()
        if profile.engine == "prerecorded":
            from pipeline.voices.prerecorded_engine import PrerecordedEngine

            return PrerecordedEngine(registry=self)
        raise VoiceNotFound(f"unknown engine '{profile.engine}' for voice {profile.id}")
```

Update the two call sites in the same file — replace:

```python
            return self._engine_for(profile), profile
```

(both in `default_for_locale` and `resolve`). They already call `self._engine_for(profile)`, so no change needed there. But since we're converting from `@staticmethod` to instance method, double-check the current calls: they already look like `self._engine_for(profile)` — good.

Remove the `@staticmethod` decorator from the method.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_voice_registry.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/voices/registry.py tests/unit/test_voice_registry.py
git commit -m "feat(voices): registry resolves prerecorded engine"
```

---

## Task 6: Thread `scene_id` through `TtsStage`

**Files:**
- Modify: `src/pipeline/stages/tts.py`
- Modify: `tests/unit/test_tts.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_tts.py`:

```python
async def test_tts_passes_scene_id_to_engine(sample_context):
    """TtsStage must pass each scene's id to engine.synthesize so
    PrerecordedEngine can key lookups by scene."""
    from pipeline.voices.base import VoiceProfile

    scenes = [
        Scene(
            id="hook_1",
            section="hook",
            narration="段落一",
            narration_est_sec=2.0,
            visual={"type": "text_card", "text": "v1"},
        ),
        Scene(
            id="ctx_1",
            section="context",
            narration="段落二",
            narration_est_sec=2.0,
            visual={"type": "text_card", "text": "v2"},
        ),
    ]
    storyboard = Storyboard(scenes=scenes)
    storyboard_path = sample_context.work_dir / "storyboard.json"
    storyboard.save(storyboard_path)
    sample_context.storyboard_path = storyboard_path

    script_dir = sample_context.work_dir / "script"
    script_dir.mkdir()
    script_path = script_dir / "script_zh-TW.md"
    script_path.write_text(storyboard.derive_script(), encoding="utf-8")
    sample_context.script_path = script_path

    seen_scene_ids: list[str | None] = []

    class _SceneSpyEngine:
        @property
        def name(self):
            return "edge"

        def synthesize(self, text, out_path, profile, scene_id=None):
            seen_scene_ids.append(scene_id)
            out_path.write_bytes(b"x")
            return out_path

    stub_pair = (
        _SceneSpyEngine(),
        VoiceProfile(id="stub", engine="edge", locale="zh-TW", params={"voice": "x"}),
    )
    stage = TtsStage()

    with (
        patch("pipeline.stages.tts.VoiceRegistry") as mock_reg_cls,
        patch("pipeline.stages.tts._get_audio_duration_ms", return_value=1000),
    ):
        mock_reg_cls.return_value.default_for_locale.return_value = stub_pair
        await stage.run(sample_context)

    assert seen_scene_ids == ["hook_1", "ctx_1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_tts.py::test_tts_passes_scene_id_to_engine -v`
Expected: FAIL — `scene_ids` list is empty or contains None values because tts doesn't pass scene_id.

- [ ] **Step 3: Update `TtsStage.run` to pass scene.id**

In `src/pipeline/stages/tts.py`, the loop currently looks like:

```python
        for i, text in enumerate(segments):
            seg_path = audio_dir / f"segment_{i:03d}.mp3"
            engine.synthesize(text, seg_path, profile)
```

Replace it with:

```python
        # Scene ids align 1:1 with segments when the storyboard is present
        # (storyboard.derive_script emits one narration line per scene).
        scene_ids: list[str | None] = []
        if ctx.storyboard_path and ctx.storyboard_path.exists():
            from pipeline.storyboard import Storyboard

            storyboard_for_ids = Storyboard.load(ctx.storyboard_path)
            scene_ids = [s.id for s in storyboard_for_ids.scenes]

        for i, text in enumerate(segments):
            seg_path = audio_dir / f"segment_{i:03d}.mp3"
            scene_id = scene_ids[i] if i < len(scene_ids) else None
            engine.synthesize(text, seg_path, profile, scene_id=scene_id)
```

(The `Storyboard` is already loaded earlier in `run` for pause timing; we reload it here to keep the change localized. A refactor to load once is out of scope.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_tts.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/tts.py tests/unit/test_tts.py
git commit -m "feat(tts): pass scene.id into engine.synthesize"
```

---

## Task 7: Honor `burn_subtitles` in `ComposeStage`

**Files:**
- Modify: `src/pipeline/stages/compose.py`
- Modify: `tests/unit/test_compose_v2.py` (add a flag test)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_compose_v2.py`:

```python
def test_compose_no_subtitles_skips_burn(monkeypatch, tmp_path):
    """With burn_subtitles=False, compose copies raw.mp4 to final
    without invoking the -vf subtitles ffmpeg pass."""
    from pathlib import Path

    from pipeline.stages.base import PipelineContext
    from pipeline.stages.compose import ComposeStage
    from pipeline.storyboard import Scene, Storyboard

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    (work_dir / "audio").mkdir()
    narration = work_dir / "audio" / "narration.mp3"
    narration.write_bytes(b"mp3")
    subs = work_dir / "audio" / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")

    storyboard = Storyboard(
        scenes=[
            Scene(
                id="s1",
                section="hook",
                narration="x",
                narration_est_sec=1.0,
                visual={"type": "text_card", "text": "hi"},
            )
        ]
    )
    sb_path = work_dir / "storyboard.json"
    storyboard.save(sb_path)

    ctx = PipelineContext(
        project_id=1,
        source_url="x",
        locale="zh-TW",
        work_dir=work_dir,
        narration_path=narration,
        subtitle_path=subs,
        storyboard_path=sb_path,
        segment_timings=[
            {"index": 0, "text": "x", "path": str(narration), "start_ms": 0, "duration_ms": 1000}
        ],
        burn_subtitles=False,
    )

    ffmpeg_calls: list[list[str]] = []

    def capture(cmd):
        ffmpeg_calls.append(cmd)
        # simulate outputs:
        if "-i" in cmd and cmd[-1].endswith(".mp4"):
            Path(cmd[-1]).write_bytes(b"mp4")

    monkeypatch.setattr("pipeline.stages.compose.run_ffmpeg", capture)
    monkeypatch.setattr(
        "pipeline.stages.compose.check_ffmpeg_available", lambda: True
    )
    monkeypatch.setattr(
        "pipeline.composer.base.render_scene",
        lambda scene, theme, width, height, work_dir, duration=None: Path(work_dir)
        / f"{scene['id']}.mp4",
    )

    import asyncio

    asyncio.run(ComposeStage().run(ctx))

    # No ffmpeg call should include the subtitles filter.
    for cmd in ffmpeg_calls:
        joined = " ".join(cmd)
        assert "subtitles=" not in joined, f"subtitles filter found in: {joined}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_compose_v2.py::test_compose_no_subtitles_skips_burn -v`
Expected: FAIL — the current code unconditionally calls the subtitles filter at step 6.

- [ ] **Step 3: Update `ComposeStage._compose_from_storyboard`**

In `src/pipeline/stages/compose.py`, find the block starting at "# Step 6: Burn subtitles" (around line 236). Replace the existing step 6 block:

```python
        # Step 6: Burn subtitles
        final_path = compose_dir / f"final_{ctx.locale}.mp4"
        escaped_sub = str(ctx.subtitle_path).replace("\\", "\\\\").replace(":", "\\:")
        subtitle_style = "FontName=Noto Sans CJK TC,FontSize=24"
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(raw_path),
                "-vf",
                f"subtitles={escaped_sub}:force_style='{subtitle_style}'",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "23",
                "-c:a",
                "copy",
                str(final_path),
            ]
        )

        return final_path
```

with:

```python
        # Step 6: Burn subtitles (optional)
        final_path = compose_dir / f"final_{ctx.locale}.mp4"
        if ctx.burn_subtitles:
            escaped_sub = str(ctx.subtitle_path).replace("\\", "\\\\").replace(":", "\\:")
            subtitle_style = "FontName=Noto Sans CJK TC,FontSize=24"
            run_ffmpeg(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(raw_path),
                    "-vf",
                    f"subtitles={escaped_sub}:force_style='{subtitle_style}'",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "23",
                    "-c:a",
                    "copy",
                    str(final_path),
                ]
            )
        else:
            # No subtitle burn: raw.mp4 is already libx264/aac from scene finals.
            import shutil

            shutil.copyfile(raw_path, final_path)

        return final_path
```

Also update `_compose_mvp` (around line 262). Find the block where `-vf subtitles=...` appears (around line 290) and wrap it similarly. Find:

```python
        final_path = compose_dir / f"final_{ctx.locale}.mp4"
        escaped_sub = str(ctx.subtitle_path).replace("\\", "\\\\").replace(":", "\\:")
        subtitle_style = "FontName=Noto Sans CJK TC,FontSize=24"
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(start_offset),
                "-i",
                str(ctx.video_path),
                "-i",
                str(ctx.narration_path),
                "-t",
                str(narration_duration),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-vf",
                f"subtitles={escaped_sub}:force_style='{subtitle_style}'",
```

Modify to build the ffmpeg arg list conditionally:

```python
        final_path = compose_dir / f"final_{ctx.locale}.mp4"
        cmd: list[str] = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start_offset),
            "-i",
            str(ctx.video_path),
            "-i",
            str(ctx.narration_path),
            "-t",
            str(narration_duration),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
        ]
        if ctx.burn_subtitles:
            escaped_sub = str(ctx.subtitle_path).replace("\\", "\\\\").replace(":", "\\:")
            subtitle_style = "FontName=Noto Sans CJK TC,FontSize=24"
            cmd += ["-vf", f"subtitles={escaped_sub}:force_style='{subtitle_style}'"]
```

Then keep the remaining `-c:v libx264 ... str(final_path)` portion as one more `cmd += [...]` before calling `run_ffmpeg(cmd)`. Read the current file to see the exact trailing arg list and preserve it.

- [ ] **Step 4: Pass `burn_subtitles` to `check_overlay_allowed`**

In `src/pipeline/stages/compose.py`, find the call at around line 158-163:

```python
            check_overlay_allowed(
                scene=scene_dict,
                overlay=scene.overlay,
                visual=scene.visual,
                burn_subtitles=True,
            )
```

Replace with:

```python
            check_overlay_allowed(
                scene=scene_dict,
                overlay=scene.overlay,
                visual=scene.visual,
                burn_subtitles=ctx.burn_subtitles,
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_compose_v2.py -v`
Expected: all tests PASS including the new one.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/stages/compose.py tests/unit/test_compose_v2.py
git commit -m "feat(compose): skip subtitle burn when burn_subtitles=False"
```

---

## Task 8: Add `--subtitles / --no-subtitles` flag to `produce`

**Files:**
- Modify: `src/pipeline/cli.py`

- [ ] **Step 1: Add flag to `produce` command**

In `src/pipeline/cli.py`, add a flag to the `produce` function signature. Find the existing signature around line 24-35 and add after the `voice` option:

```python
    subtitles: bool = typer.Option(
        False,
        "--subtitles/--no-subtitles",
        help="Burn subtitles into the final video (default: off).",
    ),
```

- [ ] **Step 2: Thread the flag into the context**

In the same function, find where `ctx` is constructed or loaded:

```python
    if start_from and context_file.exists():
        ctx = PipelineContext.load(context_file)
        if voice:
            ctx.voice_id = voice
    else:
        ctx = PipelineContext(
            project_id=project_id,
            source_url=url,
            locale=locale,
            work_dir=work_dir,
            voice_id=voice,
        )
```

Replace with:

```python
    if start_from and context_file.exists():
        ctx = PipelineContext.load(context_file)
        if voice:
            ctx.voice_id = voice
        ctx.burn_subtitles = subtitles
    else:
        ctx = PipelineContext(
            project_id=project_id,
            source_url=url,
            locale=locale,
            work_dir=work_dir,
            voice_id=voice,
            burn_subtitles=subtitles,
        )
```

- [ ] **Step 3: Sanity-check CLI wiring**

Run: `uv run pipeline produce --help`
Expected: `--subtitles / --no-subtitles` appears in help output with description.

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/cli.py
git commit -m "feat(cli): add --subtitles/--no-subtitles to produce (default off)"
```

---

## Task 9: Extend `voice add` with prerecorded fields

**Files:**
- Modify: `src/pipeline/cli_voice.py`
- Modify: `tests/unit/test_voice_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_voice_cli.py`:

```python
def test_voice_add_prerecorded(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from pipeline.cli_voice import voice_app

    monkeypatch.setenv("VOICES_DIR", str(tmp_path))

    runner = CliRunner()
    rec_dir = tmp_path / "rec"
    result = runner.invoke(
        voice_app,
        [
            "add",
            "--id",
            "tim-zhtw",
            "--engine",
            "prerecorded",
            "--locale",
            "zh-TW",
            "--recording-dir",
            str(rec_dir),
            "--fallback-voice",
            "zh-TW-default-f",
            "--display-name",
            "Tim (zh-TW)",
        ],
    )
    assert result.exit_code == 0, result.output

    import json

    data = json.loads((tmp_path / "registry.json").read_text())
    profile = next(v for v in data["voices"] if v["id"] == "tim-zhtw")
    assert profile["engine"] == "prerecorded"
    assert profile["params"]["recording_dir"] == str(rec_dir)
    assert profile["params"]["fallback_voice_id"] == "zh-TW-default-f"
```

Also, remove or update any existing test that asserted cosyvoice-specific behavior in this file. Identify them with:

```bash
grep -n "cosyvoice" tests/unit/test_voice_cli.py
```

Delete or rewrite any matching test to use `prerecorded` instead.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_voice_cli.py::test_voice_add_prerecorded -v`
Expected: FAIL — `--recording-dir` / `--fallback-voice` flags don't exist yet.

- [ ] **Step 3: Add flags to `voice add`**

In `src/pipeline/cli_voice.py`, replace the `add_voice` function with:

```python
@voice_app.command("add")
def add_voice(
    id: str = typer.Option(..., "--id"),
    engine: str = typer.Option(..., "--engine", help="edge | prerecorded"),
    locale: str = typer.Option(..., "--locale"),
    reference: Optional[Path] = typer.Option(None, "--reference"),
    reference_text: Optional[str] = typer.Option(None, "--reference-text"),
    display_name: Optional[str] = typer.Option(None, "--display-name"),
    param: list[str] = typer.Option([], "--param", help="key=value, repeatable"),
    recording_dir: Optional[Path] = typer.Option(
        None,
        "--recording-dir",
        help="Directory of per-scene recordings (prerecorded engine).",
    ),
    fallback_voice: Optional[str] = typer.Option(
        None,
        "--fallback-voice",
        help="Voice id to use when a scene recording is missing (prerecorded engine).",
    ),
) -> None:
    """Add a new voice profile to the registry."""
    params: dict[str, str] = {}
    for p in param:
        if "=" not in p:
            raise typer.BadParameter(f"--param must be key=value, got {p!r}")
        k, v = p.split("=", 1)
        params[k] = v

    if engine == "prerecorded":
        if recording_dir is None:
            raise typer.BadParameter(
                "--recording-dir is required when --engine prerecorded"
            )
        params["recording_dir"] = str(recording_dir)
        if fallback_voice is not None:
            params["fallback_voice_id"] = fallback_voice

    registry = _registry()
    entry: dict = {
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
```

- [ ] **Step 4: Handle VOICES_DIR env override for tests**

The test uses `monkeypatch.setenv("VOICES_DIR", ...)`. Check whether `PipelineConfig` reads `VOICES_DIR` from env. If not:

Run: `grep -n "VOICES_DIR" src/pipeline/config.py`

If it's just a default Path, pydantic-settings will already pick up env vars matching the field name. Confirm by running:

Run: `uv run python -c "import os; os.environ['VOICES_DIR']='/tmp/x'; from pipeline.config import PipelineConfig; print(PipelineConfig().VOICES_DIR)"`
Expected: `/tmp/x`.

If the override doesn't work, adjust the test to use `monkeypatch.setattr` on `pipeline.cli_voice._registry` instead to return a `VoiceRegistry(tmp_path)` directly.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_voice_cli.py -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/cli_voice.py tests/unit/test_voice_cli.py
git commit -m "feat(voices): voice add --engine prerecorded --recording-dir"
```

---

## Task 10: Storyboard CLI — `show`

**Files:**
- Create: `src/pipeline/cli_storyboard.py`
- Create: `tests/unit/test_storyboard_cli.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_storyboard_cli.py`:

```python
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pipeline.storyboard import Scene, Storyboard


def _write_storyboard(work_dir: Path) -> Path:
    sb = Storyboard(
        scenes=[
            Scene(
                id="hook_1",
                section="hook",
                narration="第一段旁白。",
                narration_est_sec=3.0,
                pause_after_sec=0.5,
                visual={"type": "text_card", "text": "hi"},
            ),
            Scene(
                id="ctx_1",
                section="context",
                narration="第二段旁白內容更長一些，看看顯示效果。",
                narration_est_sec=5.0,
                pause_after_sec=1.0,
                visual={"type": "text_card", "text": "hi"},
            ),
        ]
    )
    path = work_dir / "storyboard.json"
    sb.save(path)
    return path


def test_storyboard_show_lists_all_scenes(tmp_path):
    from pipeline.cli_storyboard import storyboard_app

    _write_storyboard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(storyboard_app, ["show", "--work-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "hook_1" in result.output
    assert "ctx_1" in result.output
    assert "hook" in result.output
    assert "context" in result.output


def test_storyboard_show_single_scene(tmp_path):
    from pipeline.cli_storyboard import storyboard_app

    _write_storyboard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        storyboard_app, ["show", "--scene", "ctx_1", "--work-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert "第二段旁白內容更長一些" in result.output
    assert "ctx_1" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_storyboard_cli.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `storyboard show`**

Create `src/pipeline/cli_storyboard.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from pipeline.storyboard import Storyboard

storyboard_app = typer.Typer(help="Inspect and edit storyboard.json.")
_console = Console()


def _load_storyboard(work_dir: Path) -> Storyboard:
    path = work_dir / "storyboard.json"
    if not path.exists():
        raise typer.BadParameter(
            f"no storyboard.json at {path}; pass --work-dir pointing to a project directory"
        )
    return Storyboard.load(path)


@storyboard_app.command("show")
def show(
    scene: Optional[str] = typer.Option(None, "--scene", help="Scene id to focus"),
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
) -> None:
    """List scenes or print one scene's full narration."""
    sb = _load_storyboard(work_dir)

    if scene is None:
        table = Table(title=f"Storyboard: {len(sb.scenes)} scenes")
        table.add_column("id")
        table.add_column("section")
        table.add_column("narration (first 60)")
        table.add_column("est_sec", justify="right")
        table.add_column("pause", justify="right")
        for s in sb.scenes:
            preview = s.narration[:60] + ("…" if len(s.narration) > 60 else "")
            table.add_row(
                s.id,
                s.section,
                preview,
                f"{s.narration_est_sec:.1f}",
                f"{s.pause_after_sec:.1f}",
            )
        _console.print(table)
        return

    match = sb.get_scene(scene)
    if match is None:
        typer.echo(f"scene '{scene}' not found")
        raise typer.Exit(code=1)
    _console.print(f"[bold]{match.id}[/bold]  section={match.section}  "
                   f"est_sec={match.narration_est_sec}  pause={match.pause_after_sec}")
    if match.visual:
        _console.print(f"visual: {match.visual.get('type', '?')}")
    if match.overlay:
        _console.print(f"overlay: {match.overlay.get('type', '?')}")
    _console.print()
    _console.print(match.narration)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_storyboard_cli.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/cli_storyboard.py tests/unit/test_storyboard_cli.py
git commit -m "feat(cli): storyboard show subcommand"
```

---

## Task 11: Storyboard CLI — `recordings`

**Files:**
- Modify: `src/pipeline/cli_storyboard.py`
- Modify: `tests/unit/test_storyboard_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_storyboard_cli.py`:

```python
def _write_registry(voices_dir: Path, rec_dir: Path) -> None:
    import json

    voices_dir.mkdir(parents=True, exist_ok=True)
    (voices_dir / "registry.json").write_text(
        json.dumps(
            {
                "voices": [
                    {
                        "id": "tim-zhtw",
                        "engine": "prerecorded",
                        "locale": "zh-TW",
                        "params": {"recording_dir": str(rec_dir)},
                    },
                    {
                        "id": "zh-TW-default-f",
                        "engine": "edge",
                        "locale": "zh-TW",
                        "params": {"voice": "zh-TW-HsiaoChenNeural"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )


def test_storyboard_recordings_classifies_states(tmp_path, monkeypatch):
    from pipeline.cli_storyboard import storyboard_app

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    _write_storyboard(work_dir)

    voices_dir = tmp_path / "voices"
    rec_dir = voices_dir / "prerecorded" / "tim-zhtw"
    rec_dir.mkdir(parents=True)
    _write_registry(voices_dir, rec_dir)

    # hook_1: recorded & fresh
    (rec_dir / "hook_1.wav").write_bytes(b"x")
    (rec_dir / "hook_1.txt").write_text("第一段旁白。", encoding="utf-8")

    # ctx_1: missing (no file)

    # orphan recording
    (rec_dir / "ghost_scene.wav").write_bytes(b"x")

    monkeypatch.setenv("VOICES_DIR", str(voices_dir))
    runner = CliRunner()
    result = runner.invoke(
        storyboard_app,
        ["recordings", "--voice", "tim-zhtw", "--work-dir", str(work_dir)],
    )
    assert result.exit_code == 0, result.output
    assert "hook_1" in result.output
    assert "recorded" in result.output
    assert "ctx_1" in result.output
    assert "missing" in result.output
    assert "ghost_scene" in result.output  # orphan section


def test_storyboard_recordings_marks_stale_when_text_drifts(tmp_path, monkeypatch):
    from pipeline.cli_storyboard import storyboard_app

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    _write_storyboard(work_dir)

    voices_dir = tmp_path / "voices"
    rec_dir = voices_dir / "prerecorded" / "tim-zhtw"
    rec_dir.mkdir(parents=True)
    _write_registry(voices_dir, rec_dir)

    (rec_dir / "hook_1.wav").write_bytes(b"x")
    (rec_dir / "hook_1.txt").write_text("舊文字", encoding="utf-8")

    monkeypatch.setenv("VOICES_DIR", str(voices_dir))
    runner = CliRunner()
    result = runner.invoke(
        storyboard_app,
        ["recordings", "--voice", "tim-zhtw", "--work-dir", str(work_dir)],
    )
    assert result.exit_code == 0, result.output
    assert "stale" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_storyboard_cli.py -v`
Expected: FAIL — `recordings` command doesn't exist.

- [ ] **Step 3: Implement `storyboard recordings`**

Append to `src/pipeline/cli_storyboard.py`:

```python
from pipeline.config import PipelineConfig
from pipeline.voices.base import VoiceProfile
from pipeline.voices.registry import VoiceRegistry


_RECORDING_EXTS = (".wav", ".mp3", ".m4a")


def _find_recording(rec_dir: Path, scene_id: str) -> Path | None:
    for ext in _RECORDING_EXTS:
        p = rec_dir / f"{scene_id}{ext}"
        if p.exists():
            return p
    return None


def _classify(rec_dir: Path, scene_id: str, live_text: str) -> tuple[str, str]:
    src = _find_recording(rec_dir, scene_id)
    if src is None:
        return "missing", ""
    snapshot = rec_dir / f"{scene_id}.txt"
    if not snapshot.exists():
        return "stale", "no snapshot"
    recorded = snapshot.read_text(encoding="utf-8").strip()
    if recorded != live_text.strip():
        return "stale", "text changed since record"
    return "recorded", ""


def _resolve_voice_profile(
    registry: VoiceRegistry, voice_id: Optional[str]
) -> VoiceProfile:
    if voice_id is not None:
        return registry.get(voice_id)
    prerecorded = [p for p in registry.list() if p.engine == "prerecorded"]
    if len(prerecorded) == 1:
        return prerecorded[0]
    if not prerecorded:
        raise typer.BadParameter(
            "no prerecorded voice in registry; pass --voice <id>"
        )
    raise typer.BadParameter(
        "multiple prerecorded voices in registry; pass --voice <id>"
    )


@storyboard_app.command("recordings")
def recordings(
    voice: Optional[str] = typer.Option(None, "--voice", help="Voice id"),
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
) -> None:
    """Show per-scene recording status for a prerecorded voice."""
    sb = _load_storyboard(work_dir)
    cfg = PipelineConfig()
    registry = VoiceRegistry(cfg.VOICES_DIR)
    profile = _resolve_voice_profile(registry, voice)
    if profile.engine != "prerecorded":
        raise typer.BadParameter(
            f"voice '{profile.id}' is engine '{profile.engine}', not 'prerecorded'"
        )
    rec_dir = Path(profile.params["recording_dir"])

    table = Table(title=f"Recordings for {profile.id}  ({rec_dir})")
    table.add_column("scene_id")
    table.add_column("status")
    table.add_column("note")

    known_ids: set[str] = set()
    for scene in sb.scenes:
        known_ids.add(scene.id)
        status, note = _classify(rec_dir, scene.id, scene.narration)
        table.add_row(scene.id, status, note)
    _console.print(table)

    if not rec_dir.exists():
        return
    orphans: list[str] = []
    for f in sorted(rec_dir.iterdir()):
        if f.suffix not in _RECORDING_EXTS:
            continue
        if f.stem not in known_ids:
            orphans.append(f.name)
    if orphans:
        _console.print("\n[yellow]Orphans (no matching scene):[/yellow]")
        for name in orphans:
            _console.print(f"  - {name}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_storyboard_cli.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/cli_storyboard.py tests/unit/test_storyboard_cli.py
git commit -m "feat(cli): storyboard recordings subcommand"
```

---

## Task 12: Storyboard CLI — `set`

**Files:**
- Modify: `src/pipeline/cli_storyboard.py`
- Modify: `tests/unit/test_storyboard_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_storyboard_cli.py`:

```python
def test_storyboard_set_narration(tmp_path):
    from pipeline.cli_storyboard import storyboard_app

    _write_storyboard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        storyboard_app,
        ["set", "hook_1", 'narration=新的旁白內容', "--work-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output

    import json

    data = json.loads((tmp_path / "storyboard.json").read_text())
    scene = next(s for s in data["scenes"] if s["id"] == "hook_1")
    assert scene["narration"] == "新的旁白內容"


def test_storyboard_set_pause(tmp_path):
    from pipeline.cli_storyboard import storyboard_app

    _write_storyboard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        storyboard_app,
        ["set", "hook_1", "pause_after_sec=2.5", "--work-dir", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output

    import json

    data = json.loads((tmp_path / "storyboard.json").read_text())
    scene = next(s for s in data["scenes"] if s["id"] == "hook_1")
    assert scene["pause_after_sec"] == 2.5


def test_storyboard_set_rejects_unsafe_field(tmp_path):
    from pipeline.cli_storyboard import storyboard_app

    _write_storyboard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        storyboard_app,
        ["set", "hook_1", "visual.type=still", "--work-dir", str(tmp_path)],
    )
    assert result.exit_code != 0


def test_storyboard_set_rejects_unknown_section(tmp_path):
    from pipeline.cli_storyboard import storyboard_app

    _write_storyboard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        storyboard_app,
        ["set", "hook_1", "section=unknown", "--work-dir", str(tmp_path)],
    )
    assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_storyboard_cli.py -v`
Expected: FAIL — `set` command doesn't exist.

- [ ] **Step 3: Implement `storyboard set`**

Append to `src/pipeline/cli_storyboard.py`:

```python
_ALLOWED_FIELDS = {"narration", "narration_est_sec", "pause_after_sec", "section"}
_ALLOWED_SECTIONS = {
    "hook",
    "context",
    "rising",
    "climax",
    "aftermath",
    "analysis",
    "content",
    "punchline",
}


def _coerce_value(field: str, raw: str) -> object:
    if field in {"narration_est_sec", "pause_after_sec"}:
        try:
            return float(raw)
        except ValueError as exc:
            raise typer.BadParameter(
                f"{field} must be a number, got {raw!r}"
            ) from exc
    if field == "section":
        if raw not in _ALLOWED_SECTIONS:
            raise typer.BadParameter(
                f"section must be one of {sorted(_ALLOWED_SECTIONS)}, got {raw!r}"
            )
        return raw
    return raw  # narration: free text


@storyboard_app.command("set")
def set_field(
    scene_id: str = typer.Argument(...),
    assignment: str = typer.Argument(..., help="field=value"),
    work_dir: Path = typer.Option(Path("."), "--work-dir"),
) -> None:
    """Set a safe field on a scene. Use storyboard.json directly for visual/overlay/compartment."""
    if "=" not in assignment:
        raise typer.BadParameter("expected field=value, got " + assignment)
    field, raw_value = assignment.split("=", 1)
    if field not in _ALLOWED_FIELDS:
        raise typer.BadParameter(
            f"'{field}' is not a safe field; allowed: {sorted(_ALLOWED_FIELDS)}. "
            "Edit storyboard.json directly for complex fields."
        )
    value = _coerce_value(field, raw_value)

    sb = _load_storyboard(work_dir)
    scene = sb.get_scene(scene_id)
    if scene is None:
        raise typer.BadParameter(f"scene '{scene_id}' not found")
    setattr(scene, field, value)

    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)
    typer.echo(f"updated {scene_id}.{field}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_storyboard_cli.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/cli_storyboard.py tests/unit/test_storyboard_cli.py
git commit -m "feat(cli): storyboard set subcommand with safe-field allow-list"
```

---

## Task 13: Register storyboard subcommand group in main CLI

**Files:**
- Modify: `src/pipeline/cli.py`

- [ ] **Step 1: Wire the subcommand group**

In `src/pipeline/cli.py`, add the import near the top (after `from pipeline.cli_voice import voice_app`):

```python
from pipeline.cli_storyboard import storyboard_app
```

Add the registration line right after `app.add_typer(voice_app, name="voice")`:

```python
app.add_typer(storyboard_app, name="storyboard")
```

- [ ] **Step 2: Sanity-check CLI wiring**

Run: `uv run pipeline storyboard --help`
Expected: help lists `show`, `recordings`, `set`.

Run: `uv run pipeline storyboard show --help`
Expected: help includes `--scene` and `--work-dir`.

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/cli.py
git commit -m "feat(cli): register storyboard subcommand group"
```

---

## Task 14: Update CLAUDE.md and rewrite record_voice.md

**Files:**
- Modify: `CLAUDE.md`
- Rewrite: `scripts/record_voice.md`

- [ ] **Step 1: Append storyboard commands + natural-language triggers to CLAUDE.md**

In `CLAUDE.md`, find the `## Commands` section. Find the block ending at the last `uv run pytest` example (look for the `# Lint & format` block that follows). Add a new subsection right before `# Testing` or at the end of the code block. Insert:

```markdown
# Storyboard editing (hand-edit storyboard.json helpers)
uv run pipeline storyboard show                              # list all scenes
uv run pipeline storyboard show --scene scene_003            # one scene's full text
uv run pipeline storyboard recordings --voice tim-zhtw       # recording status per scene
uv run pipeline storyboard set scene_003 narration="新文字"  # edit a safe field

# Natural-language triggers (for the assistant):
#   "show me scene X's narration"       → storyboard show --scene X
#   "which scenes still need recording" → storyboard recordings
#   "fix scene X's text to Y"           → storyboard set X narration="Y"
#   "change scene X's pause to Ns"      → storyboard set X pause_after_sec=N
```

Also find the existing `## Edge-TTS Voice IDs` section and add below it a new heading explaining the recording flow:

```markdown
## Prerecorded voice workflow

For occasional vlog-style content, a creator can record scene audio by hand
and drop files into `voices/prerecorded/<voice_id>/<scene_id>.wav`. The
pipeline's `PrerecordedEngine` picks up these files and falls back to
Edge-TTS for any scene without a recording. See `scripts/record_voice.md`
for the full workflow.
```

- [ ] **Step 2: Rewrite `scripts/record_voice.md`**

Overwrite `scripts/record_voice.md` with:

```markdown
# Recording your own voice per scene

This project supports a hybrid narration workflow: generate a draft with
Edge-TTS, then iteratively replace individual scenes with your own
recordings. You can re-run `produce` at any time; scenes with recordings
use your voice, the rest use Edge.

## One-time setup

1. Create a recording directory under `voices/prerecorded/`:
   ```bash
   mkdir -p voices/prerecorded/tim-zhtw
   ```

2. Register a `prerecorded` voice profile:
   ```bash
   uv run pipeline voice add \
     --id tim-zhtw \
     --engine prerecorded \
     --locale zh-TW \
     --recording-dir voices/prerecorded/tim-zhtw \
     --fallback-voice zh-TW-default-f \
     --display-name "Tim (zh-TW, pre-recorded)"
   ```

3. Verify:
   ```bash
   uv run pipeline voice list
   ```

## Recording loop

1. Produce a draft (Edge fills every scene):
   ```bash
   uv run pipeline produce --url <video-url> --locale zh-TW \
     --voice tim-zhtw --no-subtitles
   ```

2. See what still needs recording:
   ```bash
   uv run pipeline storyboard recordings --voice tim-zhtw \
     --work-dir output/projects/<project_id>
   ```

3. For each scene you want to re-record, read the exact text:
   ```bash
   uv run pipeline storyboard show --scene hook_1 \
     --work-dir output/projects/<project_id>
   ```

4. Record that scene. Recommended settings: 16 kHz mono WAV.
   Save as `voices/prerecorded/tim-zhtw/hook_1.wav`.

5. Re-run `produce` with the same `--project-id` and `--start-from tts`:
   ```bash
   uv run pipeline produce --url <video-url> --locale zh-TW \
     --voice tim-zhtw --no-subtitles \
     --project-id <project_id> --start-from tts
   ```

6. Iterate scene by scene. `storyboard recordings` shows progress.

## When text drifts

If you hand-edit `storyboard.json` (or re-run `direct`), a scene's
narration may change after you already recorded it. The engine compares
the live narration to the snapshot `<scene_id>.txt` saved at record time:

- If they match → recording is used silently.
- If they differ → a `prerecorded.stale_recording` warning prints and the
  recording is used anyway. `storyboard recordings` shows `status: stale`.

To refresh, re-record the scene. The snapshot is rewritten on next run.

## Orphans

A file in the recording directory that has no matching scene id in the
storyboard is an orphan. `storyboard recordings` lists orphans separately.
Delete them when you're confident they're no longer needed.

## Equipment

Any decent USB mic or headset works. Record in a quiet room. The pipeline
transcodes WAV/MP3/M4A input to MP3 automatically.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md scripts/record_voice.md
git commit -m "docs(voices): document prerecorded workflow + storyboard helpers"
```

---

## Task 15: End-to-end integration test

**Files:**
- Create: `tests/integration/test_prerecorded_end_to_end.py`
- Create: `tests/fixtures/short_narration.wav`
- Modify: `voices/prerecorded/.gitkeep` (new file)

- [ ] **Step 1: Generate the fixture WAV**

Run: `mkdir -p tests/fixtures && ffmpeg -f lavfi -i anullsrc -t 1 -ar 16000 -ac 1 tests/fixtures/short_narration.wav`
Expected: file is created, roughly 32 KB.

- [ ] **Step 2: Add `.gitkeep` for the prerecorded voices directory**

Run: `mkdir -p voices/prerecorded && touch voices/prerecorded/.gitkeep`

- [ ] **Step 3: Write the integration test**

Create `tests/integration/test_prerecorded_end_to_end.py`:

```python
"""Smoke test: TtsStage with a prerecorded voice actually transcodes a real
WAV file and hits the EdgeEngine fallback path on a missing scene.

Marked `integration` because it runs real ffmpeg and real edge-tts.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_prerecorded_mixes_with_edge_fallback(tmp_path):
    from pipeline.stages.base import PipelineContext
    from pipeline.stages.tts import TtsStage
    from pipeline.storyboard import Scene, Storyboard

    voices_dir = tmp_path / "voices"
    rec_dir = voices_dir / "prerecorded" / "tim-zhtw"
    rec_dir.mkdir(parents=True)

    fixture = Path(__file__).parent.parent / "fixtures" / "short_narration.wav"
    shutil.copyfile(fixture, rec_dir / "hook_1.wav")

    (voices_dir / "registry.json").write_text(
        json.dumps(
            {
                "voices": [
                    {
                        "id": "tim-zhtw",
                        "engine": "prerecorded",
                        "locale": "zh-TW",
                        "params": {
                            "recording_dir": str(rec_dir),
                            "fallback_voice_id": "zh-TW-default-f",
                        },
                    },
                    {
                        "id": "zh-TW-default-f",
                        "engine": "edge",
                        "locale": "zh-TW",
                        "params": {"voice": "zh-TW-HsiaoChenNeural"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    sb = Storyboard(
        scenes=[
            Scene(
                id="hook_1",
                section="hook",
                narration="你好，這是第一段。",
                narration_est_sec=1.0,
                visual={"type": "text_card", "text": "hi"},
            ),
            Scene(
                id="ctx_1",
                section="context",
                narration="這是第二段，應該用Edge合成。",
                narration_est_sec=1.5,
                visual={"type": "text_card", "text": "hi"},
            ),
        ]
    )
    sb.save(work_dir / "storyboard.json")
    script_dir = work_dir / "script"
    script_dir.mkdir()
    (script_dir / "script_zh-TW.md").write_text(sb.derive_script(), encoding="utf-8")

    ctx = PipelineContext(
        project_id=1,
        source_url="x",
        locale="zh-TW",
        work_dir=work_dir,
        storyboard_path=work_dir / "storyboard.json",
        script_path=script_dir / "script_zh-TW.md",
        voice_id="tim-zhtw",
    )

    # Override the config VOICES_DIR via env var for this test
    import os

    os.environ["VOICES_DIR"] = str(voices_dir)
    try:
        asyncio.run(TtsStage().run(ctx))
    finally:
        del os.environ["VOICES_DIR"]

    # Both scene audio files exist.
    assert (work_dir / "audio" / "segment_000.mp3").exists()
    assert (work_dir / "audio" / "segment_001.mp3").exists()
    # Snapshot was written for the recorded scene.
    assert (rec_dir / "hook_1.txt").read_text(encoding="utf-8").strip() == "你好，這是第一段。"
```

- [ ] **Step 4: Run the integration test**

Run: `uv run pytest tests/integration/test_prerecorded_end_to_end.py -v -m integration`
Expected: PASS. Requires ffmpeg binary and internet (edge-tts).

If the VOICES_DIR env override doesn't take effect (pydantic-settings caching), the test will fail and you must adjust: patch `pipeline.stages.tts.PipelineConfig` with monkeypatch instead.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_prerecorded_end_to_end.py tests/fixtures/short_narration.wav voices/prerecorded/.gitkeep
git commit -m "test(voices): integration test for prerecorded + edge fallback"
```

---

## Task 16: Final verification sweep

**Files:** (no code changes; verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -x -q`
Expected: all unit tests PASS. Integration tests run separately and may be skipped by default.

- [ ] **Step 2: Run linter + type checker**

Run: `uv run ruff check src/ tests/`
Run: `uv run ruff format --check src/ tests/`
Run: `uv run mypy src/`

Expected: no errors. Fix any issues inline (type hints for new code, formatting).

- [ ] **Step 3: Smoke-test the CLI**

Run these in order; expect each to succeed:

```bash
uv run pipeline voice list
uv run pipeline storyboard --help
uv run pipeline produce --help | grep -A1 "subtitles"
```

Expected:
- `voice list` shows the seeded edge voices.
- `storyboard --help` shows `show`, `recordings`, `set`.
- `produce --help` shows the `--subtitles / --no-subtitles` flag with default off.

- [ ] **Step 4: Commit if anything was fixed**

If the lint/type check produced fixups, commit them:

```bash
git add -A
git commit -m "chore: lint fixes after prerecorded voice feature"
```

If nothing needed fixing, this task is complete with no commit.

---

## Done

After Task 16, the feature is complete:
- CosyVoice engine and installer are gone.
- `PrerecordedEngine` with Edge fallback lives in the registry under the `prerecorded` engine type.
- `TtsStage` passes `scene.id` to engines so prerecorded can key lookups.
- `ComposeStage` respects `ctx.burn_subtitles`; `--no-subtitles` is the new default on `produce`.
- `pipeline storyboard show / recordings / set` give the creator efficient tools for iterative editing.
- `CLAUDE.md` documents the commands + natural-language triggers so future sessions route work correctly.
- `scripts/record_voice.md` is the creator's workflow reference.
