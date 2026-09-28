import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pipeline.niche_templates import NicheTemplate
from pipeline.stages.compose import ComposeStage
from pipeline.storyboard import Scene, Storyboard


@pytest.fixture(autouse=True)
def _skip_media_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pipeline.stages.compose._assert_playable_video", lambda *_args, **_kwargs: None)

    def fake_atomic(cmd, output, timeout=600):
        from pipeline.stages import compose as compose_module

        result = compose_module.run_ffmpeg(cmd)
        output.write_bytes(b"mp4")
        return result

    monkeypatch.setattr("pipeline.stages.compose.run_ffmpeg_atomic", fake_atomic)


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


async def test_compose_forwards_niche_split_style_fields(sample_context):
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
    sample_context.niche = "parenting"

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

    template = NicheTemplate(
        niche="parenting",
        intro_type="generated_image",
        intro_prompt_hint="hint",
        visual_style="cream background, no text in images",
        anchor_prompt="anchor",
        medium_hint="soft sketch lines",
        palette="cream background",
        subject_bias="same parent-child duo",
        universal_rules="no text in images",
    )
    style_anchor = SimpleNamespace(
        style_descriptor="cream background, no text in images",
        seed=123,
        anchor_image=None,
        suitability="",
    )

    stage = ComposeStage()
    with (
        patch("pipeline.niche_templates.load_niche_template", return_value=template),
        patch("pipeline.composer.style_anchor.extract_style_anchor", return_value=style_anchor),
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.render_scene") as mock_render,
        patch("pipeline.stages.compose.apply_overlay"),
        patch("pipeline.stages.compose.run_ffmpeg") as mock_ff,
    ):
        visual_out = sample_context.work_dir / "compose" / "scenes" / "s1_visual.mp4"
        visual_out.parent.mkdir(parents=True, exist_ok=True)
        visual_out.write_bytes(b"fake visual")
        mock_render.return_value = visual_out

        def _fake_ffmpeg(cmd):
            out = cmd[-1]
            if isinstance(out, str) and out.endswith(".mp4"):
                Path(out).write_bytes(b"fake")

        mock_ff.side_effect = _fake_ffmpeg
        await stage.run(sample_context)

    theme = mock_render.call_args.kwargs["theme"]
    assert theme["medium_hint"] == "soft sketch lines"
    assert theme["palette"] == "cream background"
    assert theme["subject_bias"] == "same parent-child duo"
    assert theme["universal_rules"] == "no text in images"


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


async def test_compose_blocks_storyboard_with_invalid_visual(sample_context):
    sb = Storyboard(
        scenes=[
            Scene(
                id="s1",
                section="hook",
                narration="test",
                narration_est_sec=5,
                visual={"type": "article_image", "path": "missing.jpg"},
            ),
        ]
    )
    sb_path = sample_context.work_dir / "storyboard.json"
    sb.save(sb_path)
    sample_context.storyboard_path = sb_path
    audio_dir = sample_context.work_dir / "audio"
    audio_dir.mkdir(parents=True)
    sample_context.narration_path = audio_dir / "narration.mp3"
    sample_context.narration_path.write_bytes(b"fake")
    sample_context.subtitle_path = audio_dir / "subs.srt"
    sample_context.subtitle_path.write_text("1\n00:00:00,000 --> 00:00:05,000\ntest\n")

    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        pytest.raises(ValueError, match="Storyboard visual validation failed"),
    ):
        await ComposeStage().run(sample_context)


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
    def _fake_render(scene, duration, aspect_ratio, work_dir, source_video=None, theme=None, project_root=None):
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
        lambda scene, duration, aspect_ratio, work_dir, source_video=None, theme=None, project_root=None:
            Path(work_dir) / f"{scene['id']}.mp4")

    # scenes.json is now derived from the ACTUAL concatenated clip durations.
    # ffmpeg is mocked (clips are not real videos), so stub _get_duration_sec to
    # report durations by clip filename: scene finals carry their audio length,
    # pause clips carry pause_after_sec.
    clip_durations = {"s1": 5.0, "s2": 8.0}
    def fake_duration(path):
        name = Path(path).name
        if "_pause" in name:
            return 0.5 if name.startswith("s1_") else 0.0
        for sid, dur in clip_durations.items():
            if name.startswith(f"{sid}_final"):
                return dur
        return 0.0
    monkeypatch.setattr("pipeline.stages.compose._get_duration_sec", fake_duration)

    import asyncio
    asyncio.run(ComposeStage().run(ctx))

    scenes_file = work_dir / "compose" / "scenes.json"
    assert scenes_file.exists(), "compose/scenes.json was not written"
    scenes = json.loads(scenes_file.read_text())
    assert len(scenes) == 2

    assert scenes[0]["id"] == "s1"
    assert scenes[0]["section"] == "hook"
    assert scenes[0]["start_sec"] == 0.0
    assert scenes[0]["duration_sec"] == pytest.approx(5.5)   # 5.0s clip + 0.5s pause
    assert scenes[0]["narration"] == "First scene"

    assert scenes[1]["id"] == "s2"
    assert scenes[1]["start_sec"] == pytest.approx(5.5)
    assert scenes[1]["duration_sec"] == pytest.approx(8.0)   # 8.0s clip + 0s pause
    assert scenes[1]["narration"] == "Second scene"


