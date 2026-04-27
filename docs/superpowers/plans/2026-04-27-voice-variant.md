# Voice Variant Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `pipeline compose voice-variant` and `pipeline compose promote-voice` CLI commands plus a `voice-variant` skill so re-rendering a project with a different TTS voice is a single command instead of a manual context.json hack.

**Architecture:** Two new Typer commands live in `src/pipeline/cli_compose.py` alongside `rescene`/`reburn`. `voice-variant` forks a project into a new directory named `{parent-id}_{voice-id}`, writes a fresh `context.json`, and runs TTS + Compose automatically. `promote-voice` copies the variant's rendered scenes + audio back to the parent and re-runs ComposeStage (which skips re-rendering cached scenes, only concatenating + burning subtitles). Two new optional fields on `PipelineContext` track the parent relationship. A new `.claude/skills/voice-variant.md` skill wraps the CLI for assistant-driven workflows.

**Tech Stack:** Python 3.11+, Typer, Pydantic dataclass (PipelineContext), asyncio, pytest + typer.testing.CliRunner

---

## File Map

| Action | File |
|---|---|
| Modify | `src/pipeline/stages/base.py` — add `parent_project_id`, `variant_label` fields |
| Modify | `src/pipeline/cli_compose.py` — add `voice_variant` and `promote_voice` commands |
| Create | `tests/unit/test_voice_variant.py` |
| Create | `.claude/skills/voice-variant.md` |

---

### Task 1: Add `parent_project_id` and `variant_label` to PipelineContext

**Files:**
- Modify: `src/pipeline/stages/base.py`
- Test: `tests/unit/test_voice_variant.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_voice_variant.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.stages.base import PipelineContext


def _base_ctx(work_dir: Path) -> PipelineContext:
    return PipelineContext(
        project_id=9000,
        source_url="https://youtube.com/watch?v=abc",
        locale="zh-TW",
        work_dir=work_dir,
    )


def test_parent_project_id_defaults_none(tmp_path):
    ctx = _base_ctx(tmp_path)
    assert ctx.parent_project_id is None
    assert ctx.variant_label is None


def test_variant_fields_round_trip(tmp_path):
    ctx = _base_ctx(tmp_path)
    ctx.parent_project_id = 1776997800
    ctx.variant_label = "tim-zhtw-fish"
    ctx.save()

    loaded = PipelineContext.load(tmp_path / "context.json")
    assert loaded.parent_project_id == 1776997800
    assert loaded.variant_label == "tim-zhtw-fish"


def test_from_dict_ignores_missing_variant_fields(tmp_path):
    """Old context.json without new fields loads without error."""
    ctx = _base_ctx(tmp_path)
    d = ctx.to_dict()
    d.pop("parent_project_id", None)
    d.pop("variant_label", None)
    # Simulate loading an old context.json by patching PipelineContext.from_dict
    # The new fields have defaults so missing keys must be tolerated.
    loaded = PipelineContext.from_dict(d)
    assert loaded.parent_project_id is None
    assert loaded.variant_label is None
```

- [ ] **Step 2: Run to confirm it fails**

```bash
uv run pytest tests/unit/test_voice_variant.py -v
```

Expected: `AttributeError: 'PipelineContext' object has no attribute 'parent_project_id'`

- [ ] **Step 3: Add fields to PipelineContext**

In `src/pipeline/stages/base.py`, add two fields after `reference_storyboard_path` (line 58), before `def to_dict`:

```python
    # Voice variant tracking (set when this project is a voice fork of another)
    parent_project_id: int | None = None
    variant_label: str | None = None
```

No changes to `to_dict` or `from_dict` — `asdict` serialises all fields automatically, and `from_dict` passes `**cleaned` to the constructor which already has defaults for the new fields. Unknown keys in JSON (from future additions) will still raise; that's intentional.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_voice_variant.py -v
```

Expected: all 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/base.py tests/unit/test_voice_variant.py
git commit -m "feat(context): add parent_project_id and variant_label fields"
```

---

### Task 2: `pipeline compose voice-variant` command

**Files:**
- Modify: `src/pipeline/cli_compose.py`
- Test: `tests/unit/test_voice_variant.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_voice_variant.py`:

