# Chart Renderer v1 (static, full type set) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a new `chart` visual type that renders all five static chart_types (`stat_big_number`, `proportion_blocks`, `timeline`, `bar`, `comparison`) as styled-editorial graphics, so the director stops forcing real datapoints into text `slide`s.

**Architecture:** Two-pass renderer copying `src/pipeline/composer/rich_slide.py`: an optional AI background (Flux draft tier, cached by `md5(prompt)` under `work_dir/image_cache/`, themed-flat fallback) + a Pillow composite of the data per chart_type → PNG → `image_to_video()` → scene mp4. The renderer does **not** wrap the project frame — `open_book_page` is applied later at compose time (`composer/frame.py`), exactly as for `rich_slide`. Charts carry their own title text, so `chart` is added to `overlay_rules._TEXT_VISUALS` (text overlays forbidden on top). Minimal inline validation (presence/shape) fails loudly; it is the precursor to the E5 storyboard validator.

**Tech Stack:** Python 3, Pillow (PIL) for compositing, Noto CJK fonts (`/usr/share/fonts/opentype/noto/NotoSerif/SansCJK-*.ttc`, confirmed present), ffmpeg via existing `image_to_video`. Tests: pytest with golden-PNG comparison; Flux is never called in CI (golden tests use `ai_background: false` → deterministic flat background; the AI path is tested with `try_chain` patched).

**Determinism note:** Golden PNGs are generated on this machine during execution and committed under `tests/fixtures/chart/golden/`. Pillow TrueType rendering is byte-deterministic for fixed font+size+machine, so the test re-renders and compares exact (`ImageChops.difference(...).getbbox() is None`). A `UPDATE_GOLDENS=1` env var regenerates fixtures.

**Scope OUT (do NOT build here):** animated reveal (→ E2/Sprint 2), the merged animated decline-curve (→ E2/Sprint 2), Style Manifest element registration (→ E4) + dashboard surface (→ E6), the full storyboard validator (→ E5), "small multiples" grid (→ E1 v2). **Axis guard:** this is a visual-quality lift only — it does NOT add runtime.

---

## File Structure

- **Create `src/pipeline/composer/chart.py`** — the renderer. Public `render_chart(...)`; private `_validate_chart`, `_build_background`, `_palette`, and five `_render_<type>` functions. Imports text helpers (`_load_font`, `_wrap_text`, `_hex`, font-path constants) from `rich_slide` to avoid duplication; imports `image_to_video` from `composer.base`; imports `try_chain`/`GenImageProvider`/`ProviderError` at module level so tests can patch them.
- **Modify `src/pipeline/composer/base.py`** — add `"chart"` to `VISUAL_TYPES` (line 16-28) and a dispatch branch between `slide` (line 363) and `rich_slide` (line 368).
- **Modify `src/pipeline/composer/overlay_rules.py`** — add `"chart"` to `_TEXT_VISUALS` (line 8) and update the docstring.
- **Modify `src/pipeline/stages/direct.py`** — add a `chart` line to the VISUAL TYPES block (after `slide`, ~line 223) plus a worked example carrying real numbers for each chart_type.
- **Create `tests/unit/test_chart.py`** — validation negative tests + golden-PNG tests (one per chart_type) + AI-background-path test (provider patched).
- **Create `tests/fixtures/chart/golden/<chart_type>.png`** — committed reference images (generated during execution).

---

## Task 1: `chart.py` scaffold — palette, validation, background, dispatch skeleton

**Files:**
- Create: `src/pipeline/composer/chart.py`
- Test: `tests/unit/test_chart.py`

- [ ] **Step 1: Write failing validation tests**

```python
# tests/unit/test_chart.py
import pytest
from pipeline.composer.chart import _validate_chart


def _v(**kw):
    return {"type": "chart", **kw}


def test_validate_rejects_missing_chart_type():
    with pytest.raises(ValueError, match="chart_type"):
        _validate_chart(_v(data={"value": "5"}), "s1")


def test_validate_rejects_unknown_chart_type():
    with pytest.raises(ValueError, match="unknown chart_type"):
        _validate_chart(_v(chart_type="pie", data={"value": "5"}), "s1")


def test_validate_rejects_missing_data():
    with pytest.raises(ValueError, match="data"):
        _validate_chart(_v(chart_type="stat_big_number"), "s1")


def test_validate_rejects_stat_value_over_8_chars():
    with pytest.raises(ValueError, match="8 chars"):
        _validate_chart(_v(chart_type="stat_big_number",
                            data={"value": "123456789", "unit": "x"}), "s1")


def test_validate_rejects_bar_shape_mismatch():
    with pytest.raises(ValueError, match="bar"):
        _validate_chart(_v(chart_type="bar",
                            data={"x": ["a", "b"], "y": [1]}), "s1")


def test_validate_rejects_comparison_missing_side():
    with pytest.raises(ValueError, match="comparison"):
        _validate_chart(_v(chart_type="comparison",
                            data={"left": {"label": "a", "value": "1"}}), "s1")


def test_validate_accepts_valid_stat():
    _validate_chart(_v(chart_type="stat_big_number",
                       data={"value": "230,676", "unit": "children"}), "s1")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_chart.py -q`