def test_write_scenes_json_counts_intro_and_transitions(monkeypatch, tmp_path):
    """scenes.json start_sec must include the intro plate and between-scene
    transition clips (the dashboard-misalignment bug: the old model undercounted
    these, pushing the playhead ahead of the content)."""
    from pipeline.stages.compose import ComposeStage
    from pipeline.storyboard import Scene, Storyboard

    sb = Storyboard(scenes=[
        Scene(id="s1", section="hook", narration="A", narration_est_sec=5.0,
              visual={"type": "text_card", "text": "a"}),
        Scene(id="s2", section="context", narration="B", narration_est_sec=8.0,
              visual={"type": "text_card", "text": "b"}),
    ])
    # Ordered concat list as compose builds it: intro, s1, transition, s2, s2 pause.
    clips = [
        Path("transitions/book_start_plate.mp4"),
        Path("s1_final_no_overlay_open_book_page.mp4"),
        Path("transitions/abc123.mp4"),
        Path("s2_final_no_overlay_open_book_page.mp4"),
        Path("s2_pause.mp4"),
    ]
    durs = {
        "book_start_plate.mp4": 1.5,
        "s1_final_no_overlay_open_book_page.mp4": 5.0,
        "abc123.mp4": 1.429,
        "s2_final_no_overlay_open_book_page.mp4": 8.0,
        "s2_pause.mp4": 0.3,
    }
    monkeypatch.setattr("pipeline.stages.compose._get_duration_sec",
                        lambda p: durs[Path(p).name])

    ComposeStage._write_scenes_json(tmp_path, clips, sb)
    scenes = json.loads((tmp_path / "scenes.json").read_text())

    # s1 begins after the 1.5s intro; s2 after intro + s1 + transition.
    assert scenes[0]["start_sec"] == pytest.approx(1.5)
    assert scenes[1]["start_sec"] == pytest.approx(1.5 + 5.0 + 1.429)
    # Contiguous windows: s1 spans until s2 begins (absorbs the trailing transition).
    assert scenes[0]["duration_sec"] == pytest.approx(5.0 + 1.429)
    # s2 runs to the end of the concat (its clip + pause).
    assert scenes[1]["duration_sec"] == pytest.approx(8.0 + 0.3)


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
        lambda scene, duration, aspect_ratio, work_dir, source_video=None, theme=None, project_root=None:
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
        lambda scene, duration, aspect_ratio, work_dir, source_video=None, theme=None, project_root=None:
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
        lambda scene, duration, aspect_ratio, work_dir, source_video=None, theme=None, project_root=None:
            Path(work_dir) / f"{scene['id']}.mp4")

    import asyncio
    asyncio.run(ComposeStage().run(ctx))

    secondary_str = str(secondary)
    for cmd in ffmpeg_calls:
        assert secondary_str not in cmd, (
            f"secondary_narration_path was muxed into ffmpeg cmd: {cmd}"
        )


