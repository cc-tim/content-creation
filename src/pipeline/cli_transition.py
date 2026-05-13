from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from pipeline.composer.transitions import (
    MAX_BOOK_PAGE_COUNT,
    SUPPORTED_RENDERER_MODES,
    SUPPORTED_STYLES,
    TransitionConfig,
)
from pipeline.config import PipelineConfig
from pipeline.session_log import SessionEntry, append_session, new_session_id
from pipeline.storyboard import Storyboard, Transition

transition_app = typer.Typer(name="transition", help="Per-seam transition commands")


def _resolve_work_dir(project_id: int | str) -> Path:
    return PipelineConfig().OUTPUT_DIR / "projects" / str(project_id)


def _load_storyboard(project_id: int | str) -> tuple[Path, Storyboard]:
    work = _resolve_work_dir(project_id)
    sb_path = work / "storyboard.json"
    if not sb_path.exists():
        typer.echo(f"storyboard.json not found at {sb_path}", err=True)
        raise typer.Exit(code=1)
    return sb_path, Storyboard.load(sb_path)


def _scene_ids(sb: Storyboard) -> set[str]:
    return {s.id for s in sb.scenes}


def apply_set_transition(
    *,
    project_id: int,
    from_scene: str,
    to_scene: str,
    style: str,
    duration_sec: float,
    sfx: str | None,
    page_count: int | None = None,
    renderer_mode: str | None = None,
    asset_path: str | None = None,
    asset_source: str | None = None,
    asset_source_url: str | None = None,
    asset_license: str | None = None,
    asset_notes: str | None = None,
) -> str:
    """Set or replace a transition on a project's storyboard."""
    if style not in SUPPORTED_STYLES:
        raise ValueError(
            f"Unknown transition style {style!r}. Choose from: "
            f"{', '.join(sorted(SUPPORTED_STYLES))}"
        )
    if renderer_mode is not None and renderer_mode not in SUPPORTED_RENDERER_MODES:
        raise ValueError(
            f"Unknown renderer_mode {renderer_mode!r}. Choose from: "
            f"{', '.join(sorted(SUPPORTED_RENDERER_MODES))}"
        )
    if page_count is not None and not 1 <= page_count <= MAX_BOOK_PAGE_COUNT:
        raise ValueError(f"page_count must be between 1 and {MAX_BOOK_PAGE_COUNT}")
    TransitionConfig(
        style=style,
        duration_sec=duration_sec,
        sfx=sfx,
        page_count=page_count,
        renderer_mode=renderer_mode,
        asset_path=asset_path,
        asset_source=asset_source,
        asset_source_url=asset_source_url,
        asset_license=asset_license,
        asset_notes=asset_notes,
    )
    sb_path, sb = _load_storyboard(project_id)
    ids = _scene_ids(sb)
    if from_scene not in ids:
        raise ValueError(f"Scene {from_scene!r} not found in storyboard")
    if to_scene not in ids:
        raise ValueError(f"Scene {to_scene!r} not found in storyboard")

    sb.transitions = [
        t for t in sb.transitions
        if not (t.from_scene == from_scene and t.to_scene == to_scene)
    ]
    sb.transitions.append(Transition(
        from_scene=from_scene,
        to_scene=to_scene,
        style=style,
        duration_sec=duration_sec,
        sfx=sfx,
        page_count=page_count,
        renderer_mode=renderer_mode or "generated",
        asset_path=asset_path,
        asset_source=asset_source,
        asset_source_url=asset_source_url,
        asset_license=asset_license,
        asset_notes=asset_notes,
    ))
    sb.save(sb_path)

    summary = (
        f"transition {from_scene}→{to_scene}: {style} ({duration_sec}s)"
        + (f" · {page_count}p" if page_count else "")
        + (f" · {renderer_mode}" if renderer_mode and renderer_mode != "generated" else "")
        + (f" · {asset_path}" if asset_path else "")
        + (f" + {sfx}" if sfx else "")
    )
    work = _resolve_work_dir(project_id)
    append_session(work, SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=(
            f"transition set --from {from_scene} --to {to_scene} "
            f"--style {style} --duration {duration_sec}"
            + (f" --page-count {page_count}" if page_count else "")
            + (f" --renderer-mode {renderer_mode}" if renderer_mode else "")
            + (f" --asset-path {asset_path}" if asset_path else "")
            + (f" --asset-source {asset_source}" if asset_source else "")
            + (f" --asset-source-url {asset_source_url}" if asset_source_url else "")
            + (f" --asset-license {asset_license}" if asset_license else "")
            + (f" --asset-notes {asset_notes}" if asset_notes else "")
            + (f" --sfx {sfx}" if sfx else "")
        ),
        summary=summary,
    ))
    return summary


def apply_clear_transition(
    *,
    project_id: int,
    from_scene: str,
    to_scene: str,
) -> str:
    """Remove the transition for a given seam, if any."""
    sb_path, sb = _load_storyboard(project_id)
    before = len(sb.transitions)
    sb.transitions = [
        t for t in sb.transitions
        if not (t.from_scene == from_scene and t.to_scene == to_scene)
    ]
    if len(sb.transitions) == before:
        return f"No transition for {from_scene}→{to_scene}; nothing to clear."
    sb.save(sb_path)
    summary = f"transition {from_scene}→{to_scene}: cleared"
    work = _resolve_work_dir(project_id)
    append_session(work, SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"transition clear --from {from_scene} --to {to_scene}",
        summary=summary,
    ))
    return summary


