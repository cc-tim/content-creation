"""Golden-PNG comparison policy (Sprint 8, E8 item 1, spec section 4.4).

Hub (Linux) goldens are canonical. On any other platform the byte-exact compare
is SKIPPED with a counted reason unless ``PIPELINE_GOLDEN_STRICT=1`` forces it
(informational Mac runs). ``UPDATE_GOLDENS=1`` off-Linux is a hard error: a Mac
must never overwrite canonical goldens. Determinism tests (render twice →
identical) do not use this helper and run everywhere.

GPU-rendered goldens (toy3d, E11 S12-12) use ``assert_close_to_golden``: still
hub-canonical, but compared on every machine against limits set between the
measured cross-machine noise floor and a sensitivity set.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import numpy as np
from PIL import Image, ImageChops

SKIP_REASON = (
    "golden PNGs are hub-canonical (linux); set PIPELINE_GOLDEN_STRICT=1 to compare"
)
UPDATE_OFF_HUB_ERROR = (
    "goldens regenerate on the hub only (linux); refusing UPDATE_GOLDENS on {platform}"
)


def assert_matches_golden(image: Image.Image | str | Path, golden_path: Path) -> None:
    """Compare ``image`` (PIL image or PNG path) byte-exact against ``golden_path``."""
    img = image if isinstance(image, Image.Image) else Image.open(image)
    on_hub = sys.platform == "linux"

    if os.environ.get("UPDATE_GOLDENS"):
        if not on_hub:
            raise RuntimeError(UPDATE_OFF_HUB_ERROR.format(platform=sys.platform))
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(golden_path)
        return

    if not on_hub and not os.environ.get("PIPELINE_GOLDEN_STRICT"):
        pytest.skip(SKIP_REASON)

    assert golden_path.exists(), f"missing golden {golden_path}; run with UPDATE_GOLDENS=1"
    diff = ImageChops.difference(img.convert("RGB"), Image.open(golden_path).convert("RGB"))
    assert diff.getbbox() is None, f"{golden_path.stem} render drifted from golden"


def close_stats(image: Image.Image, golden: Image.Image, tile: int = 24) -> dict:
    """Per-pixel max-channel |diff| (0-255): its mean, 99.9th percentile, the fraction over 8
    levels, the max, and the worst mean over `tile`-px tiles (a local change, not spread noise)."""
    d = np.abs(np.asarray(image.convert("RGB"), dtype=np.int16) - np.asarray(golden.convert("RGB"), dtype=np.int16))
    m = d.max(axis=2)
    h, w = m.shape
    tiles = m[: h // tile * tile, : w // tile * tile].reshape(h // tile, tile, w // tile, tile).mean(axis=(1, 3))
    return {"mean": float(m.mean()), "p999": float(np.percentile(m, 99.9)), "frac8": float((m > 8).mean()),
            "max": int(m.max()), "tile": float(tiles.max())}


def assert_close_to_golden(image: Image.Image | str | Path, golden_path: Path, *, mean: float, p999: float,
                           max_frac: float, tile: float) -> dict:
    """Compare ``image`` with ``golden_path`` within limits, on every machine (hub-canonical: only
    the hub writes goldens). Returns the stats ({} when minting)."""
    img = image if isinstance(image, Image.Image) else Image.open(image)
    if os.environ.get("UPDATE_GOLDENS"):
        if sys.platform != "linux":
            raise RuntimeError(UPDATE_OFF_HUB_ERROR.format(platform=sys.platform))
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(golden_path)
        return {}
    assert golden_path.exists(), f"missing golden {golden_path}; mint it with UPDATE_GOLDENS=1 on the hub"
    golden = Image.open(golden_path)
    assert img.size == golden.size, f"{golden_path.stem}: size {img.size} != golden {golden.size}"
    stats = close_stats(img, golden)
    limits = {"mean": mean, "p999": p999, "frac8": max_frac, "tile": tile}
    over = [k for k, lim in limits.items() if stats[k] > lim]
    assert not over, (f"{golden_path.stem} beyond tolerance on {', '.join(over)}: "
                      + ", ".join(f"{k} {stats[k]:.4g} (≤ {limits[k]})" for k in limits))
    return stats
