from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from PIL import Image

from pipeline.composer.base import get_resolution
from pipeline.composer.book_scene import BookSceneSpec

DEFAULT_THRESHOLD = 0.08
_GEN_IMAGE_EDIT = Path.home() / ".claude" / "bin" / "gen-image-edit.py"


class RefitError(RuntimeError):
    """Raised when a refit strategy fails."""


def canvas_size(storyboard: dict[str, Any]) -> tuple[int, int]:
    """Return the render canvas size for a storyboard dict."""
    return get_resolution(str(storyboard.get("aspect_ratio") or "16:9"))


def target_box(theme: dict[str, Any], canvas_w: int, canvas_h: int) -> tuple[int, int]:
    """Return the target content box for the active frame style."""
    frame_style = theme.get("frame_style") or ""
    if not frame_style:
        return canvas_w, canvas_h
    if frame_style == "open_book_page":
        inset = BookSceneSpec.open_book(canvas_w, canvas_h).inset
        return inset.w, inset.h
    raise ValueError(f"Unknown frame_style for image refit: {frame_style!r}")


def needs_refit(
    src_w: int,
    src_h: int,
    target_w: int,
    target_h: int,
    threshold: float = DEFAULT_THRESHOLD,
) -> bool:
    """Return True when source aspect ratio differs from target by more than threshold."""
    if src_w <= 0 or src_h <= 0 or target_w <= 0 or target_h <= 0:
        raise ValueError("image and target dimensions must be positive")
    src_aspect = src_w / src_h
    target_aspect = target_w / target_h
    return abs(src_aspect - target_aspect) / target_aspect > threshold


def apply_crop(
    source: Path,
    out: Path,
    target_w: int,
    target_h: int,
    bias: tuple[float, float] = (0.5, 0.5),
) -> Path:
    """Crop source to target aspect using a normalized subject bias, then resize."""
    image = Image.open(source).convert("RGB")
    src_w, src_h = image.size
    target_aspect = target_w / target_h
    src_aspect = src_w / src_h
    bx = _clamp01(bias[0])
    by = _clamp01(bias[1])

    if src_aspect > target_aspect:
        crop_h = src_h
        crop_w = max(1, round(crop_h * target_aspect))
        max_left = src_w - crop_w
        left = round(max_left * bx)
        top = 0
    else:
        crop_w = src_w
        crop_h = max(1, round(crop_w / target_aspect))
        left = 0
        max_top = src_h - crop_h
        top = round(max_top * by)

    left = max(0, min(left, src_w - crop_w))
    top = max(0, min(top, src_h - crop_h))
    cropped = image.crop((left, top, left + crop_w, top + crop_h))
    resized = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    resized.save(out)
    return out


def apply_outpaint(
    source: Path,
    out: Path,
    target_w: int,
    target_h: int,
    instruction: str,
) -> Path:
    """Run the shared FAL Kontext helper in outpaint mode."""
    cmd = [
        "python3",
        str(_GEN_IMAGE_EDIT),
        "--source",
        str(source),
        "--instruction",
        instruction,
        "--target-aspect",
        f"{target_w}:{target_h}",
        "--output",
        str(out),
        "--mode",
        "outpaint",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "gen-image-edit.py failed"
        raise RefitError(detail)
    if not out.exists():
        printed = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        printed_path = Path(printed) if printed else out
        if printed_path.exists() and printed_path != out:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(printed_path.read_bytes())
    if not out.exists():
        raise RefitError(f"outpaint output missing: {out}")
    return out


def effective_image_path(visual: dict[str, Any]) -> Path:
    """Return an existing refit sidecar if present; otherwise return the raw source path."""
    refit_path = visual.get("refit_path")
    if refit_path:
        candidate = Path(str(refit_path))
        if candidate.exists():
            return candidate
    return Path(str(visual.get("path", "")))


def aspect_diff(path: Path, target_w: int, target_h: int) -> float:
    """Return normalized aspect diff for a rendered/edit output path."""
    with Image.open(path) as image:
        src_w, src_h = image.size
    target_aspect = target_w / target_h
    return abs((src_w / src_h) - target_aspect) / target_aspect


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
