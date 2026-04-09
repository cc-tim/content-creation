from unittest.mock import MagicMock, patch

import pytest

from pipeline.composer.overlay import apply_overlay


def test_title_overlay(tmp_path):
    visual = tmp_path / "visual.mp4"
    visual.write_bytes(b"fake")

    with patch("pipeline.composer.overlay.run_ffmpeg") as mock_ff:
        mock_ff.return_value = MagicMock(returncode=0)
        result = apply_overlay(
            visual_path=visual,
            overlay={"type": "title", "text": "大標題"},
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s1",
            theme={},
        )

    cmd_str = " ".join(mock_ff.call_args[0][0])
    assert "drawtext" in cmd_str
    assert "drawbox" in cmd_str
    assert result == tmp_path / "s1_overlay.mp4"


def test_legacy_text_overlay_is_rejected(tmp_path):
    visual = tmp_path / "visual.mp4"
    visual.write_bytes(b"fake")

    with pytest.raises(ValueError):
        apply_overlay(
            visual_path=visual,
            overlay={"type": "text", "text": "重要資訊"},
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s2",
            theme={},
        )


def test_namecard_overlay(tmp_path):
    visual = tmp_path / "visual.mp4"
    visual.write_bytes(b"fake")

    with patch("pipeline.composer.overlay.run_ffmpeg") as mock_ff:
        mock_ff.return_value = MagicMock(returncode=0)
        apply_overlay(
            visual_path=visual,
            overlay={"type": "namecard", "name": "習近平", "role": "中國國家主席"},
            width=1280,
            height=720,
            work_dir=tmp_path,
            scene_id="s3",
            theme={},
        )

    cmd_str = " ".join(mock_ff.call_args[0][0])
    # Should have two drawtext calls (name + role)
    assert cmd_str.count("drawtext") == 2
