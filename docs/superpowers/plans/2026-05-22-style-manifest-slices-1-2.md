# Style Manifest Slices 1–2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a first-class style inventory (`pipeline style list`) and mutation commands (`style add`/`remove` with append-only `style_log.json`), and remove the dead `anchor_image` parameter — making every active style element visible, traceable, and controllable before E3 adds animated overlays as new globals.

**Architecture:** New `src/pipeline/style/` package (greenfield) with three focused modules: `manifest.py` (read-only data structures + builder), `log.py` (append-only mutation log), `cli.py` (Typer subcommand). The CLI is wired into the main Typer app via `app.add_typer`. The `anchor_image` no-op removal is a 5-line cleanup in `composer/image.py` and `composer/base.py`.

**Tech Stack:** Python 3.11+, Typer (existing CLI framework), dataclasses, `json`, `pathlib`. No new dependencies. Tests: `pytest` + `typer.testing.CliRunner`.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/pipeline/style/__init__.py` | Package marker (empty) |
| Create | `src/pipeline/style/manifest.py` | `StyleElement`, `PerSceneOverride`, `StyleManifest` dataclasses; `build_manifest(storyboard_path) → StyleManifest` |
| Create | `src/pipeline/style/log.py` | `StyleLogEntry` dataclass; `append_log(project_dir, action, element_id, rationale)` |
| Create | `src/pipeline/style/cli.py` | Typer `style_app` with `list`, `remove`, `add` commands; resolves project dir via `config.OUTPUT_DIR` |
| Modify | `src/pipeline/cli.py` | Add `from pipeline.style.cli import style_app` + `app.add_typer(style_app, name="style")` |
| Modify | `src/pipeline/composer/image.py:99` | Remove `anchor_image: Path \| None = None` parameter (dead code — never read in body) |
| Modify | `src/pipeline/composer/base.py:344–361` | Remove the 3 lines that read `theme["_anchor_image"]` and pass it to `render_generated_image` |
| Create | `tests/unit/test_style_manifest.py` | All tests (manifest build, log, CLI list/add/remove, dead-code absence) |

---

## Task 1: Create the style package and data structures

**Files:**
- Create: `src/pipeline/style/__init__.py`
- Create: `src/pipeline/style/manifest.py`
- Create: `tests/unit/test_style_manifest.py` (skeleton)

- [ ] **Step 1: Write failing tests for StyleElement and StyleManifest**

Create `tests/unit/test_style_manifest.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.style.manifest import (
    PerSceneOverride,
    StyleElement,
    StyleManifest,
    build_manifest,
)


# ── Data-structure smoke tests ────────────────────────────────────────────────

def test_style_element_defaults():
    el = StyleElement(
        id="frame_open_book_page",
        kind="frame",
        value="open_book_page",
        source="project_theme",
        scope="all_scenes",
        theme_key="frame_style",
    )
    assert el.active is True
    assert el.warnings == []


def test_style_element_inactive():
    el = StyleElement(
        id="anchor_image",
        kind="anchor_image",
        value="/some/path.png",
        source="project_theme",
        scope="generated_image_scenes",
        theme_key="_anchor_image",
        active=False,
        warnings=["not used in image generation"],
    )
    assert el.active is False
    assert "not used" in el.warnings[0]


def test_style_manifest_empty():
    m = StyleManifest(project_id="proj", elements=[], per_scene_overrides=[])
    assert m.project_id == "proj"
    assert m.elements == []
    assert m.per_scene_overrides == []
```

- [ ] **Step 2: Run tests to confirm import fails**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_style_manifest.py::test_style_element_defaults -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'pipeline.style'`

- [ ] **Step 3: Create the package**

Create `src/pipeline/style/__init__.py` (empty):

```python
```

