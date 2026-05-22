from __future__ import annotations

from pathlib import Path

import typer

from pipeline.config import PipelineConfig
from pipeline.style.manifest import build_manifest

style_app = typer.Typer(name="style", help="Manage style elements on a project.")

_cfg = PipelineConfig()


@style_app.callback()
def _callback() -> None:
    """Manage style elements on a project."""


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
