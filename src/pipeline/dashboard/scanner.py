from __future__ import annotations

import contextlib
import json
import re
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
    video_variants: list[dict[str, str]]
    final_video_url_path: str | None
    tags: list[str] = field(default_factory=list)
    session_logs: list[dict[str, str]] = field(default_factory=list)
    scenes: list[dict[str, object]] = field(default_factory=list)


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
        variants = _find_all_final_videos(project_dir, locale)
        has_video = len(variants) > 0
        video_variants = [
            {"label": label, "url": "/output/" + str(path.relative_to(output_dir))}
            for label, path in variants
        ]

        session_logs: list[dict[str, str]] = []
        sessions_file = project_dir / "sessions.json"
        if sessions_file.exists():
            with contextlib.suppress(json.JSONDecodeError, OSError):
                session_logs = json.loads(sessions_file.read_text())

        scenes: list[dict[str, object]] = []
        scenes_file = project_dir / "compose" / "scenes.json"
        if scenes_file.exists():
            with contextlib.suppress(json.JSONDecodeError, OSError):
                scenes = json.loads(scenes_file.read_text(encoding="utf-8"))
        elif (project_dir / "storyboard.json").exists():
            scenes = _estimate_scenes_from_storyboard(project_dir / "storyboard.json")

        if scenes:
            srt_path = project_dir / "audio" / f"subtitles_{locale}.srt"
            srt_entries = _parse_srt(srt_path)
            if srt_entries:
                _attach_subtitles(scenes, srt_entries)

        final_video_url_path = video_variants[0]["url"] if video_variants else None

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
                video_variants=video_variants,
                final_video_url_path=final_video_url_path,
                tags=meta.get("tags", []),  # type: ignore[arg-type]
                session_logs=session_logs,
                scenes=scenes,
            )
        )

    return results


def _derive_status(ctx: dict[str, object], project_dir: Path, locale: str) -> str:
    if ctx.get("youtube_video_id"):
        return "published"
    if _find_all_final_videos(project_dir, locale):
        return "rendered"
    if (project_dir / "storyboard.json").exists():
        return "storyboard"
    if (project_dir / "knowledge.json").exists():
        return "analyzed"
    if (project_dir / "source" / "video.mp4").exists():
        return "acquired"
    return "new"


def _find_all_final_videos(project_dir: Path, locale: str) -> list[tuple[str, Path]]:
    if not locale:
        return []
    compose_dir = project_dir / "compose"
    if not compose_dir.exists():
        return []
    prefix = f"final_{locale}"
    results = []
    for path in sorted(compose_dir.glob(f"{prefix}*.mp4")):
        suffix = path.stem[len(prefix) :].lstrip("_")
        label = suffix or "final"
        results.append((label, path))
    # canonical "final" variant first
    results.sort(key=lambda x: (x[0] != "final", x[0]))
    return results


def _estimate_scenes_from_storyboard(sb_path: Path) -> list[dict[str, object]]:
    with contextlib.suppress(json.JSONDecodeError, OSError):
        data = json.loads(sb_path.read_text(encoding="utf-8"))
        start = 0.0
        result: list[dict[str, object]] = []
        for scene in data.get("scenes", []):
            dur = float(scene.get("narration_est_sec", 0)) + float(scene.get("pause_after_sec", 0))
            result.append(
                {
                    "id": scene["id"],
                    "section": scene.get("section", ""),
                    "start_sec": start,
                    "duration_sec": dur,
                    "narration": scene.get("narration", ""),
                }
            )
            start += dur
        return result
    return []


def _srt_timestamp_to_sec(ts: str) -> float:
    """Convert SRT timestamp HH:MM:SS,mmm to seconds."""
    m = re.fullmatch(r"(\d+):(\d{2}):(\d{2})[,.](\d+)", ts.strip())
    if not m:
        return 0.0
    h, mn, s, ms = int(m[1]), int(m[2]), int(m[3]), int(m[4])
    return h * 3600 + mn * 60 + s + ms / 1000.0


def _parse_srt(path: Path) -> list[tuple[float, float, str]]:
    """Return list of (start_sec, end_sec, text) from an SRT file."""
    entries: list[tuple[float, float, str]] = []
    with contextlib.suppress(OSError):
        blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip())
        for block in blocks:
            lines = block.strip().splitlines()
            if len(lines) < 3:
                continue
            arrow = next((i for i, l in enumerate(lines) if "-->" in l), None)
            if arrow is None:
                continue
            parts = lines[arrow].split("-->")
            start = _srt_timestamp_to_sec(parts[0])
            end = _srt_timestamp_to_sec(parts[1])
            text = " ".join(l.strip() for l in lines[arrow + 1:] if l.strip())
            if text:
                entries.append((start, end, text))
    return entries


def _attach_subtitles(
    scenes: list[dict[str, object]],
    srt_entries: list[tuple[float, float, str]],
) -> list[dict[str, object]]:
    """Add a 'subtitle' key to each scene dict with matching SRT lines joined."""
    for i, scene in enumerate(scenes):
        start = float(scene["start_sec"])
        dur = float(scene.get("duration_sec", 0))
        end = start + dur if dur > 0 else (
            float(scenes[i + 1]["start_sec"]) if i + 1 < len(scenes) else start + 9999
        )
        lines = [text for s, e, text in srt_entries if s >= start and s < end]
        scene["subtitle"] = " ".join(lines)
    return scenes


def _sort_key(project_id: str) -> tuple[int, str]:
    parts = project_id.split("_", 1)
    try:
        return (int(parts[0]), parts[1] if len(parts) > 1 else "")
    except ValueError:
        return (0, project_id)
