from unittest.mock import patch, MagicMock
from pathlib import Path

from pipeline.composer.overlay import apply_overlay


def test_title_overlay(tmp_path):
    visual = tmp_path / "visual.mp4"
    visual.write_bytes(b"fake")
    output = tmp_path / "overlaid.mp4"

    with patch("pipeline.composer.overlay.run_ffmpeg") as mock_ff:
        mock_ff.return_value = MagicMock(returncode=0)
        result = apply_overlay(visual, {"type": "title", "text": "大標題"}, output)

    cmd_str = " ".join(mock_ff.call_args[0][0])
    assert "drawtext" in cmd_str
    assert "drawbox" in cmd_str
    assert result == output


def test_text_overlay(tmp_path):
    visual = tmp_path / "visual.mp4"
    visual.write_bytes(b"fake")
    output = tmp_path / "overlaid.mp4"

    with patch("pipeline.composer.overlay.run_ffmpeg") as mock_ff:
        mock_ff.return_value = MagicMock(returncode=0)
        apply_overlay(visual, {"type": "text", "text": "重要資訊"}, output)

    cmd_str = " ".join(mock_ff.call_args[0][0])
    assert "0.82" in cmd_str or "0.85" in cmd_str  # lower-third position


def test_namecard_overlay(tmp_path):
    visual = tmp_path / "visual.mp4"
    visual.write_bytes(b"fake")
    output = tmp_path / "overlaid.mp4"

    with patch("pipeline.composer.overlay.run_ffmpeg") as mock_ff:
        mock_ff.return_value = MagicMock(returncode=0)
        apply_overlay(
            visual,
            {"type": "namecard", "name": "習近平", "role": "中國國家主席"},
            output,
        )

    cmd_str = " ".join(mock_ff.call_args[0][0])
    # Should have two drawtext calls (name + role)
    assert cmd_str.count("drawtext") == 2
