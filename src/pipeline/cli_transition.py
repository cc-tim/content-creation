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
