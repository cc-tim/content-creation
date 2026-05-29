from __future__ import annotations

import json
from pathlib import Path

from pipeline.composer.base import get_resolution, render_scene
from pipeline.composer.frame import composite_scene_frame
from pipeline.composer.overlay import apply_overlay
from pipeline.utils.ffmpeg import run_ffmpeg

_STILL_DURATION_SEC = 1.0
_OVERLAY_VARIANTS = {"plain", "subtitles"}  # variants that burn per-scene overlays


def resolve_variant(project_dir: Path) -> str:
    """Read the delivered overlay variant from context.json; default 'plain'."""
    ctx = project_dir / "context.json"
    if ctx.exists():
        data = json.loads(ctx.read_text())
        v = data.get("preferred_variant")
        if isinstance(v, str) and v:
            return v
    return "plain"


def render_scene_still(
    scene: dict,
    *,
    variant: str,
    work_dir: Path,
    theme: dict | None = None,
) -> Path:
    """Composite one scene to a single PNG in the delivered variant.

    Reuses the compose render path (render_scene -> book-frame -> overlay) at
    minimal duration, then extracts frame 1. Deterministic for static visuals.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    scene_id = scene.get("id", "scene")
    width, height = get_resolution("16:9")

    visual_mp4 = render_scene(scene, _STILL_DURATION_SEC, "16:9", work_dir, theme=theme or {})

    framed = composite_scene_frame(
        visual_mp4,
        work_dir / f"{scene_id}_framed.mp4",
        frame_style="open_book_page",
        width=width,
        height=height,
    )

    overlay = scene.get("overlay")
    if variant in _OVERLAY_VARIANTS and overlay:
        framed = apply_overlay(framed, overlay, width, height, work_dir, scene_id, theme or {})

    still = work_dir / f"{scene_id}.png"
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(framed),
            "-frames:v",
            "1",
            "-fflags",
            "+bitexact",
            "-flags:v",
            "+bitexact",
            "-q:v",
            "2",
            str(still),
        ]
    )
    return still
