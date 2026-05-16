"""Tests for pipeline mla rebalance — word-budget math, offender ID, parsing."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.cli_mla import (
    _build_user_prompt,
    _estimate_projected_drift,
    _Offender,
    _resynth_secondary_selective,
    compute_target_words,
    count_english_words,
    identify_offenders,
    parse_rewrite_response,
)
from pipeline.stages.base import PipelineContext
from pipeline.storyboard import Scene, Storyboard, Theme


def _scene(scene_id: str, narration: str = "zh-TW text", en: str = "") -> Scene:
    return Scene(
        id=scene_id,
        section="context",
        narration=narration,
        narration_est_sec=5.0,
        narration_alt={"en": en} if en else {},
    )


# ── count_english_words ──────────────────────────────────────────────────────


def test_count_english_words_basic():
    assert count_english_words("the quick brown fox") == 4
    assert count_english_words("") == 0


def test_count_english_words_contractions_and_hyphens():
    # Contractions count as one word; hyphenated compounds count as one.
    assert count_english_words("don't stop") == 2
    assert count_english_words("state-of-the-art") == 1
    assert count_english_words("It's a well-known fact.") == 4


def test_count_english_words_punctuation_skipped():
    assert count_english_words("Hello, world!") == 2
    assert count_english_words("One — two; three.") == 3


# ── compute_target_words ─────────────────────────────────────────────────────


def test_compute_target_words_scales_with_observed_rate():
    # Current EN took 13s with 26 words. Primary is 10s. target_ratio 0.95
    # → target_ms = 9.5s → ratio = 9500/13000 ≈ 0.73 → 26 × 0.73 = 19.
    target = compute_target_words(
        current_secondary_words=26,
        current_secondary_ms=13_000,
        primary_ms=10_000,
        target_ratio=0.95,
    )
    assert target == 19


def test_compute_target_words_can_expand_for_undershoot():
    # Current EN took 5s with 8 words. Primary is 10s. target_ratio 0.95
    # → target_ms = 9.5s → ratio = 9500/5000 = 1.9 → 8 × 1.9 = 15.
    target = compute_target_words(
        current_secondary_words=8,
        current_secondary_ms=5_000,
        primary_ms=10_000,
        target_ratio=0.95,
    )
    assert target == 15


def test_compute_target_words_floor():
    # Tiny primary, large undershoot — floor (3) keeps from going to 0.
    target = compute_target_words(
        current_secondary_words=2,
        current_secondary_ms=10_000,
        primary_ms=500,
        target_ratio=0.95,
    )
    assert target == 3  # floor


def test_compute_target_words_handles_zero_inputs():
    assert compute_target_words(
        current_secondary_words=0, current_secondary_ms=1000,
        primary_ms=5000, target_ratio=0.95,
    ) == 3
    assert compute_target_words(
        current_secondary_words=5, current_secondary_ms=0,
        primary_ms=5000, target_ratio=0.95,
    ) == 3


# ── identify_offenders ───────────────────────────────────────────────────────


def test_identify_offenders_flags_overshoot():
    scenes = [_scene("s1", en="Long English text here"), _scene("s2", en="Short EN")]
    primary = [{"duration_ms": 5_000}, {"duration_ms": 5_000}]
    # s1 secondary ≈ 1.5× primary → overshoot. s2 ≈ 1.0× → fine.
    secondary = [
        {"duration_ms": 7_500, "text": "Long English text here"},
        {"duration_ms": 5_100, "text": "Short EN"},
    ]
    offenders, pri_total, sec_total = identify_offenders(
        scenes=scenes,
        primary_timings=primary,
        secondary_timings=secondary,
        sec_locale="en",
        tolerance_ms=2000,
        target_ratio=0.95,
    )
    assert len(offenders) == 1
    assert offenders[0].scene_id == "s1"
    assert offenders[0].direction == "over"
    assert pri_total == 10_000
    assert sec_total == 12_600


def test_identify_offenders_undershoot_only_when_total_drift_exceeds():
    """Undershoot scenes are silent unless total drift breaks tolerance."""
    scenes = [_scene("s1", en="A B C"), _scene("s2", en="D E F")]
    primary = [{"duration_ms": 10_000}, {"duration_ms": 10_000}]
    # Both undershoot at 0.6× but total drift is only 8s — within tolerance (10s).
    secondary = [
        {"duration_ms": 6_000, "text": "A B C"},
        {"duration_ms": 6_000, "text": "D E F"},
    ]
    offenders, _, _ = identify_offenders(
        scenes=scenes,
        primary_timings=primary,
        secondary_timings=secondary,
        sec_locale="en",
        tolerance_ms=10_000,
        target_ratio=0.95,
    )
    # Total drift 8s ≤ tolerance 10s → undershoot ignored, no offenders.
    assert offenders == []

    # Now with tighter tolerance — total drift exceeds it → undershoot promoted.
    offenders_tight, _, _ = identify_offenders(
        scenes=scenes,
        primary_timings=primary,
        secondary_timings=secondary,
        sec_locale="en",
        tolerance_ms=2_000,
        target_ratio=0.95,
    )
    assert {o.scene_id for o in offenders_tight} == {"s1", "s2"}
    assert all(o.direction == "under" for o in offenders_tight)


def test_identify_offenders_skipped_scenes_excluded():
    scenes = [_scene("s1", en="hello"), _scene("s2", en="")]
    primary = [{"duration_ms": 5_000}, {"duration_ms": 5_000}]
    secondary = [
        {"duration_ms": 5_100, "text": "hello"},
        {"duration_ms": 0, "skipped": True, "text": ""},
    ]
    offenders, pri_total, sec_total = identify_offenders(
        scenes=scenes,
        primary_timings=primary,
        secondary_timings=secondary,
        sec_locale="en",
        tolerance_ms=2_000,
        target_ratio=0.95,
    )
    assert offenders == []
    # Skipped scene's primary duration is excluded from totals.
    assert pri_total == 5_000
    assert sec_total == 5_100


def test_identify_offenders_target_words_calibrated_per_scene():
    """target_words should reflect each scene's own observed speech rate."""
    scenes = [_scene("s1", en="x " * 30), _scene("s2", en="y " * 10)]
    primary = [{"duration_ms": 5_000}, {"duration_ms": 5_000}]
    # s1: 30 words in 8000ms → rate fast. Target ms = 5000 × 0.95 = 4750ms.
    #   target_words = 30 × (4750/8000) ≈ 18.
    # s2: 10 words in 8000ms → rate slow. Target ms = 4750ms.
    #   target_words = 10 × (4750/8000) ≈ 6.
    secondary = [
        {"duration_ms": 8_000, "text": "x " * 30},
        {"duration_ms": 8_000, "text": "y " * 10},
    ]
    offenders, _, _ = identify_offenders(
        scenes=scenes,
        primary_timings=primary,
        secondary_timings=secondary,
        sec_locale="en",
        tolerance_ms=2_000,
        target_ratio=0.95,
    )
    assert len(offenders) == 2
    by_id = {o.scene_id: o for o in offenders}
    assert by_id["s1"].target_words == 18
    assert by_id["s2"].target_words == 6


