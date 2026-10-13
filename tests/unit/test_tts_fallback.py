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

    async def _run(*, path: str, fail_scenes: set[str], per_scene_first_only: bool = False):
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
        ctx = PipelineContext(
            project_id=1, source_url="x", locale="zh-TW", work_dir=work_dir,
            storyboard_path=storyboard_path,
            voice_id="tim-zhtw" if path == "prerecorded" else None,
        )
        with patch("pipeline.stages.tts._get_audio_duration_ms", return_value=1000):
            ctx = await TtsStage().run(ctx)
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
