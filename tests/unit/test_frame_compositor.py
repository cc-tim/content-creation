from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline.composer.frame import composite_scene_frame


def test_composite_scene_frame_passthrough_without_style(tmp_path: Path):
    src = tmp_path / "src.mp4"
    out = tmp_path / "out.mp4"
    src.write_bytes(b"video")

    assert composite_scene_frame(src, out, frame_style=None, width=1280, height=720) == src


def test_composite_scene_frame_rejects_unknown_style(tmp_path: Path):
    with pytest.raises(ValueError, match="Unknown frame style"):
        composite_scene_frame(
            tmp_path / "src.mp4",
            tmp_path / "out.mp4",
            frame_style="shadow_box",
            width=1280,
            height=720,
        )


def test_open_book_page_frame_invokes_ffmpeg_with_book_geometry(tmp_path: Path):
    src = tmp_path / "src.mp4"
    out = tmp_path / "out.mp4"
    src.write_bytes(b"video")

    with (
        patch("pipeline.composer.frame._probe_duration_sec", return_value=1.0),
        patch("pipeline.composer.frame.run_ffmpeg") as run,
    ):
        result = composite_scene_frame(
            src,
            out,
            frame_style="open_book_page",
            width=1280,
            height=720,
        )

    assert result == out
    cmd = run.call_args.args[0]
    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert "drawbox" in filter_complex
    assert "overlay" in filter_complex
    assert "scale=947:484" in filter_complex