# ── parse_rewrite_response ───────────────────────────────────────────────────


def test_parse_rewrite_response_basic():
    raw = (
        "s7|This is the rewritten English.\n"
        "s38|Another rewrite here."
    )
    out = parse_rewrite_response(raw)
    assert out == {
        "s7": "This is the rewritten English.",
        "s38": "Another rewrite here.",
    }


def test_parse_rewrite_response_tolerates_blank_lines_and_whitespace():
    raw = "\n\n  s1|hello world  \n\ns2|second\n"
    out = parse_rewrite_response(raw)
    assert out == {"s1": "hello world", "s2": "second"}


def test_parse_rewrite_response_ignores_garbage_lines():
    raw = (
        "Here are the rewrites:\n"
        "s1|first text\n"
        "(blank lines below)\n"
        "\n"
        "s2|second text\n"
        "Done!"
    )
    out = parse_rewrite_response(raw)
    assert out == {"s1": "first text", "s2": "second text"}


def test_parse_rewrite_response_preserves_pipes_in_text():
    raw = "s1|Before: a | b | c → done"
    out = parse_rewrite_response(raw)
    assert out["s1"] == "Before: a | b | c → done"


# ── _build_user_prompt ───────────────────────────────────────────────────────


def test_build_user_prompt_includes_per_scene_data_and_direction_hint():
    offenders = [
        _Offender(
            scene_id="s1",
            primary_text="繁體中文文字",
            primary_ms=5_000,
            secondary_text="Long English",
            secondary_ms=8_000,
            secondary_words=2,
            target_words=1,
            direction="over",
        ),
        _Offender(
            scene_id="s2",
            primary_text="另一段",
            primary_ms=5_000,
            secondary_text="short",
            secondary_ms=2_000,
            secondary_words=1,
            target_words=3,
            direction="under",
        ),
    ]
    prompt = _build_user_prompt(offenders, "zh-TW")
    assert "Primary locale: zh-TW" in prompt
    assert "[s1]" in prompt and "[s2]" in prompt
    assert "繁體中文文字" in prompt
    assert "tighten" in prompt  # over hint
    assert "expand" in prompt  # under hint
    assert "target words: 1" in prompt
    assert "target words: 3" in prompt


