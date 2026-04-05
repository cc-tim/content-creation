from unittest.mock import patch

from pipeline.stages.tts import (
    TtsStage,
    _build_subtitle_entries,
    _split_text_for_subtitles,
    extract_narration_segments,
)


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


def test_split_text_short():
    """Short text should not be split."""
    chunks = _split_text_for_subtitles("你好世界", max_chars=18)
    assert len(chunks) == 1
    assert chunks[0] == "你好世界"


def test_split_text_by_punctuation():
    """Long text splits at sentence-ending punctuation."""
    text = "這是第一句話。這是第二句話。這是第三句話。"
    chunks = _split_text_for_subtitles(text, max_chars=10)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 40  # no single chunk is absurdly long


def test_split_text_long_no_punctuation():
    """Long text without punctuation splits by comma or length."""
    text = "在美國的執法體系中，州際公路由州警負責，而市區道路則是當地警察局的管轄範圍"
    chunks = _split_text_for_subtitles(text, max_chars=18)
    assert len(chunks) >= 2


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
        assert len(e.text) <= 40
    # Timings should cover the full range
    assert entries[0].start_ms == 0
    assert abs(entries[-1].end_ms - 10000) <= 1  # rounding tolerance