Expected: FAIL — `ModuleNotFoundError`/`ImportError` (no `chart.py`).

- [ ] **Step 3: Write `chart.py` scaffold (palette + validation + background)**

```python
"""Chart renderer: styled-editorial data graphics (not a Plotly dashboard).

Two-pass like ``rich_slide.py``: an optional AI background (Flux draft, cached by
``md5(prompt)``) + a Pillow composite of the data. Five static chart_types:
stat_big_number, proportion_blocks, timeline, bar, comparison.

Charts carry their own title text; the ``open_book_page`` frame is applied later
at compose time (``composer/frame.py``), so this renderer does NOT wrap the frame.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import structlog

from pipeline.composer.base import image_to_video
from pipeline.composer.rich_slide import (
    _SANS_BOLD,
    _SANS_REGULAR,
    _SERIF_BOLD,
    _SERIF_REGULAR,
    _hex,
    _load_font,
    _wrap_text,
)
from pipeline.providers.base import ProviderError, try_chain
from pipeline.providers.gen_image import GenImageProvider

logger = structlog.get_logger()

CHART_TYPES = {"stat_big_number", "proportion_blocks", "timeline", "bar", "comparison"}

# Warm editorial palette (book-page feel). Chart OWNS its foreground colors for v1
# so the look is guaranteed editorial regardless of the project's (cool, slate) Theme
# defaults; Theme integration is deferred to E4 (Style Manifest). theme.image_style is
# still consumed for the AI background prompt, which is where art-direction continuity
# lives. (Theme.secondary_bg defaults to slate-700 #334155 — cool — so consuming it for
# chart paper would defeat the editorial goal; we do not.)
_INK = (38, 30, 22)        # near-black warm ink for headlines
_PAPER = (244, 236, 222)   # aged-paper substrate
_MUTED = (120, 104, 86)    # sepia muted for captions/axes
_ACCENT = (181, 83, 42)    # warm terracotta highlight

# Bottom 25% (>= 0.75·H) is reserved for burned narration subtitles (mirrors
# rich_slide.py:234). ALL chart body content + the source credit stay above it.
_BODY_BOTTOM_FRAC = 0.70   # chart body must not extend past this
_CREDIT_Y_FRAC = 0.71      # source credit sits in the 0.70–0.75 gap, above subtitles
_HEADER_GAP = 24           # min vertical gap between header bottom (`top`) and body


def _validate_chart(visual: dict[str, Any], scene_id: str) -> None:
    """Minimal inline validation (E5 precursor). Fail loudly with a fix hint."""
    chart_type = visual.get("chart_type")
    if not chart_type:
        raise ValueError(
            f"chart {scene_id}: missing 'chart_type' (one of {sorted(CHART_TYPES)})"
        )
    if chart_type not in CHART_TYPES:
        raise ValueError(
            f"chart {scene_id}: unknown chart_type={chart_type!r}; "
            f"use one of {sorted(CHART_TYPES)}"
        )
    data = visual.get("data")
    if not data:
        raise ValueError(f"chart {scene_id}: missing 'data' for chart_type={chart_type!r}")

    if chart_type == "stat_big_number":
        value = str(data.get("value", ""))
        if not value:
            raise ValueError(f"chart {scene_id}: stat_big_number needs data.value")
        if len(value) > 8:
            raise ValueError(
                f"chart {scene_id}: stat_big_number value {value!r} > 8 chars "
                f"(won't fit big serif); shorten or use a bar/timeline."
            )
    elif chart_type == "bar":
        x, y = data.get("x"), data.get("y")
        if not isinstance(x, list) or not isinstance(y, list) or len(x) != len(y) or not x:
            raise ValueError(
                f"chart {scene_id}: bar data needs equal-length non-empty 'x' and 'y' lists; "
                f"got x={x!r} y={y!r}"
            )
    elif chart_type == "comparison":
        left, right = data.get("left"), data.get("right")
        for side_name, side in (("left", left), ("right", right)):
            if not isinstance(side, dict) or "label" not in side or "value" not in side:
                raise ValueError(
                    f"chart {scene_id}: comparison needs {side_name} with 'label' and 'value'"
                )
    elif chart_type == "proportion_blocks":
        if "ratio" not in data:
            raise ValueError(f"chart {scene_id}: proportion_blocks needs data.ratio (0..1)")
    elif chart_type == "timeline":
        if not isinstance(data, list) or not data:
            raise ValueError(f"chart {scene_id}: timeline data must be a non-empty list of "
                             f"{{year, label}} entries")


def _palette(theme: dict) -> dict[str, tuple[int, int, int]]:
    # v1: fixed warm editorial palette (see note above). theme reserved for E4.
    return {"ink": _INK, "paper": _PAPER, "accent": _ACCENT, "muted": _MUTED}


def _build_background(visual, theme, width, height, work_dir, scene_id):
    """Flat themed paper (deterministic) unless ai_background is requested."""
    from PIL import Image

    pal = _palette(theme)
    if not visual.get("ai_background", True):
        return Image.new("RGB", (width, height), pal["paper"])

    bg_prompt = visual.get("background_prompt") or "aged paper texture, soft sepia stains, faint grid"
    image_style = theme.get("image_style", "")
    prompt = f"{bg_prompt}. Style: {image_style}" if image_style and image_style not in bg_prompt else bg_prompt

    cache_dir = work_dir / "image_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_png = cache_dir / f"{hashlib.md5(prompt.encode()).hexdigest()[:12]}.png"
    if not cached_png.exists():
        size = "1792x1024" if width > height else "1024x1792"
        try:
            try_chain([GenImageProvider(tier="draft")], prompt=prompt, out_path=cached_png, size=size)
            logger.info("chart.image_generated", scene=scene_id)
        except ProviderError as exc:
            logger.warning("chart.image_failed", scene=scene_id, error=str(exc))
            Image.new("RGB", (width, height), pal["paper"]).save(cached_png)
    else:
        logger.info("chart.image_cache_hit", scene=scene_id)
    bg = Image.open(cached_png).convert("RGB").resize((width, height), Image.LANCZOS)
    # Soften AI background so foreground data reads (translucent paper wash).
    wash = Image.new("RGB", (width, height), pal["paper"])
    return Image.blend(bg, wash, 0.55)
```

