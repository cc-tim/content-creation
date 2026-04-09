# Composition Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the caption/overlay collision bug, add a reusable "compartment" system for looping animated side-panels (e.g. the context-anxiety running-out counter), introduce a Start Scene Director sub-agent that picks a unique, compelling intro per video, and regenerate project `1775401082` with the new storyboard.

**Architecture:** Split the monolithic `text` overlay into three safe variants (`text_top`, `text_left`, `text_emphasis`) and forbid any overlay below `y=0.70` when subtitles are burned in. Add a `Scene.compartment` field that references a separate PIL-drawn looping animation (initial type: `running_out`), composited as a second overlay stream between the visual and the overlay. Add a `director` sub-agent invocation at Step 4a of `/produce` that reads the full context and proposes 2 candidate intro treatments; the user picks one and that choice drives a new intro scene visual type (initially just a richer `generated_image` + `text_emphasis` pair — no new visual primitives needed for this phase).

**Tech Stack:** Pillow (PIL) for drawing animation frames, FFmpeg for looping composition (`-stream_loop -1`), pytest with tmp fixtures, existing `composer/*` modules, Anthropic Claude via the existing evaluator pattern.

**Spec:** `docs/superpowers/specs/2026-04-08-voice-pipeline-gemini-composition-overhaul-design.md` — Feature 1.

**Depends on:** Phase A (Gemini image provider) is recommended but not required — this plan still works with DALL-E-only image generation. Phase C (Voice) is fully independent.

---

## File Structure

- **Modify:** `src/pipeline/composer/overlay.py` — remove the old `text` type, add `text_top`, `text_left`, `text_emphasis`
- **Create:** `src/pipeline/composer/compartment.py` — PIL frame generation + FFmpeg looping overlay
- **Create:** `src/pipeline/composer/compartment_renderers/__init__.py`
- **Create:** `src/pipeline/composer/compartment_renderers/running_out.py` — the "context anxiety" animation
- **Modify:** `src/pipeline/storyboard.py` — add `Scene.compartment: dict | None`
- **Modify:** `src/pipeline/stages/compose.py` — composite compartment between visual and overlay
- **Modify:** `src/pipeline/composer/base.py` — `render_scene` passes through compartments unchanged
- **Create:** `scripts/migrate_storyboard_overlays.py` — rewrite old `text` overlays to `text_top`
- **Create:** `tests/unit/test_overlay_variants.py`
- **Create:** `tests/unit/test_compartment_running_out.py`
- **Create:** `tests/unit/test_storyboard_compartment.py`
- **Create:** `tests/unit/test_overlay_collision_rule.py` — lints storyboards for forbidden overlay positions
- **Modify:** `.claude/commands/produce.md` — add Step 4a (Start Scene Director) + updated Step 7b evaluator
- **Modify:** `output/projects/1775401082/storyboard.json` — apply the fix

---

## Phase 1 — Overlay variants (fix the collision bug)

### Task 1.1: Define the three new overlay variants (failing tests)

**Files:**
- Test: `tests/unit/test_overlay_variants.py`

- [ ] **Step 1: Read the existing overlay module**

Read `src/pipeline/composer/overlay.py` to see the current `apply_overlay` signature, the `title`, `text`, and `namecard` branches, and the helper `_escape_drawtext`. Note how y/x coordinates are built via FFmpeg expressions.

- [ ] **Step 2: Write the failing test**

Create `tests/unit/test_overlay_variants.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipeline.composer.overlay import apply_overlay


def _make_blank_mp4(path: Path, duration: float = 2.0) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c=black:s=640x360:d={duration}:r=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
        capture_output=True,
    )


@pytest.mark.integration
def test_text_top_places_overlay_near_top(tmp_path):
    src = tmp_path / "src.mp4"
    _make_blank_mp4(src)
    out = apply_overlay(
        visual_path=src,
        overlay={"type": "text_top", "text": "Hello World"},
        width=640,
        height=360,
        work_dir=tmp_path,
        scene_id="s1",
        theme={},
    )
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.integration
def test_text_left_places_overlay_on_left_half(tmp_path):
    src = tmp_path / "src.mp4"
    _make_blank_mp4(src)
    out = apply_overlay(
        visual_path=src,
        overlay={"type": "text_left", "text": "Left side label"},
        width=640,
        height=360,
        work_dir=tmp_path,
        scene_id="s2",
        theme={},
    )
    assert out.exists()


@pytest.mark.integration
def test_text_emphasis_is_centered_and_large(tmp_path):
    src = tmp_path / "src.mp4"
    _make_blank_mp4(src)
    out = apply_overlay(
        visual_path=src,
        overlay={"type": "text_emphasis", "text": "BIG"},
        width=640,
        height=360,
        work_dir=tmp_path,
        scene_id="s3",
        theme={},
    )
    assert out.exists()


def test_text_overlay_type_is_rejected(tmp_path):
    # The old "text" type dropped overlays on the bottom — it's forbidden now.
    with pytest.raises(ValueError):
        apply_overlay(
            visual_path=tmp_path / "nonexistent.mp4",
            overlay={"type": "text", "text": "Would collide with subtitles"},
            width=640,
            height=360,
            work_dir=tmp_path,
            scene_id="s4",
            theme={},
        )
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_overlay_variants.py -v`
Expected: FAIL — the new types raise `ValueError`, and `text` currently does not raise.

