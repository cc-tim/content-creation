import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.stages.compose import ComposeStage
from pipeline.storyboard import Scene, Storyboard


async def test_compose_uses_storyboard_when_available(sample_context):
    """When storyboard exists, use scene-by-scene rendering."""
    # Create storyboard
    sb = Storyboard(
        scenes=[
            Scene(
                id="s1",
                section="hook",
                narration="test",
                narration_est_sec=5,
                visual={"type": "text_card", "text": "Hook", "background": "#1a1a2e"},
            ),
        ]
    )
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
        {
            "index": 0,
            "text": "test",
            "path": str(audio_dir / "seg_000.mp3"),
            "start_ms": 0,
            "duration_ms": 5000,
        }
    ]
    (audio_dir / "seg_000.mp3").write_bytes(b"fake audio")

    stage = ComposeStage()

    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.render_scene") as mock_render,
        patch("pipeline.stages.compose.apply_overlay"),
        patch("pipeline.stages.compose.run_ffmpeg") as mock_ff,
    ):
        # render_scene returns a fake visual
        visual_out = sample_context.work_dir / "compose" / "scenes" / "s1_visual.mp4"
        visual_out.parent.mkdir(parents=True, exist_ok=True)
        visual_out.write_bytes(b"fake visual")
        mock_render.return_value = visual_out

        def _fake_ffmpeg(cmd):
            out = cmd[-1]
            if isinstance(out, str) and out.endswith(".mp4"):
                Path(out).write_bytes(b"fake")

        mock_ff.side_effect = _fake_ffmpeg

        ctx = await stage.run(sample_context)

    assert ctx.final_video_path is not None
    mock_render.assert_called_once()


async def test_render_one_scene_applies_frame_wrapper_when_theme_requests_it(tmp_path):
    from pipeline.stages.base import PipelineContext

    scenes_dir = tmp_path / "compose" / "scenes"
    scenes_dir.mkdir(parents=True)
    visual = scenes_dir / "s1_visual.mp4"
    visual.write_bytes(b"visual")
    scene = Scene(
        id="s1",
        section="hook",
        narration="test",
        narration_est_sec=1.0,
        visual={"type": "text_card", "text": "Hook"},
        overlay=None,
    )
    ctx = PipelineContext(
        project_id=1,
        source_url="x",
        locale="zh-TW",
        work_dir=tmp_path,
        burn_subtitles=False,
    )
    stage = ComposeStage()

    def fake_frame(src, out, *, frame_style, width, height, fps=30):
        out.write_bytes(b"framed")
        return out

    def fake_mux(vis, out, aud):
        out.write_bytes(b"muxed")

    with (
        patch("pipeline.stages.compose.render_scene", return_value=visual),
        patch("pipeline.stages.compose.check_overlay_allowed"),
        patch("pipeline.stages.compose.composite_scene_frame", side_effect=fake_frame) as frame,
        patch.object(stage, "_mux", side_effect=fake_mux),
    ):
        result = await stage._render_one_scene(
            i=0,
            scene=scene,
            scene_dict={
                "id": "s1",
                "visual": scene.visual,
                "overlay": scene.overlay,
                "compartment": scene.compartment,
                "narration": scene.narration,
            },
            duration=1.0,
            audio_path=None,
            width=1280,
            height=720,
            scenes_dir=scenes_dir,
            source_video=None,
            theme_dict={"frame_style": "open_book_page"},
            frame_style="open_book_page",
            ctx=ctx,
            audio_segments=[],
        )

    assert result.scene_final.name == "s1_final_open_book_page.mp4"
    assert result.scene_final_no_overlay.name == "s1_final_no_overlay_open_book_page.mp4"
    assert frame.call_count == 2


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


