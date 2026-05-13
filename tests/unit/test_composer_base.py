from pathlib import Path

import pytest
from PIL import Image

from pipeline.composer.base import _camera_motion_filter, get_resolution


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


def test_camera_motion_filter_targets_normalized_focus_point(tmp_path: Path):
    image_path = tmp_path / "source.jpg"
    Image.new("RGB", (557, 534), "white").save(image_path)

    vf = _camera_motion_filter(
        image_path,
        {
            "type": "slow_push_pan",
            "focus_point": {"x": 0.66, "y": 0.69},
            "zoom_end": 2.35,
        },
        frames=324,
        width=1280,
        height=720,
        fps=30,
    )

    assert vf is not None
    assert "zoompan" in vf
    assert "2.350000" not in vf
    assert "1.350000" in vf
    assert "760." in vf
    assert "496." in vf


def test_camera_motion_filter_ignores_unconfigured_motion(tmp_path: Path):
    image_path = tmp_path / "source.jpg"
    Image.new("RGB", (100, 100), "white").save(image_path)

    assert _camera_motion_filter(image_path, None, 10, 1280, 720, 30) is None
    assert _camera_motion_filter(
        image_path,
        {"type": "unknown", "focus_point": {"x": 0.5, "y": 0.5}},
        10,
        1280,
        720,
        30,
    ) is None
