from unittest.mock import patch

import pytest

from pipeline.stages.base import PipelineContext
from pipeline.stages.tts import (
    TtsStage,
    _build_subtitle_entries,
    _check_secondary_durations,
    _split_text_for_subtitles,
    _visual_width,
    _wrap_english_two_lines,
    _wrap_subtitle_line,
    extract_narration_segments,
)
from pipeline.storyboard import Scene, Storyboard


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


async def test_tts_segment_timings_include_inter_scene_pauses(sample_context):
    """Compose adds silence gaps between scenes in the final video, but the
    audio file (used for subtitles) does not. The TTS stage must include each
    scene's pause_after_sec in cumulative_ms so the SRT timestamps stay aligned
    with the rendered video. Regression for the s7 subtitle drift seen in
    project 1775401082."""
    from pipeline.voices.base import VoiceProfile

    # Build a storyboard with three scenes, each with a different pause.
    scenes = [
        Scene(
            id=f"s{i + 1}",
            section="hook" if i == 0 else "context",
            narration=f"段落{i + 1}",
            narration_est_sec=5.0,
            pause_after_sec=p,
            visual={"type": "text_card", "text": f"v{i + 1}"},
        )
        for i, p in enumerate([0.5, 0.3, 0.0])
    ]
    storyboard = Storyboard(scenes=scenes)
    storyboard_path = sample_context.work_dir / "storyboard.json"
    storyboard.save(storyboard_path)
    sample_context.storyboard_path = storyboard_path

    script_dir = sample_context.work_dir / "script"
    script_dir.mkdir()
    script_path = script_dir / "script_zh-TW.md"
    script_path.write_text(storyboard.derive_script(), encoding="utf-8")
    sample_context.script_path = script_path

    class _StubEngine:
        @property
        def name(self):
            return "edge"

        def synthesize(self, text, out_path, profile, scene_id=None):
            out_path.write_bytes(b"x")
            return out_path

    stub_pair = (
        _StubEngine(),
        VoiceProfile(id="stub", engine="edge", locale="zh-TW", params={"voice": "x"}),
    )

    stage = TtsStage()

    with (
        patch(
            "pipeline.voices.registry.VoiceRegistry.default_for_locale",
            return_value=stub_pair,
        ),
        patch("pipeline.stages.tts._get_audio_duration_ms", return_value=4000),
    ):
        ctx = await stage.run(sample_context)

    timings = ctx.segment_timings
    assert len(timings) == 3
    # Each segment is 4000ms (mocked); pauses are 500, 300, 0 ms.
    # Segment 0 starts at 0.
    assert timings[0]["start_ms"] == 0
    # Segment 1 starts after segment 0's audio (4000) + s1 pause (500).
    assert timings[1]["start_ms"] == 4500
    # Segment 2 starts after segment 1's audio (+4000) + s2 pause (+300).
    assert timings[2]["start_ms"] == 8800


async def test_tts_generates_audio(sample_context):
    from pipeline.voices.base import VoiceProfile

    script_dir = sample_context.work_dir / "script"
    script_dir.mkdir(parents=True)
    script_path = script_dir / "script_zh-TW.md"
    script_path.write_text(
        "[HOOK]\n一段測試旁白。\n[CONTEXT]\n第二段旁白。\n",
        encoding="utf-8",
    )
    sample_context.script_path = script_path

    class _StubEngine:
        @property
        def name(self):
            return "edge"

        def synthesize(self, text, out_path, profile, scene_id=None):
            out_path.write_bytes(b"fake audio data here")
            return out_path

    stub_pair = (
        _StubEngine(),
        VoiceProfile(id="stub", engine="edge", locale="zh-TW", params={"voice": "x"}),
    )

    stage = TtsStage()
    assert stage.name == "tts"

    with patch(
        "pipeline.voices.registry.VoiceRegistry.default_for_locale",
        return_value=stub_pair,
    ):
        ctx = await stage.run(sample_context)

    assert ctx.narration_path is not None
    assert ctx.narration_path.exists()
    assert ctx.subtitle_path is not None


