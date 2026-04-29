from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

import structlog

from pipeline.composer.base import image_to_video
from pipeline.composer.image_history import save_to_history
from pipeline.providers.base import ProviderError, try_chain
from pipeline.providers.edit_image import EditImageProvider
from pipeline.providers.gen_image import GenImageProvider

logger = structlog.get_logger()


def _cache_key(prompt: str) -> str:
    return hashlib.md5(prompt.encode()).hexdigest()[:12]


def _cache_key_with_seed(prompt: str, seed: int | None) -> str:
    raw = f"{prompt}|{seed}" if seed is not None else prompt
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _size_arg(width: int, height: int) -> str:
    """Map pixel dimensions to gen-image.py size argument."""
    if width > height:
        return "1792x1024"
    if height > width:
        return "1024x1792"
    return "1024x1024"


def _is_too_dark(path: Path, threshold: int = 60) -> bool:
    """Return True if the image average brightness is below threshold (0-255)."""
    try:
        from PIL import Image
        img = Image.open(path).convert("L")
        pixels = list(img.getdata())
        return (sum(pixels) / len(pixels)) < threshold
    except Exception:
        return False


def _find_source_png(scene_id: str, work_dir: Path) -> Path | None:
    p = work_dir / f"{scene_id}_source.png"
    return p if p.exists() else None


def _edit_image(
    visual: dict,
    existing_png: Path,
    combined_prompt: str,
    work_dir: Path,
    scene_id: str,
    width: int,
    height: int,
) -> Path | None:
    edit_type = visual.get("edit_type", "img2img")
    instruction = visual.get("edit_instruction") or combined_prompt
    strength = float(visual.get("edit_strength", 0.3))
    size = _size_arg(width, height)

    cache_key = _cache_key(f"edit|{edit_type}|{instruction}|{existing_png.stat().st_size}")
    out_png = work_dir / "image_cache" / f"{cache_key}.png"
    out_png.parent.mkdir(parents=True, exist_ok=True)

    provider = EditImageProvider()
    try:
        if edit_type == "img2img":
            provider.edit_img2img(existing_png, instruction, strength, out_png, size)
        elif edit_type == "inpaint":
            provider.edit_inpaint(existing_png, instruction, out_png, size)
        else:
            logger.warning("image.edit.unknown_type", edit_type=edit_type)
            return None
        return out_png
    except Exception as exc:
        logger.warning("image.edit.failed", error=str(exc), scene=scene_id)
        return None


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
    style_prefix: str = "",
    seed: int | None = None,
    anchor_image: Path | None = None,
) -> Path:
    """Generate an image, convert to video segment.

    Style is assembled by base.py before this call; style_prefix is kept
    only for tier selection. Falls back to a themed text card on failure.
    """
    prompt = visual.get("prompt", "abstract background")
    # style_prefix already folded into prompt by base.py; kept as param for tier selection
    tier = visual.get("image_tier", "production" if style_prefix else "draft")

    output = work_dir / f"{scene_id}_visual.mp4"
    sidecar = work_dir / f"{scene_id}_source.png"
    restore = work_dir / f"{scene_id}_restore.png"

    # --- Restore override: use history image directly, skip all generation ---
    if restore.exists():
        logger.info("image.restore_override", scene=scene_id)
        shutil.move(str(restore), str(sidecar))
        image_to_video(sidecar, output, duration_sec, width, height)
        return output

    # --- Edit mode: modify existing sidecar via img2img or inpaint ---
    if visual.get("edit_mode"):
        source_png = _find_source_png(scene_id, work_dir)
        if source_png:
            save_to_history(source_png, scene_id, work_dir)
            edited = _edit_image(visual, source_png, prompt, work_dir, scene_id, width, height)
            if edited and edited.exists():
                shutil.copy2(edited, sidecar)
                image_to_video(edited, output, duration_sec, width, height)
                return output
        logger.warning(
            "image.edit_mode.fallback",
            scene=scene_id,
            reason="no source PNG found" if not source_png else "edit failed",
        )

    # --- Normal text-to-image generation ---
    cache_dir = work_dir / "image_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_name = _cache_key_with_seed(prompt, seed)
    cached_png = cache_dir / f"{cache_name}.png"

    if cached_png.exists():
        if _is_too_dark(cached_png):
            logger.warning("image.dark_cache_evicted", scene=scene_id, path=str(cached_png))
            cached_png.unlink()
        else:
            logger.info("image.cache_hit", prompt=prompt[:50])

    if not cached_png.exists():
        provider = GenImageProvider(tier=tier)
        try:
            result = try_chain(
                [provider],
                prompt=prompt,
                out_path=cached_png,
                size=_size_arg(width, height),
            )
            logger.info("image.generated", prompt=prompt[:50], provider=result.provider)
            # Retry once with explicit light-background hint if result is dark
            if _is_too_dark(cached_png):
                logger.warning("image.dark_retry", scene=scene_id)
                cached_png.unlink()
                light_prompt = f"{prompt}, white background, bright cream paper, no dark areas"
                light_key = _cache_key_with_seed(light_prompt, seed)
                light_png = cache_dir / f"{light_key}.png"
                try_chain([provider], prompt=light_prompt, out_path=light_png, size=_size_arg(width, height))
                cached_png = light_png
                logger.info("image.dark_retry_done", scene=scene_id, bright=not _is_too_dark(cached_png))
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

    # Write sidecar for future edit mode use
    if not sidecar.exists():
        shutil.copy2(cached_png, sidecar)

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
    import shutil
    from datetime import date

    from pipeline.utils.gallery import GALLERY_DIR, GalleryEntry, GalleryIndex

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
        origin="gen-image",
        prompt=prompt,
        query=None,
        tags=tags,
        niche=[niche] if niche else [],
        created_at=date.today().isoformat(),
    ))
    idx.save()
