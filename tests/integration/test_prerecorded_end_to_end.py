"""Smoke test: TtsStage with a prerecorded voice actually transcodes a real
WAV file and hits the EdgeEngine fallback path on a missing scene.

Marked `integration` because it runs real ffmpeg and real edge-tts.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_prerecorded_mixes_with_edge_fallback(tmp_path, monkeypatch):
    from pipeline.stages.base import PipelineContext
    from pipeline.stages.tts import TtsStage
    from pipeline.storyboard import Scene, Storyboard

    voices_dir = tmp_path / "voices"
    rec_dir = voices_dir / "prerecorded" / "tim-zhtw"
    rec_dir.mkdir(parents=True)

    fixture = Path(__file__).parent.parent / "fixtures" / "short_narration.wav"
    shutil.copyfile(fixture, rec_dir / "hook_1.wav")

    (voices_dir / "registry.json").write_text(
        json.dumps(
            {
                "voices": [
                    {
                        "id": "tim-zhtw",
                        "engine": "prerecorded",
                        "locale": "zh-TW",
                        "params": {
                            "recording_dir": str(rec_dir),
                            "fallback_voice_id": "zh-TW-default-f",
                        },
                    },
                    {
                        "id": "zh-TW-default-f",
                        "engine": "edge",
                        "locale": "zh-TW",
                        "params": {"voice": "zh-TW-HsiaoChenNeural"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    sb = Storyboard(
        scenes=[
            Scene(
                id="hook_1",
                section="hook",
                narration="你好，這是第一段。",
                narration_est_sec=1.0,
                visual={"type": "text_card", "text": "hi"},
            ),
            Scene(
                id="ctx_1",
                section="context",
                narration="這是第二段，應該用Edge合成。",
                narration_est_sec=1.5,
                visual={"type": "text_card", "text": "hi"},
            ),
        ]
    )
    sb.save(work_dir / "storyboard.json")
    script_dir = work_dir / "script"
    script_dir.mkdir()
    (script_dir / "script_zh-TW.md").write_text(sb.derive_script(), encoding="utf-8")

    ctx = PipelineContext(
        project_id=1,
        source_url="x",
        locale="zh-TW",
        work_dir=work_dir,
        storyboard_path=work_dir / "storyboard.json",
        script_path=script_dir / "script_zh-TW.md",
        voice_id="tim-zhtw",
    )

    # TtsStage constructs PipelineConfig() which defaults VOICES_DIR to
    # Path("voices") relative to cwd. chdir so it resolves to our tmp voices dir.
    monkeypatch.chdir(tmp_path)
    asyncio.run(TtsStage().run(ctx))

    assert (work_dir / "audio" / "segment_000.mp3").exists()
    assert (work_dir / "audio" / "segment_001.mp3").exists()
    assert (rec_dir / "hook_1.txt").read_text(encoding="utf-8").strip() == "你好，這是第一段。"
