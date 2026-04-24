from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
import typer

from pipeline.config import PipelineConfig
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
    asyncio.run(ComposeStage().run(ctx))
    typer.echo("Done.")


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
    _burn_subtitle_pass(src, dst, ctx.subtitle_path, theme_dict)
    typer.echo(f"Done → {dst}")
