# Image fit-to-frame editing — design

**Status:** Spec (approved sections; pending implementation plan)
**Author:** Claude (Opus 4.7), with Tim
**Date:** 2026-05-13

## Problem

Composer wraps scene images in a frame (currently only `open_book_page`). Canvas size comes from `src/pipeline/composer/base.py:RESOLUTIONS` — 16:9 → 1280×720, 9:16 → 720×1280. For 1280×720 the book-page inset is ~947×484 (aspect ≈ 1.96, derived from `BookSceneSpec.open_book`). Source images frequently don't match:

- `s1` baby-walker (Jesus manuscript): 557×534 (aspect 1.04) → letterboxed with dark brown bars left/right
- `s2` (Maria Apollonia portrait): 419×549 (aspect 0.76) → heavy bars, and the painting's framing already puts the child close to the edge — the visible region inside the inset feels truncated
- `s3` (Learning to walk, 1905): 934×1536 (aspect 0.61) → portrait inside landscape inset, dominant dark padding
- `s4` (Victorian satirical illustration): 3868×2601 (aspect 1.49) → mild mismatch; could fit with smart-crop

Result: dark padding distracts from the "open book page" feel, and in some scenes the subject lands too close to a hard edge.

## Goal

A unified, idempotent "fit-to-inset" step that ensures every scene's image fills the target box without clipping the subject. Operates on `article_image` and `image` scenes; skips `text_card`.

Per scene, decide between three strategies — chosen by Claude in the skill session (no extra vision API call):
- `leave-as-is` — aspect diff small enough to ignore
- `crop` — smart-crop preserves the subject (PIL, free)
- `outpaint` — extend the image with FAL Flux Pro Kontext (~$0.04/edit)

Auto-runs during `/produce` (after storyboard finalization, before TTS) and `/scene-update` (per-scene). Also invocable manually ("refit s2"). Cached by content hash so re-runs are free.

## Non-goals

- Tier selection across multiple edit models (Kontext is the only model in scope; premium fallback deferred)
- Multiple frame styles (only `open_book_page` exists; module is structured so adding more is one function)
- Parallel/batched API calls (sequential is fine at typical scene counts)
- Auto-rerun if user manually edits `refit_path` (treated as deliberate override)
- Editing source raw assets in place (always sidecar)

## Architecture

Four pieces, each with one job:

### 1. `~/.claude/bin/gen-image-edit.py` (new shared helper)

CLI sibling to `gen-image.py`. Calls FAL Flux Pro Kontext for image-conditioned edits.

```
gen-image-edit.py \
  --source <path> \
  --instruction "<text>" \
  --target-aspect <W:H> \
  --output <path> \
  [--mode outpaint|generic] \
  [--no-cache]
```

- Reuses `~/.claude/bin/keymanager.py` for FAL key rotation
- Caches output by SHA-256 of `(source bytes + instruction + target aspect + mode)`
- On success: prints absolute output path
- On key exhaustion: prints `[KEY EXHAUSTED] <provider> <key-name>` and the reset command (same contract as `gen-image.py`)
- `--mode outpaint` prepends a canonical instruction template ("Extend the image to the target aspect ratio. Preserve the existing subject and composition unchanged. Continue context naturally — match the source's medium, color palette, and period style.")

### 2. `src/pipeline/composer/refit.py` (new module — pure, testable)

