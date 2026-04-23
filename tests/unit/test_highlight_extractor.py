# tests/unit/test_highlight_extractor.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.utils.highlight_extractor import (
    CaptionProvider,
    NullCaptionProvider,
    _audio_rms_per_window,
    _count_scene_changes_per_window,
    _merge_scores,
    _score_keywords,
    _select_candidates,
    extract_highlights,
)


def test_null_caption_provider_returns_none():
    provider = NullCaptionProvider()
    assert provider.caption(Path("any.jpg")) is None


def test_caption_provider_protocol():
    """NullCaptionProvider satisfies the CaptionProvider protocol."""
    assert isinstance(NullCaptionProvider(), CaptionProvider)


def test_count_scene_changes_per_window_empty():
    with patch(
        "pipeline.utils.highlight_extractor.detect_scene_changes", return_value=[]
    ), patch("pipeline.utils.highlight_extractor.get_duration", return_value=30.0):
        result = _count_scene_changes_per_window(Path("video.mp4"), window_sec=5)
    assert len(result) == 7  # 30s / 5s + 1
    assert all(score == 0.0 for _, score in result)


def test_count_scene_changes_per_window_normalizes():
    # Two changes in window 0, one in window 1
    with patch(
        "pipeline.utils.highlight_extractor.detect_scene_changes",
        return_value=[1.0, 3.0, 6.0],
    ), patch("pipeline.utils.highlight_extractor.get_duration", return_value=15.0):
        result = _count_scene_changes_per_window(Path("video.mp4"), window_sec=5)
    ts_to_score = {ts: score for ts, score in result}
    assert ts_to_score[0.0] == pytest.approx(1.0)  # 2 changes → max → 1.0
    assert ts_to_score[5.0] == pytest.approx(0.5)  # 1 change → 0.5


def test_score_keywords_no_transcript():
    result = _score_keywords(None, duration_sec=30.0, window_sec=5)
    assert result == []


def test_score_keywords_counts_action_words(tmp_path):
    transcript = [
        {"text": "the officer shot the weapon", "start": 2.0, "duration": 3.0},
        {"text": "they were fleeing", "start": 12.0, "duration": 2.0},
    ]
    fpath = tmp_path / "transcript.json"
    fpath.write_text(json.dumps(transcript), encoding="utf-8")
    result = _score_keywords(fpath, duration_sec=20.0, window_sec=5)
    ts_to_score = {ts: score for ts, score in result}
    assert ts_to_score[0.0] == pytest.approx(1.0)   # "shot" + "weapon" = 2 hits → max
    assert ts_to_score[10.0] == pytest.approx(0.5)  # "fleeing" = 1 hit


def test_audio_rms_returns_empty_on_ffprobe_failure():
    mock = MagicMock(returncode=1, stdout="")
    with patch("subprocess.run", return_value=mock):
        result = _audio_rms_per_window(Path("video.mp4"), window_sec=5)
    assert result == []


def test_audio_rms_per_window_normalizes_db():
    """Happy path: ffprobe returns valid RMS, values are normalized correctly."""
    # -30dB → (−30+60)/60 = 0.5, averaged over 5-second window (5 frames)
    frames = [{"tags": {"lavfi.astats.Overall.RMS_level": "-30.0"}} for _ in range(5)]
    fake_output = json.dumps({"frames": frames})
    mock = MagicMock(returncode=0, stdout=fake_output)
    with patch("subprocess.run", return_value=mock):
        result = _audio_rms_per_window(Path("video.mp4"), window_sec=5)
    assert len(result) == 1
    ts, score = result[0]
    assert ts == pytest.approx(0.0)
    assert score == pytest.approx(0.5)


# Task 2: Candidate selection + extract_highlights() API

def test_merge_scores_combines_signals():
    fd = [(0.0, 0.8), (5.0, 0.2)]
    ar = [(0.0, 0.6), (5.0, 0.4)]
    kw = [(0.0, 1.0), (5.0, 0.0)]
    result = _merge_scores(fd, ar, kw, duration_sec=10.0, window_sec=5)
    assert len(result) == 3  # 0s, 5s, 10s
    # Window 0: 0.4*0.8 + 0.3*0.6 + 0.3*1.0 = 0.32 + 0.18 + 0.30 = 0.80
    assert result[0]["combined_score"] == pytest.approx(0.80, abs=0.01)
    assert result[0]["timestamp_sec"] == 0.0


def test_select_candidates_enforces_spacing():
    scored = [
        {"timestamp_sec": 0.0, "combined_score": 0.9, "frame_diff": 0.9, "audio_rms": 0.9, "keyword_score": 0.9},
        {"timestamp_sec": 5.0, "combined_score": 0.85, "frame_diff": 0.8, "audio_rms": 0.8, "keyword_score": 0.9},
        {"timestamp_sec": 20.0, "combined_score": 0.7, "frame_diff": 0.7, "audio_rms": 0.7, "keyword_score": 0.7},
    ]
    result = _select_candidates(scored, top_n=10, min_spacing_sec=15.0)
    timestamps = [c["timestamp_sec"] for c in result]
    assert 0.0 in timestamps
    assert 5.0 not in timestamps   # within 15s of 0.0 — rejected
    assert 20.0 in timestamps


def test_select_candidates_respects_top_n():
    scored = [
        {"timestamp_sec": float(i * 20), "combined_score": 1.0 - i * 0.05,
         "frame_diff": 0.5, "audio_rms": 0.5, "keyword_score": 0.5}
        for i in range(20)
    ]
    result = _select_candidates(scored, top_n=5, min_spacing_sec=15.0)
    assert len(result) == 5


def test_extract_highlights_returns_manifest_shape(tmp_path):
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"fake")

    with patch("pipeline.utils.highlight_extractor.get_duration", return_value=60.0), \
         patch("pipeline.utils.highlight_extractor.detect_scene_changes", return_value=[10.0, 25.0, 40.0]), \
         patch("pipeline.utils.highlight_extractor._audio_rms_per_window", return_value=[(0.0, 0.5), (5.0, 0.8)]), \
         patch("pipeline.utils.video_analysis.extract_keyframes", return_value=[]):
        manifest = extract_highlights(fake_video, transcript_path=None)

    assert "candidates" in manifest
    assert "rejected" in manifest
    assert manifest["caption_provider"] == "NullCaptionProvider"
    assert manifest["duration_sec"] == pytest.approx(60.0, abs=0.5)
    for c in manifest["candidates"]:
        assert "timestamp_sec" in c
        assert "combined_score" in c
        assert "caption" in c
        assert c["usable"] is True
