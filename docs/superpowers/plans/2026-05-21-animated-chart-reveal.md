# Animated Chart Reveal + Decline-Curve (Sprint 2 / E2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an animated reveal capability to the Sprint-1 `chart` substrate — left-to-right `line` curve draw (with markers sync'd to draw progress), sequential `bar` growth, and digits-only `stat_big_number` count-up — wired through a PIL multi-frame → ffmpeg pipeline that mirrors `composer/base.py:_camera_motion_to_video`. Ships a new static `chart_type: "line"` as the substrate for the animation, and delivers the producer-greenlit baby-walker merged animated decline-curve (1990→2014, six regulation markers).

**Architecture:** Two layers built on top of Sprint 1's `composer/chart.py`:
- **`composer/chart.py` gets a sixth static chart_type `line`** (axes + plotted curve + markers). Sprint-1 dispatch is unchanged; line behaves like any other chart_type when `animate.enabled` is false.
- **New `composer/chart_anim.py`** holds (a) pure frame-generator functions `(progress, visual, base_bg, width, height, palette) → PIL.Image` for `line` / `bar` / `stat_big_number`, (b) the easing helpers `_progress_linear` + `_progress_ease_out_cubic`, and (c) the orchestrator `render_animated_chart()` that builds the AI background once (cached, same as static), then per frame asks a frame-generator for the partial composite, writes a JPEG sequence to a tempdir, and runs a single ffmpeg encode copying the arg list from `_camera_motion_to_video`. Frame generators are pure (no disk, no network, no random); identical inputs return byte-identical PIL images. This is what makes sampled-frame goldens viable instead of mp4 binary comparison.

The two-axes rule lives in code: `_validate_chart` raises if `animate.reveal_duration_sec > duration_sec - HOLD_TAIL_MIN_SEC` (default `0.5s`). Reveal duration defaults to `min(duration_sec * 0.6, 5.0)` when absent. A reveal that runs during a 6-second narration line does not extend the scene; Sprint 2 cannot grow runtime.

**Tech Stack:** Python 3, Pillow (PIL) for compositing, Noto CJK fonts (re-used via existing `_SERIF_BOLD` / `_SANS_REGULAR` / `_SANS_BOLD` / `_load_font` / `_wrap_text` imports from `rich_slide`), `ffmpeg` via existing `pipeline.utils.ffmpeg.run_ffmpeg`. Tests use pytest with golden-PNG comparison; ffmpeg is **mocked** in unit tests (`patch("pipeline.composer.chart_anim.run_ffmpeg")`) so no encode runs in CI; the AI-background provider is similarly patched (`patch("pipeline.composer.chart_anim.try_chain")`).

**Determinism note:** Pillow TrueType rendering is byte-deterministic for fixed font+size+machine (Sprint 1 confirmed this). Sampled-frame goldens at `progress ∈ {0.0, 0.5, 1.0}` are generated on this machine during execution and committed under `tests/fixtures/chart_anim/golden/`. The purity test (`test_frame_generator_is_pure`) re-calls each generator twice and asserts byte-identical output BEFORE any sampled-frame test runs, so a non-deterministic generator fails loudly rather than silently passing a baked-in bug. `UPDATE_GOLDENS=1` regenerates fixtures (same convention as Sprint 1).

**Scope OUT (do NOT build here):**
- `proportion_blocks` / `timeline` / `comparison` animated variants → future Sprint 2.5 in E2 (no greenlit beat needs them today)
- Ken Burns on stills, true book-page-turn animation → later E2 sprint
- Per-marker custom callout styling on `line` (icons, colored bands, animated bands) → E3 (animated overlays)
- Style Manifest registration of the `animate` element → E4 (Sprint 3)
- Storyboard-validator hook for animation params (write-time check) → E5
- Dashboard preview of animated charts → E6
- Per-frame audio sync / SFX on marker appearance → out of arsenal scope

**Axis guard:** This is a visual-quality lift only. It does NOT add runtime. The duration-policy validator is the in-code expression of this rule — if a step is tempted to relax it, stop and ask Tim.

---

## File Structure

- **Modify `src/pipeline/composer/chart.py`** — add `"line"` to `CHART_TYPES`; add a `_render_line(draw, visual, width, height, pal, top)` function (static substrate for the animated variant); register it in the `render_chart` renderer dispatch dict; extend `_validate_chart` with `line` schema checks (`points` non-empty list of `{x, y}`, optional `markers` whose `x` is within `points` x-range) AND the `animate` block validation (duration ceiling, easing whitelist, recursive enforcement); add an `animation_enabled(visual)` helper; dispatch to `chart_anim.render_animated_chart` in `render_chart` when animation is enabled.
- **Create `src/pipeline/composer/chart_anim.py`** — new module:
  - Module constants: `HOLD_TAIL_MIN_SEC = 0.5`, `DEFAULT_REVEAL_MAX_SEC = 5.0`, `DEFAULT_REVEAL_FRACTION = 0.6`, `BAR_STAGGER_FRAC = 0.10`, `FPS = 30`.
  - Easing helpers: `_progress_linear(t: float) -> float`, `_progress_ease_out_cubic(t: float) -> float`, `EASING = {"linear": ..., "ease_out_cubic": ...}` plus a `_DEFAULT_EASING = "ease_out_cubic"`.
  - Pure frame generators: `_animate_line_frame(progress, visual, base_bg, width, height, palette)`, `_animate_bar_frame(...)`, `_animate_stat_frame(...)`. Each takes a base background `PIL.Image` (already includes header + axes + non-animated parts), draws the in-progress reveal on a copy, and returns the new image.
  - `_count_up_value(final_value: str, progress: float) -> tuple[str, bool]` — pure parser+formatter for `stat_big_number`; second tuple element is `parsed_ok`; on parse failure returns `(final_value, False)` so the orchestrator can switch to the fade-in fallback.
  - `_resolve_reveal_duration(visual, duration_sec) -> float` — applies the default + clamp.
  - `_resolve_easing(visual) -> Callable[[float], float]` — looks up easing in `EASING`, raises on unknown.
  - `render_animated_chart(visual, duration_sec, width, height, work_dir, scene_id, theme)` — public orchestrator. Builds the base background (re-using `chart._build_background` so the AI cache key is shared), builds the fully-drawn base composite once (re-using static `_render_*` for axes / non-animated chrome), enters a tempdir, writes `frame_{idx:05d}.jpg` for every frame in `duration_sec * FPS`, then calls `run_ffmpeg` exactly once with arg list mirroring `_camera_motion_to_video`. Output: `{scene_id}_visual.mp4`. Hold-tail frames repeat the final composite so the chart "settles" before the scene ends.
- **Modify `src/pipeline/stages/direct.py`** — under the `chart` block (around line 224), add `line` to the `chart_type` enum string, add a worked example for `line` with the baby-walker decline-curve datapoints (markers included), and add an `ANIMATION (optional)` subsection that shows the `animate` block on a `line` chart with `reveal_duration_sec` and `easing`. Note the duration rule explicitly in the prompt: `reveal_duration_sec must be <= scene narration duration - 0.5s`.
- **Create `tests/unit/test_chart_anim.py`** — purity test (byte-identical repeat), sampled-frame goldens (3 progress points × 3 variants = 9 fixtures), ffmpeg-mock test (assert frame count + single ffmpeg call), validation negatives (duration too long, unknown easing, line without points, markers out of range, stat parse failure → fallback path), `_count_up_value` unit tests, and `_resolve_reveal_duration` / `_resolve_easing` unit tests.
- **Modify `tests/unit/test_chart.py`** — add a static-line golden (independent of animation) + validation-passes test for a valid `line` visual; add no-animation-by-default test (line renders static when `animate` is absent).
- **Create `tests/fixtures/chart/golden/line.png`** — committed reference image.
- **Create `tests/fixtures/chart_anim/golden/line_p00.png`, `line_p05.png`, `line_p10.png`, `bar_p00.png`, `bar_p05.png`, `bar_p10.png`, `stat_p00.png`, `stat_p05.png`, `stat_p10.png`** — 9 sampled-frame fixtures.
- **Modify `output/projects/20260504-115232-baby-walker-story/storyboard.json`** — wire the existing decline-curve scene (the one currently rendering as a slide / placeholder for the "did it work?" beat) to the new animated `line` chart. This is the end-to-end acceptance vehicle.

---

## Task 1: Static `line` chart_type — substrate for the animation

**Files:**
- Modify: `src/pipeline/composer/chart.py`
- Modify: `tests/unit/test_chart.py`
- Create: `tests/fixtures/chart/golden/line.png` (generated this task)

Add the new chart_type without any animation surface. This is purely Sprint-1-shaped work and ships green even with the rest of Sprint 2 absent. The line draws a falling curve through `data.points` (1990→2014 baby-walker decline) with `data.markers` plotted as labeled dots above/below the curve at their x positions.

- [ ] **Step 1: Write failing static-line validation + golden tests**

Append to `tests/unit/test_chart.py` (the `_v` helper and `_render_png` / `_assert_golden` helpers are already at the top of the file from Sprint 1):

```python
# ── line (Sprint 2 static substrate for animation) ────────────────────────────
_LINE = {
    "type": "chart", "chart_type": "line", "ai_background": False,
    "title": "US ER visits per year", "source_credit": "AAP, 1990–2014",
    "data": {
        "points": [
            {"x": 1990, "y": 20650},
            {"x": 1999, "y": 8800},
            {"x": 2007, "y": 3200},
            {"x": 2014, "y": 2001},
        ],
        "markers": [
            {"x": 1982, "label": "First medical study"},
            {"x": 1995, "label": "Voluntary standard"},
            {"x": 1997, "label": "ASTM F977"},
            {"x": 2001, "label": "AAP ban call"},
            {"x": 2004, "label": "Canada bans"},
            {"x": 2010, "label": "CPSC mandatory"},
        ],
        "x_axis": "year", "y_axis": "ER visits",
    },
}


def test_validate_rejects_line_missing_points():
    with pytest.raises(ValueError, match="line"):
        _validate_chart(_v(chart_type="line", data={"markers": []}), "s1")


def test_validate_rejects_line_marker_out_of_range():
    with pytest.raises(ValueError, match="marker"):
        _validate_chart(
            _v(
                chart_type="line",
                data={
                    "points": [{"x": 1990, "y": 1}, {"x": 2014, "y": 1}],
                    "markers": [{"x": 1980, "label": "before"}],
                },
            ),
            "s1",
        )


def test_validate_accepts_valid_line():
    _validate_chart(_LINE, "s1")


def test_golden_line(tmp_path):
    _assert_golden(_render_png(_LINE, tmp_path, "s_line"), "line")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_chart.py::test_validate_rejects_line_missing_points tests/unit/test_chart.py::test_validate_accepts_valid_line tests/unit/test_chart.py::test_golden_line -v`

