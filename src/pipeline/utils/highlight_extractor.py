# src/pipeline/utils/highlight_extractor.py
"""Signal-scored clip manifest generator.

Replaces raw keyframe scanning in /produce Step 1b. Extracts top-10 highlight
candidates using three cheap signals: scene-change count, audio RMS, and
transcript keyword density. A pluggable CaptionProvider (NullCaptionProvider
by default) can enrich candidates with visual descriptions.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pipeline.utils.video_analysis import detect_scene_changes, get_duration

ACTION_WORDS = [
    "shot", "arrest", "fight", "crash", "verdict", "confronted",
    "screaming", "weapon", "chase", "attack", "guilty", "explosion",
    "threatening", "fleeing", "struggle", "collision", "fired",
]

# Used by caption providers (Task 2) to filter visually low-quality candidates.
REJECT_PATTERNS = [
    "talking head at desk", "anchor at desk", "blank screen",
    "empty room", "news lower third", "static title card",
]

_ACTION_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in ACTION_WORDS) + r")\b"
)


@runtime_checkable
class CaptionProvider(Protocol):
    def caption(self, frame_path: Path) -> str | None: ...


class NullCaptionProvider:
    """Default provider: no API call, caption is always None."""

    def caption(self, frame_path: Path) -> str | None:  # noqa: ARG002
        return None


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
    duration = get_duration(video_path)
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
            counts[bucket] += len(_ACTION_RE.findall(text))
    max_count = max(counts) or 1
    return [(float(i * window_sec), c / max_count) for i, c in enumerate(counts)]


def _merge_scores(
    frame_diff: list[tuple[float, float]],
    audio_rms: list[tuple[float, float]],
    keywords: list[tuple[float, float]],
    duration_sec: float,
    window_sec: int = 5,
) -> list[dict[str, Any]]:
    """Merge three signal lists into per-window combined scores."""
    def to_dict(scores: list[tuple[float, float]]) -> dict[int, float]:
        out: dict[int, float] = {}
        for ts, val in scores:
            key = round(ts / window_sec)
            out[key] = max(out.get(key, 0.0), val)
        return out

    fd = to_dict(frame_diff)
    ar = to_dict(audio_rms)
    kw = to_dict(keywords)
    n_windows = int(duration_sec / window_sec) + 1
    results = []
    for i in range(n_windows):
        f = fd.get(i, 0.0)
        a = ar.get(i, 0.0)
        k = kw.get(i, 0.0)
        results.append({
            "timestamp_sec": float(i * window_sec),
            "frame_diff": round(f, 3),
            "audio_rms": round(a, 3),
            "keyword_score": round(k, 3),
            "combined_score": round(0.4 * f + 0.3 * a + 0.3 * k, 3),
        })
    return results


def _select_candidates(
    scored: list[dict[str, Any]],
    top_n: int = 10,
    min_spacing_sec: float = 15.0,
) -> list[dict[str, Any]]:
    """Pick top-N candidates, enforcing minimum spacing between timestamps."""
    sorted_by_score = sorted(scored, key=lambda x: x["combined_score"], reverse=True)
    selected: list[dict[str, Any]] = []
    for candidate in sorted_by_score:
        ts = candidate["timestamp_sec"]
        if all(abs(ts - s["timestamp_sec"]) >= min_spacing_sec for s in selected):
            selected.append(candidate)
        if len(selected) >= top_n:
            break
    return selected


def _is_rejected_caption(caption: str) -> bool:
    caption_lower = caption.lower()
    return any(pat in caption_lower for pat in REJECT_PATTERNS)


def extract_highlights(
    video_path: Path,
    transcript_path: Path | None = None,
    caption_provider: CaptionProvider | None = None,
    window_sec: int = 5,
    top_n: int = 10,
    min_spacing_sec: float = 15.0,
) -> dict[str, Any]:
    """Generate clip manifest content for a source video.

    Returns the manifest dict. Caller writes it to disk.
    To swap in vision captioning later, pass a GptVisionCaptionProvider or
    GeminiCaptionProvider — the manifest schema is unchanged.
    """
    from pipeline.utils.video_analysis import extract_keyframes

    if caption_provider is None:
        caption_provider = NullCaptionProvider()

    duration_sec = get_duration(video_path)

    kf_dir = video_path.parent / "keyframes"
    keyframes = extract_keyframes(video_path, kf_dir, interval_sec=window_sec)
    kf_map = {round(kf["timestamp_sec"] / window_sec): kf["path"] for kf in keyframes}

    frame_diff = _count_scene_changes_per_window(video_path, window_sec)
    audio_rms = _audio_rms_per_window(video_path, window_sec)
    keywords = _score_keywords(transcript_path, duration_sec, window_sec)

    scored = _merge_scores(frame_diff, audio_rms, keywords, duration_sec, window_sec)
    for entry in scored:
        bucket = round(entry["timestamp_sec"] / window_sec)
        entry["keyframe_path"] = kf_map.get(bucket, "")

    raw_candidates = _select_candidates(scored, top_n, min_spacing_sec)

    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for c in raw_candidates:
        kf_path = Path(c["keyframe_path"]) if c.get("keyframe_path") else None
        caption = (
            caption_provider.caption(kf_path)
            if kf_path and kf_path.exists()
            else None
        )
        c["caption"] = caption
        if caption and _is_rejected_caption(caption):
            c["usable"] = False
            rejected.append({**c, "reject_reason": caption[:80]})
        else:
            c["usable"] = True
            candidates.append(c)

    return {
        "video_id": video_path.parent.parent.name,
        "duration_sec": round(duration_sec, 1),
        "caption_provider": type(caption_provider).__name__,
        "candidates": candidates,
        "rejected": rejected,
    }