def test_compose_burn_subtitles_false_returns_plain_variant(monkeypatch, tmp_path):
    """With burn_subtitles=False, compose copies raw.mp4 to final
    without invoking the -vf subtitles ffmpeg pass."""
    from pathlib import Path

    from pipeline.stages.base import PipelineContext
    from pipeline.stages.compose import ComposeStage
    from pipeline.storyboard import Scene, Storyboard

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    (work_dir / "audio").mkdir()
    narration = work_dir / "audio" / "narration.mp3"
    narration.write_bytes(b"mp3")
    subs = work_dir / "audio" / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")

    storyboard = Storyboard(
        scenes=[
            Scene(
                id="s1",
                section="hook",
                narration="x",
                narration_est_sec=1.0,
                visual={"type": "text_card", "text": "hi"},
            )
        ]
    )
    sb_path = work_dir / "storyboard.json"
    storyboard.save(sb_path)

    ctx = PipelineContext(
        project_id=1,
        source_url="x",
        locale="zh-TW",
        work_dir=work_dir,
        narration_path=narration,
        subtitle_path=subs,
        storyboard_path=sb_path,
        segment_timings=[
            {"index": 0, "text": "x", "path": str(narration), "start_ms": 0, "duration_ms": 1000}
        ],
        burn_subtitles=False,
    )

    ffmpeg_calls: list[list[str]] = []

    def capture(cmd):
        ffmpeg_calls.append(cmd)
        # simulate outputs:
        if "-i" in cmd and cmd[-1].endswith(".mp4"):
            Path(cmd[-1]).write_bytes(b"mp4")

    monkeypatch.setattr("pipeline.stages.compose.run_ffmpeg", capture)
    monkeypatch.setattr(
        "pipeline.stages.compose.check_ffmpeg_available", lambda: True
    )
    def _fake_render(scene, duration, aspect_ratio, work_dir, source_video=None, theme=None):
        return Path(work_dir) / f"{scene['id']}.mp4"

    monkeypatch.setattr("pipeline.stages.compose.render_scene", _fake_render)

    import asyncio

    result_ctx = asyncio.run(ComposeStage().run(ctx))

    # burn_subtitles=False selects the plain variant as final_video_path; subs encoding still runs
    locale = ctx.locale
    compose_dir = work_dir / "compose"
    assert result_ctx.final_video_path == compose_dir / f"final_{locale}.mp4", (
        f"Expected plain variant, got {result_ctx.final_video_path}"
    )
    assert result_ctx.final_video_path != compose_dir / f"final_{locale}_subtitles.mp4"


def test_scenes_json_written_by_storyboard_compose(monkeypatch, tmp_path):
    """After _compose_from_storyboard, compose/scenes.json exists with correct timestamps."""
    from pathlib import Path

    from pipeline.stages.base import PipelineContext
    from pipeline.stages.compose import ComposeStage
    from pipeline.storyboard import Scene, Storyboard

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    audio_dir = work_dir / "audio"
    audio_dir.mkdir()
    narration = audio_dir / "narration.mp3"
    narration.write_bytes(b"mp3")
    subs = audio_dir / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")

    storyboard = Storyboard(
        scenes=[
            Scene(id="s1", section="hook", narration="First scene", narration_est_sec=5.0,
                  visual={"type": "text_card", "text": "hi"}, pause_after_sec=0.5),
            Scene(id="s2", section="context", narration="Second scene", narration_est_sec=8.0,
                  visual={"type": "text_card", "text": "ho"}, pause_after_sec=0.0),
        ]
    )
    sb_path = work_dir / "storyboard.json"
    storyboard.save(sb_path)

    ctx = PipelineContext(
        project_id=1,
        source_url="x",
        locale="zh-TW",
        work_dir=work_dir,
        narration_path=narration,
        subtitle_path=subs,
        storyboard_path=sb_path,
        segment_timings=[
            {
                "index": 0, "text": "First scene", "path": str(narration),
                "start_ms": 0, "duration_ms": 5000,
            },
            {
                "index": 1, "text": "Second scene", "path": str(narration),
                "start_ms": 5000, "duration_ms": 8000,
            },
        ],
        burn_subtitles=False,
    )

    monkeypatch.setattr("pipeline.stages.compose.run_ffmpeg",
        lambda cmd: Path(cmd[-1]).write_bytes(b"mp4"))
    monkeypatch.setattr("pipeline.stages.compose.check_ffmpeg_available", lambda: True)
    monkeypatch.setattr("pipeline.stages.compose.render_scene",
        lambda scene, duration, aspect_ratio, work_dir, source_video=None, theme=None:
            Path(work_dir) / f"{scene['id']}.mp4")

    import asyncio
    asyncio.run(ComposeStage().run(ctx))

    scenes_file = work_dir / "compose" / "scenes.json"
    assert scenes_file.exists(), "compose/scenes.json was not written"
    scenes = json.loads(scenes_file.read_text())
    assert len(scenes) == 2

    assert scenes[0]["id"] == "s1"
    assert scenes[0]["section"] == "hook"
    assert scenes[0]["start_sec"] == 0.0
    assert scenes[0]["duration_sec"] == pytest.approx(5.5)   # 5000ms audio + 0.5s pause
    assert scenes[0]["narration"] == "First scene"

    assert scenes[1]["id"] == "s2"
    assert scenes[1]["start_sec"] == pytest.approx(5.5)
    assert scenes[1]["duration_sec"] == pytest.approx(8.0)   # 8000ms audio + 0s pause
    assert scenes[1]["narration"] == "Second scene"


