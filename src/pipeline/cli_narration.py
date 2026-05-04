from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from pipeline.config import PipelineConfig
from pipeline.session_log import SessionEntry, append_session, new_session_id
from pipeline.storyboard import NarrationSource, Storyboard

narration_app = typer.Typer(name="narration", help="Per-scene narration source commands")


@narration_app.callback()
def _main() -> None:
    """Per-scene narration source commands."""


_VALID_ENGINES = {"edge", "fish_audio", "prerecorded"}


def _resolve_work_dir(project_id: int) -> Path:
    return PipelineConfig().OUTPUT_DIR / "projects" / str(project_id)


def _load_storyboard(project_id: int) -> tuple[Path, Storyboard]:
    work = _resolve_work_dir(project_id)
    sb_path = work / "storyboard.json"
    if not sb_path.exists():
        typer.echo(f"storyboard.json not found at {sb_path}", err=True)
        raise typer.Exit(code=1)
    return sb_path, Storyboard.load(sb_path)


def _resolve_within_project(project_root: Path, rel_path: str) -> Path:
    """Resolve a project-relative path, refusing any escape via .. or absolute paths.

    Returns the absolute resolved Path. Raises typer.Exit(code=1) on violation.
    """
    candidate = (project_root / rel_path).resolve()
    project_root_resolved = project_root.resolve()
    try:
        candidate.relative_to(project_root_resolved)
    except ValueError:
        typer.echo(
            f"Refusing path {rel_path!r}: resolved outside project tree at {project_root}",
            err=True,
        )
        raise typer.Exit(code=1)
    return candidate


@narration_app.command("set-source")
def set_source(
    project_id: int = typer.Option(..., "--project-id"),
    scene: str = typer.Option(..., "--scene", help="Scene id (e.g. s9)"),
    engine: str = typer.Option(..., "--engine", help=f"One of: {', '.join(sorted(_VALID_ENGINES))}"),
    voice: str | None = typer.Option(
        None, "--voice", help="Registry voice_id (required for engine=edge|fish_audio)"
    ),
    file: str | None = typer.Option(
        None, "--file", help="Project-relative path to a WAV (required for engine=prerecorded)"
    ),
) -> None:
    """Set or replace the narration_source override for a scene. Idempotent."""
    if engine not in _VALID_ENGINES:
        typer.echo(
            f"Unknown narration engine {engine!r}. Choose from: {', '.join(sorted(_VALID_ENGINES))}",
            err=True,
        )
        raise typer.Exit(code=1)

    if engine in ("edge", "fish_audio") and not voice:
        typer.echo(f"engine={engine!r} requires --voice (registry voice_id)", err=True)
        raise typer.Exit(code=1)

    if engine == "prerecorded":
        if not file:
            typer.echo("engine='prerecorded' requires --file (project-relative WAV path)", err=True)
            raise typer.Exit(code=1)
        # Sandbox + existence check.
        project_root = _resolve_work_dir(project_id)
        resolved = _resolve_within_project(project_root, file)
        if not resolved.exists():
            typer.echo(f"File not found: {resolved}", err=True)
            raise typer.Exit(code=1)

    sb_path, sb = _load_storyboard(project_id)
    target = sb.get_scene(scene)
    if target is None:
        typer.echo(f"Scene {scene!r} not found in storyboard", err=True)
        raise typer.Exit(code=1)

    target.narration_source = NarrationSource(
        engine=engine,
        voice=voice,
        file=file,
    )
    sb.save(sb_path)

    descriptor = (
        f"engine={engine}"
        + (f" voice={voice}" if voice else "")
        + (f" file={file}" if file else "")
    )
    summary = f"narration set-source {scene}: {descriptor}"
    typer.echo(summary)
    work = _resolve_work_dir(project_id)
    append_session(work, SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"narration set-source --scene {scene} --engine {engine}"
                + (f" --voice {voice}" if voice else "")
                + (f" --file {file}" if file else ""),
        summary=summary,
    ))
