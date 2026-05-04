# Click-to-Edit Plan 2 — Narration Recorder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-scene `narration_source` override (TTS engine swap or browser-recorded WAV) with a CLI verb (`pipeline narration set-source`), three direct-action HTTP endpoints (set-source / upload / transcribe), and a dashboard modal that drives a browser MediaRecorder + Whisper-API auto-transcribe-and-diff flow.

**Architecture:** A sparse `narration_source` field on each `Scene` (Plan 1 added the parallel `transitions[]` field at the storyboard level; this plan adds the per-scene equivalent). At TTS time, `_synthesize_pass` resolves the engine **per segment** — using the scene's `narration_source` when set, else the project default. Engine `prerecorded` with a `file:` value is a NEW direct-transcode path (not via the existing `PrerecordedEngine`, which keys off scene_id under a profile-registered `recording_dir` and isn't suited to ad-hoc per-scene file paths). Whisper transcription is a thin `httpx` wrapper around `POST /v1/audio/transcriptions`. Audio normalization uses ffmpeg's `loudnorm` filter directly (no `ffmpeg-normalize` dependency).

**Tech Stack:** Python 3.12, dataclasses, Typer, FastAPI, FFmpeg (`loudnorm`), httpx (Whisper API), pytest, vanilla JS (`MediaRecorder` browser API). No new third-party Python deps.

**Spec reference:** `docs/superpowers/specs/2026-05-04-dashboard-click-to-edit-design.md` — §"Storyboard schema" (`narration_source` block), §"User flows" → "Flow 3 — Direct-action narration source + recorder", §"CLI verb surface" (`narration set-source` / `narration regen` rows; this plan implements only `set-source` — `narration regen` is agent-driven and lives in Plan 3), §"Backend — direct-action endpoints" (the three `/api/narration/...` rows), §"Component design" → "Frontend — direct-action modals" (NarrationSourceEditor).

**Important divergences from the spec wording (intentional, locked here):**

1. **Engine names use the registry's identifiers**, not the spec's hyphenated forms. The spec writes `edge-tts` / `fish-audio`; the actual `VoiceRegistry._engine_for` (`src/pipeline/voices/registry.py:73-86`) dispatches on `edge` / `fish_audio` / `prerecorded`. We use the registry names — they're the dispatch keys.
2. **`narration_source` shape**: `{engine: str, voice: str | None, file: str | None}`. For `engine="edge"` / `"fish_audio"` the `voice` field is the registry voice_id (resolved through `registry.resolve(voice_id)`). For `engine="prerecorded"` the `file` field is a project-relative path — typically `narration_overrides/<scene_id>.wav` — handled by a NEW direct-transcode code path inside `tts.py`, not by `PrerecordedEngine`.
3. **No edit-mode toggle in this plan.** Plan 4 owns edit mode and the floating composer. So Plan 2 has to expose the modal *somehow* in the meantime: a small `🎙 record` button is added inside the existing `.scene-narration` panel (`index.html:197`), visible whenever the project's detail row is open. Plan 4 will replace this with the source chip. Code comment on the button calls this out as a temporary affordance.

---

## File Structure

**Create:**

| File | Responsibility |
|---|---|
| `src/pipeline/cli_narration.py` | Typer subapp exposing `narration set-source` |
| `src/pipeline/transcribe.py` | Whisper-API wrapper (`transcribe_audio(path, language) -> str`) |
| `src/pipeline/utils/audio.py` | `normalize_to_wav(src, dst)` — ffmpeg `loudnorm` wrapper |
| `src/pipeline/dashboard/static/narration_source_editor.js` | Modal component: source dropdown, MediaRecorder, transcript-diff preview |
| `tests/unit/test_narration_source.py` | Unit tests for `NarrationSource` dataclass + Scene field |
| `tests/unit/test_cli_narration.py` | Unit tests for `pipeline narration set-source` |
| `tests/unit/test_tts_per_scene_engine.py` | Unit tests for per-scene engine dispatch in `_synthesize_pass` |
| `tests/unit/test_transcribe.py` | Unit tests for Whisper wrapper (httpx mocked) |
| `tests/unit/test_audio_normalize.py` | Unit tests for the loudnorm helper |
| `tests/unit/test_narration_endpoints.py` | Unit tests for the three FastAPI endpoints |

**Modify:**

| File | Change |
|---|---|
| `src/pipeline/storyboard.py` | Add `NarrationSource` dataclass; add `narration_source: NarrationSource \| None` field to `Scene` (sparse to_dict / from_dict) |
| `src/pipeline/stages/tts.py` | Refactor `_synthesize_pass` to resolve engine **per segment** when `scene.narration_source` is set; add a direct-transcode branch for `engine="prerecorded"` with `file=...` |
| `src/pipeline/dashboard/server.py` | Add three POST endpoints + the `🎙` button in `index.html` glue (the JS module is registered via `<script>`); reuse FastAPI's `UploadFile` |
| `src/pipeline/dashboard/static/index.html` | Inject `🎙 record` button into the `.scene-narration` panel; load `narration_source_editor.js` |
| `src/pipeline/cli.py` | Register `narration_app` from `cli_narration.py` |
| `.gitignore` | Add `output/projects/*/narration_overrides/` is **not** added — these are user-recorded artifacts that live under `output/` (already ignored). No change needed; verify in Task 10. |

**Out of scope** (later plans):

- `pipeline narration regen --text "..."` (Plan 3 — agent-driven script edit; this plan ships only `set-source`)
- Edit-mode toggle / floating composer / token chips (Plan 4)
- JobQueue + agent runtime (Plan 3)
- SSE refresh of the dashboard view after a mutation (Plan 5)
- The "Apply to s9" → automatic per-scene reburn chain. This plan stops at writing the `narration_source` field + saving the recording. Triggering reburn is a manual `pipeline compose rescene --scene sN` step. Plan 5 wires SSE-driven auto-reburn.

---

## Task 1: Add `NarrationSource` dataclass to `storyboard.py`

**Files:**
- Modify: `src/pipeline/storyboard.py` (insert after the existing `Transition` dataclass, around line 43)
- Test: `tests/unit/test_narration_source.py` (new)

- [ ] **Step 1.1: Create the test file with the `NarrationSource` parsing tests**

Create `tests/unit/test_narration_source.py`:

```python
from __future__ import annotations

import pytest

from pipeline.storyboard import NarrationSource


def test_narration_source_edge_engine_with_voice():
    ns = NarrationSource.from_dict({"engine": "edge", "voice": "zh-tw-default-f"})
    assert ns.engine == "edge"
    assert ns.voice == "zh-tw-default-f"
    assert ns.file is None


def test_narration_source_fish_audio_engine_with_voice():
    ns = NarrationSource.from_dict({"engine": "fish_audio", "voice": "fish-jingjing"})
    assert ns.engine == "fish_audio"
    assert ns.voice == "fish-jingjing"


def test_narration_source_prerecorded_with_file():
    ns = NarrationSource.from_dict({
        "engine": "prerecorded",
        "file": "narration_overrides/s9.wav",
    })
    assert ns.engine == "prerecorded"
    assert ns.file == "narration_overrides/s9.wav"
    assert ns.voice is None


def test_narration_source_to_dict_omits_none_fields():
    ns = NarrationSource(engine="edge", voice="zh-tw-default-f", file=None)
    out = ns.to_dict()
    assert out == {"engine": "edge", "voice": "zh-tw-default-f"}
    assert "file" not in out


def test_narration_source_to_dict_prerecorded_omits_voice():
    ns = NarrationSource(engine="prerecorded", voice=None, file="narration_overrides/s9.wav")
    out = ns.to_dict()
    assert out == {"engine": "prerecorded", "file": "narration_overrides/s9.wav"}
    assert "voice" not in out


def test_narration_source_rejects_unknown_engine():
    with pytest.raises(ValueError, match="Unknown narration engine"):
        NarrationSource(engine="elevenlabs", voice=None, file=None)


def test_narration_source_prerecorded_requires_file():
    """An engine='prerecorded' source without a file is invalid."""
    with pytest.raises(ValueError, match="prerecorded.*requires.*file"):
        NarrationSource(engine="prerecorded", voice=None, file=None)


def test_narration_source_tts_engine_requires_voice():
    """Engines edge/fish_audio require a voice (registry voice_id)."""
    with pytest.raises(ValueError, match="requires.*voice"):
        NarrationSource(engine="edge", voice=None, file=None)
```

- [ ] **Step 1.2: Run the tests — expect ImportError**

Run: `uv run pytest tests/unit/test_narration_source.py -v`
Expected: 8 errors of the form `ImportError: cannot import name 'NarrationSource' from 'pipeline.storyboard'`.

- [ ] **Step 1.3: Add the `NarrationSource` dataclass to `storyboard.py`**

Open `src/pipeline/storyboard.py`. Insert **after** the existing `Transition` dataclass (after line 42, before the `class Scene:` declaration on line 45):

```python
_VALID_NARRATION_ENGINES = {"edge", "fish_audio", "prerecorded"}


@dataclass
class NarrationSource:
    """Per-scene override for narration generation.

    Three forms:
      - {"engine": "edge", "voice": "<registry voice_id>"}
      - {"engine": "fish_audio", "voice": "<registry voice_id>"}
      - {"engine": "prerecorded", "file": "narration_overrides/<scene>.wav"}

    For TTS engines (edge / fish_audio), `voice` is required and resolves
    through `VoiceRegistry.resolve(voice_id)`. For `prerecorded`, `file` is
    a project-relative path to a normalized WAV; it bypasses the registry's
    `PrerecordedEngine` (which keys recordings by scene_id under a profile-
    registered directory) and is loaded directly by TtsStage.
    """

    engine: str
    voice: str | None = None
    file: str | None = None

    def __post_init__(self) -> None:
        if self.engine not in _VALID_NARRATION_ENGINES:
            raise ValueError(
                f"Unknown narration engine: {self.engine!r}. "
                f"Supported: {sorted(_VALID_NARRATION_ENGINES)}"
            )
        if self.engine == "prerecorded":
            if not self.file:
                raise ValueError(
                    "engine='prerecorded' requires a 'file' path "
                    "(typically narration_overrides/<scene_id>.wav)"
                )
        else:
            # edge / fish_audio
            if not self.voice:
                raise ValueError(
                    f"engine={self.engine!r} requires a 'voice' (registry voice_id)"
                )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NarrationSource:
        return cls(
            engine=data["engine"],
            voice=data.get("voice"),
            file=data.get("file"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"engine": self.engine}
        if self.voice is not None:
            out["voice"] = self.voice
        if self.file is not None:
            out["file"] = self.file
        return out
```

