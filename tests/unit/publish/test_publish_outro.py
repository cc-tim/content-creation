from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.publish.channels import ChannelConfig, ChannelProfile
from pipeline.publish.stage import PublishStage
from pipeline.stages.base import PipelineContext


def _profile(outro_enabled: bool = True) -> ChannelProfile:
    return ChannelProfile(
        name="ideal-parents-tw",
        niche="parenting",
        locale="zh-TW",
        channel_id="UC123",
        voice_guide="",
        default_tags=[],
        category_id=27,
        display_name="理想父母",
        tagline="陪你走過每個育兒時刻",
        outro_enabled=outro_enabled,
    )


def _cfg(outro_enabled: bool = True) -> ChannelConfig:
    prof = _profile(outro_enabled)
    return ChannelConfig(
        profiles={"ideal-parents-tw": prof},
        routing={"parenting/zh-TW": "ideal-parents-tw"},
    )


def _stage(outro_enabled: bool = True) -> PublishStage:
    return PublishStage(
        client_factory=MagicMock(),
        channel_config=_cfg(outro_enabled),
    )


def _ctx(work_dir: Path) -> PipelineContext:
    video = work_dir / "final.mp4"
    video.write_bytes(b"x" * 1024)
    return PipelineContext(
        project_id=1,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=work_dir,
        niche="parenting",
        final_video_path=video,
    )


def test_outro_attached_when_enabled_and_exists(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    channels_dir = tmp_path / "channels"
    outro_dir = channels_dir / "ideal-parents-tw"
    outro_dir.mkdir(parents=True)
    (outro_dir / "outro.mp4").write_bytes(b"x" * 512)

    def _fake_concat(inputs: list[Path], output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"merged")

    def _fake_ffprobe(args, **kwargs):
        result = MagicMock()
        if "ffprobe" in str(args[0]):
            result.stdout = "567.8\n"
            result.returncode = 0
        return result

    with (
        patch("pipeline.publish.stage.ffmpeg_concat", side_effect=_fake_concat),
        patch("subprocess.run", side_effect=_fake_ffprobe),
    ):
        stage = _stage(outro_enabled=True)
        stage._attach_outro(ctx, _profile(outro_enabled=True), channels_dir=channels_dir)

    assert ctx.final_video_path is not None
    assert ctx.final_video_path.name == "final_with_outro.mp4"


def test_outro_skipped_when_disabled(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    original_path = ctx.final_video_path

    with patch("pipeline.publish.stage.ffmpeg_concat") as mock_concat:
        stage = _stage(outro_enabled=False)
        stage._attach_outro(ctx, _profile(outro_enabled=False), channels_dir=tmp_path)

    mock_concat.assert_not_called()
    assert ctx.final_video_path == original_path


def test_outro_warning_when_enabled_but_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    ctx = _ctx(tmp_path)
    original_path = ctx.final_video_path

    with patch("pipeline.publish.stage.ffmpeg_concat") as mock_concat:
        stage = _stage(outro_enabled=True)
        stage._attach_outro(
            ctx,
            _profile(outro_enabled=True),
            channels_dir=tmp_path / "nonexistent",
        )

    mock_concat.assert_not_called()
    assert ctx.final_video_path == original_path
    # structlog outputs to stdout; verify warning was emitted
    captured = capsys.readouterr()
    assert "outro_missing" in captured.out or "outro_missing" in captured.err
