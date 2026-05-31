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

## E5 — Validation / checkpoint 🟢 (v1) · render-truth still-gate ⚠️ REWORK (Sprint 7 — TWO-LAYER as-built, Tim-approved descope; build NOT shipped — one blocking variant gap, see sprint-log 2026-05-31)

> **Reconciled 2026-05-31 to the as-built, Tim-approved, constraint-forced design** (sprint-log
> 2026-05-30 descope): a **two-layer gate** wired into `.claude/skills/storyboard-review/SKILL.md`
> after the JSON-critic PASS, before TTS. **Layer 1** = deterministic CLI `pipeline storyboard
> still-gate <id>` running `duplicate_frame` (phash+colorhash) + `blank_substrate` (content-INSET
> dominant-color). **Layer 2** = in-session vision pass (zero extra Anthropic billing, the
> `visual-review` pattern) judging meaningfulness / wrong-language / clipping — the scoped
> model-vision use Tim authorized, reversing the blanket "NO model-vision" guard for THIS use only.
> Deterministic OCR (ex-check-3) + bbox-overflow (ex-check-4) are **superseded by Layer 2**;
> tesseract is unprovisioned here (no passwordless sudo). Variant-at-gen-time (piece C) is
> **deferred**. **REVIEW VERDICT = REWORK** (not shipped): the wired gate defaults to `plain`
> (overlays burned) at Phase 3.5, so it misses the seed reused-map defect at its real invocation
> point — green tests pass only because they force `no_overlay`. Rows below flip to fully-accepted
> ✅ only at a REVIEW PASS of the reworked build.
>
> **DoD note on the ✅ tags below:** the Layer-1 rows marked "✅ passing (run 2026-05-31)" mean the
> test is **green on the branch as I ran it**, NOT that the capability is accepted into the locked
> regression contract — the sprint is in REWORK, and per my DoD only a PASS advances a sprint's rows
> into the contract. Read them as "green-on-branch, pending acceptance," not as locked regression
> rows; they become locked ✅ at REVIEW PASS of the reworked build.

