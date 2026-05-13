from pathlib import Path

import pytest
from PIL import Image

from pipeline.composer.base import (
    _camera_motion_canvas,
    _camera_motion_progress,
    _is_camera_motion,
    get_resolution,
)


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


def test_camera_motion_canvas_targets_normalized_focus_point():
    source = Image.new("RGB", (557, 534), "white")

    _base, target = _camera_motion_canvas(
        source,
        {
            "type": "slow_push_pan",
            "focus_point": {"x": 0.66, "y": 0.69},
            "zoom_end": 2.35,
        },
        width=1280,
        height=720,
    )

    assert target[0] == pytest.approx(760, abs=1)
    assert target[1] == pytest.approx(497, abs=1)


def test_camera_motion_progress_uses_hold_move_hold_phases():
    motion = {
        "type": "slow_push_pan",
        "focus_point": {"x": 0.66, "y": 0.69},
        "hold_start_sec": 2.4,
        "move_sec": 4.3,
        "hold_end_sec": 4.0,
    }

    assert _camera_motion_progress(0, 324, 30, motion) == 0.0
    assert _camera_motion_progress(72, 324, 30, motion) == 0.0
    assert _camera_motion_progress(137, 324, 30, motion) == pytest.approx(0.5, abs=0.08)
    assert _camera_motion_progress(205, 324, 30, motion) == 1.0
    assert _camera_motion_progress(323, 324, 30, motion) == 1.0


def test_camera_motion_detection_requires_focus_point():
    assert _is_camera_motion(None) is False
    assert _is_camera_motion({"type": "unknown", "focus_point": {"x": 0.5, "y": 0.5}}) is False
    assert _is_camera_motion({"type": "slow_push_pan"}) is False
    assert _is_camera_motion({"type": "slow_push_pan", "focus_point": {"x": 0.5, "y": 0.5}})
