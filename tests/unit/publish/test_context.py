from __future__ import annotations

from pathlib import Path

from pipeline.stages.base import PipelineContext


def test_context_has_publish_fields(tmp_path: Path) -> None:
    ctx = PipelineContext(
        project_id=1,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=tmp_path,
    )
    assert ctx.niche is None
    assert ctx.thumbnail_uploaded is False
    assert ctx.disclosure_set is False
    assert ctx.published_at is None
    assert ctx.publish_profile is None


def test_context_roundtrip_preserves_publish_fields(tmp_path: Path) -> None:
    ctx = PipelineContext(
        project_id=1,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=tmp_path,
        niche="parenting",
        thumbnail_uploaded=True,
        disclosure_set=True,
        published_at="2026-04-23T00:00:00+00:00",
        publish_profile="ideal-parents-tw",
        youtube_video_id="abc123",
    )
    path = ctx.save()
    loaded = PipelineContext.load(path)
    assert loaded.niche == "parenting"
    assert loaded.thumbnail_uploaded is True
    assert loaded.disclosure_set is True
    assert loaded.published_at == "2026-04-23T00:00:00+00:00"
    assert loaded.publish_profile == "ideal-parents-tw"
    assert loaded.youtube_video_id == "abc123"
