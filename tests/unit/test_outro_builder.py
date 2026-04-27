from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return p


def test_build_outro_calls_ffmpeg(tmp_path: Path) -> None:
    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=_make_png(tmp_path),
            output_path=tmp_path / "outro.mp4",
            aspect_ratio="16:9",
        )
    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "ffmpeg"


def test_build_outro_landscape_resolution(tmp_path: Path) -> None:
    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=_make_png(tmp_path),
            output_path=tmp_path / "outro.mp4",
            aspect_ratio="16:9",
        )
    cmd_str = " ".join(mock_run.call_args[0][0])
    assert "1920x1080" in cmd_str


def test_build_outro_portrait_resolution(tmp_path: Path) -> None:
    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=_make_png(tmp_path),
            output_path=tmp_path / "outro.mp4",
            aspect_ratio="9:16",
        )
    cmd_str = " ".join(mock_run.call_args[0][0])
    assert "1080x1920" in cmd_str


def test_build_outro_contains_avatar_fade(tmp_path: Path) -> None:
    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=_make_png(tmp_path),
            output_path=tmp_path / "outro.mp4",
        )
    cmd_str = " ".join(mock_run.call_args[0][0])
    assert "fade=in" in cmd_str


def test_build_outro_contains_static_hold(tmp_path: Path) -> None:
    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=_make_png(tmp_path),
            output_path=tmp_path / "outro.mp4",
        )
    cmd_str = " ".join(mock_run.call_args[0][0])
    assert "tpad" in cmd_str
    assert "stop_mode=clone" in cmd_str


def test_build_outro_contains_channel_name(tmp_path: Path) -> None:
    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=_make_png(tmp_path),
            output_path=tmp_path / "outro.mp4",
        )
    cmd_str = " ".join(mock_run.call_args[0][0])
    assert "理想父母" in cmd_str
    assert "陪你走過每個育兒時刻" in cmd_str


def test_build_outro_contains_subscribe_text(tmp_path: Path) -> None:
    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=_make_png(tmp_path),
            output_path=tmp_path / "outro.mp4",
        )
    cmd_str = " ".join(mock_run.call_args[0][0])
    assert "訂閱頻道" in cmd_str


def test_build_outro_output_codec(tmp_path: Path) -> None:
    with patch("pipeline.outro.builder.run_ffmpeg") as mock_run:
        build_outro(
            profile=_profile(),
            profile_png_path=_make_png(tmp_path),
            output_path=tmp_path / "outro.mp4",
        )
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

    with patch("pipeline.outro.builder.httpx.get", side_effect=[api_resp, img_resp]):
        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "fake-key"}):
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
