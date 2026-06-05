from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def flat_grey_png(tmp_path: Path) -> Path:
    """A near-featureless 1280x720 grey image — the blank-substrate case."""
    p = tmp_path / "flat_grey.png"
    Image.new("RGB", (1280, 720), (136, 136, 136)).save(p)
    return p


@pytest.fixture
def busy_png(tmp_path: Path) -> Path:
    """A high-edge-density image — the true-negative for blank-substrate."""
    p = tmp_path / "busy.png"
    img = Image.new("RGB", (1280, 720), (20, 20, 20))
    px = img.load()
    for y in range(720):
        for x in range(0, 1280, 3):  # dense vertical stripes => high edge density
            px[x, y] = (240, 200, 40)
    img.save(p)
    return p


def make_article_scene(scene_id: str, image_path: Path, alt: str = "x") -> dict:
    """A deterministic article_image scene (no AI background)."""
    return {
        "id": scene_id,
        "section": "context",
        "visual": {"type": "article_image", "path": str(image_path), "alt": alt},
        "overlay": None,
    }