Create `src/pipeline/style/manifest.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

StyleKind = Literal[
    "frame",
    "image_prompt_prefix",
    "transition",
    "theme_color",
    "seed",
    "anchor_image",
]

_MEDIUM_KEYWORDS = (
    "sketch",
    "lines",
    "hand-drawn",
    "illustration",
    "watercolor",
    "painted",
    "drawing",
)


@dataclass
class StyleElement:
    id: str
    kind: StyleKind
    value: str
    source: str         # "project_theme" | "niche:<name>" | "scene_override"
    scope: str          # "all_scenes" | "generated_image_scenes" | "all_transitions"
    theme_key: str      # which storyboard theme key to delete on `style remove`
    active: bool = True
    warnings: list[str] = field(default_factory=list)


@dataclass
class PerSceneOverride:
    scene_id: str
    kind: str   # "skip_niche_style" | "style_modifier"
    value: str


@dataclass
class StyleManifest:
    project_id: str
    elements: list[StyleElement]
    per_scene_overrides: list[PerSceneOverride]


def build_manifest(storyboard_path: Path) -> StyleManifest:
    """Read storyboard.json and produce a StyleManifest of all active style elements."""
    data = json.loads(storyboard_path.read_text())
    project_id = data.get("project_id", storyboard_path.parent.name)
    theme = data.get("theme", {})
    scenes = data.get("scenes", [])

    elements: list[StyleElement] = []
    overrides: list[PerSceneOverride] = []

    # 1. frame_style
    if frame_val := theme.get("frame_style"):
        elements.append(
            StyleElement(
                id=f"frame_{frame_val}",
                kind="frame",
                value=frame_val,
                source="project_theme",
                scope="all_scenes",
                theme_key="frame_style",
                warnings=[
                    "No per-scene opt-out available (all-or-nothing per project). "
                    "Use `style remove` to drop the frame globally."
                ],
            )
        )

    # 2. visual_style (niche image-prompt prefix)
    if vs := theme.get("visual_style"):
        warnings: list[str] = []
        clashing = [kw for kw in _MEDIUM_KEYWORDS if kw in vs.lower()]
        if clashing:
            warnings.append(
                f"Contains medium descriptor(s) {clashing!r} that may conflict with "
                "photo-realistic generated_image prompts. "
                "Use visual.skip_niche_style: true on affected scenes, "
                "or restructure in E4 Slice 3."
            )
        elements.append(
            StyleElement(
                id="visual_style",
                kind="image_prompt_prefix",
                value=vs,
                source="project_theme",
                scope="generated_image_scenes",
                theme_key="visual_style",
                warnings=warnings,
            )
        )

    # 3. intro_transition_style
    if trans := theme.get("intro_transition_style"):
        slug = trans.replace("-", "_").replace(" ", "_")
        elements.append(
            StyleElement(
                id=f"transition_{slug}",
                kind="transition",
                value=trans,
                source="project_theme",
                scope="all_transitions",
                theme_key="intro_transition_style",
            )
        )

    # 4. anchor_image (stored but never used — surfaces the no-op bug)
    if anchor := theme.get("_anchor_image"):
        elements.append(
            StyleElement(
                id="anchor_image",
                kind="anchor_image",
                value=anchor,
                source="project_theme",
                scope="generated_image_scenes",
                theme_key="_anchor_image",
                active=False,
                warnings=[
                    "anchor_image is stored but NOT used in image generation "
                    "(img2img not yet implemented). It has no effect on rendered output."
                ],
            )
        )

    # 5. Per-scene overrides
    for scene in scenes:
        sid = scene.get("scene_id", "")
        vis = scene.get("visual", {})
        if vis.get("skip_niche_style"):
            overrides.append(
                PerSceneOverride(scene_id=sid, kind="skip_niche_style", value="true")
            )
        if modifier := vis.get("style_modifier"):
            overrides.append(
                PerSceneOverride(scene_id=sid, kind="style_modifier", value=modifier)
            )

    return StyleManifest(
        project_id=project_id,
        elements=elements,
        per_scene_overrides=overrides,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_style_manifest.py::test_style_element_defaults tests/unit/test_style_manifest.py::test_style_element_inactive tests/unit/test_style_manifest.py::test_style_manifest_empty -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/style/__init__.py src/pipeline/style/manifest.py tests/unit/test_style_manifest.py
git commit -m "feat(style): add StyleElement/StyleManifest data structures"
```

---

## Task 2: build_manifest — read style elements from storyboard

**Files:**
- Modify: `tests/unit/test_style_manifest.py` (add `build_manifest` tests)

- [ ] **Step 1: Write failing tests for build_manifest**

Append to `tests/unit/test_style_manifest.py`:

