# Image Style Consistency & Edit Mode Design

**Date:** 2026-04-28
**Scope:** Style hierarchy for generated images, per-scene edit mode (img2img + inpaint), scene image history (regret mechanism), `storyboard set` dotted-field support.

---

## Problem Statement

Three issues observed in project 1777161293 and generalised for all future projects:

1. **Style drift across scenes** — `niche_intro_templates.toml` `visual_style` is prepended as `style_prefix` to every scene prompt, but scene prompts already embed their own style words. The two fight, producing inconsistent output (s7b, s12b rendered as watercolor while s1 rendered as semi-realistic).

2. **Concept loss on regeneration** — When a scene is rescened (e.g. after a style_prefix change), the new text-to-image generation ignores the composition/concept of the previous image. Good elements are lost (e.g. s5's extreme size contrast: enormous parent hand vs. tiny child gripping a shoe).

3. **No undo** — Once a cached image is overwritten by rescene, there is no way to recover the previous version.

---

## Design

### 1. Style Hierarchy

Three levels compose left-to-right into a single style prefix string:

```
Level 1 (niche):  niche_intro_templates.toml → visual_style
Level 2 (video):  storyboard.json → theme.visual_style          (overrides level 1 when present)
Level 3 (scene):  storyboard.json → scene.visual.style_modifier  (mood modifier, appended)
```

Prompt assembly in `render_generated_image`:
```python
base_style = theme.get("visual_style") or theme.get("style_prefix", _FALLBACK_STYLE)
modifier   = visual.get("style_modifier", "")
content    = visual.get("prompt", "abstract background")
full_prompt = ", ".join(part for part in [base_style, modifier, content] if part)
```

**Key constraint:** `visual.prompt` carries **content/concept only** — no style words. Style belongs exclusively in `theme.visual_style` (video level) or `visual.style_modifier` (scene level). This rule is enforced in the DirectStage system prompt.

**Fallback chain:**
- `theme.visual_style` present → use it, ignore niche template
- `theme.visual_style` absent → use niche template `visual_style`
- No niche template → use `_FALLBACK_STYLE`

**Immediate fix for project 1777161293:**
```json
"theme": {
  "visual_style": "warm semi-realistic illustration, soft digital painting, cozy domestic setting, gentle charcoal outline"
}
```
Strip style words from per-scene `visual.prompt`, leaving concept only. Fix s5 and s12b concept prompts (see Appendix).

---

### 2. Edit Mode

When a rescene should preserve elements from the existing image (composition, character sizes, layout) rather than generating from the text prompt alone, mark the scene with edit mode fields.

#### Storyboard fields (all in `visual` dict, all optional)

| Field | Type | Default | Description |
|---|---|---|---|
| `edit_mode` | bool | `false` | Enable edit mode for this scene |
| `edit_type` | `"img2img" \| "inpaint"` | `"img2img"` | Which edit API to call |
| `edit_instruction` | str | `""` | What to change / what to preserve |
| `edit_strength` | float 0–1 | `0.3` | img2img only — how much to deviate from source |

#### Example storyboard entry

```json
{
  "type": "generated_image",
  "prompt": "enormous adult hand and worn shoe filling the frame, tiny toddler fingers gripping the lace",
  "edit_mode": true,
  "edit_type": "img2img",
  "edit_instruction": "keep the size-contrast composition, shift style to warm semi-realistic illustration",
  "edit_strength": 0.3
}
```

#### Edit type dispatch

| `edit_type` | Provider | API endpoint | Best for |
|---|---|---|---|
| `img2img` | fal.ai | `fal-ai/flux/dev/image-to-image` | Keep composition, change style |
| `inpaint` | OpenAI | `images.edit` | Surgical fix to a region, keep rest |

#### Dispatch logic in `render_generated_image`

```python
if visual.get("edit_mode"):
    existing = _find_cached_image(scene_id, work_dir)
    if existing and existing.exists():
        _save_to_history(existing, scene_id, work_dir)   # always save before overwrite
        return _edit_image(visual, existing, base_style, modifier, work_dir, ...)
    # no cached image → fall through to normal generation

# normal text-to-image path (unchanged)
```

**After successful rescene in edit mode:** `edit_mode` is auto-cleared to `false` in storyboard.json so a subsequent `compose rescene` generates fresh rather than editing the edit.

#### Basic implementation goal

Wire up the API calls with minimal tuning. The infrastructure (history, field dispatch, auto-clear) matters more than prompt engineering at this stage — that improves iteratively as we see results.

---

### 3. Scene Image History (Regret Mechanism)

**Location:** `{work_dir}/compose/image_history/{scene_id}_{YYYYMMDDTHHMMSS}.png`

**Triggered:** Any time a cached scene image is about to be overwritten — whether by edit mode or a normal `compose rescene` that produces a different image. Saving happens **before** the new generation call.

**Auto-purge:** On every `compose rescene` or `compose reburn` run, history entries older than **7 days** are silently deleted.

#### New CLI commands

```bash
# List history entries for a scene
uv run pipeline compose history --scene s5 --project-id <ID>
# output:
#   s5_20260428T143022.png   2 hours ago
#   s5_20260427T091145.png   1 day ago

# Restore most recent history entry (re-runs image_to_video conversion)
uv run pipeline compose restore --scene s5 --project-id <ID>

# Restore a specific timestamp
uv run pipeline compose restore --scene s5 --project-id <ID> --timestamp 20260427T091145
```

#### `storyboard show` integration

When a scene has history entries, the `storyboard show` table adds `[hist:N]` in the scene row — visible at a glance without a separate command.

---

### 4. `storyboard set` Dotted-Field Extension

Current `_ALLOWED_FIELDS`: `narration`, `narration_est_sec`, `pause_after_sec`, `section`

New dotted fields routed into `scene.visual[subfield]`:

| CLI field | Maps to | Type |
|---|---|---|
| `visual.style_modifier` | `scene.visual["style_modifier"]` | free text |
| `visual.edit_mode` | `scene.visual["edit_mode"]` | bool (`true`/`false`) |
| `visual.edit_type` | `scene.visual["edit_type"]` | `"img2img"` \| `"inpaint"` |
| `visual.edit_instruction` | `scene.visual["edit_instruction"]` | free text |
| `visual.edit_strength` | `scene.visual["edit_strength"]` | float |

```bash
uv run pipeline storyboard set s5 visual.edit_mode=true
uv run pipeline storyboard set s5 visual.edit_type=img2img
uv run pipeline storyboard set s5 visual.edit_instruction="keep composition, fix style"
uv run pipeline storyboard set s5 visual.edit_strength=0.3
uv run pipeline storyboard set s5 visual.style_modifier="darker, more tense"
```

Coercion: `edit_mode` → bool, `edit_strength` → float, others → str.

---

### 5. DirectStage Prompt Update

Add to the DirectStage system prompt under the `visual` field instructions:

> `visual.prompt` must describe **concept and content only** — subject, action, spatial relationships, mood. Do NOT include style words (e.g. "watercolor", "sketch", "semi-realistic"). Style is controlled globally via `theme.visual_style`. Per-scene mood variations go in `visual.style_modifier`.

---

### 6. Provider Extensions

New methods on `GenImageProvider` (or a sibling `EditImageProvider`):

```python
def edit_img2img(
    image_path: Path,
    prompt: str,
    strength: float,          # 0.0–1.0; 0.3 default
    out_path: Path,
    size: str = "1792x1024",
) -> ProviderResult: ...

def edit_inpaint(
    image_path: Path,
    prompt: str,              # describes the desired result in the edited region
    out_path: Path,
    size: str = "1792x1024",
) -> ProviderResult: ...
```

Both fail gracefully with `ProviderError` → fallback to normal generation with a warning log.

---

### 7. What This Enables Going Forward

- **Style gallery comparison** — history dir gives us before/after pairs for every rescene, enabling future automated quality comparison.
- **Better inpaint masking** — once basic inpaint works, add `visual.edit_mask_region` (e.g. `"top-right"`) to guide the mask generation.
- **Auto edit-mode suggestion** — if a scene's concept prompt changes but composition was good, system could suggest `edit_mode: true` rather than full regeneration.
- **Strength calibration** — track which strength values produced good results per niche; feed into future defaults.

---

## Appendix: Immediate Fixes for Project 1777161293

**s5 concept prompt** (visual.prompt):
```
enormous adult hand and worn shoe filling the frame, tiny toddler fingers gripping the lace tightly refusing to let go, extreme size contrast between adult and child
```

**s12b concept prompt** (visual.prompt):
```
parent standing at closed bedroom door, hand raised to knock, face showing worry and confusion; child silhouette visible through frosted glass, turned away, unreachable
```

**s7b** — rescene after `theme.visual_style` is set; style drift will resolve automatically.

**`theme.visual_style`** for this project:
```
warm semi-realistic illustration, soft digital painting, cozy domestic setting, gentle charcoal outline
```