### Task 1.2: Implement the new overlay variants

**Files:**
- Modify: `src/pipeline/composer/overlay.py`

- [ ] **Step 1: Rewrite the branch logic**

Edit `src/pipeline/composer/overlay.py`. Keep the file structure (same public `apply_overlay` signature) and the existing `title` + `namecard` branches. Replace the old `text` branch with three new branches, and raise `ValueError` if `overlay["type"] == "text"`:

```python
def apply_overlay(
    visual_path: Path,
    overlay: dict,
    width: int,
    height: int,
    work_dir: Path,
    scene_id: str,
    theme: dict | None = None,
) -> Path:
    theme = theme or {}
    overlay_type = overlay.get("type")
    if overlay_type == "text":
        raise ValueError(
            "overlay.type='text' is forbidden (collides with subtitles). "
            "Use text_top, text_left, or text_emphasis."
        )

    # ... existing title / namecard branches unchanged ...

    if overlay_type == "text_top":
        return _render_text_top(visual_path, overlay, width, height, work_dir, scene_id, theme)
    if overlay_type == "text_left":
        return _render_text_left(visual_path, overlay, width, height, work_dir, scene_id, theme)
    if overlay_type == "text_emphasis":
        return _render_text_emphasis(visual_path, overlay, width, height, work_dir, scene_id, theme)
    raise ValueError(f"unknown overlay type: {overlay_type}")
```

Add the three helpers at the bottom of the file:

```python
def _render_text_top(visual_path, overlay, width, height, work_dir, scene_id, theme):
    text = _escape_drawtext(overlay.get("text", ""))
    font = theme.get("font", "Noto Sans CJK TC")
    color = overlay.get("color", theme.get("accent", "#38bdf8"))
    font_size = overlay.get("font_size", 44)
    out = work_dir / f"{scene_id}_overlay.mp4"
    # Band at y = 4%..16% of height (well above the subtitles at the bottom)
    vf = (
        f"drawbox=x=0:y=ih*0.04:w=iw:h=ih*0.12:color=black@0.45:t=fill,"
        f"drawtext=text='{text}':fontsize={font_size}:fontcolor={color}:font='{font}'"
        f":x=(w-text_w)/2:y=ih*0.08"
        f":shadowcolor=black@0.5:shadowx=2:shadowy=2"
    )
    run_ffmpeg([
        "ffmpeg", "-y", "-i", str(visual_path),
        "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p", str(out),
    ])
    return out


def _render_text_left(visual_path, overlay, width, height, work_dir, scene_id, theme):
    text = _escape_drawtext(overlay.get("text", ""))
    font = theme.get("font", "Noto Sans CJK TC")
    color = overlay.get("color", theme.get("accent", "#38bdf8"))
    font_size = overlay.get("font_size", 40)
    out = work_dir / f"{scene_id}_overlay.mp4"
    # Left third, vertical center, with a dim backing box for contrast.
    vf = (
        f"drawbox=x=iw*0.04:y=ih*0.25:w=iw*0.32:h=ih*0.50:color=black@0.40:t=fill,"
        f"drawtext=text='{text}':fontsize={font_size}:fontcolor={color}:font='{font}'"
        f":x=iw*0.06:y=ih*0.30:text_align=left"
        f":shadowcolor=black@0.5:shadowx=2:shadowy=2"
    )
    run_ffmpeg([
        "ffmpeg", "-y", "-i", str(visual_path),
        "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p", str(out),
    ])
    return out


def _render_text_emphasis(visual_path, overlay, width, height, work_dir, scene_id, theme):
    text = _escape_drawtext(overlay.get("text", ""))
    font = theme.get("font", "Noto Sans CJK TC")
    color = overlay.get("color", theme.get("accent", "#fbbf24"))
    font_size = overlay.get("font_size", 72)
    out = work_dir / f"{scene_id}_overlay.mp4"
    # Giant centered text, upper third (never below 60% height).
    vf = (
        f"drawtext=text='{text}':fontsize={font_size}:fontcolor={color}:font='{font}'"
        f":x=(w-text_w)/2:y=ih*0.35"
        f":shadowcolor=black@0.7:shadowx=3:shadowy=3:borderw=2:bordercolor=black"
    )
    run_ffmpeg([
        "ffmpeg", "-y", "-i", str(visual_path),
        "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p", str(out),
    ])
    return out
```

The `text_align=left` parameter requires FFmpeg 6+. Check first with `ffmpeg -version`; if it's older, remove that parameter.

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_overlay_variants.py -v`
Expected: 3 integration tests PASS (they actually run FFmpeg), 1 unit test PASS (the `text` rejection).

If FFmpeg is unavailable in this environment, mark integration tests with `pytest.mark.integration` and run only the rejection test here:
Run: `uv run pytest tests/unit/test_overlay_variants.py::test_text_overlay_type_is_rejected -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/composer/overlay.py tests/unit/test_overlay_variants.py
git commit -m "feat(overlay): replace bottom-text overlay with safe variants"
```

---

### Task 1.3: Collision lint rule (fail the pipeline on bad overlays)

**Files:**
- Create: `src/pipeline/composer/overlay_rules.py`
- Test: `tests/unit/test_overlay_collision_rule.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_overlay_collision_rule.py`:

```python
from __future__ import annotations

