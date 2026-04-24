from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

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
                scene_narration or prompt, duration_sec, width, height, work_dir, scene_id, theme
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
            if gallery_path is not None:
                _write_to_gallery(
                    image_path=cached_png,
                    prompt=prompt,
                    gallery_path=gallery_path,
                    niche=niche or "",
                    scene_narration=scene_narration,
                )
        except ProviderError as exc:
            logger.warning("image.generation_failed", error=str(exc))
            return _fallback_text_card(
                scene_narration or prompt, duration_sec, width, height, work_dir, scene_id, theme
            )

    image_to_video(cached_png, output, duration_sec, width, height)
    return output


def _fallback_text_card(
    text: str,
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
    theme: dict | None = None,
) -> Path:
    from pipeline.composer.text_card import render_text_card

    t = theme or {}
    bg = t.get("secondary_bg") or t.get("background") or "#f0e8d8"
    return render_text_card(
        {"type": "text_card", "text": text[:200], "background": bg},
        duration_sec,
        width,
        height,
        work_dir,
        scene_id,
        t,
    )


def _write_to_gallery(
    image_path: Path,
    prompt: str,
    gallery_path: Path,
    niche: str,
    scene_narration: str,
) -> None:
    """Append a successfully generated image to the global gallery index."""
    import shutil
    from datetime import date
    from pipeline.utils.gallery import GalleryEntry, GalleryIndex, GALLERY_DIR

    gallery_images_dir = GALLERY_DIR / "images"
    gallery_images_dir.mkdir(parents=True, exist_ok=True)

    entry_id = hashlib.md5(prompt.encode()).hexdigest()[:12]
    dest = gallery_images_dir / f"{entry_id}.png"

    if not dest.exists():
        shutil.copy2(image_path, dest)

    stop_words = {"a", "an", "the", "of", "in", "for", "with", "and", "or", "is", "are"}
    words = (prompt + " " + scene_narration).lower().split()
    tags = list(dict.fromkeys(w for w in words if len(w) > 3 and w not in stop_words))[:8]

    idx = GalleryIndex.load(gallery_path)
    if any(e.id == entry_id for e in idx.entries):
        return
    idx.append(GalleryEntry(
        id=entry_id,
        path=str(dest),
        type="image",
        origin="dalle",
        prompt=prompt,
        query=None,
        tags=tags,
        niche=[niche] if niche else [],
        created_at=date.today().isoformat(),
    ))
    idx.save()
