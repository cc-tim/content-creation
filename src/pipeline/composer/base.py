from __future__ import annotations

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
) -> Path:
    """Convert a static image to a video segment of given duration.

    Scales/pads the image to exactly width x height, then loops for duration.
    """
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
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            str(output_path),
        ]
    )
    return output_path


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

    elif visual_type == "generated_image":
        from pipeline.composer.image import render_generated_image

        # Append theme image_style to prompt if not already styled
        image_style = theme.get("image_style", "")
        if image_style and "prompt" in visual:
            prompt = visual["prompt"]
            if image_style not in prompt:
                visual = {**visual, "prompt": f"{prompt}. Style: {image_style}"}
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
        )

    elif visual_type == "slide":
        from pipeline.composer.slide import render_slide

        return render_slide(visual, duration_sec, width, height, work_dir, scene_id, theme)

    elif visual_type == "article_image":
        img_path = Path(visual.get("path", ""))
        if not img_path.exists():
            logger.warning("article_image.missing", path=str(img_path), scene=scene_id)
            from pipeline.composer.text_card import render_text_card

            fallback = {"type": "text_card", "text": visual.get("alt", scene_id)}
            return render_text_card(
                fallback, duration_sec, width, height, work_dir, scene_id, theme
            )
        output = work_dir / f"{scene_id}_visual.mp4"
        return image_to_video(img_path, output, duration_sec, width, height)

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
