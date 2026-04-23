from __future__ import annotations

import hashlib
from pathlib import Path

import structlog

from pipeline.composer.base import image_to_video
from pipeline.config import PipelineConfig
from pipeline.providers.base import ImageProvider, ProviderError, try_chain
from pipeline.providers.dalle import DalleImageProvider
from pipeline.providers.gemini import GeminiImageProvider

logger = structlog.get_logger()


def _cache_key(prompt: str) -> str:
    """Generate a cache key from prompt text."""
    return hashlib.md5(prompt.encode()).hexdigest()[:12]


def _build_providers(cfg: PipelineConfig) -> list[ImageProvider]:
    """Build the ordered provider chain from config.

    IMAGE_PROVIDERS="gemini,dalle" yields [Gemini, DALL-E] when both keys
    are configured. Missing keys skip that provider.
    """
    order = [p.strip() for p in cfg.IMAGE_PROVIDERS.split(",") if p.strip()]
    built: list[ImageProvider] = []
    for name in order:
        if name == "gemini" and cfg.GEMINI_API_KEY:
            built.append(GeminiImageProvider(api_key=cfg.GEMINI_API_KEY))
        elif name == "dalle" and cfg.OPENAI_API_KEY:
            built.append(DalleImageProvider(api_key=cfg.OPENAI_API_KEY))
    return built


def _dalle_size(width: int, height: int) -> str:
    """Pick a DALL-E-3 compatible size for the given aspect ratio."""
    if width > height:
        return "1792x1024"
    if height > width:
        return "1024x1792"
    return "1024x1024"


def render_generated_image(
    visual: dict,
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
) -> Path:
    """Generate an image via the configured provider chain, convert to video.

    Caches by prompt hash. Falls back to a text card if no providers are
    configured or all providers fail.
    """
    prompt = visual.get("prompt", "abstract background")
    cache_dir = work_dir / "image_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    ref_raw = visual.get("reference_image")
    reference_image: Path | None = None
    if ref_raw:
        candidate = Path(ref_raw)
        if not candidate.is_absolute():
            candidate = work_dir / ref_raw
        if candidate.exists():
            reference_image = candidate
        else:
            logger.warning("image.reference_missing", reference=str(candidate))

    cache_name = _cache_key(prompt)
    cached_png = cache_dir / f"{cache_name}.png"
    output = work_dir / f"{scene_id}_visual.mp4"

    if cached_png.exists():
        logger.info("image.cache_hit", prompt=prompt[:50], cache=str(cached_png))
    else:
        cfg = PipelineConfig()
        providers = _build_providers(cfg)
        if not providers:
            logger.warning("image.no_providers, falling back to text card")
            return _fallback_text_card(
                prompt, duration_sec, width, height, work_dir, scene_id
            )

        try:
            result = try_chain(
                providers,
                prompt=prompt,
                out_path=cached_png,
                size=_dalle_size(width, height),
                reference_image=reference_image,
            )
            logger.info(
                "image.generated",
                prompt=prompt[:50],
                provider=result.provider,
                with_reference=reference_image is not None,
            )
        except ProviderError as exc:
            logger.warning("image.generation_failed", error=str(exc))
            return _fallback_text_card(
                prompt, duration_sec, width, height, work_dir, scene_id
            )

    image_to_video(cached_png, output, duration_sec, width, height)
    return output


def _fallback_text_card(
    prompt: str,
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
) -> Path:
    from pipeline.composer.text_card import render_text_card

    return render_text_card(
        {"type": "text_card", "text": prompt[:100], "background": "#1a1a2e"},
        duration_sec,
        width,
        height,
        work_dir,
        scene_id,
    )