```python
import shutil
from unittest.mock import patch

from typer.testing import CliRunner

from pipeline.cli_compose import compose_app


def _make_parent_project(tmp_path: Path) -> Path:
    """Minimal fully-built parent project directory."""
    work_dir = tmp_path / "projects" / "1776997800"
    (work_dir / "audio").mkdir(parents=True)
    (work_dir / "compose" / "scenes").mkdir(parents=True)
    (work_dir / "script").mkdir(parents=True)

    (work_dir / "storyboard.json").write_text(
        '{"scenes": [], "aspect_ratio": "16:9", "theme": {}}'
    )
    (work_dir / "knowledge.json").write_text("{}")
    (work_dir / "script" / "script_zh-TW.md").write_text("narration")
    (work_dir / "metadata.json").write_text("{}")
    (work_dir / "thumbnail.png").write_bytes(b"png")

    srt = work_dir / "audio" / "subs.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")

    ctx = PipelineContext(
        project_id=1776997800,
        source_url="https://youtube.com/watch?v=abc",
        locale="zh-TW",
        work_dir=work_dir,
        niche="parenting",
        storyboard_path=work_dir / "storyboard.json",
        script_path=work_dir / "script" / "script_zh-TW.md",
        knowledge_path=work_dir / "knowledge.json",
        subtitle_path=srt,
        preferred_variant="subtitles_no_overlay",
        segment_timings=[{"path": str(work_dir / "audio" / "s1.wav"),
                          "text": "Hello", "start_ms": 0, "duration_ms": 1000}],
    )
    ctx.save()
    return work_dir


def test_voice_variant_creates_dir_structure(tmp_path):
    """voice-variant creates {parent}_{voice} directory with copied assets."""
    parent_dir = _make_parent_project(tmp_path)
    variant_dir = tmp_path / "projects" / "1776997800_tim-zhtw-fish"

    runner = CliRunner()
    with (
        patch("pipeline.cli_compose._resolve_projects_dir", return_value=tmp_path / "projects"),
        patch("pipeline.cli_compose.asyncio.run"),  # skip TTS+compose
    ):
        result = runner.invoke(compose_app, [
            "voice-variant",
            "--from-project", "1776997800",
            "--voice", "tim-zhtw-fish",
        ])

    assert result.exit_code == 0, result.output
    assert (variant_dir / "storyboard.json").exists()
    assert (variant_dir / "knowledge.json").exists()
    assert (variant_dir / "script" / "script_zh-TW.md").exists()
    assert (variant_dir / "metadata.json").exists()
    assert (variant_dir / "thumbnail.png").exists()


def test_voice_variant_context_json(tmp_path):
    """voice-variant writes correct context.json overrides."""
    parent_dir = _make_parent_project(tmp_path)
    variant_dir = tmp_path / "projects" / "1776997800_tim-zhtw-fish"

    runner = CliRunner()
    with (
        patch("pipeline.cli_compose._resolve_projects_dir", return_value=tmp_path / "projects"),
        patch("pipeline.cli_compose.asyncio.run"),
    ):
        runner.invoke(compose_app, [
            "voice-variant",
            "--from-project", "1776997800",
            "--voice", "tim-zhtw-fish",
        ])

    ctx = PipelineContext.load(variant_dir / "context.json")
    assert ctx.voice_id == "tim-zhtw-fish"
    assert ctx.parent_project_id == 1776997800
    assert ctx.variant_label == "tim-zhtw-fish"
    assert ctx.segment_timings is None
    assert ctx.subtitle_path is None
    assert ctx.narration_path is None
    assert ctx.final_video_path is None
    assert ctx.youtube_video_id is None
    # storyboard/script/knowledge point INSIDE the variant dir
    assert ctx.storyboard_path is not None
    assert str(ctx.storyboard_path).startswith(str(variant_dir))
    assert ctx.script_path is not None
    assert str(ctx.script_path).startswith(str(variant_dir))


def test_voice_variant_errors_if_exists(tmp_path):
    """voice-variant exits with error if variant dir already exists."""
    parent_dir = _make_parent_project(tmp_path)
    variant_dir = tmp_path / "projects" / "1776997800_tim-zhtw-fish"
    variant_dir.mkdir(parents=True)

    runner = CliRunner()
    with patch("pipeline.cli_compose._resolve_projects_dir", return_value=tmp_path / "projects"):
        result = runner.invoke(compose_app, [
            "voice-variant",
            "--from-project", "1776997800",
            "--voice", "tim-zhtw-fish",
        ])

    assert result.exit_code != 0
    assert "already exists" in result.output


def test_voice_variant_force_overwrites(tmp_path):
    """voice-variant --force removes existing variant dir before creating."""
    parent_dir = _make_parent_project(tmp_path)
    variant_dir = tmp_path / "projects" / "1776997800_tim-zhtw-fish"
    variant_dir.mkdir(parents=True)
    stale = variant_dir / "stale.txt"
    stale.write_text("stale")

    runner = CliRunner()
    with (
        patch("pipeline.cli_compose._resolve_projects_dir", return_value=tmp_path / "projects"),
        patch("pipeline.cli_compose.asyncio.run"),
    ):
        result = runner.invoke(compose_app, [
            "voice-variant",
            "--from-project", "1776997800",
            "--voice", "tim-zhtw-fish",
            "--force",
        ])

    assert result.exit_code == 0, result.output
    assert not stale.exists()
    assert (variant_dir / "storyboard.json").exists()
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest tests/unit/test_voice_variant.py::test_voice_variant_creates_dir_structure -v
```

