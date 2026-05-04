# Click-to-Edit Plan 1 — Transitions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-seam transition primitive (page-turn / fade / slide / wipe / none) to the compose pipeline, with a CLI surface (`pipeline transition set / clear`) usable independently of any UI.

**Architecture:** Sparse `transitions[]` array on the `Storyboard` dataclass; a `TransitionRenderer` Protocol + per-style implementations dispatched via a `REGISTRY` map; cached pre-rendered transition clips inserted into the existing concat-demuxer master-concat path. v1 ships `XfadeRenderer` (uses ffmpeg's built-in `xfade` filter) for all visual styles — `page-turn` is initially aliased to `xfade slideleft`. Swappable later to a PNG/webm `OverlayRenderer` behind the same Protocol with a one-line registry change.

**Tech Stack:** Python 3.12, dataclasses, Typer, FFmpeg (xfade + amix), pytest. No new third-party dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-04-dashboard-click-to-edit-design.md` — §"Storyboard schema", §"Compose pipeline change (Extra A — page-turn primitive)", §"CLI verb surface" rows for `transition set` / `transition clear`.

---

## File Structure

**Create:**

| File | Responsibility |
|---|---|
| `src/pipeline/composer/transitions.py` | `TransitionConfig` dataclass, `TransitionRenderer` Protocol, `HardCutRenderer`, `XfadeRenderer`, `REGISTRY`, cache-key helper, top-level `render_transition` dispatcher |
| `src/pipeline/cli_transition.py` | Typer subapp exposing `transition set` and `transition clear` |
| `tests/unit/test_transitions.py` | Unit tests for renderers, config validation, registry, cache key |
| `tests/unit/test_cli_transition.py` | Unit tests for the CLI commands |
| `tests/integration/test_compose_with_transitions.py` | Integration: storyboard with transitions composes with transition clips inserted between scenes |
| `assets/sfx/.gitkeep` | Reserve the directory; sfx files are user-supplied |

**Modify:**

| File | Change |
|---|---|
| `src/pipeline/storyboard.py` | Add `Transition` dataclass; add `transitions: list[Transition]` field to `Storyboard` with sparse-by-default to_dict / from_dict |
| `src/pipeline/stages/compose.py` | After scene rendering, render transition clips per `storyboard.transitions` and insert them into the `scene_finals` and `scene_finals_no_overlay` lists before `_concat_scenes` is called |
| `src/pipeline/cli_compose.py` | In `rescene` command, after deleting per-scene caches, also delete transition cache entries adjacent to the rescened scene(s) |
| `src/pipeline/cli.py` | Register `transition_app` from `cli_transition.py` via `app.add_typer(transition_app, name="transition")` |

**Out of scope** (later plans):
- Direct-action HTTP endpoint for transitions (Plan 4)
- Dashboard UI / modal editor (Plan 4)
- `narration_source` schema additions (Plan 2)
- JobQueue / agent integration (Plan 3)

---

## Task 1: Add `Transition` dataclass to `storyboard.py`

**Files:**
- Modify: `src/pipeline/storyboard.py:1-50`
- Test: `tests/unit/test_transitions.py` (new)

- [ ] **Step 1.1: Create the test file with the `Transition` parsing test**

Create `tests/unit/test_transitions.py`:

```python
from __future__ import annotations

from pipeline.storyboard import Transition


def test_transition_from_dict_minimal():
    """A minimal transition entry parses; sfx is optional."""
    t = Transition.from_dict({"from": "s1", "to": "s2", "style": "fade", "duration_sec": 0.5})
    assert t.from_scene == "s1"
    assert t.to_scene == "s2"
    assert t.style == "fade"
    assert t.duration_sec == 0.5
    assert t.sfx is None


def test_transition_from_dict_with_sfx():
    """sfx field is preserved when present."""
    t = Transition.from_dict({
        "from": "s9",
        "to": "s10",
        "style": "page-turn",
        "duration_sec": 0.5,
        "sfx": "assets/sfx/page_flip.mp3",
    })
    assert t.sfx == "assets/sfx/page_flip.mp3"


def test_transition_to_dict_uses_from_to_keys():
    """Round-trip: to_dict emits 'from' and 'to' (not from_scene/to_scene)."""
    t = Transition(from_scene="s1", to_scene="s2", style="fade", duration_sec=0.3, sfx=None)
    out = t.to_dict()
    assert out["from"] == "s1"
    assert out["to"] == "s2"
    assert "from_scene" not in out
    assert "to_scene" not in out


def test_transition_to_dict_omits_sfx_when_none():
    """sfx is omitted from output dict when None to keep storyboards lean."""
    t = Transition(from_scene="s1", to_scene="s2", style="fade", duration_sec=0.3, sfx=None)
    out = t.to_dict()
    assert "sfx" not in out
```

- [ ] **Step 1.2: Run the tests — expect 4 ImportError failures**

Run: `uv run pytest tests/unit/test_transitions.py -v`
Expected: 4 errors, all of the form `ImportError: cannot import name 'Transition' from 'pipeline.storyboard'`.

- [ ] **Step 1.3: Add the `Transition` dataclass to `storyboard.py`**

Open `src/pipeline/storyboard.py` and insert this after the existing imports and before the `class Scene:` declaration (after line 6):

```python
@dataclass
class Transition:
    """A transition between two adjacent scenes.

    JSON uses 'from' and 'to' keys (Python keyword conflict is the reason
    the dataclass fields are named from_scene/to_scene).
    """

    from_scene: str
    to_scene: str
    style: str  # none | fade | page-turn | slide | wipe
    duration_sec: float
    sfx: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transition:
        return cls(
            from_scene=data["from"],
            to_scene=data["to"],
            style=data["style"],
            duration_sec=float(data["duration_sec"]),
            sfx=data.get("sfx"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "from": self.from_scene,
            "to": self.to_scene,
            "style": self.style,
            "duration_sec": self.duration_sec,
        }
        if self.sfx is not None:
            out["sfx"] = self.sfx
        return out
```

- [ ] **Step 1.4: Run the tests — expect all 4 to pass**

Run: `uv run pytest tests/unit/test_transitions.py -v`
Expected: 4 passed.

- [ ] **Step 1.5: Commit**

```bash
git add src/pipeline/storyboard.py tests/unit/test_transitions.py
git commit -m "feat(storyboard): add Transition dataclass for seam config"
```

---

## Task 2: Add `transitions` field to `Storyboard`

**Files:**
- Modify: `src/pipeline/storyboard.py` (`Storyboard` dataclass + `to_dict` + `from_dict`)
- Test: `tests/unit/test_transitions.py` (extend)

- [ ] **Step 2.1: Add tests for the `transitions` field**

Append to `tests/unit/test_transitions.py`:

```python
import json
from pathlib import Path

from pipeline.storyboard import Storyboard


def _minimal_scene_dict(scene_id: str) -> dict:
    return {
        "id": scene_id,
        "section": "content",
        "narration": f"narration for {scene_id}",
        "narration_est_sec": 1.0,
    }


def test_storyboard_defaults_transitions_to_empty_list():
    sb = Storyboard()
    assert sb.transitions == []


def test_storyboard_from_dict_without_transitions_key():
    """Existing storyboards (no transitions key) still parse and produce []."""
    data = {
        "version": 1,
        "format": "standard",
        "target_duration_sec": 720,
        "aspect_ratio": "16:9",
        "scenes": [_minimal_scene_dict("s1"), _minimal_scene_dict("s2")],
    }
    sb = Storyboard.from_dict(data)
    assert sb.transitions == []


def test_storyboard_from_dict_with_transitions():
    data = {
        "version": 1,
        "scenes": [_minimal_scene_dict("s1"), _minimal_scene_dict("s2")],
        "transitions": [
            {"from": "s1", "to": "s2", "style": "page-turn", "duration_sec": 0.5},
        ],
    }
    sb = Storyboard.from_dict(data)
    assert len(sb.transitions) == 1
    assert sb.transitions[0].from_scene == "s1"
    assert sb.transitions[0].style == "page-turn"


def test_storyboard_to_dict_omits_transitions_key_when_empty():
    """Don't emit an empty transitions: [] for backwards-compatible storyboards."""
    sb = Storyboard(scenes=[])
    out = sb.to_dict()
    assert "transitions" not in out


def test_storyboard_to_dict_includes_transitions_when_set():
    from pipeline.storyboard import Transition
    sb = Storyboard(
        scenes=[],
        transitions=[Transition("s1", "s2", "fade", 0.3, None)],
    )
    out = sb.to_dict()
    assert out["transitions"] == [{"from": "s1", "to": "s2", "style": "fade", "duration_sec": 0.3}]


def test_storyboard_round_trip_with_transitions(tmp_path: Path):
    from pipeline.storyboard import Transition
    sb = Storyboard(
        scenes=[],
        transitions=[
            Transition("s1", "s2", "page-turn", 0.5, "assets/sfx/page_flip.mp3"),
            Transition("s5", "s6", "fade", 0.3, None),
        ],
    )
    p = tmp_path / "sb.json"
    sb.save(p)
    loaded = Storyboard.load(p)
    assert len(loaded.transitions) == 2
    assert loaded.transitions[0].sfx == "assets/sfx/page_flip.mp3"
    assert loaded.transitions[1].sfx is None
```

- [ ] **Step 2.2: Run the new tests — expect failures**

Run: `uv run pytest tests/unit/test_transitions.py -v -k storyboard`
Expected: 6 failures, all because `Storyboard` doesn't have a `transitions` field.

- [ ] **Step 2.3: Add the `transitions` field to `Storyboard`**

In `src/pipeline/storyboard.py`, modify the `Storyboard` dataclass (around line 80):

Find:
```python
    scenes: list[Scene] = field(default_factory=list)
    theme: Theme = field(default_factory=Theme)
    title: str | None = None
    description: str | None = None
```

Replace with:
```python
    scenes: list[Scene] = field(default_factory=list)
    theme: Theme = field(default_factory=Theme)
    title: str | None = None
    description: str | None = None
    transitions: list[Transition] = field(default_factory=list)
```

In `to_dict` (around line 94), find:
```python
        if self.title is not None:
            out["title"] = self.title
        if self.description is not None:
            out["description"] = self.description
        return out
```

Replace with:
```python
        if self.title is not None:
            out["title"] = self.title
        if self.description is not None:
            out["description"] = self.description
        if self.transitions:
            out["transitions"] = [t.to_dict() for t in self.transitions]
        return out
```

In `from_dict` (around line 110), find:
```python
        return cls(
            version=data.get("version", 1),
            format=data.get("format", "standard"),
            target_duration_sec=data.get("target_duration_sec", 720),
            aspect_ratio=data.get("aspect_ratio", "16:9"),
            scenes=scenes,
            theme=theme,
            title=data.get("title"),
            description=data.get("description"),
        )
```

Replace with:
```python
        transitions = [Transition.from_dict(t) for t in data.get("transitions", [])]
        return cls(
            version=data.get("version", 1),
            format=data.get("format", "standard"),
            target_duration_sec=data.get("target_duration_sec", 720),
            aspect_ratio=data.get("aspect_ratio", "16:9"),
            scenes=scenes,
            theme=theme,
            title=data.get("title"),
            description=data.get("description"),
            transitions=transitions,
        )
```

- [ ] **Step 2.4: Run all transitions tests — expect pass**

Run: `uv run pytest tests/unit/test_transitions.py -v`
Expected: 10 passed (4 from Task 1 + 6 from Task 2).

- [ ] **Step 2.5: Run the existing full test suite (excluding the pre-existing failure) to confirm no regressions**

Run: `uv run pytest --deselect tests/unit/test_compose_v2.py::test_compose_burn_subtitles_false_returns_plain_variant -q`
Expected: all pass (the deselect skips the pre-existing failure that exists on master and is unrelated to this work).

- [ ] **Step 2.6: Commit**

```bash
git add src/pipeline/storyboard.py tests/unit/test_transitions.py
git commit -m "feat(storyboard): add sparse transitions[] field to Storyboard"
```

---

## Task 3: Create `composer/transitions.py` — `TransitionConfig` + Protocol

**Files:**
- Create: `src/pipeline/composer/transitions.py`
- Test: `tests/unit/test_transitions.py` (extend)

- [ ] **Step 3.1: Add tests for `TransitionConfig` and the renderer-style validation**

Append to `tests/unit/test_transitions.py`:

```python
import pytest

from pipeline.composer.transitions import (
    SUPPORTED_STYLES,
    TransitionConfig,
)


def test_transition_config_constructs_with_valid_style():
    cfg = TransitionConfig(style="fade", duration_sec=0.5, sfx=None)
    assert cfg.style == "fade"


def test_transition_config_rejects_unknown_style():
    with pytest.raises(ValueError, match="Unknown transition style"):
        TransitionConfig(style="ribbon", duration_sec=0.5, sfx=None)


def test_supported_styles_set_matches_spec():
    assert SUPPORTED_STYLES == {"none", "fade", "page-turn", "slide", "wipe"}


def test_transition_config_from_storyboard_transition():
    from pipeline.storyboard import Transition
    t = Transition("s1", "s2", "page-turn", 0.5, "assets/sfx/page_flip.mp3")
    cfg = TransitionConfig.from_transition(t)
    assert cfg.style == "page-turn"
    assert cfg.duration_sec == 0.5
    assert cfg.sfx == "assets/sfx/page_flip.mp3"
```

- [ ] **Step 3.2: Run the new tests — expect ImportError**

Run: `uv run pytest tests/unit/test_transitions.py::test_transition_config_constructs_with_valid_style -v`
Expected: ImportError on `pipeline.composer.transitions`.

- [ ] **Step 3.3: Create `transitions.py` with config + protocol**

Create `src/pipeline/composer/transitions.py`:

```python
"""Per-seam transition primitives for the compose pipeline.

A transition is a short clip rendered between scene N and scene N+1.
Storyboards declare transitions sparsely in the `transitions[]` array;
missing entries mean a hard cut.

v1 implementation uses ffmpeg's built-in `xfade` filter for all visual
styles. The `page-turn` style is initially aliased to `xfade slideleft`
— a slide-style approximation. The Protocol abstraction allows swapping
to a PNG/webm `OverlayRenderer` later behind the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pipeline.storyboard import Transition

SUPPORTED_STYLES: set[str] = {"none", "fade", "page-turn", "slide", "wipe"}


@dataclass(frozen=True)
class TransitionConfig:
    """Render-ready config for one transition between two scenes."""

    style: str
    duration_sec: float
    sfx: str | None

    def __post_init__(self) -> None:
        if self.style not in SUPPORTED_STYLES:
            raise ValueError(
                f"Unknown transition style: {self.style!r}. "
                f"Supported: {sorted(SUPPORTED_STYLES)}"
            )

    @classmethod
    def from_transition(cls, t: Transition) -> TransitionConfig:
        return cls(style=t.style, duration_sec=t.duration_sec, sfx=t.sfx)


class TransitionRenderer(Protocol):
    """Protocol implemented by each per-style renderer.

    Implementations should be deterministic: same inputs → same output bytes.
    The cache layer above relies on this.
    """

    def render(
        self,
        scene_a: Path,
        scene_b: Path,
        cfg: TransitionConfig,
        out: Path,
        *,
        width: int,
        height: int,
        fps: int,
    ) -> Path | None:
        """Render the transition clip between scene_a and scene_b to `out`.

        Returns the output path on success, or None if no clip should be
        emitted (e.g. for HardCutRenderer — concat just stitches the two
        scenes directly).
        """
        ...
```

- [ ] **Step 3.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_transitions.py -v -k "config or supported_styles or from_storyboard"`
Expected: 4 passed.

- [ ] **Step 3.5: Commit**

```bash
git add src/pipeline/composer/transitions.py tests/unit/test_transitions.py
git commit -m "feat(composer): add TransitionConfig + TransitionRenderer Protocol"
```

---

## Task 4: Implement `HardCutRenderer`

**Files:**
- Modify: `src/pipeline/composer/transitions.py`
- Test: `tests/unit/test_transitions.py` (extend)

- [ ] **Step 4.1: Add HardCutRenderer tests**

Append to `tests/unit/test_transitions.py`:

```python
from pipeline.composer.transitions import HardCutRenderer


def test_hard_cut_renderer_returns_none(tmp_path: Path):
    """HardCutRenderer emits no clip — concat just stitches scenes directly."""
    renderer = HardCutRenderer()
    cfg = TransitionConfig(style="none", duration_sec=0.0, sfx=None)
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    out = tmp_path / "t.mp4"
    a.write_bytes(b"")  # input files don't need to be real for HardCut
    b.write_bytes(b"")
    result = renderer.render(a, b, cfg, out, width=1280, height=720, fps=30)
    assert result is None
    assert not out.exists()
```

- [ ] **Step 4.2: Run the test — expect ImportError**

Run: `uv run pytest tests/unit/test_transitions.py::test_hard_cut_renderer_returns_none -v`
Expected: ImportError.

- [ ] **Step 4.3: Add `HardCutRenderer` to `transitions.py`**

Append to `src/pipeline/composer/transitions.py`:

```python
class HardCutRenderer:
    """Emits no transition clip — the master concat stitches scenes directly."""

    def render(
        self,
        scene_a: Path,
        scene_b: Path,
        cfg: TransitionConfig,
        out: Path,
        *,
        width: int,
        height: int,
        fps: int,
    ) -> Path | None:
        return None
```

- [ ] **Step 4.4: Run the test — expect pass**

Run: `uv run pytest tests/unit/test_transitions.py::test_hard_cut_renderer_returns_none -v`
Expected: 1 passed.

- [ ] **Step 4.5: Commit**

```bash
git add src/pipeline/composer/transitions.py tests/unit/test_transitions.py
git commit -m "feat(composer): HardCutRenderer for no-op transitions"
```

---

## Task 5: Implement `XfadeRenderer`

**Files:**
- Modify: `src/pipeline/composer/transitions.py`
- Test: `tests/unit/test_transitions.py` (extend)

This renderer uses ffmpeg to:
1. Extract the last frame of `scene_a` and the first frame of `scene_b` as PNG.
2. Build static-frame video clips of `cfg.duration_sec` length from each PNG.
3. Run `xfade` between the two static clips for `cfg.duration_sec`.
4. Mix in the sfx audio (or silence).
5. Encode with the same H.264 + AAC parameters that the main scene renderer uses, so the master concat-demuxer pass can stream-copy without re-encoding.

- [ ] **Step 5.1: Add XfadeRenderer tests with a realistic ffmpeg fixture**

Append to `tests/unit/test_transitions.py`:

```python
import subprocess

from pipeline.composer.transitions import XfadeRenderer


def _make_test_clip(path: Path, *, duration: float, color: str, width: int = 320, height: int = 180, fps: int = 30) -> Path:
    """Helper: create a small solid-color test clip with silent audio."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s={width}x{height}:r={fps}:d={duration}",
            "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo",
            "-t", str(duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-b:a", "128k",
            "-shortest", str(path),
        ],
        check=True,
    )
    return path


def test_xfade_renderer_emits_clip_of_expected_duration(tmp_path: Path):
    a = _make_test_clip(tmp_path / "a.mp4", duration=1.0, color="red")
    b = _make_test_clip(tmp_path / "b.mp4", duration=1.0, color="blue")
    out = tmp_path / "t.mp4"
    cfg = TransitionConfig(style="fade", duration_sec=0.5, sfx=None)

    renderer = XfadeRenderer(xfade_name="fade")
    result = renderer.render(a, b, cfg, out, width=320, height=180, fps=30)

    assert result == out
    assert out.exists() and out.stat().st_size > 0
    # ffprobe duration should be ~0.5s (allow ±0.1s for encoding rounding)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        capture_output=True, text=True, check=True,
    )
    duration = float(probe.stdout.strip())
    assert 0.4 <= duration <= 0.6, f"Expected ~0.5s, got {duration}s"


