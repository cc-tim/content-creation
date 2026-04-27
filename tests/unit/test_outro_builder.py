from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from pipeline.outro.builder import build_outro, fetch_profile_png
from pipeline.publish.channels import ChannelProfile


def _profile() -> ChannelProfile:
    return ChannelProfile(
        name="ideal-parents-tw",
        niche="parenting",
        locale="zh-TW",
        channel_id="UCOzL_agyMJLknQtXgLMIyyA",
        voice_guide="",
        default_tags=[],
        category_id=27,
        display_name="理想父母",
        tagline="陪你走過每個育兒時刻",
        outro_enabled=True,
    )


def _make_png(tmp_path: Path) -> Path:
    p = tmp_path / "profile.png"
    Image.new("RGB", (100, 100), color=(200, 150, 100)).save(p, "PNG")
    return p


def _patched_build(tmp_path: Path, **kwargs):
    """Run build_outro with run_ffmpeg and _make_circle_png both mocked."""
    with (
        patch("pipeline.outro.builder.run_ffmpeg") as mock_run,
        patch("pipeline.outro.builder._make_circle_png"),
    ):
        build_outro(
            profile=_profile(),
            profile_png_path=_make_png(tmp_path),
            output_path=tmp_path / "outro.mp4",
            **kwargs,
        )
    return mock_run


def test_build_outro_calls_ffmpeg(tmp_path: Path) -> None:
    mock_run = _patched_build(tmp_path, aspect_ratio="16:9")
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0][0] == "ffmpeg"


def test_build_outro_landscape_resolution(tmp_path: Path) -> None:
    mock_run = _patched_build(tmp_path, aspect_ratio="16:9")
    assert "1920x1080" in " ".join(mock_run.call_args[0][0])


def test_build_outro_portrait_resolution(tmp_path: Path) -> None:
    mock_run = _patched_build(tmp_path, aspect_ratio="9:16")
    assert "1080x1920" in " ".join(mock_run.call_args[0][0])


def test_build_outro_contains_avatar_fade(tmp_path: Path) -> None:
    mock_run = _patched_build(tmp_path)
    assert "fade=in" in " ".join(mock_run.call_args[0][0])


def test_build_outro_contains_static_hold(tmp_path: Path) -> None:
    mock_run = _patched_build(tmp_path)
    cmd_str = " ".join(mock_run.call_args[0][0])
    assert "tpad" in cmd_str
    assert "stop_mode=clone" in cmd_str


def test_build_outro_contains_channel_name(tmp_path: Path) -> None:
    mock_run = _patched_build(tmp_path)
    cmd_str = " ".join(mock_run.call_args[0][0])
    assert "理想父母" in cmd_str
    assert "陪你走過每個育兒時刻" in cmd_str


def test_build_outro_contains_subscribe_text(tmp_path: Path) -> None:
    mock_run = _patched_build(tmp_path)
    assert "訂閱頻道" in " ".join(mock_run.call_args[0][0])


def test_build_outro_output_codec(tmp_path: Path) -> None:
    mock_run = _patched_build(tmp_path)
    cmd = mock_run.call_args[0][0]
    assert "libx264" in cmd
    assert "aac" in cmd


# ---------------------------------------------------------------------------
# fetch_profile_png
# ---------------------------------------------------------------------------


def test_fetch_profile_png_downloads_when_missing(tmp_path: Path) -> None:
    dest = tmp_path / "profile.png"

    api_resp = MagicMock()
    api_resp.raise_for_status = MagicMock()
    api_resp.json.return_value = {
        "items": [
            {"snippet": {"thumbnails": {"high": {"url": "https://example.com/img.jpg"}}}}
        ]
    }
    img_resp = MagicMock()
    img_resp.raise_for_status = MagicMock()
    img_resp.content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    with (
        patch("pipeline.outro.builder.httpx.get", side_effect=[api_resp, img_resp]),
        patch("pipeline.outro.builder.PipelineConfig") as mock_cfg,
    ):
        mock_cfg.return_value.YOUTUBE_API_KEY = "fake-key"
        fetch_profile_png(channel_id="UC123", dest=dest)

    assert dest.exists()
    assert dest.read_bytes() == img_resp.content


def test_fetch_profile_png_skips_when_exists(tmp_path: Path) -> None:
    dest = tmp_path / "profile.png"
    dest.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

    with patch("pipeline.outro.builder.httpx.get") as mock_get:
        fetch_profile_png(channel_id="UC123", dest=dest)

    mock_get.assert_not_called()


def test_fetch_profile_png_raises_when_no_channel_id(tmp_path: Path) -> None:
    dest = tmp_path / "profile.png"
    with pytest.raises(ValueError, match="channel_id"):
        fetch_profile_png(channel_id="", dest=dest)
