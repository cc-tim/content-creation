# Book Page-Turn SFX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-apply a CC0 page-turn sound to every `book-page-turn-v2` (and all `BOOK_PAGE_STYLES`) transition, with zero storyboard changes required on existing projects.

**Architecture:** Add an `effective_sfx` property to `TransitionConfig` that returns the explicit `sfx` if set, falls back to the bundled `assets/sfx/page_turn.wav` for book-page styles, or returns `None` for everything else. Replace every `cfg.sfx` reference in the cache key and all renderers with `cfg.effective_sfx`. Opt-out: set `sfx: ""` in storyboard transition.

**Tech Stack:** Python, FFmpeg (amix audio filter already wired), `assets/sfx/page_turn.wav` (CC0, already committed)

---

## File Map

| File | Change |
|------|--------|
| `src/pipeline/composer/transitions.py` | Add `_DEFAULT_BOOK_PAGE_SFX` constant + `effective_sfx` property on `TransitionConfig`; replace `cfg.sfx` → `cfg.effective_sfx` in `transition_cache_key` and all 5 renderer `render()` methods |
| `tests/unit/test_transitions.py` | Add 5 new unit tests for `effective_sfx` behavior and cache key impact |

No other files change.

---

## Task 1: Write failing tests for `effective_sfx`

**Files:**
- Modify: `tests/unit/test_transitions.py`

- [ ] **Step 1: Add the five new test functions**

Open `tests/unit/test_transitions.py` and append these tests at the end of the file (after `test_book_page_turn_v2_renderer_emits_clip`):

```python
# ---------------------------------------------------------------------------
# effective_sfx property
# ---------------------------------------------------------------------------

def test_effective_sfx_returns_default_for_book_page_turn_v2_when_sfx_none():
    """With sfx=None, book-page-turn-v2 gets the bundled default SFX path."""
    from pipeline.composer.transitions import _DEFAULT_BOOK_PAGE_SFX
    cfg = TransitionConfig(style="book-page-turn-v2", duration_sec=1.5, sfx=None)
    assert cfg.effective_sfx == str(_DEFAULT_BOOK_PAGE_SFX)


def test_effective_sfx_returns_default_for_all_book_page_styles():
    """All BOOK_PAGE_STYLES get the default SFX when sfx is None."""
    from pipeline.composer.transitions import _DEFAULT_BOOK_PAGE_SFX
    for style in ("book-page-turn", "book-page-turn-v2"):
        cfg = TransitionConfig(style=style, duration_sec=1.5, sfx=None)
        assert cfg.effective_sfx == str(_DEFAULT_BOOK_PAGE_SFX), f"failed for {style}"


def test_effective_sfx_returns_none_for_non_book_styles():
    """Non-book styles return None even when sfx is not set."""
    for style in ("fade", "slide", "wipe", "page-turn", "none"):
        cfg = TransitionConfig(style=style, duration_sec=0.5, sfx=None)
        assert cfg.effective_sfx is None, f"expected None for {style}"


def test_effective_sfx_empty_string_opt_out():
    """sfx='' disables the default — effective_sfx returns None."""
    cfg = TransitionConfig(style="book-page-turn-v2", duration_sec=1.5, sfx="")
    assert cfg.effective_sfx is None


def test_effective_sfx_explicit_path_overrides_default():
    """An explicit sfx path is returned as-is, overriding the default."""
    cfg = TransitionConfig(style="book-page-turn-v2", duration_sec=1.5, sfx="assets/sfx/custom.wav")
    assert cfg.effective_sfx == "assets/sfx/custom.wav"


def test_cache_key_differs_for_book_page_turn_v2_with_and_without_default_sfx(tmp_path: Path):
    """Cache key changes when effective_sfx differs (default vs opt-out)."""
    a = _make_test_clip(tmp_path / "a.mp4", duration=0.5, color="red")
    b = _make_test_clip(tmp_path / "b.mp4", duration=0.5, color="blue")
    cfg_default = TransitionConfig(style="book-page-turn-v2", duration_sec=1.5, sfx=None)
    cfg_optout = TransitionConfig(style="book-page-turn-v2", duration_sec=1.5, sfx="")
    assert transition_cache_key(a, b, cfg_default) != transition_cache_key(a, b, cfg_optout)
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_transitions.py::test_effective_sfx_returns_default_for_book_page_turn_v2_when_sfx_none \
    tests/unit/test_transitions.py::test_effective_sfx_returns_default_for_all_book_page_styles \
    tests/unit/test_transitions.py::test_effective_sfx_returns_none_for_non_book_styles \
    tests/unit/test_transitions.py::test_effective_sfx_empty_string_opt_out \
    tests/unit/test_transitions.py::test_effective_sfx_explicit_path_overrides_default \
    tests/unit/test_transitions.py::test_cache_key_differs_for_book_page_turn_v2_with_and_without_default_sfx \
    -v 2>&1 | tail -20
```