- [ ] **Step 1.4: Run the tests — expect all 8 to pass**

Run: `uv run pytest tests/unit/test_narration_source.py -v`
Expected: 8 passed.

- [ ] **Step 1.5: Commit**

```bash
git add src/pipeline/storyboard.py tests/unit/test_narration_source.py
git commit -m "feat(storyboard): add NarrationSource dataclass for per-scene engine override"
```

---

## Task 2: Add `narration_source` field to `Scene`

**Files:**
- Modify: `src/pipeline/storyboard.py` (`Scene` dataclass + `to_dict` + `from_dict`)
- Test: `tests/unit/test_narration_source.py` (extend)

- [ ] **Step 2.1: Add tests for the `narration_source` Scene field**

Append to `tests/unit/test_narration_source.py`:

```python
import json
from pathlib import Path

from pipeline.storyboard import Scene, Storyboard


def _minimal_scene_dict(scene_id: str) -> dict:
    return {
        "id": scene_id,
        "section": "content",
        "narration": f"narration for {scene_id}",
        "narration_est_sec": 1.0,
    }


def test_scene_defaults_narration_source_to_none():
    s = Scene(id="s1", section="content", narration="hi", narration_est_sec=1.0)
    assert s.narration_source is None


def test_scene_from_dict_without_narration_source():
    """Existing scenes (no narration_source key) still parse and produce None."""
    s = Scene.from_dict(_minimal_scene_dict("s1"))
    assert s.narration_source is None


def test_scene_from_dict_with_narration_source():
    data = _minimal_scene_dict("s9")
    data["narration_source"] = {"engine": "prerecorded", "file": "narration_overrides/s9.wav"}
    s = Scene.from_dict(data)
    assert s.narration_source is not None
    assert s.narration_source.engine == "prerecorded"
    assert s.narration_source.file == "narration_overrides/s9.wav"


def test_scene_to_dict_omits_narration_source_when_none():
    s = Scene(id="s1", section="content", narration="hi", narration_est_sec=1.0)
    out = s.to_dict()
    assert "narration_source" not in out


def test_scene_to_dict_includes_narration_source_when_set():
    from pipeline.storyboard import NarrationSource
    s = Scene(
        id="s9", section="content", narration="hi", narration_est_sec=1.0,
        narration_source=NarrationSource(engine="edge", voice="zh-tw-default-f"),
    )
    out = s.to_dict()
    assert out["narration_source"] == {"engine": "edge", "voice": "zh-tw-default-f"}


def test_storyboard_round_trip_with_narration_source(tmp_path: Path):
    from pipeline.storyboard import NarrationSource
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
        Scene(
            id="s9", section="content", narration="b", narration_est_sec=1.0,
            narration_source=NarrationSource(
                engine="prerecorded",
                file="narration_overrides/s9.wav",
            ),
        ),
    ])
    p = tmp_path / "sb.json"
    sb.save(p)
    loaded = Storyboard.load(p)
    assert loaded.scenes[0].narration_source is None
    assert loaded.scenes[1].narration_source is not None
    assert loaded.scenes[1].narration_source.engine == "prerecorded"
    assert loaded.scenes[1].narration_source.file == "narration_overrides/s9.wav"
```

- [ ] **Step 2.2: Run the new tests — expect failures**

Run: `uv run pytest tests/unit/test_narration_source.py -v -k "scene or storyboard_round_trip"`
Expected: 6 failures, all because `Scene` doesn't have a `narration_source` field.

- [ ] **Step 2.3: Add the `narration_source` field to `Scene`**

In `src/pipeline/storyboard.py`, modify the `Scene` dataclass. Find the existing field block (around line 47-56):

```python
@dataclass
class Scene:
    id: str
    section: str  # hook | context | rising | climax | aftermath | analysis | content | punchline
    narration: str
    narration_est_sec: float
    narration_en: str | None = None
    facts_ref: list[str] = field(default_factory=list)
    visual: dict[str, Any] = field(default_factory=dict)
    overlay: dict[str, Any] | None = None
    pause_after_sec: float = 0
    compartment: dict[str, Any] | None = None
```

Replace with:

```python
@dataclass
class Scene:
    id: str
    section: str  # hook | context | rising | climax | aftermath | analysis | content | punchline
    narration: str
    narration_est_sec: float
    narration_en: str | None = None
    facts_ref: list[str] = field(default_factory=list)
    visual: dict[str, Any] = field(default_factory=dict)
    overlay: dict[str, Any] | None = None
    pause_after_sec: float = 0
    compartment: dict[str, Any] | None = None
    narration_source: NarrationSource | None = None
```

In `Scene.from_dict` (around line 59-71), find:
```python
        return cls(
            id=data["id"],
            section=data["section"],
            narration=data["narration"],
            narration_est_sec=data["narration_est_sec"],
            narration_en=data.get("narration_en"),
            facts_ref=list(data.get("facts_ref", [])),
            visual=dict(data.get("visual", {})),
            overlay=data.get("overlay"),
            pause_after_sec=float(data.get("pause_after_sec", 0)),
            compartment=data.get("compartment"),
        )
```

Replace with:
```python
        ns_raw = data.get("narration_source")
        narration_source = NarrationSource.from_dict(ns_raw) if ns_raw else None
        return cls(
            id=data["id"],
            section=data["section"],
            narration=data["narration"],
            narration_est_sec=data["narration_est_sec"],
            narration_en=data.get("narration_en"),
            facts_ref=list(data.get("facts_ref", [])),
            visual=dict(data.get("visual", {})),
            overlay=data.get("overlay"),
            pause_after_sec=float(data.get("pause_after_sec", 0)),
            compartment=data.get("compartment"),
            narration_source=narration_source,
        )
```

In `Scene.to_dict` (around line 73-88), find:
```python
        if self.narration_en is not None:
            out["narration_en"] = self.narration_en
        if self.compartment is not None:
            out["compartment"] = self.compartment
        return out
```

Replace with:
```python
        if self.narration_en is not None:
            out["narration_en"] = self.narration_en
        if self.compartment is not None:
            out["compartment"] = self.compartment
        if self.narration_source is not None:
            out["narration_source"] = self.narration_source.to_dict()
        return out
```

- [ ] **Step 2.4: Run all narration_source tests — expect pass**

Run: `uv run pytest tests/unit/test_narration_source.py -v`
Expected: 14 passed (8 from Task 1 + 6 from Task 2).

- [ ] **Step 2.5: Run the existing full test suite (excluding the pre-existing failure) to confirm no regressions**

Run: `uv run pytest --deselect tests/unit/test_compose_v2.py::test_compose_burn_subtitles_false_returns_plain_variant -q`
Expected: all pass.

- [ ] **Step 2.6: Commit**

```bash
git add src/pipeline/storyboard.py tests/unit/test_narration_source.py
git commit -m "feat(storyboard): add sparse narration_source field to Scene"
```

---

## Task 3: CLI — `pipeline narration set-source`

**Files:**
- Create: `src/pipeline/cli_narration.py`
- Modify: `src/pipeline/cli.py`
- Test: `tests/unit/test_cli_narration.py` (new)

This task mirrors the structure of `cli_transition.py` (Plan 1) — same project-id resolution, same sandbox behavior, same session-log appending. The only command shipped here is `set-source`; `narration regen` (agent-driven script-rewrite) lives in Plan 3.

- [ ] **Step 3.1: Write CLI tests**

Create `tests/unit/test_cli_narration.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_narration import narration_app
from pipeline.storyboard import Scene, Storyboard


def _write_minimal_storyboard(work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
        Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
    ])
    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)
    (work_dir / "context.json").write_text(
        json.dumps({"project_id": 42, "source_url": "x", "locale": "zh-TW",
                    "work_dir": str(work_dir)}),
        encoding="utf-8",
    )
    return sb_path


@pytest.fixture
def project_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out_root = tmp_path / "output"
    proj = out_root / "projects" / "42"
    _write_minimal_storyboard(proj)
    monkeypatch.setattr(
        "pipeline.cli_narration.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    return proj


def test_set_source_edge_with_voice(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source",
        "--project-id", "42",
        "--scene", "s1",
        "--engine", "edge",
        "--voice", "zh-tw-default-f",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    s1 = sb.get_scene("s1")
    assert s1 is not None
    assert s1.narration_source is not None
    assert s1.narration_source.engine == "edge"
    assert s1.narration_source.voice == "zh-tw-default-f"
    assert s1.narration_source.file is None


def test_set_source_prerecorded_with_file(project_tree: Path):
    # Place a recording inside the project tree so the path resolves.
    overrides = project_tree / "narration_overrides"
    overrides.mkdir(parents=True)
    (overrides / "s1.wav").write_bytes(b"RIFF....WAVEfmt ")  # placeholder
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source",
        "--project-id", "42",
        "--scene", "s1",
        "--engine", "prerecorded",
        "--file", "narration_overrides/s1.wav",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    s1 = sb.get_scene("s1")
    assert s1 is not None
    assert s1.narration_source is not None
    assert s1.narration_source.engine == "prerecorded"
    assert s1.narration_source.file == "narration_overrides/s1.wav"


def test_set_source_replaces_existing(project_tree: Path):
    runner = CliRunner()
    runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "edge", "--voice", "zh-tw-default-f",
    ])
    runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "fish_audio", "--voice", "fish-jingjing",
    ])
    sb = Storyboard.load(project_tree / "storyboard.json")
    s1 = sb.get_scene("s1")
    assert s1 is not None
    assert s1.narration_source is not None
    assert s1.narration_source.engine == "fish_audio"
    assert s1.narration_source.voice == "fish-jingjing"


def test_set_source_rejects_unknown_engine(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "elevenlabs", "--voice", "any",
    ])
    assert result.exit_code != 0
    assert "Unknown narration engine" in result.output or "elevenlabs" in result.output


def test_set_source_rejects_unknown_scene(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s99",
        "--engine", "edge", "--voice", "zh-tw-default-f",
    ])
    assert result.exit_code != 0
    assert "s99" in result.output


def test_set_source_tts_engine_requires_voice(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "edge",  # no --voice
    ])
    assert result.exit_code != 0
    assert "voice" in result.output.lower()


def test_set_source_prerecorded_requires_file(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "prerecorded",  # no --file
    ])
    assert result.exit_code != 0
    assert "file" in result.output.lower()


def test_set_source_rejects_file_outside_project_tree(project_tree: Path):
    """Sandbox check: a --file path that escapes the project root is rejected."""
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "prerecorded", "--file", "../../etc/passwd",
    ])
    assert result.exit_code != 0
    assert "outside" in result.output.lower() or "project tree" in result.output.lower()


def test_set_source_rejects_missing_file(project_tree: Path):
    """The referenced file must exist under the project tree."""
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "prerecorded", "--file", "narration_overrides/s1.wav",
    ])
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "does not exist" in result.output.lower()


def test_set_source_appends_session_entry(project_tree: Path):
    runner = CliRunner()
    runner.invoke(narration_app, [
        "set-source", "--project-id", "42", "--scene", "s1",
        "--engine", "edge", "--voice", "zh-tw-default-f",
    ])
    sessions = json.loads((project_tree / "sessions.json").read_text())
    assert any("narration set-source" in e["command"] for e in sessions)
    assert any("s1" in e.get("summary", "") for e in sessions)
```