# ── _estimate_projected_drift ────────────────────────────────────────────────


def test_estimate_projected_drift_linear_extrapolation():
    offenders = [
        _Offender(
            scene_id="s1",
            primary_text="x", primary_ms=5_000,
            secondary_text="ten words " * 5, secondary_ms=10_000,
            secondary_words=10, target_words=5,
            direction="over",
        ),
    ]
    rewrites = {"s1": "five word rewrite goes here"}  # 5 words
    # Scale = 5/10 = 0.5 → new sec_ms for s1 = 10_000 × 0.5 = 5_000 (delta -5_000)
    # Total secondary was 10_000 → new total = 5_000. Primary was 5_000.
    # Projected drift = |5_000 - 5_000| = 0.
    drift, rewritten = _estimate_projected_drift(
        offenders, rewrites, total_primary_ms=5_000, total_secondary_ms=10_000
    )
    assert drift == 0
    assert rewritten == 1


def test_estimate_projected_drift_skips_missing_rewrites():
    offenders = [
        _Offender(
            scene_id="s1", primary_text="x", primary_ms=5_000,
            secondary_text="text", secondary_ms=8_000,
            secondary_words=5, target_words=3,
            direction="over",
        ),
    ]
    # No rewrite for s1 → drift stays the same.
    drift, rewritten = _estimate_projected_drift(
        offenders, {}, total_primary_ms=5_000, total_secondary_ms=8_000
    )
    assert drift == 3_000
    assert rewritten == 0


# ── _resynth_secondary_selective — convergence-critical behavior ─────────────


class _FakeEngine:
    """Records calls instead of doing real synthesis. Writes a marker file."""

    def __init__(self):
        self.calls: list[str] = []  # scene_ids

    def synthesize(self, text: str, out_path: Path, profile, scene_id: str = None):
        self.calls.append(scene_id or "")
        out_path.write_bytes(b"NEW-SYNTH-" + text.encode())


def test_resynth_selective_only_synthesizes_rewritten_scenes(tmp_path, monkeypatch):
    """The whole point of selective resynth: unchanged scenes' audio is untouched
    so their durations stay bit-identical across rebalance iterations.
    """
    # Build a 3-scene storyboard and pre-populate 3 segment_en files with
    # distinct byte content + a fake stable duration.
    sb = Storyboard(
        scenes=[
            Scene(id="s1", section="hook", narration="主1",
                  narration_est_sec=5, narration_alt={"en": "EN one"}),
            Scene(id="s2", section="context", narration="主2",
                  narration_est_sec=5, narration_alt={"en": "EN two"}),
            Scene(id="s3", section="climax", narration="主3",
                  narration_est_sec=5, narration_alt={"en": "EN three"}),
        ],
        theme=Theme(),
    )
    work_dir = tmp_path / "proj"
    audio_dir = work_dir / "audio"
    audio_dir.mkdir(parents=True)
    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)

    # Pre-populate "existing" segment files with marker bytes.
    s1_path = audio_dir / "segment_en_000.mp3"
    s2_path = audio_dir / "segment_en_001.mp3"
    s3_path = audio_dir / "segment_en_002.mp3"
    s1_path.write_bytes(b"OLD-S1-CONTENT")
    s2_path.write_bytes(b"OLD-S2-CONTENT")
    s3_path.write_bytes(b"OLD-S3-CONTENT")

    ctx = PipelineContext(
        project_id=1, source_url="x", locale="zh-TW", work_dir=work_dir,
        secondary_locale="en", storyboard_path=sb_path,
    )

    fake_engine = _FakeEngine()
    fake_profile = MagicMock()

    # Patch the engine resolver (uses VoiceRegistry inside _resynth_secondary_selective).
    fake_registry = MagicMock()
    fake_registry.default_for_locale.return_value = (fake_engine, fake_profile)
    fake_registry.resolve.return_value = (fake_engine, fake_profile)

    # Stable per-file durations so we can assert without ffprobe.
    def fake_duration(path: Path) -> int:
        return {"OLD-S1-CONTENT": 5000, "OLD-S3-CONTENT": 7000}.get(
            path.read_bytes().decode(errors="ignore"),
            1234,  # any "fresh-synth" duration for the rewritten scene
        )

    with patch("pipeline.cli_mla.VoiceRegistry", return_value=fake_registry), \
         patch("pipeline.cli_mla._get_audio_duration_ms", side_effect=fake_duration), \
         patch("pipeline.cli_mla._concatenate_audio"), \
         patch("pipeline.cli_mla.write_srt"):
        timings = asyncio.run(_resynth_secondary_selective(
            ctx=ctx,
            storyboard=sb,
            audio_dir=audio_dir,
            sec_locale="en",
            rewritten_scene_ids={"s2"},  # only s2 changed
        ))

    # The fake engine should have been called for s2 only.
    assert fake_engine.calls == ["s2"]
    # s1 and s3 audio files must be untouched (same bytes).
    assert s1_path.read_bytes() == b"OLD-S1-CONTENT"
    assert s3_path.read_bytes() == b"OLD-S3-CONTENT"
    # s2 was overwritten by the fake engine.
    assert s2_path.read_bytes().startswith(b"NEW-SYNTH-")

    # Timing durations match the per-file map (s1 and s3 keep their old durations).
    assert timings[0]["duration_ms"] == 5000
    assert timings[2]["duration_ms"] == 7000
    # s2 picks up the "fresh synth" sentinel duration.
    assert timings[1]["duration_ms"] == 1234