Expected: `AttributeError` or `Error: No such command 'voice-variant'`

- [ ] **Step 3: Add `_resolve_projects_dir` helper and `voice_variant` command to `cli_compose.py`**

Add `_resolve_projects_dir` right after `_resolve_work_dir` (around line 30 in `cli_compose.py`):

```python
def _resolve_projects_dir() -> Path:
    config = PipelineConfig()
    return config.OUTPUT_DIR / "projects"
```

Then add the `voice_variant` command after the `clean` command (at the end of the file):

```python
@compose_app.command("voice-variant")
def voice_variant(
    from_project: int = typer.Option(..., "--from-project", help="Parent project ID to fork from"),
    voice: str = typer.Option(..., "--voice", help="Voice profile ID for the variant"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing variant directory"),
) -> None:
    """Fork a project with a different voice and render TTS + compose."""
    import time

    from pipeline.orchestrator import Orchestrator
    from pipeline.stages.compose import ComposeStage
    from pipeline.stages.tts import TtsStage

    projects_dir = _resolve_projects_dir()
    parent_dir = projects_dir / str(from_project)
    if not parent_dir.exists():
        typer.echo(f"Parent project not found: {parent_dir}", err=True)
        raise typer.Exit(code=1)

    variant_name = f"{from_project}_{voice}"
    variant_dir = projects_dir / variant_name

    if variant_dir.exists():
        if not force:
            typer.echo(
                f"Variant directory already exists: {variant_dir}\n"
                "Use --force to overwrite.",
                err=True,
            )
            raise typer.Exit(code=1)
        shutil.rmtree(variant_dir)

    variant_dir.mkdir(parents=True)

    # Copy independent assets (storyboard, script, knowledge, metadata, thumbnail)
    for name in ("storyboard.json", "knowledge.json", "metadata.json", "thumbnail.png"):
        src = parent_dir / name
        if src.exists():
            shutil.copy2(src, variant_dir / name)

    script_src = parent_dir / "script"
    if script_src.exists():
        shutil.copytree(script_src, variant_dir / "script")

    # Build variant context.json from parent's context with overrides
    parent_ctx = PipelineContext.load(parent_dir / "context.json")

    # Remap paths that were inside parent_dir to variant_dir
    def _remap(p: Path | None) -> Path | None:
        if p is None:
            return None
        try:
            rel = p.relative_to(parent_dir)
            return variant_dir / rel
        except ValueError:
            return p  # path was already outside parent_dir (e.g. source/)

    variant_ctx = PipelineContext(
        # Identity
        project_id=int(time.time()),
        source_url=parent_ctx.source_url,
        locale=parent_ctx.locale,
        work_dir=variant_dir,
        niche=parent_ctx.niche,
        # Source material (kept from parent — variant doesn't re-download)
        video_path=parent_ctx.video_path,
        transcript_path=parent_ctx.transcript_path,
        transcript_text=parent_ctx.transcript_text,
        # Analysis (kept from parent)
        story_structure=parent_ctx.story_structure,
        knowledge_graph=parent_ctx.knowledge_graph,
        clip_timestamps=parent_ctx.clip_timestamps,
        knowledge_path=_remap(parent_ctx.knowledge_path),
        # Storyboard / script (now inside variant dir)
        storyboard_path=_remap(parent_ctx.storyboard_path),
        script_path=_remap(parent_ctx.script_path),
        # TTS — reset (will be re-generated)
        narration_path=None,
        subtitle_path=None,
        segment_timings=None,
        voice_id=voice,
        # Compose — reset
        final_video_path=None,
        burn_subtitles=parent_ctx.burn_subtitles,
        skip_overlays=parent_ctx.skip_overlays,
        preferred_variant=parent_ctx.preferred_variant,
        # Publish — reset (variant is not published until promoted)
        youtube_video_id=None,
        thumbnail_uploaded=False,
        disclosure_set=False,
        published_at=None,
        publish_profile=parent_ctx.publish_profile,
        # Provenance
        source_locale=parent_ctx.source_locale,
        reference_storyboard_path=parent_ctx.reference_storyboard_path,
        parent_project_id=from_project,
        variant_label=voice,
    )
    variant_ctx.save()

    typer.echo(f"Variant project created: {variant_dir}")
    typer.echo(f"Running TTS + compose with voice '{voice}'...")

    entry = SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"compose voice-variant --from-project {from_project} --voice {voice}",
    )
    try:
        result = asyncio.run(
            Orchestrator([TtsStage(), ComposeStage()]).run(variant_ctx, start_from="tts")
        )
        if not result.success:
            entry.outcome = "failed"
            entry.error = result.error[:200]
            entry.summary = f"voice-variant failed at {result.failed_stage}"
            append_session(variant_dir, entry)
            typer.echo(f"Pipeline failed at stage: {result.failed_stage}", err=True)
            raise typer.Exit(code=1)

        entry.stages = ["tts", "compose"]
        entry.summary = f"voice-variant: {from_project} → {variant_name}"
        final_ctx = result.ctx
    except typer.Exit:
        raise
    except Exception as exc:
        entry.outcome = "failed"
        entry.error = str(exc)[:200]
        entry.summary = f"voice-variant error: {exc}"
        append_session(variant_dir, entry)
        raise
    finally:
        append_session(variant_dir, entry)

    final_path = final_ctx.final_video_path or (
        variant_dir / "compose" / f"final_{variant_ctx.locale}_{variant_ctx.preferred_variant or 'subtitles_no_overlay'}.mp4"
    )
    typer.echo(f"\nVoice variant ready:\n  {final_path}")
    typer.echo(f"\nMake {voice} the permanent voice for project {from_project}?")
    typer.echo(f"  [P] Promote  — copy audio to original, reburn (fast, no scene re-render)")
    typer.echo(f"  [D] Delete   — discard this variant, keep original as-is")
    typer.echo(f"  [K] Keep both — decide later")
    choice = typer.prompt("Choice", default="K").strip().upper()

    if choice == "P":
        typer.echo("Promoting...")
        _do_promote(variant_name, projects_dir, ask_delete=True)
    elif choice == "D":
        shutil.rmtree(variant_dir)
        typer.echo(f"Variant deleted: {variant_dir}")
    else:
        typer.echo(
            f"Keeping both. To promote later:\n"
            f"  uv run pipeline compose promote-voice --from-project {variant_name}"
        )
```