```python
# ── build_manifest tests ──────────────────────────────────────────────────────

def _write_storyboard(tmp_path: Path, theme: dict, scenes: list | None = None) -> Path:
    sb = tmp_path / "storyboard.json"
    sb.write_text(json.dumps({
        "project_id": "test-project",
        "theme": theme,
        "scenes": scenes or [],
    }))
    return sb


def test_build_manifest_frame_style(tmp_path):
    sb = _write_storyboard(tmp_path, {"frame_style": "open_book_page"})
    manifest = build_manifest(sb)
    assert manifest.project_id == "test-project"
    ids = [e.id for e in manifest.elements]
    assert "frame_open_book_page" in ids
    el = next(e for e in manifest.elements if e.id == "frame_open_book_page")
    assert el.kind == "frame"
    assert el.value == "open_book_page"
    assert el.theme_key == "frame_style"
    assert el.active is True
    assert len(el.warnings) == 1  # "no per-scene opt-out" warning always present


def test_build_manifest_visual_style_no_warning(tmp_path):
    sb = _write_storyboard(tmp_path, {"visual_style": "warm amber tones, documentary"})
    manifest = build_manifest(sb)
    el = next(e for e in manifest.elements if e.id == "visual_style")
    assert el.kind == "image_prompt_prefix"
    assert el.warnings == []


def test_build_manifest_visual_style_medium_warning(tmp_path):
    sb = _write_storyboard(
        tmp_path,
        {"visual_style": "soft sketch lines, hand-drawn warmth, no text in images"},
    )
    manifest = build_manifest(sb)
    el = next(e for e in manifest.elements if e.id == "visual_style")
    assert len(el.warnings) == 1
    assert "medium descriptor" in el.warnings[0]


def test_build_manifest_transition(tmp_path):
    sb = _write_storyboard(tmp_path, {"intro_transition_style": "book-page-turn-v2"})
    manifest = build_manifest(sb)
    ids = [e.id for e in manifest.elements]
    assert "transition_book_page_turn_v2" in ids
    el = next(e for e in manifest.elements if e.id == "transition_book_page_turn_v2")
    assert el.kind == "transition"
    assert el.value == "book-page-turn-v2"
    assert el.theme_key == "intro_transition_style"


def test_build_manifest_anchor_image_inactive(tmp_path):
    sb = _write_storyboard(tmp_path, {"_anchor_image": "/configs/niche_anchors/parenting/style_anchor.png"})
    manifest = build_manifest(sb)
    el = next((e for e in manifest.elements if e.id == "anchor_image"), None)
    assert el is not None
    assert el.active is False
    assert el.theme_key == "_anchor_image"
    assert len(el.warnings) == 1
    assert "not used" in el.warnings[0].lower()


def test_build_manifest_empty_theme(tmp_path):
    sb = _write_storyboard(tmp_path, {})
    manifest = build_manifest(sb)
    assert manifest.elements == []
    assert manifest.per_scene_overrides == []


def test_build_manifest_per_scene_skip_niche_style(tmp_path):
    scenes = [
        {"scene_id": "s01", "visual": {"type": "generated_image", "skip_niche_style": True}},
        {"scene_id": "s02", "visual": {"type": "generated_image"}},
    ]
    sb = _write_storyboard(tmp_path, {}, scenes)
    manifest = build_manifest(sb)
    assert len(manifest.per_scene_overrides) == 1
    assert manifest.per_scene_overrides[0].scene_id == "s01"
    assert manifest.per_scene_overrides[0].kind == "skip_niche_style"


def test_build_manifest_per_scene_style_modifier(tmp_path):
    scenes = [
        {"scene_id": "s03", "visual": {"type": "generated_image", "style_modifier": "cinematic lighting"}},
    ]
    sb = _write_storyboard(tmp_path, {}, scenes)
    manifest = build_manifest(sb)
    assert len(manifest.per_scene_overrides) == 1
    assert manifest.per_scene_overrides[0].kind == "style_modifier"
    assert manifest.per_scene_overrides[0].value == "cinematic lighting"


def test_build_manifest_project_id_fallback(tmp_path):
    """project_id falls back to parent directory name if not in JSON."""
    sb = tmp_path / "storyboard.json"
    sb.write_text(json.dumps({"theme": {}, "scenes": []}))
    manifest = build_manifest(sb)
    assert manifest.project_id == tmp_path.name
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/unit/test_style_manifest.py -k "build_manifest" -v 2>&1 | tail -20
```

Expected: all `build_manifest` tests FAIL (function not yet imported).

- [ ] **Step 3: Run the full test file with the implementation in place**

The `build_manifest` implementation is already in `manifest.py` from Task 1. Run:

```bash
uv run pytest tests/unit/test_style_manifest.py -k "build_manifest" -v
```

Expected: all 9 `build_manifest` tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_style_manifest.py
git commit -m "test(style): add build_manifest test coverage"
```

---

## Task 3: Append-only style log

**Files:**
- Create: `src/pipeline/style/log.py`
- Modify: `tests/unit/test_style_manifest.py` (add log tests)

- [ ] **Step 1: Write failing tests for the log**

Append to `tests/unit/test_style_manifest.py`:

```python
# ── Style log tests ───────────────────────────────────────────────────────────

