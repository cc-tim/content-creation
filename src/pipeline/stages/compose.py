from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

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


def _burn_subtitle_pass(
    src: Path, dst: Path, subtitle_path: Path, theme_dict: dict[str, str]
) -> None:
    """Burn subtitles from subtitle_path into src, writing to dst."""
    escaped_sub = str(subtitle_path).replace("\\", "\\\\").replace(":", "\\:")
    subtitle_style = _build_subtitle_style(theme_dict)
    run_ffmpeg([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"subtitles={escaped_sub}:force_style='{subtitle_style}'",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "copy",
        str(dst),
    ])


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


def _extract_clip_thumbnail(source: Path, timestamp: float, out_path: Path) -> None:
    """Extract one frame from *source* at *timestamp* seconds via ffmpeg."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-ss", str(timestamp), "-i", str(source),
         "-vframes", "1", "-q:v", "5", str(out_path), "-y"],
        check=True, capture_output=True,
    )


def _phash_image(img_path: Path):
    """Return perceptual hash of *img_path*. Requires imagehash + Pillow."""
    import imagehash
    from PIL import Image
    return imagehash.phash(Image.open(img_path))


def _is_duplicate_frame(new_hash, seen_hashes: set, threshold: int = 8) -> bool:
    return any(new_hash - h <= threshold for h in seen_hashes)


def _apply_duplicate_guard(
    scene: dict[str, Any],
    source_video: Path | None,
    seen_hashes: set,
    style_descriptor: str,
) -> tuple[dict[str, Any], set]:
    """Check if *scene* is a duplicate clip. Return (possibly-replaced scene, updated seen_hashes).

    Storyboard/render divergence is intentional: storyboard reflects creative intent,
    render reflects reality. Replacements are logged for traceability.
    """
    visual = scene.get("visual", {})
    if visual.get("type") not in ("clip", "still_frame"):
        return scene, seen_hashes
    if source_video is None or not source_video.exists():
        return scene, seen_hashes

    timestamp = float(visual.get("start_sec", visual.get("timestamp_sec", 0)))
    thumb = source_video.parent / f"_thumb_{scene.get('id', 'x')}.jpg"

    try:
        _extract_clip_thumbnail(source_video, timestamp, thumb)
        new_hash = _phash_image(thumb)
    except Exception as exc:
        logger.warning("compose.dup_guard.thumbnail_failed", scene=scene.get("id"), error=str(exc))
        return scene, seen_hashes
    finally:
        if thumb.exists():
            thumb.unlink(missing_ok=True)

    if _is_duplicate_frame(new_hash, seen_hashes):
        logger.warning(
            "compose.clip.duplicate_detected",
            scene=scene.get("id"),
            replaced_with="generated_image",
        )
        narration = scene.get("narration", "")
        replacement_prompt = f"{style_descriptor}, {narration[:80]}".strip(", ")
        replaced = {
            **scene,
            "visual": {"type": "generated_image", "prompt": replacement_prompt},
        }
        return replaced, seen_hashes  # don't add duplicate hash to seen
    else:
        seen_hashes = seen_hashes | {new_hash}
        return scene, seen_hashes


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

        # --- Style anchor: source suitability → niche style → anchor image ---
        from pipeline.composer.style_anchor import extract_style_anchor
        from pipeline.niche_templates import load_niche_template

        niche = ctx.niche if ctx.niche and ctx.niche != "none" else None
        niche_template = load_niche_template(niche) if niche else None
        style_anchor = extract_style_anchor(
            project_id=str(ctx.project_id),
            niche=niche,
            template=niche_template,
            source_video=ctx.video_path,
            work_dir=compose_dir,
        )

        # Persist suitability back to constraints for DirectStage re-runs
        if style_anchor.suitability:
            from pipeline.constraints import ProjectConstraints
            _c = ProjectConstraints.load(ctx.work_dir) or ProjectConstraints()
            if _c.source_suitability != style_anchor.suitability:
                _c.source_suitability = style_anchor.suitability
                _c.save(ctx.work_dir)

        # Inject style anchor data into theme_dict (flows through render_scene → image.py)
        theme_dict["style_prefix"] = style_anchor.style_descriptor
        theme_dict["_seed"] = style_anchor.seed
        if style_anchor.anchor_image:
            theme_dict["_anchor_image"] = str(style_anchor.anchor_image)

        # --- Duplicate frame guard state ---
        seen_clip_hashes: set = set()

        scenes_dir = compose_dir / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)

        # Match audio segments to scenes
        audio_segments = ctx.segment_timings or []

        scene_finals: list[Path] = []
        scene_finals_no_overlay: list[Path] = []
        scenes_data: list[dict[str, object]] = []
        running_sec = 0.0

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

            # Step 3: Combine visual + audio — produce both main and no_overlay per scene
            scene_final = scenes_dir / f"{scene.id}_final.mp4"
            scene_final_no_overlay = scenes_dir / f"{scene.id}_final_no_overlay.mp4"

            if scene_final.exists() and scene_final_no_overlay.exists():
                logger.info("compose.scene.cached", scene_id=scene.id)
                if i < len(audio_segments):
                    duration = audio_segments[i]["duration_ms"] / 1000.0
                    actual = _get_duration_sec(scene_final)
                    if actual < duration - 0.5:
                        logger.warning(
                            "compose.scene.duration_mismatch",
                            scene_id=scene.id,
                            cached_sec=round(actual, 2),
                            expected_sec=round(duration, 2),
                            hint="Delete cached scene files and rescene to fix subtitle drift",
                        )
                else:
                    duration = _get_duration_sec(scene_final)
            else:
                # Apply duplicate frame guard for clip/still_frame scenes
                scene_dict_guarded, seen_clip_hashes = _apply_duplicate_guard(
                    scene_dict,
                    ctx.video_path,
                    seen_clip_hashes,
                    style_descriptor=style_anchor.style_descriptor,
                )

                # Step 1: Render visual
                try:
                    visual_path = render_scene(
                        scene_dict_guarded,
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

                # Auto-clear edit_mode after successful render
                if (scene.visual or {}).get("edit_mode"):
                    scene.visual["edit_mode"] = False
                    storyboard.save(ctx.storyboard_path)
                    logger.info("compose.edit_mode.cleared", scene_id=scene.id)

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
                visual_path_before_overlay = visual_path
                check_overlay_allowed(
                    scene=scene_dict,
                    overlay=scene.overlay,
                    visual=scene.visual,
                    burn_subtitles=ctx.burn_subtitles,
                )
                if scene.overlay and not ctx.skip_overlays:
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

                self._mux(visual_path, scene_final, audio_path)

                # No-overlay variant: use the pre-overlay visual for scenes that had overlays
                no_overlay_visual = visual_path_before_overlay if scene.overlay else visual_path
                self._mux(no_overlay_visual, scene_final_no_overlay, audio_path)

            scene_finals.append(scene_final)
            scene_finals_no_overlay.append(scene_final_no_overlay)

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
                scene_finals_no_overlay.append(pause_path)

            scene_dur = duration + scene.pause_after_sec
            scenes_data.append({
                "id": scene.id,
                "section": scene.section,
                "start_sec": running_sec,
                "duration_sec": scene_dur,
                "narration": scene.narration,
            })
            running_sec += scene_dur

        (compose_dir / "scenes.json").write_text(
            json.dumps(scenes_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Step 5: Concatenate scene lists — skip whichever raw the locked variant won't use.
        raw_path = compose_dir / "raw.mp4"
        raw_no_overlay_path = compose_dir / "raw_no_overlay.mp4"
        # Default to subtitles_no_overlay so first run builds one variant, not all four.
        # Operator overrides with `compose set-variant` or passes --variant explicitly.
        _pref = ctx.preferred_variant or "subtitles_no_overlay"
        need_plain = "no_overlay" not in _pref
        need_no_overlay = "no_overlay" in _pref
        if need_plain:
            self._concat_scenes(scene_finals, raw_path)
        if need_no_overlay:
            self._concat_scenes(scene_finals_no_overlay, raw_no_overlay_path)

        # Step 6: Produce final variants.
        # When preferred_variant is locked, only build that one (others kept stale on disk).
        locale = ctx.locale
        plain        = compose_dir / f"final_{locale}.mp4"
        plain_no_ov  = compose_dir / f"final_{locale}_no_overlay.mp4"
        subs         = compose_dir / f"final_{locale}_subtitles.mp4"
        subs_no_ov   = compose_dir / f"final_{locale}_subtitles_no_overlay.mp4"

        variant_map = {
            "plain": plain,
            "no_overlay": plain_no_ov,
            "subtitles": subs,
            "subtitles_no_overlay": subs_no_ov,
        }
        preferred = ctx.preferred_variant or "subtitles_no_overlay"

        if preferred in variant_map:
            # Focused mode: only produce the locked variant.
            logger.info("compose.focused_variant", variant=preferred)
            uses_no_overlay = "no_overlay" in preferred
            uses_subtitles = "subtitles" in preferred
            src_raw = raw_no_overlay_path if uses_no_overlay else raw_path
            dst = variant_map[preferred]
            if uses_subtitles and ctx.subtitle_path and ctx.subtitle_path.exists():
                _burn_subtitle_pass(src_raw, dst, ctx.subtitle_path, theme_dict)
            else:
                shutil.copyfile(src_raw, dst)
            final_path = dst
        else:
            # Unreachable in normal flow: `preferred` always falls back to
            # "subtitles_no_overlay" above, which is always in variant_map.
            # Would only trigger on a hand-edited context.json with an unknown variant.
            logger.warning("compose.unknown_variant", variant=preferred)
            shutil.copyfile(raw_no_overlay_path, subs_no_ov)
            final_path = subs_no_ov

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

    @staticmethod
    def _mux(vis: Path, out: Path, aud: Path | None) -> None:
        if aud and aud.exists():
            run_ffmpeg([
                "ffmpeg", "-y",
                "-i", str(vis), "-i", str(aud),
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest",
                str(out),
            ])
        else:
            run_ffmpeg([
                "ffmpeg", "-y",
                "-i", str(vis), "-c:v", "copy", "-an",
                str(out),
            ])

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
        """Concatenate scene segments using ffmpeg concat demuxer (stream-copy video)."""
        # Derive a per-output filename so raw.mp4 → concat_list.txt and
        # raw_no_overlay.mp4 → concat_list_no_overlay.txt stay independent.
        suffix = output.stem[len("raw"):]  # "" or "_no_overlay"
        filelist = output.parent / f"concat_list{suffix}.txt"
        filelist.write_text(
            "\n".join(f"file '{p.resolve()}'" for p in scene_paths),
            encoding="utf-8",
        )
        # Stream-copy video (already H.264); re-encode audio to normalize sample rates
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
                "copy",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-b:a",
                "128k",
                str(output),
            ]
        )
