# Niche Visual Style Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split niche image style into medium, palette, subject, and rule elements so photo-realistic generated-image prompts keep safe palette/rules but do not inherit sketch medium contamination.

**Architecture:** `NicheTemplate` becomes the typed source for split style fields and still exposes `visual_style` as the legacy composite. The render assembler builds the final prompt from split theme fields when present, keeps `theme.visual_style` override semantics identical, and treats `skip_niche_style` as the explicit all-style override. Style Manifest surfaces split fields as separate traceability elements while leaving the v1 CLI `image_prompt_prefix -> visual_style` mapping on the composite.

**Tech Stack:** Python dataclasses, TOML config via `tomllib`, pytest unit tests, existing compose/image mock seams, Typer CLI tests.

---

### Task 1: Niche Template Split Fields

**Files:**
- Modify: `configs/niche_intro_templates.toml`
- Modify: `src/pipeline/niche_templates.py`
- Test: `tests/unit/test_niche_templates.py`

- [ ] **Step 1: Write failing template tests**

Add tests that assert:
- `parenting` loads `medium_hint`, `palette`, `subject_bias`, and `universal_rules`.
- `true-crime` loads the same four fields.
- `save_niche_template` round-trips the new fields.
- the legacy auto-split helper handles the two real shipped legacy strings exactly enough to classify their concrete fragments.

Run:

```bash
uv run pytest tests/unit/test_niche_templates.py -q
```

Expected before implementation: failures for missing attributes or missing split behavior.

- [ ] **Step 2: Implement split fields and legacy fallback**

Update `NicheTemplate` with optional string fields:

```python
medium_hint: str = ""
palette: str = ""
subject_bias: str = ""
universal_rules: str = ""
```

`load_niche_template` reads explicit keys when present. If a template lacks all four split fields but has `visual_style`, use a private heuristic splitter for legacy data only. `save_niche_template` and `_to_toml` write the four new keys and the composite `visual_style`.

- [ ] **Step 3: Hand-author real config split**

Split the actual `parenting` and `true-crime` strings already in `configs/niche_intro_templates.toml` into the four fields. Keep `visual_style` as the back-compat composite for old consumers.

- [ ] **Step 4: Verify template tests**

Run:

```bash
uv run pytest tests/unit/test_niche_templates.py -q
```

Expected after implementation: pass.

### Task 2: Prompt Assembler Split Application

**Files:**
- Modify: `src/pipeline/composer/base.py`
- Test: `tests/unit/test_image_style.py`

- [ ] **Step 1: Write failing assembler tests**

Add tests using the existing `render_scene`/image mock seam that assert exact assembled prompts for:
- photo-realistic content suppresses `medium_hint` but keeps `palette` and `universal_rules`.
- non-photo content keeps `medium_hint`, `palette`, and `universal_rules`.
- strong explicit scene subject suppresses `subject_bias`.
- `skip_niche_style: true` suppresses all niche styling.
- legacy-only `theme.visual_style` assembles identically to the old behavior.
- `theme.visual_style` still wins over `theme.style_prefix` and split fields.

Run:

```bash
uv run pytest tests/unit/test_image_style.py -q
```

Expected before implementation: failures for missing conditional assembly.

- [ ] **Step 2: Implement assembler helpers**

Add focused helpers near the generated-image branch:
- `_has_contradicting_medium(prompt: str) -> bool` for `photo`, `photograph`, `photo-realistic`, `photorealistic`, and `photographic`.
- `_has_strong_explicit_subject(prompt: str) -> bool` using conservative subject indicators already likely in scene prompts, such as named product/person noun phrases and concrete roles.
- `_assembled_niche_style(theme: dict, content: str) -> str` that returns:
  - `theme.visual_style` unchanged when present.
  - split niche fields when any of `medium_hint`, `palette`, `subject_bias`, or `universal_rules` are present.
  - `theme.style_prefix` unchanged as the legacy fallback.

- [ ] **Step 3: Wire generated_image prompt assembly**

Keep ordering as base style, `visual.style_modifier`, scene content. Preserve `style_prefix=base_style` when calling `render_generated_image` so tier selection keeps working. Do not alter duration, scene timing, transitions, or runtime.

- [ ] **Step 4: Verify assembler tests**

Run:

```bash
uv run pytest tests/unit/test_image_style.py -q
```

Expected after implementation: pass.

### Task 3: Style Manifest Elements

**Files:**
- Modify: `src/pipeline/style/manifest.py`
- Test: `tests/unit/test_style_manifest.py`

- [ ] **Step 1: Write failing manifest tests**

Add tests that:
- `build_manifest` exposes `medium_hint`, `palette`, and `subject_bias` as separate `image_prompt_prefix` elements.
- the medium descriptor warning is attached to `medium_hint`.
- `visual_style` without split fields still appears as the legacy composite element.
- `pipeline style list` output includes the split element ids.

Run:

```bash
uv run pytest tests/unit/test_style_manifest.py -q
```

Expected before implementation: failures because split elements are not emitted.

- [ ] **Step 2: Implement manifest split elements**

Emit the split elements from theme keys when present. Keep the existing `visual_style` element for legacy/composite themes. Move the medium warning scan to `medium_hint` so palette-only composites do not carry the warning.

- [ ] **Step 3: Verify manifest tests**

Run:

```bash
uv run pytest tests/unit/test_style_manifest.py -q
```

Expected after implementation: pass.

### Task 4: Full Gates and Real Scene Demo

**Files:**
- Evidence: `tmp/niche-visual-style-split/`
- Review: engineering-manager REVIEW mode

- [ ] **Step 1: Run requested unit and static gates**

Run:

```bash
uv run pytest tests/unit/test_niche_templates.py tests/unit/test_image_style.py tests/unit/test_style_manifest.py -q
uv run ruff check src/ tests/
uv run mypy src/
```

Expected: all pass.

- [ ] **Step 2: Re-render baby-walker s25**

Inspect the current storyboard scene and render target first, then re-render only scene `s25` without changing durations or global timing. Save sampled frame evidence under `tmp/niche-visual-style-split/`.

- [ ] **Step 3: Request REVIEW gate**

Dispatch the engineering-manager subagent in REVIEW mode with the branch name, acceptance criteria, test outputs, and s25 frame evidence path. Do not merge until it returns PASS. If it returns REWORK, fix the issues and repeat the relevant gates.

- [ ] **Step 4: Final branch state**

Commit the verified implementation and evidence references. Leave `src/pipeline/style/cli.py` unchanged: v1 keeps `image_prompt_prefix -> visual_style` pointed at the composite; split-field CLI add/remove is deferred.
