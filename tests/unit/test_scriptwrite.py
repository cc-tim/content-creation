import json
from pathlib import Path

import pytest

from pipeline.stages.base import PipelineContext
from pipeline.stages.scriptwrite import ScriptwriteStage, build_scriptwrite_prompt
from pipeline.storyboard import Scene, Storyboard


def test_build_scriptwrite_prompt_includes_beats_and_locale():
    scenes = [
        Scene(id="s1", section="hook", narration="", narration_est_sec=8.0,
              beat="establishes the 600-year design stasis"),
    ]
    prompt = build_scriptwrite_prompt(scenes, "en")
    assert "establishes the 600-year design stasis" in prompt
    assert "8" in prompt  # duration budget surfaced
    assert "en" in prompt


@pytest.mark.asyncio
async def test_scriptwrite_fills_primary_and_secondary(tmp_path: Path, monkeypatch):
    from pipeline.stages import scriptwrite as sw_mod

    sb = Storyboard(
        primary_locale="zh-TW",
        scenes=[
            Scene(id="s1", section="hook", narration="", narration_est_sec=8.0, beat="b1"),
            Scene(id="s2", section="context", narration="", narration_est_sec=8.0, beat="b2"),
        ],
    )
    sb_path = tmp_path / "storyboard_zh-TW.json"
    sb.save(sb_path)

    calls = []

    def fake_write(scenes, locale):
        calls.append(locale)
        return {"s1": f"{locale}-one", "s2": f"{locale}-two"}

    monkeypatch.setattr(sw_mod, "_write_narration_for_locale", fake_write)

    ctx = PipelineContext(
        project_id=1,
        source_url="https://example.com",
        locale="zh-TW",
        work_dir=tmp_path,
    )
    ctx.secondary_locale = "en"
    ctx.storyboard_path = sb_path

    result = await ScriptwriteStage().run(ctx)

    saved = Storyboard.load(sb_path)
    assert saved.scenes[0].narration == "zh-TW-one"
    assert saved.scenes[0].narration_alt["en"] == "en-one"
    assert saved.scenes[1].narration == "zh-TW-two"
    assert saved.scenes[1].narration_alt["en"] == "en-two"
    assert set(calls) == {"zh-TW", "en"}
    assert result.script_path is not None and result.script_path.exists()
