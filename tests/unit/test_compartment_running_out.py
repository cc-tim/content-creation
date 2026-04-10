from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from pipeline.composer.compartment import (
    build_compartment_loop,
    composite_compartment_on_scene,
)
from pipeline.composer.compartment_renderers.running_out import (
    render_running_out_frames,
)


def _make_blank_mp4(path: Path, duration: float = 5.0, w: int = 1280, h: int = 720) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={w}x{h}:d={duration}:r=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
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


@pytest.mark.integration
def test_build_compartment_loop_produces_mp4(tmp_path):
    config = {
        "type": "running_out",
        "position": "right",
        "size": {"width": 0.35, "height": 0.6},
        "loop": True,
        "animation": {
            "label": "上下文",
            "stages": [
                {"value": "20%", "face": "neutral", "color": "#fbbf24"},
                {"value": "10%", "face": "worried", "color": "#fb923c"},
            ],
            "stage_duration_sec": 1.0,
        },
    }
    out = build_compartment_loop(
        compartment=config,
        scene_duration_sec=5.0,
        scene_width=1280,
        scene_height=720,
        work_dir=tmp_path,
        scene_id="s3",
    )
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.integration
def test_build_compartment_loop_with_relative_work_dir(tmp_path, monkeypatch):
    """The concat demuxer resolves `file '...'` entries relative to the concat
    file's own directory. If we write frame paths as-is and work_dir is a
    relative path (as it is in production compose), ffmpeg double-prefixes
    them and the build fails. Regression for the Phase B s3 failure.
    """
    monkeypatch.chdir(tmp_path)
    rel_work = Path("project/compose/scenes")
    rel_work.mkdir(parents=True)
    assert not rel_work.is_absolute()

    config = {
        "type": "running_out",
        "position": "right",
        "size": {"width": 0.35, "height": 0.6},
        "loop": True,
        "animation": {
            "label": "ctx",
            "stages": [{"value": "20%", "face": "neutral", "color": "#fbbf24"}],
            "stage_duration_sec": 1.0,
        },
    }
    out = build_compartment_loop(
        compartment=config,
        scene_duration_sec=3.0,
        scene_width=1280,
        scene_height=720,
        work_dir=rel_work,
        scene_id="s3",
    )
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.integration
def test_composite_compartment_on_scene_produces_mp4(tmp_path):
    scene_video = tmp_path / "scene.mp4"
    _make_blank_mp4(scene_video, duration=3.0)
    config = {
        "type": "running_out",
        "position": "right",
        "size": {"width": 0.32, "height": 0.55},
        "loop": True,
        "animation": {
            "label": "X",
            "stages": [{"value": "50%", "face": "neutral", "color": "#fbbf24"}],
            "stage_duration_sec": 1.0,
            "shake": True,
        },
    }
    compartment = build_compartment_loop(
        compartment=config,
        scene_duration_sec=3.0,
        scene_width=1280,
        scene_height=720,
        work_dir=tmp_path,
        scene_id="s9",
    )
    out = composite_compartment_on_scene(
        scene_video=scene_video,
        compartment_video=compartment,
        compartment_config=config,
        scene_width=1280,
        scene_height=720,
        work_dir=tmp_path,
        scene_id="s9",
    )
    assert out.exists()
    assert out.stat().st_size > 0