def test_preferred_variant_persists_in_context(tmp_path):
    """preferred_variant round-trips through to_dict/from_dict."""
    from pipeline.stages.base import PipelineContext
    ctx = PipelineContext(
        project_id=1, source_url="x", locale="zh-TW",
        work_dir=tmp_path, preferred_variant="subtitles_no_overlay",
    )
    data = ctx.to_dict()
    assert data["preferred_variant"] == "subtitles_no_overlay"
    ctx2 = PipelineContext.from_dict(data)
    assert ctx2.preferred_variant == "subtitles_no_overlay"


def test_compose_skips_existing_scene_finals(monkeypatch, tmp_path):
    """If sN_final.mp4 and sN_final_no_overlay.mp4 already exist, render_scene is NOT called."""
    from pipeline.stages.base import PipelineContext

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    audio_dir = work_dir / "audio"
    audio_dir.mkdir()
    narration = audio_dir / "narration.mp3"
    narration.write_bytes(b"mp3")
    subs = audio_dir / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")

    sb = Storyboard(scenes=[
        Scene(id="s1", section="hook", narration="x", narration_est_sec=1.0,
              visual={"type": "text_card", "text": "hi"})
    ])
    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)

    # Pre-create scene finals to simulate a prior completed run
    scenes_dir = work_dir / "compose" / "scenes"
    scenes_dir.mkdir(parents=True)
    (scenes_dir / "s1_final.mp4").write_bytes(b"cached")
    (scenes_dir / "s1_final_no_overlay.mp4").write_bytes(b"cached")

    ctx = PipelineContext(
        project_id=1, source_url="x", locale="zh-TW", work_dir=work_dir,
        narration_path=narration, subtitle_path=subs, storyboard_path=sb_path,
        segment_timings=[{"index": 0, "text": "x", "path": str(narration),
                          "start_ms": 0, "duration_ms": 1000}],
        burn_subtitles=False,
    )

    render_calls = []
    monkeypatch.setattr("pipeline.stages.compose.render_scene",
        lambda *a, **kw: render_calls.append(1) or Path(kw.get("work_dir", a[3])) / "s1.mp4")
    monkeypatch.setattr("pipeline.stages.compose.run_ffmpeg",
        lambda cmd: Path(cmd[-1]).write_bytes(b"mp4"))
    monkeypatch.setattr("pipeline.stages.compose.check_ffmpeg_available", lambda: True)
    monkeypatch.setattr("pipeline.stages.compose._get_duration_sec", lambda p: 1.0)

    import asyncio
    asyncio.run(ComposeStage().run(ctx))

    assert render_calls == [], "render_scene should be skipped when scene finals already exist"


def test_preferred_variant_selects_correct_final_path(monkeypatch, tmp_path):
    """When preferred_variant is set, compose returns that variant's path."""
    from pathlib import Path

    from pipeline.stages.base import PipelineContext
    from pipeline.stages.compose import ComposeStage
    from pipeline.storyboard import Scene, Storyboard

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    audio_dir = work_dir / "audio"
    audio_dir.mkdir()
    narration = audio_dir / "narration.mp3"
    narration.write_bytes(b"mp3")
    subs = audio_dir / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")

    sb = Storyboard(scenes=[
        Scene(id="s1", section="hook", narration="x", narration_est_sec=1.0,
              visual={"type": "text_card", "text": "hi"})
    ])
    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)

    ctx = PipelineContext(
        project_id=1, source_url="x", locale="zh-TW", work_dir=work_dir,
        narration_path=narration, subtitle_path=subs, storyboard_path=sb_path,
        segment_timings=[{"index": 0, "text": "x", "path": str(narration),
                          "start_ms": 0, "duration_ms": 1000}],
        burn_subtitles=False,
        preferred_variant="subtitles_no_overlay",
    )

    monkeypatch.setattr("pipeline.stages.compose.run_ffmpeg",
        lambda cmd: Path(cmd[-1]).write_bytes(b"mp4"))
    monkeypatch.setattr("pipeline.stages.compose.check_ffmpeg_available", lambda: True)
    monkeypatch.setattr("pipeline.stages.compose.render_scene",
        lambda scene, duration, aspect_ratio, work_dir, source_video=None, theme=None:
            Path(work_dir) / f"{scene['id']}.mp4")

    import asyncio
    result_ctx = asyncio.run(ComposeStage().run(ctx))

    compose_dir = work_dir / "compose"
    assert result_ctx.final_video_path == compose_dir / "final_zh-TW_subtitles_no_overlay.mp4"


