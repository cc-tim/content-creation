from __future__ import annotations

import asyncio
import shutil
from datetime import datetime
from pathlib import Path

import structlog
import typer

from pipeline.config import PipelineConfig
from pipeline.session_log import SessionEntry, append_session, new_session_id
from pipeline.stages.base import PipelineContext
from pipeline.stages.compose import ComposeStage, _burn_subtitle_pass

logger = structlog.get_logger()
compose_app = typer.Typer(name="compose", help="Compose iteration commands")

_VARIANTS = ("plain", "no_overlay", "subtitles", "subtitles_no_overlay")
_VARIANT_SUFFIXES = {
    "plain": "",
    "no_overlay": "_no_overlay",
    "subtitles": "_subtitles",
    "subtitles_no_overlay": "_subtitles_no_overlay",
}


def _resolve_work_dir(project_id: int) -> Path:
    config = PipelineConfig()
    return config.OUTPUT_DIR / "projects" / str(project_id)


def _resolve_projects_dir() -> Path:
    config = PipelineConfig()
    return config.OUTPUT_DIR / "projects"


@compose_app.command("set-variant")
def set_variant(
    project_id: int = typer.Option(..., "--project-id"),
    variant: str = typer.Option(..., "--variant", help=f"One of: {', '.join(_VARIANTS)}"),
) -> None:
    """Lock the preferred output variant in context.json."""
    if variant not in _VARIANTS:
        typer.echo(f"Unknown variant '{variant}'. Choose from: {', '.join(_VARIANTS)}", err=True)
        raise typer.Exit(code=1)
    work_dir = _resolve_work_dir(project_id)
    ctx = PipelineContext.load(work_dir / "context.json")
    ctx.preferred_variant = variant
    ctx.save()
    typer.echo(f"preferred_variant → {variant}")
    append_session(work_dir, SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"compose set-variant --variant {variant}",
        summary=f"preferred_variant → {variant}",
    ))


@compose_app.command("rescene")
def rescene(
    project_id: int = typer.Option(..., "--project-id"),
    scenes: list[str] = typer.Option(
        ..., "--scene", help="Scene ID to invalidate (repeat for multiple)"
    ),
) -> None:
    """Delete named scene finals and re-run compose (only those scenes re-render)."""
    work_dir = _resolve_work_dir(project_id)
    from pipeline.composer.image_history import purge_old
    purge_old(work_dir / "compose" / "scenes")
    scenes_dir = work_dir / "compose" / "scenes"
    for scene_id in scenes:
        for suffix in ("_final.mp4", "_final_no_overlay.mp4"):
            p = scenes_dir / f"{scene_id}{suffix}"
            if p.exists():
                p.unlink()
                logger.info("compose.rescene.deleted", path=str(p))
    ctx = PipelineContext.load(work_dir / "context.json")
    if ctx.preferred_variant:
        typer.echo(
            f"Invalidated: {', '.join(scenes)} — re-rendering... [focused: {ctx.preferred_variant}]"
        )
    else:
        typer.echo(f"Invalidated: {', '.join(scenes)} — re-rendering... [default: subtitles_no_overlay]")
    scene_list = ", ".join(scenes)
    entry = SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"compose rescene {scene_list}",
    )
    try:
        asyncio.run(ComposeStage().run(ctx))
        entry.stages = ["compose"]
        entry.summary = f"rescene: {scene_list}"
        typer.echo("Done.")
    except Exception as exc:
        entry.outcome = "failed"
        entry.error = str(exc)[:200]
        entry.summary = f"rescene failed: {scene_list}"
        append_session(work_dir, entry)
        raise
    append_session(work_dir, entry)