Also add `import shutil` at the top of `cli_compose.py` if not already there.

- [ ] **Step 4: Run the failing tests**

```bash
uv run pytest tests/unit/test_voice_variant.py -k "voice_variant" -v
```

Expected: all 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/base.py src/pipeline/cli_compose.py tests/unit/test_voice_variant.py
git commit -m "feat(compose): add voice-variant command"
```

---

### Task 3: `pipeline compose promote-voice` command

**Files:**
- Modify: `src/pipeline/cli_compose.py`
- Test: `tests/unit/test_voice_variant.py` (append)

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_voice_variant.py`:

```python
def _make_variant_project(tmp_path: Path, parent_dir: Path) -> Path:
    """Minimal rendered variant project."""
    variant_dir = tmp_path / "projects" / "1776997800_tim-zhtw-fish"
    audio_dir = variant_dir / "audio"
    scenes_dir = variant_dir / "compose" / "scenes"
    audio_dir.mkdir(parents=True)
    scenes_dir.mkdir(parents=True)
    (variant_dir / "script").mkdir()

    srt = audio_dir / "subs.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")
    narration = audio_dir / "narration.wav"
    narration.write_bytes(b"wav")
    s1 = audio_dir / "s1.wav"
    s1.write_bytes(b"s1wav")

    (scenes_dir / "s1_final.mp4").write_bytes(b"s1final")
    (scenes_dir / "s1_final_no_overlay.mp4").write_bytes(b"s1final_no_ov")

    ctx = PipelineContext(
        project_id=9001,
        source_url="https://youtube.com/watch?v=abc",
        locale="zh-TW",
        work_dir=variant_dir,
        parent_project_id=1776997800,
        variant_label="tim-zhtw-fish",
        voice_id="tim-zhtw-fish",
        subtitle_path=srt,
        narration_path=narration,
        niche="parenting",
        preferred_variant="subtitles_no_overlay",
        segment_timings=[{
            "path": str(s1),
            "text": "Hello",
            "start_ms": 0,
            "duration_ms": 1000,
        }],
        storyboard_path=parent_dir / "storyboard.json",
    )
    ctx.save()
    return variant_dir


def test_promote_voice_copies_scenes_and_audio(tmp_path):
    """promote-voice copies variant's scenes + audio to parent dir."""
    parent_dir = _make_parent_project(tmp_path)
    variant_dir = _make_variant_project(tmp_path, parent_dir)

    runner = CliRunner()
    with (
        patch("pipeline.cli_compose._resolve_projects_dir", return_value=tmp_path / "projects"),
        patch("pipeline.cli_compose.asyncio.run"),  # skip ComposeStage
    ):
        result = runner.invoke(compose_app, [
            "promote-voice",
            "--from-project", "1776997800_tim-zhtw-fish",
        ])

    assert result.exit_code == 0, result.output
    # Scene files copied to parent
    assert (parent_dir / "compose" / "scenes" / "s1_final.mp4").read_bytes() == b"s1final"
    assert (parent_dir / "compose" / "scenes" / "s1_final_no_overlay.mp4").read_bytes() == b"s1final_no_ov"
    # Audio files copied
    assert (parent_dir / "audio" / "narration.wav").exists()


def test_promote_voice_updates_parent_context(tmp_path):
    """promote-voice patches parent context.json with variant's voice + timings."""
    parent_dir = _make_parent_project(tmp_path)
    variant_dir = _make_variant_project(tmp_path, parent_dir)

    runner = CliRunner()
    with (
        patch("pipeline.cli_compose._resolve_projects_dir", return_value=tmp_path / "projects"),
        patch("pipeline.cli_compose.asyncio.run"),
    ):
        runner.invoke(compose_app, [
            "promote-voice",
            "--from-project", "1776997800_tim-zhtw-fish",
        ])

    parent_ctx = PipelineContext.load(parent_dir / "context.json")
    assert parent_ctx.voice_id == "tim-zhtw-fish"
    assert parent_ctx.segment_timings is not None
    assert parent_ctx.subtitle_path is not None
    assert str(parent_ctx.subtitle_path).startswith(str(parent_dir))


def test_promote_voice_errors_without_parent_project_id(tmp_path):
    """promote-voice exits with error if variant has no parent_project_id."""
    orphan_dir = tmp_path / "projects" / "orphan"
    orphan_dir.mkdir(parents=True)
    ctx = PipelineContext(
        project_id=9002,
        source_url="x",
        locale="zh-TW",
        work_dir=orphan_dir,
        # parent_project_id intentionally omitted
    )
    ctx.save()

    runner = CliRunner()
    with patch("pipeline.cli_compose._resolve_projects_dir", return_value=tmp_path / "projects"):
        result = runner.invoke(compose_app, ["promote-voice", "--from-project", "orphan"])

    assert result.exit_code != 0
    assert "not a voice variant" in result.output.lower() or "parent_project_id" in result.output.lower()
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest tests/unit/test_voice_variant.py -k "promote" -v
```

