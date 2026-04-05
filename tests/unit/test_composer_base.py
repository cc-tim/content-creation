from pathlib import Path

import pytest

from pipeline.composer.base import get_resolution


def test_get_resolution_16_9():
    w, h = get_resolution("16:9")
    assert w == 1280
    assert h == 720


def test_get_resolution_9_16():
    w, h = get_resolution("9:16")
    assert w == 720
    assert h == 1280


def test_get_resolution_unknown():
    with pytest.raises(ValueError, match="Unknown aspect ratio"):
        get_resolution("4:3")


def test_render_scene_unknown_type():
    from pipeline.composer.base import render_scene
    with pytest.raises(ValueError, match="Unknown visual type"):
        render_scene(
            scene={"id": "s1", "visual": {"type": "hologram"}},
            duration_sec=5.0,
            aspect_ratio="16:9",
            work_dir=Path("/tmp"),
        )