from pipeline.style.log import StyleLogEntry, append_log


def test_append_log_creates_file(tmp_path):
    append_log(tmp_path, "add", "frame_open_book_page", "Tim requested book feel")
    log_path = tmp_path / "style_log.json"
    assert log_path.exists()
    entries = json.loads(log_path.read_text())
    assert len(entries) == 1
    e = entries[0]
    assert e["action"] == "add"
    assert e["element_id"] == "frame_open_book_page"
    assert e["rationale"] == "Tim requested book feel"
    assert "timestamp" in e
    # timestamp must be ISO-8601 with timezone
    assert "T" in e["timestamp"] and ("Z" in e["timestamp"] or "+" in e["timestamp"])


def test_append_log_appends_multiple(tmp_path):
    append_log(tmp_path, "add", "el1", "first")
    append_log(tmp_path, "remove", "el1", "changed mind")
    entries = json.loads((tmp_path / "style_log.json").read_text())
    assert len(entries) == 2
    assert entries[0]["action"] == "add"
    assert entries[1]["action"] == "remove"


def test_append_log_empty_rationale(tmp_path):
    append_log(tmp_path, "remove", "anchor_image")
    entries = json.loads((tmp_path / "style_log.json").read_text())
    assert entries[0]["rationale"] == ""
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/unit/test_style_manifest.py -k "log" -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'pipeline.style.log'`

- [ ] **Step 3: Implement log.py**

Create `src/pipeline/style/log.py`:

```python
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class StyleLogEntry:
    timestamp: str
    action: str        # "add" | "remove" | "add_per_scene" | "remove_per_scene"
    element_id: str
    rationale: str = ""


def append_log(
    project_dir: Path,
    action: str,
    element_id: str,
    rationale: str = "",
) -> None:
    """Append a mutation entry to style_log.json (append-only audit trail)."""
    log_path = project_dir / "style_log.json"
    entry = StyleLogEntry(
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        action=action,
        element_id=element_id,
        rationale=rationale,
    )
    entries: list[dict] = []
    if log_path.exists():
        entries = json.loads(log_path.read_text())
    entries.append(asdict(entry))
    log_path.write_text(json.dumps(entries, indent=2))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_style_manifest.py -k "log" -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/style/log.py tests/unit/test_style_manifest.py
git commit -m "feat(style): add append-only style_log.json"
```

---

## Task 4: CLI `style list` command

**Files:**
- Create: `src/pipeline/style/cli.py`
- Modify: `tests/unit/test_style_manifest.py` (add CLI list tests)

- [ ] **Step 1: Write failing tests for `style list`**

Append to `tests/unit/test_style_manifest.py`:

```python
# ── CLI tests ─────────────────────────────────────────────────────────────────

from typer.testing import CliRunner

from pipeline.style.cli import style_app


def _make_project(tmp_path: Path, project_id: str, theme: dict, scenes: list | None = None) -> Path:
    """Create output/projects/{project_id}/storyboard.json under tmp_path."""
    project_dir = tmp_path / "output" / "projects" / project_id
    project_dir.mkdir(parents=True)
    sb = project_dir / "storyboard.json"
    sb.write_text(json.dumps({
        "project_id": project_id,
        "theme": theme,
        "scenes": scenes or [],
    }))
    return project_dir


