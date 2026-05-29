# Engineering-manager — core-usage test plan

The regression contract for the arsenal. One row per **core capability** the pipeline must
always satisfy, mapped to the pytest that proves it and a current status. I own this file:

- **SPRINT mode:** when I propose a sprint that adds/changes a capability, I append its
  acceptance test rows here as `🔲 planned` (the test path the build must create).
- **REVIEW mode:** this is my checklist. I run the listed tests via Bash, then flip rows to
  `✅ passing` / `❌ failing`. A sprint does not PASS its gate until every row it touched is
  `✅` and the listed command exits clean.

Status legend: `✅ passing` · `❌ failing` · `🔲 planned (test not yet written)` ·
`⏸️ deferred`. Skill-managed; git-tracked like `charter.md` / `standards.md`.

**Run-all command (smoke before any REVIEW verdict):**
`uv run pytest tests/unit/test_chart.py tests/unit/test_chart_anim.py tests/unit/test_callout.py tests/unit/test_style_manifest.py tests/director/test_storyboard_validator.py tests/unit/test_cli_validate.py -q`
then `uv run ruff check src/ tests/ && uv run mypy src/`.

## E1 — Charts (static) 🟢

| Capability | Test | Status |
|------------|------|--------|
| 6 chart_types render (stat_big_number, proportion_blocks, timeline, bar, comparison, line) | `tests/unit/test_chart.py` + goldens `tests/fixtures/chart/` | ✅ |
| Determinism (render twice → byte-identical) | `tests/unit/test_chart.py` (determinism smoke) | ✅ |
| chart carries own title / suppresses subtitle | `tests/unit/test_chart.py` + `overlay_rules._TEXT_VISUALS` | ✅ |

## E2 — Animation 🟢

| Capability | Test | Status |
|------------|------|--------|
| Animated reveal on line / bar / stat_big_number | `tests/unit/test_chart_anim.py` + goldens `tests/fixtures/chart_anim/` | ✅ |
| Frame generators are PURE (call twice → identical PIL) | `tests/unit/test_chart_anim.py` (determinism) | ✅ |
| Two-axes fence: `reveal_duration_sec ≤ scene_duration − 0.5s` raises | `tests/director/test_storyboard_validator.py` (animate-reveal-duration) | ✅ |
| Hold-tail caching (generator called ≤ reveal_frames) | `tests/unit/test_chart_anim.py` | ✅ |

## E3 — Overlays / callout primitive 🟢 (v1)

| Capability | Test | Status |
|------------|------|--------|
| `callout` collision-avoidance placement (vertical dodge) | `tests/unit/test_callout.py` + goldens `tests/fixtures/callout/` | ✅ |
| chart marker-labels routed through callout (static + animated) | `tests/unit/test_callout.py` / `tests/unit/test_chart_anim.py` | ✅ |
| `apply_overlay` failure raises `SceneRenderError` (loud, no demote) | `tests/unit/test_overlay_renderer.py` | ✅ |
| Overlay collision rule (`check_overlay_allowed`) | `tests/unit/test_overlay_collision_rule.py` | ✅ |
| Overlay variants (subtitles_no_overlay etc.) | `tests/unit/test_overlay_variants.py` | ✅ |
| v2 animated callout entrance (fade/slide-in) | _(test TBD)_ | 🔲 planned |

## E4 — Style Manifest 🟢 (Slices 1–2 + 4)

| Capability | Test | Status |
|------------|------|--------|
| `build_manifest` from theme + per-scene overrides | `tests/unit/test_style_manifest.py` | ✅ |
| append-only `style_log.json` | `tests/unit/test_style_manifest.py` | ✅ |
| `pipeline style list/add/remove` CLI | `tests/unit/test_style_manifest.py` | ✅ |
| anchor_image surfaced INACTIVE (dead-code removed) | `tests/unit/test_style_anchor.py` | ✅ |
| niche template load/save round-trip with split fields + legacy auto-split heuristic | `tests/unit/test_niche_templates.py` (new) | ✅ shipped Sprint 6 |
| assembler: photo-realistic prompt suppresses `medium_hint` (assembled prompt asserted) | `tests/unit/test_image_style.py` | ✅ shipped Sprint 6 |
| assembler: non-photo prompt retains `medium_hint` | `tests/unit/test_image_style.py` | ✅ shipped Sprint 6 |
| assembler: legacy-only `visual_style` composite renders identically (back-compat) | `tests/unit/test_image_style.py` | ✅ shipped Sprint 6 |
| manifest surfaces `medium_hint`/`palette`/`subject_bias` as separate elements + medium-warning re-pointed at `medium_hint` | `tests/unit/test_style_manifest.py` | ✅ shipped Sprint 6 |
| s25 real-scene demo: re-render baby-walker s25 with new assembler, frame-level confirm no surreal medium contamination | manual REVIEW evidence in `tmp/niche-visual-style-split/` | ✅ REVIEW PASS Sprint 6 |

## E5 — Validation / checkpoint 🟢 (v1) · render-truth still-gate 🟢 GREENLIT (Sprint 7, all four checks — build pending; flip rows ✅ at REVIEW)

