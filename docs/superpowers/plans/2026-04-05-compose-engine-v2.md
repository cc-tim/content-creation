# Compose Engine V2 — Scene-by-Scene Rendering

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the MVP compose stage (continuous source footage) with a scene-by-scene renderer that reads the storyboard and dispatches to pluggable visual renderers per scene, producing visually varied output.

**Architecture:** The compose stage loads `storyboard.json`, iterates scenes, dispatches each to the appropriate visual renderer (based on `scene.visual.type`), combines visual + audio per scene, concatenates all scenes, and burns subtitles. Each renderer is a standalone function in its own file under `src/pipeline/composer/`. The `ComposeStage` is rewritten to orchestrate these renderers.

**Tech Stack:** FFmpeg (drawtext filter for text cards/overlays, extract/concat for clips, image loop for stills), OpenAI DALL-E API (generated images), existing pipeline utilities.

**Spec:** `docs/superpowers/specs/2026-04-05-v2-compose-engine-design.md` (Section 5: Layer 3)

---

## File Structure

```
src/pipeline/composer/
  __init__.py
  base.py              # render_scene() dispatcher + common helpers
  clip.py              # ClipRenderer — extract segment from source video
  text_card.py         # TextCardRenderer — styled text on solid background
  image.py             # ImageRenderer — DALL-E generated image → video segment
  slide.py             # SlideRenderer — title + bullets layout
  still_frame.py       # StillFrameRenderer — single frame looped
  overlay.py           # OverlayRenderer — composite overlay on top of visual
src/pipeline/stages/compose.py   # Rewritten to use scene-by-scene rendering
tests/unit/
  test_composer_base.py
  test_clip_renderer.py
  test_text_card_renderer.py
  test_image_renderer.py
  test_slide_renderer.py
  test_still_frame_renderer.py
  test_overlay_renderer.py
  test_compose_v2.py
```

**Deferred renderers (not in this plan):**
- `MapRenderer` — requires a maps API or screenshot tool. For now, falls back to TextCardRenderer with location text.
- `NamecardRenderer` — similar to TextCardRenderer with different styling. For now, handled by TextCardRenderer.

This keeps the plan focused. Map and namecard get dedicated renderers in a future iteration.

---

### Task 1: Composer base — dispatcher + helpers

**Files:**
- Create: `src/pipeline/composer/__init__.py`
- Create: `src/pipeline/composer/base.py`
- Create: `tests/unit/test_composer_base.py`

The dispatcher function `render_scene()` takes a scene dict, duration, aspect ratio, work dir, and source video path. It looks up the visual type and calls the appropriate renderer. Common helpers: `image_to_video()` (convert a PNG to a video segment of given duration), `get_resolution()` (return width x height for aspect ratio).

Tests: dispatcher routes correctly, get_resolution returns right values, unknown type raises error.

### Task 2: ClipRenderer

**Files:**
- Create: `src/pipeline/composer/clip.py`
- Create: `tests/unit/test_clip_renderer.py`

Extracts a segment from source video. Validates start/end against source duration (clamps if beyond). Re-encodes to ensure consistent codec for concatenation. For 9:16 aspect, center-crops the 16:9 source.

Tests: command generation, timestamp clamping, aspect ratio crop filter.

### Task 3: TextCardRenderer

**Files:**
- Create: `src/pipeline/composer/text_card.py`
- Create: `tests/unit/test_text_card_renderer.py`

Generates a solid-color background with styled text using FFmpeg's `drawtext` filter. Supports CJK text (Noto Sans CJK TC font). Also handles `namecard` and `map` visual types as fallbacks (namecard = text on dark bar, map = location text on dark background).

Tests: command generation with CJK text, background color, font settings.

### Task 4: ImageRenderer (DALL-E)

**Files:**
- Create: `src/pipeline/composer/image.py`
- Create: `tests/unit/test_image_renderer.py`

Calls OpenAI DALL-E API to generate an image from a prompt, saves as PNG, converts to video segment via `image_to_video()`. Caches generated images by prompt hash to avoid re-generating. Falls back to TextCardRenderer if API key not configured or call fails.

Tests: API call mock, cache hit, fallback behavior.

### Task 5: SlideRenderer

**Files:**
- Create: `src/pipeline/composer/slide.py`
- Create: `tests/unit/test_slide_renderer.py`

Renders a presentation-style slide: title at top, bullet points below, optional image. Uses FFmpeg drawtext with multiple text layers. Dark background, white text, clean layout.

Tests: command generation with title + bullets, layout positioning.

### Task 6: StillFrameRenderer

**Files:**
- Create: `src/pipeline/composer/still_frame.py`
- Create: `tests/unit/test_still_frame_renderer.py`

Extracts a single frame from source video at a given timestamp, loops it for the scene duration. Simple: ffmpeg extract frame → image_to_video().

Tests: frame extraction command, timestamp validation.

### Task 7: OverlayRenderer

**Files:**
- Create: `src/pipeline/composer/overlay.py`
- Create: `tests/unit/test_overlay_renderer.py`

Composites an overlay (title, text, namecard) on top of a visual segment. Uses FFmpeg drawtext with semi-transparent background bar. Title = centered large text. Text/namecard = lower-third bar.

Tests: overlay positioning per type, drawtext filter generation.

### Task 8: Rewrite ComposeStage

**Files:**
- Modify: `src/pipeline/stages/compose.py`
- Create: `tests/unit/test_compose_v2.py`

Complete rewrite. The new compose stage:
1. Loads storyboard.json
2. Matches TTS audio segments to scenes (by index)
3. For each scene: render visual → apply overlay → combine with audio → output scene segment
4. Concatenates all scene segments
5. Burns subtitles on final video

Falls back to MVP compose (continuous footage) if storyboard.json doesn't exist.

Tests: full pipeline mock with multiple scene types, fallback behavior.

### Task 9: Tests + lint + E2E verification

Run full test suite, ruff lint, and verify with a real storyboard.

---

## Verification

1. `uv run pytest tests/ -v` — all tests pass (existing 45 + new ~20)
2. `uv run ruff check src/ tests/` — no lint errors
3. Re-render project 1775378564 (Xi Jinping video with storyboard):
   `uv run pipeline produce --url "..." --project-id 1775378564 --locale zh-TW --start-from tts --skip-review`
4. Final video should show visual variety: clips interspersed with text cards, slides, still frames
5. `ffprobe` confirms proper duration and codec