def test_xfade_renderer_with_sfx_mixes_audio(tmp_path: Path):
    """sfx file is mixed into the transition's audio track."""
    a = _make_test_clip(tmp_path / "a.mp4", duration=1.0, color="red")
    b = _make_test_clip(tmp_path / "b.mp4", duration=1.0, color="blue")
    sfx = tmp_path / "sfx.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
         "-c:a", "pcm_s16le", str(sfx)],
        check=True,
    )
    out = tmp_path / "t.mp4"
    cfg = TransitionConfig(style="fade", duration_sec=0.5, sfx=str(sfx))

    renderer = XfadeRenderer(xfade_name="fade")
    result = renderer.render(a, b, cfg, out, width=320, height=180, fps=30)

    assert result == out
    # Verify the output has an audio stream (the silent base + sfx mix)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_name",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        capture_output=True, text=True, check=True,
    )
    assert probe.stdout.strip() == "aac"
```

- [ ] **Step 5.2: Run the tests — expect ImportError**

Run: `uv run pytest tests/unit/test_transitions.py::test_xfade_renderer_emits_clip_of_expected_duration -v`
Expected: ImportError on `XfadeRenderer`.

- [ ] **Step 5.3: Implement `XfadeRenderer`**

First, add two new imports to the top of `src/pipeline/composer/transitions.py` alongside the existing imports:

```python
import structlog

