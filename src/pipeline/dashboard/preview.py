"""Build lightweight Telegram previews for dashboard mutation results."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pipeline.composer.base import get_resolution
from pipeline.composer.transitions import TransitionConfig, render_transition, transition_cache_key
from pipeline.storyboard import Storyboard
from pipeline.utils.ffmpeg import run_ffmpeg

PreviewKind = Literal["photo", "video", "text_diff"]


@dataclass(frozen=True)
class Preview:
    kind: PreviewKind
    path: Path | None = None
    body: str = ""
    caption: str = ""


def build_preview(
    *,
    verb: str,
    args: dict[str, Any],
    project_root: Path,
    old_text: str | None = None,
) -> Preview:
    if verb in {"subtitle set", "overlay set", "narration regen"}:
        return Preview(
            kind="text_diff",
            body=_format_text_diff(old=old_text or "", new=str(args.get("text", ""))),
        )

    if verb == "image regen":
        scene = args.get("scene")
        candidate = project_root / "images" / "scenes" / f"{scene}.png"
        if candidate.exists():
            return Preview(kind="photo", path=candidate, caption=f"image {scene} regenerated")
        return Preview(kind="text_diff", body=f"image {scene} regenerated (artifact pending)")

    if verb in {"transition set", "transition clear"}:
        from_scene = args.get("from")
        to_scene = args.get("to")
        candidate = project_root / "compose" / f"seam_{from_scene}_{to_scene}.mp4"
        if candidate.exists():
            return Preview(
                kind="video",
                path=candidate,
                caption=f"transition {from_scene} to {to_scene} preview",
            )
        return Preview(
            kind="text_diff",
            body=f"transition {from_scene} to {to_scene} updated (recompose pending)",
        )

    if verb == "narration set-source":
        return Preview(
            kind="text_diff",
            body=f"narration source for {args.get('scene')} => {args.get('engine')}",
        )

    return Preview(kind="text_diff", body=f"{verb} applied")


def _format_text_diff(*, old: str, new: str) -> str:
    return f"BEFORE: {_truncate(old)}\nAFTER:  {_truncate(new)}"


def _truncate(value: str, limit: int = 200) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def build_project_preview_manifest(project_root: Path) -> dict[str, list[dict[str, str]]]:
    storyboard_path = project_root / "storyboard.json"
    if not storyboard_path.exists():
        return {"scenes": [], "transitions": []}

    storyboard = Storyboard.load(storyboard_path)
    frame_style = storyboard.theme.frame_style or ""
    frame_suffix = f"_{frame_style}" if frame_style else ""
    scenes_dir = project_root / "compose" / "scenes"
    previews_dir = project_root / "compose" / "previews"

    scene_items: list[dict[str, str]] = []
    for scene in storyboard.scenes:
        scene_video = scenes_dir / f"{scene.id}_final_no_overlay{frame_suffix}.mp4"
        if not scene_video.exists():
            scene_video = scenes_dir / f"{scene.id}_final{frame_suffix}.mp4"
        if not scene_video.exists():
            continue
        preview_path = previews_dir / "scenes" / f"{scene.id}.jpg"
        ensure_scene_preview(scene_video, preview_path)
        scene_items.append({
            "id": scene.id,
            "label": f"{scene.id} · {scene.section}",
            "path": preview_path.relative_to(project_root).as_posix(),
        })

    transition_items: list[dict[str, str]] = []
    for transition in storyboard.transitions:
        clip = resolve_transition_clip(project_root, storyboard, transition)
        if clip is None or not clip.exists():
            continue
        preview_path = (
            previews_dir / "transitions" / f"{transition.from_scene}_{transition.to_scene}.jpg"
        )
        ensure_transition_preview(clip, preview_path)
        transition_items.append({
            "id": f"{transition.from_scene}->{transition.to_scene}",
            "label": f"{transition.from_scene} to {transition.to_scene} · {transition.style}",
            "path": preview_path.relative_to(project_root).as_posix(),
        })

    intro_item = build_intro_transition_preview(project_root, storyboard, previews_dir)
    if intro_item is not None:
        transition_items.insert(0, intro_item)

    return {"scenes": scene_items, "transitions": transition_items}


def ensure_scene_preview(scene_video: Path, out_path: Path) -> Path:
    if out_path.exists() and out_path.stat().st_mtime >= scene_video.stat().st_mtime:
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = _probe_duration_sec(scene_video)
    timestamp = max(0.0, min(duration / 2, duration - 0.05))
    run_ffmpeg([
        "ffmpeg",
        "-y",
        "-ss",
        str(timestamp),
        "-i",
        str(scene_video),
        "-frames:v",
        "1",
        "-q:v",
        "4",
        str(out_path),
    ])
    return out_path


def ensure_transition_preview(transition_video: Path, out_path: Path) -> Path:
    if out_path.exists() and out_path.stat().st_mtime >= transition_video.stat().st_mtime:
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.1, _probe_duration_sec(transition_video))
    fps = 4 / duration
    run_ffmpeg([
        "ffmpeg",
        "-y",
        "-i",
        str(transition_video),
        "-vf",
        f"fps={fps:.4f},scale=240:-1,tile=4x1",
        "-frames:v",
        "1",
        "-q:v",
        "3",
        str(out_path),
    ])
    return out_path


def resolve_transition_clip(
    project_root: Path,
    storyboard: Storyboard,
    transition: Any,
) -> Path | None:
    frame_style = storyboard.theme.frame_style or ""
    frame_suffix = f"_{frame_style}" if frame_style else ""
    scenes_dir = project_root / "compose" / "scenes"
    scene_a = scenes_dir / f"{transition.from_scene}_final{frame_suffix}.mp4"
    scene_b = scenes_dir / f"{transition.to_scene}_final{frame_suffix}.mp4"
    if not scene_a.exists() or not scene_b.exists():
        return None
    try:
        cfg = TransitionConfig.from_transition(transition)
    except ValueError:
        return None
    key = transition_cache_key(scene_a, scene_b, cfg)
    clip = project_root / "compose" / "transitions" / f"{key}.mp4"
    return clip if clip.exists() else None


def build_intro_transition_preview(
    project_root: Path,
    storyboard: Storyboard,
    previews_dir: Path,
) -> dict[str, str] | None:
    style = storyboard.theme.intro_transition_style or ""
    if not style or not storyboard.scenes:
        return None
    frame_style = storyboard.theme.frame_style or ""
    frame_suffix = f"_{frame_style}" if frame_style else ""
    first_scene = project_root / "compose" / "scenes" / f"{storyboard.scenes[0].id}_final{frame_suffix}.mp4"
    if not first_scene.exists():
        return None

    duration = float(storyboard.theme.intro_transition_duration_sec or "0.9")
    page_count = int(storyboard.theme.intro_transition_page_count or "2")
    width, height = get_resolution(storyboard.aspect_ratio)
    from pipeline.stages.compose import ComposeStage

    compose_dir = project_root / "compose"
    intro_src = ComposeStage()._book_start_plate(compose_dir, width, height, 30, duration)
    try:
        cfg = TransitionConfig(
            style=style,
            duration_sec=duration,
            sfx=None,
            page_count=page_count if style in {"book-page-turn", "stock-book-page-turn"} else None,
            renderer_mode=storyboard.theme.intro_transition_renderer_mode or None,
            asset_path=storyboard.theme.intro_transition_asset_path or None,
            asset_source=storyboard.theme.intro_transition_asset_source or None,
            asset_source_url=storyboard.theme.intro_transition_asset_source_url or None,
            asset_license=storyboard.theme.intro_transition_asset_license or None,
            asset_notes=storyboard.theme.intro_transition_asset_notes or None,
        )
    except ValueError:
        return None
    key = transition_cache_key(intro_src, first_scene, cfg)
    clip = compose_dir / "transitions" / f"{key}.mp4"
    if not clip.exists():
        return None
    preview_path = previews_dir / "transitions" / "intro.jpg"
    ensure_transition_preview(clip, preview_path)
    return {
        "id": "intro",
        "label": f"intro · {style}",
        "path": preview_path.relative_to(project_root).as_posix(),
    }


def build_transition_preview_image(
    project_root: Path,
    *,
    style: str,
    duration_sec: float,
    page_count: int | None = None,
    sfx: str | None = None,
    renderer_mode: str | None = None,
    asset_path: str | None = None,
    from_scene: str | None = None,
    to_scene: str | None = None,
    intro: bool = False,
    preview_name: str = "draft",
) -> Path | None:
    storyboard_path = project_root / "storyboard.json"
    if not storyboard_path.exists():
        return None
    storyboard = Storyboard.load(storyboard_path)
    width, height = get_resolution(storyboard.aspect_ratio)
    cfg = TransitionConfig(
        style=style,
        duration_sec=duration_sec,
        sfx=sfx,
        page_count=page_count if style in {"book-page-turn", "stock-book-page-turn"} else None,
        renderer_mode=renderer_mode,
        asset_path=asset_path,
    )
    if intro:
        clip = _render_intro_preview_clip(project_root, storyboard, cfg)
    else:
        if not from_scene or not to_scene:
            return None
        clip = _render_transition_preview_clip(
            project_root,
            storyboard,
            from_scene=from_scene,
            to_scene=to_scene,
            cfg=cfg,
            width=width,
            height=height,
        )
    if clip is None:
        return None
    preview_path = project_root / "compose" / "previews" / "transitions" / f"{preview_name}.jpg"
    ensure_transition_preview(clip, preview_path)
    return preview_path


def _render_transition_preview_clip(
    project_root: Path,
    storyboard: Storyboard,
    *,
    from_scene: str,
    to_scene: str,
    cfg: TransitionConfig,
    width: int,
    height: int,
) -> Path | None:
    scene_a = _scene_final_path(project_root, storyboard, from_scene)
    scene_b = _scene_final_path(project_root, storyboard, to_scene)
    if scene_a is None or scene_b is None:
        return None
    return render_transition(
        scene_a,
        scene_b,
        cfg,
        project_root / "compose" / "transitions",
        width=width,
        height=height,
        fps=30,
    )


def _render_intro_preview_clip(
    project_root: Path,
    storyboard: Storyboard,
    cfg: TransitionConfig,
) -> Path | None:
    if not storyboard.scenes:
        return None
    width, height = get_resolution(storyboard.aspect_ratio)
    first_scene = _scene_final_path(project_root, storyboard, storyboard.scenes[0].id)
    if first_scene is None:
        return None
    from pipeline.stages.compose import ComposeStage

    compose_dir = project_root / "compose"
    intro_src = ComposeStage()._book_start_plate(compose_dir, width, height, 30, cfg.duration_sec)
    return render_transition(
        intro_src,
        first_scene,
        cfg,
        compose_dir / "transitions",
        width=width,
        height=height,
        fps=30,
    )


def _scene_final_path(project_root: Path, storyboard: Storyboard, scene_id: str) -> Path | None:
    frame_style = storyboard.theme.frame_style or ""
    frame_suffix = f"_{frame_style}" if frame_style else ""
    scenes_dir = project_root / "compose" / "scenes"
    for suffix in (f"_final{frame_suffix}.mp4", "_final.mp4"):
        candidate = scenes_dir / f"{scene_id}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _probe_duration_sec(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return max(0.01, float(result.stdout.strip()))
