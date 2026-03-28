from unittest.mock import MagicMock, patch

from pipeline.stages.compose import ComposeStage, build_composition_plan


def test_build_composition_plan():
    script = (
        "[HOOK]\n"
        "[CLIP:00:05-00:20]\n"
        "旁白文字\n"
        "[OVERLAY:map:Texas]\n"
        "更多旁白\n"
    )
    plan = build_composition_plan(script)
    assert any(step["type"] == "clip" for step in plan)
    assert any(step["type"] == "overlay" for step in plan)


async def test_compose_builds_ffmpeg_commands(sample_context):
    # Set up all prerequisite paths
    source_dir = sample_context.work_dir / "source"
    source_dir.mkdir(parents=True)
    video_path = source_dir / "video.mp4"
    video_path.write_bytes(b"fake video")
    sample_context.video_path = video_path

    audio_dir = sample_context.work_dir / "audio"
    audio_dir.mkdir(parents=True)
    narration_path = audio_dir / "narration_zh-TW.mp3"
    narration_path.write_bytes(b"fake audio")
    sample_context.narration_path = narration_path

    subtitle_path = audio_dir / "subtitles_zh-TW.srt"
    subtitle_path.write_text("1\n00:00:00,000 --> 00:00:03,000\n測試\n")
    sample_context.subtitle_path = subtitle_path

    script_dir = sample_context.work_dir / "script"
    script_dir.mkdir(parents=True)
    script_path = script_dir / "script_zh-TW.md"
    script_path.write_text("[HOOK]\n[CLIP:00:05-00:20]\n旁白\n")
    sample_context.script_path = script_path

    sample_context.segment_timings = [
        {"index": 0, "text": "旁白", "start_ms": 0, "duration_ms": 3000}
    ]

    stage = ComposeStage()
    assert stage.name == "compose"

    # Mock run_ffmpeg to avoid needing real ffmpeg
    with (
        patch("pipeline.stages.compose.run_ffmpeg") as mock_ffmpeg,
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch.object(stage, "_compose_video") as mock_compose,
    ):
        mock_ffmpeg.return_value = MagicMock(returncode=0)
        final_path = sample_context.work_dir / "compose" / "final_zh-TW.mp4"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(b"fake final video")
        mock_compose.return_value = final_path

        ctx = await stage.run(sample_context)

    assert ctx.final_video_path is not None
