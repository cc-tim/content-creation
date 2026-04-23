from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectInfo:
    project_id: str
    status: str
    title: str | None
    locale: str
    niche: str | None
    source_url: str | None
    youtube_video_id: str | None
    published_at: str | None
    has_video: bool
    final_video_url_path: str | None
    tags: list[str] = field(default_factory=list)


def scan_projects(output_dir: Path) -> list[ProjectInfo]:
    projects_dir = output_dir / "projects"
    if not projects_dir.exists():
        return []

    ctx_files = sorted(
        projects_dir.glob("*/context.json"),
        key=lambda p: _sort_key(p.parent.name),
        reverse=True,
    )

    results: list[ProjectInfo] = []
    for ctx_file in ctx_files:
        project_dir = ctx_file.parent
        try:
            ctx = json.loads(ctx_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        meta: dict[str, object] = {}
        meta_file = project_dir / "metadata.json"
        if meta_file.exists():
            with contextlib.suppress(json.JSONDecodeError, OSError):
                meta = json.loads(meta_file.read_text())

        locale: str = ctx.get("locale", "")
        final_mp4 = _find_final_video(project_dir, locale)
        has_video = final_mp4 is not None
        final_video_url_path: str | None = None
        if final_mp4 is not None:
            final_video_url_path = "/output/" + str(final_mp4.relative_to(output_dir))

        results.append(
            ProjectInfo(
                project_id=project_dir.name,
                status=_derive_status(ctx, project_dir, locale),
                title=meta.get("title"),  # type: ignore[arg-type]
                locale=locale,
                niche=ctx.get("niche"),
                source_url=ctx.get("source_url"),
                youtube_video_id=ctx.get("youtube_video_id"),
                published_at=ctx.get("published_at"),
                has_video=has_video,
                final_video_url_path=final_video_url_path,
                tags=meta.get("tags", []),  # type: ignore[arg-type]
            )
        )

    return results


def _derive_status(ctx: dict[str, object], project_dir: Path, locale: str) -> str:
    if ctx.get("youtube_video_id"):
        return "published"
    if _find_final_video(project_dir, locale) is not None:
        return "rendered"
    if (project_dir / "storyboard.json").exists():
        return "storyboard"
    if (project_dir / "knowledge.json").exists():
        return "analyzed"
    if (project_dir / "source" / "video.mp4").exists():
        return "acquired"
    return "new"


def _find_final_video(project_dir: Path, locale: str) -> Path | None:
    if not locale:
        return None
    compose_dir = project_dir / "compose"
    if not compose_dir.exists():
        return None
    specific = compose_dir / f"final_{locale}.mp4"
    return specific if specific.exists() else None


def _sort_key(project_id: str) -> tuple[int, str]:
    parts = project_id.split("_", 1)
    try:
        return (int(parts[0]), parts[1] if len(parts) > 1 else "")
    except ValueError:
        return (0, project_id)
