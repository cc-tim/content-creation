"""TtsStage-level fallback behaviour (review finding 1): one run never mixes voices."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from pipeline.stages.base import PipelineContext
from pipeline.stages.tts import TtsStage
from pipeline.storyboard import NarrationSource, Scene, Storyboard
from pipeline.voices.base import VoiceEngineUnavailable
from pipeline.voices.edge_engine import EdgeEngine
from pipeline.voices.kokoro_engine import KokoroEngine

_VOICES = [
    {"id": "zh-TW-default-f", "engine": "edge", "locale": "zh-TW",
     "params": {"voice": "zh-TW-HsiaoChenNeural", "fallback_voice_id": "zh-TW-kokoro-f"}},
    {"id": "zh-TW-kokoro-f", "engine": "kokoro", "locale": "zh-TW", "params": {"sid": 3}},
    {"id": "tim-zhtw", "engine": "prerecorded", "locale": "zh-TW",
     "params": {"recording_dir": "__REC__", "fallback_voice_id": "zh-TW-default-f"}},
]


@pytest.fixture
def run_tts(tmp_path, monkeypatch):
    """Run TtsStage over 3 scenes; edge is unavailable on `fail_scenes`. Returns per-scene voices."""
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    registry = json.dumps({"voices": _VOICES}).replace("__REC__", str(tmp_path / "rec"))
    (voices_dir / "registry.json").write_text(registry, encoding="utf-8")
    monkeypatch.setenv("PIPELINE_VOICES_DIR", str(voices_dir))

    async def _run(
        *, path: str, fail_scenes: set[str], per_scene_first_only: bool = False,
        auto_fallback: bool | None = None,
    ):
        def edge(self, text, out_path, profile, scene_id=None):
            if scene_id in fail_scenes:
                raise VoiceEngineUnavailable("edge refused synthesis (HTTP 403)")
            out_path.write_text("edge")
            return out_path

        def kokoro(self, text, out_path, profile, scene_id=None):
            out_path.write_text("kokoro")
            return out_path

        monkeypatch.setattr(EdgeEngine, "synthesize", edge)
        monkeypatch.setattr(KokoroEngine, "synthesize", kokoro)

        source = NarrationSource(engine="edge", voice="zh-TW-default-f")
        scenes = [
            Scene(
                id=f"s{i}", section="content", narration=f"第{i}段。", narration_est_sec=1.0,
                visual={"type": "text_card", "text": "x"}, pause_after_sec=0,
                narration_source=(
                    source if path == "per-scene" and (i == 1 or not per_scene_first_only)
                    else None
                ),
            )
            for i in (1, 2, 3)
        ]
        work_dir = tmp_path / "project"
        work_dir.mkdir(exist_ok=True)
        storyboard_path = work_dir / "storyboard.json"
        Storyboard(scenes=scenes).save(storyboard_path)
        ctx_path = work_dir / "context.json"
        ctx = (
            PipelineContext.load(ctx_path)
            if ctx_path.exists()
            else PipelineContext(project_id=1, source_url="x", locale="zh-TW", work_dir=work_dir)
        )
        ctx.storyboard_path = storyboard_path
        ctx.voice_id = "tim-zhtw" if path == "prerecorded" else None
        with patch("pipeline.stages.tts._get_audio_duration_ms", return_value=1000):
            ctx = await TtsStage(auto_fallback=auto_fallback).run(ctx)
        ctx.save()
        audio = work_dir / "audio"
        return ctx, [(audio / f"segment_{i:03d}.mp3").read_text() for i in range(3)]

    return _run


_PATHS = ["default", "prerecorded", "per-scene"]


@pytest.mark.parametrize("path", _PATHS)
async def test_tts_scene_one_outage_narrates_the_whole_pass_with_the_fallback(run_tts, path):
    _ctx, voiced = await run_tts(path=path, fail_scenes={"s1"})
    assert voiced == ["kokoro", "kokoro", "kokoro"]


@pytest.mark.parametrize("path", _PATHS)
async def test_tts_later_outage_raises_instead_of_mixing(run_tts, path):
    with pytest.raises(RuntimeError, match="mix"):
        await run_tts(path=path, fail_scenes={"s2"})


async def test_tts_per_scene_success_then_default_outage_raises(run_tts):
    """Cross-engine: s1 voiced by a per-scene edge engine, s2 by the default engine."""
    with pytest.raises(RuntimeError, match="mix"):
        await run_tts(path="per-scene", fail_scenes={"s2"}, per_scene_first_only=True)


# ---- durable + visible (review finding 4) ----


async def test_tts_records_the_fallback_voice_on_the_context(run_tts, tmp_path):
    ctx, _ = await run_tts(path="default", fail_scenes={"s1"})

    assert ctx.tts_fallback_voices == {"zh-TW-default-f": "zh-TW-kokoro-f"}
    ctx.save()
    reloaded = PipelineContext.load(ctx.work_dir / "context.json")
    assert reloaded.tts_fallback_voices == {"zh-TW-default-f": "zh-TW-kokoro-f"}


async def test_tts_clean_run_clears_a_stale_fallback_record(run_tts, tmp_path):
    ctx, _ = await run_tts(path="default", fail_scenes={"s1"})
    assert ctx.tts_fallback_voices

    ctx, voiced = await run_tts(path="default", fail_scenes=set())

    assert voiced == ["edge", "edge", "edge"]
    assert ctx.tts_fallback_voices == {}


async def test_tts_complete_summary_names_the_fallback_voice(run_tts):
    from structlog.testing import capture_logs

    with capture_logs() as logs:
        await run_tts(path="default", fail_scenes={"s1"})

    complete = [e for e in logs if e["event"] == "tts.complete"]
    assert len(complete) == 1
    assert complete[0]["log_level"] == "warning"
    assert complete[0]["fallback_voices"] == {"zh-TW-default-f": "zh-TW-kokoro-f"}


async def test_tts_stage_without_auto_fallback_fails_on_an_outage(run_tts):
    """compose voice-variant runs TtsStage(auto_fallback=False): hear that voice or fail."""
    with pytest.raises(VoiceEngineUnavailable):
        await run_tts(path="default", fail_scenes={"s1"}, auto_fallback=False)


def test_voice_variant_runs_tts_without_auto_fallback(tmp_path):
    from unittest.mock import MagicMock

    from typer.testing import CliRunner

    from pipeline.cli_compose import compose_app
    from tests.unit.test_voice_variant import _make_parent_project

    _make_parent_project(tmp_path)
    orchestrator = MagicMock()
    with (
        patch("pipeline.cli_compose._resolve_projects_dir", return_value=tmp_path / "projects"),
        patch("pipeline.orchestrator.Orchestrator", orchestrator),
        patch("pipeline.cli_compose.asyncio.run"),
    ):
        result = CliRunner().invoke(compose_app, [
            "voice-variant", "--from-project", "1776997800", "--voice", "zh-TW-default-f",
        ])

    assert result.exit_code == 0, result.output
    stages = orchestrator.call_args.args[0]
    tts_stage = next(s for s in stages if isinstance(s, TtsStage))
    assert tts_stage.auto_fallback is False


# ---- MLA: a failed run must not leave unmarked fallback audio on disk ----

_JENNY = {"id": "en-US-jenny", "engine": "edge", "locale": "en",
          "params": {"voice": "en-US-JennyNeural"}}


@pytest.fixture
def mla_project(tmp_path, monkeypatch):
    """A zh-TW + en MLA project whose audio/ already holds an earlier edge narration."""
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    voices = [*_VOICES, _JENNY]
    registry = json.dumps({"voices": voices}).replace("__REC__", str(tmp_path / "rec"))
    (voices_dir / "registry.json").write_text(registry, encoding="utf-8")
    monkeypatch.setenv("PIPELINE_VOICES_DIR", str(voices_dir))

    work_dir = tmp_path / "project"
    audio = work_dir / "audio"
    audio.mkdir(parents=True)
    for name in ("narration_zh-TW.mp3", "segment_000.mp3", "narration_en.mp3"):
        (audio / name).write_text("old-edge")
    scenes = [
        Scene(id=f"s{i}", section="content", narration=f"第{i}段。", narration_est_sec=1.0,
              narration_alt={"en": f"Part {i}."}, visual={"type": "text_card", "text": "x"},
              pause_after_sec=0)
        for i in (1, 2)
    ]
    storyboard_path = work_dir / "storyboard.json"
    Storyboard(scenes=scenes).save(storyboard_path)
    ctx = PipelineContext(
        project_id=1, source_url="x", locale="zh-TW", work_dir=work_dir,
        storyboard_path=storyboard_path, mla=True, secondary_locale="en",
    )
    return ctx


def _engines_down_for(monkeypatch, down_voices: set[str] | None) -> None:
    """Edge is unavailable for down_voices (None: every voice). Kokoro always works."""

    def edge(self, text, out_path, profile, scene_id=None):
        if down_voices is None or profile.params["voice"] in down_voices:
            raise VoiceEngineUnavailable("edge refused synthesis (HTTP 403)")
        out_path.write_text("edge")
        return out_path

    def kokoro(self, text, out_path, profile, scene_id=None):
        out_path.write_text("kokoro")
        return out_path

    monkeypatch.setattr(EdgeEngine, "synthesize", edge)
    monkeypatch.setattr(KokoroEngine, "synthesize", kokoro)


async def test_mla_secondary_outage_after_a_primary_fallback_leaves_audio_untouched(
    mla_project, monkeypatch
):
    """zh falls back to Kokoro, en (no fallback) then fails: nothing on disk may change."""
    _engines_down_for(monkeypatch, None)
    audio = mla_project.work_dir / "audio"

    with (
        patch("pipeline.stages.tts._get_audio_duration_ms", return_value=1000),
        pytest.raises(VoiceEngineUnavailable),
    ):
        await TtsStage().run(mla_project)

    assert (audio / "narration_zh-TW.mp3").read_text() == "old-edge"
    assert (audio / "segment_000.mp3").read_text() == "old-edge"
    assert (audio / "narration_en.mp3").read_text() == "old-edge"
    assert sorted(p.name for p in audio.iterdir()) == [
        "narration_en.mp3", "narration_zh-TW.mp3", "segment_000.mp3",
    ]
