from __future__ import annotations

import subprocess
from pathlib import Path

from pipeline.utils.ffmpeg import run_ffmpeg


def _get_source_duration(path: Path) -> float:
    """Get video duration in seconds via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
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
) -> Path:
    """Extract a clip from source video. Clamps timestamps to source duration."""
    if source_video is None or not source_video.exists():
        raise FileNotFoundError(f"Source video not found for clip in scene {scene_id}")

    start = float(visual.get("start_sec", 0))
    end = float(visual.get("end_sec", start + duration_sec))
    source_dur = _get_source_duration(source_video)

    # Clamp to source bounds
    start = max(0, min(start, source_dur - 1))
    end = max(start + 1, min(end, source_dur))
    clip_duration = end - start

    # If clip is shorter than scene duration, we'll let it be short
    # (compose stage pads with last frame via -shortest)
    output = work_dir / f"{scene_id}_visual.mp4"

    # Determine crop filter for aspect ratio
    if width < height:
        # 9:16 — center-crop from 16:9 source
        vf = f"crop=ih*{width}/{height}:ih,scale={width}:{height}"
    else:
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
        )

    run_ffmpeg([
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(source_video),
        "-t", str(clip_duration),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-an",
        "-r", "30",
        str(output),
    ])
    return output
