# src/pipeline/utils/highlight_extractor.py
"""Signal-scored clip manifest generator.

Replaces raw keyframe scanning in /produce Step 1b. Extracts top-10 highlight
candidates using three cheap signals: scene-change count, audio RMS, and
transcript keyword density. A pluggable CaptionProvider (NullCaptionProvider
by default) can enrich candidates with visual descriptions.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Protocol, runtime_checkable

from pipeline.utils.video_analysis import detect_scene_changes

ACTION_WORDS = [
    "shot", "arrest", "fight", "crash", "verdict", "confronted",
    "screaming", "weapon", "chase", "attack", "guilty", "explosion",
    "threatening", "fleeing", "struggle", "collision", "fired",
]

REJECT_PATTERNS = [
    "talking head at desk", "anchor at desk", "blank screen",
    "empty room", "news lower third", "static title card",
]


@runtime_checkable
class CaptionProvider(Protocol):
    def caption(self, frame_path: Path) -> str | None: ...


class NullCaptionProvider:
    """Default provider: no API call, caption is always None."""

    def caption(self, frame_path: Path) -> str | None:  # noqa: ARG002
        return None


def _get_duration(video_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def _count_scene_changes_per_window(
    video_path: Path,
    window_sec: int = 5,
    threshold: float = 0.1,
) -> list[tuple[float, float]]:
    """Count scene changes per window as a frame-activity proxy.

    Uses a low threshold to catch subtle transitions as well as hard cuts.
    Returns list of (timestamp_sec, normalized_score).
    """
    timestamps = detect_scene_changes(video_path, threshold=threshold)
    duration = _get_duration(video_path)
    n_windows = int(duration / window_sec) + 1
    counts = [0] * n_windows
    for ts in timestamps:
        bucket = int(ts / window_sec)
        if 0 <= bucket < n_windows:
            counts[bucket] += 1
    max_count = max(counts) or 1
    return [(float(i * window_sec), c / max_count) for i, c in enumerate(counts)]


def _audio_rms_per_window(
    video_path: Path,
    window_sec: int = 5,
) -> list[tuple[float, float]]:
    """Sample audio RMS energy per window via ffprobe astats filter.

    Returns list of (timestamp_sec, normalized_score) where 0dB → 1.0,
    -60dB → 0.0, silence → 0.0.
    """
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-f", "lavfi",
            "-i", f"amovie={video_path},astats=metadata=1:reset=1",
            "-show_entries", "frame_tags=lavfi.astats.Overall.RMS_level",
            "-of", "json",
        ],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        return []
    try:
        frames = json.loads(result.stdout).get("frames", [])
    except json.JSONDecodeError:
        return []

    per_second: list[float] = []
    for f in frames:
        rms_str = f.get("tags", {}).get("lavfi.astats.Overall.RMS_level", "-inf")
        try:
            db = float(rms_str)
            normalized = max(0.0, (db + 60.0) / 60.0)
        except ValueError:
            normalized = 0.0
        per_second.append(normalized)

    scores: list[tuple[float, float]] = []
    for start in range(0, len(per_second), window_sec):
        window = per_second[start : start + window_sec]
        if window:
            scores.append((float(start), sum(window) / len(window)))
    return scores


def _score_keywords(
    transcript_path: Path | None,
    duration_sec: float,
    window_sec: int = 5,
) -> list[tuple[float, float]]:
    """Count action-word hits per window from transcript timestamps.

    Returns list of (timestamp_sec, normalized_score).
    """
    if transcript_path is None or not transcript_path.exists():
        return []
    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    n_windows = int(duration_sec / window_sec) + 1
    counts = [0] * n_windows
    for entry in transcript:
        start = float(entry.get("start", 0))
        text = entry.get("text", "").lower()
        bucket = int(start / window_sec)
        if 0 <= bucket < n_windows:
            for word in ACTION_WORDS:
                if word in text:
                    counts[bucket] += 1
    max_count = max(counts) or 1
    return [(float(i * window_sec), c / max_count) for i, c in enumerate(counts)]