async def test_tts_stage_uses_registry_for_voice_id(tmp_path):
    """When voice_id is set, TTS stage resolves via VoiceRegistry."""
    work_dir = tmp_path
    storyboard_path = work_dir / "storyboard.json"
    storyboard = Storyboard(
        scenes=[
            Scene(
                id="s1",
                section="hook",
                narration="你好",
                narration_est_sec=2,
                visual={"type": "text_card", "text": "hi"},
                pause_after_sec=0,
            )
        ]
    )
    storyboard.save(storyboard_path)

    script_dir = work_dir / "script"
    script_dir.mkdir()
    script_path = script_dir / "script_zh-TW.md"
    script_path.write_text(storyboard.derive_script(), encoding="utf-8")

    calls = {"synthesize": 0}

    class _StubEngine:
        @property
        def name(self):
            return "edge"

        def synthesize(self, text, out_path, profile, scene_id=None):
            calls["synthesize"] += 1
            out_path.write_bytes(b"FAKE-MP3")
            return out_path

    def fake_resolve(self, voice_id):
        from pipeline.voices.base import VoiceProfile

        return _StubEngine(), VoiceProfile(
            id=voice_id, engine="edge", locale="zh-TW", params={"voice": "x"}
        )

    ctx = PipelineContext(
        project_id=1,
        source_url="https://example/x",
        locale="zh-TW",
        work_dir=work_dir,
        voice_id="zh-TW-default-f",
        storyboard_path=storyboard_path,
        script_path=script_path,
    )

    with (
        patch("pipeline.voices.registry.VoiceRegistry.resolve", fake_resolve),
        patch("pipeline.stages.tts._get_audio_duration_ms", return_value=2000),
    ):
        ctx = await TtsStage().run(ctx)

    assert calls["synthesize"] >= 1
    assert ctx.narration_path is not None
    assert ctx.narration_path.exists()


def test_visual_width():
    """CJK chars count as 2, Latin/digits as 1."""
    assert _visual_width("abc") == 3
    assert _visual_width("你好") == 4
    assert _visual_width("bug") == 3
    assert _visual_width("AI寫code") == 8  # A(1)I(1)寫(2)c(1)o(1)d(1)e(1)
    assert _visual_width("harness") == 7


def test_split_text_short():
    """Short text should not be split."""
    chunks = _split_text_for_subtitles("你好世界", max_width=36)
    assert len(chunks) == 1
    assert chunks[0] == "你好世界"


def test_split_text_by_punctuation():
    """Long text splits at sentence-ending punctuation."""
    text = "這是第一句話。這是第二句話。這是第三句話。"
    chunks = _split_text_for_subtitles(text, max_width=20)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 40  # no single chunk is absurdly long


def test_split_text_long_no_punctuation():
    """Long text without punctuation splits by comma or length."""
    text = "在美國的執法體系中，州際公路由州警負責，而市區道路則是當地警察局的管轄範圍"
    chunks = _split_text_for_subtitles(text, max_width=36)
    assert len(chunks) >= 2


def test_wrap_subtitle_keeps_english_words_whole():
    """English words like 'bug' must not be split across lines."""
    text = "非常具體的bug。"
    result = _wrap_subtitle_line(text, max_width=16)
    # "bug" should appear whole on one line, never split as "bu\ng"
    assert "bu\ng" not in result
    assert "bug" in result


def test_wrap_subtitle_mixed_cjk_english():
    """Mixed CJK + English wraps at word boundaries."""
    text = "使用Playwright瀏覽器自動化"
    result = _wrap_subtitle_line(text, max_width=20)
    # Playwright should not be split
    assert "Playwri" not in result or "Playwright" in result


def test_wrap_subtitle_uses_real_newlines():
    """SRT format requires real newlines, not \\N (ASS format)."""
    text = "這是一段比較長的文字需要換行顯示"
    result = _wrap_subtitle_line(text, max_width=20)
    assert "\\N" not in result  # no literal \N
    assert "\n" in result  # real newline


def test_split_english_word_not_broken():
    """Full pipeline: English words in CJK text stay intact in subtitle chunks."""
    text = "Delete鍵的條件判斷錯誤、路由順序導致422錯誤"
    chunks = _split_text_for_subtitles(text, max_width=28)
    for chunk in chunks:
        # No Latin word should be split across a newline break
        assert "Delet\n" not in chunk
        assert "42\n2" not in chunk


def test_split_bug_and_harness_not_broken():
    """Specific regression: 'bug' and 'harness' must stay whole."""
    text1 = "如果讓AI寫程式碼，結果是一堆bug跟破碎的應用程式，你會怎麼辦？"
    chunks1 = _split_text_for_subtitles(text1, max_width=36)
    all_text = " ".join(chunks1)
    assert "bug" in all_text
    # "bug" must not be split by newline
    for chunk in chunks1:
        for line in chunk.split("\n"):
            if "bu" in line and "bug" not in line:
                raise AssertionError(f"'bug' broken in line: {line!r}")

    text2 = "每一個harness組件都是在假設模型做不到某件事。"
    chunks2 = _split_text_for_subtitles(text2, max_width=36)
    for chunk in chunks2:
        for line in chunk.split("\n"):
            if "harnes" in line and "harness" not in line:
                raise AssertionError(f"'harness' broken in line: {line!r}")