```python
def canvas_size(storyboard: dict) -> tuple[int, int]:
    """Wrapper around base.get_resolution(storyboard['aspect_ratio'])."""

def target_box(theme: dict, canvas_w: int, canvas_h: int) -> tuple[int, int]:
    """Return (inset_w, inset_h) for theme.frame_style. open_book_page -> BookSceneSpec.open_book(...).inset.
    Raises ValueError for unknown frame_style; this is the extension point for future styles."""

def needs_refit(src_w: int, src_h: int, target_w: int, target_h: int,
                threshold: float = 0.08) -> bool:
    """True iff |src_aspect - target_aspect| / target_aspect > threshold."""

def apply_crop(source: Path, out: Path, target_w: int, target_h: int,
               bias: tuple[float, float] = (0.5, 0.5)) -> Path:
    """PIL center-or-biased crop to target aspect. bias=(cx, cy) in [0,1]."""

def apply_outpaint(source: Path, out: Path, target_w: int, target_h: int,
                   instruction: str) -> Path:
    """Shell out to gen-image-edit.py --mode outpaint."""

def effective_image_path(visual: dict) -> Path:
    """Return refit_path if present and exists; else path. Used by composer."""
```

No skill, no CLI, no I/O beyond what the strategies need. Unit-testable.

### 3. `skills/fit-image/SKILL.md` (project skill)

User-facing layer; this is where Claude acts as the vision LLM.

For each candidate scene:
1. Cheap skip-check: aspect-diff threshold + cache hit
2. Read source image with the Read tool (vision step — Claude sees the image natively)
3. Decide `crop` vs `outpaint` from a one-line reasoning trace, then pick crop bias or write the outpaint instruction
4. Call `refit.apply_crop(...)` or `refit.apply_outpaint(...)`
5. Update storyboard: `pipeline storyboard set <scene> visual.refit_path=<path>`
6. Append to `refit_log.json`

Skill UX:
```
fit-image                    # current project, all scenes, dry-run
fit-image --apply            # all scenes, write edits + update storyboard
fit-image s2 s7 --apply      # specific scenes only
fit-image --project-id <id>  # explicit project
```

Default mode is dry-run; prints the per-scene decision table. `/produce` and `/scene-update` always call with `--apply`.

### 4. Composer integration

One-line touch to `src/pipeline/composer/frame.py` and any other module that reads `visual.path` (likely `image.py`, `image_history.py`). Each callsite calls `refit.effective_image_path(visual)` instead of reading `visual["path"]` directly. No FFmpeg filter change required.

## Decision logic (in the skill)

```
for scene in storyboard.scenes:
  if scene.visual.type not in {"article_image", "image"}: skip
  src = read scene.visual.path
  if needs_refit(src.size, target_box) is False: leave-as-is
  if scene.visual.refit_path exists AND src.mtime <= refit.mtime: cached
  else:
    # Vision step: Claude reads the image
    subject, position = identify_subject(image)
    if smart_crop_preserves_subject(subject, position, target_aspect):
       decision = crop, bias = (cx, cy)
    else:
       decision = outpaint, instruction = f"Extend horizontally; preserve {subject}; continue {style_hint}"
  apply(decision)
```

Sanity floor:
- Source < 480 px on either axis AND target much larger → prefer `outpaint`
- Source much higher resolution than target AND aspect diff mild → prefer `crop`

## Data flow

```
/produce  → storyboard finalized → human review gate
              ↓ (approved)
          fit-image --apply
              ↓ per scene
              ├─ skip-check (aspect diff < 8%? cached?)
              ├─ Read source image (vision step)
              ├─ decide → crop | outpaint | leave-as-is
              ├─ apply (PIL crop, or gen-image-edit.py → FAL Kontext)
              └─ pipeline storyboard set visual.refit_path=...
              ↓
          refit_log.json updated
              ↓
          pipeline produce --start-from tts
              ↓
          compose reads effective_image_path(visual)
```

`/scene-update s2`: same per-scene path, one iteration.

Manual: `fit-image s2 --apply` (or `--project-id <id>`).

## Storyboard schema change

```python
scene.visual = {
  "type": "article_image" | "image" | "text_card",
  "path": "raw/.../foo.jpg",
  "refit_path": "edits/s2_outpaint_3f9a1b.png",  # NEW, optional
  ...
}
```

- Absent field = unchanged behavior. No migration; old projects unaffected until they re-run fit-image.
- Rollback: delete the field (or `pipeline storyboard set s2 visual.refit_path=null`).

