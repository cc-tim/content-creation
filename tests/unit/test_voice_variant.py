# tests/unit/test_voice_variant.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from pipeline.cli_compose import compose_app
from pipeline.stages.base import PipelineContext


def _base_ctx(work_dir: Path) -> PipelineContext:
    return PipelineContext(
        project_id=9000,
        source_url="https://youtube.com/watch?v=abc",
        locale="zh-TW",
        work_dir=work_dir,
    )


def test_parent_project_id_defaults_none(tmp_path):
    ctx = _base_ctx(tmp_path)
    assert ctx.parent_project_id is None
    assert ctx.variant_label is None


def test_variant_fields_round_trip(tmp_path):
    ctx = _base_ctx(tmp_path)
    ctx.parent_project_id = 1776997800
    ctx.variant_label = "tim-zhtw-fish"
    ctx.save()

    loaded = PipelineContext.load(tmp_path / "context.json")
    assert loaded.parent_project_id == 1776997800
    assert loaded.variant_label == "tim-zhtw-fish"


def test_from_dict_ignores_missing_variant_fields(tmp_path):
    """Old context.json without new fields loads without error."""
    ctx = _base_ctx(tmp_path)
    d = ctx.to_dict()
    d.pop("parent_project_id", None)
    d.pop("variant_label", None)
    loaded = PipelineContext.from_dict(d)
    assert loaded.parent_project_id is None
    assert loaded.variant_label is None


def _make_parent_project(tmp_path: Path) -> Path:
    """Minimal fully-built parent project directory."""
    work_dir = tmp_path / "projects" / "1776997800"
    (work_dir / "audio").mkdir(parents=True)
    (work_dir / "compose" / "scenes").mkdir(parents=True)
    (work_dir / "script").mkdir(parents=True)

    (work_dir / "storyboard.json").write_text(
        '{"scenes": [], "aspect_ratio": "16:9", "theme": {}}'
    )
    (work_dir / "knowledge.json").write_text("{}")
    (work_dir / "script" / "script_zh-TW.md").write_text("narration")
    (work_dir / "metadata.json").write_text("{}")
    (work_dir / "thumbnail.png").write_bytes(b"png")

    srt = work_dir / "audio" / "subs.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")

    ctx = PipelineContext(
        project_id=1776997800,
        source_url="https://youtube.com/watch?v=abc",
        locale="zh-TW",
        work_dir=work_dir,
        niche="parenting",
        storyboard_path=work_dir / "storyboard.json",
        script_path=work_dir / "script" / "script_zh-TW.md",
        knowledge_path=work_dir / "knowledge.json",
        subtitle_path=srt,
        preferred_variant="subtitles_no_overlay",
        segment_timings=[{"path": str(work_dir / "audio" / "s1.wav"),
                          "text": "Hello", "start_ms": 0, "duration_ms": 1000}],
    )
    ctx.save()
    return work_dir


def test_voice_variant_creates_dir_structure(tmp_path):
    """voice-variant creates {parent}_{voice} directory with copied assets."""
    _make_parent_project(tmp_path)
    variant_dir = tmp_path / "projects" / "1776997800_tim-zhtw-fish"

    runner = CliRunner()
    with (
        patch("pipeline.cli_compose._resolve_projects_dir", return_value=tmp_path / "projects"),
        patch("pipeline.cli_compose.asyncio.run"),  # skip TTS+compose
    ):
        result = runner.invoke(compose_app, [
            "voice-variant",
            "--from-project", "1776997800",
            "--voice", "tim-zhtw-fish",
        ])

    assert result.exit_code == 0, result.output
    assert (variant_dir / "storyboard.json").exists()
    assert (variant_dir / "knowledge.json").exists()
    assert (variant_dir / "script" / "script_zh-TW.md").exists()
    assert (variant_dir / "metadata.json").exists()
    assert (variant_dir / "thumbnail.png").exists()


def test_voice_variant_context_json(tmp_path):
    """voice-variant writes correct context.json overrides."""
    _make_parent_project(tmp_path)
    variant_dir = tmp_path / "projects" / "1776997800_tim-zhtw-fish"

    runner = CliRunner()
    with (
        patch("pipeline.cli_compose._resolve_projects_dir", return_value=tmp_path / "projects"),
        patch("pipeline.cli_compose.asyncio.run"),
    ):
        runner.invoke(compose_app, [
            "voice-variant",
            "--from-project", "1776997800",
            "--voice", "tim-zhtw-fish",
        ])

    ctx = PipelineContext.load(variant_dir / "context.json")
    assert ctx.voice_id == "tim-zhtw-fish"
    assert ctx.parent_project_id == 1776997800
    assert ctx.variant_label == "tim-zhtw-fish"
    assert ctx.segment_timings is None
    assert ctx.subtitle_path is None
    assert ctx.narration_path is None
    assert ctx.final_video_path is None
    assert ctx.youtube_video_id is None
    # storyboard/script/knowledge point INSIDE the variant dir
    assert ctx.storyboard_path is not None
    assert str(ctx.storyboard_path).startswith(str(variant_dir))
    assert ctx.script_path is not None
    assert str(ctx.script_path).startswith(str(variant_dir))