def test_concat_scenes_uses_filter_concat_to_normalize_mixed_audio(
    monkeypatch, tmp_path,
):
    from pipeline.stages.compose import ComposeStage

    scene = tmp_path / "scene.mp4"
    transition = tmp_path / "transition.mp4"
    pause = tmp_path / "pause.mp4"
    output = tmp_path / "raw_no_overlay.mp4"
    seen: dict[str, list[str] | Path] = {}

    def fake_atomic(cmd: list[str], output_path: Path, timeout: int = 600):
        seen["cmd"] = cmd
        seen["output"] = output_path

    monkeypatch.setattr("pipeline.stages.compose.run_ffmpeg_atomic", fake_atomic)
    monkeypatch.setattr("pipeline.stages.compose._assert_playable_video", lambda path: None)

    ComposeStage()._concat_scenes([scene, transition, pause], output)

    cmd = seen["cmd"]
    assert isinstance(cmd, list)
    assert seen["output"] == output
    assert not ("-f" in cmd and "concat" in cmd)
    assert cmd.count("-i") == 3
    filter_arg = cmd[cmd.index("-filter_complex") + 1]
    assert "concat=n=3:v=1:a=1" in filter_arg
    assert "sample_rates=48000" in filter_arg
    assert "channel_layouts=stereo" in filter_arg
    assert "-c:v" in cmd
    assert cmd[cmd.index("-c:v") + 1] == "libx264"


async def test_overlay_failure_refuses_assembly_and_records_loudly(sample_context):
    """A failing apply_overlay must surface loudly (reliability posture: loud
    over silent). The swap raises SceneRenderError per-scene; ComposeStage's
    existing machinery records reason + suggested_fix in ctx.render_failures and
    refuses final assembly with a RuntimeError — instead of the old behavior,
    which logged a warning and completed silently."""
    sb = Storyboard(
        scenes=[
            Scene(
                id="s1",
                section="hook",
                narration="test",
                narration_est_sec=5,
                visual={"type": "text_card", "text": "Hook", "background": "#1a1a2e"},
                overlay={"type": "title", "text": "hi"},
            ),
        ]
    )
    sb_path = sample_context.work_dir / "storyboard.json"
    sb.save(sb_path)
    sample_context.storyboard_path = sb_path

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
         "start_ms": 0, "duration_ms": 5000},
    ]
    (audio_dir / "seg_000.mp3").write_bytes(b"fake audio")

    stage = ComposeStage()

    def _boom(*a, **k):
        raise RuntimeError("ffmpeg drawtext blew up")

    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.render_scene") as mock_render,
        patch("pipeline.stages.compose.apply_overlay", side_effect=_boom),
        patch("pipeline.stages.compose.run_ffmpeg") as mock_ff,
    ):
        visual_out = sample_context.work_dir / "compose" / "scenes" / "s1_visual.mp4"
        visual_out.parent.mkdir(parents=True, exist_ok=True)
        visual_out.write_bytes(b"fake visual")
        mock_render.return_value = visual_out

        def _fake_ffmpeg(cmd):
            out = cmd[-1]
            if isinstance(out, str) and out.endswith(".mp4"):
                Path(out).write_bytes(b"fake")

        mock_ff.side_effect = _fake_ffmpeg

        # Assembly is refused (loud) rather than completing with a warning.
        with pytest.raises(RuntimeError, match="overlay"):
            await stage.run(sample_context)

    # The overlay failure is recorded with its reason + actionable suggested_fix.
    assert "s1" in sample_context.render_failures
    failure = sample_context.render_failures["s1"]
    assert "overlay failed" in failure["reason"]
    assert "--skip-overlays" in failure["suggested_fix"]


