from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import structlog

from pipeline.stages.base import PipelineContext, PipelineStage
from pipeline.stages.scriptwrite import parse_script_markers
from pipeline.utils.ffmpeg import (
    check_ffmpeg_available,
    run_ffmpeg,
)

logger = structlog.get_logger()


def build_composition_plan(script: str) -> list[dict[str, Any]]:
    """Parse script markers into a sequential composition plan."""
    markers = parse_script_markers(script)
    plan: list[dict[str, Any]] = []

    for marker in markers:
        if marker["type"] == "clip":
            plan.append({
                "type": "clip",
                "start": marker["start"],
                "end": marker["end"],
            })
        elif marker["type"] == "overlay":
            plan.append({
                "type": "overlay",
                "overlay_type": marker["overlay_type"],
                "content": marker["content"],
            })
        elif marker["type"] == "narration":
            plan.append({"type": "narration", "text": marker["text"]})
        elif marker["type"] == "pause":
            plan.append({"type": "pause", "seconds": marker["seconds"]})

    return plan


def _get_duration_sec(path: Path) -> float:
    """Get media duration in seconds via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def _timestamp_to_seconds(ts: str) -> float:
    """Convert MM:SS to seconds."""
    parts = ts.split(":")
    return int(parts[0]) * 60 + int(parts[1])


class ComposeStage(PipelineStage):
    @property
    def name(self) -> str:
        return "compose"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.narration_path or not ctx.subtitle_path or not ctx.video_path:
            raise ValueError("Missing narration, subtitles, or source video")
        if not ctx.script_path:
            raise ValueError("Missing script")

        if not check_ffmpeg_available():
            raise RuntimeError("ffmpeg not found on PATH — install with: sudo apt install ffmpeg")

        logger.info("compose.start")

        compose_dir = ctx.work_dir / "compose"
        compose_dir.mkdir(parents=True, exist_ok=True)

        final_path = await self._compose_video(ctx, compose_dir)
        ctx.final_video_path = final_path

        logger.info("compose.complete", path=str(final_path))
        return ctx

    async def _compose_video(self, ctx: PipelineContext, compose_dir: Path) -> Path:
        """Compose final video: source footage + narration audio + burned subtitles.

        Strategy: Use full source video as visual base (the aerial footage is
        compelling throughout). Trim to narration duration, replace audio with
        TTS narration, burn CJK subtitles.

        Future: interleave specific clips with overlay cards for richer composition.
        """
        assert ctx.video_path is not None
        assert ctx.narration_path is not None
        assert ctx.subtitle_path is not None

        narration_duration = _get_duration_sec(ctx.narration_path)
        source_duration = _get_duration_sec(ctx.video_path)

        # Pick a visually interesting starting point in the source video
        # Skip the first 30s (usually intros/logos) and center on the action
        start_offset = min(30.0, source_duration * 0.05)

        final_path = compose_dir / f"final_{ctx.locale}.mp4"
        escaped_sub = str(ctx.subtitle_path).replace("\\", "\\\\").replace(":", "\\:")
        subtitle_style = "FontName=Noto Sans CJK TC,FontSize=24"
        run_ffmpeg([
            "ffmpeg", "-y",
            "-ss", str(start_offset),
            "-i", str(ctx.video_path),
            "-i", str(ctx.narration_path),
            "-t", str(narration_duration),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-vf", f"subtitles={escaped_sub}:force_style='{subtitle_style}'",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            str(final_path),
        ])

        return final_path
