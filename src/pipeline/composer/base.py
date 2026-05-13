from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import structlog

from pipeline.utils.ffmpeg import run_ffmpeg

logger = structlog.get_logger()

# Resolution presets
RESOLUTIONS = {
    "16:9": (1280, 720),
    "9:16": (720, 1280),
}


def get_resolution(aspect_ratio: str) -> tuple[int, int]:
    """Return (width, height) for an aspect ratio string."""
    if aspect_ratio not in RESOLUTIONS:
        raise ValueError(f"Unknown aspect ratio: {aspect_ratio}. Use: {list(RESOLUTIONS)}")
    return RESOLUTIONS[aspect_ratio]


def image_to_video(
    image_path: Path,
    output_path: Path,
    duration_sec: float,
    width: int = 1280,
    height: int = 720,
    camera_motion: dict[str, Any] | None = None,
) -> Path:
    """Convert a static image to a video segment with a slow Ken Burns zoom-in.

    Zooms from 1.0x to at most 1.10x at a constant per-frame rate of 0.0001.
    Scales the image to 1.3x first so zoompan has room without resampling.
    """
    fps = 30
    frames = max(1, int(duration_sec * fps))
    if _is_camera_motion(camera_motion):
        return _camera_motion_to_video(
            image_path,
            output_path,
            camera_motion or {},
            frames=frames,
            fps=fps,
            width=width,
            height=height,
        )

    # Constant zoom speed: 0.0001 per frame -> reaches 10% zoom after ~33s
    zoom_per_frame = 0.0001
    zoom_max = 1.10
    scaled_w = int(width * 1.3)
    scaled_h = int(height * 1.3)
    vf = (
        f"scale={scaled_w}:{scaled_h}:force_original_aspect_ratio=increase,"
        f"crop={scaled_w}:{scaled_h},"
        f"zoompan="
        f"z='min(zoom+{zoom_per_frame},{zoom_max})':"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={width}x{height}:fps={fps}"
    )
    run_ffmpeg(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-t",
            str(duration_sec),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            str(output_path),
        ]
    )
    return output_path


def _is_camera_motion(camera_motion: dict[str, Any] | None) -> bool:
    return bool(
        camera_motion
        and camera_motion.get("type") in {"slow_push_pan", "ken_burns"}
        and isinstance(camera_motion.get("focus_point"), dict)
    )


def _camera_motion_to_video(
    image_path: Path,
    output_path: Path,
    camera_motion: dict[str, Any],
    *,
    frames: int,
    fps: int,
    width: int,
    height: int,
) -> Path:
    from PIL import Image

    source = Image.open(image_path).convert("RGB")
    base, target = _camera_motion_canvas(source, camera_motion, width, height)
    zoom_end = max(1.0, min(4.0, _coerce_float(camera_motion.get("zoom_end"), 1.35)))
    start_center = (width / 2.0, height / 2.0)

    with tempfile.TemporaryDirectory(prefix="camera-motion-") as tmp:
        frame_dir = Path(tmp)
        for idx in range(frames):
            progress = _camera_motion_progress(idx, frames, fps, camera_motion)
            zoom = 1.0 + (zoom_end - 1.0) * progress
            crop_w = width / zoom
            crop_h = height / zoom
            end_center = _clamp_center(target, crop_w, crop_h, width, height)
            center_x = start_center[0] + (end_center[0] - start_center[0]) * progress
            center_y = start_center[1] + (end_center[1] - start_center[1]) * progress
            center_x, center_y = _clamp_center((center_x, center_y), crop_w, crop_h, width, height)
            left = center_x - crop_w / 2.0
            top = center_y - crop_h / 2.0
            right = left + crop_w
            bottom = top + crop_h
            crop_box = (
                max(0, int(round(left))),
                max(0, int(round(top))),
                min(width, int(round(right))),
                min(height, int(round(bottom))),
            )
            frame = base.crop(crop_box).resize(
                (width, height),
                Image.Resampling.BICUBIC,
            )
            frame.save(
                frame_dir / f"frame_{idx:05d}.jpg",
                quality=95,
                subsampling=0,
                optimize=False,
            )

        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                str(fps),
                "-i",
                str(frame_dir / "frame_%05d.jpg"),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(fps),
                str(output_path),
            ]
        )
    return output_path


def _camera_motion_canvas(
    source: Any,
    camera_motion: dict[str, Any] | None,
    width: int,
    height: int,
) -> tuple[Any, tuple[float, float]]:
    from PIL import Image

    base = Image.new("RGB", (width, height), "#18120b")
    scale = min(width / source.width, height / source.height)
    fitted_w = max(1, int(round(source.width * scale)))
    fitted_h = max(1, int(round(source.height * scale)))
    fitted = source.resize((fitted_w, fitted_h), Image.Resampling.LANCZOS)
    pad_x = (width - fitted_w) // 2
    pad_y = (height - fitted_h) // 2
    base.paste(fitted, (pad_x, pad_y))

    focus = (camera_motion or {}).get("focus_point")
    focus_dict = focus if isinstance(focus, dict) else {}
    focus_x = max(0.0, min(1.0, _coerce_float(focus_dict.get("x"), 0.5)))
    focus_y = max(0.0, min(1.0, _coerce_float(focus_dict.get("y"), 0.5)))
    target = (
        float(pad_x) + focus_x * fitted_w,
        float(pad_y) + focus_y * fitted_h,
    )
    return base, target


