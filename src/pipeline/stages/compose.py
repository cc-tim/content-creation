from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from pipeline.composer.base import get_resolution, render_scene
from pipeline.composer.compartment import (
    build_compartment_loop,
    composite_compartment_on_scene,
)
from pipeline.composer.frame import composite_scene_frame
from pipeline.composer.overlay import apply_overlay
from pipeline.composer.overlay_rules import check_overlay_allowed
from pipeline.composer.transitions import (
    BOOK_PAGE_STYLES,
    MAX_BOOK_PAGE_COUNT,
    TransitionConfig,
    render_transition,
)
from pipeline.config import PipelineConfig
from pipeline.stages.base import PipelineContext, PipelineStage
from pipeline.storyboard import Storyboard, Transition
from pipeline.utils.ffmpeg import (
    check_ffmpeg_available,
    get_ffmpeg_executor,
    init_ffmpeg_executor,
    run_ffmpeg,
)

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
        "-c:v", "libx264", "-preset", "medium",
        "-b:v", "2000k", "-minrate", "1000k", "-maxrate", "4000k", "-bufsize", "8000k",
        "-c:a", "copy",
        str(dst),
    ])


def _quality_pass(src: Path, dst: Path) -> None:
    """Re-encode with VBV bitrate constraints for YouTube-compliant output.

    CRF-only encoding on static content (slides, Ken Burns) can produce
    <400 kbps; VBV caps ensure adequate bitrate for 720p (2 Mbps target).
    """
    run_ffmpeg([
        "ffmpeg", "-y", "-i", str(src),
        "-c:v", "libx264", "-preset", "medium",
        "-b:v", "2000k", "-minrate", "1000k", "-maxrate", "4000k", "-bufsize", "8000k",
        "-c:a", "copy",
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


def _validate_bitrate(video_path: Path, min_kbps: int = 2000) -> None:
    """Warn if video bitrate is below minimum (720p H.264 needs ~2+ Mbps).

    Low bitrate indicates an encoder preset or CRF mismatch — see
    _burn_subtitle_pass (ultrafast on still-image video can produce <200 kbps).
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=bit_rate",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, check=True,
        )
        bitrate_bps = float(result.stdout.strip())
        bitrate_kbps = bitrate_bps / 1000.0
    except Exception:
        logger.warning("compose.bitrate_check_failed", path=str(video_path))
        return

    if bitrate_kbps < min_kbps:
        logger.warning(
            "compose.bitrate_low",
            kbps=round(bitrate_kbps),
            min_kbps=min_kbps,
            hint="Video may have visible compression artifacts. "
                 "Check encoder preset (should be 'medium', not 'ultrafast') "
                 "and CRF (should be 18-23).",
        )
    else:
        logger.info("compose.bitrate_ok", kbps=round(bitrate_kbps))


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


def splice_transitions(
    *,
    scene_paths: list[Path],
    scene_ids: list[str],
    sb: Storyboard,
    cache_dir: Path,
    width: int,
    height: int,
    fps: int,
) -> list[Path]:
    """Return a new scene-paths list with transition clips spliced between
    adjacent scenes that have a configured transition.

    `scene_paths` and `scene_ids` are parallel lists in render order.
    Looks up transitions in `sb.transitions` keyed by (from_scene, to_scene).
    HardCut transitions (style='none') and missing transitions both result
    in no inserted clip -- adjacent scenes get stitched directly by concat.
    """
    if not sb.transitions:
        return list(scene_paths)
    by_seam: dict[tuple[str, str], Transition] = {
        (t.from_scene, t.to_scene): t for t in sb.transitions
    }
    out: list[Path] = []
    for i, (path, scene_id) in enumerate(zip(scene_paths, scene_ids, strict=True)):
        out.append(path)
        # Look at the seam to the next scene
        if i + 1 < len(scene_ids):
            next_id = scene_ids[i + 1]
            t = by_seam.get((scene_id, next_id))
            if t is None:
                continue
            cfg = TransitionConfig.from_transition(t)
            clip = render_transition(
                scene_paths[i], scene_paths[i + 1], cfg, cache_dir,
                width=width, height=height, fps=fps,
            )
            if clip is not None:
                out.append(clip)
    return out


def _interleave_pauses(
    paths: list[Path],
    pause_paths: dict[int, list[Path]],
    scene_paths: list[Path],
) -> list[Path]:
    """Insert pause paths after their corresponding scene finals.

    `paths` is the output of `splice_transitions` (scene finals + optional
    transition clips in render order). `pause_paths` maps scene index to
    pause files that should appear after that scene's final. `scene_paths`
    is the original scene-finals list (1:1 with scenes, before splicing).

    Pauses are inserted immediately after each scene's final (before any
    transition clip to the next scene).  Returns a new list.
    """
    if not pause_paths:
        return paths

    result: list[Path] = []
    scene_idx = 0
    seen: set[int] = set()
    for path in paths:
        result.append(path)
        if (
            scene_idx < len(scene_paths)
            and path.resolve() == scene_paths[scene_idx].resolve()
            and scene_idx not in seen  # guard: only match once per scene
        ):
            seen.add(scene_idx)
            if scene_idx in pause_paths:
                result.extend(pause_paths[scene_idx])
            scene_idx += 1
    return result


@dataclass
class ComposeSceneResult:
    """Result of rendering one scene. Failures produce black-screen fallbacks."""
    index: int
    scene_final: Path
    scene_final_no_overlay: Path
    pause_paths: list[Path]
    pause_paths_no_overlay: list[Path]


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

        # Validate output bitrate — low bitrate means encoder/preset bug
        _validate_bitrate(final_path)

        logger.info("compose.complete", path=str(final_path))
        return ctx

    async def _compose_from_storyboard(
        self,
        ctx: PipelineContext,
        compose_dir: Path,
    ) -> Path:
        """Scene-by-scene rendering from storyboard with parallel scene rendering."""
        if ctx.mla:
            ctx.preferred_variant = "no_overlay"

        storyboard = Storyboard.load(ctx.storyboard_path)
        width, height = get_resolution(storyboard.aspect_ratio)
        theme_dict = storyboard.theme.to_dict()
        frame_style = theme_dict.get("frame_style") or None

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

        scenes_dir = compose_dir / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)

        # Match audio segments to scenes
        audio_segments = ctx.segment_timings or []

        # === SEQUENTIAL PHASE: pre-compute metadata + duplicate guard ===

        scenes_data, running_sec = self._precompute_scenes_data(
            storyboard, audio_segments,
        )

        scene_dicts = self._precompute_duplicate_guard(
            storyboard, ctx.video_path, style_anchor.style_descriptor,
        )

        # === PARALLEL PHASE: render uncached scenes concurrently ===

        max_workers = PipelineConfig().MAX_COMPOSE_WORKERS
        init_ffmpeg_executor(max_workers)

        tasks: list[asyncio.Task[ComposeSceneResult]] = []
        for i, scene in enumerate(storyboard.scenes):
            if i < len(audio_segments):
                audio_path = Path(audio_segments[i]["path"])
                duration = audio_segments[i]["duration_ms"] / 1000.0
            else:
                duration = scene.narration_est_sec
                audio_path = None

            task = asyncio.create_task(
                self._render_one_scene(
                    i=i,
                    scene=scene,
                    scene_dict=scene_dicts[i],
                    duration=duration,
                    audio_path=audio_path,
                    width=width,
                    height=height,
                    scenes_dir=scenes_dir,
                    source_video=ctx.video_path,
                    theme_dict=theme_dict,
                    frame_style=frame_style,
                    ctx=ctx,
                    audio_segments=audio_segments,
                )
            )
            tasks.append(task)

        done = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results with fallbacks for failed scenes
        results: list[ComposeSceneResult] = []
        failures: list[str] = []
        for i, maybe in enumerate(done):
            if isinstance(maybe, Exception):
                sid = storyboard.scenes[i].id
                logger.error("compose.scene.exception", scene_id=sid, error=str(maybe))
                failures.append(f"{sid}: {maybe}")
                if i < len(audio_segments):
                    d = audio_segments[i]["duration_ms"] / 1000.0
                    ap = Path(audio_segments[i]["path"])
                else:
                    d = storyboard.scenes[i].narration_est_sec
                    ap = None
                sf = scenes_dir / f"{sid}_final.mp4"
                sf_no = scenes_dir / f"{sid}_final_no_overlay.mp4"
                self._mux(
                    self._black_screen(scenes_dir, sid, d, width, height),
                    sf, ap,
                )
                self._mux(
                    self._black_screen(scenes_dir, sid, d, width, height),
                    sf_no, ap,
                )
                results.append(ComposeSceneResult(
                    index=i, scene_final=sf, scene_final_no_overlay=sf_no,
                    pause_paths=[], pause_paths_no_overlay=[],
                ))
            else:
                results.append(maybe)

        if failures:
            logger.warning("compose.scene.errors", count=len(failures), details=failures[:5])

        # Sort by scene index
        results.sort(key=lambda r: r.index)
        scene_finals = [r.scene_final for r in results]
        scene_finals_no_overlay = [r.scene_final_no_overlay for r in results]

        # Reconstruct pause_paths dicts from results
        pause_paths: dict[int, list[Path]] = {}
        pause_paths_no_overlay: dict[int, list[Path]] = {}
        for r in results:
            if r.pause_paths:
                pause_paths[r.index] = r.pause_paths
                pause_paths_no_overlay[r.index] = r.pause_paths_no_overlay

        # Deferred edit_mode clearing (avoids concurrent storyboard writes)
        edit_cleared = False
        for _i, scene in enumerate(storyboard.scenes):
            if scene.visual and (scene.visual or {}).get("edit_mode"):
                scene.visual["edit_mode"] = False
                edit_cleared = True
        if edit_cleared:
            storyboard.save(ctx.storyboard_path)
            logger.info("compose.edit_mode.batch_cleared")

        (compose_dir / "scenes.json").write_text(
            json.dumps(scenes_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # === POST-PROCESSING (must be sequential) ===
        raw_path = compose_dir / "raw.mp4"
        raw_no_overlay_path = compose_dir / "raw_no_overlay.mp4"
        _pref = ctx.preferred_variant or ("subtitles_no_overlay" if ctx.burn_subtitles else "plain")
        need_plain = "no_overlay" not in _pref
        need_no_overlay = "no_overlay" in _pref

        scene_id_seq = [s.id for s in storyboard.scenes]
        transitions_cache = compose_dir / "transitions"
        finals_with_transitions = await self._splice_transitions_async(
            scene_paths=scene_finals,
            scene_ids=scene_id_seq,
            sb=storyboard,
            cache_dir=transitions_cache,
            width=width,
            height=height,
            fps=30,
        )
        finals_no_overlay_with_transitions = await self._splice_transitions_async(
            scene_paths=scene_finals_no_overlay,
            scene_ids=scene_id_seq,
            sb=storyboard,
            cache_dir=transitions_cache,
            width=width,
            height=height,
            fps=30,
        )
        finals_with_transitions = await self._prepend_intro_transition_async(
            scene_paths=finals_with_transitions,
            first_scene=scene_finals[0] if scene_finals else None,
            theme_dict=theme_dict,
            cache_dir=transitions_cache,
            compose_dir=compose_dir,
            width=width,
            height=height,
            fps=30,
        )
        finals_no_overlay_with_transitions = await self._prepend_intro_transition_async(
            scene_paths=finals_no_overlay_with_transitions,
            first_scene=scene_finals_no_overlay[0] if scene_finals_no_overlay else None,
            theme_dict=theme_dict,
            cache_dir=transitions_cache,
            compose_dir=compose_dir,
            width=width,
            height=height,
            fps=30,
        )
        # Interleave pause paths after transition splicing
        finals_with_transitions = _interleave_pauses(
            finals_with_transitions, pause_paths, scene_finals,
        )
        finals_no_overlay_with_transitions = _interleave_pauses(
            finals_no_overlay_with_transitions, pause_paths_no_overlay, scene_finals_no_overlay,
        )

        if need_plain:
            self._concat_scenes(finals_with_transitions, raw_path)
        if need_no_overlay:
            self._concat_scenes(finals_no_overlay_with_transitions, raw_no_overlay_path)

        # Step 6: Produce final variants.
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
        preferred = ctx.preferred_variant or ("subtitles_no_overlay" if ctx.burn_subtitles else "plain")

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
                # Re-encode with VBV bitrate constraints instead of shutil.copyfile
                _quality_pass(src_raw, dst)
            final_path = dst
        else:
            logger.warning("compose.unknown_variant", variant=preferred)
            _quality_pass(raw_no_overlay_path, subs_no_ov)
            final_path = subs_no_ov

        return final_path

    @staticmethod
    def _precompute_scenes_data(
        storyboard: Storyboard,
        audio_segments: list[dict],
    ) -> tuple[list[dict[str, object]], float]:
        """Build scenes_data and running_sec from storyboard + audio timings.

        Pure function — does not depend on render output, so it can be computed
        before the parallel rendering phase.
        """
        scenes_data: list[dict[str, object]] = []
        running_sec = 0.0
        for i, scene in enumerate(storyboard.scenes):
            if i < len(audio_segments):
                duration = audio_segments[i]["duration_ms"] / 1000.0
            else:
                duration = scene.narration_est_sec
            scene_dur = duration + scene.pause_after_sec
            scenes_data.append({
                "id": scene.id,
                "section": scene.section,
                "start_sec": running_sec,
                "duration_sec": scene_dur,
                "narration": scene.narration,
            })
            running_sec += scene_dur
        return scenes_data, running_sec

    @staticmethod
    def _precompute_duplicate_guard(
        storyboard: Storyboard,
        source_video: Path | None,
        style_descriptor: str,
    ) -> list[dict[str, Any]]:
        """Run duplicate frame detection on all clip/still_frame scenes upfront.

        This MUST be sequential (seen_clip_hashes is cross-scene mutable state).
        Returns scene_dict list with guards applied, ready for parallel rendering.
        """
        seen_clip_hashes: set = set()
        scene_dicts: list[dict[str, Any]] = []
        for scene in storyboard.scenes:
            sd = {
                "id": scene.id,
                "visual": scene.visual,
                "overlay": scene.overlay,
                "compartment": scene.compartment,
                "narration": scene.narration,
            }
            guarded, seen_clip_hashes = _apply_duplicate_guard(
                sd, source_video, seen_clip_hashes,
                style_descriptor=style_descriptor,
            )
            scene_dicts.append(guarded)
        return scene_dicts

    async def _render_one_scene(
        self,
        i: int,
        scene: Any,  # StoryboardScene
        scene_dict: dict[str, Any],
        duration: float,
        audio_path: Path | None,
        width: int,
        height: int,
        scenes_dir: Path,
        source_video: Path | None,
        theme_dict: dict[str, str],
        frame_style: str | None,
        ctx: PipelineContext,
        audio_segments: list[dict],
    ) -> ComposeSceneResult:
        """Render one complete scene (visual → compartment → overlay → mux).

        Runs the synchronous render chain in the shared thread pool so the
        event loop stays free.  Scene-internal steps remain sequential;
        concurrency is across scenes.

        Never raises: failures produce black-screen fallback paths.
        """
        frame_suffix = f"_{frame_style}" if frame_style else ""
        scene_final = scenes_dir / f"{scene.id}_final{frame_suffix}.mp4"
        scene_final_no_overlay = scenes_dir / f"{scene.id}_final_no_overlay{frame_suffix}.mp4"

        # Cache check
        if scene_final.exists() and scene_final_no_overlay.exists():
            logger.info("compose.scene.cached", scene_id=scene.id)
            if i < len(audio_segments):
                d_check = audio_segments[i]["duration_ms"] / 1000.0
                actual = _get_duration_sec(scene_final)
                if actual < d_check - 0.5:
                    logger.warning(
                        "compose.scene.duration_mismatch",
                        scene_id=scene.id,
                        cached_sec=round(actual, 2),
                        expected_sec=round(d_check, 2),
                        hint="Delete cached scene files and rescene to fix subtitle drift",
                    )
            pause_paths_c: list[Path] = []
            if scene.pause_after_sec > 0:
                pause_paths_c = [
                    self._silence_gap(scenes_dir, scene.id, scene.pause_after_sec, width, height)
                ]
            return ComposeSceneResult(
                index=i,
                scene_final=scene_final,
                scene_final_no_overlay=scene_final_no_overlay,
                pause_paths=pause_paths_c,
                pause_paths_no_overlay=list(pause_paths_c),
            )

        logger.info("compose.scene", scene_id=scene.id, duration=f"{duration:.1f}s")

        loop = asyncio.get_running_loop()
        executor = get_ffmpeg_executor()

        def _render_sync() -> tuple[Path, Path, Path | None, Path | None]:
            """Synchronous scene render — runs in thread pool via run_in_executor."""
            # Step 1: Render visual
            try:
                vis = render_scene(
                    scene_dict,
                    duration,
                    "16:9",  # aspect_ratio default; storyboard-driven is 16:9
                    scenes_dir,
                    source_video=source_video,
                    theme=theme_dict,
                )
            except Exception as e:
                logger.warning("compose.scene.visual_failed", scene_id=scene.id, error=str(e))
                vis = self._black_screen(scenes_dir, scene.id, duration, width, height)

            # Step 1b: Compartment animation
            if scene.compartment:
                try:
                    comp_vid = build_compartment_loop(
                        compartment=scene.compartment,
                        scene_duration_sec=duration,
                        scene_width=width,
                        scene_height=height,
                        work_dir=scenes_dir,
                        scene_id=scene.id,
                    )
                    vis = composite_compartment_on_scene(
                        scene_video=vis,
                        compartment_video=comp_vid,
                        compartment_config=scene.compartment,
                        scene_width=width,
                        scene_height=height,
                        work_dir=scenes_dir,
                        scene_id=scene.id,
                    )
                except Exception as e:
                    logger.warning(
                        "compose.scene.compartment_failed", scene_id=scene.id, error=str(e),
                    )

            # Step 2: Overlay
            vis_before_overlay = vis
            check_overlay_allowed(
                scene=scene_dict,
                overlay=scene.overlay,
                visual=scene.visual,
                burn_subtitles=ctx.burn_subtitles,
            )
            if scene.overlay and not ctx.skip_overlays:
                try:
                    vis = apply_overlay(
                        visual_path=vis,
                        overlay=scene.overlay,
                        width=width, height=height,
                        work_dir=scenes_dir,
                        scene_id=scene.id,
                        theme=theme_dict,
                    )
                except Exception as e:
                    logger.warning(
                        "compose.scene.overlay_failed", scene_id=scene.id, error=str(e),
                    )

            # Step 3: Mux both variants
            if frame_style:
                vis = composite_scene_frame(
                    vis,
                    scenes_dir / f"{scene.id}_visual{frame_suffix}.mp4",
                    frame_style=frame_style,
                    width=width,
                    height=height,
                )
                vis_before_overlay = composite_scene_frame(
                    vis_before_overlay,
                    scenes_dir / f"{scene.id}_visual_no_overlay{frame_suffix}.mp4",
                    frame_style=frame_style,
                    width=width,
                    height=height,
                )
            self._mux(vis, scene_final, audio_path)
            no_overlay_vis = vis_before_overlay if scene.overlay else vis
            self._mux(no_overlay_vis, scene_final_no_overlay, audio_path)

            # Step 4: Pause gap
            pause: Path | None = None
            if scene.pause_after_sec > 0:
                pause = self._silence_gap(
                    scenes_dir, scene.id, scene.pause_after_sec, width, height,
                )
            return scene_final, scene_final_no_overlay, pause, pause

        try:
            final, final_no_ov, pause, pause_no = await loop.run_in_executor(
                executor, _render_sync,
            )
        except Exception as e:
            logger.error("compose.scene.catastrophic_failure", scene_id=scene.id, error=str(e))
            self._mux(
                self._black_screen(scenes_dir, scene.id, duration, width, height),
                scene_final, audio_path,
            )
            self._mux(
                self._black_screen(scenes_dir, scene.id, duration, width, height),
                scene_final_no_overlay, audio_path,
            )
            final = scene_final
            final_no_ov = scene_final_no_overlay
            pause = None
            pause_no = None

        pause_paths_c = [pause] if pause else []
        pause_paths_no_c = [pause_no] if pause_no else []
        return ComposeSceneResult(
            index=i,
            scene_final=final,
            scene_final_no_overlay=final_no_ov,
            pause_paths=pause_paths_c,
            pause_paths_no_overlay=pause_paths_no_c,
        )

    @staticmethod
    async def _splice_transitions_async(
        *,
        scene_paths: list[Path],
        scene_ids: list[str],
        sb: Storyboard,
        cache_dir: Path,
        width: int,
        height: int,
        fps: int,
    ) -> list[Path]:
        """Same as splice_transitions but renders transition clips in parallel."""
        if not sb.transitions:
            return list(scene_paths)
        by_seam: dict[tuple[str, str], Transition] = {
            (t.from_scene, t.to_scene): t for t in sb.transitions
        }
        loop = asyncio.get_running_loop()
        executor = get_ffmpeg_executor()

        # Launch all transition renders in parallel
        seam_tasks: list[tuple[int, asyncio.Task[Path | None]]] = []
        for i in range(len(scene_paths) - 1):
            scene_id = scene_ids[i]
            next_id = scene_ids[i + 1]
            t = by_seam.get((scene_id, next_id))
            if t is None:
                continue
            cfg = TransitionConfig.from_transition(t)

            async def _render_one_transition(
                a: Path, b: Path, c: TransitionConfig, d: Path, w: int, h: int, fps_: int,
            ) -> Path | None:
                return await loop.run_in_executor(
                    executor,
                    lambda: render_transition(a, b, c, d, width=w, height=h, fps=fps_),
                )

            task = asyncio.create_task(
                _render_one_transition(
                    scene_paths[i], scene_paths[i + 1], cfg, cache_dir,
                    width, height, fps,
                )
            )
            seam_tasks.append((i, task))

        # Wait for all, map back to position
        clip_by_seam: dict[int, Path | None] = {}
        for after_idx, task in seam_tasks:
            clip_by_seam[after_idx] = await task

        # Build output list
        out: list[Path] = []
        for i, path in enumerate(scene_paths):
            out.append(path)
            clip = clip_by_seam.get(i)
            if clip is not None:
                out.append(clip)
        return out

    async def _prepend_intro_transition_async(
        self,
        *,
        scene_paths: list[Path],
        first_scene: Path | None,
        theme_dict: dict[str, str],
        cache_dir: Path,
        compose_dir: Path,
        width: int,
        height: int,
        fps: int,
    ) -> list[Path]:
        style = theme_dict.get("intro_transition_style") or ""
        if not style or first_scene is None or not scene_paths:
            return scene_paths

        duration_raw = theme_dict.get("intro_transition_duration_sec") or "0.9"
        page_count_raw = theme_dict.get("intro_transition_page_count") or "2"
        try:
            duration = float(duration_raw)
        except ValueError:
            duration = 0.9
        try:
            page_count = max(1, min(MAX_BOOK_PAGE_COUNT, int(page_count_raw)))
        except ValueError:
            page_count = 2

        intro_src = self._book_start_plate(compose_dir, width, height, fps, duration)
        cfg = TransitionConfig(
            style=style,
            duration_sec=duration,
            sfx=None,
            page_count=page_count if style in BOOK_PAGE_STYLES else None,
            renderer_mode=theme_dict.get("intro_transition_renderer_mode") or None,
            asset_path=theme_dict.get("intro_transition_asset_path") or None,
            asset_source=theme_dict.get("intro_transition_asset_source") or None,
            asset_source_url=theme_dict.get("intro_transition_asset_source_url") or None,
            asset_license=theme_dict.get("intro_transition_asset_license") or None,
            asset_notes=theme_dict.get("intro_transition_asset_notes") or None,
        )
        loop = asyncio.get_running_loop()
        executor = get_ffmpeg_executor()
        clip = await loop.run_in_executor(
            executor,
            lambda: render_transition(
                intro_src,
                first_scene,
                cfg,
                cache_dir,
                width=width,
                height=height,
                fps=fps,
            ),
        )
        if clip is None:
            return scene_paths
        return [clip, *scene_paths]

    def _book_start_plate(
        self,
        compose_dir: Path,
        width: int,
        height: int,
        fps: int,
        duration: float,
    ) -> Path:
        output = compose_dir / f"book_start_plate_{duration:.2f}.mp4"
        if output.exists():
            return output
        base_h = max(36, int(height * 0.09))
        run_ffmpeg([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=#2b1f14:s={width}x{height}:r={fps}:d={duration}",
            "-vf",
            (
                f"drawbox=x={int(width * 0.09)}:y={int(height * 0.18)}:"
                f"w={int(width * 0.82)}:h={int(height * 0.63)}:"
                f"color=#5b2e19@0.96:t=fill,"
                f"drawbox=x={int(width * 0.09)}:y={int(height * 0.18)}:"
                f"w={int(width * 0.82)}:h={int(height * 0.63)}:"
                f"color=#c79749@0.72:t=8,"
                f"drawbox=x={int(width * 0.055)}:y={height - base_h}:"
                f"w={int(width * 0.89)}:h={max(8, base_h // 3)}:"
                f"color=#6f3f1e@0.92:t=fill"
            ),
            "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "22",
            "-pix_fmt", "yuv420p", "-r", str(fps),
            str(output),
        ])
        return output

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
