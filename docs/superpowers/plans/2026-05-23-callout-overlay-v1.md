# Callout Overlay Primitive v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a pure, manifest-registered `callout` overlay primitive that places short labels above a plot with collision-avoidance (vertical dodge + leader lines), and route BOTH the static `chart._render_line` and the animated `chart_anim._animate_line_frame` marker labels through it — fixing the baby-walker s21 decline-curve marker-label overlap.

**Architecture:** `composer/callout.py` exposes three layers on one geometry core so production and golden tests cannot diverge:
- `place_callouts(...)` — **pure geometry**: sorts labels by x, dodges overlapping ones up to the next free row (capped by a row budget and by available header space), returns `PlacedCallout`s; raises `CalloutPlacementError` when the budget is exhausted.
- `_draw_placed_callouts(draw, placed, ...)` — draws labels + leader lines onto a caller-supplied `ImageDraw` (used by the two chart call sites, which own a shared `draw`).
- `render_callouts(callouts, base_image, ...) -> Image` — copies a base image, runs `place_callouts` + `_draw_placed_callouts`, returns the new image. **This is primarily the golden-test surface** (the chart call sites have a `draw`, not an image handle, so they call `place_callouts` + `_draw_placed_callouts` directly — do NOT refactor them to consume `render_callouts`).

Two call sites delegate to the core: `chart._render_line` (static) and `chart_anim._animate_line_frame` (animated — the path that actually renders s21). The animated path's wipe rectangle is widened to cover the taller multi-row label stack. The primitive registers as a `"overlay"`-kind Style Manifest element (aggregate-by-type). Separately, the silent `apply_overlay` fallback in `compose.py` is converted to a loud `SceneRenderError`.

**Tech Stack:** Python 3.11, Pillow (PIL), pytest, ruff, mypy. No new dependencies, no API/network calls (pure Pillow over already-rendered frames → $0 incremental).

**Scope discovery (correction to the EM proposal):** the proposal pointed only at the static `chart.py:529-539`. The observed bug (s21) is *animated*, rendered by `chart_anim.py:224-240`, which carries an identical 2-row stagger. Fixing only the static path would leave the named bug unfixed, so v1 wires BOTH paths through the shared primitive (the intended DRY win). Flagged to Tim on completion.

