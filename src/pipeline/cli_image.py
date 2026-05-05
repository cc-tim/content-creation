from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from pipeline.config import PipelineConfig
from pipeline.session_log import SessionEntry, append_session, new_session_id
from pipeline.storyboard import Storyboard

image_app = typer.Typer(name="image", help="Per-scene image regen commands")


@image_app.callback()
def _main() -> None:
    """Per-scene image regen commands."""


_VALID_TIERS = {"draft", "production"}


def _resolve_work_dir(project_id: int) -> Path:
    return PipelineConfig().OUTPUT_DIR / "projects" / str(project_id)


def _load_storyboard(project_id: int) -> tuple[Path, Storyboard]:
    work = _resolve_work_dir(project_id)
    sb_path = work / "storyboard.json"
    if not sb_path.exists():
        typer.echo(f"storyboard.json not found at {sb_path}", err=True)
        raise typer.Exit(code=1)
    return sb_path, Storyboard.load(sb_path)


def _delete_image_cache_for_scene(work_dir: Path, scene_id: str) -> None:
    """Delete cached scene image and clips before the next compose rescene."""
    images_dir = work_dir / "images"
    if images_dir.exists():
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            path = images_dir / f"{scene_id}{ext}"
            if path.exists():
                path.unlink()

    scenes_dir = work_dir / "compose" / "scenes"
    if scenes_dir.exists():
        for suffix in ("_final.mp4", "_final_no_overlay.mp4"):
            path = scenes_dir / f"{scene_id}{suffix}"
            if path.exists():
                path.unlink()


@image_app.command("regen")
def regen(
    project_id: int = typer.Option(..., "--project-id"),
    scene: str = typer.Option(..., "--scene", help="Scene id (e.g. s9)"),
    prompt: str = typer.Option(..., "--prompt", help="New image generation prompt"),
    tier: str = typer.Option(..., "--tier", help=f"One of: {', '.join(sorted(_VALID_TIERS))}"),
) -> None:
    """Update a scene's image prompt + tier and clear its image cache.

    Mutates storyboard + cache only. Run `pipeline compose rescene --scene <id>`
    afterwards to actually regenerate the image and recompose the scene.
    """
    if tier not in _VALID_TIERS:
        typer.echo(
            f"Unknown tier {tier!r}. Choose from: {', '.join(sorted(_VALID_TIERS))}",
            err=True,
        )
        raise typer.Exit(code=1)

    sb_path, sb = _load_storyboard(project_id)
    target = sb.get_scene(scene)
    if target is None:
        typer.echo(f"Scene {scene!r} not found in storyboard", err=True)
        raise typer.Exit(code=1)

    visual = dict(target.visual) if target.visual else {}
    visual["prompt"] = prompt
    visual["tier"] = tier
    target.visual = visual
    sb.save(sb_path)

    work = _resolve_work_dir(project_id)
    _delete_image_cache_for_scene(work, scene)

    summary = f"image regen {scene}: tier={tier} prompt={prompt[:40]}"
    typer.echo(summary)
    append_session(
        work,
        SessionEntry(
            session_id=new_session_id(),
            timestamp=datetime.now().isoformat(timespec="seconds"),
            command=f"image regen --scene {scene} --prompt {prompt!r} --tier {tier}",
            summary=summary,
        ),
    )
