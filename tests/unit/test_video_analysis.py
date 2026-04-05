from unittest.mock import MagicMock, patch

from pipeline.utils.video_analysis import (
    detect_scene_changes,
    extract_keyframes,
    extract_review_frames,
)


def test_extract_keyframes(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    out_dir = tmp_path / "keyframes"

    with (
        patch("pipeline.utils.video_analysis._get_duration", return_value=30.0),
        patch("pipeline.utils.video_analysis.run_ffmpeg") as mock_ff,
    ):
        mock_ff.return_value = MagicMock(returncode=0)
        # Simulate ffmpeg creating keyframe files
        out_dir.mkdir(parents=True)
        for i in range(4):
            (out_dir / f"keyframe_{i + 1:04d}.jpg").write_bytes(b"jpg")

        frames = extract_keyframes(video, out_dir, interval_sec=10)

    assert len(frames) == 4
    assert frames[0]["timestamp_sec"] == 0
    assert frames[1]["timestamp_sec"] == 10
    mock_ff.assert_called_once()


def test_detect_scene_changes_parses_output(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")

    fake_output = '{"frames": [{"pts_time": "5.5"}, {"pts_time": "12.3"}]}'

    with patch("pipeline.utils.video_analysis.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=fake_output,
        )
        timestamps = detect_scene_changes(video, threshold=0.3)

    assert len(timestamps) == 2
    assert timestamps[0] == 5.5
    assert timestamps[1] == 12.3


def test_detect_scene_changes_handles_failure(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")

    with patch("pipeline.utils.video_analysis.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        timestamps = detect_scene_changes(video)

    assert timestamps == []


def test_extract_review_frames(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    out_dir = tmp_path / "review"

    with (
        patch("pipeline.utils.video_analysis._get_duration", return_value=60.0),
        patch("pipeline.utils.video_analysis.run_ffmpeg") as mock_ff,
    ):
        mock_ff.return_value = MagicMock(returncode=0)
        out_dir.mkdir(parents=True)
        # Simulate frame extraction
        for i in range(4):
            (out_dir / f"review_{i:03d}.jpg").write_bytes(b"jpg")

        frames = extract_review_frames(video, out_dir, count=4)

    assert len(frames) == 4
    assert mock_ff.call_count == 4


def test_extract_review_frames_with_timestamps(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    out_dir = tmp_path / "review"

    with patch("pipeline.utils.video_analysis.run_ffmpeg") as mock_ff:
        mock_ff.return_value = MagicMock(returncode=0)
        out_dir.mkdir(parents=True)
        (out_dir / "review_000.jpg").write_bytes(b"jpg")
        (out_dir / "review_001.jpg").write_bytes(b"jpg")

        frames = extract_review_frames(
            video, out_dir, timestamps=[10.0, 25.0],
        )

    assert len(frames) == 2
    assert frames[0]["timestamp_sec"] == 10.0