async def test_scene_render_error_leaves_no_cached_black_fallback(sample_context):
    """A SceneRenderError refuses assembly. It must not ALSO leave a black+audio stand-in at
    {sid}_final*.mp4: the next `produce --start-from compose` would find that file "cached" and
    assemble a black scene, defeating the loud failure (e.g. a broken toon scene)."""
    from pipeline.errors import SceneRenderError

    sb = Storyboard(scenes=[
        Scene(id="s1", section="hook", narration="test", narration_est_sec=5,
              visual={"type": "text_card", "text": "Hook", "background": "#1a1a2e"}),
    ])
    sb_path = sample_context.work_dir / "storyboard.json"
    sb.save(sb_path)
    sample_context.storyboard_path = sb_path

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
         "start_ms": 0, "duration_ms": 5000},
    ]
    (audio_dir / "seg_000.mp3").write_bytes(b"fake audio")

    def _fake_ffmpeg(cmd):
        out = cmd[-1]
        if isinstance(out, str) and out.endswith(".mp4"):
            Path(out).write_bytes(b"fake")

    err = SceneRenderError(scene="s1", reason="toon: shots[0].set: unknown set 'moon'",
                           suggested_fix="Run `uv run pipeline toon validate <scene>`.")
    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.render_scene", side_effect=err),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_fake_ffmpeg),
        pytest.raises(RuntimeError, match="final assembly refused"),
    ):
        await ComposeStage().run(sample_context)

    scenes_dir = sample_context.work_dir / "compose" / "scenes"
    assert sorted(p.name for p in scenes_dir.glob("s1_final*.mp4")) == []
    assert "unknown set" in sample_context.render_failures["s1"]["reason"]


# --- E5 loud-failure sweep (docs/superpowers/specs/2026-09-29-e5-loud-failure-sweep-design.md) ---


def _write_fake_mp4(cmd):
    """Stand-in for run_ffmpeg: create the output file ffmpeg would have written."""
    out = cmd[-1]
    if isinstance(out, str) and out.endswith(".mp4"):
        Path(out).write_bytes(b"fake")


def _prep_storyboard(ctx, scenes, seg_sec: float = 5.0) -> Path:
    """Save *scenes* as ctx's storyboard with one fake audio segment per scene.

    Returns compose/scenes/ (created), where scene cache files live."""
    sb_path = ctx.work_dir / "storyboard.json"
    Storyboard(scenes=scenes).save(sb_path)
    ctx.storyboard_path = sb_path
    audio_dir = ctx.work_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    ctx.narration_path = audio_dir / "narration.mp3"
    ctx.narration_path.write_bytes(b"fake")
    ctx.subtitle_path = audio_dir / "subs.srt"
    ctx.subtitle_path.write_text("1\n00:00:00,000 --> 00:00:05,000\ntest\n")
    ctx.segment_timings = []
    for i, _scene in enumerate(scenes):
        seg = audio_dir / f"seg_{i:03d}.mp3"
        seg.write_bytes(b"fake audio")
        ctx.segment_timings.append({
            "index": i, "text": "t", "path": str(seg),
            "start_ms": int(i * seg_sec * 1000), "duration_ms": int(seg_sec * 1000),
        })
    scenes_dir = ctx.work_dir / "compose" / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    return scenes_dir


async def test_project_relative_clip_renders_from_project_root(sample_context, tmp_path, monkeypatch):
    """Sprint 9 hub-smoke defect, end to end: `path: source/clip.mp4` validated clean against
    the project dir, then compose looked in cwd, hit "Source video not found" and rendered
    black. Compose (render and duplicate guard) must read the project's file."""
    clip_file = sample_context.work_dir / "source" / "clip.mp4"
    clip_file.parent.mkdir(parents=True)
    clip_file.write_bytes(b"fake clip")
    _prep_storyboard(sample_context, [
        Scene(id="s1", section="hook", narration="t", narration_est_sec=5,
              visual={"type": "clip", "path": "source/clip.mp4", "start_sec": 0, "end_sec": 5}),
    ])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    clip_calls: list[list[str]] = []

    def _clip_ffmpeg(cmd):
        clip_calls.append(list(cmd))
        _write_fake_mp4(cmd)

    thumb_sources: list[Path] = []

    def _no_thumbnail(source, timestamp, out_path):
        thumb_sources.append(source)
        raise RuntimeError("no thumbnails in unit tests")

    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        patch("pipeline.stages.compose._extract_clip_thumbnail", side_effect=_no_thumbnail),
        patch("pipeline.composer.clip._get_source_duration", return_value=10.0),
        patch("pipeline.composer.clip.run_ffmpeg", side_effect=_clip_ffmpeg),
    ):
        await ComposeStage().run(sample_context)

    assert len(clip_calls) == 1, "the clip was never extracted from the project's file"
    cmd = clip_calls[0]
    assert cmd[cmd.index("-i") + 1] == str(clip_file)
    assert thumb_sources == [clip_file]  # the duplicate-frame guard reads the same file


