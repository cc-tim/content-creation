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
    _score_keywords,
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
