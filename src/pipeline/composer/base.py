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
    """Convert a static image to a video segment with a slow Ken Burns zoom-in.

    Zooms from 1.0x to at most 1.10x at a constant per-frame rate of 0.0001.
    Scales the image to 1.3x first so zoompan has room without resampling.
    """
    fps = 30
    frames = max(1, int(duration_sec * fps))
    # Constant zoom speed: 0.0001 per frame → reaches 10% zoom after ~33s
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
