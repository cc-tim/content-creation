from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pipeline.publish.channels import ChannelConfig, ChannelProfile
    from pipeline.publish.metadata import Metadata

import structlog
from pydantic import ValidationError

from pipeline.publish.metadata import load_metadata
from pipeline.stages.base import PipelineContext
from pipeline.utils.ffmpeg import ffmpeg_concat

logger = structlog.get_logger()

MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024
MAX_VIDEO_WARN_BYTES = 10 * 1024 * 1024 * 1024
MAX_VIDEO_HARD_BYTES = 128 * 1024 * 1024 * 1024


class PreflightError(RuntimeError):
    """Raised by run_preflight on any missing/invalid input."""


def _thumbnail_path(work_dir: Path) -> Path:
    return work_dir / "thumbnail.png"


def _metadata_path(work_dir: Path) -> Path:
    return work_dir / "metadata.json"


def run_preflight(
    *,
    ctx: PipelineContext,
    privacy: str,
    schedule_iso: str | None,
) -> None:
    """Validate all local inputs before any API call. Raises PreflightError."""
    if ctx.final_video_path is None or not ctx.final_video_path.exists():
        raise PreflightError(
            f"final video not found (ctx.final_video_path={ctx.final_video_path}). "
            f"Run compose stage first."
        )
    size = ctx.final_video_path.stat().st_size
    if size > MAX_VIDEO_HARD_BYTES:
        raise PreflightError(f"final video exceeds YouTube's 128GB limit (is {size} bytes)")
    if size > MAX_VIDEO_WARN_BYTES:
        logger.warning("publish.preflight.large_video", bytes=size)

    meta_path = _metadata_path(ctx.work_dir)
    if not meta_path.exists():
        raise PreflightError(
            f"metadata.json not found at {meta_path}. "
            f"Run: pipeline metadata regenerate --work-dir {ctx.work_dir}"
        )
    try:
        load_metadata(meta_path)
    except ValidationError as exc:
        raise PreflightError(f"metadata invalid: {exc}") from exc

    thumb = _thumbnail_path(ctx.work_dir)
    if not thumb.exists():
        raise PreflightError(f"thumbnail.png not found at {thumb}. Hand-design one and save there.")
    tsize = thumb.stat().st_size
    if tsize > MAX_THUMBNAIL_BYTES:
        raise PreflightError(f"thumbnail.png exceeds 2MB limit (is {tsize} bytes). Shrink it.")

    if schedule_iso is not None:
        if privacy == "public":
            raise PreflightError("--schedule requires privacy=private|unlisted (public conflicts)")
        try:
            when = datetime.fromisoformat(schedule_iso)
        except ValueError as exc:
            raise PreflightError(f"--schedule must be ISO8601: {exc}") from exc
        if when.tzinfo is None:
            raise PreflightError("--schedule must include timezone (e.g. +08:00)")
        if when <= datetime.now(tz=UTC):
            raise PreflightError(f"--schedule is in the past: {schedule_iso}")

    logger.info("publish.preflight.ok", project_id=ctx.project_id)


