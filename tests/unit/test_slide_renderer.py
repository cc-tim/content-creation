from unittest.mock import MagicMock, patch

from pipeline.composer.slide import render_slide


def test_render_slide_with_title_and_bullets(tmp_path):
    with patch("pipeline.composer.slide.run_ffmpeg") as mock_ff:
        mock_ff.return_value = MagicMock(returncode=0)
        (tmp_path / "s1_visual.mp4").write_bytes(b"out")

        result = render_slide(
            visual={
                "type": "slide",
                "title": "權力金字塔",
                "bullets": ["中央委員會", "政治局", "常委會"],
            },
            duration_sec=12.0, width=1280, height=720,
            work_dir=tmp_path, scene_id="s1",
        )

    cmd_str = " ".join(mock_ff.call_args[0][0])
    assert "drawtext" in cmd_str
    assert "1280x720" in cmd_str
    assert result.name == "s1_visual.mp4"


def test_render_slide_empty(tmp_path):
    with patch("pipeline.composer.slide.run_ffmpeg") as mock_ff:
        mock_ff.return_value = MagicMock(returncode=0)
        (tmp_path / "s2_visual.mp4").write_bytes(b"out")

        render_slide(
            visual={"type": "slide"},
            duration_sec=5.0, width=1280, height=720,
            work_dir=tmp_path, scene_id="s2",
        )

    # Should still produce a valid command with null filter
    mock_ff.assert_called_once()
