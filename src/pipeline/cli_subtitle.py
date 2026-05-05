from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from pipeline.config import PipelineConfig
from pipeline.session_log import SessionEntry, append_session, new_session_id
from pipeline.storyboard import Storyboard

subtitle_app = typer.Typer(name="subtitle", help="Per-scene subtitle override commands")


@subtitle_app.callback()
def _main() -> None:
    """Per-scene subtitle override commands."""


def _resolve_work_dir(project_id: int) -> Path:
    return PipelineConfig().OUTPUT_DIR / "projects" / str(project_id)


def _load_storyboard(project_id: int) -> tuple[Path, Storyboard]:
    work = _resolve_work_dir(project_id)
    sb_path = work / "storyboard.json"
    if not sb_path.exists():
        typer.echo(f"storyboard.json not found at {sb_path}", err=True)
        raise typer.Exit(code=1)
    return sb_path, Storyboard.load(sb_path)


@subtitle_app.command("set")
def set_subtitle(
    project_id: int = typer.Option(..., "--project-id"),
    scene: str = typer.Option(..., "--scene", help="Scene id (e.g. s9)"),
    text: str = typer.Option(..., "--text", help="Subtitle text override"),
) -> None:
    """Write a subtitle_override on the named scene. Idempotent.

    The override mutates storyboard state only. Run `pipeline compose reburn`
    afterwards to re-burn subtitles into the final video.
    """
    sb_path, sb = _load_storyboard(project_id)
    target = sb.get_scene(scene)
    if target is None:
        typer.echo(f"Scene {scene!r} not found in storyboard", err=True)
        raise typer.Exit(code=1)

    target.subtitle_override = text
    sb.save(sb_path)

    summary = f"subtitle set {scene}: {text[:40]}"
    typer.echo(summary)
    work = _resolve_work_dir(project_id)
    append_session(
        work,
        SessionEntry(
            session_id=new_session_id(),
            timestamp=datetime.now().isoformat(timespec="seconds"),
            command=f"subtitle set --scene {scene} --text {text!r}",
            summary=summary,
        ),
    )
