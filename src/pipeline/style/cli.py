from __future__ import annotations

import json
from pathlib import Path

import typer

from pipeline.config import PipelineConfig
from pipeline.style.log import append_log
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


@style_app.command("remove")
def remove_element(
    project_id: str = typer.Option(..., "--project-id"),
    element_id: str = typer.Argument(..., help="Element ID (from 'style list')"),
    rationale: str = typer.Option("", "--rationale", help="Reason for removal"),
) -> None:
    """Remove a style element from a project."""
    sb_path = _storyboard_path(project_id)
    data = json.loads(sb_path.read_text(encoding="utf-8"))
    theme = data.setdefault("theme", {})

    manifest = build_manifest(sb_path)
    el = next((e for e in manifest.elements if e.id == element_id), None)

    if el is None:
        typer.echo(f"Element {element_id!r} not found on this project.", err=True)
        raise typer.Exit(1)

    if el.theme_key not in theme:
        typer.echo(f"Element {element_id!r} already absent from theme.", err=True)
        raise typer.Exit(1)

    del theme[el.theme_key]
    sb_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    append_log(_project_dir(project_id), "remove", element_id, rationale)

    affected = len(data.get("scenes", []))
    if el.kind == "frame":
        typer.echo(
            f"Removed {element_id}. {affected} scene(s) will lose the frame on next render.\n"
            f"Run: uv run pipeline compose reburn --project-id {project_id}"
        )
    else:
        typer.echo(f"Removed {element_id}. Logged to style_log.json.")


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
    data = json.loads(sb_path.read_text(encoding="utf-8"))
    theme = data.setdefault("theme", {})
    theme[_KIND_TO_THEME_KEY[kind]] = value
    sb_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    append_log(_project_dir(project_id), "add", element_id, rationale)
    typer.echo(f"Added {element_id} ({kind}={value!r}). Logged to style_log.json.")