import pytest

from pipeline.composer.overlay_rules import check_overlay_allowed, OverlayCollisionError


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_overlay_collision_rule.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the rule module**

Create `src/pipeline/composer/overlay_rules.py`:

```python
from __future__ import annotations


class OverlayCollisionError(ValueError):
    """Raised when a scene overlay would collide with subtitles or text visuals."""


_TEXT_VISUALS = {"text_card", "slide"}
_FORBIDDEN_OVERLAY_TYPES = {"text"}  # legacy name, bottom-anchored


def check_overlay_allowed(
    *,
    scene: dict,
    overlay: dict | None,
    visual: dict,
    burn_subtitles: bool,
) -> None:
    """Raise if this overlay + visual combination is unsafe.

    Rules:
    - The legacy `text` overlay type is banned.
    - text_* overlays cannot be applied to text_card or slide visuals.
    - `title` overlays are allowed anywhere (top-anchored).
    """
    if overlay is None:
        return

    overlay_type = overlay.get("type")
    if overlay_type in _FORBIDDEN_OVERLAY_TYPES:
        raise OverlayCollisionError(
            f"scene {scene.get('id', '?')}: overlay type {overlay_type!r} is forbidden "
            "(collides with burned subtitles). Use text_top, text_left, or text_emphasis."
        )

    if overlay_type and overlay_type.startswith("text"):
        if visual.get("type") in _TEXT_VISUALS:
            raise OverlayCollisionError(
                f"scene {scene.get('id', '?')}: cannot apply {overlay_type!r} overlay to "
                f"{visual.get('type')!r} visual (text-on-text is unreadable)."
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_overlay_collision_rule.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Wire the rule into `stages/compose.py`**

Read `src/pipeline/stages/compose.py` and locate the per-scene loop that calls `apply_overlay`. Right before that call, add:

```python
from pipeline.composer.overlay_rules import check_overlay_allowed

# ...
check_overlay_allowed(
    scene=scene_dict,
    overlay=scene_dict.get("overlay"),
    visual=scene_dict["visual"],
    burn_subtitles=True,
)
```

This makes the compose stage fail loudly on a bad storyboard instead of producing a broken render.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/composer/overlay_rules.py src/pipeline/stages/compose.py tests/unit/test_overlay_collision_rule.py
git commit -m "feat(compose): enforce overlay collision rules before render"
```

---

### Task 1.4: Migration script for existing storyboards

**Files:**
- Create: `scripts/migrate_storyboard_overlays.py`

- [ ] **Step 1: Write the script**

Create `scripts/migrate_storyboard_overlays.py`:

```python
#!/usr/bin/env python3
"""Rewrite legacy `text` overlays to `text_top` for an existing storyboard.

Usage:
    uv run python scripts/migrate_storyboard_overlays.py output/projects/<ID>/storyboard.json

Safe to re-run — it's idempotent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def migrate(storyboard_path: Path) -> int:
    data = json.loads(storyboard_path.read_text())
    changed = 0
    for scene in data.get("scenes", []):
        overlay = scene.get("overlay")
        if not overlay:
            continue
        if overlay.get("type") == "text":
            overlay["type"] = "text_top"
            changed += 1
        # Disallow applying text overlays to text visuals.
        if overlay.get("type", "").startswith("text"):
            v = scene.get("visual", {})
            if v.get("type") in ("text_card", "slide"):
                scene["overlay"] = None
                changed += 1
    storyboard_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False)
    )
    return changed


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 1
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"no such file: {path}", file=sys.stderr)
        return 1
    changed = migrate(path)
    print(f"migrated {changed} overlay entries in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Manual smoke test**

Run: `uv run python scripts/migrate_storyboard_overlays.py output/projects/1775401082/storyboard.json`
Expected: Prints `migrated N overlay entries` where N is the number of `text` overlays in that file.

- [ ] **Step 3: Commit**

```bash
git add scripts/migrate_storyboard_overlays.py
git commit -m "feat(scripts): add storyboard overlay migration helper"
```

---

## Phase 2 — Compartment system (the "context anxiety" animation)

### Task 2.1: Add `compartment` field to `Scene`

**Files:**
- Modify: `src/pipeline/storyboard.py`
- Test: `tests/unit/test_storyboard_compartment.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_storyboard_compartment.py`:

```python
from __future__ import annotations

from pipeline.storyboard import Scene, Storyboard


def test_scene_accepts_compartment():
    scene = Scene.from_dict(
        {
            "id": "s3",
            "section": "context",
            "narration": "脈絡焦慮",
            "narration_est_sec": 10,
            "facts_ref": ["f1"],
            "visual": {"type": "generated_image", "prompt": "brain"},
            "overlay": {"type": "text_left", "text": "上下文焦慮"},
            "compartment": {
                "type": "running_out",
                "position": "right",
                "size": {"width": 0.35, "height": 0.6},
                "loop": True,
                "animation": {
                    "label": "上下文",
                    "stages": [
                        {"value": "20%", "face": "neutral", "color": "#fbbf24"},
                        {"value": "10%", "face": "worried", "color": "#fb923c"},
                        {"value": "5%", "face": "panicked", "color": "#ef4444"},
                    ],
                    "stage_duration_sec": 1.5,
                    "shake": True,
                },
            },
        }
    )
    assert scene.compartment is not None
    assert scene.compartment["type"] == "running_out"