def test_style_list_shows_frame(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_project(tmp_path, "test-proj", {"frame_style": "open_book_page"})
    runner = CliRunner()
    result = runner.invoke(style_app, ["list", "--project-id", "test-proj"])
    assert result.exit_code == 0, result.output
    assert "frame_open_book_page" in result.output
    assert "frame" in result.output


def test_style_list_shows_anchor_inactive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_project(tmp_path, "test-anchor", {"_anchor_image": "/some/path.png"})
    runner = CliRunner()
    result = runner.invoke(style_app, ["list", "--project-id", "test-anchor"])
    assert result.exit_code == 0, result.output
    assert "anchor_image" in result.output
    assert "INACTIVE" in result.output


def test_style_list_unknown_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(style_app, ["list", "--project-id", "no-such-project"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/unit/test_style_manifest.py -k "style_list" -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'pipeline.style.cli'`

- [ ] **Step 3: Implement the `list` command**

Create `src/pipeline/style/cli.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import typer

from pipeline.config import PipelineConfig
from pipeline.style.log import append_log
from pipeline.style.manifest import StyleManifest, build_manifest

style_app = typer.Typer(name="style", help="Manage style elements on a project.")

_cfg = PipelineConfig()


def _project_dir(project_id: str) -> Path:
    d = _cfg.OUTPUT_DIR / "projects" / project_id
    if not d.exists():
        typer.echo(f"Project not found: {d}", err=True)
        raise typer.Exit(1)
    return d


def _storyboard_path(project_id: str) -> Path:
    return _project_dir(project_id) / "storyboard.json"


@style_app.command("list")
def list_elements(
    project_id: str = typer.Option(..., "--project-id", help="Project ID"),
) -> None:
    """List all active style elements on a project."""
    sb_path = _storyboard_path(project_id)
    manifest = build_manifest(sb_path)

    typer.echo(f"\nStyle elements active on project: {manifest.project_id}\n")
    col = (36, 22, 16, 26)
    header = (
        f"  {'ID':<{col[0]}} {'KIND':<{col[1]}} {'SOURCE':<{col[2]}} "
        f"{'SCOPE':<{col[3]}} STATUS"
    )
    typer.echo(header)
    typer.echo("  " + "-" * (sum(col) + 10))

    for el in manifest.elements:
        if not el.active:
            status = "INACTIVE ⚠"
        elif el.warnings:
            status = "⚠"
        else:
            status = "ok"
        typer.echo(
            f"  {el.id:<{col[0]}} {el.kind:<{col[1]}} {el.source:<{col[2]}} "
            f"{el.scope:<{col[3]}} {status}"
        )
        for w in el.warnings:
            typer.echo(f"    ⚠  {w}")

    if manifest.per_scene_overrides:
        typer.echo("\nPer-scene overrides:")
        for ov in manifest.per_scene_overrides:
            typer.echo(f"  {ov.scene_id}: {ov.kind}={ov.value}")

    log_path = _project_dir(project_id) / "style_log.json"
    if log_path.exists():
        typer.echo(f"\nStyle log: {log_path}")
    typer.echo()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_style_manifest.py -k "style_list" -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/style/cli.py tests/unit/test_style_manifest.py
git commit -m "feat(style): add 'pipeline style list' command"
```

---

## Task 5: CLI `style remove` command

**Files:**
- Modify: `src/pipeline/style/cli.py`
- Modify: `tests/unit/test_style_manifest.py`

- [ ] **Step 1: Write failing tests for `style remove`**

Append to `tests/unit/test_style_manifest.py`:

```python
def test_style_remove_frame(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project_dir = _make_project(
        tmp_path, "proj-remove",
        {"frame_style": "open_book_page"},
        scenes=[{"scene_id": "s01", "visual": {}}, {"scene_id": "s02", "visual": {}}],
    )
    runner = CliRunner()
    result = runner.invoke(
        style_app,
        ["remove", "--project-id", "proj-remove", "frame_open_book_page"],
    )
    assert result.exit_code == 0, result.output
    # storyboard.json must no longer have frame_style
    data = json.loads((project_dir / "storyboard.json").read_text())
    assert "frame_style" not in data["theme"]
    # log must have been written
    log = json.loads((project_dir / "style_log.json").read_text())
    assert len(log) == 1
    assert log[0]["action"] == "remove"
    assert log[0]["element_id"] == "frame_open_book_page"
    # output must mention how many scenes are affected
    assert "2 scene" in result.output


def test_style_remove_anchor_image(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project_dir = _make_project(
        tmp_path, "proj-anchor",
        {"_anchor_image": "/configs/niche_anchors/parenting/style_anchor.png"},
    )
    runner = CliRunner()
    result = runner.invoke(
        style_app,
        ["remove", "--project-id", "proj-anchor", "anchor_image"],
    )
    assert result.exit_code == 0, result.output
    data = json.loads((project_dir / "storyboard.json").read_text())
    assert "_anchor_image" not in data["theme"]


def test_style_remove_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_project(tmp_path, "proj-notfound", {})
    runner = CliRunner()
    result = runner.invoke(
        style_app,
        ["remove", "--project-id", "proj-notfound", "frame_open_book_page"],
    )
    assert result.exit_code != 0


def test_style_remove_with_rationale(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project_dir = _make_project(tmp_path, "proj-rationale", {"frame_style": "open_book_page"})
    runner = CliRunner()
    runner.invoke(
        style_app,
        [
            "remove", "--project-id", "proj-rationale",
            "frame_open_book_page", "--rationale", "switching to clean look",
        ],
    )
    log = json.loads((project_dir / "style_log.json").read_text())
    assert log[0]["rationale"] == "switching to clean look"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/unit/test_style_manifest.py -k "style_remove" -v 2>&1 | tail -10
```

Expected: all `style_remove` tests FAIL (command not yet implemented).

- [ ] **Step 3: Add `remove` command to `cli.py`**

Append to `src/pipeline/style/cli.py` (before the end of the file):

```python
@style_app.command("remove")
def remove_element(
    project_id: str = typer.Option(..., "--project-id"),
    element_id: str = typer.Argument(..., help="Element ID (from 'style list')"),
    rationale: str = typer.Option("", "--rationale", help="Reason for removal"),
) -> None:
    """Remove a style element from a project."""
    sb_path = _storyboard_path(project_id)
    data = json.loads(sb_path.read_text())
    theme = data.setdefault("theme", {})

    # Build the manifest to look up the element's theme_key
    manifest = build_manifest(sb_path)
    el = next((e for e in manifest.elements if e.id == element_id), None)

    if el is None:
        typer.echo(f"Element {element_id!r} not found on this project.", err=True)
        raise typer.Exit(1)

    if el.theme_key not in theme:
        typer.echo(f"Element {element_id!r} already absent from theme.", err=True)
        raise typer.Exit(1)

    del theme[el.theme_key]
    sb_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    append_log(_project_dir(project_id), "remove", element_id, rationale)

    affected = len(data.get("scenes", []))
    if el.kind == "frame":
        typer.echo(
            f"Removed {element_id}. {affected} scene(s) will lose the frame on next render.\n"
            f"Run: uv run pipeline compose reburn --project-id {project_id}"
        )
    else:
        typer.echo(f"Removed {element_id}. Logged to style_log.json.")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_style_manifest.py -k "style_remove" -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/style/cli.py tests/unit/test_style_manifest.py
git commit -m "feat(style): add 'pipeline style remove' command"
```

---

## Task 6: CLI `style add` command

**Files:**
- Modify: `src/pipeline/style/cli.py`
- Modify: `tests/unit/test_style_manifest.py`

- [ ] **Step 1: Write failing tests for `style add`**

Append to `tests/unit/test_style_manifest.py`:

```python
def test_style_add_frame(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project_dir = _make_project(tmp_path, "proj-add", {})
    runner = CliRunner()
    result = runner.invoke(
        style_app,
        [
            "add", "--project-id", "proj-add",
            "frame_open_book_page", "frame", "open_book_page",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads((project_dir / "storyboard.json").read_text())
    assert data["theme"]["frame_style"] == "open_book_page"
    log = json.loads((project_dir / "style_log.json").read_text())
    assert log[0]["action"] == "add"
    assert log[0]["element_id"] == "frame_open_book_page"


def test_style_add_image_prompt_prefix(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    project_dir = _make_project(tmp_path, "proj-add-vs", {})
    runner = CliRunner()
    result = runner.invoke(
        style_app,
        [
            "add", "--project-id", "proj-add-vs",
            "visual_style", "image_prompt_prefix", "warm amber documentary tones",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads((project_dir / "storyboard.json").read_text())
    assert data["theme"]["visual_style"] == "warm amber documentary tones"


def test_style_add_unknown_kind(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_project(tmp_path, "proj-bad-kind", {})
    runner = CliRunner()
    result = runner.invoke(
        style_app,
        ["add", "--project-id", "proj-bad-kind", "some_id", "unknown_kind", "value"],
    )
    assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/unit/test_style_manifest.py -k "style_add" -v 2>&1 | tail -10
```

Expected: all `style_add` tests FAIL.

- [ ] **Step 3: Add `add` command to `cli.py`**

Append to `src/pipeline/style/cli.py`:

```python
_KIND_TO_THEME_KEY: dict[str, str] = {
    "frame": "frame_style",
    "image_prompt_prefix": "visual_style",
    "transition": "intro_transition_style",
}


@style_app.command("add")
def add_element(
    project_id: str = typer.Option(..., "--project-id"),
    element_id: str = typer.Argument(..., help="Descriptive ID for this element"),
    kind: str = typer.Argument(..., help="frame | image_prompt_prefix | transition"),
    value: str = typer.Argument(..., help="The value to set"),
    rationale: str = typer.Option("", "--rationale", help="Reason for adding"),
) -> None:
    """Add a style element to a project."""
    if kind not in _KIND_TO_THEME_KEY:
        supported = ", ".join(_KIND_TO_THEME_KEY)
        typer.echo(f"Unknown kind {kind!r}. Supported: {supported}", err=True)
        raise typer.Exit(1)

    sb_path = _storyboard_path(project_id)
    data = json.loads(sb_path.read_text())
    theme = data.setdefault("theme", {})
    theme[_KIND_TO_THEME_KEY[kind]] = value
    sb_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    append_log(_project_dir(project_id), "add", element_id, rationale)
    typer.echo(f"Added {element_id} ({kind}={value!r}). Logged to style_log.json.")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_style_manifest.py -k "style_add" -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/style/cli.py tests/unit/test_style_manifest.py
git commit -m "feat(style): add 'pipeline style add' command"
```

---

## Task 7: Wire `style_app` into main CLI

**Files:**
- Modify: `src/pipeline/cli.py`

- [ ] **Step 1: Add import and add_typer**

In `src/pipeline/cli.py`, find the block of `add_typer` calls (lines 42–60). Add after the last one:

```python
from pipeline.style.cli import style_app
```
(add to the imports block at the top, with other `from pipeline.cli_*` imports)

And in the `add_typer` block:

```python
app.add_typer(style_app, name="style")
```

The full change to `cli.py`:

1. In the imports section (around line 20), add:
   ```python
   from pipeline.style.cli import style_app
   ```

2. After line 59 (last `add_typer` call), add:
   ```python
   app.add_typer(style_app, name="style")
   ```

- [ ] **Step 2: Verify `pipeline style --help` works**

```bash
uv run pipeline style --help
```

Expected output contains:
```
Commands:
  add     Add a style element to a project.
  list    List all active style elements on a project.
  remove  Remove a style element from a project.
```

- [ ] **Step 3: Smoke-test against the real baby-walker project**

```bash
uv run pipeline style list --project-id 20260504-115232-baby-walker-story
```

Expected: prints a table with at minimum `frame_open_book_page` and `visual_style` rows.

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/cli.py
git commit -m "feat(style): wire style_app into main pipeline CLI"
```

---

## Task 8: Remove the dead `anchor_image` parameter

**Files:**
- Modify: `src/pipeline/composer/image.py`
- Modify: `src/pipeline/composer/base.py`
- Modify: `tests/unit/test_style_manifest.py`

- [ ] **Step 1: Write a test that will pass only after the removal**

Append to `tests/unit/test_style_manifest.py`:

```python
# ── Dead-code removal verification ────────────────────────────────────────────

def test_render_generated_image_no_anchor_param():
    """anchor_image must NOT be a parameter of render_generated_image (dead code removed)."""
    import inspect
    from pipeline.composer.image import render_generated_image
    sig = inspect.signature(render_generated_image)
    assert "anchor_image" not in sig.parameters, (
        "anchor_image is still in render_generated_image signature. "
        "Remove it from image.py:99 and the call site in base.py."
    )
```

- [ ] **Step 2: Run test to confirm it currently fails**

```bash
uv run pytest tests/unit/test_style_manifest.py::test_render_generated_image_no_anchor_param -v
```

Expected: FAIL — `anchor_image is still in render_generated_image signature`

- [ ] **Step 3: Remove `anchor_image` from `image.py`**

In `src/pipeline/composer/image.py`, remove the line at ~line 99:

Old function signature (lines ~87–100):
```python
def render_generated_image(
    visual: dict,
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
    gallery_path: Path | None = None,
    niche: str | None = None,
    scene_narration: str = "",
    theme: dict | None = None,
    style_prefix: str = "",
    seed: int | None = None,
    anchor_image: Path | None = None,   # ← REMOVE THIS LINE
) -> Path:
```

New signature (remove the `anchor_image` line):
```python
def render_generated_image(
    visual: dict,
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
    gallery_path: Path | None = None,
    niche: str | None = None,
    scene_narration: str = "",
    theme: dict | None = None,
    style_prefix: str = "",
    seed: int | None = None,
) -> Path:
```

- [ ] **Step 4: Remove the `anchor_image` read and call site from `base.py`**

In `src/pipeline/composer/base.py`, around lines 344–361, remove three lines:

Current code:
```python
        seed_raw = theme.get("_seed")
        seed: int | None = int(seed_raw) if seed_raw is not None else None
        anchor_raw = theme.get("_anchor_image")          # ← REMOVE
        anchor_image: Path | None = Path(anchor_raw) if anchor_raw else None  # ← REMOVE

        gallery_path = Path("output/gallery/gallery_index.json")
        return render_generated_image(
            visual,
            duration_sec,
            width,
            height,
            work_dir,
            scene_id,
            gallery_path=gallery_path,
            niche=theme.get("niche"),
            scene_narration=scene.get("narration", ""),
            theme=theme,
            style_prefix=base_style,
            seed=seed,
            anchor_image=anchor_image,   # ← REMOVE
        )
```

New code (3 lines removed):
```python
        seed_raw = theme.get("_seed")
        seed: int | None = int(seed_raw) if seed_raw is not None else None

        gallery_path = Path("output/gallery/gallery_index.json")
        return render_generated_image(
            visual,
            duration_sec,
            width,
            height,
            work_dir,
            scene_id,
            gallery_path=gallery_path,
            niche=theme.get("niche"),
            scene_narration=scene.get("narration", ""),
            theme=theme,
            style_prefix=base_style,
            seed=seed,
        )
```

- [ ] **Step 5: Run the dead-code test to confirm it passes**

```bash
uv run pytest tests/unit/test_style_manifest.py::test_render_generated_image_no_anchor_param -v
```

Expected: PASSED.

- [ ] **Step 6: Run the full test suite to confirm no regressions**

```bash
uv run pytest tests/unit/ -x -q 2>&1 | tail -20
```

Expected: all tests pass (including all existing chart / chart_anim tests).

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/composer/image.py src/pipeline/composer/base.py tests/unit/test_style_manifest.py
git commit -m "refactor(style): remove dead anchor_image parameter from render_generated_image"
```

---

## Task 9: Quality pass and final verification

**Files:** none new — verification only

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest -x -q 2>&1 | tail -20
```

Expected: all tests pass. Note any pre-existing failures in unrelated files (do not fix them).

- [ ] **Step 2: ruff + mypy on new and modified files**

```bash
uv run ruff check src/pipeline/style/ src/pipeline/composer/image.py src/pipeline/composer/base.py src/pipeline/cli.py
uv run mypy src/pipeline/style/ src/pipeline/composer/image.py src/pipeline/composer/base.py
```

Expected: no errors on the sprint files. Pre-existing errors in unrelated files are out of scope.

- [ ] **Step 3: Manual smoke-test on the baby-walker project**

```bash
uv run pipeline style list --project-id 20260504-115232-baby-walker-story
```

Verify the output shows:
- `frame_open_book_page` — frame — project_theme — all_scenes — ⚠ (with "no per-scene opt-out" warning)
- `visual_style` — image_prompt_prefix — project_theme — generated_image_scenes — ok (or ⚠ if it contains medium descriptors)
- `transition_book_page_turn_v2` — transition — project_theme — all_transitions — ok

- [ ] **Step 4: Final sprint commit with sprint log update**

```bash
git add .agent-memory/engineering-manager/sprint-log.md
git commit -m "docs(em): record Sprint 3 SHIPPED in sprint-log"
```

---

## Self-Review

**Spec coverage:**
- ✅ `pipeline style list` — Task 4
- ✅ `pipeline style remove` (project-level) — Task 5
- ✅ `pipeline style add` — Task 6
- ✅ `style_log.json` append-only — Task 3
- ✅ `anchor_image` dead-code removal — Task 8
- ✅ Wired into main CLI — Task 7
- ✅ `build_manifest` reads frame, visual_style, transition, anchor_image, per-scene overrides — Task 1+2
- ✅ Warnings for medium-descriptor conflicts and anchor INACTIVE — Task 1+2
- ⬜ Per-scene `style remove` (e.g. `--scene s25 skip_niche_style`) — scoped OUT per proposal (deferred to E4 later sprint)
- ⬜ Slice 3 (niche template refactor) — scoped OUT
- ⬜ Slice 5 (dashboard panel) — scoped OUT → E6

**Placeholder scan:** No TBDs, no "similar to above", all code blocks contain real code.

**Type consistency:**
- `StyleElement.theme_key: str` used in Task 1, referenced in Task 5 (`el.theme_key`) — ✅
- `append_log(project_dir: Path, ...)` defined in Task 3, called in Tasks 5+6 — ✅
- `build_manifest(storyboard_path: Path) → StyleManifest` defined in Task 1, called in Tasks 2+4+5 — ✅
- `style_app` defined in Task 4, imported in Task 7 — ✅
- `_make_project` test helper defined in Task 4, reused in Tasks 5+6 — ✅
