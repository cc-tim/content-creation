from __future__ import annotations

import pytest

from pipeline.composer.overlay_rules import (
    OverlayCollisionError,
    check_overlay_allowed,
)


def test_text_type_is_forbidden():
    with pytest.raises(OverlayCollisionError):
        check_overlay_allowed(
            scene={"id": "s5"},
            overlay={"type": "text", "text": "x"},
            visual={"type": "article_image"},
            burn_subtitles=True,
        )


def test_text_top_allowed_over_image():
    check_overlay_allowed(
        scene={"id": "s5"},
        overlay={"type": "text_top", "text": "x"},
        visual={"type": "article_image"},
        burn_subtitles=True,
    )


def test_overlay_on_text_card_is_forbidden():
    # Text-on-text-on-text is unreadable.
    with pytest.raises(OverlayCollisionError):
        check_overlay_allowed(
            scene={"id": "s5"},
            overlay={"type": "text_top", "text": "x"},
            visual={"type": "text_card", "text": "A"},
            burn_subtitles=True,
        )


def test_overlay_on_slide_is_forbidden():
    with pytest.raises(OverlayCollisionError):
        check_overlay_allowed(
            scene={"id": "s5"},
            overlay={"type": "text_top", "text": "x"},
            visual={"type": "slide"},
            burn_subtitles=True,
        )


def test_title_allowed_anywhere():
    check_overlay_allowed(
        scene={"id": "s5"},
        overlay={"type": "title", "text": "x"},
        visual={"type": "clip"},
        burn_subtitles=True,
    )


def test_missing_overlay_is_noop():
    # No overlay = no rule to enforce
    check_overlay_allowed(
        scene={"id": "s5"},
        overlay=None,
        visual={"type": "text_card"},
        burn_subtitles=True,
    )