def test_build_subtitle_entries_splits():
    """Subtitle entries should be split from long narration."""
    timings = [
        {
            "index": 0,
            "text": "這是一段很長的旁白文字。它會被分成多個字幕條目。每個條目最多顯示兩行。",
            "path": "/tmp/seg.mp3",
            "start_ms": 0,
            "duration_ms": 10000,
        }
    ]
    entries = _build_subtitle_entries(timings)
    assert len(entries) >= 2
    # Each entry should be reasonably short
    for e in entries:
        assert _visual_width(e.text.replace("\n", "")) <= 80
    # Timings should cover the full range
    assert entries[0].start_ms == 0
    assert abs(entries[-1].end_ms - 10000) <= 1  # rounding tolerance


async def test_tts_passes_scene_id_to_engine(sample_context):
    """TtsStage must pass each scene's id to engine.synthesize so
    PrerecordedEngine can key lookups by scene."""
    from pipeline.voices.base import VoiceProfile

    scenes = [
        Scene(
            id="hook_1",
            section="hook",
            narration="段落一",
            narration_est_sec=2.0,
            visual={"type": "text_card", "text": "v1"},
        ),
        Scene(
            id="ctx_1",
            section="context",
            narration="段落二",
            narration_est_sec=2.0,
            visual={"type": "text_card", "text": "v2"},
        ),
    ]
    storyboard = Storyboard(scenes=scenes)
    storyboard_path = sample_context.work_dir / "storyboard.json"
    storyboard.save(storyboard_path)
    sample_context.storyboard_path = storyboard_path

    script_dir = sample_context.work_dir / "script"
    script_dir.mkdir()
    script_path = script_dir / "script_zh-TW.md"
    script_path.write_text(storyboard.derive_script(), encoding="utf-8")
    sample_context.script_path = script_path

    seen_scene_ids: list[str | None] = []

    class _SceneSpyEngine:
        @property
        def name(self):
            return "edge"

        def synthesize(self, text, out_path, profile, scene_id=None):
            seen_scene_ids.append(scene_id)
            out_path.write_bytes(b"x")
            return out_path

    stub_pair = (
        _SceneSpyEngine(),
        VoiceProfile(id="stub", engine="edge", locale="zh-TW", params={"voice": "x"}),
    )
    stage = TtsStage()

    with (
        patch("pipeline.stages.tts.VoiceRegistry") as mock_reg_cls,
        patch("pipeline.stages.tts._get_audio_duration_ms", return_value=1000),
    ):
        mock_reg_cls.return_value.default_for_locale.return_value = stub_pair
        await stage.run(sample_context)

    assert seen_scene_ids == ["hook_1", "ctx_1"]


# --- English subtitle splitting ---


def test_split_english_long_narration_produces_multiple_chunks():
    """Regression: 189-char English scene produces multiple short chunks, not 1 mega-block."""
    text = (
        "Aisle seven. The cart. The yogurt pouch they wanted and then didn't want. "
        "The scream that seems to come from a much bigger body than theirs. "
        "Everyone is looking. You feel your face go hot."
    )
    chunks = _split_text_for_subtitles(text, max_width=36)
    assert len(chunks) >= 2, f"Expected 2+ chunks for {len(text)}-char English text, got {len(chunks)}"
    for chunk in chunks:
        lines = chunk.split("\n")
        assert len(lines) <= 2, f"Chunk has {len(lines)} lines: {chunk!r}"
        for line in lines:
            assert len(line) <= 45, f"Line too long ({len(line)} chars): {line!r}"


def test_split_english_very_long_sentence():
    """Very long single English sentence (>84 chars) splits into multiple valid chunks."""
    text = (
        "And what the researchers found is that these are the toddlers whose parents most "
        "often reach for a screen when a meltdown starts. Which makes total sense. "
        "It works in the moment. But here is the thing."
    )
    chunks = _split_text_for_subtitles(text, max_width=36)
    assert len(chunks) >= 2
    for chunk in chunks:
        lines = chunk.split("\n")
        assert len(lines) <= 2
        for line in lines:
            assert len(line) <= 45


