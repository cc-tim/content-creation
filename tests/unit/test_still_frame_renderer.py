from unittest.mock import MagicMock, patch

import pytest

from pipeline.composer.still_frame import render_still_frame


def test_render_still_frame_command(tmp_path):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"fake")

    with (
        patch("pipeline.composer.still_frame.run_ffmpeg") as mock_ff,
        patch("pipeline.composer.still_frame.image_to_video") as mock_itv,
    ):
        mock_ff.return_value = MagicMock(returncode=0)
        expected_out = tmp_path / "s1_visual.mp4"
        mock_itv.return_value = expected_out

        result = render_still_frame(
            visual={"type": "still_frame", "timestamp_sec": 120},
            duration_sec=10.0,
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s1",
            source_video=source,
        )

    # Check frame extraction
    extract_cmd = mock_ff.call_args[0][0]
    assert "-ss" in extract_cmd
    assert "120" in extract_cmd or "120.0" in extract_cmd
    assert "-frames:v" in extract_cmd

    # Check image_to_video was called
    mock_itv.assert_called_once()
    assert result == expected_out


def test_render_still_frame_no_source(tmp_path):
    with pytest.raises(FileNotFoundError):
        render_still_frame(
            visual={"type": "still_frame", "timestamp_sec": 0},
            duration_sec=5.0,
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s1",
            source_video=None,
        )
