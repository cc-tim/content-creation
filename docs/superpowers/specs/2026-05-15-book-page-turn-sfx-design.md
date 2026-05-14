# Book Page-Turn SFX — Design Spec

**Date:** 2026-05-15  
**Status:** Approved

## Goal

Play a realistic paper-rustle sound during every `book-page-turn-v2` transition automatically, without requiring any storyboard change on existing or new projects.

## SFX Asset

- **File:** `assets/sfx/page_turn.wav`
- **Source:** BigSoundBank sound #0164 (CC0, no attribution required)
- **Specs:** 48 kHz, 16-bit, stereo, −12 dBFS, 0.63 s
- **Why −12 dB:** Sits below TTS narration level; audible as a texture cue, not a foreground sound.

## Architecture

The `sfx` field is already wired end-to-end through the pipeline:

```
Transition.sfx  →  TransitionConfig.sfx  →  renderer FFmpeg amix
```

All renderers already handle SFX with `amix=inputs=2`. What is missing is auto-defaulting so the field doesn't need to be set in every storyboard.

## Design: `effective_sfx` property

Add `effective_sfx: str | None` property to `TransitionConfig` in `transitions.py`:

```python
_DEFAULT_BOOK_PAGE_SFX: Path = _REPO_ROOT / "assets" / "sfx" / "page_turn.wav"

@property
def effective_sfx(self) -> str | None:
    if self.sfx is not None:           # explicit override (including "" to opt-out)
        return self.sfx or None        # "" → None (disabled)
    if self.style in BOOK_PAGE_STYLES and _DEFAULT_BOOK_PAGE_SFX.exists():
        return str(_DEFAULT_BOOK_PAGE_SFX)
    return None
```

**Override rules:**
- `sfx` not set (None) → default SFX for book-page styles, None for others
- `sfx: ""` in storyboard → opt-out (no SFX)
- `sfx: "path/to/custom.wav"` → custom SFX

## Changes

### `src/pipeline/composer/transitions.py`

1. Add `_DEFAULT_BOOK_PAGE_SFX` constant (repo-relative Path).
2. Add `effective_sfx` property to `TransitionConfig`.
3. Update `transition_cache_key()`: hash `cfg.effective_sfx or ""` instead of `cfg.sfx or ""`. Cache keys automatically change for book-page transitions that previously had no SFX — old cached clips regenerate on next render.
4. Update all renderer `.render()` methods: replace every `cfg.sfx` reference with `cfg.effective_sfx`.

### `src/pipeline/composer/book_scene.py`

5. In `BookPageTurnV2Renderer.render()`: pass `sfx=cfg.effective_sfx` to `render_book_page_turn_v2()`.

### `assets/sfx/page_turn.wav`

Already created. No code change needed.

## Cache Invalidation

No version bump required. Changing `cfg.sfx` → `cfg.effective_sfx` in the hash means existing cached transition clips (which hashed `""` for sfx) will get a different key and re-render automatically on the next compose run.

## Scope

Applies to all styles in `BOOK_PAGE_STYLES` (`book-page-turn`, `book-page-turn-v2`, `stock-book-page-turn`). Other styles (fade, slide, wipe) unaffected.

## Testing

- `TransitionConfig(style="book-page-turn-v2", duration_sec=1.5, sfx=None).effective_sfx` → path string
- `TransitionConfig(style="book-page-turn-v2", duration_sec=1.5, sfx="").effective_sfx` → None (opt-out)
- `TransitionConfig(style="fade", duration_sec=1.0, sfx=None).effective_sfx` → None
- Cache key changes when `effective_sfx` is non-None
- End-to-end: rescene a project with book-page-turn-v2 transitions → rendered clip has non-silent audio
