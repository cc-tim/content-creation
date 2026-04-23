from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.publish.client import QuotaExceededError, YouTubeClient


def _make_client() -> tuple[YouTubeClient, MagicMock]:
    api = MagicMock()
    return YouTubeClient(api=api), api


def test_videos_insert_uploads_and_returns_id(tmp_path: Path) -> None:
    client, api = _make_client()
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake-mp4-bytes")

    insert_call = api.videos.return_value.insert.return_value
    insert_call.next_chunk.side_effect = [
        (MagicMock(progress=lambda: 0.5), None),
        (MagicMock(progress=lambda: 1.0), {"id": "VIDEO123"}),
    ]

    video_id = client.videos_insert(
        file_path=video,
        body={"snippet": {}, "status": {}},
    )
    assert video_id == "VIDEO123"


def test_videos_insert_raises_quota_exceeded(tmp_path: Path) -> None:
    from googleapiclient.errors import HttpError

    client, api = _make_client()
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")

    resp = MagicMock()
    resp.status = 403
    resp.reason = "quotaExceeded"
    err = HttpError(resp=resp, content=b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}')

    api.videos.return_value.insert.return_value.next_chunk.side_effect = err

    with pytest.raises(QuotaExceededError):
        client.videos_insert(file_path=video, body={"snippet": {}, "status": {}})


def test_thumbnails_set_uploads(tmp_path: Path) -> None:
    client, api = _make_client()
    thumb = tmp_path / "thumb.png"
    thumb.write_bytes(b"PNG")

    set_call = api.thumbnails.return_value.set.return_value
    set_call.execute.return_value = {"items": [{"default": {"url": "http://..."}}]}

    client.thumbnails_set(video_id="VIDEO123", file_path=thumb)

    api.thumbnails.assert_called_once()


def test_videos_update_alters_metadata() -> None:
    client, api = _make_client()
    update_call = api.videos.return_value.update.return_value
    update_call.execute.return_value = {"id": "VIDEO123"}

    client.videos_update(
        video_id="VIDEO123",
        part="snippet",
        body={"id": "VIDEO123", "snippet": {"title": "new"}},
    )
    api.videos.return_value.update.assert_called_once_with(
        part="snippet",
        body={"id": "VIDEO123", "snippet": {"title": "new"}},
    )


def test_channels_list_mine() -> None:
    client, api = _make_client()
    api.channels.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "UC_abc", "snippet": {"title": "My Channel"}}]
    }
    items = client.channels_list_mine(part="id,snippet")
    assert items[0]["id"] == "UC_abc"


def test_videos_list() -> None:
    client, api = _make_client()
    api.videos.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "V1", "status": {"privacyStatus": "unlisted"}}]
    }
    items = client.videos_list(video_id="V1", part="status")
    assert items[0]["status"]["privacyStatus"] == "unlisted"


def test_build_from_credentials() -> None:
    with patch("pipeline.publish.client.build") as build:
        build.return_value = MagicMock()
        YouTubeClient.from_credentials(credentials=MagicMock())
    build.assert_called_once()
    assert build.call_args[0][0] == "youtube"
    assert build.call_args[0][1] == "v3"