def test_voice_variant_errors_if_exists(tmp_path):
    """voice-variant exits with error if variant dir already exists."""
    _make_parent_project(tmp_path)
    variant_dir = tmp_path / "projects" / "1776997800_tim-zhtw-fish"
    variant_dir.mkdir(parents=True)

    runner = CliRunner()
    with patch("pipeline.cli_compose._resolve_projects_dir", return_value=tmp_path / "projects"):
        result = runner.invoke(compose_app, [
            "voice-variant",
            "--from-project", "1776997800",
            "--voice", "tim-zhtw-fish",
        ])

    assert result.exit_code != 0
    assert "already exists" in result.output


def test_voice_variant_force_overwrites(tmp_path):
    """voice-variant --force removes existing variant dir before creating."""
    _make_parent_project(tmp_path)
    variant_dir = tmp_path / "projects" / "1776997800_tim-zhtw-fish"
    variant_dir.mkdir(parents=True)
    stale = variant_dir / "stale.txt"
    stale.write_text("stale")

    runner = CliRunner()
    with (
        patch("pipeline.cli_compose._resolve_projects_dir", return_value=tmp_path / "projects"),
        patch("pipeline.cli_compose.asyncio.run"),
    ):
        result = runner.invoke(compose_app, [
            "voice-variant",
            "--from-project", "1776997800",
            "--voice", "tim-zhtw-fish",
            "--force",
        ])

    assert result.exit_code == 0, result.output
    assert not stale.exists()
    assert (variant_dir / "storyboard.json").exists()


def _make_variant_project(tmp_path: Path, parent_dir: Path) -> Path:
    """Minimal rendered variant project."""
    variant_dir = tmp_path / "projects" / "1776997800_tim-zhtw-fish"
    audio_dir = variant_dir / "audio"
    scenes_dir = variant_dir / "compose" / "scenes"
    audio_dir.mkdir(parents=True)
    scenes_dir.mkdir(parents=True)
    (variant_dir / "script").mkdir()

    srt = audio_dir / "subs.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")
    narration = audio_dir / "narration.wav"
    narration.write_bytes(b"wav")
    s1 = audio_dir / "s1.wav"
    s1.write_bytes(b"s1wav")

    (scenes_dir / "s1_final.mp4").write_bytes(b"s1final")
    (scenes_dir / "s1_final_no_overlay.mp4").write_bytes(b"s1final_no_ov")

    ctx = PipelineContext(
        project_id=9001,
        source_url="https://youtube.com/watch?v=abc",
        locale="zh-TW",
        work_dir=variant_dir,
        parent_project_id=1776997800,
        variant_label="tim-zhtw-fish",
        voice_id="tim-zhtw-fish",
        subtitle_path=srt,
        narration_path=narration,
        niche="parenting",
        preferred_variant="subtitles_no_overlay",
        segment_timings=[{
            "path": str(s1),
            "text": "Hello",
            "start_ms": 0,
            "duration_ms": 1000,
        }],
        storyboard_path=parent_dir / "storyboard.json",
    )
    ctx.save()
    return variant_dir


def test_promote_voice_copies_scenes_and_audio(tmp_path):
    """promote-voice copies variant's scenes + audio to parent dir."""
    parent_dir = _make_parent_project(tmp_path)
    _make_variant_project(tmp_path, parent_dir)

    runner = CliRunner()
    with (
        patch("pipeline.cli_compose._resolve_projects_dir", return_value=tmp_path / "projects"),
        patch("pipeline.cli_compose.asyncio.run"),  # skip ComposeStage
    ):
        result = runner.invoke(compose_app, [
            "promote-voice",
            "--from-project", "1776997800_tim-zhtw-fish",
        ])

    assert result.exit_code == 0, result.output
    assert (parent_dir / "compose" / "scenes" / "s1_final.mp4").read_bytes() == b"s1final"
    assert (parent_dir / "compose" / "scenes" / "s1_final_no_overlay.mp4").read_bytes() == b"s1final_no_ov"
    assert (parent_dir / "audio" / "narration.wav").exists()


def test_promote_voice_updates_parent_context(tmp_path):
    """promote-voice patches parent context.json with variant's voice + timings."""
    parent_dir = _make_parent_project(tmp_path)
    _make_variant_project(tmp_path, parent_dir)

    runner = CliRunner()
    with (
        patch("pipeline.cli_compose._resolve_projects_dir", return_value=tmp_path / "projects"),
        patch("pipeline.cli_compose.asyncio.run"),
    ):
        runner.invoke(compose_app, [
            "promote-voice",
            "--from-project", "1776997800_tim-zhtw-fish",
        ])

    parent_ctx = PipelineContext.load(parent_dir / "context.json")
    assert parent_ctx.voice_id == "tim-zhtw-fish"
    assert parent_ctx.segment_timings is not None
    assert parent_ctx.subtitle_path is not None
    assert str(parent_ctx.subtitle_path).startswith(str(parent_dir))


def test_promote_voice_errors_without_parent_project_id(tmp_path):
    """promote-voice exits with error if variant has no parent_project_id."""
    orphan_dir = tmp_path / "projects" / "orphan"
    orphan_dir.mkdir(parents=True)
    ctx = PipelineContext(
        project_id=9002,
        source_url="x",
        locale="zh-TW",
        work_dir=orphan_dir,
    )
    ctx.save()

    runner = CliRunner()
    with patch("pipeline.cli_compose._resolve_projects_dir", return_value=tmp_path / "projects"):
        result = runner.invoke(compose_app, ["promote-voice", "--from-project", "orphan"])

    assert result.exit_code != 0
    assert "not a voice variant" in result.output.lower() or "parent_project_id" in result.output.lower()