Expected: all 6 FAIL with `AttributeError: 'TransitionConfig' object has no attribute 'effective_sfx'` or similar.

---

## Task 2: Implement `effective_sfx` + update cache key

**Files:**
- Modify: `src/pipeline/composer/transitions.py`

- [ ] **Step 1: Add `_DEFAULT_BOOK_PAGE_SFX` constant**

In `src/pipeline/composer/transitions.py`, directly below the line:

```python
_REPO_ROOT = Path(__file__).resolve().parents[3]
```

Add:

```python
_DEFAULT_BOOK_PAGE_SFX: Path = _REPO_ROOT / "assets" / "sfx" / "page_turn.wav"
```

- [ ] **Step 2: Add `effective_sfx` property to `TransitionConfig`**

In `src/pipeline/composer/transitions.py`, after the existing `effective_page_surface` property (around line 141), add:

```python
    @property
    def effective_sfx(self) -> str | None:
        if self.sfx is not None:
            return self.sfx or None          # "" → opt-out (None)
        if self.style in BOOK_PAGE_STYLES and _DEFAULT_BOOK_PAGE_SFX.exists():
            return str(_DEFAULT_BOOK_PAGE_SFX)
        return None
```

- [ ] **Step 3: Update `transition_cache_key` to hash `effective_sfx`**

In `transition_cache_key()`, find:

```python
    h.update((cfg.sfx or "").encode())
```

Replace with:

```python
    h.update((cfg.effective_sfx or "").encode())
```

- [ ] **Step 4: Run the new tests — they should pass now**

```bash
uv run pytest tests/unit/test_transitions.py::test_effective_sfx_returns_default_for_book_page_turn_v2_when_sfx_none \
    tests/unit/test_transitions.py::test_effective_sfx_returns_default_for_all_book_page_styles \
    tests/unit/test_transitions.py::test_effective_sfx_returns_none_for_non_book_styles \
    tests/unit/test_transitions.py::test_effective_sfx_empty_string_opt_out \
    tests/unit/test_transitions.py::test_effective_sfx_explicit_path_overrides_default \
    tests/unit/test_transitions.py::test_cache_key_differs_for_book_page_turn_v2_with_and_without_default_sfx \
    -v 2>&1 | tail -20
```

Expected: all 6 PASS.

- [ ] **Step 5: Run the full transition test suite to check for regressions**

```bash
uv run pytest tests/unit/test_transitions.py -v 2>&1 | tail -30
```

Expected: all existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/composer/transitions.py tests/unit/test_transitions.py
git commit -m "feat(transitions): add effective_sfx property with book-page default

TransitionConfig.effective_sfx returns the bundled page_turn.wav for
BOOK_PAGE_STYLES when sfx is not explicitly set. Empty string sfx opts
out. transition_cache_key now hashes effective_sfx so cache keys change
correctly when the default applies.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Update all renderers to use `effective_sfx`

**Files:**
- Modify: `src/pipeline/composer/transitions.py` (5 renderer `render()` methods)
- Modify: `src/pipeline/composer/book_scene.py` (`BookPageTurnV2Renderer.render()` call)

Each renderer currently does `if cfg.sfx:` / `cmd += ["-i", cfg.sfx]`. Replace every occurrence with `cfg.effective_sfx`.

- [ ] **Step 1: Update `XfadeRenderer.render()`**

Find (in `XfadeRenderer.render()`, around line 248):

```python
        if cfg.sfx:
            cmd += ["-i", cfg.sfx]
            audio_filter = "[2:a][3:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
        else:
            audio_filter = "[2:a]anull[a]"
```

Replace with:

```python
        if cfg.effective_sfx:
            cmd += ["-i", cfg.effective_sfx]
            audio_filter = "[2:a][3:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
        else:
            audio_filter = "[2:a]anull[a]"
```

- [ ] **Step 2: Update `BookPageTurnRenderer.render()`**

Find (in `BookPageTurnRenderer.render()`, around line 343):

```python
        if cfg.sfx:
            cmd += ["-i", cfg.sfx]
            audio_filter = "[2:a][3:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
        else:
            audio_filter = "[2:a]anull[a]"
```

Replace with:

```python
        if cfg.effective_sfx:
            cmd += ["-i", cfg.effective_sfx]
            audio_filter = "[2:a][3:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
        else:
            audio_filter = "[2:a]anull[a]"
```

- [ ] **Step 3: Update `BookPageTurnV2Renderer.render()`**

Find (in `BookPageTurnV2Renderer.render()`, around line 435):

```python
            return render_book_page_turn_v2(
                frame_a=frame_a,
                frame_b=frame_b,
                out=out,
                width=width,
                height=height,
                fps=fps,
                duration_sec=cfg.duration_sec,
                page_count=cfg.page_count or 2,
                page_surface=cfg.effective_page_surface,
                sfx=cfg.sfx,
            )
```

Replace with:

```python
            return render_book_page_turn_v2(
                frame_a=frame_a,
                frame_b=frame_b,
                out=out,
                width=width,
                height=height,
                fps=fps,
                duration_sec=cfg.duration_sec,
                page_count=cfg.page_count or 2,
                page_surface=cfg.effective_page_surface,
                sfx=cfg.effective_sfx,
            )
```

- [ ] **Step 4: Update `LicensedClipRenderer.render()`**

Find (in `LicensedClipRenderer.render()`, around line 473):

```python
        if cfg.sfx:
            cmd += ["-i", cfg.sfx]
            audio_filter = "[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
        else:
            audio_filter = "[1:a]anull[a]"
```

Replace with:

```python
        if cfg.effective_sfx:
            cmd += ["-i", cfg.effective_sfx]
            audio_filter = "[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
        else:
            audio_filter = "[1:a]anull[a]"
```

- [ ] **Step 5: Update `OverlayAssetRenderer.render()`**

Find (in `OverlayAssetRenderer.render()`, around line 542):

```python
        if cfg.sfx:
            cmd += ["-i", cfg.sfx]
            audio_filter = "[2:a][3:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
        else:
            audio_filter = "[2:a]anull[a]"
```

Replace with:

```python
        if cfg.effective_sfx:
            cmd += ["-i", cfg.effective_sfx]
            audio_filter = "[2:a][3:a]amix=inputs=2:duration=first:dropout_transition=0[a]"
        else:
            audio_filter = "[2:a]anull[a]"
```

- [ ] **Step 6: Run the full transition test suite**

```bash
uv run pytest tests/unit/test_transitions.py -v 2>&1 | tail -30
```

Expected: all tests PASS.

- [ ] **Step 7: Run the broader test suite for regressions**

```bash
uv run pytest tests/unit/ -x -q 2>&1 | tail -20
```

Expected: all tests PASS (or pre-existing failures only — check `git stash && uv run pytest tests/unit/ -q 2>&1 | tail -5` to compare baseline if unsure).

- [ ] **Step 8: Commit**

```bash
git add src/pipeline/composer/transitions.py
git commit -m "feat(transitions): wire effective_sfx into all renderers

All five renderer render() methods and BookPageTurnV2Renderer's call
to render_book_page_turn_v2 now use cfg.effective_sfx instead of
cfg.sfx, so the bundled page-turn sound plays automatically for every
book-page-turn transition.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Smoke-test end-to-end on the baby-walker project

- [ ] **Step 1: Clear the transition cache for the project**

```bash
rm -f output/projects/20260504-115232-baby-walker-story/compose/transitions/*.mp4
echo "Transition cache cleared"
```

- [ ] **Step 2: Rescene s1 to regenerate a transition clip with SFX**

```bash
uv run pipeline compose rescene --project-id 20260504-115232-baby-walker-story --scene s1 2>&1 | grep -E "transition\.|compose\."
```

Expected log lines like:
```
transition.render   key=... style=book-page-turn-v2
compose.complete    path=output/projects/.../compose/final_zh-TW_no_overlay.mp4
```

- [ ] **Step 3: Verify a transition clip has non-silent audio**

```bash
python3 - <<'EOF'
import subprocess, glob, json
clips = sorted(glob.glob("output/projects/20260504-115232-baby-walker-story/compose/transitions/*.mp4"))
if not clips:
    print("No transition clips found — check cache clear step")
else:
    clip = clips[0]
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", clip],
        capture_output=True, text=True
    )
    streams = json.loads(r.stdout).get("streams", [])
    audio = [s for s in streams if s["codec_type"] == "audio"]
    print(f"Clip: {clip}")
    print(f"Audio streams: {len(audio)}")
    if audio:
        print(f"Codec: {audio[0]['codec_name']}, sample_rate: {audio[0]['sample_rate']}")
EOF
```

Expected: 1 audio stream, codec=aac, sample_rate=48000.

- [ ] **Step 4: (Optional) listen to the transition clip directly**

```bash
# On Linux with PulseAudio/PipeWire:
ffplay -autoexit output/projects/20260504-115232-baby-walker-story/compose/transitions/*.mp4 2>/dev/null | head -1
```

---

## Self-Review Notes

- `effective_sfx` uses `_DEFAULT_BOOK_PAGE_SFX.exists()` guard so tests without the asset still work if the file is absent (returns None gracefully)
- `sfx=""` → `self.sfx is not None` is True → `return self.sfx or None` → `return None` ✓ opt-out works
- Cache key hashes `effective_sfx or ""` — existing transitions cached with `sfx=None` (hashed as `""`) will now hash the SFX path → different key → automatic re-render ✓
- `stock-book-page-turn` uses `BookPageTurnRenderer` (not V2) — it also gets the SFX via Step 2 in Task 3 ✓
- `LicensedClipRenderer` and `OverlayAssetRenderer` also updated — consistent behavior across all modes ✓
