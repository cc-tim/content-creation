from __future__ import annotations

import hashlib
from pathlib import Path

import structlog

from pipeline.composer.base import image_to_video
from pipeline.config import PipelineConfig

logger = structlog.get_logger()


def _cache_key(prompt: str) -> str:
    """Generate a cache key from prompt text."""
    return hashlib.md5(prompt.encode()).hexdigest()[:12]


def _download_dalle_image(prompt: str, output_path: Path, width: int, height: int) -> Path:
    """Call OpenAI DALL-E API to generate an image."""
    from openai import OpenAI

    config = PipelineConfig()
    client = OpenAI(api_key=config.OPENAI_API_KEY)

    # DALL-E 3 supports 1024x1024, 1024x1792, 1792x1024
    if width > height:
        size = "1792x1024"
    elif height > width:
        size = "1024x1792"
    else:
        size = "1024x1024"

    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size=size,
        quality="standard",
        n=1,
    )

    image_url = response.data[0].url

    # Download the image
    import urllib.request

    urllib.request.urlretrieve(image_url, str(output_path))

    return output_path


def render_generated_image(
    visual: dict,
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
) -> Path:
    """Generate an image via DALL-E, convert to video segment.

    Caches by prompt hash. Falls back to a placeholder if API unavailable.
    """
    prompt = visual.get("prompt", "abstract background")
    cache_dir = work_dir / "image_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_name = _cache_key(prompt)
    cached_png = cache_dir / f"{cache_name}.png"
    output = work_dir / f"{scene_id}_visual.mp4"

    if cached_png.exists():
        logger.info("image.cache_hit", prompt=prompt[:50], cache=str(cached_png))
    else:
        config = PipelineConfig()
        if not config.OPENAI_API_KEY:
            logger.warning("image.no_api_key, falling back to text card")
            from pipeline.composer.text_card import render_text_card

            return render_text_card(
                {"type": "text_card", "text": prompt[:100], "background": "#1a1a2e"},
                duration_sec,
                width,
                height,
                work_dir,
                scene_id,
            )

        try:
            _download_dalle_image(prompt, cached_png, width, height)
            logger.info("image.generated", prompt=prompt[:50])
        except Exception as e:
            logger.warning("image.generation_failed", error=str(e))
            from pipeline.composer.text_card import render_text_card

            return render_text_card(
                {"type": "text_card", "text": prompt[:100], "background": "#1a1a2e"},
                duration_sec,
                width,
                height,
                work_dir,
                scene_id,
            )

    image_to_video(cached_png, output, duration_sec, width, height)
    return output
