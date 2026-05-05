from __future__ import annotations

import pytest

from pipeline.dashboard.trust_gate import classify_tier
from pipeline.storyboard import Scene, Storyboard


def _sb_with_scene(
    scene_id: str,
    narration: str = "the quick brown fox",
    subtitle_override: str | None = "the quick brown fox",
) -> Storyboard:
    return Storyboard(
        scenes=[
            Scene(
                id=scene_id,
                section="content",
                narration=narration,
                narration_est_sec=1.0,
                subtitle_override=subtitle_override,
            )
        ]
    )


def test_subtitle_set_small_delta_is_auto_apply():
    sb = _sb_with_scene("s1", subtitle_override="the quick brown fox")
    tier = classify_tier(
        "subtitle set",
        {"scene": "s1", "text": "the quick red fox"},
        sb,
    )
    assert tier == "auto_apply"


def test_subtitle_set_large_delta_is_propose():
    sb = _sb_with_scene("s1", subtitle_override="hi")
    tier = classify_tier(
        "subtitle set",
        {"scene": "s1", "text": "completely different and much longer text"},
        sb,
    )
    assert tier == "propose"


def test_subtitle_set_for_unknown_scene_is_propose():
    sb = _sb_with_scene("s1")
    tier = classify_tier("subtitle set", {"scene": "s99", "text": "x"}, sb)
    assert tier == "propose"


def test_overlay_set_small_delta_is_auto_apply():
    sb = Storyboard(
        scenes=[
            Scene(
                id="s1",
                section="content",
                narration="x",
                narration_est_sec=1.0,
                overlay={"text": "Original Overlay"},
            )
        ]
    )
    tier = classify_tier("overlay set", {"scene": "s1", "text": "Updated Overlay"}, sb)
    assert tier == "auto_apply"


def test_narration_regen_small_delta_is_auto_apply():
    sb = _sb_with_scene("s1", narration="hello world hello world")
    tier = classify_tier(
        "narration regen",
        {"scene": "s1", "text": "hello world hello there"},
        sb,
    )
    assert tier == "auto_apply"


def test_image_regen_is_always_propose():
    sb = _sb_with_scene("s1")
    tier = classify_tier(
        "image regen",
        {"scene": "s1", "prompt": "anything", "tier": "draft"},
        sb,
    )
    assert tier == "propose"


def test_transition_set_is_propose_via_agent():
    sb = _sb_with_scene("s1")
    tier = classify_tier(
        "transition set",
        {"from": "s1", "to": "s2", "style": "fade", "duration_sec": 0.5},
        sb,
    )
    assert tier == "propose"


def test_narration_set_source_is_propose_via_agent():
    sb = _sb_with_scene("s1")
    tier = classify_tier(
        "narration set-source",
        {"scene": "s1", "engine": "prerecorded", "file": "narration_overrides/s1.wav"},
        sb,
    )
    assert tier == "propose"


def test_unknown_verb_defaults_to_propose():
    sb = _sb_with_scene("s1")
    tier = classify_tier("future verb", {"scene": "s1"}, sb)
    assert tier == "propose"


@pytest.mark.parametrize(
    ("delta_ratio", "expected"),
    [
        (0.10, "auto_apply"),
        (0.50, "auto_apply"),
        (0.79, "auto_apply"),
        (0.80, "propose"),
        (0.95, "propose"),
    ],
)
def test_char_delta_threshold_is_80_percent(delta_ratio: float, expected: str):
    base = "a" * 100
    changed = int(100 * delta_ratio)
    new_text = "a" * (100 - changed) + "b" * changed
    sb = _sb_with_scene("s1", subtitle_override=base)
    tier = classify_tier("subtitle set", {"scene": "s1", "text": new_text}, sb)
    assert tier == expected
