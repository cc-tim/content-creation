"""Golden-PNG comparison policy (Sprint 8, E8 item 1, spec section 4.4).

Hub (Linux) goldens are canonical. On any other platform the byte-exact compare
is SKIPPED with a counted reason unless ``PIPELINE_GOLDEN_STRICT=1`` forces it
(informational Mac runs). ``UPDATE_GOLDENS=1`` off-Linux is a hard error: a Mac
must never overwrite canonical goldens. Determinism tests (render twice →
identical) do not use this helper and run everywhere.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
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
