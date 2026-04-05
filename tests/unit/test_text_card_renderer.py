from unittest.mock import patch, MagicMock
from pathlib import Path

from pipeline.composer.text_card import render_text_card, _escape_drawtext


def test_escape_drawtext():
    assert _escape_drawtext("hello:world") == "hello\\:world"
    assert _escape_drawtext("50%") == "50%%"
    assert _escape_drawtext("it's") == "it'\\''" + "s"  # escaped single quote: ' → '\''


def test_render_text_card_command(tmp_path):
    with patch("pipeline.composer.text_card.run_ffmpeg") as mock_ff:
        mock_ff.return_value = MagicMock(returncode=0)
        (tmp_path / "s1_visual.mp4").write_bytes(b"out")

        result = render_text_card(
            visual={"type": "text_card", "text": "重要資訊", "background": "#2d2d44"},
            duration_sec=8.0, width=1280, height=720,
            work_dir=tmp_path, scene_id="s1",
        )

    cmd = mock_ff.call_args[0][0]
    cmd_str = " ".join(cmd)
    assert "drawtext" in cmd_str
    assert "1280x720" in cmd_str
    assert "#2d2d44" in cmd_str
    assert result.name == "s1_visual.mp4"


def test_render_text_card_default_bg(tmp_path):
    with patch("pipeline.composer.text_card.run_ffmpeg") as mock_ff:
        mock_ff.return_value = MagicMock(returncode=0)
        (tmp_path / "s2_visual.mp4").write_bytes(b"out")

        render_text_card(
            visual={"type": "text_card", "text": "test"},
            duration_sec=5.0, width=1280, height=720,
            work_dir=tmp_path, scene_id="s2",
        )

    cmd_str = " ".join(mock_ff.call_args[0][0])
    assert "#1a1a2e" in cmd_str  # default background