def test_compose_forces_no_overlay_when_mla(monkeypatch, tmp_path):
    """When ctx.mla=True, compose forces preferred_variant to no_overlay."""
    from pipeline.stages.base import PipelineContext
    from pipeline.stages.compose import ComposeStage
    from pipeline.storyboard import Scene, Storyboard

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    audio_dir = work_dir / "audio"
    audio_dir.mkdir()
    narration = audio_dir / "narration.mp3"
    narration.write_bytes(b"mp3")
    subs = audio_dir / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")

    sb = Storyboard(scenes=[
        Scene(id="s1", section="hook", narration="x", narration_est_sec=1.0,
              visual={"type": "text_card", "text": "hi"})
    ])
    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)

    ctx = PipelineContext(
        project_id=1,
        source_url="x",
        locale="zh-TW",
        work_dir=work_dir,
        narration_path=narration,
        subtitle_path=subs,
        storyboard_path=sb_path,
        segment_timings=[{"index": 0, "text": "x", "path": str(narration),
                          "start_ms": 0, "duration_ms": 1000}],
        burn_subtitles=False,
        preferred_variant=None,
        mla=True,
    )

    monkeypatch.setattr("pipeline.stages.compose.run_ffmpeg",
        lambda cmd: Path(cmd[-1]).write_bytes(b"mp4"))
    monkeypatch.setattr("pipeline.stages.compose.check_ffmpeg_available", lambda: True)
    monkeypatch.setattr("pipeline.stages.compose.render_scene",
        lambda scene, duration, aspect_ratio, work_dir, source_video=None, theme=None:
            Path(work_dir) / f"{scene['id']}.mp4")

    import asyncio
    result_ctx = asyncio.run(ComposeStage().run(ctx))

    # mla=True must force no_overlay variant
    assert result_ctx.preferred_variant == "no_overlay", (
        f"Expected preferred_variant='no_overlay', got {result_ctx.preferred_variant!r}"
    )
    compose_dir = work_dir / "compose"
    assert result_ctx.final_video_path == compose_dir / "final_zh-TW_no_overlay.mp4", (
        f"Expected no_overlay path, got {result_ctx.final_video_path}"
    )
    assert str(result_ctx.final_video_path).endswith("_no_overlay.mp4")


def test_compose_mla_does_not_mux_secondary_audio(monkeypatch, tmp_path):
    """When ctx.mla=True, the secondary_narration_path is never muxed into the final mp4."""
    from pipeline.stages.base import PipelineContext
    from pipeline.stages.compose import ComposeStage
    from pipeline.storyboard import Scene, Storyboard

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    audio_dir = work_dir / "audio"
    audio_dir.mkdir()
    narration = audio_dir / "narration.mp3"
    narration.write_bytes(b"mp3")
    secondary = audio_dir / "secondary_narration.mp3"
    secondary.write_bytes(b"secondary mp3")
    subs = audio_dir / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")

    sb = Storyboard(scenes=[
        Scene(id="s1", section="hook", narration="x", narration_est_sec=1.0,
              visual={"type": "text_card", "text": "hi"})
    ])
    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)

    ctx = PipelineContext(
        project_id=1,
        source_url="x",
        locale="zh-TW",
        work_dir=work_dir,
        narration_path=narration,
        subtitle_path=subs,
        storyboard_path=sb_path,
        segment_timings=[{"index": 0, "text": "x", "path": str(narration),
                          "start_ms": 0, "duration_ms": 1000}],
        burn_subtitles=False,
        mla=True,
        secondary_narration_path=secondary,
    )

    ffmpeg_calls: list[list[str]] = []

    def capture(cmd):
        ffmpeg_calls.append(list(cmd))
        if isinstance(cmd[-1], str) and cmd[-1].endswith(".mp4"):
            Path(cmd[-1]).write_bytes(b"mp4")

    monkeypatch.setattr("pipeline.stages.compose.run_ffmpeg", capture)
    monkeypatch.setattr("pipeline.stages.compose.check_ffmpeg_available", lambda: True)
    monkeypatch.setattr("pipeline.stages.compose.render_scene",
        lambda scene, duration, aspect_ratio, work_dir, source_video=None, theme=None:
            Path(work_dir) / f"{scene['id']}.mp4")

    import asyncio
    asyncio.run(ComposeStage().run(ctx))

    secondary_str = str(secondary)
    for cmd in ffmpeg_calls:
        assert secondary_str not in cmd, (
            f"secondary_narration_path was muxed into ffmpeg cmd: {cmd}"
        )