from pipeline.utils.ffmpeg import run_ffmpeg
```

And immediately after the imports block (before `SUPPORTED_STYLES`), add:

```python
logger = structlog.get_logger()
```

Then append to the same file (after the `HardCutRenderer` class):

```python
class XfadeRenderer:
    """Renders a transition using ffmpeg's xfade filter.

    Pipeline:
      1. Extract the last frame of scene_a and first frame of scene_b as PNG.
      2. Build a static-frame video clip of cfg.duration_sec from each PNG
         (with silent stereo audio at 48kHz to match the project standard).
      3. Apply xfade between the two clips for cfg.duration_sec.
      4. If cfg.sfx is set, amix the sfx into the audio track.
      5. Encode H.264 + AAC with the same params as scene clips so the
         master concat demuxer can stream-copy the result.
    """

    def __init__(self, xfade_name: str) -> None:
        # xfade built-in transition name (fade | slideleft | slideright | wiperight | wipeleft ...)
        self.xfade_name = xfade_name

    def render(
        self,
        scene_a: Path,
        scene_b: Path,
        cfg: TransitionConfig,
        out: Path,
        *,
        width: int,
        height: int,
        fps: int,
    ) -> Path | None:
        work = out.parent
        work.mkdir(parents=True, exist_ok=True)
        frame_a = work / f"{out.stem}_a.png"
        frame_b = work / f"{out.stem}_b.png"

        # 1. Extract last frame of scene_a (sseof = seek from end)
        run_ffmpeg([
            "ffmpeg", "-y", "-sseof", "-0.05", "-i", str(scene_a),
            "-frames:v", "1", "-update", "1", str(frame_a),
        ])
        # 2. Extract first frame of scene_b
        run_ffmpeg([
            "ffmpeg", "-y", "-i", str(scene_b),
            "-frames:v", "1", "-update", "1", str(frame_b),
        ])

        # 3. Build the xfade + audio pipeline in one ffmpeg invocation.
        #    Two looped images (with silent audio) → xfade → optional sfx mix → encode.
        d = cfg.duration_sec
        # filter_complex pieces
        video_filter = (
            f"[0:v]scale={width}:{height},setsar=1,fps={fps},format=yuv420p[va];"
            f"[1:v]scale={width}:{height},setsar=1,fps={fps},format=yuv420p[vb];"
            f"[va][vb]xfade=transition={self.xfade_name}:duration={d}:offset=0[v]"
        )
        # Inputs: two static images looped, one anullsrc for silent base audio,
        # plus the sfx file if provided.
        cmd: list[str] = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(d), "-i", str(frame_a),
            "-loop", "1", "-t", str(d), "-i", str(frame_b),
            "-f", "lavfi", "-t", str(d), "-i", "anullsrc=r=48000:cl=stereo",
        ]
        if cfg.sfx:
            cmd += ["-i", cfg.sfx]
            audio_filter = "[2:a][3:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
        else:
            audio_filter = "[2:a]anull[a]"
        cmd += [
            "-filter_complex", f"{video_filter};{audio_filter}",
            "-map", "[v]", "-map", "[a]",
            "-t", str(d),
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-ar", "48000", "-b:a", "128k",
            "-shortest", str(out),
        ]
        run_ffmpeg(cmd)
        # Cleanup intermediates
        frame_a.unlink(missing_ok=True)
        frame_b.unlink(missing_ok=True)
        return out
