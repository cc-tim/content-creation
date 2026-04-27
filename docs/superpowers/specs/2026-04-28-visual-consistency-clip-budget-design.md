# Visual Consistency, Clip Budget & Intro Template Design

**Date:** 2026-04-28
**Status:** Approved
**Scope:** DirectStage + ComposeStage + niche config system

---

## Problem Statement

Three related issues found in project 1777161293 (parenting/zh-TW):

1. **Source overuse** — no enforcement stops Claude from assigning `clip` to nearly every scene, making the video feel like a copy of the source.
2. **Duplicate source frames** — the source video reuses the same illustration panel at multiple timestamps; multiple `clip` scenes end up identical (confirmed: s1 and s8 pixel-identical).
3. **Generated image style conflict** — generated images span multiple incompatible styles (anime, chibi, watercolor) with no visual coherence and no relationship to our intended niche aesthetic.
4. **Intro copies source** — s1 uses a source clip, making the opening look like the original video.

---

## Design Principles

- **We define the visual identity; source is raw material.** Generated images carry the visual story. Source clips supplement where real footage adds genuine value.
- **Style = niche_profile + source_hints + story_tone** (in that priority order). We can reference the source style but are not bound by it.
- **Niche templates grow on first use.** First produce for a new niche triggers a user confirmation; the confirmed choice becomes the template for all future videos in that niche.
- **Two enforcement levels.** Clip budget (Section A) is soft — violations log warnings and surface at the review gate, never block the pipeline. Intro template (Section B) is hard — s1 using a source clip is forbidden in the Claude prompt, but the pipeline never errors; if Claude ignores the instruction, the review gate highlights it for human correction.

---

## Architecture

```
DirectStage (storyboard generation)
  ├── A. Source clip budget  →  inject "≤60% of scenes may be clip/still_frame"
  └── B. Intro template      →  per-niche s1 rule; confirm + save on first use

ComposeStage (video rendering)
  ├── C. StyleAnchorExtractor  →  source suitability + niche style → lock all generated images
  └── D. Duplicate frame guard →  pHash each clip; replace duplicates with generated_image
```

---

## Section A — Source Clip Budget

### Constraint field

`constraints.py` gains two fields:

```python
max_source_clip_pct: float = 0.60   # soft limit on clip+still_frame scene count
source_suitability: str = ""         # "high" | "medium" | "low" — set at compose time
```

### DirectStage prompt injection

```
VISUAL BUDGET CONSTRAINT:
- At most {pct}% of scenes may use type "clip" or "still_frame" from source.
- For a 20-scene video: max {n} clip scenes.
- Prefer generated_image for explanation/analysis/concept scenes.
- If source suitability is low (repetitive panels, talking-head, watermarked), reduce to 30%.
```

### Post-generation validation

After Claude returns the storyboard, `DirectStage` counts `clip + still_frame` scenes.  
If count > threshold: log warning, list offending scene IDs, surface at review gate.  
No auto-correction — human decides whether to override.

---

## Section B — Per-Niche Intro Template

### Config file: `configs/niche_intro_templates.toml`

```toml
[parenting]
# s1 must open with original material — never a source clip
intro_type = "generated_image"
intro_prompt_hint = "parent and child in a warm home moment, sketch style, relatable, no text"
visual_style = "clean educational sketch, minimal line art, simple warm tones, no clutter, conceptual"
anchor_prompt = "parent and child in a calm home moment, sketch style, minimal color"
rationale = "Parenting source videos reuse the same illustration panels; our hook must be original"

[true-crime]
intro_type = "text_card"
intro_prompt_hint = "Dark background, bold white hook — one sentence, mid-action, no setup"
visual_style = "cinematic still, dramatic lighting, documentary aesthetic, high contrast"
anchor_prompt = "empty corridor at night, single dim light, tense silence, photorealistic"
rationale = "True-crime hooks land harder as stark text than clips"
```

### DirectStage flow

1. Look up niche in `niche_intro_templates.toml`.
2. **Template found** → inject into Claude prompt:
   > "Scene s1 MUST use visual type `{intro_type}` with prompt hint: `{intro_prompt_hint}`. Never use `clip` or `still_frame` for s1."
3. **No template** → still forbid `clip` for s1; at the review gate, Claude Haiku generates 2–3 style suggestions for the user to pick or rewrite; confirmed choice is written to the TOML and committed.
4. **`--skip-review` with no template** → fall through to a built-in default: `generated_image` with prompt `"opening scene for a {niche} video, {visual_style_if_known}, welcoming, original"`. No blocking, no prompts. Template remains unset until the next interactive run.

---

## Section C — Style Anchor & Visual Identity

### New component: `src/pipeline/composer/style_anchor.py`