- [ ] **Step 4: Run validation tests to verify they pass**

Run: `uv run pytest tests/unit/test_chart.py -q`
Expected: PASS (7 validation tests).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/composer/chart.py tests/unit/test_chart.py
git commit -m "feat(chart): chart.py scaffold — palette, inline validation, background"
```

---

## Task 2: `render_chart` entry point + `stat_big_number` renderer + golden test

**Files:**
- Modify: `src/pipeline/composer/chart.py`
- Test: `tests/unit/test_chart.py`, `tests/fixtures/chart/golden/stat_big_number.png`

- [ ] **Step 1: Add a golden-test helper + the stat golden test**

```python
# add to tests/unit/test_chart.py
import os
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageChops
from pipeline.composer.chart import render_chart

_GOLDEN = Path(__file__).parent.parent / "fixtures" / "chart" / "golden"
W, H = 1280, 720


def _render_png(visual, tmp_path, scene_id):
    """Render a chart to PNG with the mp4 step mocked out; return the PNG path."""
    with patch("pipeline.composer.chart.image_to_video") as itv:
        itv.side_effect = lambda png, out, *a, **k: out
        render_chart(visual, 8.0, W, H, tmp_path, scene_id, theme={})
    png = tmp_path / f"{scene_id}_chart.png"
    assert png.exists()
    return png


