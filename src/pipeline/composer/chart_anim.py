"""Animated chart reveals: pure frame generators + ffmpeg orchestrator.

Built on top of ``composer/chart.py`` (Sprint 1) and copying the multi-frame
ffmpeg pipeline from ``composer/base.py:_camera_motion_to_video``. Three animated
variants in v1: ``line`` (left-to-right curve draw with markers synced to draw
progress), ``bar`` (sequential grow with stagger), ``stat_big_number`` (digits-only
count-up with formatting preserved).

Frame generators are PURE: ``(progress, visual, base_bg, width, height, palette,
top) -> PIL.Image``. No disk, no network, no random. Identical inputs return
byte-identical images — what makes sampled-frame goldens viable.

Two-axes guardrail: ``_resolve_reveal_duration`` defaults to a fraction of the
scene duration with a ceiling; ``chart._validate_chart`` enforces
``reveal_duration_sec <= duration_sec - HOLD_TAIL_MIN_SEC`` (raises). Animation
is a visual-QUALITY lift, NOT a runtime extender.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger()

FPS = 30
HOLD_TAIL_MIN_SEC = 0.5
DEFAULT_REVEAL_FRACTION = 0.6
DEFAULT_REVEAL_MAX_SEC = 5.0
BAR_STAGGER_FRAC = 0.10
_DEFAULT_EASING = "ease_out_cubic"


def _progress_linear(t: float) -> float:
    return max(0.0, min(1.0, t))


def _progress_ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


EASING: dict[str, Callable[[float], float]] = {
    "linear": _progress_linear,
    "ease_out_cubic": _progress_ease_out_cubic,
}


def _resolve_easing(visual: dict[str, Any]) -> Callable[[float], float]:
    name = (visual.get("animate") or {}).get("easing", _DEFAULT_EASING)
    if name not in EASING:
        raise ValueError(
            f"unknown easing {name!r}; use one of {sorted(EASING)}"
        )
    return EASING[name]


def _resolve_reveal_duration(visual: dict[str, Any], duration_sec: float) -> float:
    """Default to ``min(duration_sec * fraction, max)`` when absent.

    Validation of the ceiling lives in ``chart._validate_chart`` so it fires at
    compose-time, not at frame-write-time.
    """
    explicit = (visual.get("animate") or {}).get("reveal_duration_sec")
    if explicit is not None:
        return float(explicit)
    return min(duration_sec * DEFAULT_REVEAL_FRACTION, DEFAULT_REVEAL_MAX_SEC)


_DIGIT_PATTERN = re.compile(r"(\d+)")


def _count_up_value(final_value: str, progress: float) -> tuple[str, bool]:
    """Return ``(display_string, parsed_ok)``.

    Parses contiguous digit runs in ``final_value``, scales each by ``progress``,
    reapplies the surrounding non-digit characters verbatim. Empty digit match
    (no digits at all) returns ``(final_value, False)`` so the orchestrator can
    switch to a fade-in fallback.
    """
    matches = list(_DIGIT_PATTERN.finditer(final_value))
    if not matches:
        return final_value, False
    p = max(0.0, min(1.0, progress))
    out: list[str] = []
    cursor = 0
    for m in matches:
        out.append(final_value[cursor : m.start()])
        digits = m.group(1)
        scaled = int(round(int(digits) * p))
        out.append(str(scaled).zfill(len(digits)))
        cursor = m.end()
    out.append(final_value[cursor:])
    return "".join(out), True
