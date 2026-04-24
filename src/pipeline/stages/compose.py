from __future__ import annotations

import subprocess
from pathlib import Path

import structlog

from pipeline.composer.base import get_resolution, render_scene
from pipeline.composer.compartment import (
    build_compartment_loop,
    composite_compartment_on_scene,
)
from pipeline.composer.overlay import apply_overlay
from pipeline.composer.overlay_rules import check_overlay_allowed
from pipeline.stages.base import PipelineContext, PipelineStage
from pipeline.storyboard import Storyboard
from pipeline.utils.ffmpeg import check_ffmpeg_available, run_ffmpeg

logger = structlog.get_logger()


def _hex_to_ass_color(hex_color: str) -> str:
    """Convert #RRGGBB hex to ASS &H00BBGGRR color format for FFmpeg force_style."""
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"&H00{b:02X}{g:02X}{r:02X}"
    return "&H00FFFFFF"


def _build_subtitle_style(theme_dict: dict[str, str]) -> str:
    """Build FFmpeg force_style string from theme colors and font."""
    font = theme_dict.get("font", "Noto Sans CJK TC")
    text_color = theme_dict.get("text_color", "#f8fafc")
    primary = _hex_to_ass_color(text_color)
    # White outline on light themes, black on dark themes — auto-detect by luminance
    h = text_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        outline_color = "&H00FFFFFF" if luminance < 128 else "&H00000000"
    else:
        outline_color = "&H00000000"
    return (
        f"FontName={font},FontSize=28,Bold=1,"
        f"PrimaryColour={primary},OutlineColour={outline_color},"
        f"Outline=2,Shadow=0,Alignment=2,MarginV=20"
    )


def _get_duration_sec(path: Path) -> float:
    """Get media duration in seconds via ffprobe."""
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


