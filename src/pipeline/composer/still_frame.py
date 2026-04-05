from __future__ import annotations

from pathlib import Path

from pipeline.composer.base import image_to_video
from pipeline.utils.ffmpeg import run_ffmpeg


def render_still_frame(
    visual: dict,
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
    source_video: Path | None = None,
) -> Path:
    """Extract a single frame from source video at a timestamp, loop for duration."""
    if source_video is None or not source_video.exists():
        raise FileNotFoundError(f"Source video not found for still_frame in scene {scene_id}")

    timestamp = float(visual.get("timestamp_sec", 0))
    frame_path = work_dir / f"{scene_id}_frame.png"
    output = work_dir / f"{scene_id}_visual.mp4"

    # Extract single frame as PNG
    run_ffmpeg([
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", str(source_video),
        "-frames:v", "1",
        "-q:v", "2",
        str(frame_path),
    ])

    # Convert to video segment
    image_to_video(frame_path, output, duration_sec, width, height)
    return output