@dataclass
class PublishStage:
    """Publishes a produced project to YouTube.

    Not an orchestrator-chain PipelineStage — always invoked explicitly.
    Idempotent via context fields (youtube_video_id, thumbnail_uploaded, disclosure_set).
    """

    client_factory: Callable[[Any], Any]
    channel_config: ChannelConfig
    privacy: str = "private"
    schedule_iso: str | None = None
    force_metadata: bool = False
    force_thumbnail: bool = False
    dry_run: bool = False

    def _attach_outro(
        self,
        ctx: PipelineContext,
        profile: ChannelProfile,
        channels_dir: Path | None = None,
    ) -> None:
        """Concat outro.mp4 onto final_video_path when outro_enabled. Non-blocking on missing."""
        if not profile.outro_enabled:
            return
        if ctx.final_video_path is None:
            return
        base = channels_dir or Path("configs/channels")
        outro_path = base / profile.name / "outro.mp4"
        if not outro_path.exists():
            logger.warning("publish.outro_missing", expected=str(outro_path))
            return
        out = ctx.work_dir / "compose" / "final_with_outro.mp4"
        # Idempotency guard: publish may be re-run to resume thumbnail/disclosure.
        # If the context already points at the merged outro file, concatenating
        # that file into itself would truncate/corrupt the result and can leave
        # an outro-only upload candidate.
        if ctx.final_video_path.resolve() == out.resolve():
            logger.info("publish.outro_already_attached", output=str(out))
            return
        out.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg_concat([ctx.final_video_path, outro_path], out)

        # Validate: broken concat can produce a ~0s file (e.g., 1776997800).
        # If the merged output is clearly too short, discard it and keep original.
        try:
            import subprocess as _sp
            result = _sp.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
                capture_output=True, text=True, check=True,
            )
            merged_dur = float(result.stdout.strip())
        except Exception:
            merged_dur = 0.0

        if merged_dur < 10.0:
            logger.error(
                "publish.outro_concat_broken",
                expected_min=10.0,
                actual=round(merged_dur, 2),
                hint="Deleting broken merge; keeping original final for upload",
            )
            out.unlink(missing_ok=True)
            return

        ctx.final_video_path = out
        ctx.save()
        logger.info("publish.outro_attached", outro=str(outro_path))

    def publish(
        self,
        ctx: PipelineContext,
        *,
        profile_override: str | None,
    ) -> PipelineContext:
        """Run preflight + phased upload. Mutates and returns ctx."""
        from pipeline.notify.telegram import notify_failure
        from pipeline.publish.channels import resolve_profile

        # Resolve profile first — needed for outro attachment before preflight validation
        profile = resolve_profile(
            self.channel_config,
            niche=ctx.niche,
            locale=ctx.locale,
            override=profile_override,
        )
        ctx.publish_profile = profile.name
        logger.info(
            "publish.profile_resolved",
            profile=profile.name,
            channel_id=profile.channel_id,
        )

        # Attach outro before preflight so preflight validates the merged file
        self._attach_outro(ctx, profile)

        run_preflight(ctx=ctx, privacy=self.privacy, schedule_iso=self.schedule_iso)

        metadata = load_metadata(ctx.work_dir / "metadata.json")
        upload_body = self._build_upload_body(metadata)

        if self.dry_run:
            import json as _json

            print(_json.dumps(upload_body, indent=2, ensure_ascii=False))
            return ctx

        client = self.client_factory(profile)

        try:
            self._phase_a_upload(client, ctx, upload_body)
            self._phase_b_thumbnail(client, ctx)
            self._phase_c_disclosure(client, ctx, metadata)
        except Exception as exc:
            notify_failure(
                project_id=ctx.project_id,
                profile=profile.name,
                phase=self._current_phase(ctx),
                error=str(exc),
                fix_command=f"pipeline publish {ctx.project_id}",
            )
            raise

        ctx.published_at = datetime.now(tz=UTC).isoformat()
        ctx.save()
        return ctx

    def _build_upload_body(self, metadata: Metadata) -> dict[str, Any]:
        body: dict[str, Any] = {
            "snippet": {
                "title": metadata.title,
                "description": metadata.description,
                "tags": metadata.tags,
                "categoryId": str(metadata.category_id),
                "defaultLanguage": metadata.default_language,
                "defaultAudioLanguage": metadata.default_audio_language,
            },
            "status": {
                "selfDeclaredMadeForKids": metadata.made_for_kids,
            },
        }
        if self.schedule_iso is not None:
            body["status"]["privacyStatus"] = "private"
            body["status"]["publishAt"] = self.schedule_iso
        else:
            body["status"]["privacyStatus"] = self.privacy
        if metadata.localizations:
            body["localizations"] = {
                lang: {"title": lm.title, "description": lm.description}
                for lang, lm in metadata.localizations.items()
            }
        return body

    def _phase_a_upload(self, client: Any, ctx: PipelineContext, body: dict[str, Any]) -> None:
        if ctx.youtube_video_id is not None and not self.force_metadata:
            logger.info("publish.phase_a.skipped", video_id=ctx.youtube_video_id)
            return
        if ctx.youtube_video_id is not None and self.force_metadata:
            client.videos_update(
                video_id=ctx.youtube_video_id,
                part="snippet,status",
                body={"id": ctx.youtube_video_id, **body},
            )
            logger.info("publish.phase_a.metadata_updated", video_id=ctx.youtube_video_id)
            return

        logger.info("publish.upload.start", project_id=ctx.project_id)
        video_id = client.videos_insert(file_path=ctx.final_video_path, body=body)
        ctx.youtube_video_id = video_id
        ctx.save()
        logger.info("publish.upload.complete", video_id=video_id)

    def _phase_b_thumbnail(self, client: Any, ctx: PipelineContext) -> None:
        if ctx.thumbnail_uploaded and not self.force_thumbnail:
            return
        thumb = ctx.work_dir / "thumbnail.png"
        client.thumbnails_set(video_id=ctx.youtube_video_id, file_path=thumb)
        ctx.thumbnail_uploaded = True
        ctx.save()
        logger.info("publish.thumbnail.complete", video_id=ctx.youtube_video_id)

    def _phase_c_disclosure(self, client: Any, ctx: PipelineContext, metadata: Metadata) -> None:
        if ctx.disclosure_set:
            return
        body = {
            "id": ctx.youtube_video_id,
            "status": {
                "containsSyntheticMedia": metadata.altered_or_synthetic_content
                == "synthetic_voice",
            },
        }
        client.videos_update(video_id=ctx.youtube_video_id, part="status", body=body)
        ctx.disclosure_set = True
        ctx.save()
        logger.info("publish.disclosure.complete", video_id=ctx.youtube_video_id)

    @staticmethod
    def _current_phase(ctx: PipelineContext) -> str:
        if ctx.youtube_video_id is None:
            return "upload"
        if not ctx.thumbnail_uploaded:
            return "thumbnail"
        if not ctx.disclosure_set:
            return "disclosure"
        return "complete"