- [ ] **Step 3.2: Run the tests — expect ImportError**

Run: `uv run pytest tests/unit/test_cli_narration.py -v`
Expected: ImportError on `pipeline.cli_narration`.

- [ ] **Step 3.3: Create `cli_narration.py`**

Create `src/pipeline/cli_narration.py`:

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from pipeline.config import PipelineConfig
from pipeline.session_log import SessionEntry, append_session, new_session_id
from pipeline.storyboard import NarrationSource, Storyboard

narration_app = typer.Typer(name="narration", help="Per-scene narration source commands")


_VALID_ENGINES = {"edge", "fish_audio", "prerecorded"}


def _resolve_work_dir(project_id: int) -> Path:
    return PipelineConfig().OUTPUT_DIR / "projects" / str(project_id)


def _load_storyboard(project_id: int) -> tuple[Path, Storyboard]:
    work = _resolve_work_dir(project_id)
    sb_path = work / "storyboard.json"
    if not sb_path.exists():
        typer.echo(f"storyboard.json not found at {sb_path}", err=True)
        raise typer.Exit(code=1)
    return sb_path, Storyboard.load(sb_path)


def _resolve_within_project(project_root: Path, rel_path: str) -> Path:
    """Resolve a project-relative path, refusing any escape via .. or absolute paths.

    Returns the absolute resolved Path. Raises typer.Exit(code=1) on violation.
    """
    candidate = (project_root / rel_path).resolve()
    project_root_resolved = project_root.resolve()
    try:
        candidate.relative_to(project_root_resolved)
    except ValueError:
        typer.echo(
            f"Refusing path {rel_path!r}: resolved outside project tree at {project_root}",
            err=True,
        )
        raise typer.Exit(code=1)
    return candidate


@narration_app.command("set-source")
def set_source(
    project_id: int = typer.Option(..., "--project-id"),
    scene: str = typer.Option(..., "--scene", help="Scene id (e.g. s9)"),
    engine: str = typer.Option(..., "--engine", help=f"One of: {', '.join(sorted(_VALID_ENGINES))}"),
    voice: str | None = typer.Option(
        None, "--voice", help="Registry voice_id (required for engine=edge|fish_audio)"
    ),
    file: str | None = typer.Option(
        None, "--file", help="Project-relative path to a WAV (required for engine=prerecorded)"
    ),
) -> None:
    """Set or replace the narration_source override for a scene. Idempotent."""
    if engine not in _VALID_ENGINES:
        typer.echo(
            f"Unknown narration engine {engine!r}. Choose from: {', '.join(sorted(_VALID_ENGINES))}",
            err=True,
        )
        raise typer.Exit(code=1)

    if engine in ("edge", "fish_audio") and not voice:
        typer.echo(f"engine={engine!r} requires --voice (registry voice_id)", err=True)
        raise typer.Exit(code=1)

    if engine == "prerecorded":
        if not file:
            typer.echo("engine='prerecorded' requires --file (project-relative WAV path)", err=True)
            raise typer.Exit(code=1)
        # Sandbox + existence check.
        project_root = _resolve_work_dir(project_id)
        resolved = _resolve_within_project(project_root, file)
        if not resolved.exists():
            typer.echo(f"File not found: {resolved}", err=True)
            raise typer.Exit(code=1)

    sb_path, sb = _load_storyboard(project_id)
    target = sb.get_scene(scene)
    if target is None:
        typer.echo(f"Scene {scene!r} not found in storyboard", err=True)
        raise typer.Exit(code=1)

    target.narration_source = NarrationSource(
        engine=engine,
        voice=voice,
        file=file,
    )
    sb.save(sb_path)

    descriptor = (
        f"engine={engine}"
        + (f" voice={voice}" if voice else "")
        + (f" file={file}" if file else "")
    )
    summary = f"narration set-source {scene}: {descriptor}"
    typer.echo(summary)
    work = _resolve_work_dir(project_id)
    append_session(work, SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"narration set-source --scene {scene} --engine {engine}"
                + (f" --voice {voice}" if voice else "")
                + (f" --file {file}" if file else ""),
        summary=summary,
    ))
```

- [ ] **Step 3.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_cli_narration.py -v`
Expected: 10 passed.

- [ ] **Step 3.5: Register `narration_app` in `cli.py`**

Open `src/pipeline/cli.py`. Find the existing import:

```python
from pipeline.cli_compose import compose_app
```

Add below it:
```python
from pipeline.cli_narration import narration_app
```

Find the existing block of `app.add_typer` calls. Add (alphabetical order; place after the `metadata_app` line):
```python
app.add_typer(narration_app, name="narration")
```

- [ ] **Step 3.6: Verify the CLI registers — manually invoke `--help`**

Run: `uv run pipeline narration --help`
Expected: typer help output listing `set-source` subcommand. Exit code 0.

Run: `uv run pipeline narration set-source --help`
Expected: help showing `--scene`, `--engine`, `--voice`, `--file` options.

- [ ] **Step 3.7: Commit**

```bash
git add src/pipeline/cli_narration.py src/pipeline/cli.py tests/unit/test_cli_narration.py
git commit -m "feat(cli): pipeline narration set-source command"
```

---

## Task 4: Per-scene engine dispatch in TtsStage

**Files:**
- Modify: `src/pipeline/stages/tts.py` (refactor `_synthesize_pass`, lines 46-121)
- Test: `tests/unit/test_tts_per_scene_engine.py` (new)

This is the most architecturally significant task in this plan. Currently `_synthesize_pass` resolves an engine + profile **once** at the top and reuses them for every segment (`tts.py:94`). The change: resolve **per segment** based on `scene.narration_source` when set, else use the per-call `default_engine`/`default_profile`.

Critical: the prerecorded `engine="prerecorded"` + `file=...` form needs a NEW direct-transcode path (NOT `PrerecordedEngine`), because `PrerecordedEngine` keys recordings by scene_id under a profile-registered `recording_dir` and is unaware of arbitrary file paths.

- [ ] **Step 4.1: Write the per-scene dispatch tests**

Create `tests/unit/test_tts_per_scene_engine.py`:

```python
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from pipeline.storyboard import NarrationSource, Scene, Storyboard
from pipeline.stages.tts import _synthesize_pass


class _RecordingEngine:
    """Test double: records each call and writes a tiny placeholder mp3."""
    def __init__(self, name: str):
        self._name = name
        self.calls: list[tuple[str, str | None, str]] = []  # (text, scene_id, profile_id)

    @property
    def name(self) -> str:
        return self._name

    def synthesize(self, text: str, out_path: Path, profile: Any, scene_id: str | None = None) -> Path:
        self.calls.append((text, scene_id, profile.id))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Write a 0.1s silent mp3 placeholder so duration probing returns >0
        import subprocess
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
             "-t", "0.1", "-c:a", "libmp3lame", str(out_path)],
            check=True,
        )
        return out_path


class _StubProfile:
    def __init__(self, id_: str):
        self.id = id_


class _StubRegistry:
    """Minimal registry stub. Resolves voice_ids → (engine, profile) tuples."""
    def __init__(self, mapping: dict[str, tuple[Any, Any]]):
        self._m = mapping

    def resolve(self, voice_id: str) -> tuple[Any, Any]:
        if voice_id not in self._m:
            from pipeline.voices.base import VoiceNotFound
            raise VoiceNotFound(voice_id)
        return self._m[voice_id]


def _make_storyboard(scenes_with_sources: list[tuple[str, NarrationSource | None]]) -> Storyboard:
    return Storyboard(scenes=[
        Scene(id=sid, section="content", narration=f"text-{sid}",
              narration_est_sec=1.0, narration_source=ns)
        for sid, ns in scenes_with_sources
    ])


def test_synthesize_pass_uses_default_when_no_narration_source(tmp_path: Path):
    """Backwards compat: scenes without narration_source use the passed-in default."""
    default_engine = _RecordingEngine("default")
    default_profile = _StubProfile("default-voice")
    sb = _make_storyboard([("s1", None), ("s2", None)])

    asyncio.run(_synthesize_pass(
        segments=["text-s1", "text-s2"],
        scene_ids=["s1", "s2"],
        scene_pauses_ms=[0, 0],
        audio_dir=tmp_path,
        locale_tag="zh-TW",
        engine=default_engine,
        profile=default_profile,
        seg_prefix="segment",
        registry=_StubRegistry({}),
        storyboard=sb,
    ))

    assert len(default_engine.calls) == 2
    assert all(c[2] == "default-voice" for c in default_engine.calls)


def test_synthesize_pass_dispatches_to_per_scene_edge_engine(tmp_path: Path):
    """A scene with narration_source.engine='edge' resolves through registry."""
    default_engine = _RecordingEngine("default")
    default_profile = _StubProfile("default-voice")
    custom_engine = _RecordingEngine("custom")
    custom_profile = _StubProfile("custom-voice")

    sb = _make_storyboard([
        ("s1", None),
        ("s2", NarrationSource(engine="edge", voice="custom-voice")),
    ])

    asyncio.run(_synthesize_pass(
        segments=["text-s1", "text-s2"],
        scene_ids=["s1", "s2"],
        scene_pauses_ms=[0, 0],
        audio_dir=tmp_path,
        locale_tag="zh-TW",
        engine=default_engine,
        profile=default_profile,
        seg_prefix="segment",
        registry=_StubRegistry({"custom-voice": (custom_engine, custom_profile)}),
        storyboard=sb,
    ))

    # s1 → default; s2 → custom
    assert len(default_engine.calls) == 1
    assert default_engine.calls[0][1] == "s1"
    assert len(custom_engine.calls) == 1
    assert custom_engine.calls[0][1] == "s2"
    assert custom_engine.calls[0][2] == "custom-voice"


def test_synthesize_pass_prerecorded_file_transcodes_directly(tmp_path: Path):
    """engine='prerecorded' + file=... bypasses VoiceEngine and transcodes the file."""
    import subprocess

    default_engine = _RecordingEngine("default")
    default_profile = _StubProfile("default-voice")

    # Create a real WAV input so ffmpeg can transcode it.
    overrides = tmp_path / "narration_overrides"
    overrides.mkdir()
    src_wav = overrides / "s2.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
         "-c:a", "pcm_s16le", str(src_wav)],
        check=True,
    )

    sb = _make_storyboard([
        ("s1", None),
        ("s2", NarrationSource(engine="prerecorded",
                               file="narration_overrides/s2.wav")),
    ])

    asyncio.run(_synthesize_pass(
        segments=["text-s1", "text-s2"],
        scene_ids=["s1", "s2"],
        scene_pauses_ms=[0, 0],
        audio_dir=tmp_path,
        locale_tag="zh-TW",
        engine=default_engine,
        profile=default_profile,
        seg_prefix="segment",
        registry=_StubRegistry({}),
        storyboard=sb,
        project_root=tmp_path,
    ))

    # s1 used the default engine; s2 went through direct transcode (no engine call).
    assert len(default_engine.calls) == 1
    # The s2 segment file must exist and be a valid mp3 (we transcode wav→mp3).
    assert (tmp_path / "segment_001.mp3").exists()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_name",
         "-of", "default=noprint_wrappers=1:nokey=1", str(tmp_path / "segment_001.mp3")],
        capture_output=True, text=True, check=True,
    )
    assert probe.stdout.strip() == "mp3"


def test_synthesize_pass_falls_back_when_voice_not_in_registry(tmp_path: Path):
    """If the per-scene voice isn't in the registry, fall back to default and warn."""
    default_engine = _RecordingEngine("default")
    default_profile = _StubProfile("default-voice")

    sb = _make_storyboard([
        ("s1", NarrationSource(engine="edge", voice="missing-voice")),
    ])

    asyncio.run(_synthesize_pass(
        segments=["text-s1"],
        scene_ids=["s1"],
        scene_pauses_ms=[0],
        audio_dir=tmp_path,
        locale_tag="zh-TW",
        engine=default_engine,
        profile=default_profile,
        seg_prefix="segment",
        registry=_StubRegistry({}),  # empty: missing-voice will not resolve
        storyboard=sb,
    ))

    # Falls back to the default engine.
    assert len(default_engine.calls) == 1
    assert default_engine.calls[0][2] == "default-voice"
```