**Decisions locked (Tim's open-question answers + advisor pin-downs):**
1. Static v1 (no animated entrance — placement only). 2. Vertical dodge to next free row + leader lines. 3. Include the `compose.py` loud-failure swap. 4. Manifest grain = aggregate-by-type. 5. Row-budget exhaustion → `place_callouts` raises → render path surfaces `SceneRenderError` (precise geometric fence at render time; a validate-time density *mirror* is deferred — see Scope OUT). 6. Header collision avoided by capping `max_rows` so the topmost label stays at/below `top_limit`. 7. `StyleKind` gains `"overlay"`. 8. Compose loud-failure test triggers by patching `apply_overlay` to raise (mirrors `test_composer_base.py:48`).

**Scope OUT (deferred):**
- Animated callout entrance (fade/slide-in, `progress`-parameterized wrapper + `entrance_duration ≤ scene_duration − tail` fence) → **E3 v2**.
- Lower-thirds / source-credit bars; CapCut word-by-word subtitles → **E3 v2+**.
- Retrofitting the 6 existing ffmpeg `overlay.py` types into the primitive → deferred (v1 only adds `callout` and wires the two chart line paths).
- Director taxonomy worked-example for a director-emitted `callout` → deferred (v1 derives callouts internally from chart markers).
- Validate-time marker-density mirror in `validate_chart_visual` → deferred: an accurate fit check needs render geometry (font metrics + pixel width) the validator does not have; a magic-number guess would be worse than the precise render-time raise. Named here so it is not forgotten.

---

## File Structure

- **Create** `src/pipeline/composer/callout.py` — the primitive (geometry core + draw helper + image wrapper). One responsibility: collision-free label placement + drawing.
- **Create** `tests/unit/test_callout.py` — geometry unit tests, determinism test, 4 placement goldens.
- **Create** `tests/fixtures/callout/golden/*.png` — 4 reference PNGs (gated behind `UPDATE_GOLDENS=1`, eyeballed).
- **Modify** `src/pipeline/composer/chart.py:528-539` (`_render_line` marker-label loop) — delegate to the primitive.
- **Modify** `src/pipeline/composer/chart_anim.py` (`_animate_line_frame` marker-label loop ~224-240 + wipe rectangle ~142) — delegate to the primitive; widen wipe.
- **Modify** `tests/fixtures/chart/golden/line.png` — regenerate (static path changed).
- **Modify** `tests/fixtures/chart_anim/golden/line_p00.png`, `line_p05.png`, `line_p10.png` — regenerate (animated path + base changed).
- **Modify** `src/pipeline/style/manifest.py` — add `"overlay"` to `StyleKind`; append a `callout` element when any scene is a line chart with markers.
- **Modify** `tests/unit/test_style_manifest.py` — assert the `callout` element is built.
- **Modify** `src/pipeline/stages/compose.py:1050-1063` — convert the silent overlay `except → logger.warning` into a loud `SceneRenderError`.
- **Modify** `tests/unit/test_compose_v2.py` — assert overlay failure now raises `SceneRenderError`.

---

### Task 1: Callout geometry core (`place_callouts`)

**Files:**
- Create: `src/pipeline/composer/callout.py`
- Test: `tests/unit/test_callout.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_callout.py
import os
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

from pipeline.composer.callout import (
    BASE_LABEL_GAP,
    DEFAULT_MAX_ROWS,
    ROW_HEIGHT,
    Callout,
    CalloutPlacementError,
    PlacedCallout,
    place_callouts,
)

# Deterministic monospace-ish measure: 10 px per char. Keeps geometry tests
# independent of installed fonts.
def _measure(label: str) -> int:
    return 10 * len(label)


_GEO = dict(left=100, right=1180, body_top=300, top_limit=120)


def test_single_callout_sits_on_bottom_row_no_leader():
    placed = place_callouts([Callout(x=600, label="1990")], measure=_measure, **_GEO)
    assert len(placed) == 1
    p = placed[0]
    assert p.row == 0
    assert p.needs_leader is False
    # bottom row top-y = body_top - BASE_LABEL_GAP - ROW_HEIGHT
    assert p.y == _GEO["body_top"] - BASE_LABEL_GAP - ROW_HEIGHT
    # centered on its anchor (width = 40), clamped within [left, right-width]
    assert p.x == 600 - 40 // 2
    assert p.anchor_x == 600


def test_two_overlapping_callouts_dodge_to_second_row():
    # Two anchors 20px apart with 40px labels overlap horizontally -> second dodges up.
    placed = place_callouts(
        [Callout(x=600, label="1995"), Callout(x=620, label="1997")],
        measure=_measure, **_GEO,
    )
    rows = sorted(p.row for p in placed)
    assert rows == [0, 1]
    dodged = next(p for p in placed if p.row == 1)
    assert dodged.needs_leader is True
    assert dodged.y == _GEO["body_top"] - BASE_LABEL_GAP - 2 * ROW_HEIGHT


def test_far_apart_callouts_both_stay_bottom_row():
    placed = place_callouts(
        [Callout(x=200, label="1990"), Callout(x=1000, label="2014")],
        measure=_measure, **_GEO,
    )
    assert {p.row for p in placed} == {0}
    assert all(p.needs_leader is False for p in placed)


def test_label_clamped_within_horizontal_bounds():
    # Anchor at the far right; label must not run past `right`.
    placed = place_callouts([Callout(x=1180, label="VOLUNTARY")], measure=_measure, **_GEO)
    p = placed[0]
    assert p.x + _measure("VOLUNTARY") <= _GEO["right"]
    assert p.x >= _GEO["left"]


def test_budget_exhaustion_raises():
    # 6 labels stacked on the same x cannot fit in DEFAULT_MAX_ROWS rows.
    callouts = [Callout(x=600, label=f"L{i}") for i in range(DEFAULT_MAX_ROWS + 3)]
    with pytest.raises(CalloutPlacementError, match="within"):
        place_callouts(callouts, measure=_measure, **_GEO)


def test_max_rows_capped_by_header_space():
    # top_limit close to body_top leaves room for only 1 row; 2 stacked anchors -> raise.
    tight = dict(left=100, right=1180, body_top=300, top_limit=300 - BASE_LABEL_GAP - ROW_HEIGHT)
    with pytest.raises(CalloutPlacementError):
        place_callouts(
            [Callout(x=600, label="1995"), Callout(x=610, label="1997")],
            measure=_measure, **tight,
        )


def test_results_sorted_and_stable():
    a = place_callouts([Callout(x=300, label="A"), Callout(x=305, label="B")],
                       measure=_measure, **_GEO)
    b = place_callouts([Callout(x=305, label="B"), Callout(x=300, label="A")],
                       measure=_measure, **_GEO)
    assert [(p.label, p.row, p.x, p.y) for p in a] == [(p.label, p.row, p.x, p.y) for p in b]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tim-huang/content-creation && uv run pytest tests/unit/test_callout.py -q`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'pipeline.composer.callout'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/pipeline/composer/callout.py
"""Callout overlay primitive: collision-free placement of short labels above a
plot, with leader lines when a label is dodged off its anchor row.

Pure geometry + drawing helpers (no I/O, no network, no randomness) so output
is deterministic and golden-testable — the same contract as
``composer/chart_anim.py`` frame generators. Two chart call sites consume it:
``chart._render_line`` (static) and ``chart_anim._animate_line_frame``
(animated); both delegate marker-label placement here so they cannot drift.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ROW_HEIGHT = 22          # vertical pitch between dodge rows (px)
BASE_LABEL_GAP = 6       # gap between body_top and the bottom row's top-y
DEFAULT_MAX_ROWS = 3     # vertical dodge budget (placement, NOT runtime — two-axes)
LABEL_PAD = 6            # horizontal padding around a label for overlap tests


class CalloutPlacementError(ValueError):
    """Raised when callouts cannot be placed within the available row budget."""


@dataclass
class Callout:
    x: int          # anchor x in px (the marker column)
    label: str


@dataclass
class PlacedCallout:
    x: int          # clamped label left-x
    y: int          # label top-y
    label: str
    anchor_x: int   # original marker x (leader-line origin x)
    width: int      # measured label width (px)
    row: int        # 0 = bottom row (closest to the plot), higher = stacked upward
    needs_leader: bool


def _row_top_y(body_top: int, row: int) -> int:
    return body_top - BASE_LABEL_GAP - (row + 1) * ROW_HEIGHT


def place_callouts(
    callouts: list[Callout],
    *,
    measure: Callable[[str], int],
    left: int,
    right: int,
    body_top: int,
    top_limit: int,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> list[PlacedCallout]:
    """Place labels above ``body_top`` without horizontal overlap.

    Labels stack upward in rows of ``ROW_HEIGHT``. Each label is centered on its
    anchor x, clamped to ``[left, right]``. A label is assigned the LOWEST row
    whose horizontal span (± ``LABEL_PAD``) is free; the bottom row (0) needs no
    leader line, higher rows do. ``max_rows`` is capped so the topmost row's
    top-y never rises above ``top_limit`` (keeps labels out of the chart title).
    Raises ``CalloutPlacementError`` if a label cannot be placed.
    """
    # Cap the row budget by available header space above body_top.
    space = body_top - BASE_LABEL_GAP - top_limit
    space_rows = max(1, space // ROW_HEIGHT)
    budget = max(1, min(max_rows, space_rows))

    occupied: dict[int, list[tuple[int, int]]] = {r: [] for r in range(budget)}
    placed: list[PlacedCallout] = []

    for c in sorted(callouts, key=lambda c: (c.x, c.label)):
        w = measure(c.label)
        x_left = max(left, min(right - w, c.x - w // 2))
        span = (x_left - LABEL_PAD, x_left + w + LABEL_PAD)
        for row in range(budget):
            if all(span[1] <= s or span[0] >= e for (s, e) in occupied[row]):
                occupied[row].append(span)
                placed.append(
                    PlacedCallout(
                        x=x_left,
                        y=_row_top_y(body_top, row),
                        label=c.label,
                        anchor_x=c.x,
                        width=w,
                        row=row,
                        needs_leader=row != 0,
                    )
                )
                break
        else:
            raise CalloutPlacementError(
                f"cannot place callout {c.label!r} within {budget} rows "
                f"(reduce marker count or widen the chart)"
            )

    return placed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tim-huang/content-creation && uv run pytest tests/unit/test_callout.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/composer/callout.py tests/unit/test_callout.py
git commit -m "feat(callout): pure place_callouts geometry core with vertical dodge"
```

---

### Task 2: Draw helper + image wrapper + determinism/golden tests

**Files:**
- Modify: `src/pipeline/composer/callout.py`
- Test: `tests/unit/test_callout.py`
- Create: `tests/fixtures/callout/golden/*.png`

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_callout.py`)

```python
from pipeline.composer.callout import render_callouts  # add to imports at top

_GOLDEN = Path(__file__).parent.parent / "fixtures" / "callout" / "golden"
W, H = 1280, 720
_INK = (38, 30, 22)
_MUTED = (120, 104, 86)
_PAPER = (244, 236, 222)


def _base():
    return Image.new("RGB", (W, H), _PAPER)


def _render(callouts):
    return render_callouts(
        callouts,
        _base(),
        left=128, right=1190, body_top=216, top_limit=90,
        leader_from_y=216, ink=_INK, muted=_MUTED, font_size=18,
    )


def _assert_golden(image, name: str) -> None:
    golden = _GOLDEN / f"{name}.png"
    if os.environ.get("UPDATE_GOLDENS"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        image.save(golden)
        return
    assert golden.exists(), f"missing golden {golden}; run with UPDATE_GOLDENS=1"
    diff = ImageChops.difference(image, Image.open(golden).convert("RGB"))
    assert diff.getbbox() is None, f"{name} render drifted from golden"


def test_render_callouts_is_deterministic():
    cs = [Callout(x=600, label="1995"), Callout(x=620, label="1997")]
    a = _render(cs)
    b = _render(cs)
    assert ImageChops.difference(a, b).getbbox() is None


def test_golden_one_marker():
    _assert_golden(_render([Callout(x=600, label="1990 data starts")]), "one_marker")


def test_golden_two_close():
    _assert_golden(
        _render([Callout(x=600, label="1995 ban"), Callout(x=640, label="1997 std")]),
        "two_close",
    )


def test_golden_three_close():
    _assert_golden(
        _render([
            Callout(x=600, label="1995"), Callout(x=636, label="1997"),
            Callout(x=672, label="2001"),
        ]),
        "three_close",
    )


def test_golden_tight_cluster():
    # The s21 case: 6 regulation markers, several <5yr apart on a long span.
    _assert_golden(
        _render([
            Callout(x=300, label="1982 study"), Callout(x=560, label="1995 ban"),
            Callout(x=600, label="1997 std"), Callout(x=700, label="2001 voluntary"),
            Callout(x=760, label="2004 ASTM"), Callout(x=900, label="2010 mandatory"),
        ]),
        "tight_cluster",
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_callout.py -q`
Expected: FAIL — `ImportError: cannot import name 'render_callouts'`.

- [ ] **Step 3: Write minimal implementation** (append to `src/pipeline/composer/callout.py`)

```python
def _draw_placed_callouts(
    draw: Any,
    placed: list[PlacedCallout],
    *,
    ink: tuple[int, int, int],
    muted: tuple[int, int, int],
    font: Any,
    leader_from_y: int,
) -> None:
    """Draw labels + leader lines onto a caller-supplied ImageDraw (pure)."""
    for p in placed:
        if p.needs_leader:
            label_cx = p.x + p.width // 2
            label_bottom = p.y + ROW_HEIGHT
            draw.line([(p.anchor_x, leader_from_y), (label_cx, label_bottom)],
                      fill=muted, width=1)
        draw.text((p.x, p.y), p.label, font=font, fill=ink)


def render_callouts(
    callouts: list[Callout],
    base_image: Any,
    *,
    left: int,
    right: int,
    body_top: int,
    top_limit: int,
    leader_from_y: int,
    ink: tuple[int, int, int],
    muted: tuple[int, int, int],
    font_size: int = 18,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> Any:
    """Composite callouts onto a copy of ``base_image`` and return it.

    Primarily the golden-test surface (chart call sites use ``place_callouts`` +
    ``_draw_placed_callouts`` directly because they own a shared ``ImageDraw``).
    """
    from PIL import ImageDraw

    from pipeline.composer.rich_slide import _SANS_BOLD, _load_font

    font = _load_font(_SANS_BOLD, font_size)
    img = base_image.copy()
    draw = ImageDraw.Draw(img)
    placed = place_callouts(
        callouts,
        measure=lambda s: int(draw.textlength(s, font=font)),
        left=left, right=right, body_top=body_top, top_limit=top_limit,
        max_rows=max_rows,
    )
    _draw_placed_callouts(draw, placed, ink=ink, muted=muted, font=font,
                          leader_from_y=leader_from_y)
    return img
```

- [ ] **Step 4: Generate goldens, EYEBALL each, then verify**

```bash
UPDATE_GOLDENS=1 uv run pytest tests/unit/test_callout.py -q
```
Then open and visually inspect each of the 4 PNGs in `tests/fixtures/callout/golden/` — confirm: labels legible, no horizontal overlap, dodged labels have a thin leader line to their anchor, nothing clipped at edges. (A passing deterministic test will happily bake in a layout bug — looking is mandatory.)

Run again WITHOUT the env var to confirm the comparison path passes:
`uv run pytest tests/unit/test_callout.py -q`
Expected: PASS (12 tests total).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/composer/callout.py tests/unit/test_callout.py tests/fixtures/callout/golden/
git commit -m "feat(callout): render_callouts image wrapper + 4 placement goldens"
```

---

### Task 3: Route the static `_render_line` through the primitive

**Files:**
- Modify: `src/pipeline/composer/chart.py:528-539`
- Modify (regen): `tests/fixtures/chart/golden/line.png`

- [ ] **Step 1: Replace the inline marker-label loop**

In `src/pipeline/composer/chart.py`, the current loop (lines ~528-539) draws the marker line + dot inline and places the label with a 2-row stagger. Keep the line + dot; replace the label placement. New version:

```python
    mf = _load_font(_SANS_BOLD, 18)
    callouts = []
    for m in markers:
        mx = float(m["x"])
        mpx = pad_l + int(plot_w * (mx - x_min) / x_span)
        draw.line([mpx, body_top + 8, mpx, body_bottom], fill=pal["muted"], width=1)
        draw.ellipse([mpx - 7, body_top + 1, mpx + 7, body_top + 15], fill=pal["ink"])
        callouts.append(Callout(x=mpx, label=str(m.get("label", ""))))

    placed = place_callouts(
        callouts,
        measure=lambda s: int(draw.textlength(s, font=mf)),
        left=pad_l, right=pad_l + plot_w, body_top=body_top, top_limit=top + 2,
    )
    _draw_placed_callouts(draw, placed, ink=pal["ink"], muted=pal["muted"],
                          font=mf, leader_from_y=body_top)
```

Add the import near the top of `chart.py` (with the other composer imports):

```python
from pipeline.composer.callout import Callout, _draw_placed_callouts, place_callouts
```

- [ ] **Step 2: Run the line golden test to confirm it now fails (placement changed)**

Run: `uv run pytest tests/unit/test_chart.py -q -k line`
Expected: FAIL — `line render drifted from golden` (the static `line.png` golden no longer matches; this is expected).

- [ ] **Step 3: Regenerate the static line golden + EYEBALL**

```bash
UPDATE_GOLDENS=1 uv run pytest tests/unit/test_chart.py -q -k line
```
Open `tests/fixtures/chart/golden/line.png` — confirm marker labels are now collision-free with leader lines where dodged, curve + dots intact, source-credit strip clear.

Run without the env var: `uv run pytest tests/unit/test_chart.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/composer/chart.py tests/fixtures/chart/golden/line.png
git commit -m "feat(chart): route static line marker labels through callout primitive"
```

---

### Task 4: Route the animated `_animate_line_frame` through the primitive + widen wipe

**Files:**
- Modify: `src/pipeline/composer/chart_anim.py` (wipe rect ~142; marker-label loop ~224-240)
- Modify (regen): `tests/fixtures/chart_anim/golden/line_p00.png`, `line_p05.png`, `line_p10.png`

- [ ] **Step 1: Widen the wipe rectangle to cover the multi-row label stack**

The current wipe (chart_anim.py ~140-143) starts at `body_top - 34` — too low to cover a 3-row stack. The header content sits above `top`, so it is safe to wipe from just below `top`. Change the wipe's top edge:

```python
    wipe.rectangle(
        [pad_l - 16, top + 2, pad_l + plot_w + pad_r + 8, body_bottom + 6],
        fill=palette["paper"],
    )
```

(`top` is the function parameter; `top + 2` clears the full label-stack region without touching the header.)

- [ ] **Step 2: Replace the animated marker-label loop**

Replace the marker loop (chart_anim.py ~224-240) — keep the progress-gated marker reveal (markers appear as the draw passes their x), but route label placement through the primitive. Markers already revealed get a callout; the placement is computed once over the revealed set so dodging is stable:

```python
    mf = _load_font(_SANS_BOLD, 18)
    revealed = []
    for m in markers:
        mx = float(m["x"])
        if (mx - x_min) / x_span > progress:
            continue  # not yet reached by the draw head
        mpx = pad_l + int(plot_w * (mx - x_min) / x_span)
        draw.line([mpx, body_top + 8, mpx, body_bottom], fill=palette["muted"], width=1)
        draw.ellipse([mpx - 7, body_top + 1, mpx + 7, body_top + 15], fill=palette["ink"])
        revealed.append(Callout(x=mpx, label=str(m.get("label", ""))))

    placed = place_callouts(
        revealed,
        measure=lambda s: int(draw.textlength(s, font=mf)),
        left=pad_l, right=pad_l + plot_w, body_top=body_top, top_limit=top + 2,
    )
    _draw_placed_callouts(draw, placed, ink=palette["ink"], muted=palette["muted"],
                          font=mf, leader_from_y=body_top)
```

> NOTE: confirm the actual reveal condition in the existing code — if markers are currently revealed by an already-computed `marker visible` boolean rather than `(mx - x_min)/x_span > progress`, reuse that exact condition; do not change the reveal semantics, only the label placement. The point is: build `revealed` from the SAME markers the existing code draws, then place their labels via the primitive.

Add the import near the top of `chart_anim.py`:

```python
from pipeline.composer.callout import Callout, _draw_placed_callouts, place_callouts
```

- [ ] **Step 3: Run the animated line goldens to confirm they fail**

Run: `uv run pytest tests/unit/test_chart_anim.py -q -k line`
Expected: FAIL — `line_p05`/`line_p10` (and likely `line_p00` via the changed base + wipe) drift from golden. Expected.

- [ ] **Step 4: Regenerate the 3 animated line goldens + EYEBALL each**

```bash
UPDATE_GOLDENS=1 uv run pytest tests/unit/test_chart_anim.py -q -k line
```
Open `line_p00.png`, `line_p05.png`, `line_p10.png` in `tests/fixtures/chart_anim/golden/`:
- `p00`: only axes/axis labels, no data, no leftover labels from the base (wipe must be clean).
- `p05`: curve drawn to ~halfway, only markers reached so far have labels, no overlap.
- `p10`: full curve, ALL 6 markers labeled collision-free with leader lines where dodged.

Run without the env var: `uv run pytest tests/unit/test_chart_anim.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/composer/chart_anim.py tests/fixtures/chart_anim/golden/line_p00.png tests/fixtures/chart_anim/golden/line_p05.png tests/fixtures/chart_anim/golden/line_p10.png
git commit -m "feat(chart-anim): route animated line labels through callout primitive; widen wipe"
```

---

### Task 5: Register `callout` as a Style Manifest element

**Files:**
- Modify: `src/pipeline/style/manifest.py`
- Test: `tests/unit/test_style_manifest.py`

- [ ] **Step 1: Write the failing test** (append to `tests/unit/test_style_manifest.py`)

```python
def test_build_manifest_registers_callout_for_line_chart_markers(tmp_path):
    sb = {
        "project_id": "p1",
        "theme": {},
        "scenes": [
            {"id": "s1", "visual": {"type": "generated_image"}},
            {"id": "s21", "visual": {
                "type": "chart", "chart_type": "line",
                "data": {"points": [{"x": 1990, "y": 5}], "markers": [{"x": 1995, "label": "ban"}]},
            }},
        ],
    }
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(sb), encoding="utf-8")

    manifest = build_manifest(p)
    callout = next((e for e in manifest.elements if e.kind == "overlay"), None)
    assert callout is not None
    assert callout.id == "callout"
    assert "s21" in callout.value
    assert callout.active is True


def test_build_manifest_no_callout_when_no_markers(tmp_path):
    sb = {
        "project_id": "p1", "theme": {},
        "scenes": [{"id": "s1", "visual": {"type": "chart", "chart_type": "bar",
                                            "data": {"x": ["a"], "y": [1]}}}],
    }
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(sb), encoding="utf-8")
    assert not any(e.kind == "overlay" for e in build_manifest(p).elements)
```

(Ensure `import json` is present at the top of the test file.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_style_manifest.py -q -k callout`
Expected: FAIL — no `overlay`-kind element (and/or `StyleKind` has no `"overlay"`).

- [ ] **Step 3: Implement**

In `src/pipeline/style/manifest.py`, add `"overlay"` to the `StyleKind` literal (find its definition near the top — e.g. `StyleKind = Literal["frame", "image_prompt_prefix", "transition", "anchor_image"]`) → add `, "overlay"`.

Then, after the per-scene-overrides loop builds `overrides` (just before `return StyleManifest(...)`), append the aggregate callout element:

```python
    # 6. callout overlay (aggregate-by-type): line charts with markers carry
    #    collision-placed callouts. Derived from chart data, not a theme global.
    callout_scenes = [
        (scene.get("id") or scene.get("scene_id", ""))
        for scene in scenes
        if (vis := scene.get("visual", {})).get("type") == "chart"
        and vis.get("chart_type") == "line"
        and (vis.get("data") or {}).get("markers")
    ]
    if callout_scenes:
        elements.append(
            StyleElement(
                id="callout",
                kind="overlay",
                value=f"marker callouts on {', '.join(callout_scenes)}",
                source="chart_data",
                scope="chart_line_scenes",
                theme_key="",
                warnings=[
                    "Derived from line-chart markers, not a removable theme global. "
                    "To change, edit visual.data.markers on the listed scenes."
                ],
            )
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_style_manifest.py -q`
Expected: PASS (all, including the 2 new tests).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/style/manifest.py tests/unit/test_style_manifest.py
git commit -m "feat(style): register callout as an aggregate overlay manifest element"
```

---

### Task 6: Loud-failure swap for `apply_overlay` in compose

**Files:**
- Modify: `src/pipeline/stages/compose.py:1050-1063`
- Test: `tests/unit/test_compose_v2.py`

- [ ] **Step 1: Write the failing test** (add to `tests/unit/test_compose_v2.py`)

Mirror the article_image pattern (`test_composer_base.py:48`). Use the existing compose-v2 test harness in this file; patch `apply_overlay` to raise. Locate the harness that renders a single scene with an overlay (the file already `patch("pipeline.stages.compose.apply_overlay")` at line ~70 — reuse that fixture/shape). Concretely:

```python
def test_overlay_failure_raises_scene_render_error(tmp_path, monkeypatch):
    from pipeline.errors import SceneRenderError
    # Build the minimal compose context used elsewhere in this file for a
    # single overlay-bearing scene (reuse the existing helper/fixture in this
    # module — e.g. _single_scene_ctx(...) — do not invent a new one).
    ctx = _single_scene_ctx(tmp_path, overlay={"type": "title", "text": "hi"})

    def _boom(*a, **k):
        raise RuntimeError("ffmpeg drawtext blew up")

    monkeypatch.setattr("pipeline.stages.compose.apply_overlay", _boom)

    with pytest.raises(SceneRenderError, match="overlay"):
        _run_single_scene(ctx)   # the same per-scene render entry used by sibling tests
```

> NOTE: this file already exercises per-scene compose with a patched `apply_overlay`; reuse its existing setup/run helpers (named like the surrounding tests) rather than constructing a fresh pipeline. The assertion that matters: the exception type is `SceneRenderError` and its message mentions the overlay.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_compose_v2.py -q -k overlay_failure`
Expected: FAIL — currently the exception is swallowed to `logger.warning`, so no `SceneRenderError` is raised.

- [ ] **Step 3: Implement the swap**

In `src/pipeline/stages/compose.py`, the overlay block (~1050-1063) currently:

```python
            if scene.overlay and not ctx.skip_overlays:
                try:
                    vis = apply_overlay(...)
                except Exception as e:
                    logger.warning(
                        "compose.scene.overlay_failed", scene_id=scene.id, error=str(e),
                    )
```

Replace the `except` with a loud failure (re-raise an existing `SceneRenderError` as-is; wrap anything else):

```python
            if scene.overlay and not ctx.skip_overlays:
                try:
                    vis = apply_overlay(
                        visual_path=vis,
                        overlay=scene.overlay,
                        width=width, height=height,
                        work_dir=scenes_dir,
                        scene_id=scene.id,
                        theme=theme_dict,
                    )
                except SceneRenderError:
                    raise
                except Exception as e:
                    raise SceneRenderError(
                        scene=scene.id,
                        reason=f"overlay failed: {e}",
                        suggested_fix=(
                            "Fix or remove scene.overlay (check overlay.type and text), "
                            "or re-run with --skip-overlays to bypass overlays."
                        ),
                    ) from e
```

(`SceneRenderError` is already imported at `compose.py:29`.)

- [ ] **Step 4: Run to verify it passes + no regressions in compose tests**

Run: `uv run pytest tests/unit/test_compose_v2.py tests/unit/test_overlay_renderer.py tests/unit/test_overlay_collision_rule.py -q`
Expected: PASS. If any sibling test relied on the silent warning (rendering past a bad overlay), update it to expect `SceneRenderError` — that is the intended behavior change.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/compose.py tests/unit/test_compose_v2.py
git commit -m "feat(compose): apply_overlay failure raises SceneRenderError (loud)"
```

---

### Task 7: Full verification + s21 end-to-end + roadmap/memory deltas

**Files:**
- Modify: `docs/ROADMAP.md` (Sprint 5 → shipped; E3 v1 shipped)
- Modify: `.agent-memory/engineering-manager/arsenal-state.md`, `sprint-log.md`

- [ ] **Step 1: Full test + lint + type gate**

```bash
uv run pytest tests/unit/test_callout.py tests/unit/test_chart.py tests/unit/test_chart_anim.py tests/unit/test_style_manifest.py tests/unit/test_compose_v2.py -q
uv run ruff check src/pipeline/composer/callout.py src/pipeline/composer/chart.py src/pipeline/composer/chart_anim.py src/pipeline/style/manifest.py src/pipeline/stages/compose.py tests/unit/test_callout.py
uv run mypy src/pipeline/composer/callout.py
```
Expected: all green. Then run the broad suite to catch ripples: `uv run pytest -q` (note any pre-existing unrelated failures — e.g. `test_memory_sync.py` — and leave them alone per multi-agent hygiene).

- [ ] **Step 2: Baby-walker s21 end-to-end sanity (the actual bug)**

```bash
uv run pipeline compose rescene --project-id 20260504-115232-baby-walker-story --scene s21
```
Then sample frames from the rendered s21 segment (use the existing frame-extraction approach in `tmp/animation_review_probe.py` or `pipeline visual-review extract-frames`) at progress ~0.5 and ~1.0 and EYEBALL: the regulation markers (1982/1995/1997/2001/2004/2010) are labeled without overlap, leader lines connect dodged labels to their marker dots. This is the acceptance vehicle.

- [ ] **Step 3: Apply roadmap + memory deltas (build-complete)**

- `docs/ROADMAP.md`: Sprint 5 → 🟢 *shipped 2026-05-23*; E3 epic → 🟢 *v1 shipped (Sprint 5)* with the callout primitive recorded in the baseline arsenal (note both line paths route through it; animated entrance is E3 v2). Bump "Last updated".
- `.agent-memory/engineering-manager/arsenal-state.md`: add `callout` overlay primitive to shipped inventory; note `apply_overlay` is now loud; E3 moves from "static-only" to "static + collision-placed callouts; animated entrance v2".
- `.agent-memory/engineering-manager/sprint-log.md`: append `## Sprint 5 — 2026-05-23 — SHIPPED` with what landed, the static-vs-animated scope correction, goldens regenerated, and the standards reaffirmed (pure geometry core + determinism test before goldens; loud failure over silent fallback).

- [ ] **Step 4: Final commit**

```bash
git add docs/ROADMAP.md .agent-memory/engineering-manager/arsenal-state.md .agent-memory/engineering-manager/sprint-log.md
git commit -m "docs(roadmap): Sprint 5 shipped — callout overlay primitive v1 (E3)"
```

> Do NOT stage `src/pipeline/dashboard/*` or `tests/**/test_job*` — those are another agent's in-flight work. `git status` before each `git add`; stage only the files named in each task.

---

## Acceptance criteria (whole sprint)

1. `place_callouts` is pure geometry with a deterministic measure; collision/dodge/clamp/budget-exhaustion/header-cap all unit-tested (Task 1).
2. `render_callouts` is deterministic (two calls byte-identical) and the 4 placement goldens render stably AND were eyeballed legible (Task 2).
3. The static `chart/golden/line.png` and all three animated `chart_anim/golden/line_p{00,05,10}.png` regenerate to collision-free, eyeballed layouts; both line paths route through the primitive (Tasks 3–4).
4. `pipeline style list` / `build_manifest` surfaces a `callout` (`kind="overlay"`) element for a project with line-chart markers (Task 5).
5. `apply_overlay` failure raises `SceneRenderError` with a `suggested_fix`; a compose test asserts it (Task 6).
6. baby-walker s21 rescene shows non-overlapping regulation-marker labels (Task 7 step 2).
7. `uv run pytest` (sprint files) + `ruff check` + `mypy src/pipeline/composer/callout.py` all green (Task 7 step 1).

**Cost:** $0 incremental — pure Pillow over already-rendered frames; no provider calls. **Size:** ~1.5 sessions (the geometry core + two call-site wirings + 7 regenerated/new goldens + manifest + loud-failure swap).

**Two-axes statement:** this is a **visual-quality** lift (legible labels + first reusable E3 primitive). It does **NOT** add runtime — pure geometry/compositing, no new beats, no longer scenes. No code-level duration fence in v1 because there is no animation yet; that fence lands with the E3 v2 animated entrance.
