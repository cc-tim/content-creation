from __future__ import annotations

import contextlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    updated_at: str | None
    has_video: bool
    video_variants: list[dict[str, str]]
    final_video_url_path: str | None
    tags: list[str] = field(default_factory=list)
    session_logs: list[dict[str, str]] = field(default_factory=list)
    scenes: list[dict[str, object]] = field(default_factory=list)
    transitions: list[dict[str, object]] = field(default_factory=list)
    intro_transition: dict[str, object] | None = None
    theme: dict[str, object] = field(default_factory=dict)
    render_freshness: dict[str, object] = field(default_factory=dict)


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
                raw: list[dict[str, str]] = json.loads(sessions_file.read_text())
                # Deduplicate by session_id, keeping the entry with the latest timestamp
                seen: dict[str, dict[str, str]] = {}
                for entry in raw:
                    sid = entry.get("session_id", "")
                    if sid and seen.get(sid, {}).get("timestamp", "") <= entry.get("timestamp", ""):
                        seen[sid] = entry
                    elif not sid:
                        session_logs.append(entry)
                session_logs = list(seen.values())

        scenes: list[dict[str, object]] = []
        storyboard_data = _load_json(project_dir / "storyboard.json")
        scenes_file = project_dir / "compose" / "scenes.json"
        if scenes_file.exists():
            with contextlib.suppress(json.JSONDecodeError, OSError):
                scenes = json.loads(scenes_file.read_text(encoding="utf-8"))
        elif storyboard_data:
            scenes = _estimate_scenes_from_storyboard_data(storyboard_data)

        if scenes and storyboard_data:
            _attach_storyboard_scene_metadata(scenes, storyboard_data)

        if scenes:
            srt_path = project_dir / "audio" / f"subtitles_{locale}.srt"
            srt_entries = _parse_srt(srt_path)
            if srt_entries:
                _attach_subtitles(scenes, srt_entries)

        final_video_url_path = video_variants[0]["url"] if video_variants else None

        # Extract updated_at from context.json mtime
        try:
            mtime = ctx_file.stat().st_mtime
            updated_at = datetime.fromtimestamp(mtime, tz=UTC).isoformat()
        except OSError:
            updated_at = None

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
                updated_at=updated_at,
                has_video=has_video,
                video_variants=video_variants,
                final_video_url_path=final_video_url_path,
                tags=meta.get("tags", []),  # type: ignore[arg-type]
                session_logs=session_logs,
                scenes=scenes,
                transitions=_transition_summaries(storyboard_data),
                intro_transition=_intro_transition_summary(storyboard_data),
                theme=storyboard_data.get("theme", {}) if storyboard_data else {},
                render_freshness=_render_freshness(project_dir),
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


def _load_json(path: Path) -> dict[str, object]:
    with contextlib.suppress(json.JSONDecodeError, OSError):
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    return {}


def _estimate_scenes_from_storyboard_data(data: dict[str, object]) -> list[dict[str, object]]:
    start = 0.0
    result: list[dict[str, object]] = []
    scenes = data.get("scenes", [])
    if not isinstance(scenes, list):
        return []
    for scene in scenes:
        if not isinstance(scene, dict) or not scene.get("id"):
            continue
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


def _attach_storyboard_scene_metadata(
    scenes: list[dict[str, object]],
    storyboard: dict[str, object],
) -> None:
    storyboard_scenes = storyboard.get("scenes", [])
    if not isinstance(storyboard_scenes, list):
        return
    by_id = {
        str(scene.get("id")): scene
        for scene in storyboard_scenes
        if isinstance(scene, dict) and scene.get("id")
    }
    for scene in scenes:
        source = by_id.get(str(scene.get("id") or ""))
        if not isinstance(source, dict):
            continue
        visual = source.get("visual")
        if not isinstance(visual, dict):
            continue
        camera_motion = visual.get("camera_motion")
        if isinstance(camera_motion, dict):
            scene["camera_motion"] = camera_motion


def _transition_summaries(storyboard: dict[str, object]) -> list[dict[str, object]]:
    transitions = storyboard.get("transitions", []) if storyboard else []
    if not isinstance(transitions, list):
        return []
    out: list[dict[str, object]] = []
    for item in transitions:
        if not isinstance(item, dict):
            continue
        out.append({
            "from": item.get("from"),
            "to": item.get("to"),
            "style": item.get("style", "none"),
            "duration_sec": item.get("duration_sec", 0),
            "page_count": item.get("page_count"),
            "sfx": item.get("sfx"),
            "renderer_mode": _renderer_mode_for_transition(item),
            "asset_path": item.get("asset_path"),
            "asset_source": item.get("asset_source"),
            "asset_source_url": item.get("asset_source_url"),
            "asset_license": item.get("asset_license"),
            "asset_notes": item.get("asset_notes"),
            "asset_warning": _transition_asset_warning(
                renderer_mode=_renderer_mode_for_transition(item),
                asset_path=item.get("asset_path"),
                asset_source=item.get("asset_source"),
                asset_license=item.get("asset_license"),
                asset_notes=item.get("asset_notes"),
            ),
        })
    return out