def _text_scene(sid: str = "s1", **kwargs) -> Scene:
    return Scene(id=sid, section="hook", narration="t", narration_est_sec=5,
                 visual={"type": "text_card", "text": "Hook"}, **kwargs)


def _visual_file(scenes_dir: Path, sid: str = "s1") -> Path:
    out = scenes_dir / f"{sid}_visual.mp4"
    out.write_bytes(b"fake visual")
    return out


def _scene_ctx(tmp_path: Path):
    from pipeline.stages.base import PipelineContext

    return PipelineContext(project_id=1, source_url="x", locale="zh-TW",
                           work_dir=tmp_path / "proj", burn_subtitles=False)


async def _render_s1_directly(stage, ctx, scenes_dir, frame_style):
    scene = _text_scene()
    return await stage._render_one_scene(
        i=0, scene=scene,
        scene_dict={"id": "s1", "visual": scene.visual, "overlay": None,
                    "compartment": None, "narration": scene.narration},
        duration=1.0, audio_path=None, width=1280, height=720, scenes_dir=scenes_dir,
        source_video=None, theme_dict={}, frame_style=frame_style, ctx=ctx, audio_segments=[],
    )


async def test_generic_visual_failure_refuses_assembly_without_black(sample_context):
    """P1: any non-SceneRenderError from render_scene used to be swapped for a black screen
    and assembled. It must refuse assembly with the step, the error and an actionable fix."""
    scenes_dir = _prep_storyboard(sample_context, [_text_scene()])
    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.render_scene", side_effect=RuntimeError("provider exploded")),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        pytest.raises(RuntimeError, match="final assembly refused"),
    ):
        await ComposeStage().run(sample_context)

    failure = sample_context.render_failures["s1"]
    assert "visual (text_card) failed: RuntimeError: provider exploded" in failure["reason"]
    pid = sample_context.work_dir.name
    assert f"uv run pipeline validate {pid}" in failure["suggested_fix"]
    assert f"compose rescene --project-id {pid} --scene s1" in failure["suggested_fix"]
    assert sorted(p.name for p in scenes_dir.glob("s1_final*.mp4")) == []
    assert not (scenes_dir / "s1_black.mp4").exists()


async def test_overlay_rule_violation_refuses_assembly(sample_context):
    """P2: check_overlay_allowed raises OverlayCollisionError (a ValueError the validator never
    checks); it used to fall into the outer black fallback and ship."""
    scenes_dir = _prep_storyboard(
        sample_context, [_text_scene(overlay={"type": "text_top", "text": "hi"})],
    )
    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.render_scene", return_value=_visual_file(scenes_dir)),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        pytest.raises(RuntimeError, match="final assembly refused"),
    ):
        await ComposeStage().run(sample_context)

    failure = sample_context.render_failures["s1"]
    assert failure["reason"].startswith("overlay rule failed: OverlayCollisionError:")
    assert "cannot apply 'text_top' overlay to 'text_card' visual" in failure["reason"]
    assert "cannot apply 'text_top'" in failure["suggested_fix"]
    assert "scene.overlay" in failure["suggested_fix"]
    assert sorted(p.name for p in scenes_dir.glob("s1_final*.mp4")) == []


