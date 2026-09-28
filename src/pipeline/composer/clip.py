from __future__ import annotations

import subprocess
from pathlib import Path

from pipeline.errors import SceneRenderError
from pipeline.utils.ffmpeg import run_ffmpeg
from pipeline.utils.paths import media_path_candidates, resolve_media_path


def _resolve_source_video(
    visual: dict, source_video: Path | None, project_root: Path | None = None
) -> Path | None:
    """The clip's source file: `visual.path` via the shared media resolver, else the
    project's primary source video."""
    raw_path = visual.get("path")
    if raw_path:
        return resolve_media_path(str(raw_path), project_root)
    return source_video


def _get_source_duration(path: Path) -> float:
    """Get video duration in seconds via ffprobe."""
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
    return float(result.stdout.strip())


def render_clip(
    visual: dict,
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
    source_video: Path | None = None,
    project_root: Path | None = None,
) -> Path:
    """Extract a clip from source video. Clamps timestamps to source duration."""
    clip_source = _resolve_source_video(visual, source_video, project_root)
    if clip_source is None or not clip_source.exists():
        raw_path = visual.get("path")
        if raw_path:
            tried = ", ".join(str(p) for p in media_path_candidates(str(raw_path), project_root))
            where = f"visual.path {raw_path!r} not found; tried: {tried}"
        else:
            where = "no visual.path and no primary source video"
        pid = project_root.name if project_root else "<project-id>"
        raise SceneRenderError(
            scene=scene_id,
            reason=f"clip source not found: {where}",
            suggested_fix=(
                "Fix visual.path (project-relative, repo-relative or absolute) or re-acquire "
                f"the primary source video, then `uv run pipeline validate {pid}` and "
                f"`uv run pipeline compose rescene --project-id {pid} --scene {scene_id}`."
            ),
        )

    start = float(visual.get("start_sec", 0))
    source_dur = _get_source_duration(clip_source)

    # Clip duration always follows audio duration, not storyboard's end_sec estimate.
    # end_sec in the storyboard was generated from narration_est_sec which is often wrong.
    start = max(0, min(start, source_dur - 1))
    # available_clip may be shorter than duration_sec when the source ends first;
    # we freeze the last frame to fill the remaining time (see tpad below).
    available_clip = max(1.0, min(source_dur - start, source_dur))

    output = work_dir / f"{scene_id}_visual.mp4"

    # crop_bottom_pct: strip the bottom N% of the frame before scaling.
    # Use 0.20 for illustration-style source videos with burned-in subtitles,
    # so only the illustration area is shown.
    crop_bottom_pct = float(visual.get("crop_bottom_pct", 0.0))
    crop_bottom_pct = max(0.0, min(crop_bottom_pct, 0.5))  # clamp to sane range

    if width < height:
        # 9:16 portrait — center-crop from 16:9 source
        if crop_bottom_pct > 0:
            keep_h = 1.0 - crop_bottom_pct
            vf = (
                f"crop=iw:ih*{keep_h:.3f}:0:0,"
                f"crop=ih*{keep_h:.3f}*{width}/{height}:ih*{keep_h:.3f}:(iw-ih*{keep_h:.3f}*{width}/{height})/2:0,"
                f"scale={width}:{height}"
            )
        else:
            vf = f"crop=ih*{width}/{height}:ih,scale={width}:{height}"
    else:
        if crop_bottom_pct > 0:
            keep_h = 1.0 - crop_bottom_pct
            # Crop bottom, then scale-to-fill (no black bars) by overscaling + center-crop
            vf = (
                f"crop=iw:ih*{keep_h:.3f}:0:0,"
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}"
            )
        else:
            vf = (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}"
            )

    # If source ends before duration_sec, freeze the last frame to fill the gap
    # so the muxed scene always matches the audio length.
    if available_clip < duration_sec - 0.1:
        vf = vf + ",tpad=stop_mode=clone:stop=-1"

    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(start),
            "-i",
            str(clip_source),
            "-vf",
            vf,
            "-t",
            str(duration_sec),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-an",
            "-r",
            "30",
            str(output),
        ]
    )
    return output
