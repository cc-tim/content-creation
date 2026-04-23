from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pipeline.publish.channels import ChannelConfig, ChannelProfile
from pipeline.publish.stage import PublishStage
from pipeline.stages.base import PipelineContext

META_FIXTURE = Path(__file__).parents[2] / "fixtures" / "sample_metadata.json"


def _make_profile() -> ChannelProfile:
    return ChannelProfile(
        name="sample-profile",
        niche="sample",
        locale="zh-TW",
        channel_id="UC_sample",
        voice_guide="",
        default_tags=[],
        category_id=27,
    )


def _make_config() -> ChannelConfig:
    p = _make_profile()
    return ChannelConfig(profiles={p.name: p}, routing={"sample/zh-TW": p.name})


@pytest.fixture
def ready_project(tmp_path: Path) -> Path:
    d = tmp_path / "project"
    d.mkdir()
    (d / "final.mp4").write_bytes(b"x" * 1024)
    (d / "thumbnail.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 500)
    shutil.copy(META_FIXTURE, d / "metadata.json")
    return d


def _make_ctx(project_dir: Path) -> PipelineContext:
    return PipelineContext(
        project_id=42,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=project_dir,
        niche="sample",
        final_video_path=project_dir / "final.mp4",
    )


def test_upload_sequence_happy_path(ready_project: Path) -> None:
    client = MagicMock()
    client.videos_insert.return_value = "VIDEO123"

    stage = PublishStage(
        client_factory=lambda profile: client,
        channel_config=_make_config(),
        privacy="unlisted",
        schedule_iso=None,
    )
    ctx = _make_ctx(ready_project)
    result = stage.publish(ctx, profile_override=None)

    assert result.youtube_video_id == "VIDEO123"
    assert result.thumbnail_uploaded is True
    assert result.disclosure_set is True
    assert result.publish_profile == "sample-profile"
    client.videos_insert.assert_called_once()
    client.thumbnails_set.assert_called_once()
    client.videos_update.assert_called_once()


def test_resume_skips_phase_a_when_video_id_exists(ready_project: Path) -> None:
    client = MagicMock()
    stage = PublishStage(
        client_factory=lambda profile: client,
        channel_config=_make_config(),
        privacy="unlisted",
        schedule_iso=None,
    )
    ctx = _make_ctx(ready_project)
    ctx.youtube_video_id = "EXISTING"
    ctx.thumbnail_uploaded = False

    stage.publish(ctx, profile_override=None)

    client.videos_insert.assert_not_called()
    client.thumbnails_set.assert_called_once_with(
        video_id="EXISTING", file_path=ready_project / "thumbnail.png"
    )
    client.videos_update.assert_called_once()


def test_resume_skips_phase_b_when_thumbnail_uploaded(ready_project: Path) -> None:
    client = MagicMock()
    stage = PublishStage(
        client_factory=lambda profile: client,
        channel_config=_make_config(),
        privacy="unlisted",
        schedule_iso=None,
    )
    ctx = _make_ctx(ready_project)
    ctx.youtube_video_id = "EXISTING"
    ctx.thumbnail_uploaded = True

    stage.publish(ctx, profile_override=None)

    client.videos_insert.assert_not_called()
    client.thumbnails_set.assert_not_called()
    client.videos_update.assert_called_once()


def test_resume_skips_everything_when_all_done(ready_project: Path) -> None:
    client = MagicMock()
    stage = PublishStage(
        client_factory=lambda profile: client,
        channel_config=_make_config(),
        privacy="unlisted",
        schedule_iso=None,
    )
    ctx = _make_ctx(ready_project)
    ctx.youtube_video_id = "EXISTING"
    ctx.thumbnail_uploaded = True
    ctx.disclosure_set = True

    stage.publish(ctx, profile_override=None)

    client.videos_insert.assert_not_called()
    client.thumbnails_set.assert_not_called()
    client.videos_update.assert_not_called()


def test_scheduled_upload_uses_private_status(ready_project: Path) -> None:
    client = MagicMock()
    client.videos_insert.return_value = "VIDEO_SCHED"
    stage = PublishStage(
        client_factory=lambda profile: client,
        channel_config=_make_config(),
        privacy="unlisted",
        schedule_iso="2099-01-01T12:00:00+00:00",
    )
    ctx = _make_ctx(ready_project)
    stage.publish(ctx, profile_override=None)

    body = client.videos_insert.call_args.kwargs["body"]
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["publishAt"] == "2099-01-01T12:00:00+00:00"


def test_explicit_profile_override(ready_project: Path) -> None:
    client = MagicMock()
    client.videos_insert.return_value = "V"
    cfg = _make_config()
    other = ChannelProfile(
        name="other",
        niche="x",
        locale="en",
        channel_id="UC_other",
        voice_guide="",
        default_tags=[],
        category_id=1,
    )
    cfg = ChannelConfig(
        profiles={**cfg.profiles, "other": other},
        routing=cfg.routing,
    )
    stage = PublishStage(
        client_factory=lambda profile: client,
        channel_config=cfg,
        privacy="unlisted",
        schedule_iso=None,
    )
    ctx = _make_ctx(ready_project)
    result = stage.publish(ctx, profile_override="other")

    assert result.publish_profile == "other"
