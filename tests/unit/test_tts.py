from unittest.mock import patch

from pipeline.stages.tts import (
    TtsStage,
    _build_subtitle_entries,
    _split_text_for_subtitles,
    _visual_width,
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

    stage = TtsStage()

    with (
        patch("pipeline.stages.tts.generate_edge_tts") as mock_tts,
        patch("pipeline.stages.tts._get_audio_duration_ms", return_value=4000),
    ):

        async def fake_tts(text, voice, output_path):
            output_path.write_bytes(b"x")
            return {"duration_ms": 0, "word_timings": []}

        mock_tts.side_effect = fake_tts
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
