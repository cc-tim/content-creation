from __future__ import annotations

from pathlib import Path

import imagehash
from PIL import Image

from pipeline.composer.base import get_resolution
from pipeline.composer.book_scene import BookSceneSpec
from pipeline.director.still_gate.model import Finding

# Hamming distance <= this means "the same delivered frame" for phash(hash_size=8).
_DUP_PHASH_MAX = 4
# colorhash distance <= this additionally confirms color-domain similarity.
# colorhash of 0 = identical palette; 6 = clearly different hue bucket.
_DUP_COLORHASH_MAX = 3


def _is_duplicate(
    h_p: object, h_c: object, ph: object, ch: object
) -> bool:
    """True when both perceptual structure AND color palette are near-identical."""
    return (h_p - ph) <= _DUP_PHASH_MAX and (h_c - ch) <= _DUP_COLORHASH_MAX  # type: ignore[operator]


def check_duplicate_frames(stills: list[tuple[str, Path]]) -> list[Finding]:
    """Flag scenes whose composited still is (near-)identical to an earlier one."""
    findings: list[Finding] = []
    # Each entry: (scene_id, phash, colorhash)
    hashes: list[tuple[str, object, object]] = []
    for scene_id, png in stills:
        with Image.open(png) as im:
            rgb = im.convert("RGB")
            h_p = imagehash.phash(rgb)
            h_c = imagehash.colorhash(im)
        match = next(
            (sid for sid, ph, ch in hashes if _is_duplicate(h_p, h_c, ph, ch)),
            None,
        )
        if match is not None:
            findings.append(
                Finding(
                    scene_id=scene_id,
                    check="duplicate_frame",
                    severity="error",
                    message=f"{scene_id} renders the same frame as {match}",
                    suggested_fix=(
                        "give this scene a distinct image/crop/camera_motion, "
                        "a distinct generated_image, or merge the redundant beat"
                    ),
                )
            )
        else:
            hashes.append((scene_id, h_p, h_c))
    return findings


_BLANK_DOMINANT_FRACTION_MAX = 0.85


def check_blank_substrate(still: Path, scene: dict) -> list[Finding]:
    """Flag a still that is mostly one flat color (a meaningless substrate).

    Measurement is taken over the content inset region of the book frame so
    that the brown border material does not dilute the dominant-color fraction
    and mask genuinely flat content panels.
    """
    scene_id = scene.get("id", "scene")
    with Image.open(still) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size
        # Measure only the content inset so the book border does not dilute the
        # dominant-color fraction.  Fall back to the full frame for non-standard
        # canvas sizes or if geometry extraction fails.
        try:
            canvas_w, canvas_h = get_resolution("16:9")
            if (w, h) == (canvas_w, canvas_h):
                g = BookSceneSpec.open_book(canvas_w, canvas_h).as_frame_geometry()
                ix = int(g["inset_x"])
                iy = int(g["inset_y"])
                iw = int(g["inset_w"])
                ih = int(g["inset_h"])
                box = (ix, iy, ix + iw, iy + ih)
                region = rgb.crop(box)
            else:
                region = rgb
        except Exception:
            region = rgb
        total = region.width * region.height
        colors = region.getcolors(maxcolors=total) or []
    if not colors:
        return []
    dominant = max(c for c, _ in colors)
    if dominant / total >= _BLANK_DOMINANT_FRACTION_MAX:
        return [
            Finding(
                scene_id=scene_id,
                check="blank_substrate",
                severity="error",
                message=f"{scene_id} is a near-blank frame ({dominant / total:.0%} one color)",
                suggested_fix=(
                    "bake the beat's meaning into the asset (annotate the map / "
                    "fill the chart) or merge the scene; a bare substrate communicates nothing"
                ),
            )
        ]
    return []


def run_checks(
    stills: list[tuple[str, Path, dict]],
) -> list[Finding]:
    """Run all slice-1 checks over the rendered stills.

    `stills` is (scene_id, png_path, scene_dict). Per-still checks run per item;
    cross-still checks (duplicate-frame) run over the whole set.
    """
    findings: list[Finding] = []
    findings.extend(check_duplicate_frames([(sid, png) for sid, png, _ in stills]))
    for _scene_id, png, scene in stills:
        findings.extend(check_blank_substrate(png, scene))
    return findings