def _camera_motion_progress(
    frame_idx: int,
    frames: int,
    fps: int,
    camera_motion: dict[str, Any],
) -> float:
    duration_sec = frames / fps
    hold_start = max(0.0, _coerce_float(camera_motion.get("hold_start_sec"), 0.0))
    hold_end = max(0.0, _coerce_float(camera_motion.get("hold_end_sec"), 0.0))
    move = max(0.1, _coerce_float(camera_motion.get("move_sec"), duration_sec))
    total = hold_start + move + hold_end
    if total > duration_sec:
        scale = duration_sec / total
        hold_start *= scale
        move *= scale
    elif "move_sec" not in camera_motion:
        move = max(0.1, duration_sec - hold_start - hold_end)

    time_sec = frame_idx / fps
    if time_sec <= hold_start:
        return 0.0
    if time_sec >= hold_start + move:
        return 1.0
    linear = (time_sec - hold_start) / move
    return linear * linear * (3.0 - 2.0 * linear)


def _clamp_center(
    center: tuple[float, float],
    crop_w: float,
    crop_h: float,
    width: int,
    height: int,
) -> tuple[float, float]:
    half_w = crop_w / 2.0
    half_h = crop_h / 2.0
    return (
        max(half_w, min(width - half_w, center[0])),
        max(half_h, min(height - half_h, center[1])),
    )


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def render_scene(
    scene: dict[str, Any],
    duration_sec: float,
    aspect_ratio: str,
    work_dir: Path,
    source_video: Path | None = None,
    theme: dict | None = None,
) -> Path:
    """Dispatch to the appropriate visual renderer based on scene.visual.type.

    Returns path to the rendered video segment (.mp4).
    """
    visual = scene.get("visual", {})
    visual_type = visual.get("type", "text_card")
    scene_id = scene.get("id", "unknown")
    width, height = get_resolution(aspect_ratio)
    theme = theme or {}

    logger.info("render_scene", scene_id=scene_id, type=visual_type, duration=duration_sec)

    if visual_type == "clip":
        from pipeline.composer.clip import render_clip

        return render_clip(visual, duration_sec, width, height, work_dir, scene_id, source_video)

    elif visual_type == "text_card":
        from pipeline.composer.text_card import render_text_card

        return render_text_card(visual, duration_sec, width, height, work_dir, scene_id, theme)

    elif visual_type == "image_sequence":
        from pipeline.composer.image_sequence import render_image_sequence

        return render_image_sequence(
            visual,
            duration_sec,
            width,
            height,
            work_dir,
            scene_id,
            gallery_path=Path("output/gallery/gallery_index.json"),
            niche=theme.get("niche") if theme else None,
            scene_narration=scene.get("narration", ""),
            theme=theme,
        )

    elif visual_type == "generated_image":
        from pipeline.composer.image import render_generated_image

        # Style hierarchy: theme.visual_style > theme.style_prefix (niche template) > fallback
        base_style = theme.get("visual_style") or theme.get("style_prefix", "")
        modifier = visual.get("style_modifier", "")
        content = visual.get("prompt", "abstract background")

        parts = [p for p in [base_style, modifier, content] if p]
        visual = {**visual, "prompt": ", ".join(parts)}

        seed_raw = theme.get("_seed")
        seed: int | None = int(seed_raw) if seed_raw is not None else None
        anchor_raw = theme.get("_anchor_image")
        anchor_image: Path | None = Path(anchor_raw) if anchor_raw else None

        gallery_path = Path("output/gallery/gallery_index.json")
        return render_generated_image(
            visual,
            duration_sec,
            width,
            height,
            work_dir,
            scene_id,
            gallery_path=gallery_path,
            niche=theme.get("niche"),
            scene_narration=scene.get("narration", ""),
            theme=theme,
            style_prefix=base_style,
            seed=seed,
            anchor_image=anchor_image,
        )

    elif visual_type == "slide":
        from pipeline.composer.slide import render_slide

        return render_slide(visual, duration_sec, width, height, work_dir, scene_id, theme)

    elif visual_type == "rich_slide":
        from pipeline.composer.rich_slide import render_rich_slide

        return render_rich_slide(visual, duration_sec, width, height, work_dir, scene_id, theme)

    elif visual_type == "article_image":
        img_path = Path(visual.get("path", ""))
        if not img_path.exists():
            logger.warning("article_image.missing", path=str(img_path), scene=scene_id)
            from pipeline.composer.text_card import render_text_card

            fallback = {"type": "text_card", "text": visual.get("alt", scene_id)}
            return render_text_card(
                fallback, duration_sec, width, height, work_dir, scene_id, theme
            )
        from pipeline.utils.ffmpeg import verify_is_image

        if not verify_is_image(img_path):
            logger.warning("article_image.invalid", path=str(img_path), scene=scene_id)
            from pipeline.composer.text_card import render_text_card

            fallback = {"type": "text_card", "text": visual.get("alt", scene_id)}
            return render_text_card(
                fallback, duration_sec, width, height, work_dir, scene_id, theme
            )
        output = work_dir / f"{scene_id}_visual.mp4"
        camera_motion = visual.get("camera_motion")
        return image_to_video(
            img_path,
            output,
            duration_sec,
            width,
            height,
            camera_motion=camera_motion if isinstance(camera_motion, dict) else None,
        )

    elif visual_type == "still_frame":
        from pipeline.composer.still_frame import render_still_frame

        return render_still_frame(
            visual, duration_sec, width, height, work_dir, scene_id, source_video
        )

    elif visual_type in ("namecard", "map"):
        from pipeline.composer.text_card import render_text_card

        fallback_visual = {
            "type": "text_card",
            "text": visual.get("name", visual.get("query", visual_type)),
        }
        return render_text_card(
            fallback_visual, duration_sec, width, height, work_dir, scene_id, theme
        )

    else:
        raise ValueError(f"Unknown visual type: {visual_type} in scene {scene_id}")
