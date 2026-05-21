import pytest

from pipeline.composer.chart_anim import (
    DEFAULT_REVEAL_FRACTION,
    DEFAULT_REVEAL_MAX_SEC,
    EASING,
    HOLD_TAIL_MIN_SEC,
    _count_up_value,
    _progress_ease_out_cubic,
    _progress_linear,
    _resolve_easing,
    _resolve_reveal_duration,
)


# ── Easing ─────────────────────────────────────────────────────────────────────
def test_progress_linear_endpoints():
    assert _progress_linear(0.0) == 0.0
    assert _progress_linear(1.0) == 1.0


def test_progress_ease_out_cubic_endpoints():
    assert _progress_ease_out_cubic(0.0) == 0.0
    assert _progress_ease_out_cubic(1.0) == 1.0


def test_progress_ease_out_cubic_is_front_loaded():
    assert _progress_ease_out_cubic(0.5) > 0.5


def test_easing_registry_contains_both():
    assert set(EASING.keys()) == {"linear", "ease_out_cubic"}


# ── _resolve_easing ────────────────────────────────────────────────────────────
def test_resolve_easing_defaults_to_ease_out_cubic():
    fn = _resolve_easing({"animate": {"enabled": True}})
    assert fn(0.5) > 0.5


def test_resolve_easing_explicit_linear():
    fn = _resolve_easing({"animate": {"enabled": True, "easing": "linear"}})
    assert fn(0.5) == 0.5


def test_resolve_easing_rejects_unknown():
    with pytest.raises(ValueError, match="unknown easing"):
        _resolve_easing({"animate": {"enabled": True, "easing": "bounce"}})


# ── _resolve_reveal_duration ───────────────────────────────────────────────────
def test_resolve_reveal_duration_uses_explicit_value():
    visual = {"animate": {"enabled": True, "reveal_duration_sec": 3.0}}
    assert _resolve_reveal_duration(visual, duration_sec=8.0) == 3.0


def test_resolve_reveal_duration_defaults_to_fraction_of_scene():
    visual = {"animate": {"enabled": True}}
    assert _resolve_reveal_duration(visual, duration_sec=8.0) == pytest.approx(4.8)


def test_resolve_reveal_duration_caps_at_default_max():
    visual = {"animate": {"enabled": True}}
    assert _resolve_reveal_duration(visual, duration_sec=20.0) == DEFAULT_REVEAL_MAX_SEC


# ── _count_up_value ────────────────────────────────────────────────────────────
def test_count_up_value_plain_integer():
    text, ok = _count_up_value("42", progress=0.5)
    assert ok is True
    assert text == "21"


def test_count_up_value_preserves_thousands_separator():
    text, ok = _count_up_value("230,676", progress=1.0)
    assert ok is True
    assert text == "230,676"


def test_count_up_value_progress_zero_is_zero_formatted():
    text, ok = _count_up_value("230,676", progress=0.0)
    assert ok is True
    assert text == "000,000"


def test_count_up_value_with_units_preserves_units():
    text, ok = _count_up_value("$1.1B", progress=1.0)
    assert ok is True
    assert text == "$1.1B"


def test_count_up_value_no_digits_returns_unparsed_flag():
    text, ok = _count_up_value("N/A", progress=0.5)
    assert ok is False
    assert text == "N/A"


# ── Module constants ───────────────────────────────────────────────────────────
def test_hold_tail_default():
    assert HOLD_TAIL_MIN_SEC == 0.5


def test_default_reveal_constants():
    assert DEFAULT_REVEAL_FRACTION == 0.6
    assert DEFAULT_REVEAL_MAX_SEC == 5.0