async def test_compartment_failure_refuses_assembly(sample_context):
    """P4: a compartment build failure used to log a warning and ship the scene without it."""
    scenes_dir = _prep_storyboard(
        sample_context, [_text_scene(compartment={"type": "loop", "asset": "missing.png"})],
    )
    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.render_scene", return_value=_visual_file(scenes_dir)),
        patch("pipeline.stages.compose.build_compartment_loop",
              side_effect=RuntimeError("compartment exploded")),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        pytest.raises(RuntimeError, match="final assembly refused"),
    ):
        await ComposeStage().run(sample_context)

    failure = sample_context.render_failures["s1"]
    assert failure["reason"] == "compartment failed: RuntimeError: compartment exploded"
    assert "scene.compartment" in failure["suggested_fix"]
    assert sorted(p.name for p in scenes_dir.glob("s1_final*.mp4")) == []


async def test_render_one_scene_post_visual_failure_raises_and_leaves_no_cache(tmp_path):
    """P2 at the frame step: _render_one_scene used to mux black to the frame-suffixed cache
    paths and return normally."""
    from pipeline.errors import SceneRenderError

    ctx = _scene_ctx(tmp_path)
    scenes_dir = ctx.work_dir / "compose" / "scenes"
    scenes_dir.mkdir(parents=True)
    with (
        patch("pipeline.stages.compose.render_scene", return_value=_visual_file(scenes_dir)),
        patch("pipeline.stages.compose.composite_scene_frame",
              side_effect=RuntimeError("frame exploded")),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        pytest.raises(SceneRenderError) as ei,
    ):
        await _render_s1_directly(ComposeStage(), ctx, scenes_dir, "open_book_page")

    assert ei.value.reason == "frame/mux failed: RuntimeError: frame exploded"
    assert not (scenes_dir / "s1_final_open_book_page.mp4").exists()
    assert not (scenes_dir / "s1_final_no_overlay_open_book_page.mp4").exists()


async def test_escaped_scene_exception_leaves_no_cached_black(sample_context):
    """P3: an exception escaping _render_one_scene used to leave black stand-ins at the
    unsuffixed cache paths, and never cleaned the frame-suffixed ones."""
    scenes_dir = _prep_storyboard(sample_context, [_text_scene()])
    (scenes_dir / "s1_final_open_book_page.mp4").write_bytes(b"stale")  # an earlier framed run

    async def _escaped(self, **kwargs):
        raise RuntimeError("escaped the scene boundary")

    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch.object(ComposeStage, "_render_one_scene", _escaped),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        pytest.raises(RuntimeError, match="final assembly refused"),
    ):
        await ComposeStage().run(sample_context)

    assert sorted(p.name for p in scenes_dir.glob("s1_final*.mp4")) == []
    assert "escaped the scene boundary" in sample_context.render_failures["s1"]["reason"]


async def test_refused_compose_rerun_does_not_cache_hit(sample_context):
    """P1 + cache: the first failing run used to assemble and cache black, so the second run
    never retried the visual."""
    _prep_storyboard(sample_context, [_text_scene()])
    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.render_scene",
              side_effect=RuntimeError("provider exploded")) as mock_render,
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
    ):
        for _run in range(2):
            with pytest.raises(RuntimeError, match="final assembly refused"):
                await ComposeStage().run(sample_context)

    assert mock_render.call_count == 2


# Review Focus (E5 plan): inputs the spec implies that §10's tests do not reach.