| Capability | Test | Status |
|------------|------|--------|
| `validate_storyboard` branches all visual types incl. chart | `tests/director/test_storyboard_validator.py` (26 tests) | ✅ |
| `pipeline validate <id>` CLI exit codes (0/1/2) | `tests/unit/test_cli_validate.py` | ✅ |
| Unknown `visual.type` → error | `tests/director/test_storyboard_validator.py` | ✅ |
| **Sprint 7 (Layer 1)** — still-composite renderer is DETERMINISTIC (render twice → byte-identical via `+bitexact`) | `tests/director/still_gate/test_render.py` (`test_render_scene_still_is_deterministic`) | ✅ passing (run 2026-05-31) — but see variant gap below before PASS |
| **Sprint 7 (Layer 1)** — `Finding` is a frozen dataclass with the issue shape | `tests/director/still_gate/test_model.py` | ✅ passing |
| **Sprint 7 (Layer 1)** — contact-sheet assembler emits labeled sheet (scene id · type · path) | `tests/director/still_gate/test_sheet.py` | ✅ passing |
| **Sprint 7 (Layer 1)** — check 1 duplicate-frame (phash+colorhash) is pure + FIRES on identical stills | `tests/director/still_gate/test_checks.py` (dup-positive) | ✅ passing |
| **Sprint 7 (Layer 1)** — check 1 TRUE-NEGATIVE: two visibly-distinct frames → NO dup finding | `tests/director/still_gate/test_checks.py` (dup-negative) | ✅ passing |
| **Sprint 7 (Layer 1)** — check 2 blank/flat-substrate is pure + FIRES on a content-empty frame | `tests/director/still_gate/test_checks.py` (blank-positive) | ✅ passing |
| **Sprint 7 (Layer 1)** — check 2 measured on the **content INSET** (book border excluded), not the whole frame | `tests/director/still_gate/test_checks.py` (`test_blank_substrate_measures_inset_not_whole_frame`) | ✅ passing (the `fe89cc1` post-plan correction) |
| **Sprint 7 (Layer 1)** — check 2 TRUE-NEGATIVE: a sparse-but-valid frame (busy/photo) → NO blank finding (cry-wolf guard) | `tests/director/still_gate/test_checks.py` (blank-negative) | ✅ passing |
| **Sprint 7 (Layer 1)** — `pipeline storyboard still-gate <id>` CLI exit codes (0 clean / 2 findings) | `tests/director/still_gate/test_cli.py` | ✅ passing |
| **Sprint 7 (Layer 1)** — END-TO-END CLEAN PASS: gate on a clean storyboard → exit 0, zero findings | `tests/director/still_gate/test_cli.py` (`test_still_gate_exits_0_when_clean`) | ✅ passing |
| **Sprint 7 — BLOCKING (REWORK):** gate driven through `resolve_variant` with NO `preferred_variant` in `context.json` (the real Phase-3.5 state → defaults `plain`, overlays burned) → `duplicate_frame` STILL fires on the defect-snapshot reused map. Today no test exercises the wired default path; the gate would miss its seed defect in `plain`. Fix: default the gate to `no_overlay` / run both variants / pull variant-C forward. | `tests/director/still_gate/test_cli.py` (new — no-context default path) | ❌ failing-by-omission (no test; the as-built default is `plain` which would NOT fire) |
| **Sprint 7 (Layer 2 wiring)** — `storyboard-review/SKILL.md` PASS path invokes Layer-1 CLI THEN the in-session vision pass (meaningfulness / wrong-language / clipping) before TTS; does NOT proceed with open findings | manual REVIEW evidence (SKILL Step 8 inspected 2026-05-31) + skill-wiring smoke | 🔲 planned (acceptance is the SKILL text + the variant fix; no automatable unit test for the human/vision judgment — by design) |
| **Sprint 7 — REAL-SCENE DEMO (reconciled to as-built):** run the gate on baby-walker DEFECT-STATE snapshot (`tmp/storyboard.BEFORE-quality-pass.json` — s24/s25/s26 carry the identical `north_america_blank_map.png`) → **`duplicate_frame` FIRES on the reuse** (the deterministically-catchable defect). `blank_substrate` does NOT fire on this bordered ~62%-dominant map (honest known gap — Layer-2 meaningfulness covers it). s23 English labels + s25 clip are covered by Layer-2 (wrong-language / clipping), NOT deterministic checks. | `tests/director/still_gate/test_real_scene_demo.py` | ✅ passing (asserts dup fires) — but forces `variant="no_overlay"`; the WIRED default-`plain` path is the open gap above |
| **Sprint 7 — deterministic OCR wrong-language (ex-check-3)** — Latin-script block on a zh-TW scene fires a deterministic finding | _superseded — covered by the Layer-2 vision pass; tesseract unprovisioned (no passwordless sudo)_ | ⏸️ superseded by Layer-2 |
| **Sprint 7 — deterministic OCR skip-if-absent (ex-check-3, Q4)** | _superseded — no deterministic OCR shipped_ | ⏸️ superseded by Layer-2 |
| **Sprint 7 — deterministic overflow/clipping (ex-check-4)** — laid-out text bbox vs inner-panel inset fires on s25-style clip | _superseded — covered by the Layer-2 vision pass; the novel text-bbox instrumentation was high-risk/low-verifiability here_ | ⏸️ superseded by Layer-2 |
| **Sprint 7 — overlay-variant field at gen-time (piece C)** — single-source-of-truth with `context.json` `preferred_variant`, authoritative pre-TTS | `tests/director/still_gate/` (variant) — when built | ⏸️ deferred (the gate currently reads existing `preferred_variant` via `resolve_variant`; moving the decision to gen-time is NOT done — and is one of the fix options for the BLOCKING row above) |

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