class ComposeStage(PipelineStage):
    @property
    def name(self) -> str:
        return "compose"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.narration_path or not ctx.subtitle_path:
            raise ValueError("Missing narration or subtitles")

        if not check_ffmpeg_available():
            raise RuntimeError("ffmpeg not found — install with: sudo apt install ffmpeg")

        logger.info("compose.start")

        compose_dir = ctx.work_dir / "compose"
        compose_dir.mkdir(parents=True, exist_ok=True)

        # Try storyboard-driven compose, fall back to MVP
        if ctx.storyboard_path and ctx.storyboard_path.exists():
            final_path = await self._compose_from_storyboard(ctx, compose_dir)
        else:
            final_path = await self._compose_mvp(ctx, compose_dir)

        ctx.final_video_path = final_path
        logger.info("compose.complete", path=str(final_path))
        return ctx

    async def _compose_from_storyboard(
        self,
        ctx: PipelineContext,
        compose_dir: Path,
    ) -> Path:
        """Scene-by-scene rendering from storyboard."""
        storyboard = Storyboard.load(ctx.storyboard_path)
        width, height = get_resolution(storyboard.aspect_ratio)
        theme_dict = storyboard.theme.to_dict()

        scenes_dir = compose_dir / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)

        # Match audio segments to scenes
        audio_segments = ctx.segment_timings or []

        scene_finals: list[Path] = []

        for i, scene in enumerate(storyboard.scenes):
            scene_dict = {
                "id": scene.id,
                "visual": scene.visual,
                "overlay": scene.overlay,
                "compartment": scene.compartment,
                "narration": scene.narration,
            }

            # Get audio for this scene
            if i < len(audio_segments):
                audio_path = Path(audio_segments[i]["path"])
                duration = audio_segments[i]["duration_ms"] / 1000.0
            else:
                duration = scene.narration_est_sec
                audio_path = None

            logger.info("compose.scene", scene_id=scene.id, duration=f"{duration:.1f}s")

            # Step 1: Render visual
            try:
                visual_path = render_scene(
                    scene_dict,
                    duration,
                    storyboard.aspect_ratio,
                    scenes_dir,
                    source_video=ctx.video_path,
                    theme=theme_dict,
                )
            except Exception as e:
                logger.warning(
                    "compose.scene.visual_failed",
                    scene_id=scene.id,
                    error=str(e),
                )
                # Fallback: black screen for this scene
                visual_path = self._black_screen(
                    scenes_dir,
                    scene.id,
                    duration,
                    width,
                    height,
                )

            # Step 1b: Composite compartment animation if present
            if scene.compartment:
                try:
                    compartment_video = build_compartment_loop(
                        compartment=scene.compartment,
                        scene_duration_sec=duration,
                        scene_width=width,
                        scene_height=height,
                        work_dir=scenes_dir,
                        scene_id=scene.id,
                    )
                    visual_path = composite_compartment_on_scene(
                        scene_video=visual_path,
                        compartment_video=compartment_video,
                        compartment_config=scene.compartment,
                        scene_width=width,
                        scene_height=height,
                        work_dir=scenes_dir,
                        scene_id=scene.id,
                    )
                except Exception as e:
                    logger.warning(
                        "compose.scene.compartment_failed",
                        scene_id=scene.id,
                        error=str(e),
                    )

            # Step 2: Apply overlay if present (collision rule enforced upfront)
            check_overlay_allowed(
                scene=scene_dict,
                overlay=scene.overlay,
                visual=scene.visual,
                burn_subtitles=ctx.burn_subtitles,
            )
            if scene.overlay:
                try:
                    overlaid_path = apply_overlay(
                        visual_path=visual_path,
                        overlay=scene.overlay,
                        width=width,
                        height=height,
                        work_dir=scenes_dir,
                        scene_id=scene.id,
                        theme=theme_dict,
                    )
                    visual_path = overlaid_path
                except Exception as e:
                    logger.warning(
                        "compose.scene.overlay_failed",
                        scene_id=scene.id,
                        error=str(e),
                    )

            # Step 3: Combine visual + audio
            scene_final = scenes_dir / f"{scene.id}_final.mp4"
            if audio_path and audio_path.exists():
                run_ffmpeg(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(visual_path),
                        "-i",
                        str(audio_path),
                        "-c:v",
                        "copy",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "128k",
                        "-shortest",
                        str(scene_final),
                    ]
                )
            else:
                # No audio — use silent visual
                run_ffmpeg(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(visual_path),
                        "-c:v",
                        "copy",
                        "-an",
                        str(scene_final),
                    ]
                )

            scene_finals.append(scene_final)

            # Step 4: Add pause if needed
            if scene.pause_after_sec > 0:
                pause_path = self._silence_gap(
                    scenes_dir,
                    scene.id,
                    scene.pause_after_sec,
                    width,
                    height,
                )
                scene_finals.append(pause_path)

        # Step 5: Concatenate all scene segments
        raw_path = compose_dir / "raw.mp4"
        self._concat_scenes(scene_finals, raw_path)

        # Step 6: Burn subtitles (optional)
        final_path = compose_dir / f"final_{ctx.locale}.mp4"
        if ctx.burn_subtitles:
            escaped_sub = str(ctx.subtitle_path).replace("\\", "\\\\").replace(":", "\\:")
            subtitle_style = _build_subtitle_style(theme_dict)
            run_ffmpeg(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(raw_path),
                    "-vf",
                    f"subtitles={escaped_sub}:force_style='{subtitle_style}'",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "23",
                    "-c:a",
                    "copy",
                    str(final_path),
                ]
            )
        else:
            # No subtitle burn: raw.mp4 is already libx264/aac from scene finals.
            import shutil

            shutil.copyfile(raw_path, final_path)

        return final_path

    async def _compose_mvp(self, ctx: PipelineContext, compose_dir: Path) -> Path:
        """Fallback: MVP compose (continuous source footage)."""
        assert ctx.video_path is not None
        assert ctx.narration_path is not None
        assert ctx.subtitle_path is not None

        narration_duration = _get_duration_sec(ctx.narration_path)
        source_duration = _get_duration_sec(ctx.video_path)
        start_offset = min(30.0, source_duration * 0.05)

        final_path = compose_dir / f"final_{ctx.locale}.mp4"
        cmd: list[str] = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start_offset),
            "-i",
            str(ctx.video_path),
            "-i",
            str(ctx.narration_path),
            "-t",
            str(narration_duration),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
        ]
        if ctx.burn_subtitles:
            escaped_sub = str(ctx.subtitle_path).replace("\\", "\\\\").replace(":", "\\:")
            from pipeline.storyboard import Theme
            subtitle_style = _build_subtitle_style(Theme().to_dict())
            cmd += ["-vf", f"subtitles={escaped_sub}:force_style='{subtitle_style}'"]
        cmd += [
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(final_path),
        ]
        run_ffmpeg(cmd)
        return final_path

    def _black_screen(
        self,
        work_dir: Path,
        scene_id: str,
        duration: float,
        width: int,
        height: int,
    ) -> Path:
        """Generate a black screen video segment."""
        output = work_dir / f"{scene_id}_black.mp4"
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=black:s={width}x{height}:d={duration}:r=30",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                str(output),
            ]
        )
        return output

    def _silence_gap(
        self,
        work_dir: Path,
        scene_id: str,
        duration: float,
        width: int,
        height: int,
    ) -> Path:
        """Generate a black + silent video segment for pause gaps."""
        output = work_dir / f"{scene_id}_pause.mp4"
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=black:s={width}x{height}:d={duration}:r=30",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=mono:sample_rate=24000",
                "-t",
                str(duration),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-pix_fmt",
                "yuv420p",
                "-shortest",
                str(output),
            ]
        )
        return output

    def _concat_scenes(self, scene_paths: list[Path], output: Path) -> None:
        """Concatenate scene segments using ffmpeg concat demuxer.

        Re-encodes to ensure consistent format across all segments.
        """
        filelist = output.parent / "concat_list.txt"
        filelist.write_text(
            "\n".join(f"file '{p.resolve()}'" for p in scene_paths),
            encoding="utf-8",
        )
        # Use concat protocol with re-encode for format consistency
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(filelist),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(output),
            ]
        )
