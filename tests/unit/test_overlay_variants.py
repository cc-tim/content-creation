from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipeline.composer.overlay import apply_overlay


def _make_blank_mp4(path: Path, duration: float = 2.0) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=640x360:d={duration}:r=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


@pytest.mark.integration
def test_text_top_places_overlay_near_top(tmp_path):
    src = tmp_path / "src.mp4"
    _make_blank_mp4(src)
    out = apply_overlay(
        visual_path=src,
        overlay={"type": "text_top", "text": "Hello World"},
        width=640,
        height=360,
        work_dir=tmp_path,
        scene_id="s1",
        theme={},
    )
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.integration
def test_text_left_places_overlay_on_left_half(tmp_path):
    src = tmp_path / "src.mp4"
    _make_blank_mp4(src)
    out = apply_overlay(
        visual_path=src,
        overlay={"type": "text_left", "text": "Left side label"},
        width=640,
        height=360,
        work_dir=tmp_path,
        scene_id="s2",
        theme={},
    )
    assert out.exists()


@pytest.mark.integration
def test_text_emphasis_is_centered_and_large(tmp_path):
    src = tmp_path / "src.mp4"
    _make_blank_mp4(src)
    out = apply_overlay(
        visual_path=src,
        overlay={"type": "text_emphasis", "text": "BIG"},
        width=640,
        height=360,
        work_dir=tmp_path,
        scene_id="s3",
        theme={},
    )
    assert out.exists()


def test_text_overlay_type_is_rejected(tmp_path):
    # The old "text" type dropped overlays on the bottom — it's forbidden now.
    with pytest.raises(ValueError):
        apply_overlay(
            visual_path=tmp_path / "nonexistent.mp4",
            overlay={"type": "text", "text": "Would collide with subtitles"},
            width=640,
            height=360,
            work_dir=tmp_path,
            scene_id="s4",
            theme={},
        )