async def test_unreadable_cached_scene_is_deleted_and_refused(sample_context):
    """RF1: a cached scene file ffprobe cannot read must not be trusted: refuse with the
    `cached scene` step, delete both cache files, and re-render on the next run."""
    import subprocess

    scenes_dir = _prep_storyboard(sample_context, [_text_scene()])
    (scenes_dir / "s1_final.mp4").write_bytes(b"truncated")
    (scenes_dir / "s1_final_no_overlay.mp4").write_bytes(b"truncated")
    unreadable = subprocess.CalledProcessError(1, ["ffprobe"], stderr="moov atom not found")

    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose._get_duration_sec", side_effect=unreadable),
        patch("pipeline.stages.compose.render_scene") as mock_render,
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        pytest.raises(RuntimeError, match="final assembly refused"),
    ):
        await ComposeStage().run(sample_context)

    failure = sample_context.render_failures["s1"]
    assert failure["reason"].startswith("cached scene failed: CalledProcessError:")
    assert "deleted" in failure["suggested_fix"]
    assert mock_render.call_count == 0
    assert sorted(p.name for p in scenes_dir.glob("s1_final*.mp4")) == []

    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose._get_duration_sec", return_value=5.0),
        patch("pipeline.stages.compose.render_scene",
              return_value=_visual_file(scenes_dir)) as mock_render,
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
    ):
        await ComposeStage().run(sample_context)
    assert mock_render.call_count == 1


async def test_second_mux_failure_leaves_neither_cache_file(tmp_path):
    """RF2: ffmpeg wrote s1_final.mp4, then died half-way through s1_final_no_overlay.mp4.
    Neither file may survive (the cache check needs only both to exist), and the reason
    must carry ffmpeg's own error so the fix is actionable."""
    import subprocess

    from pipeline.errors import SceneRenderError

    ctx = _scene_ctx(tmp_path)
    scenes_dir = ctx.work_dir / "compose" / "scenes"
    scenes_dir.mkdir(parents=True)

    def _dies_on_no_overlay(cmd):
        out = Path(cmd[-1])
        out.write_bytes(b"partial")
        if out.name.startswith("s1_final_no_overlay"):
            raise subprocess.CalledProcessError(1, cmd, stderr="Error writing trailer: No space left on device")

    with (
        patch("pipeline.stages.compose.render_scene", return_value=_visual_file(scenes_dir)),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_dies_on_no_overlay),
        pytest.raises(SceneRenderError) as ei,
    ):
        await _render_s1_directly(ComposeStage(), ctx, scenes_dir, None)

    assert ei.value.reason.startswith("frame/mux failed: CalledProcessError:")
    assert "No space left on device" in ei.value.reason
    assert not (scenes_dir / "s1_final.mp4").exists()
    assert not (scenes_dir / "s1_final_no_overlay.mp4").exists()


async def test_several_failed_scenes_all_reported_and_good_scene_stays_cached(sample_context):
    """RF3: two scenes fail in one run. Both are recorded and named; the good scene s10
    (whose id starts with a failed one's) keeps its cache, so the rescene is cheap."""
    scenes = [_text_scene("s1"), _text_scene("s2"), _text_scene("s10")]
    scenes_dir = _prep_storyboard(sample_context, scenes)
    failing = {"s1", "s2"}
    rendered: list[str] = []

    def _render(scene, duration, aspect_ratio, work_dir, source_video=None, theme=None,
                project_root=None):
        rendered.append(scene["id"])
        if scene["id"] in failing:
            raise RuntimeError(f"provider exploded for {scene['id']}")
        return _visual_file(Path(work_dir), scene["id"])

    with (
        patch("pipeline.stages.compose.check_ffmpeg_available", return_value=True),
        patch("pipeline.stages.compose.render_scene", side_effect=_render),
        patch("pipeline.stages.compose.run_ffmpeg", side_effect=_write_fake_mp4),
        patch("pipeline.stages.compose._get_duration_sec", return_value=5.0),
    ):
        with pytest.raises(RuntimeError, match="final assembly refused") as ei:
            await ComposeStage().run(sample_context)
        assert "s1: " in str(ei.value) and "s2: " in str(ei.value)
        assert set(sample_context.render_failures) == {"s1", "s2"}
        assert (scenes_dir / "s10_final.mp4").exists()
        assert (scenes_dir / "s10_final_no_overlay.mp4").exists()
        assert sorted(p.name for p in scenes_dir.glob("s1_final*.mp4")) == []
        assert sorted(p.name for p in scenes_dir.glob("s2_final*.mp4")) == []

        failing.clear()
        rendered.clear()
        await ComposeStage().run(sample_context)

    assert sorted(rendered) == ["s1", "s2"]  # s10 came from its cache