| Capability | Test | Status |
|------------|------|--------|
| `validate_storyboard` branches all visual types incl. chart | `tests/director/test_storyboard_validator.py` (26 tests) | ✅ |
| `pipeline validate <id>` CLI exit codes (0/1/2) | `tests/unit/test_cli_validate.py` | ✅ |
| Unknown `visual.type` → error | `tests/director/test_storyboard_validator.py` | ✅ |
| **Sprint 7** — still-composite renderer is DETERMINISTIC (render twice → byte-identical; tested before any golden) | `tests/unit/test_still_gate.py` (determinism) | 🔲 planned (Sprint 7) |
| **Sprint 7** — contact-sheet assembler emits labeled sheet (scene id · visual.type · visual.path) | `tests/unit/test_still_gate.py` | 🔲 planned (Sprint 7) |
| **Sprint 7** — check 1 duplicate-frame (perceptual hash) is pure + FIRES on as-rendered dup | `tests/unit/test_still_gate_checks.py` (dup-positive) | 🔲 planned (Sprint 7) |
| **Sprint 7** — check 1 TRUE-NEGATIVE: two visibly-distinct frames → NO dup finding | `tests/unit/test_still_gate_checks.py` (dup-negative) | 🔲 planned (Sprint 7) |
| **Sprint 7** — check 2 blank/flat-substrate is pure + FIRES on a content-empty frame | `tests/unit/test_still_gate_checks.py` (blank-positive) | 🔲 planned (Sprint 7) |
| **Sprint 7** — check 2 TRUE-NEGATIVE: a legitimately-sparse-but-valid frame (`stat_big_number` chart / real photo) → NO blank finding (the cry-wolf guard — a gate that false-positives on minimal-by-design visuals gets ignored, recreating the failure) | `tests/unit/test_still_gate_checks.py` (blank-negative) | 🔲 planned (Sprint 7) |
| **Sprint 7** — END-TO-END CLEAN PASS: gate on a known-good storyboard → exits 0, ZERO findings | `tests/unit/test_still_gate.py` (clean-pass) / `tests/unit/test_cli_still_gate.py` | 🔲 planned (Sprint 7) |
| **Sprint 7** — overlay-variant field at gen-time is single-source-of-truth with `context.json` `preferred_variant` | `tests/unit/test_still_gate.py` (variant) / `tests/unit/test_storyboard.py` | 🔲 planned (Sprint 7) |
| **Sprint 7** — `pipeline storyboard still-gate <id>` CLI exit codes (0 clean / non-0 findings) | `tests/unit/test_cli_still_gate.py` | 🔲 planned (Sprint 7) |
| **Sprint 7** — check 3 OCR wrong-language: Latin-script block on a zh-TW scene → finding FIRES (not byte-exact transcript — tesseract not byte-stable) | `tests/unit/test_still_gate_checks.py` (ocr-positive) | 🔲 planned (Sprint 7) |
| **Sprint 7** — check 3 TRUE-NEGATIVE: an all-zh-TW (or numeric-only) scene → NO wrong-language finding | `tests/unit/test_still_gate_checks.py` (ocr-negative) | 🔲 planned (Sprint 7) |
| **Sprint 7** — check 3 skip-if-absent: tesseract not installed → check is SKIPPED with a loud note, gate still runs (Q4 posture) | `tests/unit/test_still_gate_checks.py` (ocr-skip) | 🔲 planned (Sprint 7) |
| **Sprint 7** — check 4 overflow/clipping: laid-out text bbox vs inner-panel inset (`frame.py` `inset_x/y/w/h`) → FIRES on s25-style clipped verbatim | `tests/unit/test_still_gate_checks.py` (overflow-positive) | 🔲 planned (Sprint 7) |
| **Sprint 7** — check 4 TRUE-NEGATIVE: text that fits within the inner-panel inset → NO overflow finding | `tests/unit/test_still_gate_checks.py` (overflow-negative) | 🔲 planned (Sprint 7) |
| **Sprint 7 — REAL-SCENE DEMO (gating):** run the gate on baby-walker DEFECT-STATE snapshot (`tmp/storyboard.BEFORE-quality-pass.json` — s24/s25/s26 verified to still carry the identical `north_america_blank_map.png`) → **all four checks fire on their real defect**: check 2 blank map, check 1 3+-reuse map, check 3 s23 English labels, check 4 s25 clipped verbatim. (Live storyboard already fixed s25 → must use the snapshot.) | fixtures `tests/fixtures/still_gate/` seeded from the snapshot + manual REVIEW evidence in `tmp/` | 🔲 planned (Sprint 7) |

## E6 — Compose efficiency / dashboard 🟡 (partly in flight)

| Capability | Test | Status |
|------------|------|--------|
| Compose dup-guard (no double-render) | `tests/unit/test_compose_dup_guard.py` | ✅ |
| Transition-change cache invalidation | `tests/unit/test_cli_compose_transition_invalidation.py` | ✅ |
| Dashboard job-queue endpoints | `tests/integration/test_jobs_endpoints.py` / `tests/unit/test_job_queue.py` | ⏸️ in flight (another agent — do not double-schedule) |

## E7 — Audio arsenal & SFX legibility 🔵 (new epic, 2026-05-26)

_No rows yet — no E7 sprint proposed. The first E7 sprint (SFX asset registry, or the SFX
layer-visibility dashboard surface) populates this section with its acceptance rows as
`🔲 planned`._

## Cross-cutting

| Capability | Test | Status |
|------------|------|--------|
| Animation-review harness | `tests/unit/test_animation_review.py` | ✅ |
| Composer base dispatch (all visual types) | `tests/unit/test_composer_base.py` | ✅ |
| Real-scene demonstration harness (canonical-scene picker + run a new capability against it) — _tooling half of Idea A; the REVIEW-gate requirement itself is in `standards.md`, this row tracks the picker/runner if/when it's built_ | _(test TBD — `tests/unit/test_demo_harness.py`)_ | 🔲 planned |
