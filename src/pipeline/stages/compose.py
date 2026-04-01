from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from pipeline.stages.base import PipelineContext, PipelineStage
from pipeline.stages.scriptwrite import parse_script_markers
from pipeline.utils.ffmpeg import (
    build_burn_subtitles_cmd,
    build_concat_cmd,
    build_extract_clip_cmd,
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
        """MVP composition: narration audio + burned subtitles over source clips."""
        assert ctx.video_path is not None
        assert ctx.narration_path is not None
        assert ctx.subtitle_path is not None

        # Step 1: Extract relevant clips from source video
        script_text = ctx.script_path.read_text(encoding="utf-8") if ctx.script_path else ""
        plan = build_composition_plan(script_text)

        clip_segments = [s for s in plan if s["type"] == "clip"]
        clip_paths: list[Path] = []

        for i, clip in enumerate(clip_segments):
            clip_path = compose_dir / f"clip_{i:03d}.mp4"
            start = _timestamp_to_seconds(clip["start"])
            end = _timestamp_to_seconds(clip["end"])
            cmd = build_extract_clip_cmd(
                str(ctx.video_path), str(clip_path), start, end
            )
            run_ffmpeg(cmd)
            clip_paths.append(clip_path)

        # Step 2: Concatenate clips (or use full source if no clips extracted)
        if clip_paths:
            filelist = compose_dir / "clips.txt"
            filelist.write_text(
                "\n".join(f"file '{p.resolve()}'" for p in clip_paths),
                encoding="utf-8",
            )
            clips_video = compose_dir / "clips_concat.mp4"
            run_ffmpeg(build_concat_cmd(str(filelist), str(clips_video)))
            base_video = clips_video
        else:
            base_video = ctx.video_path

        # Step 3: Replace audio with narration
        narration_video = compose_dir / "with_narration.mp4"
        run_ffmpeg([
            "ffmpeg", "-y",
            "-i", str(base_video),
            "-i", str(ctx.narration_path),
            "-c:v", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            str(narration_video),
        ])

        # Step 4: Burn subtitles
        final_path = compose_dir / f"final_{ctx.locale}.mp4"
        cmd = build_burn_subtitles_cmd(
            str(narration_video),
            str(ctx.subtitle_path),
            str(final_path),
            font_name="Noto Sans CJK TC",
        )
        run_ffmpeg(cmd)

        return final_path