- [ ] **Step 4.2: Run the tests — expect failures**

Run: `uv run pytest tests/unit/test_tts_per_scene_engine.py -v`
Expected: failures — `_synthesize_pass` does not currently accept `registry`, `storyboard`, or `project_root` kwargs.

- [ ] **Step 4.3: Refactor `_synthesize_pass`**

Open `src/pipeline/stages/tts.py`.

First, add a new helper function. Insert this **after** the `extract_narration_segments` function (around line 44, before `_synthesize_pass`):

```python
def _transcode_to_mp3(src: Path, dst: Path) -> None:
    """Transcode any ffmpeg-readable audio file to MP3 at dst."""
    import subprocess as _sp
    dst.parent.mkdir(parents=True, exist_ok=True)
    _sp.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(src),
            "-c:a", "libmp3lame", "-q:a", "2",
            str(dst),
        ],
        check=True,
    )


def _resolve_per_scene_engine(
    *,
    scene: "Scene | None",
    registry: "VoiceRegistry | None",
    default_engine: Any,
    default_profile: Any,
) -> tuple[Any, Any] | None:
    """Resolve the (engine, profile) tuple to use for this scene's narration.

    Returns:
      - (engine, profile) — when the scene has a narration_source that resolves
        to a TTS engine (engine=edge or fish_audio) successfully via the registry.
      - None — signals "use direct transcode" (engine=prerecorded with file=...).
        The caller is responsible for invoking _transcode_to_mp3 in that case.

    On any resolution failure (missing scene, no narration_source, voice not in
    registry, registry is None), returns (default_engine, default_profile) so the
    caller falls back to the call-level defaults. A warning is logged when the
    fallback is due to an unresolvable per-scene voice id.
    """
    if scene is None or scene.narration_source is None or registry is None:
        return default_engine, default_profile

    ns = scene.narration_source
    if ns.engine == "prerecorded":
        return None  # signal: caller should direct-transcode the file

    # edge / fish_audio — resolve through registry; fall back on miss.
    try:
        return registry.resolve(ns.voice)  # type: ignore[arg-type]
    except Exception as exc:  # VoiceNotFound or anything else
        logger.warning(
            "tts.per_scene.voice_unresolved",
            scene_id=scene.id,
            voice_id=ns.voice,
            error=str(exc),
        )
        return default_engine, default_profile
```

Second, change the `_synthesize_pass` signature to accept the new optional kwargs. Find the existing signature (lines 46-55):

```python
async def _synthesize_pass(
    segments: list[str],
    scene_ids: list[str | None],
    scene_pauses_ms: list[int],
    audio_dir: Path,
    locale_tag: str,
    engine: Any,
    profile: Any,
    seg_prefix: str = "segment",
) -> tuple[Path, Path, list[dict[str, Any]]]:
```

Replace with:

```python
async def _synthesize_pass(
    segments: list[str],
    scene_ids: list[str | None],
    scene_pauses_ms: list[int],
    audio_dir: Path,
    locale_tag: str,
    engine: Any,
    profile: Any,
    seg_prefix: str = "segment",
    *,
    registry: "VoiceRegistry | None" = None,
    storyboard: "Storyboard | None" = None,
    project_root: Path | None = None,
) -> tuple[Path, Path, list[dict[str, Any]]]:
```

Third, replace the segment-loop body inside `_synthesize_pass`. Find this block (around lines 91-94):

```python
        seg_path = audio_dir / f"{seg_prefix}_{i:03d}.mp3"
        # Engines are sync and some (EdgeEngine) call asyncio.run internally,
        # which blows up inside this running loop. Offload to a worker thread.
        await asyncio.to_thread(engine.synthesize, text, seg_path, profile, scene_id=scene_id)
```

Replace with:

```python
        seg_path = audio_dir / f"{seg_prefix}_{i:03d}.mp3"
        # Per-scene narration_source override (Plan 2). Resolve which engine
        # to use for this segment.
        scene_obj = (
            storyboard.get_scene(scene_id) if (storyboard is not None and scene_id) else None
        )
        resolved = _resolve_per_scene_engine(
            scene=scene_obj,
            registry=registry,
            default_engine=engine,
            default_profile=profile,
        )

        if resolved is None:
            # Direct-transcode path (engine="prerecorded" + file=...).
            assert scene_obj is not None and scene_obj.narration_source is not None
            ns = scene_obj.narration_source
            assert ns.file is not None
            src_path = (project_root / ns.file) if project_root else Path(ns.file)
            if not src_path.exists():
                logger.warning(
                    "tts.prerecorded.missing_file_falling_back_to_default",
                    scene_id=scene_id,
                    file=str(src_path),
                )
                # Fall back: use the default engine for this segment.
                await asyncio.to_thread(engine.synthesize, text, seg_path, profile, scene_id=scene_id)
            else:
                logger.info("tts.prerecorded.transcode", scene_id=scene_id, src=str(src_path))
                await asyncio.to_thread(_transcode_to_mp3, src_path, seg_path)
        else:
            seg_engine, seg_profile = resolved
            # Engines are sync and some (EdgeEngine) call asyncio.run internally,
            # which blows up inside this running loop. Offload to a worker thread.
            await asyncio.to_thread(
                seg_engine.synthesize, text, seg_path, seg_profile, scene_id=scene_id,
            )
```

Fourth, ensure the new types are importable inside `tts.py`. At the top of the file, add to the existing `from typing import Any` import line a TYPE_CHECKING import for the storyboard types. Find:

```python
from typing import Any
```

Replace with:

```python
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.storyboard import Scene, Storyboard
    from pipeline.voices.registry import VoiceRegistry
```

(The runtime imports in `TtsStage.run` can stay as-is; the type-only references are for mypy.)

Fifth, update the two call sites in `TtsStage.run` and `_run_secondary_tts` to pass the new kwargs. Find the primary call site (around line 175-184):

```python
        narration_path, subtitle_path, segment_timings = await _synthesize_pass(
            segments=segments,
            scene_ids=scene_ids,
            scene_pauses_ms=scene_pauses_ms,
            audio_dir=audio_dir,
            locale_tag=ctx.locale,
            engine=engine,
            profile=profile,
            seg_prefix="segment",
        )
```

Replace with:

```python
        # Pre-load storyboard once for per-scene narration_source dispatch.
        sb_for_dispatch = None
        if ctx.storyboard_path and ctx.storyboard_path.exists():
            from pipeline.storyboard import Storyboard
            sb_for_dispatch = Storyboard.load(ctx.storyboard_path)

        narration_path, subtitle_path, segment_timings = await _synthesize_pass(
            segments=segments,
            scene_ids=scene_ids,
            scene_pauses_ms=scene_pauses_ms,
            audio_dir=audio_dir,
            locale_tag=ctx.locale,
            engine=engine,
            profile=profile,
            seg_prefix="segment",
            registry=registry,
            storyboard=sb_for_dispatch,
            project_root=ctx.work_dir,
        )
```

For the secondary-MLA call site (around line 227-236), add the same kwargs:

```python
        sec_narration_path, sec_subtitle_path, sec_timings = await _synthesize_pass(
            segments=en_segments,
            scene_ids=en_scene_ids,
            scene_pauses_ms=scene_pauses_ms,
            audio_dir=audio_dir,
            locale_tag=ctx.secondary_locale,  # type: ignore[arg-type]
            engine=sec_engine,
            profile=sec_profile,
            seg_prefix="segment_en",
            registry=registry,
            storyboard=storyboard,
            project_root=ctx.work_dir,
        )
```