Expected: FAIL — `_validate_chart` doesn't know about `line` yet, `render_chart` will raise `unknown chart_type`.

- [ ] **Step 3: Add `line` to `CHART_TYPES` and `_validate_chart` in `chart.py`**

In `src/pipeline/composer/chart.py`, change the constant at module-top:

```python
CHART_TYPES = {"stat_big_number", "proportion_blocks", "timeline", "bar", "comparison", "line"}
```

And extend `_validate_chart` (after the existing `timeline` branch, before its closing) with a `line` branch:

```python
    elif chart_type == "line":
        points = data.get("points")
        if not isinstance(points, list) or not points:
            raise ValueError(
                f"chart {scene_id}: line data needs non-empty 'points' list of "
                f"{{x, y}} entries; got {points!r}"
            )
        for i, p in enumerate(points):
            if not isinstance(p, dict) or "x" not in p or "y" not in p:
                raise ValueError(
                    f"chart {scene_id}: line points[{i}] must be {{x, y}}; got {p!r}"
                )
        xs = [float(p["x"]) for p in points]
        x_min, x_max = min(xs), max(xs)
        markers = data.get("markers") or []
        if not isinstance(markers, list):
            raise ValueError(
                f"chart {scene_id}: line 'markers' must be a list; got {markers!r}"
            )
        for i, m in enumerate(markers):
            mx = m.get("x") if isinstance(m, dict) else None
            if mx is None:
                raise ValueError(
                    f"chart {scene_id}: line marker[{i}] missing 'x'"
                )
            if not (x_min <= float(mx) <= x_max):
                raise ValueError(
                    f"chart {scene_id}: line marker[{i}].x={mx} out of points "
                    f"x-range [{x_min}, {x_max}]"
                )
```

- [ ] **Step 4: Add `_render_line` to `chart.py`**

Add this function at the bottom of `src/pipeline/composer/chart.py`, alongside the other `_render_*` functions:

```python
def _render_line(draw, visual, width, height, pal, top) -> None:
    """Draw axes + falling curve through data.points + labeled markers.

    Used both as a static chart_type AND as the base for the animated variant.
    The animated frame generator re-uses this layout but masks the curve / markers
    by a progress factor.
    """
    data = visual["data"]
    points = data["points"]
    markers = data.get("markers") or []

    pad_l = int(width * 0.10)
    pad_r = int(width * 0.07)
    body_top = max(top + _HEADER_GAP, int(height * 0.30))
    body_bottom = int(height * _BODY_BOTTOM_FRAC)
    plot_w = width - pad_l - pad_r
    plot_h = body_bottom - body_top

    xs = [float(p["x"]) for p in points]
    ys = [float(p["y"]) for p in points]
    x_min, x_max = min(xs), max(xs)
    y_max = max(ys) or 1.0
    x_span = max(1.0, x_max - x_min)

    def _to_px(x: float, y: float) -> tuple[int, int]:
        px = pad_l + int(plot_w * (x - x_min) / x_span)
        py = body_top + int(plot_h * (1.0 - y / y_max))
        return px, py

    # Axes.
    draw.line([pad_l, body_bottom, pad_l + plot_w, body_bottom], fill=pal["muted"], width=2)
    draw.line([pad_l, body_top, pad_l, body_bottom], fill=pal["muted"], width=2)

    # X-axis year labels at first/last point.
    yf = _load_font(_SANS_REGULAR, 22)
    for x_label in (x_min, x_max):
        s = f"{int(x_label)}"
        sb = draw.textbbox((0, 0), s, font=yf)
        px = pad_l + int(plot_w * (x_label - x_min) / x_span)
        draw.text((px - (sb[2] - sb[0]) // 2, body_bottom + 8), s, font=yf, fill=pal["muted"])

    # The curve (segment by segment so the animated path can stop mid-segment).
    px_points = [_to_px(p["x"], p["y"]) for p in points]
    for a, b in zip(px_points, px_points[1:], strict=False):
        draw.line([a, b], fill=pal["accent"], width=4)
    for px, py in px_points:
        draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=pal["accent"])

    # Markers — vertical tick + dot + label, alternating above/below the curve.
    mf = _load_font(_SANS_BOLD, 18)
    for i, m in enumerate(markers):
        mx = float(m["x"])
        mpx = pad_l + int(plot_w * (mx - x_min) / x_span)
        draw.line([mpx, body_top + 8, mpx, body_bottom], fill=pal["muted"], width=1)
        draw.ellipse([mpx - 7, body_top + 1, mpx + 7, body_top + 15], fill=pal["ink"])
        label = str(m.get("label", ""))
        lb = draw.textbbox((0, 0), label, font=mf)
        lab_x = max(pad_l, min(pad_l + plot_w - (lb[2] - lb[0]), mpx - (lb[2] - lb[0]) // 2))
        # Alternate: even-indexed markers above the axis area, odd below.
        lab_y = body_top - 26 if i % 2 == 0 else body_top - 6
        draw.text((lab_x, lab_y), label, font=mf, fill=pal["ink"])
```

- [ ] **Step 5: Register `line` in the `render_chart` dispatch dict**

In `src/pipeline/composer/chart.py`, inside `render_chart`, change:

```python
    renderer = {
        "stat_big_number": _render_stat,
        "proportion_blocks": _render_proportion,
        "timeline": _render_timeline,
        "bar": _render_bar,
        "comparison": _render_comparison,
    }[chart_type]
```

to:

```python
    renderer = {
        "stat_big_number": _render_stat,
        "proportion_blocks": _render_proportion,
        "timeline": _render_timeline,
        "bar": _render_bar,
        "comparison": _render_comparison,
        "line": _render_line,
    }[chart_type]
```

- [ ] **Step 6: Run validation tests to confirm they pass**

Run: `uv run pytest tests/unit/test_chart.py::test_validate_rejects_line_missing_points tests/unit/test_chart.py::test_validate_rejects_line_marker_out_of_range tests/unit/test_chart.py::test_validate_accepts_valid_line -v`

Expected: PASS.

- [ ] **Step 7: Generate the static line golden**

Run: `UPDATE_GOLDENS=1 uv run pytest tests/unit/test_chart.py::test_golden_line -v`

Expected: PASS — `tests/fixtures/chart/golden/line.png` is created.

- [ ] **Step 8: Visually inspect the golden BEFORE committing**