Responsibilities:
1. **Source suitability assessment** — extract frame at ~10% of source duration; call Claude Haiku Vision with: *"Is this source footage clean and visually unique, or repetitive/cluttered? Answer: high / medium / low and one sentence why."* Result stored in `context.json` as `source_suitability`.
2. **Style synthesis** — combine: niche `visual_style` profile (primary) + source hints (reference, not rule) + story tone from storyboard. Produce a `style_descriptor` (~30 words). Stored in `context.json` as `style_descriptor`. If no niche profile exists yet, Claude Haiku drafts one from source + story; user approves at review gate; saved to TOML.
3. **Anchor image** — check `configs/channels/<profile>/style_anchor.png`. If exists, reuse (no API call). If not, generate one with `anchor_prompt` + `visual_style` at production tier with project seed. Save to `configs/channels/<profile>/style_anchor.png` for reuse across all videos in the niche.

### Clip budget adjustment from suitability

| Source suitability | Clip budget override |
|-|-|
| `high` | Use constraint default (60%) |
| `medium` | Recommend 40% in DirectStage prompt |
| `low` | Recommend 25%; DirectStage generates more scenes using generated_image |

### Applying to all generated images

Every `render_generated_image` call receives:

- `style_prefix: str` — prepended to the scene prompt: `f"{style_descriptor}, {scene_prompt}"`
- `seed: int` — `int(hashlib.md5(project_id.encode()).hexdigest()[:8], 16)` (deterministic across processes; cache handles dedup on re-renders)
- `tier: str` — always `"production"` when style anchor is active (`fal-ai/flux-pro/v1.1`)
- `anchor_image: Path | None` — passed as `reference_image` to `GeminiImageProvider` when credits available; ignored by `GenImageProvider` (no-op, future slot)

### Changes to `composer/image.py`

`render_generated_image` signature gains:
```python
style_prefix: str = "",
seed: int | None = None,
anchor_image: Path | None = None,
```

The prompt becomes `f"{style_prefix}, {prompt}".strip(", ")`.  
Cache key includes seed: `hashlib.md5(f"{prompt}|{seed}".encode())`.

### Changes to `~/.claude/bin/gen-image.py`

No changes needed. `--seed` already passes through to fal.ai payload. Production tier already supported via `--tier production`.

---

## Section D — Duplicate Source Frame Guard

### Mechanism

In `ComposeStage`, before full render of each `clip` scene:

1. Extract one thumbnail frame from the source at the scene's `timestamp_sec` using `ffmpeg -vframes 1`.
2. Compute perceptual hash (`imagehash.phash`, 8×8).
3. Track all seen hashes for this video in a `set`.
4. If new hash distance ≤ 8 from any seen hash → **duplicate detected**.
5. Replace the scene's visual with `generated_image` using scene narration + `style_descriptor` as prompt. Log: `compose.clip.duplicate_detected scene=sN replaced_with=generated_image`.
6. Add hash to seen set either way.

**Storyboard/render divergence is intentional.** When a clip is replaced at render time, `storyboard.json` still shows `clip` — the storyboard reflects creative intent, the render reflects reality. The replacement is logged so it's traceable. If the user wants to make the replacement permanent, they edit the storyboard manually (or via `storyboard set`).

This automatically fixes s1/s8 — whichever arrives second gets replaced with a generated image in the niche style.

### New dependency

Add to `pyproject.toml`: `imagehash>=4.3`

---

## File Change Summary

| File | Change |
|---|---|
| `src/pipeline/constraints.py` | Add `max_source_clip_pct`, `source_suitability` fields |
| `src/pipeline/stages/direct.py` | Inject clip budget, intro template, style hint into Claude prompt; review-gate prompts for missing niche templates |
| `src/pipeline/stages/compose.py` | Call `StyleAnchorExtractor`; pass style/seed/anchor to image renderer; add duplicate frame guard |
| `src/pipeline/composer/style_anchor.py` | **New** — suitability assessment, style synthesis, anchor image generation |
| `src/pipeline/composer/image.py` | Accept `style_prefix`, `seed`, `anchor_image`; use production tier when anchor active |
| `configs/niche_intro_templates.toml` | **New** — seeded with `parenting` profile |
| `pyproject.toml` | Add `imagehash>=4.3` |

---

## Project 1777161293 Remediation (after system is built)

1. Run storytelling + proofreader subagents for full narration review (fix s2 wording etc.)
2. Re-run `DirectStage` with new clip budget + parenting intro template
3. Recompose: duplicate frame guard handles s1/s8 automatically
4. All generated images use parenting niche style (sketch/minimal, not conflicting watercolor)

---

## Out of Scope

- Midjourney / Ideogram as providers (budget constraint; revisit if Gemini reference doesn't satisfy after recharge)
- Qwen for Asian-aesthetic images (achievable via prompt engineering for now)
- Hard block on clip budget violations (soft warning is sufficient)
- Auto-correcting storyboard clip overuse (human decides at review gate)