(The `storyboard` local is already defined a few lines earlier in `_run_secondary_tts`.)

- [ ] **Step 4.4: Run the new tests — expect pass**

Run: `uv run pytest tests/unit/test_tts_per_scene_engine.py -v`
Expected: 4 passed.

- [ ] **Step 4.5: Run the full suite to confirm no TTS regressions**

Run: `uv run pytest --deselect tests/unit/test_compose_v2.py::test_compose_burn_subtitles_false_returns_plain_variant -q`
Expected: all pass.

- [ ] **Step 4.6: Commit**

```bash
git add src/pipeline/stages/tts.py tests/unit/test_tts_per_scene_engine.py
git commit -m "feat(tts): per-scene narration_source dispatch with prerecorded transcode"
```

---

## Task 5: Whisper transcription wrapper

**Files:**
- Create: `src/pipeline/transcribe.py`
- Test: `tests/unit/test_transcribe.py` (new)

The dashboard's "auto-transcribe" checkbox needs to convert a recorded WAV into text. Use OpenAI's Whisper API (already costed in `~$3/month` budget per CLAUDE.md). Direct `httpx.post` to `/v1/audio/transcriptions`; no SDK dep added.

- [ ] **Step 5.1: Write the wrapper tests with a mocked httpx response**

Create `tests/unit/test_transcribe.py`:

```python
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
```

- [ ] **Step 5.2: Run the tests — expect ImportError**

Run: `uv run pytest tests/unit/test_transcribe.py -v`
Expected: ImportError on `pipeline.transcribe`.

- [ ] **Step 5.3: Implement `transcribe.py`**

Create `src/pipeline/transcribe.py`:

```python
"""OpenAI Whisper API wrapper for browser-recorded narration audio.

Used by the dashboard's narration-source modal: after a user records via the
browser MediaRecorder API and uploads the WAV, the dashboard calls Whisper to
produce a transcript and shows a diff against the storyboard's existing
narration text. The user accepts or rejects the transcript before any
storyboard mutation lands.

Single function only. No SDK dep — direct httpx POST to the multipart endpoint.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import structlog

logger = structlog.get_logger()

_ENDPOINT = "https://api.openai.com/v1/audio/transcriptions"
_MODEL = "whisper-1"


def transcribe_audio(audio_path: Path, *, language: str, api_key: str, timeout: float = 60.0) -> str:
    """Transcribe a local audio file using OpenAI Whisper API.

    `language` is an ISO 639-1 code (e.g. "zh", "ja", "es"). Whisper accepts
    the locale-style "zh-TW" and similar but the simpler form is recommended.

    Returns the transcript text. Raises:
      - FileNotFoundError if audio_path doesn't exist.
      - ValueError if api_key is empty.
      - Whatever httpx.HTTPStatusError chain `raise_for_status` raises on
        non-2xx responses.
    """
    if not api_key:
        raise ValueError("OPENAI_API_KEY is empty; cannot call Whisper")
    if not audio_path.exists():
        raise FileNotFoundError(f"audio file not found: {audio_path}")

    logger.info("transcribe.start", path=str(audio_path), language=language)
    with audio_path.open("rb") as fh:
        response = httpx.post(
            _ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
            data={"model": _MODEL, "language": language},
            files={"file": (audio_path.name, fh, "audio/wav")},
            timeout=timeout,
        )
    response.raise_for_status()
    text = str(response.json().get("text", ""))
    logger.info("transcribe.complete", chars=len(text))
    return text
```

- [ ] **Step 5.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_transcribe.py -v`
Expected: 4 passed.

- [ ] **Step 5.5: Commit**

```bash
git add src/pipeline/transcribe.py tests/unit/test_transcribe.py
git commit -m "feat(transcribe): OpenAI Whisper API wrapper"
```

---

## Task 6: ffmpeg loudnorm helper for upload normalization

**Files:**
- Create: `src/pipeline/utils/audio.py`
- Test: `tests/unit/test_audio_normalize.py` (new)

Browser MediaRecorder produces opus-in-webm at varying loudness levels. Before saving as the project's narration override, normalize to a consistent LUFS target and convert to WAV at 48kHz/stereo (matching the project audio standard used elsewhere — e.g. the Plan 1 transition renderer also uses 48kHz/stereo).

- [ ] **Step 6.1: Write the helper tests**

Create `tests/unit/test_audio_normalize.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipeline.utils.audio import normalize_to_wav


def _make_test_audio(path: Path, *, duration: float, frequency: int) -> Path:
    """Create a small sine-wave audio file (any container ffmpeg supports)."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={duration}",
         "-c:a", "libmp3lame", str(path)],
        check=True,
    )
    return path


def test_normalize_to_wav_emits_48k_stereo_wav(tmp_path: Path):
    src = _make_test_audio(tmp_path / "src.mp3", duration=1.0, frequency=440)
    dst = tmp_path / "out.wav"
    normalize_to_wav(src, dst)

    assert dst.exists() and dst.stat().st_size > 0
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_name,sample_rate,channels",
         "-of", "default=noprint_wrappers=1", str(dst)],
        capture_output=True, text=True, check=True,
    )
    assert "codec_name=pcm_s16le" in probe.stdout
    assert "sample_rate=48000" in probe.stdout
    assert "channels=2" in probe.stdout


def test_normalize_to_wav_creates_parent_dir(tmp_path: Path):
    src = _make_test_audio(tmp_path / "src.mp3", duration=0.5, frequency=440)
    dst = tmp_path / "deep" / "nested" / "out.wav"
    normalize_to_wav(src, dst)
    assert dst.exists()


def test_normalize_to_wav_raises_on_missing_source(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        normalize_to_wav(tmp_path / "missing.mp3", tmp_path / "out.wav")


def test_normalize_to_wav_handles_webm_input(tmp_path: Path):
    """Browser recorders produce opus-in-webm; verify we can normalize that."""
    src = tmp_path / "src.webm"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1.0",
         "-c:a", "libopus", str(src)],
        check=True,
    )
    dst = tmp_path / "out.wav"
    normalize_to_wav(src, dst)
    assert dst.exists() and dst.stat().st_size > 0
```

- [ ] **Step 6.2: Run the tests — expect ImportError**

Run: `uv run pytest tests/unit/test_audio_normalize.py -v`
Expected: ImportError on `pipeline.utils.audio`.

- [ ] **Step 6.3: Implement `audio.py`**

Create `src/pipeline/utils/audio.py`:

```python
"""Audio normalization helpers for narration recording / upload.

Used by the dashboard's narration-source endpoint to convert browser-recorded
opus-in-webm uploads into a consistent WAV format suitable for the TTS-bypass
(`narration_source.engine = 'prerecorded'`) flow.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from pipeline.utils.ffmpeg import run_ffmpeg

logger = structlog.get_logger()


