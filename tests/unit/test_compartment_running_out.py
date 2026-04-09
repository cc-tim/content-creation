from __future__ import annotations

from pipeline.composer.compartment_renderers.running_out import (
    render_running_out_frames,
)


def test_running_out_writes_one_png_per_stage(tmp_path):
    config = {
        "label": "上下文",
        "stages": [
            {"value": "20%", "face": "neutral", "color": "#fbbf24"},
            {"value": "10%", "face": "worried", "color": "#fb923c"},
            {"value": "5%", "face": "panicked", "color": "#ef4444"},
        ],
        "stage_duration_sec": 1.5,
        "shake": True,
    }
    frames = render_running_out_frames(
        out_dir=tmp_path,
        config=config,
        width=480,
        height=640,
    )
    assert len(frames) == len(config["stages"])
    for frame in frames:
        assert frame.path.exists()
        assert frame.path.stat().st_size > 100
        assert frame.duration_sec == 1.5


def test_running_out_handles_unknown_face(tmp_path):
    # Unknown face should fall back to neutral, not crash.
    config = {
        "label": "X",
        "stages": [{"value": "50%", "face": "mystery", "color": "#ffffff"}],
        "stage_duration_sec": 1.0,
    }
    frames = render_running_out_frames(
        out_dir=tmp_path, config=config, width=320, height=480
    )
    assert len(frames) == 1
    assert frames[0].path.exists()
