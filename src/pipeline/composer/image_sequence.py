"""Image sequence renderer: generates N images in order, each with Ken Burns,
concatenated into a single video segment for the scene duration.

Storyboard visual format:
  {
    "type": "image_sequence",
    "images": [
      {"prompt": "...", "weight": 1},   # weight controls relative duration
      {"prompt": "...", "weight": 1},
      {"prompt": "...", "weight": 1}
    ]
  }
Duration is split proportionally by weight (default 1 each = equal split).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import structlog

from pipeline.composer.base import image_to_video
from pipeline.providers.base import ProviderError, try_chain
from pipeline.providers.gen_image import GenImageProvider
from pipeline.utils.ffmpeg import run_ffmpeg

logger = structlog.get_logger()


def _cache_key(prompt: str) -> str:
    return hashlib.md5(prompt.encode()).hexdigest()[:12]


def _size_arg(width: int, height: int) -> str:
    if width > height:
        return "1792x1024"
    if height > width:
        return "1024x1792"
    return "1024x1024"


def _is_too_dark(path: Path, threshold: int = 60) -> bool:
    try:
        from PIL import Image
        img = Image.open(path).convert("L")
        pixels = list(img.getdata())
        return (sum(pixels) / len(pixels)) < threshold
    except Exception:
        return False


def _fetch_image(
    prompt: str,
    tier: str,
    cache_dir: Path,
    scene_id: str,
    idx: int,
    width: int,
    height: int,
) -> Path | None:
    cache_name = _cache_key(prompt)
    cached_png = cache_dir / f"{cache_name}.png"

    if cached_png.exists():
        if _is_too_dark(cached_png):
            logger.warning("image_seq.dark_evicted", scene=scene_id, idx=idx)
            cached_png.unlink()
        else:
            logger.info("image_seq.cache_hit", scene=scene_id, idx=idx, prompt=prompt[:50])
            return cached_png

    provider = GenImageProvider(tier=tier)
    try:
        result = try_chain(
            [provider],
            prompt=prompt,
            out_path=cached_png,
            size=_size_arg(width, height),
        )
        logger.info("image_seq.generated", scene=scene_id, idx=idx, provider=result.provider)
        if _is_too_dark(cached_png):
            cached_png.unlink()
            light_prompt = f"{prompt}, white background, bright cream paper, no dark areas"
            light_png = cache_dir / f"{_cache_key(light_prompt)}.png"
            try_chain([provider], prompt=light_prompt, out_path=light_png, size=_size_arg(width, height))
            cached_png = light_png
        return cached_png
    except ProviderError as exc:
        logger.warning("image_seq.generation_failed", scene=scene_id, idx=idx, error=str(exc))
        return None


def _black_clip(work_dir: Path, scene_id: str, idx: int, duration: float, width: int, height: int) -> Path:
    out = work_dir / f"{scene_id}_seq{idx}_visual.mp4"
    run_ffmpeg([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=black:s={width}x{height}:d={duration}:r=30",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
        str(out),
    ])
    return out


def render_image_sequence(
    visual: dict[str, Any],
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
    gallery_path: Path | None = None,
    niche: str | None = None,
    scene_narration: str = "",
    theme: dict | None = None,
) -> Path:
    images = visual.get("images", [])
    if not images:
        raise ValueError(f"image_sequence in scene {scene_id} has no images list")

    total_weight = sum(img.get("weight", 1) for img in images)
    cache_dir = work_dir / "image_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    image_style = (theme or {}).get("image_style", "")

    clip_paths: list[Path] = []
    for idx, img_spec in enumerate(images):
        weight = img_spec.get("weight", 1)
        clip_dur = duration_sec * weight / total_weight

        prompt = img_spec.get("prompt", "abstract background")
        if image_style and image_style not in prompt:
            prompt = f"{prompt}. Style: {image_style}"

        tier = img_spec.get("image_tier", "draft")
        png = _fetch_image(prompt, tier, cache_dir, scene_id, idx, width, height)

        clip_path = work_dir / f"{scene_id}_seq{idx}_visual.mp4"
        if png:
            image_to_video(png, clip_path, clip_dur, width, height)
        else:
            clip_path = _black_clip(work_dir, scene_id, idx, clip_dur, width, height)
        clip_paths.append(clip_path)

    output = work_dir / f"{scene_id}_visual.mp4"

    if len(clip_paths) == 1:
        import shutil
        shutil.copy2(clip_paths[0], output)
        return output

    concat_txt = work_dir / f"{scene_id}_seq_concat.txt"
    with concat_txt.open("w") as f:
        for cp in clip_paths:
            f.write(f"file '{cp.resolve()}'\n")

    run_ffmpeg([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-c", "copy",
        str(output),
    ])
    return output