```

- [ ] **Step 5.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_transitions.py -v -k xfade`
Expected: 2 passed. (May take 5-10 seconds — actual ffmpeg invocations.)

- [ ] **Step 5.5: Commit**

```bash
git add src/pipeline/composer/transitions.py tests/unit/test_transitions.py
git commit -m "feat(composer): XfadeRenderer using ffmpeg xfade filter"
```

---

## Task 6: REGISTRY + cache key + top-level dispatcher

**Files:**
- Modify: `src/pipeline/composer/transitions.py`
- Test: `tests/unit/test_transitions.py` (extend)

- [ ] **Step 6.1: Add tests for REGISTRY and cache key**

Append to `tests/unit/test_transitions.py`:

```python
from pipeline.composer.transitions import REGISTRY, transition_cache_key, render_transition


def test_registry_covers_all_supported_styles():
    assert set(REGISTRY.keys()) == SUPPORTED_STYLES


def test_registry_page_turn_is_xfade_slideleft_in_v1():
    """v1 ships page-turn as XfadeRenderer(slideleft); document the alias."""
    page_turn = REGISTRY["page-turn"]
    assert isinstance(page_turn, XfadeRenderer)
    assert page_turn.xfade_name == "slideleft"


def test_registry_none_is_hard_cut():
    assert isinstance(REGISTRY["none"], HardCutRenderer)


def test_cache_key_deterministic(tmp_path: Path):
    a = _make_test_clip(tmp_path / "a.mp4", duration=0.5, color="red")
    b = _make_test_clip(tmp_path / "b.mp4", duration=0.5, color="blue")
    cfg = TransitionConfig(style="fade", duration_sec=0.5, sfx=None)
    k1 = transition_cache_key(a, b, cfg)
    k2 = transition_cache_key(a, b, cfg)
    assert k1 == k2
    assert len(k1) == 40  # sha1 hex digest


def test_cache_key_differs_with_style(tmp_path: Path):
    a = _make_test_clip(tmp_path / "a.mp4", duration=0.5, color="red")
    b = _make_test_clip(tmp_path / "b.mp4", duration=0.5, color="blue")
    cfg1 = TransitionConfig(style="fade", duration_sec=0.5, sfx=None)
    cfg2 = TransitionConfig(style="slide", duration_sec=0.5, sfx=None)
    assert transition_cache_key(a, b, cfg1) != transition_cache_key(a, b, cfg2)


def test_cache_key_differs_with_sfx(tmp_path: Path):
    a = _make_test_clip(tmp_path / "a.mp4", duration=0.5, color="red")
    b = _make_test_clip(tmp_path / "b.mp4", duration=0.5, color="blue")
    cfg1 = TransitionConfig(style="fade", duration_sec=0.5, sfx=None)
    cfg2 = TransitionConfig(style="fade", duration_sec=0.5, sfx="assets/sfx/whoosh.mp3")
    assert transition_cache_key(a, b, cfg1) != transition_cache_key(a, b, cfg2)


def test_render_transition_returns_none_for_hard_cut(tmp_path: Path):
    """The dispatcher returns None when style='none'."""
    a = _make_test_clip(tmp_path / "a.mp4", duration=0.5, color="red")
    b = _make_test_clip(tmp_path / "b.mp4", duration=0.5, color="blue")
    cfg = TransitionConfig(style="none", duration_sec=0.0, sfx=None)
    result = render_transition(a, b, cfg, tmp_path / "cache", width=320, height=180, fps=30)
    assert result is None


def test_render_transition_caches_result(tmp_path: Path):
    """Second call with same inputs returns the same cached path without re-rendering."""
    a = _make_test_clip(tmp_path / "a.mp4", duration=0.5, color="red")
    b = _make_test_clip(tmp_path / "b.mp4", duration=0.5, color="blue")
    cache_dir = tmp_path / "cache"
    cfg = TransitionConfig(style="fade", duration_sec=0.5, sfx=None)

    p1 = render_transition(a, b, cfg, cache_dir, width=320, height=180, fps=30)
    assert p1 is not None and p1.exists()
    mtime1 = p1.stat().st_mtime

    p2 = render_transition(a, b, cfg, cache_dir, width=320, height=180, fps=30)
    assert p2 == p1
    assert p2.stat().st_mtime == mtime1  # not re-rendered
```

- [ ] **Step 6.2: Run the tests — expect ImportError**

Run: `uv run pytest tests/unit/test_transitions.py -v -k "registry or cache_key or render_transition"`
Expected: ImportError.

- [ ] **Step 6.3: Add REGISTRY, cache key helper, and `render_transition` dispatcher**

First, add `import hashlib` to the top of `src/pipeline/composer/transitions.py` alongside the existing imports.

Then append to the same file:

```python
REGISTRY: dict[str, TransitionRenderer] = {
    "none":      HardCutRenderer(),
    "fade":      XfadeRenderer(xfade_name="fade"),
    "page-turn": XfadeRenderer(xfade_name="slideleft"),  # v1 alias; swap to OverlayRenderer later
    "slide":     XfadeRenderer(xfade_name="slideleft"),
    "wipe":      XfadeRenderer(xfade_name="wiperight"),
}


def _file_sha1_short(path: Path, *, n_bytes: int = 65536) -> str:
    """Hash the first n_bytes of a file. Sufficient for cache invalidation
    when the scene clip changes — full-file hash isn't needed."""
    h = hashlib.sha1()
    with path.open("rb") as f:
        h.update(f.read(n_bytes))
    return h.hexdigest()[:16]


def transition_cache_key(scene_a: Path, scene_b: Path, cfg: TransitionConfig) -> str:
    """Cache key from style + duration + sfx + content hashes of adjacent scenes."""
    h = hashlib.sha1()
    h.update(cfg.style.encode())
    h.update(f"{cfg.duration_sec:.4f}".encode())
    h.update((cfg.sfx or "").encode())
    h.update(_file_sha1_short(scene_a).encode())
    h.update(_file_sha1_short(scene_b).encode())
    return h.hexdigest()


def render_transition(
    scene_a: Path,
    scene_b: Path,
    cfg: TransitionConfig,
    cache_dir: Path,
    *,
    width: int,
    height: int,
    fps: int,
) -> Path | None:
    """Render a transition clip into the cache directory.

    Returns the path to the rendered clip, or None for hard-cut transitions
    (no clip is needed; the master concat stitches scenes directly).
    Cache hit: returns existing path without re-rendering.
    """
    if cfg.style == "none":
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = transition_cache_key(scene_a, scene_b, cfg)
    out = cache_dir / f"{key}.mp4"
    if out.exists():
        logger.info("transition.cache_hit", key=key, style=cfg.style)
        return out
    logger.info("transition.render", key=key, style=cfg.style, duration=cfg.duration_sec)
    renderer = REGISTRY[cfg.style]
    return renderer.render(scene_a, scene_b, cfg, out, width=width, height=height, fps=fps)
```

- [ ] **Step 6.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_transitions.py -v -k "registry or cache_key or render_transition"`
Expected: 7 passed.

- [ ] **Step 6.5: Run the full test_transitions.py file — confirm all tests pass**

Run: `uv run pytest tests/unit/test_transitions.py -v`
Expected: all (~22) passed.

- [ ] **Step 6.6: Commit**

```bash
git add src/pipeline/composer/transitions.py tests/unit/test_transitions.py
git commit -m "feat(composer): REGISTRY + cache + render_transition dispatcher"
```

---

## Task 7: CLI — `pipeline transition set` and `pipeline transition clear`

**Files:**
- Create: `src/pipeline/cli_transition.py`
- Modify: `src/pipeline/cli.py`
- Test: `tests/unit/test_cli_transition.py` (new)

- [ ] **Step 7.1: Write CLI tests**

Create `tests/unit/test_cli_transition.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_transition import transition_app
from pipeline.storyboard import Storyboard, Scene


def _write_minimal_storyboard(work_dir: Path) -> Path:
    """Create a project tree with a 2-scene storyboard for the CLI to mutate."""
    work_dir.mkdir(parents=True, exist_ok=True)
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
        Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
    ])
    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)
    # Minimal context.json (required by some commands; not strictly needed by transition)
    (work_dir / "context.json").write_text(
        json.dumps({"project_id": 42, "source_url": "x", "locale": "zh-TW",
                    "work_dir": str(work_dir)}),
        encoding="utf-8",
    )
    return sb_path