@compose_app.command("reburn")
def reburn(
    project_id: int = typer.Option(..., "--project-id"),
    variant: str = typer.Option(
        "",
        "--variant",
        help=(
            f"Variant to rebuild from raws. One of: {', '.join(_VARIANTS)}. "
            "Defaults to preferred_variant in context.json, then subtitles_no_overlay."
        ),
    ),
) -> None:
    """Re-burn subtitles from existing raw.mp4 / raw_no_overlay.mp4 without re-rendering scenes."""
    work_dir = _resolve_work_dir(project_id)
    from pipeline.composer.image_history import purge_old
    purge_old(work_dir / "compose" / "scenes")
    ctx = PipelineContext.load(work_dir / "context.json")
    variant = variant or ctx.preferred_variant or "subtitles_no_overlay"
    compose_dir = work_dir / "compose"
    locale = ctx.locale

    if ctx.subtitle_path is None or not ctx.subtitle_path.exists():
        typer.echo("No subtitle file in context — cannot reburn.", err=True)
        raise typer.Exit(code=1)

    from pipeline.storyboard import Storyboard
    theme_dict: dict = {}
    if ctx.storyboard_path and ctx.storyboard_path.exists():
        sb = Storyboard.load(ctx.storyboard_path)
        theme_dict = sb.theme.to_dict()

    raw = compose_dir / "raw.mp4"
    raw_no_ov = compose_dir / "raw_no_overlay.mp4"

    reburn_map = {
        "subtitles": (raw, compose_dir / f"final_{locale}_subtitles.mp4"),
        "subtitles_no_overlay": (
            raw_no_ov,
            compose_dir / f"final_{locale}_subtitles_no_overlay.mp4",
        ),
    }

    if variant not in reburn_map:
        typer.echo(
            f"reburn only supports subtitle variants. Got '{variant}'. "
            f"Choose from: {', '.join(reburn_map)}",
            err=True,
        )
        raise typer.Exit(code=1)

    src, dst = reburn_map[variant]
    if not src.exists():
        typer.echo(f"Raw not found: {src}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Burning subtitles: {src.name} → {dst.name}")
    entry = SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"compose reburn --variant {variant}",
    )
    try:
        _burn_subtitle_pass(src, dst, ctx.subtitle_path, theme_dict)
        entry.summary = f"reburn: {variant}"
        typer.echo(f"Done → {dst}")
    except Exception as exc:
        entry.outcome = "failed"
        entry.error = str(exc)[:200]
        entry.summary = f"reburn failed: {variant}"
        append_session(work_dir, entry)
        raise
    append_session(work_dir, entry)


@compose_app.command("clean")
def clean(
    project_id: int = typer.Option(..., "--project-id"),
    dry_run: bool = typer.Option(False, "--dry-run", help="List files that would be removed without deleting."),
) -> None:
    """Delete final variant files that are not the preferred_variant.

    Keeps the locked preferred_variant final on disk; removes the other three
    to reduce clutter. Safe to re-run — only deletes what exists.
    """
    work_dir = _resolve_work_dir(project_id)
    ctx = PipelineContext.load(work_dir / "context.json")
    preferred = ctx.preferred_variant
    if not preferred:
        typer.echo("No preferred_variant set — nothing to clean. Run set-variant first.", err=True)
        raise typer.Exit(code=1)

    locale = ctx.locale
    compose_dir = work_dir / "compose"
    removed: list[str] = []

    for variant, suffix in _VARIANT_SUFFIXES.items():
        if variant == preferred:
            continue
        path = compose_dir / f"final_{locale}{suffix}.mp4"
        if path.exists():
            if dry_run:
                typer.echo(f"[dry-run] would remove: {path.name}")
            else:
                path.unlink()
                removed.append(path.name)
                logger.info("compose.clean.removed", path=str(path))

    if dry_run:
        return

    if removed:
        typer.echo(f"Removed: {', '.join(removed)}")
        append_session(work_dir, SessionEntry(
            session_id=new_session_id(),
            timestamp=datetime.now().isoformat(timespec="seconds"),
            command=f"compose clean",
            summary=f"clean: removed {', '.join(removed)}",
        ))
    else:
        typer.echo("Nothing to remove.")