Expected: `Error: No such command 'promote-voice'`

- [ ] **Step 3: Add `_do_promote` helper and `promote_voice` command to `cli_compose.py`**

Add a module-level `_do_promote` helper (called by both `voice_variant` inline choice P and the standalone `promote-voice` command). Place it just before the `voice_variant` command:

```python
def _do_promote(variant_name: str, projects_dir: Path, ask_delete: bool = False) -> None:
    """Copy variant audio + scenes to parent, update parent context, re-compose."""
    from pipeline.orchestrator import Orchestrator
    from pipeline.stages.compose import ComposeStage

    variant_dir = projects_dir / variant_name
    if not variant_dir.exists():
        typer.echo(f"Variant directory not found: {variant_dir}", err=True)
        raise typer.Exit(code=1)

    variant_ctx = PipelineContext.load(variant_dir / "context.json")
    if variant_ctx.parent_project_id is None:
        typer.echo(
            f"'{variant_name}' is not a voice variant (parent_project_id not set).", err=True
        )
        raise typer.Exit(code=1)

    parent_dir = projects_dir / str(variant_ctx.parent_project_id)
    if not parent_dir.exists():
        typer.echo(f"Parent project not found: {parent_dir}", err=True)
        raise typer.Exit(code=1)

    parent_ctx = PipelineContext.load(parent_dir / "context.json")

    # 1. Copy audio directory (all files)
    parent_audio = parent_dir / "audio"
    parent_audio.mkdir(exist_ok=True)
    for f in (variant_dir / "audio").iterdir():
        shutil.copy2(f, parent_audio / f.name)

    # 2. Copy scene files (overwrite parent's existing scenes)
    parent_scenes = parent_dir / "compose" / "scenes"
    parent_scenes.mkdir(parents=True, exist_ok=True)
    variant_scenes = variant_dir / "compose" / "scenes"
    if variant_scenes.exists():
        for f in variant_scenes.iterdir():
            shutil.copy2(f, parent_scenes / f.name)

    # 3. Delete parent's stale raw.mp4 / raw_no_overlay.mp4 so ComposeStage re-concatenates
    for raw_name in ("raw.mp4", "raw_no_overlay.mp4"):
        raw = parent_dir / "compose" / raw_name
        if raw.exists():
            raw.unlink()

    # 4. Patch parent context.json: voice, timings, subtitle path, narration path
    def _remap_to_parent(p: Path | None) -> Path | None:
        if p is None:
            return None
        try:
            rel = p.relative_to(variant_dir)
            return parent_dir / rel
        except ValueError:
            return p

    parent_ctx.voice_id = variant_ctx.voice_id
    parent_ctx.segment_timings = variant_ctx.segment_timings
    parent_ctx.subtitle_path = _remap_to_parent(variant_ctx.subtitle_path)
    parent_ctx.narration_path = _remap_to_parent(variant_ctx.narration_path)
    parent_ctx.save()

    # 5. Re-run ComposeStage (skips scene re-render since files exist; only concatenates + burns)
    typer.echo("Re-composing parent project...")
    asyncio.run(ComposeStage().run(parent_ctx))

    typer.echo(
        f"Promoted. Parent project {variant_ctx.parent_project_id} now uses voice '{variant_ctx.voice_id}'."
    )

    if ask_delete:
        if typer.confirm(f"Delete variant directory '{variant_name}'?", default=False):
            shutil.rmtree(variant_dir)
            typer.echo(f"Variant deleted: {variant_dir}")
```

