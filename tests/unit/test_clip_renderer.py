from unittest.mock import MagicMock, patch

from pipeline.composer.clip import render_clip


def test_render_clip_command(tmp_path):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"fake")

    with (
        patch("pipeline.composer.clip._get_source_duration", return_value=120.0),
        patch("pipeline.composer.clip.run_ffmpeg") as mock_ff,
    ):
        mock_ff.return_value = MagicMock(returncode=0)
        # Create the expected output so we can verify the return
        expected_out = tmp_path / "s1_visual.mp4"
        expected_out.write_bytes(b"fake output")

        result = render_clip(
            visual={"type": "clip", "source": "primary", "start_sec": 10, "end_sec": 25},
            duration_sec=15.0,
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s1",
            source_video=source,
        )

    cmd = mock_ff.call_args[0][0]
    assert "-ss" in cmd
    assert "10" in cmd or "10.0" in cmd
    assert result.name == "s1_visual.mp4"


def test_render_clip_uses_visual_path_when_present(tmp_path):
    primary = tmp_path / "primary.mp4"
    primary.write_bytes(b"primary")
    asset = tmp_path / "asset.mp4"
    asset.write_bytes(b"asset")

    with (
        patch("pipeline.composer.clip._get_source_duration", return_value=120.0),
        patch("pipeline.composer.clip.run_ffmpeg") as mock_ff,
    ):
        mock_ff.return_value = MagicMock(returncode=0)
        (tmp_path / "s1_visual.mp4").write_bytes(b"fake output")

        render_clip(
            visual={"type": "clip", "path": str(asset), "start_sec": 2, "end_sec": 7},
            duration_sec=5.0,
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s1",
            source_video=primary,
        )

    cmd = mock_ff.call_args[0][0]
    input_idx = cmd.index("-i")
    assert cmd[input_idx + 1] == str(asset)


def test_render_clip_clamps_beyond_source(tmp_path):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"fake")

    with (
        patch("pipeline.composer.clip._get_source_duration", return_value=30.0),
        patch("pipeline.composer.clip.run_ffmpeg") as mock_ff,
    ):
        mock_ff.return_value = MagicMock(returncode=0)
        (tmp_path / "s2_visual.mp4").write_bytes(b"out")

        render_clip(
            visual={"type": "clip", "start_sec": 50, "end_sec": 65},
            duration_sec=15.0,
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s2",
            source_video=source,
        )

    cmd = mock_ff.call_args[0][0]
    ss_idx = cmd.index("-ss")
    start_val = float(cmd[ss_idx + 1])
    assert start_val <= 29.0  # clamped to source_dur - 1


def test_render_clip_no_source(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        render_clip(
            visual={"type": "clip", "start_sec": 0, "end_sec": 10},
            duration_sec=10.0,
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s1",
            source_video=None,
        )
