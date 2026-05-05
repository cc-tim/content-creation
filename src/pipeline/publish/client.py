from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

_Body = dict[str, Any]

logger = structlog.get_logger()


class QuotaExceededError(RuntimeError):
    """Raised when YouTube API returns a quotaExceeded error."""


def _is_quota_error(exc: HttpError) -> bool:
    try:
        content = exc.content
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        payload = json.loads(content)
        errors = payload.get("error", {}).get("errors", [])
        return any(e.get("reason") == "quotaExceeded" for e in errors)
    except Exception:
        return False


@dataclass
class YouTubeClient:
    """Thin wrapper over googleapiclient's YouTube Data API v3."""

    api: Any  # googleapiclient.discovery.Resource

    @classmethod
    def from_credentials(cls, *, credentials: Any) -> YouTubeClient:
        api = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        return cls(api=api)

    def videos_insert(
        self,
        *,
        file_path: Path,
        body: _Body,
        chunk_size: int = -1,
    ) -> str:
        """Upload a video (resumable). Returns video_id on success."""
        media = MediaFileUpload(str(file_path), chunksize=chunk_size, resumable=True)
        request = self.api.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
        )
        response = None
        try:
            while response is None:
                status, response = request.next_chunk()
                if status is not None:
                    logger.info("publish.upload.progress", progress=status.progress())
        except HttpError as exc:
            if _is_quota_error(exc):
                raise QuotaExceededError(
                    "YouTube daily quota exceeded. Retry after PT midnight."
                ) from exc
            raise
        return response["id"]

    def thumbnails_set(self, *, video_id: str, file_path: Path) -> None:
        media = MediaFileUpload(str(file_path))
        self.api.thumbnails().set(videoId=video_id, media_body=media).execute()

    def videos_update(self, *, video_id: str, part: str, body: _Body) -> _Body:
        return self.api.videos().update(part=part, body=body).execute()  # type: ignore[no-any-return]

    def channels_list_mine(self, *, part: str = "id") -> list[_Body]:
        response = self.api.channels().list(part=part, mine=True).execute()
        return list(response.get("items", []))

    def videos_list(self, *, video_id: str, part: str) -> list[_Body]:
        response = self.api.videos().list(part=part, id=video_id).execute()
        return list(response.get("items", []))

    def captions_insert(
        self,
        *,
        video_id: str,
        language: str,
        name: str,
        srt_path: Path,
    ) -> str:
        """Upload an SRT caption track. Returns the YouTube caption_id.

        Quota cost: ~400 units per call.
        Note: sync= parameter is deprecated as of 2026-05-04 and not passed.
        """
        body: _Body = {
            "snippet": {
                "videoId": video_id,
                "language": language,
                "name": name,
                "isDraft": False,
            }
        }
        media = MediaFileUpload(str(srt_path), mimetype="text/plain")
        response = (
            self.api.captions()
            .insert(part="snippet", body=body, media_body=media)
            .execute()
        )
        return response["id"]
