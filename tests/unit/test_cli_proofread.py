"""Unit tests for cli_proofread._format_for_review."""
import json


def test_format_for_review_no_overlay_adds_notice(tmp_path):
    """When no scene has overlay text, the formatted string must contain the no-overlay notice."""
    from pipeline.cli_proofread import _format_for_review

    sb = {
        "version": 1,
        "format": "storyboard_v1",
        "target_duration_sec": 300,
        "aspect_ratio": "9:16",
        "theme": {},
        "scenes": [
            {"id": "s1", "section": "hook", "narration": "第一句旁白。",
             "narration_est_sec": 5, "facts_ref": [], "visual": {},
             "overlay": {}, "pause_after_sec": 0.5},
            {"id": "s2", "section": "body", "narration": "第二句旁白。",
             "narration_est_sec": 5, "facts_ref": [], "visual": {},
             "overlay": None, "pause_after_sec": 0.5},
        ],
    }
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(sb), encoding="utf-8")

    result = _format_for_review(p)
    assert "本腳本無 OVERLAY 文字" in result


def test_format_for_review_with_overlay_no_notice(tmp_path):
    """When at least one overlay exists, the no-overlay notice must NOT appear."""
    from pipeline.cli_proofread import _format_for_review

    sb = {
        "version": 1,
        "format": "storyboard_v1",
        "target_duration_sec": 300,
        "aspect_ratio": "9:16",
        "theme": {},
        "scenes": [
            {"id": "s1", "section": "hook", "narration": "旁白。",
             "narration_est_sec": 5, "facts_ref": [], "visual": {},
             "overlay": {"text": "標題文字"}, "pause_after_sec": 0.5},
        ],
    }
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(sb), encoding="utf-8")

    result = _format_for_review(p)
    assert "本腳本無 OVERLAY 文字" not in result
