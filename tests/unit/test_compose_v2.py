from pathlib import Path
from unittest.mock import MagicMock, patch

from pipeline.stages.compose import ComposeStage
from pipeline.storyboard import Scene, Storyboard


async def test_compose_uses_storyboard_when_available(sample_context):
    """When storyboard exists, use scene-by-scene rendering."""
    # Create storyboard
    sb = Storyboard(scenes=[
        Scene(id="s1", section="hook", narration="test",
              narration_est_sec=5,
              visual={"type": "text_card", "text": "Hook", "background": "#1a1a2e"}),
    ])
    sb_path = sample_context.work_dir / "storyboard.json"
    sb.save(sb_path)
    sample_context.storyboard_path = sb_path

    # Create required paths
    audio_dir = sample_context.work_dir / "audio"
    audio_dir.mkdir(parents=True)
    narration = audio_dir / "narration.mp3"
    narration.write_bytes(b"fake")
    sample_context.narration_path = narration

    subtitle = audio_dir / "subs.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:05,000\ntest\n")
    sample_context.subtitle_path = subtitle

    sample_context.segment_timings = [
        {"index": 0, "text": "test", "path": str(audio_dir / "seg_000.mp3"),
         "start_ms": 0, "duration_ms": 5000}
    ]
    (audio_dir / "seg_000.mp3").write_bytes(b"fake audio")

    stage = ComposeStage()

    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.render_scene") as mock_render,
        patch("pipeline.stages.compose.apply_overlay") as mock_overlay,
        patch("pipeline.stages.compose.run_ffmpeg") as mock_ff,
    ):
        # render_scene returns a fake visual
        visual_out = sample_context.work_dir / "compose" / "scenes" / "s1_visual.mp4"
        visual_out.parent.mkdir(parents=True, exist_ok=True)
        visual_out.write_bytes(b"fake visual")
        mock_render.return_value = visual_out

        mock_ff.return_value = MagicMock(returncode=0)

        # Create expected output files that ffmpeg would produce
        (sample_context.work_dir / "compose" / "scenes" / "s1_final.mp4").write_bytes(b"f")
        (sample_context.work_dir / "compose" / "raw.mp4").write_bytes(b"f")
        final = sample_context.work_dir / "compose" / f"final_{sample_context.locale}.mp4"
        final.write_bytes(b"final")

        ctx = await stage.run(sample_context)

    assert ctx.final_video_path is not None
    mock_render.assert_called_once()


async def test_compose_falls_back_to_mvp(sample_context):
    """When no storyboard, use MVP compose."""
    source_dir = sample_context.work_dir / "source"
    source_dir.mkdir(parents=True)
    video = source_dir / "video.mp4"
    video.write_bytes(b"fake")
    sample_context.video_path = video
    sample_context.storyboard_path = None  # No storyboard

    audio_dir = sample_context.work_dir / "audio"
    audio_dir.mkdir(parents=True)
    narration = audio_dir / "narration.mp3"
    narration.write_bytes(b"fake")
    sample_context.narration_path = narration

    subtitle = audio_dir / "subs.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:05,000\ntest\n")
    sample_context.subtitle_path = subtitle

    sample_context.script_path = sample_context.work_dir / "script.md"
    sample_context.script_path.write_text("[HOOK]\ntest")

    stage = ComposeStage()

    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose._get_duration_sec", return_value=60.0),
        patch("pipeline.stages.compose.run_ffmpeg") as mock_ff,
    ):
        mock_ff.return_value = MagicMock(returncode=0)
        final = sample_context.work_dir / "compose" / f"final_{sample_context.locale}.mp4"
        final.parent.mkdir(parents=True, exist_ok=True)
        final.write_bytes(b"final")

        ctx = await stage.run(sample_context)

    assert ctx.final_video_path is not None
    # Should have called run_ffmpeg with MVP approach (single call)
    assert mock_ff.called