@transition_app.command("set")
def set_transition(
    project_id: int = typer.Option(..., "--project-id"),
    from_scene: str = typer.Option(..., "--from", help="Source scene id (e.g. s9)"),
    to_scene: str = typer.Option(..., "--to", help="Destination scene id (e.g. s10)"),
    style: str = typer.Option(
        ...,
        "--style",
        help=f"One of: {', '.join(sorted(SUPPORTED_STYLES))}",
    ),
    duration: float = typer.Option(..., "--duration", help="Transition duration in seconds"),
    sfx: str | None = typer.Option(None, "--sfx", help="Optional sound effect path"),
    page_count: int | None = typer.Option(
        None,
        "--page-count",
        help=f"Optional page count for book-page-turn transitions (1-{MAX_BOOK_PAGE_COUNT})",
    ),
    renderer_mode: str | None = typer.Option(
        None,
        "--renderer-mode",
        help=f"Optional renderer mode: {', '.join(sorted(SUPPORTED_RENDERER_MODES))}",
    ),
    asset_path: str | None = typer.Option(None, "--asset-path", help="Optional stock asset path"),
    asset_source: str | None = typer.Option(None, "--asset-source", help="Optional stock source note"),
    asset_source_url: str | None = typer.Option(None, "--asset-source-url", help="Optional stock source URL"),
    asset_license: str | None = typer.Option(None, "--asset-license", help="Optional license note"),
    asset_notes: str | None = typer.Option(None, "--asset-notes", help="Optional stock usage note"),
) -> None:
    """Set or replace a transition between two scenes. Idempotent."""
    try:
        summary = apply_set_transition(
            project_id=project_id,
            from_scene=from_scene,
            to_scene=to_scene,
            style=style,
            duration_sec=duration,
            sfx=sfx,
            page_count=page_count,
            renderer_mode=renderer_mode,
            asset_path=asset_path,
            asset_source=asset_source,
            asset_source_url=asset_source_url,
            asset_license=asset_license,
            asset_notes=asset_notes,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(summary)


@transition_app.command("clear")
def clear_transition(
    project_id: int = typer.Option(..., "--project-id"),
    from_scene: str = typer.Option(..., "--from"),
    to_scene: str = typer.Option(..., "--to"),
) -> None:
    """Remove the transition for a given seam, if any."""
    summary = apply_clear_transition(
        project_id=project_id,
        from_scene=from_scene,
        to_scene=to_scene,
    )
    typer.echo(summary)


@transition_app.command("review")
def review_transition_animation(
    project_id: str | None = typer.Option(
        None,
        "--project-id",
        help="Project id to review from output/projects/<id>.",
    ),
    clip: Path | None = typer.Option(
        None,
        "--clip",
        help="Review one standalone transition/scene clip instead of a project.",
    ),
    label: str = typer.Option("clip", "--label", help="Label for --clip output."),
    first: int = typer.Option(4, "--first", help="Number of transition clips to review."),
    include_scenes: bool = typer.Option(
        False,
        "--include-scenes/--no-include-scenes",
        help="Also review the first scene clips for static-hold or in-scene motion issues.",
    ),
    first_scenes: int = typer.Option(3, "--first-scenes", help="Number of scenes to review."),
    out_dir: Path | None = typer.Option(
        None,
        "--out-dir",
        help="Output directory for review artifacts.",
    ),
    variant: str = typer.Option(
        "no_overlay",
        "--variant",
        help="Scene variant used to resolve transition cache keys: no_overlay or final.",
    ),
    max_samples: int = typer.Option(
        18,
        "--max-samples",
        help="Maximum sampled frames per contact sheet.",
    ),
) -> None:
    """Generate agent-readable animation review artifacts and metrics."""
    from pipeline.composer.animation_review import (
        ReviewTarget,
        review_project,
        review_targets,
    )

    if clip is not None:
        output = out_dir or Path("tmp") / "animation-review"
        reviews = review_targets(
            [ReviewTarget(label, clip, "clip")],
            output,
            max_samples=max_samples,
        )
    else:
        if project_id is None:
            typer.echo("--project-id or --clip is required", err=True)
            raise typer.Exit(code=1)
        project_root = _resolve_work_dir(project_id)
        if not (project_root / "storyboard.json").exists():
            typer.echo(f"storyboard.json not found at {project_root}", err=True)
            raise typer.Exit(code=1)
        reviews = review_project(
            project_root,
            first=first,
            include_scenes=include_scenes,
            first_scenes=first_scenes,
            out_dir=out_dir,
            variant=variant,
            max_samples=max_samples,
        )

    summary_path = Path(reviews[0].artifacts["metrics_json"]).parents[1] / "summary.md"
    typer.echo(f"animation review: {len(reviews)} clip(s)")
    typer.echo(f"summary: {summary_path}")
    for review in reviews:
        finding_count = len(review.findings)
        typer.echo(
            f"{review.label}: {review.agent_review_status} "
            f"({finding_count} finding{'s' if finding_count != 1 else ''})"
        )
