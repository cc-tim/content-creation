"""Video analysis utilities for clip confidence.

Provides keyframe extraction, scene change detection, and post-render
frame review. Used by the /produce skill to make informed clip decisions.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from pipeline.utils.ffmpeg import run_ffmpeg


def extract_keyframes(
    video_path: Path,
    output_dir: Path,
    interval_sec: int = 10,
) -> list[dict]:
    """Extract one frame every N seconds from a video.

    Returns list of {"timestamp_sec": float, "path": Path} dicts.
    The agent can read these images to decide which moments are visually relevant.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps=1/{interval_sec}",
            "-q:v",
            "5",
            str(output_dir / "keyframe_%04d.jpg"),
        ]
    )

    # Collect results
    frames = []
    for i, f in enumerate(sorted(output_dir.glob("keyframe_*.jpg"))):
        frames.append(
            {
                "timestamp_sec": i * interval_sec,
                "path": str(f),
            }
        )

    return frames


def detect_scene_changes(
    video_path: Path,
    threshold: float = 0.3,
) -> list[float]:
    """Detect scene changes in a video using FFmpeg's scene filter.

    Returns list of timestamps (seconds) where visual transitions occur.
    Higher threshold = fewer detections (only dramatic cuts).
    Lower threshold = more detections (subtle changes too).
    """
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "frame=pts_time",
            "-select_streams",
            "v:0",
            "-of",
            "json",
            "-f",
            "lavfi",
            f"movie={video_path},select=gt(scene\\,{threshold})",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        # Fallback: return empty list if detection fails
        return []

    try:
        data = json.loads(result.stdout)
        timestamps = []
        for frame in data.get("frames", []):
            pts = frame.get("pts_time")
            if pts:
                timestamps.append(float(pts))
        return timestamps
    except (json.JSONDecodeError, KeyError):
        return []


def extract_review_frames(
    video_path: Path,
    output_dir: Path,
    timestamps: list[float] | None = None,
    count: int = 8,
) -> list[dict]:
    """Extract specific frames from a video for post-render review.

    If timestamps provided, extract at those points.
    Otherwise, extract `count` evenly spaced frames.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if timestamps is None:
        duration = get_duration(video_path)
        interval = duration / (count + 1)
        timestamps = [interval * (i + 1) for i in range(count)]

    frames = []
    for i, ts in enumerate(timestamps):
        out_path = output_dir / f"review_{i:03d}.jpg"
        try:
            run_ffmpeg(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    str(ts),
                    "-i",
                    str(video_path),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    str(out_path),
                ]
            )
            frames.append({"timestamp_sec": ts, "path": str(out_path)})
        except subprocess.CalledProcessError:
            continue

    return frames


def get_duration(path: Path) -> float:
    """Get media duration in seconds."""
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