def _assert_golden(png_path, name):
    golden = _GOLDEN / f"{name}.png"
    if os.environ.get("UPDATE_GOLDENS"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        Image.open(png_path).save(golden)
        return
    assert golden.exists(), f"missing golden {golden}; run with UPDATE_GOLDENS=1"
    diff = ImageChops.difference(Image.open(png_path).convert("RGB"),
                                 Image.open(golden).convert("RGB"))
    assert diff.getbbox() is None, f"{name} render drifted from golden"


def test_golden_stat_big_number(tmp_path):
    visual = {"type": "chart", "chart_type": "stat_big_number", "ai_background": False,
              "title": "Cumulative injuries", "source_credit": "AAP, 2014",
              "data": {"value": "230,676", "unit": "children", "context": "1990–2014"}}
    _assert_golden(_render_png(visual, tmp_path, "s13"), "stat_big_number")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_chart.py::test_golden_stat_big_number -q`
Expected: FAIL — `render_chart` not defined.

- [ ] **Step 3: Implement `render_chart` + `_render_stat` + the title/credit helpers**

```python
# append to src/pipeline/composer/chart.py

def render_chart(visual, duration_sec, width, height, work_dir, scene_id, theme=None):
    from PIL import ImageDraw

    theme = theme or {}
    _validate_chart(visual, scene_id)
    chart_type = visual["chart_type"]
    pal = _palette(theme)

    bg = _build_background(visual, theme, width, height, work_dir, scene_id)
    draw = ImageDraw.Draw(bg)

    top = _draw_header(draw, visual, width, height, pal)
    renderer = {
        "stat_big_number": _render_stat,
        "proportion_blocks": _render_proportion,
        "timeline": _render_timeline,
        "bar": _render_bar,
        "comparison": _render_comparison,
    }[chart_type]
    renderer(draw, visual, width, height, pal, top)
    _draw_credit(draw, visual, width, height, pal)

    composite_png = work_dir / f"{scene_id}_chart.png"
    bg.save(composite_png)
    output = work_dir / f"{scene_id}_visual.mp4"
    image_to_video(composite_png, output, duration_sec, width, height)
    return output


def _draw_header(draw, visual, width, height, pal) -> int:
    """Title + subtitle at the top; return y where chart body may start."""
    pad = int(width * 0.07)
    y = int(height * 0.09)
    title = visual.get("title", "")
    if title:
        f = _load_font(_SERIF_BOLD, 40)
        for line in _wrap_text(title, f, width - pad * 2, draw):
            draw.text((pad, y), line, font=f, fill=pal["ink"])
            y += (draw.textbbox((0, 0), line, font=f)[3]) + 6
    subtitle = visual.get("subtitle", "")
    if subtitle:
        f = _load_font(_SANS_REGULAR, 24)
        draw.text((pad, y), subtitle, font=f, fill=pal["muted"])
        y += 34
    draw.rectangle([pad, y + 6, pad + 70, y + 10], fill=pal["accent"])
    return y + 28


def _draw_credit(draw, visual, width, height, pal) -> None:
    credit = visual.get("source_credit")
    if not credit:
        return
    f = _load_font(_SANS_REGULAR, 20)
    pad = int(width * 0.07)
    draw.text((pad, int(height * 0.93)), f"Source: {credit}", font=f, fill=pal["muted"])


def _render_stat(draw, visual, width, height, pal, top) -> None:
    data = visual["data"]
    cx = width // 2
    num_f = _load_font(_SERIF_BOLD, 168)
    value = str(data["value"])
    bbox = draw.textbbox((0, 0), value, font=num_f)
    nx = cx - (bbox[2] - bbox[0]) // 2
    ny = int(height * 0.34)
    draw.text((nx, ny), value, font=num_f, fill=pal["accent"])
    y = ny + (bbox[3] - bbox[1]) + 30
    unit = str(data.get("unit", ""))
    if unit:
        uf = _load_font(_SANS_BOLD, 38)
        ub = draw.textbbox((0, 0), unit.upper(), font=uf)
        draw.text((cx - (ub[2] - ub[0]) // 2, y), unit.upper(), font=uf, fill=pal["ink"])
        y += 56
    context = str(data.get("context", ""))
    if context:
        cf = _load_font(_SANS_REGULAR, 28)
        cb = draw.textbbox((0, 0), context, font=cf)
        draw.text((cx - (cb[2] - cb[0]) // 2, y), context, font=cf, fill=pal["muted"])
```

(Add no-op stubs `def _render_proportion(*a): raise NotImplementedError` etc. for the four not-yet-built types so the dispatch dict resolves; they get real bodies in Tasks 3-6.)

- [ ] **Step 4: Generate the golden, then run the test**

Run: `UPDATE_GOLDENS=1 uv run pytest tests/unit/test_chart.py::test_golden_stat_big_number -q`
Then inspect the PNG visually (open `tests/fixtures/chart/golden/stat_big_number.png`); confirm it reads as an editorial stat card, not an Excel chart.
Run again without the env var: `uv run pytest tests/unit/test_chart.py::test_golden_stat_big_number -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/composer/chart.py tests/unit/test_chart.py tests/fixtures/chart/golden/stat_big_number.png
git commit -m "feat(chart): render_chart entry + stat_big_number renderer + golden"
```

---

## Task 3: `proportion_blocks` renderer + golden

**Files:** Modify `src/pipeline/composer/chart.py`; Test `tests/unit/test_chart.py`, `tests/fixtures/chart/golden/proportion_blocks.png`

- [ ] **Step 1: Add the golden test**

```python
def test_golden_proportion_blocks(tmp_path):
    visual = {"type": "chart", "chart_type": "proportion_blocks", "ai_background": False,
              "title": "Where walker injuries happen", "source_credit": "AAP",
              "data": {"label": "74% stair falls", "ratio": 0.74,
                       "secondary_label": "26% other", "secondary_ratio": 0.26}}
    _assert_golden(_render_png(visual, tmp_path, "s12"), "proportion_blocks")
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/unit/test_chart.py::test_golden_proportion_blocks -q` → FAIL (`NotImplementedError`).

- [ ] **Step 3: Implement `_render_proportion`** — a single horizontal strip split by `ratio`: primary segment in `accent`, secondary in `muted`; ratio % printed inside each segment in paper-white; labels beneath. Strip occupies the middle band between `top` and ~0.78·H, full content width with `0.07·W` padding.

```python
def _render_proportion(draw, visual, width, height, pal, top) -> None:
    data = visual["data"]
    pad = int(width * 0.07)
    bar_w = width - pad * 2
    ratio = max(0.0, min(1.0, float(data["ratio"])))
    y0 = max(top + 40, int(height * 0.40))
    bar_h = int(height * 0.16)
    split = pad + int(bar_w * ratio)
    draw.rectangle([pad, y0, split, y0 + bar_h], fill=pal["accent"])
    draw.rectangle([split, y0, pad + bar_w, y0 + bar_h], fill=pal["muted"])
    pf = _load_font(_SERIF_BOLD, 52)
    draw.text((pad + 24, y0 + bar_h // 2 - 30), f"{round(ratio * 100)}%", font=pf, fill=pal["paper"])
    lf = _load_font(_SANS_REGULAR, 28)
    draw.text((pad, y0 + bar_h + 22), str(data.get("label", "")), font=lf, fill=pal["ink"])
    sec = data.get("secondary_label")
    if sec:
        sb = draw.textbbox((0, 0), str(sec), font=lf)
        draw.text((pad + bar_w - (sb[2] - sb[0]), y0 + bar_h + 22), str(sec), font=lf, fill=pal["muted"])
```

- [ ] **Step 4: Generate golden + run** — `UPDATE_GOLDENS=1 uv run pytest ...::test_golden_proportion_blocks -q`; inspect PNG; re-run without env → PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(chart): proportion_blocks renderer + golden"`

---

## Task 4: `timeline` renderer + golden

**Files:** Modify `chart.py`; Test `test_chart.py`, `fixtures/chart/golden/timeline.png`

- [ ] **Step 1: Add the golden test**

```python
def test_golden_timeline(tmp_path):
    visual = {"type": "chart", "chart_type": "timeline", "ai_background": False,
              "title": "Two decades of walker injuries",
              "data": [{"year": 1990, "label": "20,650 ER visits"},
                       {"year": 2001, "label": "AAP ban call"},
                       {"year": 2004, "label": "Canada bans"},
                       {"year": 2014, "label": "230k cumulative"}]}
    _assert_golden(_render_png(visual, tmp_path, "s10"), "timeline")
```

- [ ] **Step 2: Run to verify it fails** → `NotImplementedError`.

- [ ] **Step 3: Implement `_render_timeline`** — a horizontal axis line at mid-height; one circular marker per entry, evenly spaced across the content width; year in serif-bold below the axis, label wrapped above the axis, alternating vertical offset so adjacent labels don't collide.

```python
def _render_timeline(draw, visual, width, height, pal, top) -> None:
    data = visual["data"]
    pad = int(width * 0.09)
    axis_y = int(height * 0.55)
    span = width - pad * 2
    n = len(data)
    draw.line([pad, axis_y, pad + span, axis_y], fill=pal["muted"], width=3)
    yf = _load_font(_SERIF_BOLD, 30)
    lf = _load_font(_SANS_REGULAR, 22)
    for i, entry in enumerate(data):
        x = pad + (span * i // max(1, n - 1))
        draw.ellipse([x - 9, axis_y - 9, x + 9, axis_y + 9], fill=pal["accent"])
        year = str(entry.get("year", ""))
        yb = draw.textbbox((0, 0), year, font=yf)
        draw.text((x - (yb[2] - yb[0]) // 2, axis_y + 22), year, font=yf, fill=pal["ink"])
        label = str(entry.get("label", ""))
        lines = _wrap_text(label, lf, int(span / n) + 40, draw)
        ly = axis_y - 30 - (40 if i % 2 else 0) - len(lines) * 26
        for line in lines:
            lb = draw.textbbox((0, 0), line, font=lf)
            draw.text((x - (lb[2] - lb[0]) // 2, ly), line, font=lf, fill=pal["muted"])
            ly += 26
```

- [ ] **Step 4: Generate golden + run** → PASS.
- [ ] **Step 5: Commit** — `"feat(chart): timeline renderer + golden"`

---

## Task 5: `bar` renderer + golden

**Files:** Modify `chart.py`; Test `test_chart.py`, `fixtures/chart/golden/bar.png`

- [ ] **Step 1: Add the golden test**

```python
def test_golden_bar(tmp_path):
    visual = {"type": "chart", "chart_type": "bar", "ai_background": False,
              "title": "Walker injury mechanisms", "source_credit": "AAP",
              "data": {"x": ["stair falls", "tip-overs", "burns", "drowning"],
                       "y": [74, 13, 6, 4], "y_unit": "%"}}
    _assert_golden(_render_png(visual, tmp_path, "s11"), "bar")
```

- [ ] **Step 2: Run to verify it fails** → `NotImplementedError`.

- [ ] **Step 3: Implement `_render_bar`** — horizontal bars, one row per `x`. Category label left-aligned above each bar; bar width ∝ `y / max(y)`; value (+`y_unit`) printed just past the bar tip in ink. Accent fill. Rows evenly distributed between `top` and ~0.85·H.

```python
def _render_bar(draw, visual, width, height, pal, top) -> None:
    data = visual["data"]
    xs, ys = data["x"], [float(v) for v in data["y"]]
    unit = data.get("y_unit", "")
    pad = int(width * 0.07)
    label_f = _load_font(_SANS_BOLD, 26)
    val_f = _load_font(_SERIF_BOLD, 28)
    max_v = max(ys) or 1.0
    track_w = int(width * 0.62)
    y0 = max(top + 30, int(height * 0.30))
    row_h = int((height * 0.85 - y0) / len(xs))
    bar_h = min(int(row_h * 0.42), 46)
    for label, v in zip(xs, ys, strict=False):
        draw.text((pad, y0), str(label), font=label_f, fill=pal["ink"])
        by = y0 + 34
        bw = int(track_w * (v / max_v))
        draw.rectangle([pad, by, pad + max(2, bw), by + bar_h], fill=pal["accent"])
        vtxt = f"{v:g}{unit}"
        draw.text((pad + bw + 16, by + bar_h // 2 - 16), vtxt, font=val_f, fill=pal["ink"])
        y0 += row_h
```

- [ ] **Step 4: Generate golden + run** → PASS.
- [ ] **Step 5: Commit** — `"feat(chart): bar renderer + golden"`

---

## Task 6: `comparison` renderer + golden

**Files:** Modify `chart.py`; Test `test_chart.py`, `fixtures/chart/golden/comparison.png`

- [ ] **Step 1: Add the golden test**

```python
def test_golden_comparison(tmp_path):
    visual = {"type": "chart", "chart_type": "comparison", "ai_background": False,
              "title": "Speed vs. reaction",
              "data": {"left": {"label": "Sit-in walker", "value": "3 ft/s"},
                       "right": {"label": "Adult reaction", "value": "0.7 s"}}}
    _assert_golden(_render_png(visual, tmp_path, "s14"), "comparison")
```

- [ ] **Step 2: Run to verify it fails** → `NotImplementedError`.

- [ ] **Step 3: Implement `_render_comparison`** — two columns split by a centered vertical rule; each side shows `value` in large serif (accent left / ink right) above `label` in sans. Centered within each half.

```python
def _render_comparison(draw, visual, width, height, pal, top) -> None:
    data = visual["data"]
    mid = width // 2
    y_val = int(height * 0.40)
    draw.line([mid, int(height * 0.30), mid, int(height * 0.82)], fill=pal["muted"], width=2)
    vf = _load_font(_SERIF_BOLD, 96)
    lf = _load_font(_SANS_REGULAR, 30)
    for side, cx, color in (("left", mid // 2, pal["accent"]), ("right", mid + mid // 2, pal["ink"])):
        s = data[side]
        val = str(s["value"])
        vb = draw.textbbox((0, 0), val, font=vf)
        draw.text((cx - (vb[2] - vb[0]) // 2, y_val), val, font=vf, fill=color)
        lab = str(s["label"])
        lb = draw.textbbox((0, 0), lab, font=lf)
        draw.text((cx - (lb[2] - lb[0]) // 2, y_val + (vb[3] - vb[1]) + 28), lab, font=lf, fill=pal["muted"])
```

Replace the four `NotImplementedError` stubs as each task lands; after Task 6 none remain.

- [ ] **Step 4: Generate golden + run** → PASS.
- [ ] **Step 5: Commit** — `"feat(chart): comparison renderer + golden"`

---

## Task 7: Wire dispatch in `base.py` + integration test

**Files:** Modify `src/pipeline/composer/base.py`; Test `tests/unit/test_chart.py`

- [ ] **Step 1: Add the integration + AI-background tests**

```python
def test_render_scene_dispatches_chart(tmp_path):
    from pipeline.composer.base import render_scene
    with patch("pipeline.composer.chart.image_to_video") as itv:
        itv.side_effect = lambda png, out, *a, **k: out
        out = render_scene(
            scene={"id": "s1", "visual": {"type": "chart", "chart_type": "stat_big_number",
                    "ai_background": False, "data": {"value": "42", "unit": "x"}}},
            duration_sec=5.0, aspect_ratio="16:9", work_dir=tmp_path, theme={})
    assert out.name == "s1_visual.mp4"


def test_ai_background_path_calls_provider(tmp_path):
    def fake_chain(providers, prompt, out_path, size):
        Image.new("RGB", (64, 64), (200, 180, 150)).save(out_path)
    with patch("pipeline.composer.chart.try_chain", side_effect=fake_chain) as fc, \
         patch("pipeline.composer.chart.image_to_video") as itv:
        itv.side_effect = lambda png, out, *a, **k: out
        render_chart({"type": "chart", "chart_type": "stat_big_number",
                      "ai_background": True, "data": {"value": "42", "unit": "x"}},
                     5.0, W, H, tmp_path, "s2", theme={"image_style": "warm sepia"})
    fc.assert_called_once()
    assert (tmp_path / "s2_chart.png").exists()
```

- [ ] **Step 2: Run to verify dispatch test fails** — `uv run pytest tests/unit/test_chart.py::test_render_scene_dispatches_chart -q` → FAIL (`Unknown visual type: chart`).

- [ ] **Step 3: Add `"chart"` to `VISUAL_TYPES` and the dispatch branch**

In `base.py` `VISUAL_TYPES` set (after `"rich_slide",`): add `"chart",`.
Between the `slide` branch (ends line 366) and the `rich_slide` branch (line 368):

```python
    elif visual_type == "chart":
        from pipeline.composer.chart import render_chart

        return render_chart(visual, duration_sec, width, height, work_dir, scene_id, theme)
```

- [ ] **Step 4: Run both tests** → PASS.
- [ ] **Step 5: Commit** — `git add base.py tests/...; git commit -m "feat(chart): dispatch chart in render_scene + VISUAL_TYPES"`

---

## Task 8: `overlay_rules` — forbid text overlays on charts

**Files:** Modify `src/pipeline/composer/overlay_rules.py`; Test `tests/unit/test_overlay_renderer.py`

- [ ] **Step 1: Add the test**

```python
# tests/unit/test_overlay_renderer.py
def test_text_overlay_forbidden_on_chart():
    from pipeline.composer.overlay_rules import check_overlay_allowed, OverlayCollisionError
    import pytest
    with pytest.raises(OverlayCollisionError, match="text-on-text"):
        check_overlay_allowed(scene={"id": "s1"}, overlay={"type": "text_top", "text": "x"},
                              visual={"type": "chart"}, burn_subtitles=True)
```

- [ ] **Step 2: Run to verify it fails** → no raise (chart not in `_TEXT_VISUALS`).
- [ ] **Step 3: Add `"chart"` to `_TEXT_VISUALS`** (line 8 → `{"text_card", "slide", "chart"}`) and add `chart` to the docstring's text-on-text rule.
- [ ] **Step 4: Run test** → PASS.
- [ ] **Step 5: Commit** — `"feat(chart): forbid text overlays on chart visuals (carries own title)"`

---

## Task 9: Director taxonomy + worked examples (`direct.py`)

**Files:** Modify `src/pipeline/stages/direct.py` (~line 223); Test `tests/unit/test_direct_prompt.py` (new, lightweight)

- [ ] **Step 1: Add a prompt-content test**

```python
# tests/unit/test_direct_prompt.py
def test_prompt_includes_chart_taxonomy_and_examples():
    from pipeline.stages import direct
    # Build the storyboard prompt with minimal inputs (use the module's builder).
    import inspect
    src = inspect.getsource(direct)
    assert '"type": "chart"' in src
    assert "stat_big_number" in src and "proportion_blocks" in src
    assert "timeline" in src and "bar" in src and "comparison" in src
    # A worked example with a real number is present (teaches the data schema):
    assert "230,676" in src or "230676" in src
```

(If `direct.py` already exposes a prompt-builder function callable with simple args, prefer asserting on its returned string instead of source.)

- [ ] **Step 2: Run to verify it fails** → assertion error (no `chart` in prompt).

- [ ] **Step 3: Add the taxonomy line + worked examples** after the `slide:` line (~223):

```
- chart: {"type": "chart", "chart_type": "stat_big_number|proportion_blocks|timeline|bar|comparison",
          "title": "...", "data": {...}, "source_credit": "optional"}
  Use when the scene's CORE message IS a number, proportion, sequence of years, ranking, or
  two-way contrast. If the scene names a real datapoint, prefer chart over slide+text.
  Examples (note the per-type data schema):
  - stat_big_number: {"chart_type":"stat_big_number","title":"Cumulative injuries",
      "data":{"value":"230,676","unit":"children","context":"1990–2014"}}
  - proportion_blocks: {"chart_type":"proportion_blocks","title":"Where falls happen",
      "data":{"label":"74% stair falls","ratio":0.74,"secondary_label":"26% other","secondary_ratio":0.26}}
  - timeline: {"chart_type":"timeline","title":"Two decades",
      "data":[{"year":1990,"label":"20,650 ER visits"},{"year":2014,"label":"230k cumulative"}]}
  - bar: {"chart_type":"bar","title":"Injury mechanisms",
      "data":{"x":["stair falls","tip-overs","burns"],"y":[74,13,6],"y_unit":"%"}}
  - comparison: {"chart_type":"comparison","title":"Speed vs reaction",
      "data":{"left":{"label":"Sit-in walker","value":"3 ft/s"},"right":{"label":"Adult reaction","value":"0.7 s"}}}
  RULE: stat_big_number value must be <= 8 chars. Charts carry their own title — do NOT add a text overlay.
```

Also extend the `confidence` guidance (~line 230) so "clear data → chart (or slide for non-numeric lists)".

- [ ] **Step 4: Run test** → PASS.
- [ ] **Step 5: Commit** — `"feat(chart): director taxonomy + per-type worked examples for chart"`

---

## Task 10: Full verification, roadmap/memory finalization, wrap-up commit

- [ ] **Step 1: Run the whole gate**

```bash
uv run pytest tests/unit/test_chart.py tests/unit/test_overlay_renderer.py tests/unit/test_composer_base.py tests/unit/test_direct_prompt.py -q
uv run ruff check src/ tests/
uv run mypy src/pipeline/composer/chart.py
```
Expected: all green. (Run the broader `uv run pytest -q` to confirm no regressions in the composer suite.)

- [ ] **Step 2: Spot-check the five goldens visually** — open each `tests/fixtures/chart/golden/*.png`; confirm editorial feel (warm, book-page), legible, no clipping. If any reads like an Excel chart, refine the renderer and regenerate that golden (this is the acceptance bar — quality is the north star).

- [ ] **Step 3: Roadmap delta** — in `docs/ROADMAP.md`: move Sprint 1 heading 🟡 → 🟢 *shipped*; in "Current arsenal" add `chart` to Visual types; bump "Last updated". In epic E1 mark 🔵 → 🟢.

- [ ] **Step 4: Memory updates** — `.agent-memory/engineering-manager/arsenal-state.md`: move `chart` from "Designed, not built" to a shipped row (note: 5 static types, two-pass, `ai_background` flag, inline validation). `sprint-log.md`: append `## Sprint 1 — 2026-05-21 — SHIPPED` with what landed + the standards lesson. `standards.md` (Tim-confirmed): add the "renderers don't self-wrap the frame" + "golden tests in tests/unit, deterministic flat bg, no provider in CI" lessons under "Anatomy of a new visual type".

- [ ] **Step 5: Final commit**

```bash
git add docs/ROADMAP.md .agent-memory/engineering-manager/ src/ tests/
git commit -m "feat(chart): ship Chart Renderer v1 — 5 static chart_types; close Sprint 1"
```

---

## Self-Review (run against the proposal/handoff)

- **Spec coverage:** chart.py two-pass ✓ (T1-T6) · dispatch ✓ (T7) · taxonomy+worked examples ✓ (T9) · overlay_rules ✓ (T8) · inline validation ✓ (T1) · golden tests per type ✓ (T2-T6) · all five chart_types ✓. theme.image_style consumed (not niche visual_style) ✓ (T1 `_build_background`). Frame NOT self-wrapped ✓ (compose-level). Cost: Flux draft cached, ai_background=false in tests → $0 CI ✓.
- **Placeholder scan:** the four `_render_*` stubs are explicitly temporary (NotImplementedError) and replaced by Tasks 3-6; no TODO/TBD remain.
- **Type consistency:** `render_chart(visual, duration_sec, width, height, work_dir, scene_id, theme=None)` matches the dispatch call in T7 and the `rich_slide`/`slide` signatures. `_palette` keys (`ink/paper/accent/muted`) are used consistently across all `_render_*`. Each `_render_*(draw, visual, width, height, pal, top)` signature is uniform.
- **Axis guard:** plan header + Scope OUT state visual-quality only, no runtime. ✓
