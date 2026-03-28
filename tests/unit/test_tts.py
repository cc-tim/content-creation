from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline.stages.tts import TtsStage, extract_narration_segments
from pipeline.stages.base import PipelineContext


def test_extract_narration_segments():
    script = (
        "[HOOK]\n"
        "[CLIP:00:05-00:20]\n"
        "這是第一段旁白文字。\n"
        "\n"
        "[OVERLAY:map:Texas]\n"
        "這是第二段旁白文字。\n"
        "[PAUSE:2s]\n"
        "這是第三段。\n"
    )
    segments = extract_narration_segments(script)
    assert len(segments) == 3
    assert segments[0] == "這是第一段旁白文字。"
    assert segments[1] == "這是第二段旁白文字。"
    assert segments[2] == "這是第三段。"


async def test_tts_generates_audio(sample_context):
    script_dir = sample_context.work_dir / "script"
    script_dir.mkdir(parents=True)
    script_path = script_dir / "script_zh-TW.md"
    script_path.write_text(
        "[HOOK]\n一段測試旁白。\n[CONTEXT]\n第二段旁白。\n",
        encoding="utf-8",
    )
    sample_context.script_path = script_path

    stage = TtsStage()
    assert stage.name == "tts"

    with patch("pipeline.stages.tts.generate_edge_tts") as mock_tts:
        async def fake_tts(text, voice, output_path):
            output_path.write_bytes(b"fake audio data here")
            return {"duration_ms": 3000, "word_timings": []}

        mock_tts.side_effect = fake_tts

        ctx = await stage.run(sample_context)

    assert ctx.narration_path is not None
    assert ctx.narration_path.exists()
    assert ctx.subtitle_path is not None