## On-disk layout

```
output/projects/<id>/
├── edits/
│   ├── s2_outpaint_3f9a1b.png
│   ├── s7_crop_8d2e44.png
│   └── refit_log.json
└── storyboard.json   # updated with visual.refit_path
```

`refit_log.json` entries:
```json
{
  "scene_id": "s2",
  "decision": "outpaint",
  "rationale": "Source 419x549 portrait; target ~2:1 landscape; cropping would lose vertical composition of the painting. Outpainting horizontally.",
  "source_path": "raw/parenting/baby-walker/assets/Kraeck_Maria_Apollonia_of_Savoy_Stupinigi.jpg",
  "source_hash": "sha256:abc...",
  "source_size": [419, 549],
  "target_size": [947, 484],
  "output_path": "edits/s2_outpaint_3f9a1b.png",
  "instruction": "Extend the painting horizontally...",
  "model": "fal-ai/flux-pro/kontext",
  "cost_estimate_usd": 0.04,
  "post_crop": false,
  "ts": "2026-05-13T14:22:18Z"
}
```

## Integration points

- **`/produce` skill** — after `pipeline storyboard show` review is approved, before `pipeline produce --start-from tts`, run `fit-image --apply` on the project. Runs even when `--skip-review` is set (correctness, not a review concern).
- **`/scene-update` skill** — after `pipeline storyboard set ...`, run `fit-image <scene_id> --apply`. Cached decisions are free.
- **Manual** — `fit-image` invoked directly; dry-run by default.

## Error handling

| Failure | Behavior |
|---|---|
| `[KEY EXHAUSTED]` from gen-image-edit.py | Report provider/key + reset command; record `decision=failed_quota`; leave `refit_path` unset; compose uses letterbox fallback. |
| FAL API 5xx / network error | Retry once with 5s backoff; second failure → `decision=failed_api`. |
| Output aspect drifts from target by >1% | PIL post-crop to target; record `post_crop=true`. If still >5% off → `failed_aspect`. |
| Source path missing | Fail loud (storyboard bug). |
| Storyboard write fails mid-batch | Each `pipeline storyboard set` runs as its own command; partial progress is durable. `refit_log.json` records what was actually written. |

Letterbox fallback in `frame.py` stays untouched — when `refit_path` is missing/failed, the existing `force_original_aspect_ratio=decrease` + pad still produces a watchable frame.

## Testing

Unit (`tests/composer/test_refit.py`):
- `target_box(theme={"frame_style": "open_book_page"}, 1280, 720)` returns `(947, 484)` within ±1 px (and aspect ≈ 1.96 holds at 1920×1080 too)
- `needs_refit` returns `False` for aspect diff `< 8%`, `True` otherwise
- `apply_crop` output preserves target aspect within 1 px and writes to the requested output path
- `effective_image_path` returns `refit_path` when present and existing, else `path`

Integration:
- Tiny fixture image + mocked `gen-image-edit.py` (returns a pre-baked output, no real FAL calls in CI)
- Verifies the skill's storyboard updates and `refit_log.json` content

Manual smoke:
- Run `fit-image --apply` on `20260504-115232-baby-walker-story`
- Re-render scenes s1–s5; visually verify no dark bars, no clipped subjects
- Confirm rerun produces `decision=cached` for all five

## Cost

Typical project (~38 scenes):
- Most scenes are `crop` or `leave-as-is` (free)
- ~5–10 scenes need `outpaint` × $0.04 = $0.20–$0.40
- Caching makes reruns free

Well within the $50/month FAL budget.

## YAGNI / Out of scope

- Tier selection across multiple edit models (Kontext only; premium fallback deferred until quality complaints)
- Frame styles other than `open_book_page` (none exist today; `target_box` is the single extension point)
- Parallel API calls (sequential at ~1–2s per edit is fine)
- Auto-rerun when user manually overrides `refit_path` (treat as deliberate)
- Editing source raw assets in place
