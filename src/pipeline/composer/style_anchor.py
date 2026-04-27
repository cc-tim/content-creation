from __future__ import annotations

import base64
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

import structlog

from pipeline.niche_templates import NicheTemplate

logger = structlog.get_logger()

NICHE_ANCHOR_DIR = Path(__file__).parent.parent.parent.parent / "configs" / "niche_anchors"
_HAIKU_MODEL = "claude-haiku-4-5-20251001"  # update when this model ID retires
_FALLBACK_STYLE = "clean illustration, simple composition, warm tones, educational, friendly"


@dataclass
class StyleAnchorResult:
    style_descriptor: str       # 30-word style string to prepend to all image prompts
    seed: int                   # deterministic per-project seed for image generation
    anchor_image: Path | None   # path to niche anchor PNG (None if generation failed)
    suitability: str            # "high" | "medium" | "low" | ""


def _derive_seed(project_id: str) -> int:
    return int(hashlib.md5(project_id.encode()).hexdigest()[:8], 16)


def _synthesize_style(template: NicheTemplate | None, source_hint: str) -> str:
    """Combine niche profile (primary) + source hint (reference). Niche wins."""
    if template:
        base = template.visual_style
        if source_hint:
            return f"{base}, referencing {source_hint}"
        return base
    if source_hint:
        return f"{_FALLBACK_STYLE}, inspired by {source_hint}"
    return _FALLBACK_STYLE


def _extract_source_frame(source_video: Path, work_dir: Path) -> Path | None:
    """Extract a frame at ~10% of source duration. Returns path or None on failure."""
    frame_path = work_dir / "style_source_frame.jpg"
    if frame_path.exists():
        return frame_path
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(source_video)],
            capture_output=True, text=True, check=True,
        )
        duration = float(result.stdout.strip())
        timestamp = max(5.0, duration * 0.10)
        subprocess.run(
            ["ffmpeg", "-ss", str(timestamp), "-i", str(source_video),
             "-vframes", "1", "-q:v", "2", str(frame_path), "-y"],
            check=True, capture_output=True,
        )
        return frame_path
    except Exception as exc:
        logger.warning("style_anchor.frame_extract_failed", error=str(exc))
        return None


def _assess_source(frame_path: Path) -> tuple[str, str]:
    """Return (suitability, source_hint). Calls Claude Haiku with vision."""
    try:
        import anthropic

        from pipeline.config import PipelineConfig  # noqa: PLC0415

        img_bytes = frame_path.read_bytes()
        b64 = base64.standard_b64encode(img_bytes).decode()
        client = anthropic.Anthropic(api_key=PipelineConfig().ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/jpeg", "data": b64,
                    }},
                    {"type": "text", "text": (
                        "Answer in exactly 2 lines:\n"
                        "Line 1: ONE word — is this source footage high, medium, or low quality "
                        "for reuse? (high=unique clean footage, medium=OK but some repetition, "
                        "low=repetitive panels or talking-head or watermarked)\n"
                        "Line 2: Describe the visual style in 10 words max "
                        "(art medium, line style, palette)."
                    )},
                ],
            }],
        )
        lines = resp.content[0].text.strip().splitlines()
        suitability = lines[0].strip().lower() if lines else "medium"
        if suitability not in ("high", "medium", "low"):
            suitability = "medium"
        source_hint = lines[1].strip() if len(lines) > 1 else ""
        return suitability, source_hint
    except Exception as exc:
        logger.warning("style_anchor.assess_failed", error=str(exc))
        return "medium", ""


def _generate_anchor_image(
    anchor_prompt: str, style_descriptor: str, seed: int, out_path: Path
) -> Path | None:
    """Generate one anchor image at production tier. Returns path or None on failure."""
    from pipeline.providers.base import ProviderError
    from pipeline.providers.gen_image import GenImageProvider

    out_path.parent.mkdir(parents=True, exist_ok=True)
    provider = GenImageProvider(tier="production")
    full_prompt = f"{style_descriptor}, {anchor_prompt}"
    try:
        provider.generate(prompt=full_prompt, out_path=out_path, size="1792x1024")
        logger.info("style_anchor.anchor_generated", path=str(out_path))
        return out_path
    except ProviderError as exc:
        logger.warning("style_anchor.anchor_generation_failed", error=str(exc))
        return None


def extract_style_anchor(
    project_id: str,
    niche: str | None,
    template: NicheTemplate | None,
    source_video: Path | None,
    work_dir: Path,
) -> StyleAnchorResult:
    """Orchestrate: source frame → suitability → style descriptor → anchor image.

    Returns a StyleAnchorResult. Fails gracefully — never raises.
    """
    seed = _derive_seed(project_id)

    source_hint = ""
    suitability = "medium"
    if source_video and source_video.exists():
        frame = _extract_source_frame(source_video, work_dir)
        if frame:
            suitability, source_hint = _assess_source(frame)
            logger.info("style_anchor.suitability", value=suitability, hint=source_hint)

    style_descriptor = _synthesize_style(template, source_hint)

    anchor_image: Path | None = None
    if niche:
        anchor_path = NICHE_ANCHOR_DIR / niche / "style_anchor.png"
        if anchor_path.exists():
            logger.info("style_anchor.anchor_reused", niche=niche)
            anchor_image = anchor_path
        elif template:
            anchor_image = _generate_anchor_image(
                anchor_prompt=template.anchor_prompt,
                style_descriptor=style_descriptor,
                seed=seed,
                out_path=anchor_path,
            )

    return StyleAnchorResult(
        style_descriptor=style_descriptor,
        seed=seed,
        anchor_image=anchor_image,
        suitability=suitability,
    )