def test_wrap_english_two_lines_short_text():
    """Short English text stays on one line."""
    result = _wrap_english_two_lines("Short text.", chars_per_line=42)
    assert result == "Short text."
    assert "\n" not in result


def test_wrap_english_two_lines_wraps_at_word_boundary():
    """English text > chars_per_line wraps at a word boundary."""
    text = "The scream that seems to come from a much bigger body than theirs."
    result = _wrap_english_two_lines(text, chars_per_line=42)
    lines = result.split("\n")
    assert len(lines) == 2
    for line in lines:
        assert len(line) <= 42
    # No word should be split across lines
    assert "".join(result.split()) == "".join(text.split())


def test_split_english_preserves_cjk_path():
    """Predominantly CJK text still uses original CJK splitting logic."""
    text = "這是第一句話。這是第二句話。這是第三句話。"
    chunks = _split_text_for_subtitles(text, max_width=20)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 40


# --- MLA (Multi-Language Audio) secondary TTS pass ---


def _make_mla_storyboard(tmp_path, scenes_data):
    """Helper: build and save a storyboard, return (storyboard_path, script_path)."""
    scenes = [
        Scene(
            id=d["id"],
            section=d.get("section", "hook"),
            narration=d["narration"],
            narration_en=d.get("narration_en"),
            narration_est_sec=d.get("narration_est_sec", 3.0),
            visual={"type": "text_card", "text": d.get("visual_text", "v")},
            pause_after_sec=d.get("pause_after_sec", 0.0),
        )
        for d in scenes_data
    ]
    storyboard = Storyboard(scenes=scenes)
    storyboard_path = tmp_path / "storyboard.json"
    storyboard.save(storyboard_path)

    script_dir = tmp_path / "script"
    script_dir.mkdir()
    script_path = script_dir / "script_zh-TW.md"
    script_path.write_text(storyboard.derive_script(), encoding="utf-8")

    return storyboard_path, script_path


async def test_tts_produces_secondary_audio_when_mla(tmp_path):
    """When secondary_locale is set, TTS writes secondary narration and subtitle paths."""
    from pipeline.voices.base import VoiceProfile

    storyboard_path, script_path = _make_mla_storyboard(
        tmp_path,
        [
            {"id": "s1", "narration": "段落一", "narration_en": "Paragraph one."},
            {"id": "s2", "narration": "段落二", "narration_en": "Paragraph two."},
        ],
    )

    ctx = PipelineContext(
        project_id=99,
        source_url="https://example/mla",
        locale="zh-TW",
        work_dir=tmp_path,
        storyboard_path=storyboard_path,
        script_path=script_path,
        secondary_locale="en",
    )

    synthesize_calls: list[tuple[str, str]] = []  # (locale_hint_from_profile, text)

    class _StubEngine:
        def __init__(self, locale: str):
            self._locale = locale

        @property
        def name(self) -> str:
            return "edge"

        def synthesize(self, text, out_path, profile, scene_id=None):
            synthesize_calls.append((self._locale, text))
            out_path.write_bytes(b"FAKE-AUDIO")

    zh_engine = _StubEngine("zh-TW")
    en_engine = _StubEngine("en")

    zh_profile = VoiceProfile(id="zh-stub", engine="edge", locale="zh-TW", params={"voice": "x"})
    en_profile = VoiceProfile(id="en-stub", engine="edge", locale="en", params={"voice": "y"})

    def fake_default_for_locale(self_reg, locale):
        if locale == "zh-TW":
            return zh_engine, zh_profile
        return en_engine, en_profile

    with (
        patch(
            "pipeline.voices.registry.VoiceRegistry.default_for_locale",
            fake_default_for_locale,
        ),
        patch("pipeline.stages.tts._get_audio_duration_ms", return_value=1000),
    ):
        ctx = await TtsStage().run(ctx)

    # Primary outputs
    assert ctx.narration_path is not None and ctx.narration_path.exists()
    assert ctx.subtitle_path is not None and ctx.subtitle_path.exists()

    # Secondary outputs
    assert ctx.secondary_narration_path is not None, "secondary_narration_path should be set"
    assert ctx.secondary_narration_path.exists(), "secondary narration file must exist"
    assert ctx.secondary_subtitle_path is not None, "secondary_subtitle_path should be set"
    assert ctx.secondary_subtitle_path.exists(), "secondary subtitle file must exist"

    # Naming convention: narration_<locale>.mp3 / subtitles_<locale>.srt
    assert ctx.secondary_narration_path.name == "narration_en.mp3"
    assert ctx.secondary_subtitle_path.name == "subtitles_en.srt"

    # Engine was called for both locales
    zh_calls = [c for c in synthesize_calls if c[0] == "zh-TW"]
    en_calls = [c for c in synthesize_calls if c[0] == "en"]
    assert len(zh_calls) == 2, f"expected 2 zh-TW synth calls, got {zh_calls}"
    assert len(en_calls) == 2, f"expected 2 EN synth calls, got {en_calls}"
    assert en_calls[0][1] == "Paragraph one."
    assert en_calls[1][1] == "Paragraph two."