Then add the `promote_voice` command at the end of the file:

```python
@compose_app.command("promote-voice")
def promote_voice(
    from_project: str = typer.Option(
        ..., "--from-project",
        help="Variant directory name (e.g. 1776997800_tim-zhtw-fish)"
    ),
) -> None:
    """Promote a voice variant's audio to its parent project and reburn."""
    projects_dir = _resolve_projects_dir()
    _do_promote(from_project, projects_dir, ask_delete=True)
```

- [ ] **Step 4: Run all voice-variant tests**

```bash
uv run pytest tests/unit/test_voice_variant.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Run full unit test suite to check for regressions**

```bash
uv run pytest tests/unit/ -v --tb=short
```

Expected: all pass (no regressions in existing compose tests)

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/cli_compose.py tests/unit/test_voice_variant.py
git commit -m "feat(compose): add promote-voice command"
```

---

### Task 4: `voice-variant` skill

**Files:**
- Create: `.claude/skills/voice-variant.md`

No unit tests — skill files are markdown that the assistant reads at runtime.

- [ ] **Step 1: Write the skill file**

```markdown
---
name: voice-variant
description: Use when the user wants to build a variant of an existing project with a different TTS voice, try a custom voice on a produced project, or promote/discard a voice variant. Triggers: "try X voice on project Y", "build a tim-zhtw-fish version", "make a voice variant", "promote the voice variant", "delete the voice variant".
---

# Voice Variant

Build, compare, and decide on voice variants of produced projects.

## Input

- **Arguments:** $ARGUMENTS
- Formats: `<project-id> <voice-id>`, `promote <variant-dir>`, `delete <variant-dir>`, or infer from conversation context.

---

## Autonomy contract

Once the user states their intent (build / promote / delete), execute the full chain automatically — no mid-chain confirmations.

Gates where you pause:
1. Confirming project-id and voice-id before building (if not clear from context)
2. After render: showing the P/D/K prompt
3. After Promote: "Delete variant?" (ask once, then act)
4. Unexpected failure

---

## Step 1 — Resolve project and voice

From conversation context, determine:
- `--from-project` — the parent project ID (integer)
- `--voice` — the voice profile ID (e.g. `tim-zhtw-fish`)

If either is ambiguous, ask once before proceeding. Check variant dir doesn't already exist:

```bash
ls output/projects/ | grep "^{from_project}_"
```

If it exists and `--force` is not intended, ask the user: "Variant `{parent}_{voice}` already exists — overwrite with `--force`, or work with the existing one?"

---

## Step 2 — Build the variant

```bash
uv run pipeline compose voice-variant \
    --from-project <from_project> \
    --voice <voice_id>