def test_resynth_selective_synthesizes_missing_files(tmp_path):
    """If a segment_en file is missing (e.g. new scene added), synthesize it."""
    sb = Storyboard(
        scenes=[
            Scene(id="s1", section="hook", narration="主1",
                  narration_est_sec=5, narration_alt={"en": "EN one"}),
        ],
        theme=Theme(),
    )
    work_dir = tmp_path / "proj"
    audio_dir = work_dir / "audio"
    audio_dir.mkdir(parents=True)
    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)

    ctx = PipelineContext(
        project_id=1, source_url="x", locale="zh-TW", work_dir=work_dir,
        secondary_locale="en", storyboard_path=sb_path,
    )

    fake_engine = _FakeEngine()
    fake_registry = MagicMock()
    fake_registry.default_for_locale.return_value = (fake_engine, MagicMock())

    with patch("pipeline.cli_mla.VoiceRegistry", return_value=fake_registry), \
         patch("pipeline.cli_mla._get_audio_duration_ms", return_value=4000), \
         patch("pipeline.cli_mla._concatenate_audio"), \
         patch("pipeline.cli_mla.write_srt"):
        asyncio.run(_resynth_secondary_selective(
            ctx=ctx,
            storyboard=sb,
            audio_dir=audio_dir,
            sec_locale="en",
            rewritten_scene_ids=set(),  # nothing rewritten — but file missing
        ))

    # File was missing → fallback synth must have happened.
    assert fake_engine.calls == ["s1"]
    assert (audio_dir / "segment_en_000.mp3").exists()


def test_resynth_selective_handles_empty_narration_alt(tmp_path):
    """Scenes with no narration_alt[en] are skipped (no synth, no concat entry)."""
    sb = Storyboard(
        scenes=[
            Scene(id="s1", section="hook", narration="主1",
                  narration_est_sec=5, narration_alt={"en": "hello"}),
            Scene(id="s2", section="context", narration="主2",
                  narration_est_sec=5, narration_alt={}),
        ],
        theme=Theme(),
    )
    work_dir = tmp_path / "proj"
    audio_dir = work_dir / "audio"
    audio_dir.mkdir(parents=True)
    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)
    (audio_dir / "segment_en_000.mp3").write_bytes(b"existing")

    ctx = PipelineContext(
        project_id=1, source_url="x", locale="zh-TW", work_dir=work_dir,
        secondary_locale="en", storyboard_path=sb_path,
    )

    fake_engine = _FakeEngine()
    fake_registry = MagicMock()
    fake_registry.default_for_locale.return_value = (fake_engine, MagicMock())

    with patch("pipeline.cli_mla.VoiceRegistry", return_value=fake_registry), \
         patch("pipeline.cli_mla._get_audio_duration_ms", return_value=3000), \
         patch("pipeline.cli_mla._concatenate_audio"), \
         patch("pipeline.cli_mla.write_srt"):
        timings = asyncio.run(_resynth_secondary_selective(
            ctx=ctx,
            storyboard=sb,
            audio_dir=audio_dir,
            sec_locale="en",
            rewritten_scene_ids=set(),
        ))

    assert fake_engine.calls == []  # no synth at all
    assert timings[0]["duration_ms"] == 3000
    assert timings[1].get("skipped") is True
    assert timings[1]["duration_ms"] == 0


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