@pytest.fixture
def project_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set up a fake projects directory and return the project's work dir."""
    out_root = tmp_path / "output"
    proj = out_root / "projects" / "42"
    _write_minimal_storyboard(proj)
    monkeypatch.setattr(
        "pipeline.cli_transition.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    return proj


def test_set_writes_transition_to_storyboard(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(transition_app, [
        "set",
        "--project-id", "42",
        "--from", "s1",
        "--to", "s2",
        "--style", "page-turn",
        "--duration", "0.5",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert len(sb.transitions) == 1
    assert sb.transitions[0].from_scene == "s1"
    assert sb.transitions[0].to_scene == "s2"
    assert sb.transitions[0].style == "page-turn"
    assert sb.transitions[0].duration_sec == 0.5
    assert sb.transitions[0].sfx is None


def test_set_with_sfx_writes_sfx(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(transition_app, [
        "set", "--project-id", "42", "--from", "s1", "--to", "s2",
        "--style", "fade", "--duration", "0.3",
        "--sfx", "assets/sfx/page_flip.mp3",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.transitions[0].sfx == "assets/sfx/page_flip.mp3"


def test_set_updates_existing_transition_for_same_seam(project_tree: Path):
    runner = CliRunner()
    runner.invoke(transition_app, [
        "set", "--project-id", "42", "--from", "s1", "--to", "s2",
        "--style", "fade", "--duration", "0.3",
    ])
    runner.invoke(transition_app, [
        "set", "--project-id", "42", "--from", "s1", "--to", "s2",
        "--style", "page-turn", "--duration", "0.6",
    ])
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert len(sb.transitions) == 1, "second set should replace, not append"
    assert sb.transitions[0].style == "page-turn"
    assert sb.transitions[0].duration_sec == 0.6


def test_set_rejects_unknown_style(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(transition_app, [
        "set", "--project-id", "42", "--from", "s1", "--to", "s2",
        "--style", "ribbon", "--duration", "0.5",
    ])
    assert result.exit_code != 0
    assert "Unknown transition style" in result.output or "ribbon" in result.output


def test_set_rejects_unknown_scene(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(transition_app, [
        "set", "--project-id", "42", "--from", "s1", "--to", "s99",
        "--style", "fade", "--duration", "0.5",
    ])
    assert result.exit_code != 0
    assert "s99" in result.output


def test_clear_removes_transition(project_tree: Path):
    runner = CliRunner()
    runner.invoke(transition_app, [
        "set", "--project-id", "42", "--from", "s1", "--to", "s2",
        "--style", "fade", "--duration", "0.3",
    ])
    result = runner.invoke(transition_app, [
        "clear", "--project-id", "42", "--from", "s1", "--to", "s2",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.transitions == []


def test_clear_is_noop_when_no_transition_exists(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(transition_app, [
        "clear", "--project-id", "42", "--from", "s1", "--to", "s2",
    ])
    assert result.exit_code == 0
    assert "no transition" in result.output.lower() or "nothing to clear" in result.output.lower()
```

- [ ] **Step 7.2: Run the tests — expect ImportError**

Run: `uv run pytest tests/unit/test_cli_transition.py -v`
Expected: ImportError on `pipeline.cli_transition`.

- [ ] **Step 7.3: Create `cli_transition.py`**

Create `src/pipeline/cli_transition.py`:

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from pipeline.composer.transitions import SUPPORTED_STYLES
from pipeline.config import PipelineConfig
from pipeline.session_log import SessionEntry, append_session, new_session_id
from pipeline.storyboard import Storyboard, Transition

transition_app = typer.Typer(name="transition", help="Per-seam transition commands")


def _resolve_work_dir(project_id: int) -> Path:
    return PipelineConfig().OUTPUT_DIR / "projects" / str(project_id)


def _load_storyboard(project_id: int) -> tuple[Path, Storyboard]:
    work = _resolve_work_dir(project_id)
    sb_path = work / "storyboard.json"
    if not sb_path.exists():
        typer.echo(f"storyboard.json not found at {sb_path}", err=True)
        raise typer.Exit(code=1)
    return sb_path, Storyboard.load(sb_path)


def _scene_ids(sb: Storyboard) -> set[str]:
    return {s.id for s in sb.scenes}


@transition_app.command("set")
def set_transition(
    project_id: int = typer.Option(..., "--project-id"),
    from_scene: str = typer.Option(..., "--from", help="Source scene id (e.g. s9)"),
    to_scene: str = typer.Option(..., "--to", help="Destination scene id (e.g. s10)"),
    style: str = typer.Option(..., "--style", help=f"One of: {', '.join(sorted(SUPPORTED_STYLES))}"),
    duration: float = typer.Option(..., "--duration", help="Transition duration in seconds"),
    sfx: str | None = typer.Option(None, "--sfx", help="Optional sound effect path"),
) -> None:
    """Set or replace a transition between two scenes. Idempotent."""
    if style not in SUPPORTED_STYLES:
        typer.echo(
            f"Unknown transition style {style!r}. Choose from: {', '.join(sorted(SUPPORTED_STYLES))}",
            err=True,
        )
        raise typer.Exit(code=1)
    sb_path, sb = _load_storyboard(project_id)
    ids = _scene_ids(sb)
    if from_scene not in ids:
        typer.echo(f"Scene {from_scene!r} not found in storyboard", err=True)
        raise typer.Exit(code=1)
    if to_scene not in ids:
        typer.echo(f"Scene {to_scene!r} not found in storyboard", err=True)
        raise typer.Exit(code=1)

    # Remove existing entry for this seam, then append the new one.
    sb.transitions = [
        t for t in sb.transitions
        if not (t.from_scene == from_scene and t.to_scene == to_scene)
    ]
    sb.transitions.append(Transition(
        from_scene=from_scene, to_scene=to_scene,
        style=style, duration_sec=duration, sfx=sfx,
    ))
    sb.save(sb_path)

    summary = f"transition {from_scene}→{to_scene}: {style} ({duration}s)" + (f" + {sfx}" if sfx else "")
    typer.echo(summary)
    work = _resolve_work_dir(project_id)
    append_session(work, SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"transition set --from {from_scene} --to {to_scene} --style {style} --duration {duration}"
                + (f" --sfx {sfx}" if sfx else ""),
        summary=summary,
    ))


@transition_app.command("clear")
def clear_transition(
    project_id: int = typer.Option(..., "--project-id"),
    from_scene: str = typer.Option(..., "--from"),
    to_scene: str = typer.Option(..., "--to"),
) -> None:
    """Remove the transition for a given seam, if any."""
    sb_path, sb = _load_storyboard(project_id)
    before = len(sb.transitions)
    sb.transitions = [
        t for t in sb.transitions
        if not (t.from_scene == from_scene and t.to_scene == to_scene)
    ]
    if len(sb.transitions) == before:
        typer.echo(f"No transition for {from_scene}→{to_scene}; nothing to clear.")
        return
    sb.save(sb_path)
    summary = f"transition {from_scene}→{to_scene}: cleared"
    typer.echo(summary)
    work = _resolve_work_dir(project_id)
    append_session(work, SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"transition clear --from {from_scene} --to {to_scene}",
        summary=summary,
    ))
```

- [ ] **Step 7.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_cli_transition.py -v`
Expected: 7 passed.

- [ ] **Step 7.5: Register `transition_app` in `cli.py`**

Open `src/pipeline/cli.py`. Find the existing import:

```python
from pipeline.cli_compose import compose_app
```

Add below it:
```python
from pipeline.cli_transition import transition_app
```

Find the existing block of `app.add_typer` calls (around line 33). Add:
```python
app.add_typer(transition_app, name="transition")
```

- [ ] **Step 7.6: Verify the CLI registers — manually invoke `--help`**

Run: `uv run pipeline transition --help`
Expected: typer help output listing `set` and `clear` subcommands. Exit code 0.

- [ ] **Step 7.7: Commit**

```bash
git add src/pipeline/cli_transition.py src/pipeline/cli.py tests/unit/test_cli_transition.py
git commit -m "feat(cli): pipeline transition set/clear commands"
```

---

## Task 8: Compose stage integration — insert transitions into concat

**Files:**
- Modify: `src/pipeline/stages/compose.py` (around line 439, before `_concat_scenes` is called)
- Test: `tests/integration/test_compose_with_transitions.py` (new)

This is the most architecturally significant task. The existing compose flow renders each scene to its own MP4, builds two parallel lists (`scene_finals` for overlay variant, `scene_finals_no_overlay` for the no-overlay variant), then concatenates each list with `_concat_scenes`.

The change: between scene rendering and concat, walk `storyboard.transitions`; for each entry, render the transition clip into a per-project cache directory, then insert the rendered clip's path between the corresponding scene paths in BOTH lists. `HardCutRenderer` (style `none`) returns `None`, so no clip is inserted — the concat just stitches the two scenes directly.

- [ ] **Step 8.1: Write integration test**

Create `tests/integration/test_compose_with_transitions.py`:

```python
"""Integration: storyboard with a transition produces a master concat that
includes a transition clip between the two scenes.

These tests run real ffmpeg invocations and may take 10-30s each.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipeline.composer.transitions import REGISTRY


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _make_solid_clip(path: Path, *, duration: float, color: str,
                      width: int = 320, height: int = 180, fps: int = 30) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c={color}:s={width}x{height}:r={fps}:d={duration}",
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-t", str(duration),
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-ar", "48000", "-b:a", "128k",
         "-shortest", str(path)],
        check=True,
    )
    return path


def test_concat_with_transition_clip_increases_total_duration(tmp_path: Path):
    """When we splice a transition clip into the concat list, the output is
    longer by the transition's duration."""
    from pipeline.composer.transitions import TransitionConfig, render_transition

    a = _make_solid_clip(tmp_path / "scene1.mp4", duration=1.0, color="red")
    b = _make_solid_clip(tmp_path / "scene2.mp4", duration=1.0, color="blue")
    cfg = TransitionConfig(style="fade", duration_sec=0.5, sfx=None)
    cache = tmp_path / "cache"
    transition_clip = render_transition(a, b, cfg, cache, width=320, height=180, fps=30)
    assert transition_clip is not None and transition_clip.exists()

    # Build a concat list and run the demuxer.
    filelist = tmp_path / "list.txt"
    filelist.write_text("\n".join(f"file '{p.resolve()}'" for p in [a, transition_clip, b]),
                         encoding="utf-8")
    out = tmp_path / "out.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", str(filelist),
         "-c:v", "copy", "-c:a", "aac", "-ar", "48000", "-b:a", "128k", str(out)],
        check=True,
    )
    duration = _ffprobe_duration(out)
    # Two 1.0s scenes + one 0.5s transition = ~2.5s
    assert 2.4 <= duration <= 2.6, f"Expected ~2.5s, got {duration}s"


def test_compose_stage_inserts_transition_between_scenes(tmp_path: Path, monkeypatch):
    """End-to-end: ComposeStage sees storyboard.transitions and emits a longer master concat."""
    pytest.importorskip("pipeline.stages.compose")
    from pipeline.stages.compose import ComposeStage
    from pipeline.stages.base import PipelineContext
    from pipeline.storyboard import Storyboard, Scene, Transition

    work = tmp_path / "work"
    work.mkdir()
    compose_dir = work / "compose"
    compose_dir.mkdir()

    # Pre-render two scene clips to bypass the per-scene renderer (which
    # depends on a wider scene-rendering pipeline). We monkeypatch the
    # ComposeStage's per-scene render to return these pre-baked clips.
    s1_clip = _make_solid_clip(compose_dir / "s1_final.mp4", duration=1.0, color="red")
    s2_clip = _make_solid_clip(compose_dir / "s2_final.mp4", duration=1.0, color="blue")

    sb = Storyboard(
        scenes=[
            Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
            Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
        ],
        transitions=[Transition("s1", "s2", "fade", 0.5, None)],
    )

    # The implementation must expose a helper this test can call. Once
    # Step 8.3 lands, expose `splice_transitions(scene_paths, sb, cache_dir, width, height, fps)`
    # in compose.py (or in transitions.py) that returns the new list with
    # transition clips spliced in. Test that helper directly to keep the
    # integration test fast.
    from pipeline.stages.compose import splice_transitions

    spliced = splice_transitions(
        scene_paths=[s1_clip, s2_clip],
        scene_ids=["s1", "s2"],
        sb=sb,
        cache_dir=compose_dir / "transitions",
        width=320, height=180, fps=30,
    )
    assert len(spliced) == 3
    assert spliced[0] == s1_clip
    assert spliced[2] == s2_clip
    assert spliced[1].name.endswith(".mp4")
    assert spliced[1].parent == compose_dir / "transitions"


def test_splice_transitions_skips_hard_cut(tmp_path: Path):
    from pipeline.stages.compose import splice_transitions
    from pipeline.storyboard import Storyboard, Scene, Transition
    s1 = _make_solid_clip(tmp_path / "s1.mp4", duration=1.0, color="red")
    s2 = _make_solid_clip(tmp_path / "s2.mp4", duration=1.0, color="blue")
    sb = Storyboard(
        scenes=[
            Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
            Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
        ],
        transitions=[Transition("s1", "s2", "none", 0.0, None)],
    )
    spliced = splice_transitions(
        scene_paths=[s1, s2],
        scene_ids=["s1", "s2"],
        sb=sb,
        cache_dir=tmp_path / "cache",
        width=320, height=180, fps=30,
    )
    assert len(spliced) == 2  # no clip inserted for "none"


def test_splice_transitions_passthrough_when_no_transitions(tmp_path: Path):
    from pipeline.stages.compose import splice_transitions
    from pipeline.storyboard import Storyboard, Scene
    s1 = _make_solid_clip(tmp_path / "s1.mp4", duration=1.0, color="red")
    s2 = _make_solid_clip(tmp_path / "s2.mp4", duration=1.0, color="blue")
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
        Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
    ])
    spliced = splice_transitions(
        scene_paths=[s1, s2],
        scene_ids=["s1", "s2"],
        sb=sb,
        cache_dir=tmp_path / "cache",
        width=320, height=180, fps=30,
    )
    assert spliced == [s1, s2]
```

- [ ] **Step 8.2: Run the tests — expect failures**

Run: `uv run pytest tests/integration/test_compose_with_transitions.py -v`
Expected: first test passes (it doesn't depend on `splice_transitions`); the other three fail with `ImportError: cannot import name 'splice_transitions' from 'pipeline.stages.compose'`.

- [ ] **Step 8.3: Add `splice_transitions` helper to `compose.py`**

Open `src/pipeline/stages/compose.py`. Near the top of the file (after the existing imports), add:

```python
from pipeline.composer.transitions import (
    TransitionConfig,
    render_transition,
)
```

Then add this module-level helper function before the `ComposeStage` class definition:

```python
def splice_transitions(
    *,
    scene_paths: list[Path],
    scene_ids: list[str],
    sb: "Storyboard",
    cache_dir: Path,
    width: int,
    height: int,
    fps: int,
) -> list[Path]:
    """Return a new scene-paths list with transition clips spliced between
    adjacent scenes that have a configured transition.

    `scene_paths` and `scene_ids` are parallel lists in render order.
    Looks up transitions in `sb.transitions` keyed by (from_scene, to_scene).
    HardCut transitions (style='none') and missing transitions both result
    in no inserted clip — adjacent scenes get stitched directly by concat.
    """
    if not sb.transitions:
        return list(scene_paths)
    by_seam: dict[tuple[str, str], "Transition"] = {
        (t.from_scene, t.to_scene): t for t in sb.transitions
    }
    out: list[Path] = []
    for i, (path, scene_id) in enumerate(zip(scene_paths, scene_ids)):
        out.append(path)
        # Look at the seam to the next scene
        if i + 1 < len(scene_ids):
            next_id = scene_ids[i + 1]
            t = by_seam.get((scene_id, next_id))
            if t is None:
                continue
            cfg = TransitionConfig.from_transition(t)
            clip = render_transition(
                scene_paths[i], scene_paths[i + 1], cfg, cache_dir,
                width=width, height=height, fps=fps,
            )
            if clip is not None:
                out.append(clip)
    return out
```

The forward references `"Storyboard"` and `"Transition"` in the type hints (note the quotes) avoid needing to reorder imports. `compose.py` already imports `Storyboard` from `pipeline.storyboard`, and `Transition` is referenced only inside the function body via `sb.transitions` so it does not need to be imported.

- [ ] **Step 8.4: Wire `splice_transitions` into the existing concat path**

In `src/pipeline/stages/compose.py`, find the block around line 439:

```python
        # Step 5: Concatenate scene lists — skip whichever raw the locked variant won't use.
        raw_path = compose_dir / "raw.mp4"
        raw_no_overlay_path = compose_dir / "raw_no_overlay.mp4"
        # Default to subtitles_no_overlay so first run builds one variant, not all four.
        # Operator overrides with `compose set-variant` or passes --variant explicitly.
        _pref = ctx.preferred_variant or "subtitles_no_overlay"
        need_plain = "no_overlay" not in _pref
        need_no_overlay = "no_overlay" in _pref
        if need_plain:
            self._concat_scenes(scene_finals, raw_path)
        if need_no_overlay:
            self._concat_scenes(scene_finals_no_overlay, raw_no_overlay_path)
```

Replace with:

```python
        # Step 5: Splice transition clips between scenes (where storyboard
        # declares them), then concat. Skip whichever raw the locked variant
        # won't use.
        raw_path = compose_dir / "raw.mp4"
        raw_no_overlay_path = compose_dir / "raw_no_overlay.mp4"
        scene_id_seq = [s.id for s in storyboard.scenes]
        transitions_cache = compose_dir / "transitions"
        finals_with_transitions = splice_transitions(
            scene_paths=scene_finals,
            scene_ids=scene_id_seq,
            sb=storyboard,
            cache_dir=transitions_cache,
            width=width,
            height=height,
            fps=30,
        )
        finals_no_overlay_with_transitions = splice_transitions(
            scene_paths=scene_finals_no_overlay,
            scene_ids=scene_id_seq,
            sb=storyboard,
            cache_dir=transitions_cache,
            width=width,
            height=height,
            fps=30,
        )
        # Default to subtitles_no_overlay so first run builds one variant, not all four.
        # Operator overrides with `compose set-variant` or passes --variant explicitly.
        _pref = ctx.preferred_variant or "subtitles_no_overlay"
        need_plain = "no_overlay" not in _pref
        need_no_overlay = "no_overlay" in _pref
        if need_plain:
            self._concat_scenes(finals_with_transitions, raw_path)
        if need_no_overlay:
            self._concat_scenes(finals_no_overlay_with_transitions, raw_no_overlay_path)
```

Note: this assumes `storyboard`, `width`, and `height` are local variables in this method. Verify by reading the surrounding context. If the variable is named differently (e.g. `sb`), use that name. If `width`/`height` are not in scope here, derive them from `get_resolution(storyboard.aspect_ratio)`.

- [ ] **Step 8.5: Run the integration tests — expect pass**

Run: `uv run pytest tests/integration/test_compose_with_transitions.py -v`
Expected: 4 passed (may take 30-60s due to ffmpeg work).

- [ ] **Step 8.6: Run the full test suite (excluding the known pre-existing failure)**

Run: `uv run pytest --deselect tests/unit/test_compose_v2.py::test_compose_burn_subtitles_false_returns_plain_variant -q`
Expected: all pass.

- [ ] **Step 8.7: Commit**

```bash
git add src/pipeline/stages/compose.py tests/integration/test_compose_with_transitions.py
git commit -m "feat(compose): splice transition clips into master concat"
```

---

## Task 9: Per-scene reburn invalidates adjacent transition cache

**Files:**
- Modify: `src/pipeline/cli_compose.py` (`rescene` command, around line 60-127)
- Test: `tests/unit/test_cli_compose_transition_invalidation.py` (new)

When `rescene` deletes a scene's per-scene cache (e.g. `s9_final.mp4`), any transition clip whose cache key includes `s9` becomes stale because it was hashed from `s9`'s old contents. We invalidate by deleting transition cache entries whose seam touches the rescened scene id(s).

Cache lives at `<work>/compose/transitions/<sha1>.mp4` — but the file name doesn't encode the scene ids directly. We track which transitions touch which scene by walking `storyboard.transitions` and hashing the current cache key for each entry. Any cache file that's a hash of an entry touching the rescened scene gets removed.

Simpler: just delete the entire `<work>/compose/transitions/` cache directory on rescene. It's cheap to re-render (each transition is a 0.5s clip), and avoids subtle staleness bugs. If transitions become expensive later (PNG overlay path), revisit.

- [ ] **Step 9.1: Add a unit test that simulates rescene's cache cleanup**

Create `tests/unit/test_cli_compose_transition_invalidation.py`:

```python
from __future__ import annotations

from pathlib import Path

from pipeline.cli_compose import _delete_transition_cache_for_scenes


def test_delete_transition_cache_removes_directory(tmp_path: Path):
    """The helper wipes the entire transitions cache directory."""
    compose = tmp_path / "compose"
    transitions = compose / "transitions"
    transitions.mkdir(parents=True)
    (transitions / "abc123.mp4").write_bytes(b"x")
    (transitions / "def456.mp4").write_bytes(b"y")

    _delete_transition_cache_for_scenes(compose, ["s9"])

    assert not transitions.exists()


def test_delete_transition_cache_noop_when_directory_absent(tmp_path: Path):
    """Helper is safe to call when no transition cache exists yet."""
    compose = tmp_path / "compose"
    compose.mkdir()
    # Should not raise.
    _delete_transition_cache_for_scenes(compose, ["s9"])
```

- [ ] **Step 9.2: Run the test — expect ImportError**

Run: `uv run pytest tests/unit/test_cli_compose_transition_invalidation.py -v`
Expected: ImportError on `_delete_transition_cache_for_scenes`.

- [ ] **Step 9.3: Add the helper to `cli_compose.py` and call it from `rescene`**

Open `src/pipeline/cli_compose.py`. Add this helper function near the other module-level helpers (after `_resolve_projects_dir`, around line 36):

```python
def _delete_transition_cache_for_scenes(compose_dir: Path, scene_ids: list[str]) -> None:
    """Remove the entire transition cache directory.

    Called from `rescene` to invalidate any transition clips that were
    cached against the rescened scene's prior content. The transitions
    are cheap to re-render (sub-second xfade clips), so we wipe the whole
    cache rather than tracking per-transition dependencies. The
    `scene_ids` argument is for future targeted invalidation; the v1
    behavior wipes everything.
    """
    cache = compose_dir / "transitions"
    if cache.exists():
        import shutil
        shutil.rmtree(cache)
        logger.info("rescene.transition_cache_cleared", path=str(cache))
```

Then, in the `rescene` command (around line 60-127), find the block that deletes per-scene caches. After that block, add a call to the new helper:

```python
        # Invalidate transition cache for adjacent seams (cheap to re-render).
        _delete_transition_cache_for_scenes(compose_dir, scenes)
```

The exact insertion point is just before the `append_session(...)` call at the end of the `rescene` body. Use the existing `compose_dir` variable (it's resolved earlier in the same function as `work_dir / "compose"`); if not present, derive it: `compose_dir = _resolve_work_dir(project_id) / "compose"`.

- [ ] **Step 9.4: Run the unit test — expect pass**

Run: `uv run pytest tests/unit/test_cli_compose_transition_invalidation.py -v`
Expected: 2 passed.

- [ ] **Step 9.5: Run the integration test suite again to confirm rescene + transitions still cooperate**

Run: `uv run pytest tests/integration/test_compose_with_transitions.py tests/unit/test_cli_compose_transition_invalidation.py -v`
Expected: all pass.

- [ ] **Step 9.6: Commit**

```bash
git add src/pipeline/cli_compose.py tests/unit/test_cli_compose_transition_invalidation.py
git commit -m "feat(compose): rescene invalidates transition cache"
```

---

## Task 10: Reserve `assets/sfx/` directory + final verification

**Files:**
- Create: `assets/sfx/.gitkeep`

- [ ] **Step 10.1: Reserve the `assets/sfx/` directory**

```bash
mkdir -p assets/sfx
touch assets/sfx/.gitkeep
```

- [ ] **Step 10.2: Final lint + type check**

Run: `uv run ruff check src/pipeline/composer/transitions.py src/pipeline/cli_transition.py src/pipeline/storyboard.py src/pipeline/stages/compose.py src/pipeline/cli_compose.py`
Expected: no errors.

Run: `uv run mypy src/pipeline/composer/transitions.py src/pipeline/cli_transition.py`
Expected: no errors. (If mypy reports issues in dependencies that are pre-existing on master, those can be ignored.)

- [ ] **Step 10.3: Run the full test suite once more**

Run: `uv run pytest --deselect tests/unit/test_compose_v2.py::test_compose_burn_subtitles_false_returns_plain_variant -q`
Expected: all pass.

- [ ] **Step 10.4: Manual smoke test — set a transition on a real project**

Pick any existing project under `output/projects/`. Then:

```bash
PROJ=$(ls output/projects/ | head -1)
uv run pipeline transition set --project-id "$PROJ" --from s1 --to s2 --style page-turn --duration 0.5
uv run pipeline storyboard show --scene s1
```

Verify the storyboard's `transitions` array now has an entry for `s1→s2`. Then clear it:

```bash
uv run pipeline transition clear --project-id "$PROJ" --from s1 --to s2
```

If the project's first scene isn't `s1`, substitute the actual ids from `pipeline storyboard show`.

- [ ] **Step 10.5: Commit assets directory**

```bash
git add assets/sfx/.gitkeep
git commit -m "chore: reserve assets/sfx/ for transition sound effects"
```

---

## Plan complete

After all tasks above are checked off:

- New CLI: `pipeline transition set / clear` works end-to-end against a real project storyboard.
- `Storyboard.transitions` field is sparse, backwards-compatible, round-trip safe.
- `compose` stage detects transitions and inserts rendered clips into the master concat.
- Transition clips are cached (sha1 keyed) under `<project>/compose/transitions/`.
- `rescene` invalidates the transition cache so it rebuilds on next compose.
- All five styles (`none`, `fade`, `page-turn`, `slide`, `wipe`) are wired; `page-turn` v1 = `xfade slideleft` (one-line registry swap to upgrade to PNG/webm overlay later).
- Existing storyboards (no `transitions` field) continue to compose unchanged.

**Hand-off note for follow-on plans:** Plans 2-5 layer the dashboard UI, agent runtime, and trust gate on top of this CLI. The direct-action HTTP endpoints in Plan 4 will call `pipeline transition set` / `clear` internally — no second source of truth.