async def test_tts_secondary_warns_for_missing_narration_en(tmp_path):
    """Scenes where narration_en is None should log a warning and be skipped."""
    from pipeline.voices.base import VoiceProfile

    storyboard_path, script_path = _make_mla_storyboard(
        tmp_path,
        [
            {"id": "s1", "narration": "段落一", "narration_en": "Paragraph one."},
            # narration_en intentionally absent
            {"id": "s2", "narration": "段落二", "narration_en": None},
        ],
    )

    ctx = PipelineContext(
        project_id=100,
        source_url="https://example/mla-warn",
        locale="zh-TW",
        work_dir=tmp_path,
        storyboard_path=storyboard_path,
        script_path=script_path,
        secondary_locale="en",
    )

    class _StubEngine:
        @property
        def name(self) -> str:
            return "edge"

        def synthesize(self, text, out_path, profile, scene_id=None):
            out_path.write_bytes(b"AUDIO")

    stub_profile = VoiceProfile(id="s", engine="edge", locale="en", params={"voice": "x"})
    stub_pair = (_StubEngine(), stub_profile)

    with (
        patch(
            "pipeline.voices.registry.VoiceRegistry.default_for_locale",
            return_value=stub_pair,
        ),
        patch("pipeline.stages.tts._get_audio_duration_ms", return_value=1000),
    ):
        # Should NOT raise even though s2 has no narration_en.
        ctx = await TtsStage().run(ctx)

    assert ctx.secondary_narration_path is not None
    assert ctx.secondary_narration_path.exists()
    # Only s1 had content; s2 was skipped — the file still exists (just smaller).
    assert ctx.secondary_narration_path.stat().st_size > 0


def test_check_secondary_durations_warns_per_scene(monkeypatch):
    """Per-scene warning fires when EN duration > primary × 1.15."""
    warnings_emitted: list[str] = []

    def fake_warning(event, **kw):
        warnings_emitted.append(event)

    import pipeline.stages.tts as tts_mod

    monkeypatch.setattr(tts_mod.logger, "warning", fake_warning)

    primary_timings = [
        {"index": 0, "duration_ms": 1000},
        {"index": 1, "duration_ms": 2000},
    ]
    secondary_timings = [
        {"index": 0, "duration_ms": 1200},  # 20% over → warn
        {"index": 1, "duration_ms": 2100},  # 5% over → no warn
    ]

    # Total deviation: primary=3000, secondary=3300 → 300ms → within ±2s → no raise.
    _check_secondary_durations(primary_timings, secondary_timings, "zh-TW", "en")

    # Only scene 0 (20% overage) should have triggered a warning.
    exceed_warns = [w for w in warnings_emitted if "scene_duration_exceed" in w]
    assert len(exceed_warns) == 1, f"Expected 1 per-scene warning, got {exceed_warns}"


def test_check_secondary_durations_hard_fails_on_total_deviation():
    """Hard-fail raised when total EN-vs-primary deviation exceeds ±2s."""
    primary_timings = [{"index": 0, "duration_ms": 10_000}]
    secondary_timings = [{"index": 0, "duration_ms": 13_000}]  # 3s over

    with pytest.raises(ValueError, match="exceeds ±2s limit"):
        _check_secondary_durations(primary_timings, secondary_timings, "zh-TW", "en")


def test_check_secondary_durations_skips_empty_scenes():
    """Skipped scenes (narration_en=None) are excluded from both warn and total checks."""
    primary_timings = [
        {"index": 0, "duration_ms": 1000},
        {"index": 1, "duration_ms": 5000},
    ]
    secondary_timings = [
        {"index": 0, "duration_ms": 1100},
        # s2 was skipped; even though primary=5000 they won't be compared
        {"index": 1, "duration_ms": 0, "skipped": True},
    ]

    # Should not raise: only s1 is compared; deviation = 100ms.
    _check_secondary_durations(primary_timings, secondary_timings, "zh-TW", "en")