```

This runs TTS + Compose automatically. Wait for it to complete (may take several minutes for FishAudio voices).

---

## Step 3 — Post-render decision

After the command prints the soft prompt, relay it to the user:

```
Voice variant ready:
  output/projects/{parent}_{voice}/compose/final_zh-TW_subtitles_no_overlay.mp4

Make {voice} the permanent voice for project {parent}?
  [P] Promote  — copy audio to original, reburn (fast, no scene re-render)
  [D] Delete   — discard this variant, keep original as-is
  [K] Keep both — decide later
```

Wait for the user's choice. The CLI itself also prompts — if running interactively, the CLI will handle it. If the CLI was invoked non-interactively (via `asyncio.run`), relay the prompt yourself and act on the response.

---

## Step 4 — Act on choice (no further prompts)

### P — Promote

```bash
uv run pipeline compose promote-voice --from-project {parent}_{voice}
```

After promote completes, ask once: "Delete the variant directory `{parent}_{voice}`? [y/N]"
Then act immediately.

### D — Delete

```bash
rm -rf output/projects/{parent}_{voice}/
```

Confirm deletion to the user.

### K — Keep both

Remind the user of the promote command for later:

```
Both projects kept. Original project {parent} is still the default for publish.
To promote later: uv run pipeline compose promote-voice --from-project {parent}_{voice}
```

---

## Rebuild decision tree

```
User: "try tim-zhtw-fish on project 1776997800"
  ↓
Resolve project-id + voice-id
  ↓
Check variant dir doesn't already exist
  ↓
Run: pipeline compose voice-variant --from-project 1776997800 --voice tim-zhtw-fish
  ↓
[Render completes]
  ↓
Show P/D/K prompt — wait for user
  ↓
P → promote-voice → ask delete once → act
D → rm -rf variant dir
K → print keep-both message, done
```
```

- [ ] **Step 2: Write the skill file to disk**

Save the content above to `.claude/skills/voice-variant.md`.

- [ ] **Step 3: Verify skill is discoverable**

```bash
grep -l "voice-variant" .claude/skills/
```

Expected: `.claude/skills/voice-variant.md`

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/voice-variant.md
git commit -m "feat(skill): add voice-variant skill"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task that covers it |
|---|---|
| `parent_project_id` + `variant_label` schema fields | Task 1 |
| `voice-variant` creates variant dir with correct name | Task 2 |
| `voice-variant` copies storyboard/script/knowledge/metadata/thumbnail | Task 2 |
| `voice-variant` resets audio/compose/publish fields | Task 2 (context JSON assertions) |
| `voice-variant` runs TTS + Compose | Task 2 (Orchestrator call) |
| `voice-variant --force` overwrites existing variant | Task 2 |
| Soft prompt P/D/K printed after render | Task 2 (inline in command) |
| `promote-voice` copies scenes + audio to parent | Task 3 |
| `promote-voice` updates parent context.json | Task 3 |
| `promote-voice` deletes stale raw.mp4 so ComposeStage re-concatenates | Task 3 (`_do_promote`) |
| `promote-voice` errors cleanly without `parent_project_id` | Task 3 |
| `voice-variant` skill with autonomy contract | Task 4 |
| Skill triggers, P/D/K handling, promote command | Task 4 |

All spec requirements covered. No gaps found.