def _intro_transition_summary(storyboard: dict[str, object]) -> dict[str, object] | None:
    theme = storyboard.get("theme", {}) if storyboard else {}
    if not isinstance(theme, dict):
        return None
    style = theme.get("intro_transition_style") or ""
    if not style:
        return None
    return {
        "style": style,
        "duration_sec": theme.get("intro_transition_duration_sec") or "0.9",
        "page_count": theme.get("intro_transition_page_count") or "2",
        "renderer_mode": _renderer_mode_for_intro(theme),
        "asset_path": theme.get("intro_transition_asset_path") or None,
        "asset_source": theme.get("intro_transition_asset_source") or None,
        "asset_source_url": theme.get("intro_transition_asset_source_url") or None,
        "asset_license": theme.get("intro_transition_asset_license") or None,
        "asset_notes": theme.get("intro_transition_asset_notes") or None,
        "asset_warning": _transition_asset_warning(
            renderer_mode=_renderer_mode_for_intro(theme),
            asset_path=theme.get("intro_transition_asset_path"),
            asset_source=theme.get("intro_transition_asset_source"),
            asset_license=theme.get("intro_transition_asset_license"),
            asset_notes=theme.get("intro_transition_asset_notes"),
        ),
    }


def _render_freshness(project_dir: Path) -> dict[str, object]:
    storyboard = project_dir / "storyboard.json"
    explainer = project_dir / "source" / "explainer.md"
    compose_dir = project_dir / "compose"
    contract_paths = [p for p in (storyboard, explainer) if p.exists()]
    render_paths: list[Path] = []
    for pattern in ("raw*.mp4", "final*.mp4", "transitions/*.mp4"):
        render_paths.extend(compose_dir.glob(pattern))

    newest_contract = max((p.stat().st_mtime for p in contract_paths), default=0.0)
    newest_render = max((p.stat().st_mtime for p in render_paths), default=0.0)
    newest_transition = max(
        (p.stat().st_mtime for p in (compose_dir / "transitions").glob("*.mp4")),
        default=0.0,
    )
    warnings: list[str] = []
    if newest_contract and newest_render and newest_contract > newest_render:
        warnings.append("Storyboard or explainer changed after final render. Recompose needed.")
    if storyboard.exists() and newest_transition and storyboard.stat().st_mtime > newest_transition:
        warnings.append("Storyboard changed after transition clips. Recompose transitions.")
    return {
        "stale": bool(warnings),
        "warnings": warnings,
        "newest_contract_mtime": newest_contract or None,
        "newest_render_mtime": newest_render or None,
        "newest_transition_mtime": newest_transition or None,
    }


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
            arrow = next((i for i, line in enumerate(lines) if "-->" in line), None)
            if arrow is None:
                continue
            parts = lines[arrow].split("-->")
            start = _srt_timestamp_to_sec(parts[0])
            end = _srt_timestamp_to_sec(parts[1])
            text = " ".join(line.strip() for line in lines[arrow + 1:] if line.strip())
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


def _renderer_mode_for_transition(item: dict[str, object]) -> str:
    explicit = str(item.get("renderer_mode") or "")
    if explicit:
        return explicit
    if item.get("style") == "stock-book-page-turn":
        return "licensed_clip"
    return "generated"


def _renderer_mode_for_intro(theme: dict[str, object]) -> str:
    explicit = str(theme.get("intro_transition_renderer_mode") or "")
    if explicit:
        return explicit
    if theme.get("intro_transition_style") == "stock-book-page-turn":
        return "licensed_clip"
    return "generated"


def _transition_asset_warning(
    *,
    renderer_mode: str,
    asset_path: object,
    asset_source: object,
    asset_license: object,
    asset_notes: object,
) -> str | None:
    if renderer_mode == "generated" and not asset_path:
        return None
    joined = " ".join(
        str(value)
        for value in (asset_path, asset_source, asset_license, asset_notes)
        if value
    ).lower()
    if "preview" in joined or "watermark" in joined:
        return "Preview or watermarked stock asset noted. Replace it before publish."
    if not any((asset_source, asset_license, asset_notes)):
        return "Stock transition is missing source or license notes."
    return None
