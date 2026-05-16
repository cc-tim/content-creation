from pathlib import Path

import pytest

from pipeline.stages.base import PipelineContext
from pipeline.stages.scriptwrite import (
    ScriptwriteStage,
    _english_word_budget_for_zhtw,
    build_scriptwrite_prompt,
)
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


def test_english_word_budget_for_zhtw_counts_cjk_only():
    # 34 CJK chars (comma is excluded) × 0.55 ≈ 19
    text = "在十七世紀時，木製的學步輪首次出現在歐洲家庭中提供給幼童使用以練習走路"
    assert _english_word_budget_for_zhtw(text) == 19
    # Digits + Latin + spaces + punctuation excluded — only 年的 count → max(3, round(2*0.55)) = 3
    assert _english_word_budget_for_zhtw("1901 年的 Sloan") == 3
    # Empty input → floor
    assert _english_word_budget_for_zhtw("") == 3
    # 100 chars → 55 (well above floor)
    assert _english_word_budget_for_zhtw("文" * 100) == 55


def test_build_scriptwrite_prompt_omits_mla_block_when_no_primary_narrations():
    """Primary-locale pass: no MLA discipline block (it's only for alt tracks)."""
    scenes = [
        Scene(id="s1", section="hook", narration="", narration_est_sec=5.0, beat="b"),
    ]
    prompt = build_scriptwrite_prompt(scenes, "zh-TW")
    assert "MLA / LENGTH DISCIPLINE" not in prompt


def test_build_scriptwrite_prompt_adds_mla_block_on_secondary_pass():
    """Secondary-locale pass with primary narrations: MLA block with per-scene budgets."""
    scenes = [
        Scene(id="s1", section="hook", narration="一二三四五六七八九十",
              narration_est_sec=5.0, beat="b1"),
        Scene(id="s2", section="context", narration="",
              narration_est_sec=5.0, beat="b2"),
    ]
    primary_narrations = {"s1": "一二三四五六七八九十", "s2": "甲乙丙丁"}
    prompt = build_scriptwrite_prompt(
        scenes, "en",
        primary_narrations=primary_narrations,
        primary_locale="zh-TW",
    )
    assert "MLA / LENGTH DISCIPLINE" in prompt
    # 10 chars × 0.55 = 6 (rounded from 5.5)
    assert "s1: ~6 words" in prompt
    # 4 chars × 0.55 = 2 → floor of 3
    assert "s2: ~3 words" in prompt
    assert "zh-TW chars × 0.55" in prompt


def test_build_scriptwrite_prompt_skips_mla_block_when_locale_matches_primary():
    """A secondary call where locale happens to equal primary_locale → no block."""
    scenes = [Scene(id="s1", section="hook", narration="一二三", narration_est_sec=5, beat="b")]
    prompt = build_scriptwrite_prompt(
        scenes, "zh-TW",
        primary_narrations={"s1": "一二三"},
        primary_locale="zh-TW",
    )
    assert "MLA / LENGTH DISCIPLINE" not in prompt


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

    def fake_write(scenes, locale, *, primary_narrations=None, primary_locale=None):
        calls.append((locale, primary_narrations is not None))
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
    assert {c[0] for c in calls} == {"zh-TW", "en"}
    # Primary pass: no primary_narrations passed. Secondary pass: primary_narrations
    # included so the MLA length-budget block can be built.
    by_locale = dict(calls)
    assert by_locale["zh-TW"] is False
    assert by_locale["en"] is True
    assert result.script_path is not None and result.script_path.exists()
