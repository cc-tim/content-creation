import json
from pathlib import Path

from pipeline.stages.base import PipelineContext


def test_context_round_trip_serialization(tmp_path: Path):
    ctx = PipelineContext(
        project_id=1,
        source_url="https://youtube.com/watch?v=abc",
        locale="zh-TW",
        work_dir=tmp_path / "project_1",
    )
    ctx.transcript_text = "Hello world"
    ctx.clip_timestamps = [(0.0, 30.0), (120.0, 135.0)]

    # Serialize
    data = ctx.to_dict()
    json_str = json.dumps(data)

    # Deserialize
    loaded = PipelineContext.from_dict(json.loads(json_str))
    assert loaded.project_id == 1
    assert loaded.source_url == "https://youtube.com/watch?v=abc"
    assert loaded.locale == "zh-TW"
    assert loaded.transcript_text == "Hello world"
    assert loaded.video_path is None
    # clip_timestamps should round-trip as tuples
    assert loaded.clip_timestamps == [(0.0, 30.0), (120.0, 135.0)]
    assert isinstance(loaded.clip_timestamps[0], tuple)


def test_context_save_and_load(tmp_path: Path):
    work_dir = tmp_path / "project_1"
    work_dir.mkdir()
    ctx = PipelineContext(
        project_id=1,
        source_url="https://youtube.com/watch?v=abc",
        locale="zh-TW",
        work_dir=work_dir,
    )
    ctx.save()
    loaded = PipelineContext.load(work_dir / "context.json")
    assert loaded.project_id == ctx.project_id
    assert loaded.work_dir == ctx.work_dir


def test_context_new_path_fields(tmp_path: Path):
    ctx = PipelineContext(
        project_id=1,
        source_url="https://youtube.com/watch?v=abc",
        locale="zh-TW",
        work_dir=tmp_path / "project_1",
    )
    ctx.knowledge_path = tmp_path / "knowledge.json"
    ctx.storyboard_path = tmp_path / "storyboard.json"

    data = ctx.to_dict()
    loaded = PipelineContext.from_dict(data)
    assert loaded.knowledge_path == ctx.knowledge_path
    assert loaded.storyboard_path == ctx.storyboard_path


def test_context_roundtrips_source_locale_and_reference_storyboard(tmp_path):
    ctx = PipelineContext(
        project_id=1,
        source_url="original",
        locale="ja",
        work_dir=tmp_path,
        source_locale="US",
        reference_storyboard_path=tmp_path / "storyboard_en.json",
    )

    round = PipelineContext.from_dict(ctx.to_dict())

    assert round.source_locale == "US"
    assert round.reference_storyboard_path == tmp_path / "storyboard_en.json"
