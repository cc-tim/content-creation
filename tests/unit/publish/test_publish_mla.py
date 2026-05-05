from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pipeline.publish.channels import ChannelConfig, ChannelProfile
from pipeline.publish.client import YouTubeClient
from pipeline.publish.metadata import LocalizedMeta, Metadata
from pipeline.publish.stage import PublishStage
from pipeline.stages.base import PipelineContext

META_FIXTURE = Path(__file__).parents[2] / "fixtures" / "sample_metadata.json"
SRT_FIXTURE = Path(__file__).parents[2] / "fixtures" / "sample.srt"


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
        youtube_video_id="VIDEO123",
        thumbnail_uploaded=True,
        disclosure_set=True,
    )


# ---------------------------------------------------------------------------
# Phase C: localizations in videos.update
# ---------------------------------------------------------------------------


def test_phase_c_includes_localizations_when_present(tmp_path: Path) -> None:
    """When metadata.localizations is non-empty, videos.update receives localizations body
    and part includes 'localizations'."""
    client = MagicMock()

    metadata = Metadata(
        title="Title",
        description="Desc",
        tags=[],
        category_id=27,
        default_language="zh-TW",
        default_audio_language="zh-TW",
        altered_or_synthetic_content="synthetic_voice",
        localizations={
            "en": LocalizedMeta(title="English Title", description="English Desc")
        },
    )

    ctx = PipelineContext(
        project_id=1,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=tmp_path,
        youtube_video_id="VIDEO123",
    )

    stage = PublishStage(
        client_factory=lambda p: client,
        channel_config=_make_config(),
    )
    stage._phase_c_disclosure(client, ctx, metadata)

    assert ctx.disclosure_set is True
    call_kwargs = client.videos_update.call_args.kwargs
    assert "localizations" in call_kwargs["part"]
    assert "status" in call_kwargs["part"]
    assert "localizations" in call_kwargs["body"]
    assert call_kwargs["body"]["localizations"]["en"] == {
        "title": "English Title",
        "description": "English Desc",
    }


def test_phase_c_skips_localizations_when_empty(tmp_path: Path) -> None:
    """When metadata.localizations is empty, part is just 'status' and body has no localizations."""
    client = MagicMock()

    metadata = Metadata(
        title="Title",
        description="Desc",
        tags=[],
        category_id=27,
        default_language="zh-TW",
        default_audio_language="zh-TW",
        altered_or_synthetic_content="synthetic_voice",
        localizations={},
    )

    ctx = PipelineContext(
        project_id=1,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=tmp_path,
        youtube_video_id="VIDEO123",
    )

    stage = PublishStage(
        client_factory=lambda p: client,
        channel_config=_make_config(),
    )
    stage._phase_c_disclosure(client, ctx, metadata)

    call_kwargs = client.videos_update.call_args.kwargs
    assert call_kwargs["part"] == "status"
    assert "localizations" not in call_kwargs["body"]


# ---------------------------------------------------------------------------
# Phase D: caption upload
# ---------------------------------------------------------------------------


def test_phase_d_uploads_both_caption_tracks(tmp_path: Path) -> None:
    """When primary and secondary SRTs exist, captions_insert is called for both locales."""
    client = MagicMock()
    client.captions_insert.side_effect = ["CAP_ZHTW", "CAP_EN"]

    primary_srt = tmp_path / "subtitles.srt"
    secondary_srt = tmp_path / "subtitles_en.srt"
    shutil.copy(SRT_FIXTURE, primary_srt)
    shutil.copy(SRT_FIXTURE, secondary_srt)

    ctx = PipelineContext(
        project_id=1,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=tmp_path,
        youtube_video_id="VIDEO123",
        subtitle_path=primary_srt,
        secondary_locale="en",
        secondary_subtitle_path=secondary_srt,
    )

    stage = PublishStage(
        client_factory=lambda p: client,
        channel_config=_make_config(),
    )
    stage._phase_d_captions(client, ctx)

    assert client.captions_insert.call_count == 2
    assert ctx.captions_uploaded == {"zh-TW": "CAP_ZHTW", "en": "CAP_EN"}

    calls = client.captions_insert.call_args_list
    assert calls[0].kwargs["language"] == "zh-TW"
    assert calls[0].kwargs["video_id"] == "VIDEO123"
    assert calls[1].kwargs["language"] == "en"
    assert calls[1].kwargs["video_id"] == "VIDEO123"