Open `tests/fixtures/chart/golden/line.png`. Verify by eye:
- Warm editorial palette (cream paper, terracotta curve).
- Axes legible; "1990" and "2014" labels visible under the x-axis.
- Falling curve passes through the four datapoints.
- Six regulation markers visible above the plot area with labels alternating heights (so they don't overlap).
- Source credit visible bottom-right; no overlap with the bottom-25% subtitle safe zone.

If any check fails — adjust `_render_line` and regenerate. Goldens lock in layout bugs; eyeball before commit.

- [ ] **Step 9: Re-run golden test without `UPDATE_GOLDENS` to confirm determinism**

Run: `uv run pytest tests/unit/test_chart.py::test_golden_line -v`

Expected: PASS (the just-rendered output matches the golden byte-for-byte). If this fails, the renderer is non-deterministic on this machine and Sprint-1's determinism contract is broken — STOP and report.

- [ ] **Step 10: Run the full chart suite to confirm Sprint-1 fixtures still pass**

Run: `uv run pytest tests/unit/test_chart.py -v`

Expected: ALL pass (Sprint-1's five goldens + the new line one + validation tests).

- [ ] **Step 11: Commit**

```bash
git add src/pipeline/composer/chart.py tests/unit/test_chart.py tests/fixtures/chart/golden/line.png
git commit -m "feat(chart): add static 'line' chart_type substrate for E2 animation"
```

---

## Task 2: `chart_anim.py` scaffold — easing helpers + frame-generator purity contract

**Files:**
- Create: `src/pipeline/composer/chart_anim.py`
- Create: `tests/unit/test_chart_anim.py`

Stand up the new module with only the foundational pieces: module constants, easing functions, the `_resolve_*` helpers, and the `_count_up_value` parser. No frame generators yet — those come in Tasks 3/4/5. This task locks in the contracts before any animation code lands.

- [ ] **Step 1: Write failing easing + helper tests**

Create `tests/unit/test_chart_anim.py`:

```python
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
    # ease_out_cubic should be > linear at the midpoint (fast arrival).
    assert _progress_ease_out_cubic(0.5) > 0.5


def test_easing_registry_contains_both():
    assert set(EASING.keys()) == {"linear", "ease_out_cubic"}


# ── _resolve_easing ────────────────────────────────────────────────────────────
def test_resolve_easing_defaults_to_ease_out_cubic():
    fn = _resolve_easing({"animate": {"enabled": True}})
    assert fn(0.5) > 0.5  # ease_out_cubic signature


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
    # 8.0 * 0.6 = 4.8, below the 5.0 ceiling.
    assert _resolve_reveal_duration(visual, duration_sec=8.0) == pytest.approx(4.8)


def test_resolve_reveal_duration_caps_at_default_max():
    visual = {"animate": {"enabled": True}}
    # 20.0 * 0.6 = 12.0, capped at DEFAULT_REVEAL_MAX_SEC = 5.0.
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
    # All digits go to 0 but the separator pattern is preserved.
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_chart_anim.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.composer.chart_anim'`.

- [ ] **Step 3: Create the `chart_anim.py` scaffold**

Create `src/pipeline/composer/chart_anim.py`:

```python
"""Animated chart reveals: pure frame generators + ffmpeg orchestrator.

Built on top of ``composer/chart.py`` (Sprint 1) and copying the multi-frame
ffmpeg pipeline from ``composer/base.py:_camera_motion_to_video``. Three animated
variants in v1: ``line`` (left-to-right curve draw with markers synced to draw
progress), ``bar`` (sequential grow with stagger), ``stat_big_number`` (digits-only
count-up with formatting preserved).

Frame generators are PURE: ``(progress, visual, base_bg, width, height, palette)
-> PIL.Image``. No disk, no network, no random. Identical inputs return
byte-identical images. This is what makes sampled-frame goldens viable.

Two-axes guardrail: ``_resolve_reveal_duration`` defaults to a fraction of the
scene duration with a ceiling; ``chart._validate_chart`` enforces
``reveal_duration_sec <= duration_sec - HOLD_TAIL_MIN_SEC`` (raises). Animation
is a visual-QUALITY lift, NOT a runtime extender.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any, Callable

import structlog

from pipeline.utils.ffmpeg import run_ffmpeg

logger = structlog.get_logger()

# Module constants — referenced by tests; bumping these is a deliberate change.
FPS = 30
HOLD_TAIL_MIN_SEC = 0.5
DEFAULT_REVEAL_FRACTION = 0.6
DEFAULT_REVEAL_MAX_SEC = 5.0
BAR_STAGGER_FRAC = 0.10
_DEFAULT_EASING = "ease_out_cubic"


# ── Easing ─────────────────────────────────────────────────────────────────────
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

    Validation of the ceiling (reveal <= duration - HOLD_TAIL_MIN_SEC) lives in
    ``chart._validate_chart`` so it fires at compose-time, not at frame-write-time.
    """
    explicit = (visual.get("animate") or {}).get("reveal_duration_sec")
    if explicit is not None:
        return float(explicit)
    return min(duration_sec * DEFAULT_REVEAL_FRACTION, DEFAULT_REVEAL_MAX_SEC)


# ── stat_big_number count-up parser ────────────────────────────────────────────
_DIGIT_PATTERN = re.compile(r"(\d+)")


def _count_up_value(final_value: str, progress: float) -> tuple[str, bool]:
    """Return (display_string, parsed_ok).

    Parses contiguous digit runs in ``final_value``, scales each by ``progress``,
    and reapplies the surrounding non-digit characters verbatim. Empty digit
    matches (no digits in the string) return ``(final_value, False)`` so the
    orchestrator can switch to a fade-in fallback.

    Examples:
      "42"      , 0.5 -> "21"
      "230,676" , 1.0 -> "230,676"
      "230,676" , 0.0 -> "000,000"   # separator preserved, digits go to 0
      "$1.1B"   , 1.0 -> "$1.1B"
      "N/A"     , 0.5 -> ("N/A", False)
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
        # Preserve the original digit width by zero-padding to len(digits).
        out.append(str(scaled).zfill(len(digits)))
        cursor = m.end()
    out.append(final_value[cursor:])
    return "".join(out), True
```

- [ ] **Step 4: Run the easing + helper tests**

Run: `uv run pytest tests/unit/test_chart_anim.py -v`

Expected: PASS — all 16 tests in this file pass.

- [ ] **Step 5: Run ruff + mypy on the new module**

Run: `uv run ruff check src/pipeline/composer/chart_anim.py tests/unit/test_chart_anim.py && uv run mypy src/pipeline/composer/chart_anim.py`

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/composer/chart_anim.py tests/unit/test_chart_anim.py
git commit -m "feat(chart-anim): scaffold easing + reveal-duration + count-up helpers"
```

---

## Task 3: Animated `line` frame generator + sampled-frame goldens

**Files:**
- Modify: `src/pipeline/composer/chart_anim.py`
- Modify: `tests/unit/test_chart_anim.py`
- Create: `tests/fixtures/chart_anim/golden/line_p00.png`
- Create: `tests/fixtures/chart_anim/golden/line_p05.png`
- Create: `tests/fixtures/chart_anim/golden/line_p10.png`

The `line` frame generator is the flagship — it draws the curve up to `progress * line_length` and reveals markers as the draw passes their x position. The base background already has the header + axes drawn (built by the orchestrator); the frame generator copies it and draws only the in-progress curve + revealed markers + revealed datapoint dots.

- [ ] **Step 1: Add the purity contract test**

Append to `tests/unit/test_chart_anim.py`:

```python
# ── Frame-generator purity (the contract that makes goldens viable) ────────────
from pathlib import Path

from PIL import Image, ImageChops

from pipeline.composer.chart import _palette
from pipeline.composer.chart_anim import _animate_line_frame

_GOLDEN_ANIM = Path(__file__).parent.parent / "fixtures" / "chart_anim" / "golden"
W, H = 1280, 720

_LINE_VISUAL = {
    "type": "chart", "chart_type": "line", "ai_background": False,
    "title": "US ER visits per year", "source_credit": "AAP, 1990-2014",
    "animate": {"enabled": True, "reveal_duration_sec": 4.0, "easing": "ease_out_cubic"},
    "data": {
        "points": [
            {"x": 1990, "y": 20650},
            {"x": 1999, "y": 8800},
            {"x": 2007, "y": 3200},
            {"x": 2014, "y": 2001},
        ],
        "markers": [
            {"x": 1982, "label": "First medical study"},
            {"x": 1995, "label": "Voluntary standard"},
            {"x": 1997, "label": "ASTM F977"},
            {"x": 2001, "label": "AAP ban call"},
            {"x": 2004, "label": "Canada bans"},
            {"x": 2010, "label": "CPSC mandatory"},
        ],
    },
}


def _line_base_bg(width=W, height=H):
    """Replicate what the orchestrator produces: paper + header + axes drawn.

    The frame generator MUST be pure — it does no I/O — so the test builds the
    base in memory using the same primitives as the static path.
    """
    from PIL import Image, ImageDraw

    from pipeline.composer.chart import _draw_header, _palette, _render_line
    pal = _palette({})
    bg = Image.new("RGB", (width, height), pal["paper"])
    draw = ImageDraw.Draw(bg)
    top = _draw_header(draw, _LINE_VISUAL, width, height, pal)
    # Draw axes + axis labels (NOT the data) — the easiest way is to render the
    # full static then have the animated generator overdraw with progress.
    # For Sprint 2 we accept that the base IS the full static image and the
    # frame generator masks the curve / markers by re-drawing them on a copy.
    _render_line(draw, _LINE_VISUAL, width, height, pal, top)
    return bg, pal, top


def test_animate_line_frame_is_pure():
    base, pal, top = _line_base_bg()
    a = _animate_line_frame(0.5, _LINE_VISUAL, base, W, H, pal, top)
    b = _animate_line_frame(0.5, _LINE_VISUAL, base, W, H, pal, top)
    diff = ImageChops.difference(a, b)
    assert diff.getbbox() is None, "line frame generator is non-deterministic"


def _assert_anim_golden(image, name: str) -> None:
    import os
    golden = _GOLDEN_ANIM / f"{name}.png"
    if os.environ.get("UPDATE_GOLDENS"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        image.save(golden)
        return
    assert golden.exists(), f"missing golden {golden}; run with UPDATE_GOLDENS=1"
    diff = ImageChops.difference(image, Image.open(golden).convert("RGB"))
    assert diff.getbbox() is None, f"{name} render drifted from golden"


def test_golden_line_progress_00():
    base, pal, top = _line_base_bg()
    img = _animate_line_frame(0.0, _LINE_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "line_p00")


def test_golden_line_progress_05():
    base, pal, top = _line_base_bg()
    img = _animate_line_frame(0.5, _LINE_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "line_p05")


def test_golden_line_progress_10():
    base, pal, top = _line_base_bg()
    img = _animate_line_frame(1.0, _LINE_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "line_p10")
```

NB the test imports `_palette` and `_draw_header` and `_render_line` from `chart.py`; those already exist (Sprint 1) — `_render_line` was added in Task 1.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_chart_anim.py::test_animate_line_frame_is_pure -v`

Expected: FAIL — `ImportError: cannot import name '_animate_line_frame'`.

- [ ] **Step 3: Implement `_animate_line_frame` in `chart_anim.py`**

Append to `src/pipeline/composer/chart_anim.py`:

```python
# ── Frame generators ───────────────────────────────────────────────────────────
def _animate_line_frame(
    progress: float,
    visual: dict[str, Any],
    base_bg: Any,
    width: int,
    height: int,
    palette: dict[str, tuple[int, int, int]],
    top: int,
) -> Any:
    """Draw the `line` chart up to `progress` of its total path length.

    The base background is taken AS-IS (the orchestrator drew the header onto a
    paper canvas; the frame generator paints the data on a copy). At progress=0
    nothing data-related is drawn. At progress=1 the full curve + all markers
    are visible. Markers appear as the draw passes their x-position — i.e. a
    marker at x=1995 becomes visible the moment the curve reaches x=1995.
    """
    from PIL import Image, ImageDraw

    from pipeline.composer.chart import _BODY_BOTTOM_FRAC, _HEADER_GAP

    # Operate on a copy so the base remains pristine across frames.
    img = base_bg.copy()
    # WIPE the data layer that the test's base-builder drew — we re-draw it at
    # the requested progress. The wipe rectangle covers the plot area only; the
    # header stays.
    pad_l = int(width * 0.10)
    pad_r = int(width * 0.07)
    body_top = max(top + _HEADER_GAP, int(height * 0.30))
    body_bottom = int(height * _BODY_BOTTOM_FRAC)
    plot_w = width - pad_l - pad_r

    wipe = ImageDraw.Draw(img)
    wipe.rectangle(
        [pad_l - 12, body_top - 30, pad_l + plot_w + pad_r, body_bottom + 40],
        fill=palette["paper"],
    )

    data = visual["data"]
    points = data["points"]
    markers = data.get("markers") or []

    xs = [float(p["x"]) for p in points]
    ys = [float(p["y"]) for p in points]
    x_min, x_max = min(xs), max(xs)
    y_max = max(ys) or 1.0
    x_span = max(1.0, x_max - x_min)
    plot_h = body_bottom - body_top

    def _to_px(x: float, y: float) -> tuple[int, int]:
        px = pad_l + int(plot_w * (x - x_min) / x_span)
        py = body_top + int(plot_h * (1.0 - y / y_max))
        return px, py

    draw = ImageDraw.Draw(img)
    # Axes always at full.
    draw.line([pad_l, body_bottom, pad_l + plot_w, body_bottom],
              fill=palette["muted"], width=2)
    draw.line([pad_l, body_top, pad_l, body_bottom],
              fill=palette["muted"], width=2)

    # X-axis year labels.
    from pipeline.composer.rich_slide import _SANS_BOLD, _SANS_REGULAR, _load_font
    yf = _load_font(_SANS_REGULAR, 22)
    for x_label in (x_min, x_max):
        s = f"{int(x_label)}"
        sb = draw.textbbox((0, 0), s, font=yf)
        px = pad_l + int(plot_w * (x_label - x_min) / x_span)
        draw.text((px - (sb[2] - sb[0]) // 2, body_bottom + 8),
                  s, font=yf, fill=palette["muted"])

    # Curve: walk segments, draw fully until we cross the progress threshold,
    # then truncate the final visible segment.
    if progress > 0.0:
        px_points = [_to_px(p["x"], p["y"]) for p in points]
        # Compute total path length to know where progress crosses.
        seg_lengths = [
            ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            for a, b in zip(px_points, px_points[1:], strict=False)
        ]
        total = sum(seg_lengths) or 1.0
        target = total * progress

        consumed = 0.0
        cur_x_data = xs[0]  # x in data-space that the draw has reached
        for (a, b), seg_len, a_x_data, b_x_data in zip(
            zip(px_points, px_points[1:], strict=False),
            seg_lengths,
            xs,
            xs[1:],
            strict=False,
        ):
            if consumed + seg_len <= target:
                draw.line([a, b], fill=palette["accent"], width=4)
                consumed += seg_len
                cur_x_data = b_x_data
            else:
                frac = (target - consumed) / seg_len if seg_len > 0 else 1.0
                end = (
                    a[0] + int((b[0] - a[0]) * frac),
                    a[1] + int((b[1] - a[1]) * frac),
                )
                draw.line([a, end], fill=palette["accent"], width=4)
                cur_x_data = a_x_data + (b_x_data - a_x_data) * frac
                break
        # Draw datapoint dots only for points whose x has been reached.
        for (px, py), px_x in zip(px_points, xs, strict=False):
            if px_x <= cur_x_data:
                draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=palette["accent"])
    else:
        cur_x_data = xs[0] - 1.0  # no data drawn yet → no markers visible

    # Markers — appear when the draw has passed their x.
    mf = _load_font(_SANS_BOLD, 18)
    for i, m in enumerate(markers):
        mx = float(m["x"])
        if mx > cur_x_data:
            continue
        mpx = pad_l + int(plot_w * (mx - x_min) / x_span)
        draw.line([mpx, body_top + 8, mpx, body_bottom], fill=palette["muted"], width=1)
        draw.ellipse([mpx - 7, body_top + 1, mpx + 7, body_top + 15], fill=palette["ink"])
        label = str(m.get("label", ""))
        lb = draw.textbbox((0, 0), label, font=mf)
        lab_x = max(pad_l, min(pad_l + plot_w - (lb[2] - lb[0]),
                                mpx - (lb[2] - lb[0]) // 2))
        lab_y = body_top - 26 if i % 2 == 0 else body_top - 6
        draw.text((lab_x, lab_y), label, font=mf, fill=palette["ink"])

    return img
```

- [ ] **Step 4: Run the purity test**

Run: `uv run pytest tests/unit/test_chart_anim.py::test_animate_line_frame_is_pure -v`

Expected: PASS — calling the generator twice with identical inputs returns byte-identical PIL images.

If FAIL: investigate non-determinism BEFORE generating goldens. A common cause is iterating over a dict — Python 3 preserves insertion order, but if the implementation uses `set()` for marker iteration the order changes between runs. The reference implementation above uses `list` everywhere; if you've diverged, fix.

- [ ] **Step 5: Generate the line sampled-frame goldens**

Run: `UPDATE_GOLDENS=1 uv run pytest "tests/unit/test_chart_anim.py::test_golden_line_progress_00" "tests/unit/test_chart_anim.py::test_golden_line_progress_05" "tests/unit/test_chart_anim.py::test_golden_line_progress_10" -v`

Expected: PASS — three PNGs created under `tests/fixtures/chart_anim/golden/`.

- [ ] **Step 6: Visually inspect each golden**

Open `tests/fixtures/chart_anim/golden/line_p00.png`, `line_p05.png`, `line_p10.png` and verify by eye:
- `p00`: no curve, no markers, no datapoint dots. Axes + year labels visible. (The header was drawn on the base before wipe; verify the title is still there.)
- `p05`: curve drawn approximately halfway across the plot (left half visible, right half empty). Markers up to mid-x are visible; later markers (Canada bans, CPSC mandatory) are NOT yet visible.
- `p10`: full curve, all six markers visible with alternating heights.

If any layout looks wrong (markers overlapping, curve cropped, year labels in the subtitle safe zone) — fix `_animate_line_frame` and regenerate.

- [ ] **Step 7: Re-run golden tests without `UPDATE_GOLDENS` to confirm determinism**

Run: `uv run pytest tests/unit/test_chart_anim.py -k "golden_line" -v`

Expected: ALL three pass.

- [ ] **Step 8: Commit**

```bash
git add src/pipeline/composer/chart_anim.py tests/unit/test_chart_anim.py tests/fixtures/chart_anim/golden/line_p00.png tests/fixtures/chart_anim/golden/line_p05.png tests/fixtures/chart_anim/golden/line_p10.png
git commit -m "feat(chart-anim): animated line frame generator + sampled-frame goldens"
```

---

## Task 4: Animated `bar` frame generator + sampled-frame goldens

**Files:**
- Modify: `src/pipeline/composer/chart_anim.py`
- Modify: `tests/unit/test_chart_anim.py`
- Create: `tests/fixtures/chart_anim/golden/bar_p00.png`, `bar_p05.png`, `bar_p10.png`

Each bar grows from width 0 → final width. Bars stagger-start at `i * BAR_STAGGER_FRAC * total_reveal_fraction` so they read sequentially. The label always shows at full opacity (else the chart looks broken at p=0).

- [ ] **Step 1: Append the bar tests**

Append to `tests/unit/test_chart_anim.py`:

```python
from pipeline.composer.chart_anim import _animate_bar_frame

_BAR_VISUAL = {
    "type": "chart", "chart_type": "bar", "ai_background": False,
    "title": "Walker injury mechanisms", "source_credit": "AAP",
    "animate": {"enabled": True, "reveal_duration_sec": 4.0, "easing": "ease_out_cubic"},
    "data": {
        "x": ["stair falls", "tip-overs", "burns", "drowning"],
        "y": [74, 13, 6, 4],
        "y_unit": "%",
    },
}


def _bar_base_bg(width=W, height=H):
    from PIL import Image, ImageDraw

    from pipeline.composer.chart import _draw_header, _palette
    pal = _palette({})
    bg = Image.new("RGB", (width, height), pal["paper"])
    draw = ImageDraw.Draw(bg)
    top = _draw_header(draw, _BAR_VISUAL, width, height, pal)
    # Bar base is just header + paper; the bar frame generator draws every bar
    # at its progress-scaled width on each frame.
    return bg, pal, top


def test_animate_bar_frame_is_pure():
    base, pal, top = _bar_base_bg()
    a = _animate_bar_frame(0.5, _BAR_VISUAL, base, W, H, pal, top)
    b = _animate_bar_frame(0.5, _BAR_VISUAL, base, W, H, pal, top)
    diff = ImageChops.difference(a, b)
    assert diff.getbbox() is None


def test_golden_bar_progress_00():
    base, pal, top = _bar_base_bg()
    img = _animate_bar_frame(0.0, _BAR_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "bar_p00")


def test_golden_bar_progress_05():
    base, pal, top = _bar_base_bg()
    img = _animate_bar_frame(0.5, _BAR_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "bar_p05")


def test_golden_bar_progress_10():
    base, pal, top = _bar_base_bg()
    img = _animate_bar_frame(1.0, _BAR_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "bar_p10")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_chart_anim.py::test_animate_bar_frame_is_pure -v`

Expected: FAIL — `ImportError: cannot import name '_animate_bar_frame'`.

- [ ] **Step 3: Implement `_animate_bar_frame`**

Append to `src/pipeline/composer/chart_anim.py`:

```python
def _animate_bar_frame(
    progress: float,
    visual: dict[str, Any],
    base_bg: Any,
    width: int,
    height: int,
    palette: dict[str, tuple[int, int, int]],
    top: int,
) -> Any:
    """Draw the `bar` chart with each bar grown to `progress` of its final width.

    Bars stagger-start: bar `i` (0-indexed) starts growing at fraction
    ``i * BAR_STAGGER_FRAC`` of the overall reveal and finishes at
    ``i * BAR_STAGGER_FRAC + (1 - (n-1) * BAR_STAGGER_FRAC)``. Labels always show
    at full opacity from progress=0 (so the chart never reads "broken").
    """
    from PIL import ImageDraw

    from pipeline.composer.chart import _BODY_BOTTOM_FRAC, _HEADER_GAP
    from pipeline.composer.rich_slide import _SANS_BOLD, _SERIF_BOLD, _load_font

    img = base_bg.copy()
    draw = ImageDraw.Draw(img)

    data = visual["data"]
    xs = data["x"]
    ys = [float(v) for v in data["y"]]
    unit = data.get("y_unit", "")
    pad = int(width * 0.07)

    label_f = _load_font(_SANS_BOLD, 26)
    val_f = _load_font(_SERIF_BOLD, 28)
    max_v = max(ys) or 1.0
    track_w = int(width * 0.62)
    y0 = max(top + _HEADER_GAP, int(height * 0.28))
    body_bottom = int(height * _BODY_BOTTOM_FRAC)
    row_h = int((body_bottom - y0) / len(xs))
    bar_h = min(int(row_h * 0.42), 46)

    n = len(xs)
    # Stagger window: each bar grows over a window of size grow_span centered on
    # its stagger start. Last bar finishes exactly at progress=1.
    grow_span = max(0.0, 1.0 - (n - 1) * BAR_STAGGER_FRAC)

    for i, (label, v) in enumerate(zip(xs, ys, strict=False)):
        start_frac = i * BAR_STAGGER_FRAC
        local = (progress - start_frac) / max(0.0001, grow_span)
        local = max(0.0, min(1.0, local))

        # Label always rendered at full.
        draw.text((pad, y0), str(label), font=label_f, fill=palette["ink"])
        by = y0 + 34
        full_bw = int(track_w * (v / max_v))
        bw = max(0, int(full_bw * local))
        if bw > 0:
            draw.rectangle([pad, by, pad + max(2, bw), by + bar_h],
                           fill=palette["accent"])
        # Value text appears only once the bar has reached at least 90% of its
        # final width (else the number "races" the bar and looks wrong).
        if local >= 0.9:
            vtxt = f"{v:g}{unit}"
            draw.text((pad + max(2, full_bw) + 16, by + bar_h // 2 - 16),
                      vtxt, font=val_f, fill=palette["ink"])
        y0 += row_h

    return img
```

- [ ] **Step 4: Run the purity test**

Run: `uv run pytest tests/unit/test_chart_anim.py::test_animate_bar_frame_is_pure -v`

Expected: PASS.

- [ ] **Step 5: Generate the bar goldens**

Run: `UPDATE_GOLDENS=1 uv run pytest "tests/unit/test_chart_anim.py::test_golden_bar_progress_00" "tests/unit/test_chart_anim.py::test_golden_bar_progress_05" "tests/unit/test_chart_anim.py::test_golden_bar_progress_10" -v`

Expected: PASS — three PNGs created.

- [ ] **Step 6: Visually inspect**

- `bar_p00`: all four labels visible, no bars drawn yet, no value text. Header visible.
- `bar_p05`: bar 1 (stair falls) close to full + value text visible; bar 2 partial; bar 3 just starting; bar 4 not yet visible.
- `bar_p10`: all four bars at full width, all values printed.

If layout fails (labels overlapping, value text inside the bar, last bar clipped at bottom of safe zone) — fix and regenerate.

- [ ] **Step 7: Re-run goldens without `UPDATE_GOLDENS`**

Run: `uv run pytest tests/unit/test_chart_anim.py -k "golden_bar" -v`

Expected: ALL three pass.

- [ ] **Step 8: Commit**

```bash
git add src/pipeline/composer/chart_anim.py tests/unit/test_chart_anim.py tests/fixtures/chart_anim/golden/bar_p00.png tests/fixtures/chart_anim/golden/bar_p05.png tests/fixtures/chart_anim/golden/bar_p10.png
git commit -m "feat(chart-anim): animated bar frame generator + sampled-frame goldens"
```

---

## Task 5: Animated `stat_big_number` frame generator + sampled-frame goldens

**Files:**
- Modify: `src/pipeline/composer/chart_anim.py`
- Modify: `tests/unit/test_chart_anim.py`
- Create: `tests/fixtures/chart_anim/golden/stat_p00.png`, `stat_p05.png`, `stat_p10.png`

Counts the digits up from 0 → final, preserving the original character spacing (so `230,676` reads `000,000 → 115,338 → 230,676`). Falls back to a fade-in for non-numeric values (e.g. `"N/A"` — display stays at the final value with opacity scaled by progress).

- [ ] **Step 1: Append the stat tests**

Append to `tests/unit/test_chart_anim.py`:

```python
from pipeline.composer.chart_anim import _animate_stat_frame

_STAT_VISUAL = {
    "type": "chart", "chart_type": "stat_big_number", "ai_background": False,
    "title": "Cumulative injuries", "source_credit": "AAP, 2014",
    "animate": {"enabled": True, "reveal_duration_sec": 3.0, "easing": "ease_out_cubic"},
    "data": {"value": "230,676", "unit": "children", "context": "1990-2014"},
}


def _stat_base_bg(width=W, height=H):
    from PIL import Image, ImageDraw

    from pipeline.composer.chart import _draw_header, _palette
    pal = _palette({})
    bg = Image.new("RGB", (width, height), pal["paper"])
    draw = ImageDraw.Draw(bg)
    top = _draw_header(draw, _STAT_VISUAL, width, height, pal)
    return bg, pal, top


def test_animate_stat_frame_is_pure():
    base, pal, top = _stat_base_bg()
    a = _animate_stat_frame(0.5, _STAT_VISUAL, base, W, H, pal, top)
    b = _animate_stat_frame(0.5, _STAT_VISUAL, base, W, H, pal, top)
    diff = ImageChops.difference(a, b)
    assert diff.getbbox() is None


def test_golden_stat_progress_00():
    base, pal, top = _stat_base_bg()
    img = _animate_stat_frame(0.0, _STAT_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "stat_p00")


def test_golden_stat_progress_05():
    base, pal, top = _stat_base_bg()
    img = _animate_stat_frame(0.5, _STAT_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "stat_p05")


def test_golden_stat_progress_10():
    base, pal, top = _stat_base_bg()
    img = _animate_stat_frame(1.0, _STAT_VISUAL, base, W, H, pal, top)
    _assert_anim_golden(img, "stat_p10")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_chart_anim.py::test_animate_stat_frame_is_pure -v`

Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement `_animate_stat_frame`**

Append to `src/pipeline/composer/chart_anim.py`:

```python
def _animate_stat_frame(
    progress: float,
    visual: dict[str, Any],
    base_bg: Any,
    width: int,
    height: int,
    palette: dict[str, tuple[int, int, int]],
    top: int,
) -> Any:
    """Count the value digit-by-digit from 0 → final.

    For parseable values (e.g. ``"230,676"``, ``"$1.1B"``) digits are scaled by
    progress; the surrounding characters (commas, currency markers, suffixes)
    are preserved verbatim. For values with no digit runs (e.g. ``"N/A"``) we
    fall back to a fade-in: the final value is drawn at every frame with an
    accent→ink color blend driven by progress, so the chart never reads "broken".
    """
    from PIL import ImageDraw

    from pipeline.composer.chart import _BODY_BOTTOM_FRAC, _HEADER_GAP
    from pipeline.composer.rich_slide import _SANS_BOLD, _SANS_REGULAR, _SERIF_BOLD, _load_font

    img = base_bg.copy()
    draw = ImageDraw.Draw(img)

    data = visual["data"]
    final_value = str(data["value"])
    display_value, parsed_ok = _count_up_value(final_value, progress)

    if not parsed_ok:
        logger.warning(
            "chart_anim.stat_count_up_parse_failed",
            scene=visual.get("_scene_id", "?"),
            value=final_value,
        )

    cx = width // 2
    body_top = max(top + _HEADER_GAP, int(height * 0.30))

    num_f = _load_font(_SERIF_BOLD, 150)
    nb = draw.textbbox((0, 0), display_value, font=num_f)
    color = palette["accent"]
    if not parsed_ok:
        # Fade-in fallback: blend accent → ink by progress on the FINAL value.
        a = palette["accent"]
        k = max(0.0, min(1.0, progress))
        color = (
            int(a[0] * k + palette["paper"][0] * (1 - k)),
            int(a[1] * k + palette["paper"][1] * (1 - k)),
            int(a[2] * k + palette["paper"][2] * (1 - k)),
        )
    draw.text((cx - (nb[2] - nb[0]) // 2, body_top), display_value,
              font=num_f, fill=color)
    y = body_top + nb[3] + 24

    unit = str(data.get("unit", ""))
    if unit:
        uf = _load_font(_SANS_BOLD, 36)
        ub = draw.textbbox((0, 0), unit.upper(), font=uf)
        draw.text((cx - (ub[2] - ub[0]) // 2, y), unit.upper(),
                  font=uf, fill=palette["ink"])
        y += 52

    context = str(data.get("context", ""))
    if context:
        cf = _load_font(_SANS_REGULAR, 28)
        cb = draw.textbbox((0, 0), context, font=cf)
        draw.text((cx - (cb[2] - cb[0]) // 2, y), context,
                  font=cf, fill=palette["muted"])

    return img
```

- [ ] **Step 4: Run the purity test**

Run: `uv run pytest tests/unit/test_chart_anim.py::test_animate_stat_frame_is_pure -v`

Expected: PASS.

- [ ] **Step 5: Generate the stat goldens**

Run: `UPDATE_GOLDENS=1 uv run pytest "tests/unit/test_chart_anim.py::test_golden_stat_progress_00" "tests/unit/test_chart_anim.py::test_golden_stat_progress_05" "tests/unit/test_chart_anim.py::test_golden_stat_progress_10" -v`

Expected: PASS — three PNGs created.

- [ ] **Step 6: Visually inspect**

- `stat_p00`: header visible; large terracotta number reading `000,000`; unit `CHILDREN`; context `1990-2014`.
- `stat_p05`: number reads `115,338` (half of 230,676). Same unit + context below.
- `stat_p10`: number reads `230,676`. Identical layout.

Layout should match the Sprint-1 static stat golden (`tests/fixtures/chart/golden/stat_big_number.png`) at `p10` — the renderer reuses the same primitives. Eyeball both side-by-side; if they diverge unexpectedly, the layout drifted.

- [ ] **Step 7: Re-run goldens without `UPDATE_GOLDENS`**

Run: `uv run pytest tests/unit/test_chart_anim.py -k "golden_stat" -v`

Expected: ALL three pass.

- [ ] **Step 8: Commit**

```bash
git add src/pipeline/composer/chart_anim.py tests/unit/test_chart_anim.py tests/fixtures/chart_anim/golden/stat_p00.png tests/fixtures/chart_anim/golden/stat_p05.png tests/fixtures/chart_anim/golden/stat_p10.png
git commit -m "feat(chart-anim): animated stat_big_number frame generator + goldens"
```

---

## Task 6: `render_animated_chart` orchestrator + ffmpeg-mock test

**Files:**
- Modify: `src/pipeline/composer/chart_anim.py`
- Modify: `tests/unit/test_chart_anim.py`

The orchestrator builds the base background once, builds the fully-drawn base composite, then iterates `duration_sec * FPS` frames: each frame calls the right frame generator with `progress = easing(idx / (reveal_frames - 1))` clamped to 1.0 once `idx >= reveal_frames`. Frames are saved to a tempdir as `frame_{idx:05d}.jpg`; a single `run_ffmpeg` call encodes the sequence to the scene mp4. Args are copied verbatim from `composer/base.py:_camera_motion_to_video:172-192`.

- [ ] **Step 1: Append the ffmpeg-mock + variant-dispatch tests**

Append to `tests/unit/test_chart_anim.py`:

```python
from unittest.mock import patch

from pipeline.composer.chart_anim import FPS, render_animated_chart


def test_render_animated_chart_writes_frame_sequence_and_calls_ffmpeg(tmp_path):
    """No ffmpeg in CI: mock run_ffmpeg, assert correct frame count and one call."""
    captured: dict[str, Any] = {}

    def fake_ffmpeg(cmd, timeout=600):
        # Capture the framerate-input pattern + count files written to the dir
        # that the -i argument references.
        idx = cmd.index("-i")
        pattern = cmd[idx + 1]
        frame_dir = Path(pattern).parent
        captured["frame_count"] = len(list(frame_dir.glob("frame_*.jpg")))
        captured["pattern"] = pattern
        captured["fps_arg"] = cmd[cmd.index("-framerate") + 1]
        # Touch the output path so the orchestrator's existence check passes.
        Path(cmd[-1]).write_bytes(b"")
        return None

    duration = 4.0
    with patch("pipeline.composer.chart_anim.run_ffmpeg", side_effect=fake_ffmpeg) as ff:
        out = render_animated_chart(
            _LINE_VISUAL, duration_sec=duration, width=W, height=H,
            work_dir=tmp_path, scene_id="s_line", theme={},
        )

    assert ff.call_count == 1, "ffmpeg must be invoked exactly once per scene"
    assert captured["frame_count"] == int(duration * FPS)
    assert captured["pattern"].endswith("frame_%05d.jpg")
    assert captured["fps_arg"] == str(FPS)
    assert out == tmp_path / "s_line_visual.mp4"


def test_render_animated_chart_dispatches_to_correct_generator(tmp_path):
    """The orchestrator must call the chart_type's frame generator, not a fixed one."""
    called: list[str] = []

    def fake_ffmpeg(cmd, timeout=600):
        Path(cmd[-1]).write_bytes(b"")

    def wrap(name):
        from pipeline.composer import chart_anim as ca
        orig = getattr(ca, name)
        def wrapped(*a, **k):
            called.append(name)
            return orig(*a, **k)
        return wrapped

    with patch("pipeline.composer.chart_anim.run_ffmpeg", side_effect=fake_ffmpeg), \
         patch("pipeline.composer.chart_anim._animate_line_frame", side_effect=wrap("_animate_line_frame")), \
         patch("pipeline.composer.chart_anim._animate_bar_frame", side_effect=wrap("_animate_bar_frame")), \
         patch("pipeline.composer.chart_anim._animate_stat_frame", side_effect=wrap("_animate_stat_frame")):
        render_animated_chart(_BAR_VISUAL, duration_sec=3.0, width=W, height=H,
                               work_dir=tmp_path / "a", scene_id="s_bar", theme={})

    assert "_animate_bar_frame" in called
    assert "_animate_line_frame" not in called
    assert "_animate_stat_frame" not in called


def test_render_animated_chart_holds_final_frame_after_reveal(tmp_path):
    """Frames past reveal_duration_sec should be the progress=1.0 image."""
    saved_progresses: list[float] = []
    real_line = None

    from pipeline.composer import chart_anim as ca
    real_line = ca._animate_line_frame

    def capturing_line(progress, *a, **k):
        saved_progresses.append(progress)
        return real_line(progress, *a, **k)

    def fake_ffmpeg(cmd, timeout=600):
        Path(cmd[-1]).write_bytes(b"")

    with patch("pipeline.composer.chart_anim.run_ffmpeg", side_effect=fake_ffmpeg), \
         patch("pipeline.composer.chart_anim._animate_line_frame", side_effect=capturing_line):
        # 4s reveal, 6s total → 2s (60 frames) of hold tail at progress=1.0.
        visual = {**_LINE_VISUAL, "animate": {"enabled": True, "reveal_duration_sec": 4.0,
                                              "easing": "linear"}}
        render_animated_chart(visual, duration_sec=6.0, width=W, height=H,
                               work_dir=tmp_path, scene_id="s_h", theme={})

    # The last 60 progresses (hold tail) must all be 1.0 — orchestrator returned
    # the cached p=1.0 image rather than re-rendering. Equivalent: any progress
    # after the first 1.0 entry is 1.0.
    assert 1.0 in saved_progresses
    first_1 = saved_progresses.index(1.0)
    assert all(p == 1.0 for p in saved_progresses[first_1:])
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_chart_anim.py::test_render_animated_chart_writes_frame_sequence_and_calls_ffmpeg -v`

Expected: FAIL — `render_animated_chart` doesn't exist yet.

- [ ] **Step 3: Implement `render_animated_chart` in `chart_anim.py`**

Append to `src/pipeline/composer/chart_anim.py`:

```python
# ── Orchestrator ───────────────────────────────────────────────────────────────
def _animated_dispatcher(chart_type: str):
    if chart_type == "line":
        return _animate_line_frame
    if chart_type == "bar":
        return _animate_bar_frame
    if chart_type == "stat_big_number":
        return _animate_stat_frame
    raise ValueError(
        f"chart_type {chart_type!r} has no animated variant in Sprint 2 "
        f"(supported: line, bar, stat_big_number)"
    )


def render_animated_chart(
    visual: dict[str, Any],
    duration_sec: float,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
    theme: dict[str, Any] | None = None,
) -> Path:
    """Render an animated chart to ``{scene_id}_visual.mp4``.

    Mirrors ``composer/base.py:_camera_motion_to_video``: write a JPEG frame
    sequence to a tempdir, then run a single ffmpeg encode. The base background
    is built once via ``chart._build_background`` so the AI cache key is shared
    with the static path (no extra Flux call when the same scene was rendered
    static first).
    """
    from pipeline.composer.chart import (
        _BODY_BOTTOM_FRAC,
        _HEADER_GAP,
        _build_background,
        _draw_header,
        _palette,
    )
    from PIL import ImageDraw

    theme = theme or {}
    chart_type = visual["chart_type"]
    pal = _palette(theme)
    frame_fn = _animated_dispatcher(chart_type)
    easing = _resolve_easing(visual)
    reveal_sec = _resolve_reveal_duration(visual, duration_sec)

    total_frames = max(1, int(duration_sec * FPS))
    reveal_frames = max(1, int(reveal_sec * FPS))

    # Build the base background (paper or AI-bg) ONCE.
    bg = _build_background(visual, theme, width, height, work_dir, scene_id)
    draw = ImageDraw.Draw(bg)
    top = _draw_header(draw, visual, width, height, pal)

    # Persist a static reference PNG for debug / dashboard reuse.
    composite_png = work_dir / f"{scene_id}_chart.png"
    bg.save(composite_png)

    # Hold-tail optimization: render the p=1.0 frame ONCE and reuse it for all
    # frames after the reveal. Saves ~30% wall-time on a 6s scene with 4s reveal.
    final_frame = frame_fn(1.0, visual, bg, width, height, pal, top)

    output = work_dir / f"{scene_id}_visual.mp4"
    pix_fmt = "yuv420p" if (width % 2 == 0 and height % 2 == 0) else "yuv444p"

    with tempfile.TemporaryDirectory(prefix=f"chart-anim-{scene_id}-") as tmp:
        frame_dir = Path(tmp)
        for idx in range(total_frames):
            if idx >= reveal_frames - 1:
                frame = final_frame
            else:
                t = idx / max(1, reveal_frames - 1)
                progress = easing(t)
                frame = frame_fn(progress, visual, bg, width, height, pal, top)
            frame.save(
                frame_dir / f"frame_{idx:05d}.jpg",
                quality=95,
                subsampling=0,
                optimize=False,
            )

        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                str(FPS),
                "-i",
                str(frame_dir / "frame_%05d.jpg"),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "23",
                "-pix_fmt",
                pix_fmt,
                "-r",
                str(FPS),
                str(output),
            ]
        )

    if not output.exists():
        raise RuntimeError(
            f"chart_anim {scene_id}: ffmpeg returned but {output} is missing"
        )
    logger.info(
        "chart_anim.rendered",
        scene=scene_id, chart_type=chart_type,
        duration_sec=duration_sec, reveal_sec=reveal_sec,
        frames=total_frames,
    )
    return output
```

- [ ] **Step 4: Run the orchestrator tests**

Run: `uv run pytest tests/unit/test_chart_anim.py -v -k "render_animated_chart"`

Expected: ALL three pass (`test_render_animated_chart_writes_frame_sequence_and_calls_ffmpeg`, `test_render_animated_chart_dispatches_to_correct_generator`, `test_render_animated_chart_holds_final_frame_after_reveal`).

If `test_render_animated_chart_holds_final_frame_after_reveal` fails because `1.0 not in saved_progresses`: the orchestrator is gating on `idx >= reveal_frames - 1` but capturing only fresh calls. Verify the hold-tail branch is hit on the LAST reveal frame (the canonical 1.0 frame) and re-used for the tail.

- [ ] **Step 5: Run the full chart_anim test file**

Run: `uv run pytest tests/unit/test_chart_anim.py -v`

Expected: ALL pass (easing + helpers + 3 purity tests + 9 sampled-frame goldens + 3 orchestrator tests).

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/composer/chart_anim.py tests/unit/test_chart_anim.py
git commit -m "feat(chart-anim): orchestrator with frame loop + ffmpeg encode (mirrors _camera_motion_to_video)"
```

---

## Task 7: Wire animation into `render_chart` + duration-policy validation

**Files:**
- Modify: `src/pipeline/composer/chart.py`
- Modify: `tests/unit/test_chart.py` (validation tests)
- Modify: `tests/unit/test_chart_anim.py` (dispatch test through `render_chart`)

`render_chart` checks `visual.animate.enabled`; when true, delegates to `render_animated_chart` BEFORE doing any static drawing. Validation extends to the `animate` block: easing must be known, reveal_duration must fit, line markers must be in range (already in Task 1), and chart_types without an animated variant must be rejected.

- [ ] **Step 1: Write failing validation tests**

Append to `tests/unit/test_chart.py`:

```python
def test_validate_rejects_reveal_duration_over_limit():
    with pytest.raises(ValueError, match="reveal_duration_sec"):
        _validate_chart(
            _v(chart_type="line", animate={"enabled": True, "reveal_duration_sec": 6.0},
                data={"points": [{"x": 1, "y": 1}, {"x": 2, "y": 2}]}),
            "s1", duration_sec=5.0,
        )


def test_validate_rejects_unknown_easing():
    with pytest.raises(ValueError, match="unknown easing"):
        _validate_chart(
            _v(chart_type="line",
                animate={"enabled": True, "easing": "bounce"},
                data={"points": [{"x": 1, "y": 1}, {"x": 2, "y": 2}]}),
            "s1", duration_sec=10.0,
        )


def test_validate_rejects_animated_variant_not_implemented():
    with pytest.raises(ValueError, match="animated variant"):
        _validate_chart(
            _v(chart_type="proportion_blocks",
                animate={"enabled": True},
                data={"ratio": 0.5}),
            "s1", duration_sec=5.0,
        )


def test_validate_passes_static_without_animate_block():
    _validate_chart(
        _v(chart_type="line",
            data={"points": [{"x": 1, "y": 1}, {"x": 2, "y": 2}]}),
        "s1",
    )
```

These tests pass an optional `duration_sec` kwarg to `_validate_chart`. The Sprint-1 signature didn't have it; this task extends it (callers that don't care can omit it — animate-block checks are skipped when `duration_sec` is None).

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_chart.py -k "reveal_duration_over_limit or unknown_easing or animated_variant_not_implemented or passes_static" -v`

Expected: FAIL — `_validate_chart` doesn't accept `duration_sec` yet and doesn't check the animate block.

- [ ] **Step 3: Extend `_validate_chart` signature + body**

In `src/pipeline/composer/chart.py`:

Change the function signature from:

```python
def _validate_chart(visual: dict[str, Any], scene_id: str) -> None:
```

to:

```python
def _validate_chart(
    visual: dict[str, Any],
    scene_id: str,
    duration_sec: float | None = None,
) -> None:
```

At the END of the function (after all existing chart_type-specific checks), append:

```python
    animate = visual.get("animate") or {}
    if animate.get("enabled"):
        # 1. chart_type must have an animated variant in this sprint.
        if chart_type not in {"line", "bar", "stat_big_number"}:
            raise ValueError(
                f"chart {scene_id}: chart_type={chart_type!r} has no animated "
                f"variant (supported: line, bar, stat_big_number); set "
                f"animate.enabled=false or pick a supported chart_type"
            )
        # 2. easing must be known.
        easing_name = animate.get("easing", "ease_out_cubic")
        from pipeline.composer.chart_anim import EASING
        if easing_name not in EASING:
            raise ValueError(
                f"chart {scene_id}: unknown easing {easing_name!r}; use one of "
                f"{sorted(EASING)}"
            )
        # 3. reveal_duration_sec must fit within scene duration - hold tail.
        if duration_sec is not None:
            from pipeline.composer.chart_anim import HOLD_TAIL_MIN_SEC
            reveal = animate.get("reveal_duration_sec")
            if reveal is not None:
                if float(reveal) > duration_sec - HOLD_TAIL_MIN_SEC:
                    raise ValueError(
                        f"chart {scene_id}: reveal_duration_sec={reveal} > "
                        f"duration_sec({duration_sec}) - hold_tail({HOLD_TAIL_MIN_SEC}); "
                        f"shorten the reveal — animation cannot extend the scene "
                        f"(two-axes rule: arsenal items do not add runtime)"
                    )
```

Also update the call site inside `render_chart` to pass `duration_sec`:

Find the line:

```python
    _validate_chart(visual, scene_id)
```

Change to:

```python
    _validate_chart(visual, scene_id, duration_sec=duration_sec)
```

- [ ] **Step 4: Add animation dispatch to `render_chart`**

In `src/pipeline/composer/chart.py`, inside `render_chart`, AFTER the validation call and BEFORE `_build_background`, add the early-return:

```python
    if (visual.get("animate") or {}).get("enabled"):
        from pipeline.composer.chart_anim import render_animated_chart
        return render_animated_chart(
            visual, duration_sec, width, height, work_dir, scene_id, theme
        )
```

The function body below this dispatch handles the static path unchanged.

- [ ] **Step 5: Run the validation tests**

Run: `uv run pytest tests/unit/test_chart.py -k "reveal_duration_over_limit or unknown_easing or animated_variant_not_implemented or passes_static" -v`

Expected: PASS.

- [ ] **Step 6: Add the through-render_chart dispatch test**

Append to `tests/unit/test_chart_anim.py`:

```python
def test_render_chart_dispatches_to_animated_when_enabled(tmp_path):
    """Confirm the chart.render_chart entry point routes animated visuals to
    the orchestrator (so the storyboard doesn't need a separate visual type)."""
    from pipeline.composer.chart import render_chart

    def fake_ffmpeg(cmd, timeout=600):
        Path(cmd[-1]).write_bytes(b"")

    with patch("pipeline.composer.chart_anim.run_ffmpeg",
               side_effect=fake_ffmpeg) as ff:
        out = render_chart(_LINE_VISUAL, 4.0, W, H, tmp_path, "s_dispatch", theme={})

    assert ff.call_count == 1
    assert out == tmp_path / "s_dispatch_visual.mp4"


def test_render_chart_static_path_unchanged_when_animate_disabled(tmp_path):
    """When animate.enabled is false (or absent), the static Sprint-1 path runs."""
    from pipeline.composer.chart import render_chart

    static_visual = {**_LINE_VISUAL}
    static_visual.pop("animate", None)
    with patch("pipeline.composer.chart_anim.run_ffmpeg") as ff_anim, \
         patch("pipeline.composer.chart.image_to_video") as itv:
        itv.side_effect = lambda png, out, *a, **k: out
        render_chart(static_visual, 4.0, W, H, tmp_path, "s_static", theme={})

    assert ff_anim.call_count == 0, "animated orchestrator must not run for static"
    assert itv.call_count == 1, "static path must call image_to_video"
```

- [ ] **Step 7: Run the dispatch tests + the full chart suites**

Run: `uv run pytest tests/unit/test_chart.py tests/unit/test_chart_anim.py -v`

Expected: ALL pass.

- [ ] **Step 8: Run ruff + mypy on the touched files**

Run: `uv run ruff check src/pipeline/composer/chart.py src/pipeline/composer/chart_anim.py tests/unit/test_chart.py tests/unit/test_chart_anim.py && uv run mypy src/pipeline/composer/chart.py src/pipeline/composer/chart_anim.py`

Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add src/pipeline/composer/chart.py src/pipeline/composer/chart_anim.py tests/unit/test_chart.py tests/unit/test_chart_anim.py
git commit -m "feat(chart): wire animation dispatch + enforce reveal duration <= scene - hold tail (two-axes rule)"
```

---

## Task 8: Director taxonomy — `line` + `animate` worked examples

**Files:**
- Modify: `src/pipeline/stages/direct.py`

The director model picks visual types and chart_types by example. Sprint 1 gave it per-chart_type worked examples; this task adds the `line` example with the baby-walker decline-curve data AND a separate "ANIMATION" subsection showing the `animate` block.

- [ ] **Step 1: Locate the chart block**

Open `src/pipeline/stages/direct.py` and find the line:

```python
- chart: {{"type": "chart", "chart_type": "stat_big_number|proportion_blocks|timeline|bar|comparison", "title": "...", "data": {{...}}, "source_credit": "optional"}}
```

(currently around line 224).

- [ ] **Step 2: Update the chart_type enum string + add line worked example + animation subsection**

Replace the chart block (the line above plus its per-type worked-example block ending with the rule about `stat_big_number value <= 8 chars`) with:

```python
- chart: {{"type": "chart", "chart_type": "stat_big_number|proportion_blocks|timeline|bar|comparison|line", "title": "...", "data": {{...}}, "source_credit": "optional"}}
  Use when the scene's CORE message IS a number, a proportion, a sequence of years, a ranking, a two-way contrast, or a TREND OVER TIME.
  If the scene names a REAL datapoint, PREFER chart over slide+text — a stat deserves a real visualization, not a bullet.
  Copy the per-type data shape EXACTLY (the schema differs per chart_type):
  - stat_big_number: {{"chart_type": "stat_big_number", "title": "Cumulative injuries", "data": {{"value": "230,676", "unit": "children", "context": "1990-2014"}}}}
  - proportion_blocks: {{"chart_type": "proportion_blocks", "title": "Where falls happen", "data": {{"label": "74% stair falls", "ratio": 0.74, "secondary_label": "26% other", "secondary_ratio": 0.26}}}}
  - timeline: {{"chart_type": "timeline", "title": "Two decades", "data": [{{"year": 1990, "label": "20,650 ER visits"}}, {{"year": 2014, "label": "230k cumulative"}}]}}
  - bar: {{"chart_type": "bar", "title": "Injury mechanisms", "data": {{"x": ["stair falls", "tip-overs", "burns"], "y": [74, 13, 6], "y_unit": "%"}}}}
  - comparison: {{"chart_type": "comparison", "title": "Speed vs reaction", "data": {{"left": {{"label": "Sit-in walker", "value": "3 ft/s"}}, "right": {{"label": "Adult reaction", "value": "0.7 s"}}}}}}
  - line: {{"chart_type": "line", "title": "US ER visits per year", "data": {{"points": [{{"x": 1990, "y": 20650}}, {{"x": 1999, "y": 8800}}, {{"x": 2014, "y": 2001}}], "markers": [{{"x": 1997, "label": "ASTM F977"}}, {{"x": 2010, "label": "CPSC mandatory"}}]}}}}
    USE `line` (not `timeline`) when the SCENE'S CORE IS the trend itself — a series of numeric Y values per X (typically year), with optional event markers. USE `timeline` for unconnected dated events with no quantitative axis. The decline of an injury rate, a price curve, a search-interest line: those are `line`. A sequence of "1990 → 2001 → 2014" event labels with no numbers: that's `timeline`.
  RULE: stat_big_number value must be <= 8 chars. Charts carry their own title — do NOT also add a text overlay.

  ANIMATION (optional, for line / bar / stat_big_number only): add an `animate` block on the visual:
    "animate": {{"enabled": true, "reveal_duration_sec": 4.0, "easing": "ease_out_cubic"}}
  - `reveal_duration_sec` MUST be <= scene narration duration - 0.5s (the renderer holds the final frame for the last 0.5s so the chart settles; longer reveals are rejected at compose time). If omitted, defaults to min(narration_sec * 0.6, 5.0).
  - `easing` is "ease_out_cubic" (default — fast arrival, settle) or "linear".
  - Use animation when the SCENE'S NARRATION ITSELF builds momentum to the data ("By 2014, ER visits dropped to about 2,000 — ninety percent below the 1990 peak" → animated line draws the fall as the narration delivers the verdict). A static chart is fine when the scene presents the number without dramatic arrival.
  - Animation is a VISUAL-QUALITY lift only; it does NOT extend the scene. Pick scene narration_est_sec based on the line, not on how long the chart "should" play.
```

- [ ] **Step 3: Confirm director smoke tests still pass**

The director has snapshot tests under `tests/director/` and friends. Run:

Run: `uv run pytest tests/director/ tests/unit/test_direct.py -v 2>&1 | tail -50`

Expected: all pass. If a snapshot fails because the prompt changed, that's expected — inspect the diff, confirm it's the expected addition, and update with `UPDATE_GOLDENS=1` if the test family uses that env var, otherwise update the snapshot per the test's local convention.

(NB: this step assumes there's no snapshot of the literal prompt string in `tests/`. If there is and it fails, the diff is the chart-block edit — update the snapshot. If there isn't, the prompt is generative and no test cares.)

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/stages/direct.py
git commit -m "feat(direct): add 'line' chart_type + animate block to taxonomy"
```

---

## Task 9: End-to-end — baby-walker decline-curve wiring + final verification

**Files:**
- Modify: `output/projects/20260504-115232-baby-walker-story/storyboard.json` (one scene)

This is the acceptance vehicle. The baby-walker storyboard already has a "did it work?" beat (currently rendering as a slide / placeholder); wire it to the new animated `line` chart with the producer-greenlit datapoints + markers, render the scene, and visually confirm the curve draws and markers appear in time.

- [ ] **Step 1: Locate the decline-curve scene in the storyboard**

Run: `grep -n "1990 peak\|−57%\|s_decline\|did it work\|US ER visits" output/projects/20260504-115232-baby-walker-story/storyboard.json | head -10`

The scene that currently text-renders the trend (likely "1990 peak: ~20,650 / 1999: ~8,800 / −57%") is the merge target. The wiki mandate says ONE merged curve replaces the two adjacent table-style scenes. Identify the scene id of the surviving merged scene (the one with the longer narration that talks about the regulation arc + the 90% drop).

- [ ] **Step 2: Edit the scene's `visual` block in `storyboard.json`**

Replace the existing `visual` of the target scene with:

```json
{
  "type": "chart",
  "chart_type": "line",
  "title": "US ER visits per year",
  "source_credit": "AAP, 1990-2014",
  "ai_background": true,
  "background_prompt": "aged paper texture, soft sepia stains, faint grid",
  "animate": {
    "enabled": true,
    "reveal_duration_sec": 5.0,
    "easing": "ease_out_cubic"
  },
  "data": {
    "points": [
      {"x": 1990, "y": 20650},
      {"x": 1999, "y": 8800},
      {"x": 2007, "y": 3200},
      {"x": 2014, "y": 2001}
    ],
    "markers": [
      {"x": 1982, "label": "First medical study"},
      {"x": 1995, "label": "Voluntary standard"},
      {"x": 1997, "label": "ASTM F977"},
      {"x": 2001, "label": "AAP ban call"},
      {"x": 2004, "label": "Canada bans"},
      {"x": 2010, "label": "CPSC mandatory"}
    ],
    "x_axis": "year",
    "y_axis": "ER visits"
  },
  "confidence": "high",
  "rationale": "trend-over-time data with regulation events as causal markers; line+animate carries the cause-and-effect read across the narration"
}
```

Note: `reveal_duration_sec` MUST be `<= narration_est_sec - 0.5s`. If the target scene's `narration_est_sec` is < 5.5s, lower `reveal_duration_sec` accordingly (e.g. narration_est_sec=6 → reveal=4.5).

- [ ] **Step 3: Clear the stale cached scene render**

Run:

```bash
rm -f output/projects/20260504-115232-baby-walker-story/compose/scenes/<the-scene-id>_visual.mp4 \
      output/projects/20260504-115232-baby-walker-story/compose/scenes/<the-scene-id>_chart.png
```

Substitute the actual scene id you edited.

- [ ] **Step 4: Rescene the single scene**

Run:

```bash
uv run pipeline compose rescene --project-id 20260504-115232-baby-walker-story --scene <the-scene-id>
```

Expected: the rescene runs without error and produces a fresh `_visual.mp4` for that scene.

- [ ] **Step 5: Sample a few frames from the rendered mp4 to visually confirm**

Run:

```bash
ffmpeg -y -i output/projects/20260504-115232-baby-walker-story/compose/scenes/<the-scene-id>_visual.mp4 \
       -vf "fps=2" tmp/decline-curve-frame-%03d.jpg
```

Open `tmp/decline-curve-frame-001.jpg` (early), `tmp/decline-curve-frame-005.jpg` (mid-reveal), `tmp/decline-curve-frame-010.jpg` (later). Verify by eye:
- Frame 1: header visible, axes drawn, no curve yet (or just starting).
- Frame 5: curve drawn left-to-right past 1999; early markers visible; later markers (Canada bans / CPSC mandatory) NOT yet visible.
- Frame 10: full curve, all six markers visible, layout matches `tests/fixtures/chart_anim/golden/line_p10.png` in spirit (AI background is real here, not flat paper).

If any frame is wrong — fix the renderer or the storyboard data and rescene.

- [ ] **Step 6: Run the full pytest suite, ruff, and mypy**

Run:

```bash
uv run pytest -q
uv run ruff check src/ tests/
uv run mypy src/
```

Expected:
- pytest: ALL pass (Sprint 1's 963 + the new chart/anim tests; total ~980+).
- ruff: clean.
- mypy: clean.

If anything fails: STOP and report. Do not bypass with --no-verify or pytest skips.

- [ ] **Step 7: Update ROADMAP + EM memory (ship deltas)**

Apply the roadmap deltas from the EM proposal (in the same commit as the storyboard wiring is OK; the roadmap and memory update is the official "shipped" record):

In `docs/ROADMAP.md`:
- Bump "Last updated" to today.
- "Current arsenal (baseline, ...)" → update the visual-types bullet to: `chart` (6 static chart_types, 3 with animated reveal — Sprint 1 + 2 🟢). Add a `Reveals:` bullet: `line-draw / bar-grow / count-up (Sprint 2 🟢)`.
- E2 status: 🔵 → 🟢 *v1 shipped (Sprint 2)*. Append: "v1 covers animated reveal for `line` / `bar` / `stat_big_number`; `proportion_blocks` / `timeline` / `comparison` reveals + Ken Burns + true page-turn remain in epic."
- Sprint 2 backlog entry: status → 🟢 *shipped 2026-MM-DD*. Body unchanged.
- Promote Sprint 3 to `▶ next` (Style Manifest Slices 1–2).

In `.agent-memory/engineering-manager/arsenal-state.md`:
- Move "Programmatic animation: animated chart reveal" from 🔵 → 🟢 (partial — `line` / `bar` / `stat_big_number` only; mark remaining variants explicitly).
- Add `chart_type: line` to the chart row and note "animated reveal supported on line/bar/stat_big_number; reveal_duration_sec validated <= scene duration − 0.5s".
- Bump "As of" date.
- Demand pressure: drop "Animated decline-curve" from top pressure. New top pressure is whichever item Sprint 3 addresses (Style Manifest / `anchor_image` no-op).

In `.agent-memory/engineering-manager/standards.md`:
- Promote one Sprint-2 lesson into the standards list:

```
**Lessons from Sprint 2 (animation):**
- **Frame generators are PURE.** Contract: `(progress, visual, base_bg, w, h,
  palette) → PIL.Image` — no disk, no network, no random. The orchestrator owns
  all I/O. This is what makes sampled-frame goldens viable; without purity you
  fall back to mp4 binary comparison which is flaky across ffmpeg builds.
- **Two-axes guardrails belong in code.** A reveal-duration policy stated only
  in docs erodes; one enforced by the validator (`reveal_duration_sec <=
  duration_sec − 0.5s` raises) survives pressure. New animation-adjacent sprints
  must check whether their own runtime-vs-quality tradeoff has a code-level fence.
- **ffmpeg invocation is duplicated, not abstracted, until a 3rd caller appears.**
  `_camera_motion_to_video` and `render_animated_chart` both call `run_ffmpeg`
  with the same JPEG-sequence arg list; a shared helper waits for the 3rd
  caller (premature abstraction is the bigger risk).
```

In `.agent-memory/engineering-manager/sprint-log.md`:
- Append a `## Sprint 2 — 2026-MM-DD — SHIPPED` entry summarizing what landed (the chart_anim module, the `line` chart_type, the orchestrator, the 9 sampled-frame goldens + 3 purity tests + ffmpeg-mock + duration-policy validator, the baby-walker scene wiring) and any standards promoted.
- Set "Next:" to Sprint 3 (Style Manifest Slices 1–2 / E4).

- [ ] **Step 8: Final commit**

```bash
git add output/projects/20260504-115232-baby-walker-story/storyboard.json docs/ROADMAP.md .agent-memory/engineering-manager/arsenal-state.md .agent-memory/engineering-manager/standards.md .agent-memory/engineering-manager/sprint-log.md
git commit -m "feat(chart-anim): ship Sprint 2 — animated reveal v1 + baby-walker decline-curve

Animated chart_anim v1 with three variants (line/bar/stat_big_number), new
static 'line' chart_type substrate, baby-walker merged decline-curve scene
wired to animated line + six regulation markers. ROADMAP + EM memory moved
E2 to v1-shipped; Sprint 3 (Style Manifest) becomes ▶ next.

Visual-quality axis only — reveal_duration_sec validated <= scene duration
− 0.5s hold tail. No runtime added."
```

- [ ] **Step 9: Sanity-check the final branch state**

Run:

```bash
git log --oneline master..HEAD
git status
```

Expected:
- ~9 commits on the branch, one per Task plus the ship commit, with feat-prefixed messages.
- Clean status; only the tmp/ files that existed before Task 1 remain untracked (no leftover render artifacts from manual scene rescene).

---

## Acceptance criteria (matches the Sprint 2 proposal)

1. `uv run pytest tests/unit/test_chart_anim.py` — all green (purity + 9 sampled-frame goldens + ffmpeg-mock + dispatch tests).
2. `uv run pytest` — full suite green (~980+ tests).
3. `uv run ruff check src/ tests/` — clean.
4. `uv run mypy src/` — clean.
5. Static `line` golden renders for the baby-walker data; visually inspected.
6. Animated `line` reveal — re-rendering the baby-walker decline-curve scene produces an mp4 where the curve draws left-to-right and markers appear in time.
7. Animated `bar` and `stat_big_number` — generator goldens at p=0/0.5/1.0 confirm staggered grow and count-up.
8. Duration policy enforced — `animate.reveal_duration_sec > duration_sec − 0.5s` raises `ValueError` with a fix hint.
9. Director sees `line` + `animate` examples in the taxonomy prompt.
10. No silent fallback — provider failure still drops to flat-paper background; frame-generation failure raises.
11. ROADMAP + EM memory updated; Sprint 3 promoted to ▶ next.

---

## Self-review checklist (DO NOT delete from this plan)

Before declaring done, the executing engineer (or subagent driver) re-reads the plan and confirms:

- [ ] Every spec section in the Sprint 2 proposal has a Task touching it (Scope IN: `chart_anim.py` ✓, `line` chart_type ✓, animate block ✓, three animated variants ✓, duration policy ✓, easing helpers ✓, director taxonomy ✓, tests inc. purity + ffmpeg-mock + 9 sampled goldens ✓, baby-walker wiring ✓).
- [ ] No placeholders (`TBD`, `// implement`, `# similar to above`) remain.
- [ ] The two-axes rule is enforced in code, not just docs (Task 7 Step 3 validator).
- [ ] `_animate_*_frame` signatures match across Tasks 3/4/5: `(progress, visual, base_bg, width, height, palette, top)`.
- [ ] `render_animated_chart` is called from `render_chart` in Task 7 (not built into `chart_anim.py` in isolation).
- [ ] The static `line` (Task 1) and animated `line` (Task 3) data shape match — same `points` / `markers` schema.
- [ ] Determinism + visual eyeball steps are present for EVERY golden file (no fixture is committed unseen).
