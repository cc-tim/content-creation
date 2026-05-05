from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from pipeline.config import PipelineConfig
from pipeline.session_log import SessionEntry, append_session, new_session_id
from pipeline.storyboard import Storyboard

overlay_app = typer.Typer(name="overlay", help="Per-scene overlay text commands")


@overlay_app.callback()
def _main() -> None:
    """Per-scene overlay text commands."""


def _resolve_work_dir(project_id: int) -> Path:
    return PipelineConfig().OUTPUT_DIR / "projects" / str(project_id)


def _load_storyboard(project_id: int) -> tuple[Path, Storyboard]:
    work = _resolve_work_dir(project_id)
    sb_path = work / "storyboard.json"
    if not sb_path.exists():
        typer.echo(f"storyboard.json not found at {sb_path}", err=True)
        raise typer.Exit(code=1)
    return sb_path, Storyboard.load(sb_path)


@overlay_app.command("set")
def set_overlay(
    project_id: int = typer.Option(..., "--project-id"),
    scene: str = typer.Option(..., "--scene", help="Scene id (e.g. s9)"),
    text: str = typer.Option(..., "--text", help="Overlay text"),
) -> None:
    """Set the overlay text on the named scene. Preserves other overlay keys.

    Mutates storyboard state only. Run `pipeline compose rescene --scene <id>`
    afterwards to re-render the scene clip with the new overlay.
    """
    sb_path, sb = _load_storyboard(project_id)
    target = sb.get_scene(scene)
    if target is None:
        typer.echo(f"Scene {scene!r} not found in storyboard", err=True)
        raise typer.Exit(code=1)

    existing = dict(target.overlay) if target.overlay else {}
    existing["text"] = text
    target.overlay = existing
    sb.save(sb_path)

    summary = f"overlay set {scene}: {text[:40]}"
    typer.echo(summary)
    work = _resolve_work_dir(project_id)
    append_session(
        work,
        SessionEntry(
            session_id=new_session_id(),
            timestamp=datetime.now().isoformat(timespec="seconds"),
            command=f"overlay set --scene {scene} --text {text!r}",
            summary=summary,
        ),
    )