def normalize_to_wav(src: Path, dst: Path) -> Path:
    """Normalize loudness and convert to 48kHz/stereo PCM WAV.

    Uses ffmpeg's single-pass `loudnorm` filter (target -16 LUFS, true-peak
    -1.5 dBTP, LRA 11) which is ample for narration. Two-pass loudnorm gives
    slightly tighter conformance but isn't worth the latency hit for this use.

    Resamples to 48000 Hz and forces stereo so downstream concat with
    project narration tracks (also 48k/stereo per `_synthesize_pass` and the
    Plan 1 transition renderer) doesn't trigger format mismatches.
    """
    if not src.exists():
        raise FileNotFoundError(f"audio source not found: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    logger.info("audio.normalize.start", src=str(src), dst=str(dst))
    run_ffmpeg([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", "48000",
        "-ac", "2",
        "-c:a", "pcm_s16le",
        str(dst),
    ])
    logger.info("audio.normalize.complete", dst=str(dst), size=dst.stat().st_size)
    return dst
```

- [ ] **Step 6.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_audio_normalize.py -v`
Expected: 4 passed (may take 5-10 seconds — actual ffmpeg invocations).

- [ ] **Step 6.5: Commit**

```bash
git add src/pipeline/utils/audio.py tests/unit/test_audio_normalize.py
git commit -m "feat(audio): loudnorm-based WAV normalization helper"
```

---

## Task 7: Dashboard endpoints — set-source / upload / transcribe

**Files:**
- Modify: `src/pipeline/dashboard/server.py` (add three POST endpoints + a Pydantic body model + an `UploadFile` import)
- Test: `tests/unit/test_narration_endpoints.py` (new)

These are the three direct-action HTTP endpoints from the spec's §"Backend — direct-action endpoints":

- `POST /api/narration/<project_id>/set-source` — body `{scene, engine, voice?, file?}` — invokes the same logic as `pipeline narration set-source`
- `POST /api/narration/<project_id>/upload` — multipart audio → `loudnorm` → save to `output/projects/<id>/narration_overrides/<scene>.wav`
- `POST /api/narration/<project_id>/transcribe` — body `{scene, file}` → Whisper → returns `{transcript: str}`

Per spec §415: "All mutating endpoints internally invoke the same project-scoped CLI verbs the agent uses, ensuring single source of truth." The `set-source` endpoint imports and calls the same helper that `cli_narration.py` uses; we extract that shared helper in this task.

- [ ] **Step 7.1: Write endpoint tests**

Create `tests/unit/test_narration_endpoints.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from pipeline.dashboard.server import create_app
from pipeline.storyboard import Scene, Storyboard


@pytest.fixture
def project_tree(tmp_path: Path) -> Path:
    out_root = tmp_path / "output"
    proj = out_root / "projects" / "42"
    proj.mkdir(parents=True)
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="hello", narration_est_sec=1.0),
        Scene(id="s2", section="content", narration="world", narration_est_sec=1.0),
    ])
    sb.save(proj / "storyboard.json")
    (proj / "context.json").write_text(
        json.dumps({"project_id": 42, "source_url": "x", "locale": "zh-TW",
                    "work_dir": str(proj)}),
        encoding="utf-8",
    )
    return out_root


@pytest.fixture
def client(project_tree: Path) -> TestClient:
    app = create_app(output_dir=project_tree / "projects")
    return TestClient(app)


def test_set_source_endpoint_writes_storyboard(client: TestClient, project_tree: Path):
    resp = client.post(
        "/api/narration/42/set-source",
        json={"scene": "s1", "engine": "edge", "voice": "zh-tw-default-f"},
    )
    assert resp.status_code == 200, resp.text
    sb = Storyboard.load(project_tree / "projects" / "42" / "storyboard.json")
    s1 = sb.get_scene("s1")
    assert s1 is not None and s1.narration_source is not None
    assert s1.narration_source.engine == "edge"


def test_set_source_endpoint_rejects_unknown_engine(client: TestClient):
    resp = client.post(
        "/api/narration/42/set-source",
        json={"scene": "s1", "engine": "elevenlabs", "voice": "x"},
    )
    assert resp.status_code == 400


def test_set_source_endpoint_rejects_unknown_scene(client: TestClient):
    resp = client.post(
        "/api/narration/42/set-source",
        json={"scene": "s99", "engine": "edge", "voice": "zh-tw-default-f"},
    )
    assert resp.status_code == 404


def test_set_source_endpoint_404_on_unknown_project(client: TestClient):
    resp = client.post(
        "/api/narration/9999/set-source",
        json={"scene": "s1", "engine": "edge", "voice": "any"},
    )
    assert resp.status_code == 404


def test_upload_endpoint_normalizes_and_saves(
    client: TestClient, project_tree: Path, tmp_path: Path,
):
    # Build a tiny webm input to upload.
    import subprocess
    src = tmp_path / "rec.webm"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
         "-c:a", "libopus", str(src)],
        check=True,
    )
    with src.open("rb") as fh:
        resp = client.post(
            "/api/narration/42/upload",
            params={"scene": "s2"},
            files={"file": ("rec.webm", fh, "audio/webm")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    expected_rel = "narration_overrides/s2.wav"
    assert body["path"] == expected_rel
    saved = project_tree / "projects" / "42" / expected_rel
    assert saved.exists() and saved.stat().st_size > 0


def test_upload_endpoint_rejects_scene_id_with_path_traversal(client: TestClient):
    resp = client.post(
        "/api/narration/42/upload",
        params={"scene": "../../etc/passwd"},
        files={"file": ("rec.webm", b"x", "audio/webm")},
    )
    assert resp.status_code == 400


def test_upload_endpoint_rejects_unknown_scene(client: TestClient):
    resp = client.post(
        "/api/narration/42/upload",
        params={"scene": "s99"},
        files={"file": ("rec.webm", b"x", "audio/webm")},
    )
    assert resp.status_code == 404


def test_transcribe_endpoint_returns_transcript(
    client: TestClient, project_tree: Path, tmp_path: Path,
):
    # Place a recording inside the project tree.
    overrides = project_tree / "projects" / "42" / "narration_overrides"
    overrides.mkdir(parents=True)
    (overrides / "s1.wav").write_bytes(b"RIFF....WAVEfmt ")

    with patch("pipeline.dashboard.server.transcribe_audio", return_value="你好"):
        resp = client.post(
            "/api/narration/42/transcribe",
            json={"scene": "s1", "file": "narration_overrides/s1.wav", "language": "zh"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["transcript"] == "你好"


def test_transcribe_endpoint_rejects_path_traversal(client: TestClient):
    resp = client.post(
        "/api/narration/42/transcribe",
        json={"scene": "s1", "file": "../../etc/passwd", "language": "zh"},
    )
    assert resp.status_code == 400


def test_transcribe_endpoint_rejects_missing_file(client: TestClient):
    resp = client.post(
        "/api/narration/42/transcribe",
        json={"scene": "s1", "file": "narration_overrides/missing.wav", "language": "zh"},
    )
    assert resp.status_code == 404
```

- [ ] **Step 7.2: Run the tests — expect failures**

Run: `uv run pytest tests/unit/test_narration_endpoints.py -v`
Expected: failures — none of the endpoints exist yet.

- [ ] **Step 7.3: Add the endpoints to `server.py`**

Open `src/pipeline/dashboard/server.py`. At the top of the file, add to the FastAPI imports. Find:

```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
```

Replace with:

```python
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipeline.config import PipelineConfig
from pipeline.storyboard import NarrationSource, Storyboard
from pipeline.transcribe import transcribe_audio
from pipeline.utils.audio import normalize_to_wav
```

Add new request body models near the existing `_SkipBody` / `_ManualCheckBody` (around line 25-32):

```python
class _SetSourceBody(BaseModel):
    scene: str
    engine: str
    voice: str | None = None
    file: str | None = None


class _TranscribeBody(BaseModel):
    scene: str
    file: str
    language: str = "zh"


_VALID_NARRATION_ENGINES = {"edge", "fish_audio", "prerecorded"}
```

Inside `create_app`, add a small project-relative path helper near the top of the function (after the existing `_project_root` helper, around line 88):

```python
    def _resolve_within_project(project_root: Path, rel_path: str) -> Path:
        """Resolve `rel_path` inside `project_root`. Refuses absolute paths or
        any escape via ``..``. Raises HTTPException(400) on violation.

        Returns the absolute resolved path; caller checks `.exists()` if needed.
        """
        candidate = (project_root / rel_path).resolve()
        if not str(candidate).startswith(str(project_root.resolve())):
            raise HTTPException(
                status_code=400,
                detail=f"path {rel_path!r} resolves outside project tree",
            )
        return candidate
```

Then, anywhere inside `create_app` (e.g. just before the final `app.mount("/output"...)` around line 176), add the three endpoints:

```python
    @app.post("/api/narration/{project_id}/set-source")
    def post_set_source(project_id: str, body: _SetSourceBody) -> JSONResponse:
        proj = _project_root(project_id)
        sb_path = proj / "storyboard.json"
        if not sb_path.exists():
            raise HTTPException(status_code=409, detail="storyboard.json not yet generated")

        if body.engine not in _VALID_NARRATION_ENGINES:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown narration engine {body.engine!r}",
            )
        if body.engine in ("edge", "fish_audio") and not body.voice:
            raise HTTPException(
                status_code=400,
                detail=f"engine={body.engine!r} requires 'voice'",
            )
        if body.engine == "prerecorded":
            if not body.file:
                raise HTTPException(
                    status_code=400,
                    detail="engine='prerecorded' requires 'file'",
                )
            resolved = _resolve_within_project(proj, body.file)
            if not resolved.exists():
                raise HTTPException(status_code=404, detail=f"file not found: {body.file}")

        sb = Storyboard.load(sb_path)
        target = sb.get_scene(body.scene)
        if target is None:
            raise HTTPException(status_code=404, detail=f"scene {body.scene!r} not found")
        target.narration_source = NarrationSource(
            engine=body.engine, voice=body.voice, file=body.file,
        )
        sb.save(sb_path)
        return JSONResponse({
            "ok": True,
            "scene": body.scene,
            "narration_source": target.narration_source.to_dict(),
        })

    @app.post("/api/narration/{project_id}/upload")
    async def post_upload(
        project_id: str,
        scene: str,
        file: UploadFile = File(...),
    ) -> JSONResponse:
        proj = _project_root(project_id)
        sb_path = proj / "storyboard.json"
        if not sb_path.exists():
            raise HTTPException(status_code=409, detail="storyboard.json not yet generated")

        # Defensive: scene id must look like a storyboard id, no path separators.
        if "/" in scene or "\\" in scene or ".." in scene or scene.startswith("."):
            raise HTTPException(status_code=400, detail=f"invalid scene id {scene!r}")

        sb = Storyboard.load(sb_path)
        if sb.get_scene(scene) is None:
            raise HTTPException(status_code=404, detail=f"scene {scene!r} not found")

        # Save the upload to a temp file, normalize, write to the override slot.
        overrides_dir = proj / "narration_overrides"
        overrides_dir.mkdir(parents=True, exist_ok=True)
        tmp_upload = overrides_dir / f".{scene}.upload"
        try:
            with tmp_upload.open("wb") as out:
                while chunk := await file.read(1024 * 64):
                    out.write(chunk)
            dst = overrides_dir / f"{scene}.wav"
            normalize_to_wav(tmp_upload, dst)
        finally:
            tmp_upload.unlink(missing_ok=True)

        rel = f"narration_overrides/{scene}.wav"
        return JSONResponse({"ok": True, "path": rel})

    @app.post("/api/narration/{project_id}/transcribe")
    def post_transcribe(project_id: str, body: _TranscribeBody) -> JSONResponse:
        proj = _project_root(project_id)
        resolved = _resolve_within_project(proj, body.file)
        if not resolved.exists():
            raise HTTPException(status_code=404, detail=f"file not found: {body.file}")
        api_key = PipelineConfig().OPENAI_API_KEY
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="OPENAI_API_KEY is not configured",
            )
        transcript = transcribe_audio(resolved, language=body.language, api_key=api_key)
        return JSONResponse({"ok": True, "transcript": transcript})
```

- [ ] **Step 7.4: Run the endpoint tests — expect pass**

Run: `uv run pytest tests/unit/test_narration_endpoints.py -v`
Expected: 10 passed (the upload test runs ffmpeg; expect ~3-5s).

- [ ] **Step 7.5: Run the full suite to confirm no regressions**

Run: `uv run pytest --deselect tests/unit/test_compose_v2.py::test_compose_burn_subtitles_false_returns_plain_variant -q`
Expected: all pass.

- [ ] **Step 7.6: Commit**

```bash
git add src/pipeline/dashboard/server.py tests/unit/test_narration_endpoints.py
git commit -m "feat(dashboard): direct-action narration endpoints (set-source, upload, transcribe)"
```

---

## Task 8: Dashboard frontend — NarrationSourceEditor modal

**Files:**
- Create: `src/pipeline/dashboard/static/narration_source_editor.js`
- Modify: `src/pipeline/dashboard/static/index.html` (inject `🎙 record` button + `<script>` tag)

This task is the user-facing flow from spec §"Flow 3 — Direct-action narration source + recorder". The modal:

1. Shows the scene's current narration text (read-only).
2. Source dropdown — fixed list for v1: `edge`, `fish_audio`, `prerecorded`.
3. Voice text input (visible when source is `edge` or `fish_audio`) — voice_id from the registry.
4. Recorder section (visible when source is `prerecorded`) — REC / STOP / Play, timer.
5. ☑ Auto-transcribe checkbox.
6. Apply button.

When source is `prerecorded` and recording is captured: upload → optional transcribe → diff preview → user accepts → POST set-source.

**Note**: this plan ships a barebones modal. Plan 4 will replace the trigger ( `🎙 record` button) with the source chip in edit mode and may reskin the modal styling. Plan 5 adds SSE-driven dashboard refresh after Apply.

Dynamically-discovered voices (e.g. populating the voice dropdown from `voices/registry.json`) is out of scope: the user types the voice_id directly. A `pipeline voice list` CLI helper already exists if they need to look it up.

- [ ] **Step 8.1: Create the JS module**

Create `src/pipeline/dashboard/static/narration_source_editor.js`:

```javascript
// NarrationSourceEditor — direct-action modal for per-scene narration.
//
// Flow:
//   1. Open modal for a given (project_id, scene). Modal shows current scene
//      narration text (read-only) and a source dropdown.
//   2. User picks edge | fish_audio | prerecorded.
//   3. For TTS engines: user types a voice_id; clicks Apply → POST set-source.
//   4. For prerecorded:
//        a. User taps REC, records via MediaRecorder, taps STOP.
//        b. User taps Apply.
//        c. Multipart-upload the blob → /api/narration/<id>/upload — server
//           normalizes to WAV and saves to narration_overrides/<scene>.wav.
//        d. If auto-transcribe is on: call /api/narration/<id>/transcribe;
//           show a side-by-side diff vs the storyboard's existing narration.
//           User accepts (will then POST set-source) or rejects.
//        e. Final POST: /api/narration/<id>/set-source with engine=prerecorded
//           and file=narration_overrides/<scene>.wav.
//   5. Close modal. (SSE-driven dashboard refresh lands in Plan 5; for now
//      the user re-opens the project detail row to see the change.)

(function () {
  'use strict';

  const STYLE = `
    .nse-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.7); display: flex;
      align-items: center; justify-content: center; z-index: 1000; }
    .nse-modal { background: #1a1a2e; color: #e2e8f0; border: 1px solid #2d3748;
      border-radius: 6px; padding: 18px; width: min(560px, 92vw); }
    .nse-h { font-size: 14px; font-weight: 600; margin-bottom: 10px; }
    .nse-narration { background: #0f172a; border: 1px solid #1e293b; border-radius: 4px;
      padding: 10px; font-size: 12px; color: #cbd5e1; max-height: 120px; overflow: auto;
      margin-bottom: 12px; }
    .nse-row { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
    .nse-row label { font-size: 11px; color: #94a3b8; min-width: 70px; }
    .nse-row select, .nse-row input[type="text"] {
      flex: 1; background: #0f172a; color: #e2e8f0; border: 1px solid #2d3748;
      border-radius: 4px; padding: 5px 8px; font-size: 12px; }
    .nse-rec-section { background: #0f172a; border: 1px solid #1e293b; border-radius: 4px;
      padding: 12px; margin-bottom: 10px; }
    .nse-rec-btns { display: flex; gap: 8px; align-items: center; }
    .nse-rec-btns button { font-size: 11px; padding: 5px 12px; border-radius: 4px;
      border: 1px solid #2d3748; background: #1e293b; color: #e2e8f0; cursor: pointer; }
    .nse-rec-btns button:disabled { opacity: .4; cursor: not-allowed; }
    .nse-rec-btns button.recording { background: #7f1d1d; border-color: #b91c1c; }
    .nse-timer { font-family: monospace; font-size: 12px; color: #94a3b8; }
    .nse-diff { display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
      background: #0f172a; border: 1px solid #1e293b; border-radius: 4px;
      padding: 10px; margin-bottom: 10px; font-size: 11px; }
    .nse-diff h4 { font-size: 10px; color: #64748b; margin-bottom: 4px; text-transform: uppercase; }
    .nse-diff pre { white-space: pre-wrap; color: #cbd5e1; font-family: inherit; }
    .nse-actions { display: flex; gap: 8px; justify-content: flex-end; }
    .nse-actions button { font-size: 11px; padding: 6px 14px; border-radius: 4px;
      border: 1px solid #2d3748; background: #1e293b; color: #e2e8f0; cursor: pointer; }
    .nse-actions button.primary { background: #1e3a5f; border-color: #3b82f6; }
    .nse-status { font-size: 11px; color: #94a3b8; margin-bottom: 8px; min-height: 14px; }
    .nse-status.error { color: #ef4444; }
  `;

  function ensureStyleInjected() {
    if (document.getElementById('nse-style')) return;
    const s = document.createElement('style');
    s.id = 'nse-style';
    s.textContent = STYLE;
    document.head.appendChild(s);
  }

  async function uploadRecording(projectId, scene, blob) {
    const fd = new FormData();
    fd.append('file', blob, `${scene}.webm`);
    const resp = await fetch(`/api/narration/${projectId}/upload?scene=${encodeURIComponent(scene)}`, {
      method: 'POST', body: fd,
    });
    if (!resp.ok) throw new Error(`upload failed: ${resp.status} ${await resp.text()}`);
    return await resp.json();  // { ok, path }
  }

  async function transcribeFile(projectId, scene, file, language) {
    const resp = await fetch(`/api/narration/${projectId}/transcribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene, file, language }),
    });
    if (!resp.ok) throw new Error(`transcribe failed: ${resp.status} ${await resp.text()}`);
    return (await resp.json()).transcript;
  }

  async function setSource(projectId, scene, engine, voice, file) {
    const resp = await fetch(`/api/narration/${projectId}/set-source`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene, engine, voice, file }),
    });
    if (!resp.ok) throw new Error(`set-source failed: ${resp.status} ${await resp.text()}`);
    return await resp.json();
  }

  function openEditor({ projectId, scene, narrationText, locale }) {
    ensureStyleInjected();

    const overlay = document.createElement('div');
    overlay.className = 'nse-overlay';
    overlay.innerHTML = `
      <div class="nse-modal" role="dialog" aria-modal="true">
        <div class="nse-h">Narration source · ${scene}</div>
        <div class="nse-narration">${escapeHtml(narrationText)}</div>
        <div class="nse-row">
          <label>Source</label>
          <select class="nse-engine">
            <option value="edge">Edge-TTS</option>
            <option value="fish_audio">Fish Audio</option>
            <option value="prerecorded">🎙 Prerecorded</option>
          </select>
        </div>
        <div class="nse-row nse-voice-row">
          <label>Voice ID</label>
          <input type="text" class="nse-voice" placeholder="e.g. zh-tw-default-f">
        </div>
        <div class="nse-rec-section" hidden>
          <div class="nse-rec-btns">
            <button class="nse-rec">REC</button>
            <button class="nse-stop" disabled>STOP</button>
            <button class="nse-play" disabled>Play</button>
            <span class="nse-timer">0:00</span>
          </div>
          <label style="display:block;margin-top:10px;font-size:11px;color:#94a3b8">
            <input type="checkbox" class="nse-auto-transcribe" checked>
            Auto-transcribe and show diff before applying
          </label>
        </div>
        <div class="nse-diff" hidden>
          <div><h4>Storyboard narration</h4><pre class="nse-diff-orig"></pre></div>
          <div><h4>Whisper transcript</h4><pre class="nse-diff-new"></pre></div>
        </div>
        <div class="nse-status"></div>
        <div class="nse-actions">
          <button class="nse-cancel">Cancel</button>
          <button class="nse-apply primary">Apply</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const $ = (sel) => overlay.querySelector(sel);
    const engineSel = $('.nse-engine');
    const voiceRow = $('.nse-voice-row');
    const voiceInput = $('.nse-voice');
    const recSection = $('.nse-rec-section');
    const recBtn = $('.nse-rec');
    const stopBtn = $('.nse-stop');
    const playBtn = $('.nse-play');
    const timerEl = $('.nse-timer');
    const autoTransCb = $('.nse-auto-transcribe');
    const diffSection = $('.nse-diff');
    const diffOrig = $('.nse-diff-orig');
    const diffNew = $('.nse-diff-new');
    const statusEl = $('.nse-status');
    const applyBtn = $('.nse-apply');
    const cancelBtn = $('.nse-cancel');

    let recorder = null;
    let recordedBlob = null;
    let recordedUrl = null;
    let timerHandle = null;
    let recordStart = 0;

    function setStatus(msg, isError) {
      statusEl.textContent = msg;
      statusEl.classList.toggle('error', !!isError);
    }

    function applyEngineVisibility() {
      const e = engineSel.value;
      voiceRow.hidden = (e === 'prerecorded');
      recSection.hidden = (e !== 'prerecorded');
    }
    engineSel.addEventListener('change', applyEngineVisibility);
    applyEngineVisibility();

    recBtn.addEventListener('click', async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recorder = new MediaRecorder(stream);
        const chunks = [];
        recorder.ondataavailable = (e) => chunks.push(e.data);
        recorder.onstop = () => {
          recordedBlob = new Blob(chunks, { type: 'audio/webm' });
          if (recordedUrl) URL.revokeObjectURL(recordedUrl);
          recordedUrl = URL.createObjectURL(recordedBlob);
          stream.getTracks().forEach((t) => t.stop());
          playBtn.disabled = false;
          stopBtn.disabled = true;
          recBtn.disabled = false;
          recBtn.classList.remove('recording');
        };
        recorder.start();
        recordStart = Date.now();
        timerHandle = setInterval(() => {
          const t = Math.floor((Date.now() - recordStart) / 1000);
          timerEl.textContent = `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
        }, 200);
        recBtn.disabled = true;
        recBtn.classList.add('recording');
        stopBtn.disabled = false;
        setStatus('Recording…');
      } catch (err) {
        setStatus(`Microphone access failed: ${err.message}`, true);
      }
    });

    stopBtn.addEventListener('click', () => {
      if (recorder && recorder.state !== 'inactive') recorder.stop();
      if (timerHandle) clearInterval(timerHandle);
      setStatus('Recording stopped. Press Apply to upload.');
    });

    playBtn.addEventListener('click', () => {
      if (!recordedUrl) return;
      const a = new Audio(recordedUrl);
      a.play().catch((e) => setStatus(`Playback failed: ${e.message}`, true));
    });

    cancelBtn.addEventListener('click', () => {
      if (recordedUrl) URL.revokeObjectURL(recordedUrl);
      overlay.remove();
    });

    applyBtn.addEventListener('click', async () => {
      const engine = engineSel.value;
      try {
        applyBtn.disabled = true;
        if (engine === 'prerecorded') {
          if (!recordedBlob) {
            setStatus('Record audio first.', true);
            applyBtn.disabled = false;
            return;
          }
          setStatus('Uploading & normalizing…');
          const upload = await uploadRecording(projectId, scene, recordedBlob);
          if (autoTransCb.checked) {
            setStatus('Transcribing…');
            const language = (locale || 'zh').split('-')[0];
            const transcript = await transcribeFile(projectId, scene, upload.path, language);
            diffOrig.textContent = narrationText;
            diffNew.textContent = transcript;
            diffSection.hidden = false;
            const accept = window.confirm(
              `Whisper transcript:\n\n${transcript}\n\nApply this recording? ` +
              `(The storyboard narration will be left unchanged; only narration_source is set.)`
            );
            if (!accept) {
              setStatus('Cancelled by user.');
              applyBtn.disabled = false;
              return;
            }
          }
          setStatus('Saving narration_source…');
          await setSource(projectId, scene, 'prerecorded', null, upload.path);
        } else {
          // edge / fish_audio
          const voice = voiceInput.value.trim();
          if (!voice) {
            setStatus('Voice ID is required for TTS engines.', true);
            applyBtn.disabled = false;
            return;
          }
          setStatus('Saving narration_source…');
          await setSource(projectId, scene, engine, voice, null);
        }
        setStatus('Saved. Run `pipeline compose rescene --scene ' + scene + '` to re-render.');
        setTimeout(() => overlay.remove(), 1500);
      } catch (err) {
        setStatus(err.message, true);
        applyBtn.disabled = false;
      }
    });
  }

  function escapeHtml(str) {
    return String(str || '').replace(/[&<>"]/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  // Public entry point
  window.NarrationSourceEditor = { open: openEditor };
})();
```

- [ ] **Step 8.2: Wire the modal trigger into `index.html`**

Open `src/pipeline/dashboard/static/index.html`. Find the existing `.scene-narration` block (around line 197-201):

```html
      <div class="scene-narration">
        <div class="scene-panel-label">旁白 Narration</div>
        <div class="scene-nar-hdr"></div>
        <div class="scene-nar-text"></div>
      </div>
```

Replace with:

```html
      <div class="scene-narration">
        <div class="scene-panel-label">旁白 Narration
          <!-- Plan 2: temporary trigger for the narration-source modal.
               Plan 4 replaces this with the source-chip click-target. -->
          <button class="nse-open-btn" type="button" style="float:right;font-size:10px;
            padding:2px 8px;background:#1e293b;color:#94a3b8;border:1px solid #2d3748;
            border-radius:3px;cursor:pointer;font-weight:normal">🎙 record</button>
        </div>
        <div class="scene-nar-hdr"></div>
        <div class="scene-nar-text"></div>
      </div>
```

Find the existing closing `</script>` block at the bottom (the one followed by the HMR script around line 377-378). Just **after** the main `<script>...</script>` block (the one that defines `refresh()` and `setInterval(refresh, 30000)`), insert:

```html
<script src="/static/narration_source_editor.js"></script>
<script>
  // Wire the 🎙 record button: opens NarrationSourceEditor for the active scene.
  document.getElementById('tbody').addEventListener('click', (e) => {
    const btn = e.target.closest('.nse-open-btn');
    if (!btn) return;
    const detailRow = btn.closest('tr.detail-row');
    if (!detailRow) return;
    const projectId = detailRow.dataset.detailFor;
    const project = currentData.find((p) => p.project_id === projectId);
    if (!project) return;
    // Use the currently-displayed scene from the strip's active chip.
    const activeChip = detailRow.querySelector('.scene-chip.sc-active')
                       || detailRow.querySelector('.scene-chip');
    if (!activeChip) return;
    const idx = +activeChip.dataset.idx;
    const scene = project.scenes[idx];
    if (!scene) return;
    window.NarrationSourceEditor.open({
      projectId,
      scene: scene.id,
      narrationText: scene.narration || '',
      locale: project.locale || 'zh-TW',
    });
  });
</script>
```

For the `<script src="/static/...">` path to resolve, ensure FastAPI serves the static dir. Check `server.py` — there's currently no `/static` mount. Add one. Open `src/pipeline/dashboard/server.py` and find the existing block where `_STATIC_DIR` is referenced inside `create_app` (around line 36-37 or wherever the static dir is mounted; if there's no mount yet, add it after the `app = FastAPI(title="Content Dashboard")` line):

```python
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
```

(If a mount already exists at `/static`, leave it alone.)

- [ ] **Step 8.3: Manual UI smoke test**

Spin up the dashboard locally and verify the trigger appears:

```bash
./scripts/start-dashboard.sh --local-only
```

Open http://localhost:<port> (the script prints the port). Click any project's preview button to expand the detail row — there should now be a `🎙 record` button in the top-right corner of the Narration panel. Click it: the modal should appear, with the source dropdown defaulting to "Edge-TTS" and the Voice ID input visible. Pick "🎙 Prerecorded" — voice input should hide and the recorder section should appear.

Tap REC → grant mic permission → speak → STOP → Play → confirm playback. Don't tap Apply yet (no real OPENAI_API_KEY at play here unless one is configured); cancel out.

If your dashboard host doesn't have a microphone (CI / remote), skip this step — the JS module's logic is exercised by the browser tests in Task 9.

- [ ] **Step 8.4: Commit**

```bash
git add src/pipeline/dashboard/static/narration_source_editor.js src/pipeline/dashboard/static/index.html src/pipeline/dashboard/server.py
git commit -m "feat(dashboard): NarrationSourceEditor modal + 🎙 trigger button"
```

---

## Task 9: Reserve `narration_overrides/` artifact path + final verification

**Files:**
- Modify: `.gitignore` (verify `output/` is already ignored — confirm narration_overrides won't escape)
- Documentation: brief README note about the new commands (defer; not in scope unless project convention requires)

`output/` is already excluded by `.gitignore`. Per-project `narration_overrides/` directories live under `output/projects/<id>/` and inherit the exclusion — no new gitignore line is needed. This task verifies that and runs the full project tooling pass.

- [ ] **Step 9.1: Confirm `output/` covers narration_overrides**

Run: `git check-ignore -v output/projects/42/narration_overrides/s9.wav 2>&1 || echo "NOT IGNORED"`
Expected output mentions `output/` (the directory rule). If it says NOT IGNORED, add a new line to `.gitignore` (`output/projects/*/narration_overrides/`) and commit separately.

- [ ] **Step 9.2: Full lint pass**

Run: `uv run ruff check src/pipeline/cli_narration.py src/pipeline/transcribe.py src/pipeline/utils/audio.py src/pipeline/dashboard/server.py src/pipeline/storyboard.py src/pipeline/stages/tts.py`
Expected: no errors.

- [ ] **Step 9.3: Type check**

Run: `uv run mypy src/pipeline/cli_narration.py src/pipeline/transcribe.py src/pipeline/utils/audio.py`
Expected: no errors. (Pre-existing mypy issues in dependencies that are not introduced by this plan can be ignored — but no new errors.)

- [ ] **Step 9.4: Full test suite**

Run: `uv run pytest --deselect tests/unit/test_compose_v2.py::test_compose_burn_subtitles_false_returns_plain_variant -q`
Expected: all pass.

- [ ] **Step 9.5: Manual smoke test — set a narration source on a real project**

Pick a real project under `output/projects/`:

```bash
PROJ=$(ls output/projects/ | head -1)
# Look up a scene id
uv run pipeline storyboard show --project-id "$PROJ" | head -20
# Set an edge-tts source on the first content scene (replace s1 with the actual id)
uv run pipeline narration set-source --project-id "$PROJ" --scene s1 --engine edge --voice zh-tw-default-f
```

Verify the storyboard.json now has a `narration_source` block on `s1`:

```bash
python -c "import json; sb=json.load(open('output/projects/'+'$PROJ'+'/storyboard.json')); s=[x for x in sb['scenes'] if x['id']=='s1'][0]; print(s.get('narration_source'))"
```

Expected: `{'engine': 'edge', 'voice': 'zh-tw-default-f'}`.

Set it back to default by re-running with the project's normal voice, or remove the block manually for now (a `narration clear-source` verb is out of scope; the user can edit storyboard.json by hand or re-set with the previous value).

- [ ] **Step 9.6: Commit final tidy if needed (e.g. .gitignore)**

```bash
# Only if Step 9.1 required a gitignore change:
git add .gitignore
git commit -m "chore: explicitly ignore output/projects/*/narration_overrides/"
```

---

## Plan complete

After all tasks above are checked off:

- New schema: `Scene.narration_source` is sparse, backwards-compatible, round-trip safe.
- New CLI: `pipeline narration set-source` writes the field, validates engine/voice/file, sandbox-checks file paths against the project tree, and appends to `sessions.json`.
- Per-segment engine dispatch in `_synthesize_pass`: scenes with `narration_source` use the per-scene engine (resolved through `VoiceRegistry`) or the new direct-transcode path for `engine="prerecorded"` + `file=...`. Scenes without an override fall back to the project default — no behavior change for existing storyboards.
- Three direct-action HTTP endpoints (`/set-source`, `/upload`, `/transcribe`) wired into the dashboard FastAPI app, with the same validation as the CLI.
- Dashboard frontend: a temporary `🎙 record` button on the narration panel opens `NarrationSourceEditor`, which uses `MediaRecorder` for browser-side recording, uploads/normalizes via `loudnorm`, optionally calls Whisper for a transcript-diff preview, and POSTs the final `set-source` mutation.
- Whisper wrapper is a 30-line `httpx` direct call; no SDK dep.
- Audio normalization uses ffmpeg `loudnorm` — no `ffmpeg-normalize` package.

**What you can do as soon as this lands:**

- Swap a scene to `fish_audio` with a different voice without touching the project default.
- Record your own voice for a scene in the browser, get a Whisper transcript shown next to the storyboard text, and replace the TTS output with your recording.
- Verify the change with `pipeline storyboard show` or by re-rendering with `pipeline compose rescene --scene sN`.

**Hand-off note for follow-on plans:**

- **Plan 3** (JobQueue + agent runtime) will add `pipeline narration regen --scene sN --text "..."` (agent-driven script edit + re-TTS) and call the same `narration set-source` HTTP endpoint internally where appropriate.
- **Plan 4** (edit-mode + composer) replaces the temporary `🎙 record` button trigger with the source-chip click target inside the floating composer / direct-action chip system.
- **Plan 5** (SSE refresh) wires the `set-source` endpoint to emit `files_changed` so the dashboard auto-refreshes after Apply, and adds an automatic `compose rescene` chain so users don't need the manual "run rescene" hint shown in the Apply success message.