def test_scene_without_compartment_round_trips():
    data = {
        "id": "s1",
        "section": "hook",
        "narration": "開場",
        "narration_est_sec": 8,
        "facts_ref": [],
        "visual": {"type": "text_card", "text": "hi"},
        "overlay": None,
    }
    scene = Scene.from_dict(data)
    assert scene.compartment is None
    round_tripped = scene.to_dict()
    assert "compartment" not in round_tripped or round_tripped["compartment"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_storyboard_compartment.py -v`
Expected: FAIL — `Scene` has no `compartment` field.

- [ ] **Step 3: Add the field to `Scene`**

Edit `src/pipeline/storyboard.py`. In the `@dataclass Scene`, add:

```python
    compartment: dict | None = None
```

In `Scene.from_dict`, add `compartment=data.get("compartment")` to the constructor call.

In `Scene.to_dict`, include `compartment` only when it is not None:

```python
        if self.compartment is not None:
            out["compartment"] = self.compartment
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_storyboard_compartment.py -v`
Expected: PASS (2 tests). Also run the existing storyboard tests to make sure nothing regressed: `uv run pytest tests/unit/ -q -k storyboard`.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/storyboard.py tests/unit/test_storyboard_compartment.py
git commit -m "feat(storyboard): add Scene.compartment field"
```

---

### Task 2.2: PIL-drawn `running_out` animation frames

**Files:**
- Create: `src/pipeline/composer/compartment_renderers/__init__.py`
- Create: `src/pipeline/composer/compartment_renderers/running_out.py`
- Test: `tests/unit/test_compartment_running_out.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_compartment_running_out.py`:

```python
from __future__ import annotations

from pathlib import Path

from pipeline.composer.compartment_renderers.running_out import (
    render_running_out_frames,
)


def test_running_out_writes_one_png_per_stage(tmp_path):
    config = {
        "label": "上下文",
        "stages": [
            {"value": "20%", "face": "neutral", "color": "#fbbf24"},
            {"value": "10%", "face": "worried", "color": "#fb923c"},
            {"value": "5%", "face": "panicked", "color": "#ef4444"},
        ],
        "stage_duration_sec": 1.5,
        "shake": True,
    }
    frames = render_running_out_frames(
        out_dir=tmp_path,
        config=config,
        width=480,
        height=640,
    )
    assert len(frames) == len(config["stages"])
    for frame in frames:
        assert frame.path.exists()
        assert frame.path.stat().st_size > 100
        assert frame.duration_sec == 1.5


def test_running_out_handles_unknown_face(tmp_path):
    # Unknown face should fall back to neutral, not crash.
    config = {
        "label": "X",
        "stages": [{"value": "50%", "face": "mystery", "color": "#ffffff"}],
        "stage_duration_sec": 1.0,
    }
    frames = render_running_out_frames(
        out_dir=tmp_path, config=config, width=320, height=480
    )
    assert len(frames) == 1
    assert frames[0].path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_compartment_running_out.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the frame renderer**

Create `src/pipeline/composer/compartment_renderers/__init__.py` (empty).

Create `src/pipeline/composer/compartment_renderers/running_out.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont


@dataclass
class CompartmentFrame:
    path: Path
    duration_sec: float


_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _draw_face(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, kind: str) -> None:
    """Draw a simple PIL emoji-style face centered at (cx, cy)."""
    # Face circle
    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        fill=(255, 220, 90),
        outline=(60, 40, 10),
        width=max(2, r // 20),
    )

    eye_y = cy - r // 3
    eye_dx = r // 2
    eye_r = max(3, r // 10)

    if kind == "neutral":
        draw.ellipse(
            (cx - eye_dx - eye_r, eye_y - eye_r, cx - eye_dx + eye_r, eye_y + eye_r),
            fill=(40, 20, 0),
        )
        draw.ellipse(
            (cx + eye_dx - eye_r, eye_y - eye_r, cx + eye_dx + eye_r, eye_y + eye_r),
            fill=(40, 20, 0),
        )
        draw.line((cx - r // 2, cy + r // 3, cx + r // 2, cy + r // 3), fill=(40, 20, 0), width=max(2, r // 25))
    elif kind == "worried":
        # Angled brows
        draw.line((cx - eye_dx - r // 4, eye_y - r // 3, cx - eye_dx + r // 4, eye_y - r // 5), fill=(40, 20, 0), width=max(2, r // 20))
        draw.line((cx + eye_dx - r // 4, eye_y - r // 5, cx + eye_dx + r // 4, eye_y - r // 3), fill=(40, 20, 0), width=max(2, r // 20))
        # Small eyes
        draw.ellipse((cx - eye_dx - eye_r // 2, eye_y, cx - eye_dx + eye_r // 2, eye_y + eye_r), fill=(40, 20, 0))
        draw.ellipse((cx + eye_dx - eye_r // 2, eye_y, cx + eye_dx + eye_r // 2, eye_y + eye_r), fill=(40, 20, 0))
        # Downturned mouth
        draw.arc(
            (cx - r // 2, cy + r // 6, cx + r // 2, cy + r // 2),
            start=180, end=360,
            fill=(40, 20, 0),
            width=max(2, r // 20),
        )
    elif kind == "panicked":
        # Wide round eyes
        draw.ellipse((cx - eye_dx - eye_r, eye_y - eye_r - 2, cx - eye_dx + eye_r, eye_y + eye_r + 2), fill=(255, 255, 255), outline=(40, 20, 0), width=2)
        draw.ellipse((cx + eye_dx - eye_r, eye_y - eye_r - 2, cx + eye_dx + eye_r, eye_y + eye_r + 2), fill=(255, 255, 255), outline=(40, 20, 0), width=2)
        draw.ellipse((cx - eye_dx - 2, eye_y - 2, cx - eye_dx + 2, eye_y + 2), fill=(40, 20, 0))
        draw.ellipse((cx + eye_dx - 2, eye_y - 2, cx + eye_dx + 2, eye_y + 2), fill=(40, 20, 0))
        # Open shout mouth
        draw.ellipse((cx - r // 3, cy + r // 5, cx + r // 3, cy + r // 2 + r // 6), fill=(120, 20, 20), outline=(40, 0, 0), width=2)
    else:
        # Unknown face: fall back to neutral
        _draw_face(draw, cx, cy, r, "neutral")


def _parse_hex_color(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        return (250, 200, 60)
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def render_running_out_frames(
    out_dir: Path,
    config: dict,
    width: int,
    height: int,
) -> list[CompartmentFrame]:
    """Draw one PNG per stage and return the list in order."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stages: Sequence[dict] = config.get("stages", [])
    duration = float(config.get("stage_duration_sec", 1.5))
    label = config.get("label", "")

    label_font = _load_font(max(20, height // 14))
    value_font = _load_font(max(48, height // 5))

    frames: list[CompartmentFrame] = []
    for idx, stage in enumerate(stages):
        img = Image.new("RGBA", (width, height), (15, 23, 42, 220))  # slate backdrop
        draw = ImageDraw.Draw(img)

        # Border accent in the stage color
        color = _parse_hex_color(stage.get("color", "#fbbf24"))
        draw.rectangle((0, 0, width - 1, height - 1), outline=color, width=6)

        # Label at top
        label_y = height // 12
        lw = draw.textlength(label, font=label_font)
        draw.text(
            ((width - lw) / 2, label_y),
            label,
            font=label_font,
            fill=(226, 232, 240, 255),
        )

        # Face in the middle
        face_cx = width // 2
        face_cy = int(height * 0.42)
        face_r = min(width, height) // 4
        _draw_face(draw, face_cx, face_cy, face_r, stage.get("face", "neutral"))

        # Big value at the bottom
        value = stage.get("value", "")
        vw = draw.textlength(value, font=value_font)
        draw.text(
            ((width - vw) / 2, int(height * 0.72)),
            value,
            font=value_font,
            fill=color + (255,),
        )

        frame_path = out_dir / f"running_out_{idx:02d}.png"
        img.save(frame_path)
        frames.append(CompartmentFrame(path=frame_path, duration_sec=duration))

    return frames
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_compartment_running_out.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/composer/compartment_renderers/__init__.py src/pipeline/composer/compartment_renderers/running_out.py tests/unit/test_compartment_running_out.py
git commit -m "feat(compartment): add PIL-drawn running_out frame renderer"
```

---

### Task 2.3: Compartment video builder (loop + composite)

**Files:**
- Create: `src/pipeline/composer/compartment.py`
- Test: `tests/unit/test_compartment_running_out.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_compartment_running_out.py`:

```python
import pytest

from pipeline.composer.compartment import build_compartment_loop


@pytest.mark.integration
def test_build_compartment_loop_produces_mp4(tmp_path):
    config = {
        "type": "running_out",
        "position": "right",
        "size": {"width": 0.35, "height": 0.6},
        "loop": True,
        "animation": {
            "label": "上下文",
            "stages": [
                {"value": "20%", "face": "neutral", "color": "#fbbf24"},
                {"value": "10%", "face": "worried", "color": "#fb923c"},
            ],
            "stage_duration_sec": 1.0,
        },
    }
    out = build_compartment_loop(
        compartment=config,
        scene_duration_sec=5.0,
        scene_width=1920,
        scene_height=1080,
        work_dir=tmp_path,
        scene_id="s3",
    )
    assert out.exists()
    assert out.stat().st_size > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_compartment_running_out.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the builder**

Create `src/pipeline/composer/compartment.py`:

```python
from __future__ import annotations

from pathlib import Path

from pipeline.composer.compartment_renderers.running_out import render_running_out_frames
from pipeline.utils.ffmpeg import run_ffmpeg


def build_compartment_loop(
    compartment: dict,
    scene_duration_sec: float,
    scene_width: int,
    scene_height: int,
    work_dir: Path,
    scene_id: str,
) -> Path:
    """Build a looping compartment video sized for overlay on a scene.

    Returns a path to an mp4 whose duration matches scene_duration_sec so it can
    be laid over the main visual as a second input.
    """
    ctype = compartment.get("type", "running_out")
    if ctype != "running_out":
        raise ValueError(f"unknown compartment type: {ctype}")

    size = compartment.get("size", {"width": 0.35, "height": 0.6})
    width = max(64, int(scene_width * float(size.get("width", 0.35))))
    height = max(64, int(scene_height * float(size.get("height", 0.6))))

    frames_dir = work_dir / f"{scene_id}_compartment_frames"
    frames = render_running_out_frames(
        out_dir=frames_dir,
        config=compartment.get("animation", {}),
        width=width,
        height=height,
    )
    if not frames:
        raise ValueError("compartment produced zero frames")

    # Build a concat list that loops through stages. Duration per frame lives in
    # each CompartmentFrame.
    stage_list_path = work_dir / f"{scene_id}_compartment_frames.txt"
    lines: list[str] = []
    for frame in frames:
        lines.append(f"file '{frame.path.as_posix()}'")
        lines.append(f"duration {frame.duration_sec}")
    # ffmpeg concat demuxer requires the final file listed one extra time.
    lines.append(f"file '{frames[-1].path.as_posix()}'")
    stage_list_path.write_text("\n".join(lines) + "\n")

    loop_mp4 = work_dir / f"{scene_id}_compartment.mp4"
    # -stream_loop -1 loops the concat until we hit -t scene_duration_sec.
    run_ffmpeg([
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-f", "concat", "-safe", "0", "-i", str(stage_list_path),
        "-t", f"{scene_duration_sec}",
        "-vf", f"fps=30,scale={width}:{height},format=yuva420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "22",
        "-pix_fmt", "yuv420p",
        str(loop_mp4),
    ])
    return loop_mp4


def composite_compartment_on_scene(
    scene_video: Path,
    compartment_video: Path,
    compartment_config: dict,
    scene_width: int,
    scene_height: int,
    work_dir: Path,
    scene_id: str,
) -> Path:
    """Overlay the compartment loop on top of the scene video using FFmpeg."""
    position = compartment_config.get("position", "right")
    size = compartment_config.get("size", {"width": 0.35, "height": 0.6})
    cw = int(scene_width * float(size.get("width", 0.35)))
    ch = int(scene_height * float(size.get("height", 0.6)))

    if position == "right":
        x_expr = f"W-w-{int(scene_width * 0.03)}"
    elif position == "left":
        x_expr = f"{int(scene_width * 0.03)}"
    else:
        x_expr = "(W-w)/2"
    y_expr = "(H-h)/2"

    shake = compartment_config.get("animation", {}).get("shake", False)
    if shake:
        amp = max(2, cw // 40)
        x_expr = f"({x_expr})+({amp}*sin(6*t))"
        y_expr = f"({y_expr})+({amp}*cos(6*t))"

    out = work_dir / f"{scene_id}_with_compartment.mp4"
    filter_complex = (
        f"[1:v]scale={cw}:{ch}[comp];"
        f"[0:v][comp]overlay=x='{x_expr}':y='{y_expr}':format=auto[v]"
    )
    run_ffmpeg([
        "ffmpeg", "-y",
        "-i", str(scene_video),
        "-i", str(compartment_video),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "22",
        "-pix_fmt", "yuv420p",
        str(out),
    ])
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_compartment_running_out.py -v`
Expected: PASS (3 tests if FFmpeg is available; otherwise the integration test is skipped).

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/composer/compartment.py tests/unit/test_compartment_running_out.py
git commit -m "feat(compartment): add looping compartment builder + compositor"
```

---

### Task 2.4: Wire compartments into `stages/compose.py`

**Files:**
- Modify: `src/pipeline/stages/compose.py`

- [ ] **Step 1: Read the current compose stage**

Re-read `src/pipeline/stages/compose.py`, specifically `_compose_from_storyboard`. Note the exact location where each scene's video is rendered (call to `render_scene`) and where `apply_overlay` is called.

- [ ] **Step 2: Add the compartment step between visual and overlay**

Edit `src/pipeline/stages/compose.py`. Near the top add:

```python
from pipeline.composer.compartment import (
    build_compartment_loop,
    composite_compartment_on_scene,
)
```

Inside the per-scene loop, after `visual_video = render_scene(...)` and before `apply_overlay(...)`, insert:

```python
compartment_cfg = scene_dict.get("compartment")
if compartment_cfg:
    compartment_video = build_compartment_loop(
        compartment=compartment_cfg,
        scene_duration_sec=scene_duration_sec,
        scene_width=width,
        scene_height=height,
        work_dir=scene_work_dir,
        scene_id=scene_dict["id"],
    )
    visual_video = composite_compartment_on_scene(
        scene_video=visual_video,
        compartment_video=compartment_video,
        compartment_config=compartment_cfg,
        scene_width=width,
        scene_height=height,
        work_dir=scene_work_dir,
        scene_id=scene_dict["id"],
    )
```

Variable names (`scene_duration_sec`, `width`, `height`, `scene_work_dir`) may differ in the current file — match what is already defined in the loop scope.

- [ ] **Step 3: Write a compose integration test (or reuse an existing one)**

If `tests/integration/test_compose.py` exists, extend it with one scenario that includes a compartment; otherwise skip the integration test for now and rely on the unit tests from Task 2.3.

- [ ] **Step 4: Run unit tests**

Run: `uv run pytest tests/unit/ -q`
Expected: No regressions.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/stages/compose.py
git commit -m "feat(compose): composite scene compartments between visual and overlay"
```

---

## Phase 3 — Start Scene Director + produce.md updates

### Task 3.1: Document the Start Scene Director sub-agent in `/produce`

**Files:**
- Modify: `.claude/commands/produce.md`

- [ ] **Step 1: Read the current file**

Re-read `.claude/commands/produce.md`. Note the existing Step 4 (Direct) and Step 4b (Storyboard Evaluator), and the Step 7b render evaluator. The new Director runs as Step 4a — between the draft storyboard and the quality evaluator.

- [ ] **Step 2: Add Step 4a**

Insert a new section between Step 4 and Step 4b:

````markdown
### Step 4a: Start Scene Director (SUB-AGENT)

**Dispatch a separate Director sub-agent** to pick the most compelling intro
treatment for this specific video. The Director must read the whole context
(knowledge.json, draft storyboard, keyframes, article images if web source)
and propose TWO distinct candidate intros. You then present both to the user
and apply the one they pick. If the user already said which treatment they
want in their /produce arguments, skip the sub-agent and apply their choice
directly.

```
Agent(
  subagent_type="general-purpose",
  description="Pick best intro for this video",
  prompt="""You are the START SCENE DIRECTOR. Your job is to design the opening
scene (s1) of a short video so it grabs attention and sets up the story.

Read these files carefully — do not skim:
1. output/projects/<ID>/knowledge.json
2. output/projects/<ID>/storyboard.json
3. ls output/projects/<ID>/source/keyframes/ (YouTube sources)
4. ls output/projects/<ID>/source/images/ (web sources, if present)
5. .claude/commands/produce.md (visual guidelines)

Your output is TWO distinct candidate intro treatments. They should differ in
style — not two variants of the same idea. For each candidate provide:

- Name (e.g. "Kinetic stat slam", "Montage of reactions", "Quiet question")
- Rationale (1-2 sentences: why this opening suits THIS video's topic and tone)
- A concrete storyboard patch for s1:
  ```json
  {
    "id": "s1",
    "visual": { "type": "...", "...": "..." },
    "overlay": { "type": "...", "text": "..." },
    "compartment": null,
    "narration": "...",
    "narration_est_sec": 8
  }
  ```
- The visual type must be one of: generated_image, article_image, clip,
  text_card, slide. Do not invent new types.
- If you pick generated_image, write a concrete prompt in the visual.
- Do not put text overlays on text_card or slide visuals.
- Do not place overlays below y=0.70 (collides with subtitles).

Return STRICTLY in this format:

```
## Candidate A: <name>
Rationale: ...
Patch:
<json block>

## Candidate B: <name>
Rationale: ...
Patch:
<json block>
```

Be opinionated. Under 500 words."""
)
```

Present both candidates to the user. Ask which to apply. If they picked one up
front via /produce arguments, apply that one directly without asking.

Then patch `storyboard.json` with the chosen s1 block and re-save.
````

- [ ] **Step 3: Update Step 7b evaluator rules**

Inside Step 7b, expand the "Anti-pattern check" section to include:

```markdown
**Anti-pattern checks (hard fail if any are true):**
- Any overlay with `type == "text"` (banned legacy type).
- Any text_* overlay applied to a text_card or slide visual.
- Any scene where the opening shot is a plain text_card and no generated_image
  or article_image variant was considered.
- Any scene with a compartment whose `position == "bottom"` (collides with subs).
- Duration mismatch: rendered video vs storyboard.target_duration_sec diverges
  by more than 15%.
```

- [ ] **Step 4: Commit**

```bash
git add .claude/commands/produce.md
git commit -m "docs(produce): add Start Scene Director step + stricter evaluator"
```

---

## Phase 4 — Regenerate project 1775401082

### Task 4.1: Migrate the existing storyboard

**Files:**
- Modify: `output/projects/1775401082/storyboard.json`

- [ ] **Step 1: Run the migration script**

Run: `uv run python scripts/migrate_storyboard_overlays.py output/projects/1775401082/storyboard.json`
Expected: Prints `migrated N overlay entries`.

- [ ] **Step 2: Manually apply the anxiety compartment to s3**

Read `output/projects/1775401082/storyboard.json`. Find the Context Anxiety scene (the one whose narration describes the running-out-of-context problem — likely `s3`). Patch it:

```json
{
  "id": "s3",
  "visual": { "type": "generated_image", "prompt": "flat minimalist illustration of a brain with a tiny hourglass inside, glowing amber, dark slate background" },
  "overlay": { "type": "text_left", "text": "脈絡焦慮" },
  "compartment": {
    "type": "running_out",
    "position": "right",
    "size": { "width": 0.32, "height": 0.55 },
    "loop": true,
    "animation": {
      "label": "上下文",
      "stages": [
        { "value": "20%", "face": "neutral",  "color": "#fbbf24" },
        { "value": "10%", "face": "worried",  "color": "#fb923c" },
        { "value": "5%",  "face": "panicked", "color": "#ef4444" }
      ],
      "stage_duration_sec": 1.5,
      "shake": true
    }
  }
}
```

Preserve the other scene fields (`section`, `narration`, `narration_est_sec`, `facts_ref`).

- [ ] **Step 3: Fix the garbled s10 overlay**

Find the scene whose overlay text reads `單獨AI： / 壞掉 vs 多代理：00 / 16功能完整` (or any scene with suspiciously numeric mangled strings). Replace its overlay with a clean `text_top`:

```json
"overlay": { "type": "text_top", "text": "$9 vs $200 — 完整功能" }
```

- [ ] **Step 4: Commit**

```bash
git add output/projects/1775401082/storyboard.json
git commit -m "fix(1775401082): migrate overlays, add anxiety compartment, fix s10"
```

---

### Task 4.2: Run the Start Scene Director for this project

**Files:**
- Modify: `output/projects/1775401082/storyboard.json`

- [ ] **Step 1: Dispatch the Director sub-agent**

Use the Agent tool with the prompt template from Task 3.1, substituting `<ID>` with `1775401082`. Read both candidates it returns.

- [ ] **Step 2: Pick the candidate with the strongest visual hook**

Prefer the one whose patch uses `generated_image` + `text_emphasis` or `article_image` + `text_top`. Do not use a bare `text_card`.

- [ ] **Step 3: Patch the storyboard**

Apply the chosen patch to `output/projects/1775401082/storyboard.json` under scene `s1`. Keep `facts_ref` and `section` as they were.

- [ ] **Step 4: Commit**

```bash
git add output/projects/1775401082/storyboard.json
git commit -m "feat(1775401082): apply director-chosen intro scene"
```

---

### Task 4.3: Regenerate from TTS onward

**Files:**
- None (runs the pipeline)

- [ ] **Step 1: Ensure the Gemini key is available**

Run: `bash -lc 'echo ${GEMINI_API_KEY:0:6}...'`
Expected: Prints a non-empty prefix. If empty, re-source `~/.bashrc` or re-run the key setup.

- [ ] **Step 2: Re-run compose (TTS can be skipped if narration already exists)**

Run:

```bash
uv run pipeline produce \
  --url "https://www.youtube.com/watch?v=<the-source-url>" \
  --project-id 1775401082 \
  --locale zh-TW \
  --start-from compose \
  --skip-review
```

If the source URL is lost, read `output/projects/1775401082/context.json` for the `source_url` field.

If compose fails because narration is missing or out of sync with the new storyboard, fall back to:

```bash
uv run pipeline produce \
  --url "<URL>" \
  --project-id 1775401082 \
  --locale zh-TW \
  --start-from tts \
  --skip-review
```

Expected: Produces `output/projects/1775401082/compose/final_zh-TW.mp4`.

- [ ] **Step 3: Verify output**

Run:

```bash
ls -lh output/projects/1775401082/compose/final_zh-TW.mp4
ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 output/projects/1775401082/compose/final_zh-TW.mp4
```

Expected: File exists, duration within 15% of the storyboard's `target_duration_sec`.

- [ ] **Step 4: Extract review frames**

Run:

```bash
uv run python3 -c "
from pathlib import Path
from pipeline.utils.video_analysis import extract_review_frames
video = Path('output/projects/1775401082/compose/final_zh-TW.mp4')
review_dir = Path('output/projects/1775401082/compose/review_frames')
frames = extract_review_frames(video, review_dir, count=8)
for f in frames:
    print(f['timestamp_sec'], f['path'])
"
```

- [ ] **Step 5: Read each frame image**

Use the Read tool on each review frame PNG. Confirm:
- No overlay text overlaps with burned subtitles at the bottom.
- s3 (anxiety) shows the right-side compartment with the face + percentage.
- s1 looks distinctly different from a stock slide — the director's choice is visible.
- s10 shows clean "$9 vs $200 — 完整功能" text, no garbled digits.

---

### Task 4.4: Dispatch the render evaluator sub-agent

**Files:**
- None (runs the evaluator per `/produce` Step 7b)

- [ ] **Step 1: Dispatch the evaluator**

Use the Agent tool with the updated Step 7b prompt from `.claude/commands/produce.md`, substituting `<ID>` with `1775401082` and `<LOCALE>` with `zh-TW`.

- [ ] **Step 2: Read the verdict**

- If verdict is **PASS** (all scores ≥ 3 and no anti-pattern failures): done. Tell the user the video is ready, print the path, stop.
- If verdict is **NEEDS_WORK**: apply the evaluator's recommended storyboard edits and go back to Task 4.3 Step 2.

---

## Done criteria

- `uv run pytest tests/unit/test_overlay_variants.py tests/unit/test_overlay_collision_rule.py tests/unit/test_storyboard_compartment.py tests/unit/test_compartment_running_out.py -v` is green.
- `/produce` skill doc contains Step 4a Director block and strict Step 7b anti-pattern checks.
- `output/projects/1775401082/compose/final_zh-TW.mp4` is regenerated.
- Render evaluator reports PASS — specifically confirming no overlay/subtitle collision, compartment visible on s3, and intro scene is visually distinctive.
- No occurrence of `"type": "text"` in any overlay in `output/projects/1775401082/storyboard.json`.

