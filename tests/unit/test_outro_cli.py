from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.outro.cli import _fetch_profile_png_via_oauth


def test_fetch_via_oauth_downloads_and_writes(tmp_path: Path) -> None:
    dest = tmp_path / "profile.png"
    img_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200

    fake_channel = {"snippet": {"thumbnails": {"high": {"url": "https://example.com/img.png"}}}}
    mock_client = MagicMock()
    mock_client.channels_list_mine.return_value = [fake_channel]

    mock_img_resp = MagicMock()
    mock_img_resp.raise_for_status = MagicMock()
    mock_img_resp.content = img_bytes

    with patch("pipeline.outro.cli.YouTubeClient") as mock_yt, \
         patch("pipeline.outro.cli.token_path_for"), \
         patch("pipeline.outro.cli.load_credentials"), \
         patch("pipeline.outro.cli.httpx.get", return_value=mock_img_resp):
        mock_yt.from_credentials.return_value = mock_client
        _fetch_profile_png_via_oauth("UC123", dest, "ideal-parents-tw")

    assert dest.exists()
    assert dest.read_bytes() == img_bytes


def test_fetch_via_oauth_raises_when_no_channel(tmp_path: Path) -> None:
    dest = tmp_path / "profile.png"

    mock_client = MagicMock()
    mock_client.channels_list_mine.return_value = []

    with patch("pipeline.outro.cli.YouTubeClient") as mock_yt, \
         patch("pipeline.outro.cli.token_path_for"), \
         patch("pipeline.outro.cli.load_credentials"):
        mock_yt.from_credentials.return_value = mock_client
        with pytest.raises(RuntimeError, match="No channel"):
            _fetch_profile_png_via_oauth("UC123", dest, "ideal-parents-tw")