def test_phase_d_idempotent_skips_already_uploaded(tmp_path: Path) -> None:
    """If one locale is already in captions_uploaded, captions_insert is only called for the other."""
    client = MagicMock()
    client.captions_insert.return_value = "CAP_EN"

    primary_srt = tmp_path / "subtitles.srt"
    secondary_srt = tmp_path / "subtitles_en.srt"
    shutil.copy(SRT_FIXTURE, primary_srt)
    shutil.copy(SRT_FIXTURE, secondary_srt)

    ctx = PipelineContext(
        project_id=1,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=tmp_path,
        youtube_video_id="VIDEO123",
        subtitle_path=primary_srt,
        secondary_locale="en",
        secondary_subtitle_path=secondary_srt,
        captions_uploaded={"zh-TW": "CAP_ZHTW"},
    )

    stage = PublishStage(
        client_factory=lambda p: client,
        channel_config=_make_config(),
    )
    stage._phase_d_captions(client, ctx)

    # Only the secondary (en) should be uploaded
    client.captions_insert.assert_called_once()
    assert client.captions_insert.call_args.kwargs["language"] == "en"
    assert ctx.captions_uploaded == {"zh-TW": "CAP_ZHTW", "en": "CAP_EN"}


def test_phase_d_skips_missing_srt(tmp_path: Path) -> None:
    """If SRT path does not exist, captions_insert is not called (warning logged)."""
    client = MagicMock()

    ctx = PipelineContext(
        project_id=1,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=tmp_path,
        youtube_video_id="VIDEO123",
        subtitle_path=tmp_path / "nonexistent.srt",
    )

    stage = PublishStage(
        client_factory=lambda p: client,
        channel_config=_make_config(),
    )
    stage._phase_d_captions(client, ctx)

    client.captions_insert.assert_not_called()
    assert ctx.captions_uploaded == {}


# ---------------------------------------------------------------------------
# client.captions_insert unit test
# ---------------------------------------------------------------------------


def test_captions_insert_builds_correct_request(tmp_path: Path) -> None:
    """captions_insert calls the YouTube API with correct snippet body and media."""
    srt = tmp_path / "test.srt"
    shutil.copy(SRT_FIXTURE, srt)

    api = MagicMock()
    api.captions.return_value.insert.return_value.execute.return_value = {
        "id": "CAPTION_ABC",
        "snippet": {"videoId": "VIDEO123", "language": "zh-TW"},
    }

    client = YouTubeClient(api=api)
    caption_id = client.captions_insert(
        video_id="VIDEO123",
        language="zh-TW",
        name="Subtitles (zh-TW)",
        srt_path=srt,
    )

    assert caption_id == "CAPTION_ABC"

    # Verify the API was called with correct part and body
    insert_call = api.captions.return_value.insert
    insert_call.assert_called_once()
    call_kwargs = insert_call.call_args.kwargs
    assert call_kwargs["part"] == "snippet"
    assert call_kwargs["body"]["snippet"]["videoId"] == "VIDEO123"
    assert call_kwargs["body"]["snippet"]["language"] == "zh-TW"
    assert call_kwargs["body"]["snippet"]["name"] == "Subtitles (zh-TW)"
    assert call_kwargs["body"]["snippet"]["isDraft"] is False


# ---------------------------------------------------------------------------
# Full publish flow with MLA
# ---------------------------------------------------------------------------


def test_full_publish_phase_d_called_in_flow(ready_project: Path) -> None:
    """captions_insert is called during full publish flow when subtitle_path exists."""
    srt = ready_project / "subtitles.srt"
    shutil.copy(SRT_FIXTURE, srt)

    client = MagicMock()
    client.videos_insert.return_value = "VIDEO123"
    client.captions_insert.return_value = "CAP_ZHTW"

    stage = PublishStage(
        client_factory=lambda profile: client,
        channel_config=_make_config(),
        privacy="unlisted",
    )
    ctx = PipelineContext(
        project_id=42,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=ready_project,
        niche="sample",
        final_video_path=ready_project / "final.mp4",
        subtitle_path=srt,
    )
    result = stage.publish(ctx, profile_override=None)

    assert result.captions_uploaded.get("zh-TW") == "CAP_ZHTW"
    client.captions_insert.assert_called_once_with(
        video_id="VIDEO123",
        language="zh-TW",
        name="Subtitles (zh-TW)",
        srt_path=srt,
    )
