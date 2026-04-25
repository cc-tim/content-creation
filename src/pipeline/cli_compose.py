from __future__ import annotations

import asyncio
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


def _resolve_work_dir(project_id: int) -> Path:
    config = PipelineConfig()
    return config.OUTPUT_DIR / "projects" / str(project_id)


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
    scenes: list[str] = typer.Option(..., "--scene", help="Scene ID to invalidate (repeat for multiple)"),
) -> None:
    """Delete named scene finals and re-run compose (only those scenes re-render)."""
    work_dir = _resolve_work_dir(project_id)
    scenes_dir = work_dir / "compose" / "scenes"
    for scene_id in scenes:
        for suffix in ("_final.mp4", "_final_no_overlay.mp4"):
            p = scenes_dir / f"{scene_id}{suffix}"
            if p.exists():
                p.unlink()
                logger.info("compose.rescene.deleted", path=str(p))
    typer.echo(f"Invalidated: {', '.join(scenes)} — re-rendering...")
    ctx = PipelineContext.load(work_dir / "context.json")
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
        "subtitles_no_overlay",
        "--variant",
        help=f"Variant to rebuild from raws. One of: {', '.join(_VARIANTS)}",
    ),
) -> None:
    """Re-burn subtitles from existing raw.mp4 / raw_no_overlay.mp4 without re-rendering scenes."""
    work_dir = _resolve_work_dir(project_id)
    ctx = PipelineContext.load(work_dir / "context.json")
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

    _REBURN_MAP = {
        "subtitles": (raw, compose_dir / f"final_{locale}_subtitles.mp4"),
        "subtitles_no_overlay": (raw_no_ov, compose_dir / f"final_{locale}_subtitles_no_overlay.mp4"),
    }

    if variant not in _REBURN_MAP:
        typer.echo(
            f"reburn only supports subtitle variants. Got '{variant}'. "
            f"Choose from: {', '.join(_REBURN_MAP)}",
            err=True,
        )
        raise typer.Exit(code=1)

    src, dst = _REBURN_MAP[variant]
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
