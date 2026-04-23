# tests/integration/test_highlight_extractor.py
"""Integration test: real ffprobe against a fixture video file.

Requires: ffmpeg installed, fixture video present.
Run with: uv run pytest tests/integration/test_highlight_extractor.py -v -m integration
"""
from __future__ import annotations

import pytest
from pathlib import Path

from pipeline.utils.highlight_extractor import extract_highlights

FIXTURE_VIDEO = Path("tests/fixtures/sample_short.mp4")


@pytest.mark.integration
def test_extract_highlights_returns_valid_manifest():
    if not FIXTURE_VIDEO.exists():
        pytest.skip(f"Fixture video not found: {FIXTURE_VIDEO}")

    manifest = extract_highlights(FIXTURE_VIDEO, transcript_path=None)

    assert isinstance(manifest["candidates"], list)
    assert isinstance(manifest["rejected"], list)
    assert manifest["caption_provider"] == "NullCaptionProvider"
    assert manifest["duration_sec"] > 0

    for c in manifest["candidates"]:
        assert 0.0 <= c["combined_score"] <= 1.0
        assert c["usable"] is True
        assert "timestamp_sec" in c
        assert "keyframe_path" in c

    # Spacing check: no two candidates within 15s of each other
    timestamps = sorted(c["timestamp_sec"] for c in manifest["candidates"])
    for i in range(1, len(timestamps)):
        assert timestamps[i] - timestamps[i - 1] >= 14.9, (
            f"Candidates too close: {timestamps[i-1]}s and {timestamps[i]}s"
        )
