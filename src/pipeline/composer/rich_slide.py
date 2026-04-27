"""Rich slide renderer: AI background image + Pillow text compositor.

Supports two layouts:
  slide  — title + bullet list + optional footer (for comparison/fact scenes)
  quote  — large centred quote block (for text_card-style scenes)

Both begin from the visual dict that the storyboard carries.  The visual type
in the storyboard is ``rich_slide``; a ``layout`` sub-key selects the mode.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from pipeline.composer.base import image_to_video

logger = structlog.get_logger()

# ── Font paths ────────────────────────────────────────────────────────────────
_SANS_REGULAR = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
_SANS_BOLD    = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")
_SERIF_REGULAR = Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc")
_SERIF_BOLD    = Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc")
_TC_INDEX = 4   # Noto CJK TTC index order: JP=0, HK=1, KR=2, SC=3, TC=4


def _load_font(path: Path, size: int, index: int = _TC_INDEX):
    from PIL import ImageFont
    return ImageFont.truetype(str(path), size=size, index=index)


def _wrap_text(text: str, font, max_width: int, draw) -> list[str]:
    """Word-wrap text to fit max_width pixels."""
    lines: list[str] = []
    for para in text.split("\n"):
        current = ""
        for char in para:
            test = current + char
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] > max_width and current:
                lines.append(current)
                current = char
            else:
                current = test
        if current:
            lines.append(current)
    return lines


def _hex(color: str) -> tuple[int, int, int]:
    h = color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _gradient_overlay(img, y_start: float, y_end: float, alpha_top: int, alpha_bottom: int) -> None:
    """Paint a vertical gradient (dark overlay) using RGBA compositing."""
    from PIL import Image
    w, h = img.size
    ys = int(h * y_start)
    ye = int(h * y_end)
    span = max(ye - ys, 1)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    px = overlay.load()
    for y in range(ys, ye):
        a = int(alpha_top + (alpha_bottom - alpha_top) * (y - ys) / span)
        for x in range(w):
            px[x, y] = (10, 8, 30, a)

    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))


def _ensure_bg_image(
    bg_prompt: str,
    width: int,
    height: int,
    cache_dir: Path,
    scene_id: str,
    theme: dict,
) -> Path:
    """Generate or load the background image (PNG)."""
    import hashlib
    from pipeline.providers.base import ProviderError, try_chain
    from pipeline.providers.gen_image import GenImageProvider

    image_style = theme.get("image_style", "")
    if image_style and image_style not in bg_prompt:
        prompt = f"{bg_prompt}. Style: {image_style}"
    else:
        prompt = bg_prompt

    cache_name = hashlib.md5(prompt.encode()).hexdigest()[:12]
    cached_png = cache_dir / f"{cache_name}.png"

    if not cached_png.exists():
        size = "1792x1024" if width > height else "1024x1792"
        provider = GenImageProvider(tier="draft")
        try:
            try_chain([provider], prompt=prompt, out_path=cached_png, size=size)
            logger.info("rich_slide.image_generated", scene=scene_id)
        except ProviderError as exc:
            logger.warning("rich_slide.image_failed", scene=scene_id, error=str(exc))
            # Fallback: plain themed background
            from PIL import Image as PILImage
            r, g, b = _hex(theme.get("secondary_bg", "#f0e8d8"))
            PILImage.new("RGB", (width, height), (r, g, b)).save(cached_png)
    else:
        logger.info("rich_slide.image_cache_hit", scene=scene_id)

    return cached_png


def render_rich_slide(
    visual: dict[str, Any],
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
    theme: dict | None = None,
) -> Path:
    """Render an AI-backed rich slide and return path to the .mp4 segment."""
    from PIL import Image, ImageDraw

    theme = theme or {}
    layout = visual.get("layout", "quote")   # "slide" or "quote"
    bg_prompt = visual.get("bg_prompt", "soft abstract background, warm tones")

    cache_dir = work_dir / "image_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    bg_path = _ensure_bg_image(bg_prompt, width, height, cache_dir, scene_id, theme)

    # Load and scale background
    bg = Image.open(bg_path).convert("RGB")
    bg = bg.resize((width, height), Image.LANCZOS)

    # Gradient overlay on lower portion so text is legible
    _gradient_overlay(bg, y_start=0.35, y_end=1.0, alpha_top=0, alpha_bottom=210)

    draw = ImageDraw.Draw(bg)
    accent = _hex(theme.get("accent", "#6b62c5"))
    white = (248, 246, 242)
    muted = (160, 155, 180)

    pad_x = int(width * 0.07)
    text_w = width - pad_x * 2

    if layout == "slide":
        _render_slide_layout(draw, visual, width, height, pad_x, text_w, accent, white, muted)
    else:
        _render_quote_layout(draw, visual, width, height, pad_x, text_w, accent, white, muted)

    # Save composite PNG → video
    composite_png = work_dir / f"{scene_id}_rich.png"
    bg.save(composite_png)

    output = work_dir / f"{scene_id}_visual.mp4"
    image_to_video(composite_png, output, duration_sec, width, height)
    return output


def _render_slide_layout(draw, visual, width, height, pad_x, text_w, accent, white, muted):
    """Title + bullets + footer."""
    from PIL import ImageDraw as ID

    title   = visual.get("title", "")
    bullets = visual.get("bullets", [])
    footer  = visual.get("footer") or ""

    # Layout: start from 40% height
    y = int(height * 0.42)
    line_gap = 10

    # Accent rule
    draw.rectangle([pad_x, y - 4, pad_x + 60, y], fill=accent)
    y += 14

    # Title
    title_font = _load_font(_SERIF_BOLD, 44)
    wrapped = _wrap_text(title, title_font, text_w, draw)
    for line in wrapped:
        draw.text((pad_x, y), line, font=title_font, fill=accent + (255,) if len(accent) == 3 else accent)
        bbox = draw.textbbox((0, 0), line, font=title_font)
        y += bbox[3] - bbox[1] + line_gap
    y += 18

    # Bullets
    bullet_font = _load_font(_SANS_REGULAR, 32)
    for bullet in bullets:
        # Bullet dot
        dot_y = y + 12
        draw.ellipse([pad_x, dot_y, pad_x + 10, dot_y + 10], fill=(*accent, 255))
        lines = _wrap_text(bullet, bullet_font, text_w - 24, draw)
        for i, line in enumerate(lines):
            draw.text((pad_x + 22, y), line, font=bullet_font, fill=white)
            bbox = draw.textbbox((0, 0), line, font=bullet_font)
            y += bbox[3] - bbox[1] + line_gap
        y += 10

    # Footer
    if footer:
        footer_font = _load_font(_SANS_REGULAR, 26)
        y += 8
        draw.line([pad_x, y, pad_x + 80, y], fill=(*muted, 180), width=1)
        y += 12
        lines = _wrap_text(footer, footer_font, text_w, draw)
        for line in lines:
            draw.text((pad_x, y), line, font=footer_font, fill=muted)
            bbox = draw.textbbox((0, 0), line, font=footer_font)
            y += bbox[3] - bbox[1] + 8


def _render_quote_layout(draw, visual, width, height, pad_x, text_w, accent, white, muted):
    """Large centred quote block."""
    text = visual.get("text", "")

    quote_font = _load_font(_SERIF_REGULAR, 38)
    lines = _wrap_text(text, quote_font, text_w, draw)

    total_h = 0
    line_gap = 14
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=quote_font)
        lh = bbox[3] - bbox[1]
        line_heights.append(lh)
        total_h += lh + line_gap

    # Vertically centre in lower 55% of frame; leave 25% at bottom for subtitles.
    zone_top = int(height * 0.42)
    zone_h   = height - zone_top - int(height * 0.25)
    y = zone_top + max(0, (zone_h - total_h) // 2)

    # Decorative left rule
    rule_h = total_h
    draw.rectangle([pad_x, y, pad_x + 4, y + rule_h], fill=(*accent, 200))

    text_x = pad_x + 18
    for line, lh in zip(lines, line_heights):
        draw.text((text_x, y), line, font=quote_font, fill=white)
        y += lh + line_gap