def _do_promote(variant_name: str, projects_dir: Path, ask_delete: bool = False) -> None:
    """Copy variant audio + scenes to parent, update parent context, re-compose."""
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

    # 3. Delete stale raw concat files so ComposeStage re-concatenates from new scenes
    for raw_name in ("raw.mp4", "raw_no_overlay.mp4"):
        raw = parent_dir / "compose" / raw_name
        if raw.exists():
            raw.unlink()

    # 4. Patch parent context.json
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

    # 5. Re-run ComposeStage (skips scene re-render since scene files exist; only concatenates + burns)
    typer.echo("Re-composing parent project...")
    asyncio.run(ComposeStage().run(parent_ctx))

    typer.echo(
        f"Promoted. Parent project {variant_ctx.parent_project_id} now uses voice '{variant_ctx.voice_id}'."
    )

    if ask_delete:
        try:
            delete = typer.confirm(f"Delete variant directory '{variant_name}'?", default=False)
        except (EOFError, Exception):
            delete = False
        if delete:
            shutil.rmtree(variant_dir)
            typer.echo(f"Variant deleted: {variant_dir}")


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

    # Copy independent assets
    for name in ("storyboard.json", "knowledge.json", "metadata.json", "thumbnail.png"):
        src = parent_dir / name
        if src.exists():
            shutil.copy2(src, variant_dir / name)

    script_src = parent_dir / "script"
    if script_src.exists():
        shutil.copytree(script_src, variant_dir / "script")

    # Build variant context.json from parent's context with overrides
    parent_ctx = PipelineContext.load(parent_dir / "context.json")

    def _remap(p: Path | None) -> Path | None:
        if p is None:
            return None
        try:
            rel = p.relative_to(parent_dir)
            return variant_dir / rel
        except ValueError:
            return p

    variant_ctx = PipelineContext(
        project_id=int(time.time()),
        source_url=parent_ctx.source_url,
        locale=parent_ctx.locale,
        work_dir=variant_dir,
        niche=parent_ctx.niche,
        video_path=parent_ctx.video_path,
        transcript_path=parent_ctx.transcript_path,
        transcript_text=parent_ctx.transcript_text,
        story_structure=parent_ctx.story_structure,
        knowledge_graph=parent_ctx.knowledge_graph,
        clip_timestamps=parent_ctx.clip_timestamps,
        knowledge_path=_remap(parent_ctx.knowledge_path),
        storyboard_path=_remap(parent_ctx.storyboard_path),
        script_path=_remap(parent_ctx.script_path),
        narration_path=None,
        subtitle_path=None,
        segment_timings=None,
        voice_id=voice,
        final_video_path=None,
        burn_subtitles=parent_ctx.burn_subtitles,
        skip_overlays=parent_ctx.skip_overlays,
        preferred_variant=parent_ctx.preferred_variant,
        youtube_video_id=None,
        thumbnail_uploaded=False,
        disclosure_set=False,
        published_at=None,
        publish_profile=parent_ctx.publish_profile,
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
    typer.echo("  [P] Promote  — copy audio to original, reburn (fast, no scene re-render)")
    typer.echo("  [D] Delete   — discard this variant, keep original as-is")
    typer.echo("  [K] Keep both — decide later")
    try:
        choice = typer.prompt("Choice", default="K").strip().upper()
    except (EOFError, Exception):
        choice = "K"

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


@compose_app.command("history")
def history(
    project_id: int = typer.Option(..., "--project-id"),
    scene: str = typer.Option(..., "--scene"),
) -> None:
    """List image history entries for a scene."""
    from pipeline.composer.image_history import find_history
    work_dir = _resolve_work_dir(project_id)
    scenes_dir = work_dir / "compose" / "scenes"
    entries = find_history(scene, scenes_dir)
    if not entries:
        typer.echo(f"No history for scene '{scene}'")
        return
    now = datetime.now()
    for ts, path in entries:
        age = now - ts
        if age.days:
            age_str = f"{age.days}d ago"
        else:
            age_str = f"{age.seconds // 3600}h ago" if age.seconds >= 3600 else f"{age.seconds // 60}m ago"
        typer.echo(f"  {path.name}  ({age_str})")


@compose_app.command("restore")
def restore(
    project_id: int = typer.Option(..., "--project-id"),
    scene: str = typer.Option(..., "--scene"),
    timestamp: str | None = typer.Option(None, "--timestamp", help="e.g. 20260428T143022"),
) -> None:
    """Restore most-recent (or timestamped) history entry for a scene, then re-render."""
    from pipeline.composer.image_history import restore_scene
    work_dir = _resolve_work_dir(project_id)
    scenes_dir = work_dir / "compose" / "scenes"

    restore_path = restore_scene(scene, scenes_dir, timestamp)
    if restore_path is None:
        typer.echo(f"No history entries for scene '{scene}'", err=True)
        raise typer.Exit(code=1)

    # Clear scene finals so ComposeStage re-renders this scene
    for suffix in ("_final.mp4", "_final_no_overlay.mp4"):
        p = scenes_dir / f"{scene}{suffix}"
        if p.exists():
            p.unlink()

    typer.echo(f"Restored {restore_path.name} — re-rendering scene {scene}...")
    ctx = PipelineContext.load(work_dir / "context.json")
    entry = SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"compose restore --scene {scene}",
    )
    try:
        asyncio.run(ComposeStage().run(ctx))
        entry.summary = f"restore: {scene}"
        typer.echo("Done.")
    except Exception as exc:
        entry.outcome = "failed"
        entry.error = str(exc)[:200]
        entry.summary = f"restore failed: {scene}"
        append_session(work_dir, entry)
        raise
    append_session(work_dir, entry)
