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

## E5 — Validation / checkpoint 🟢 (v1)

| Capability | Test | Status |
|------------|------|--------|
| `validate_storyboard` branches all visual types incl. chart | `tests/director/test_storyboard_validator.py` (26 tests) | ✅ |
| `pipeline validate <id>` CLI exit codes (0/1/2) | `tests/unit/test_cli_validate.py` | ✅ |
| Unknown `visual.type` → error | `tests/director/test_storyboard_validator.py` | ✅ |

## E6 — Compose efficiency / dashboard 🟡 (partly in flight)

| Capability | Test | Status |
|------------|------|--------|
| Compose dup-guard (no double-render) | `tests/unit/test_compose_dup_guard.py` | ✅ |
| Transition-change cache invalidation | `tests/unit/test_cli_compose_transition_invalidation.py` | ✅ |
| Dashboard job-queue endpoints | `tests/integration/test_jobs_endpoints.py` / `tests/unit/test_job_queue.py` | ⏸️ in flight (another agent — do not double-schedule) |

## E7 — Audio arsenal & SFX legibility 🔵 (new epic, 2026-05-26)

**Music/audio-axis (first E7 sprint — engineering shipped on master `12bfce3`; EM REVIEW
2026-05-29 = ADVISE, NOT PASS — the epic item stays 🔵 until the real-scene demo + real tracks
land and EM re-REVIEWs). Engineering rows below are `✅` (run by me on the master worktree); the
real-scene demo row is `🔲` because the music library is empty so the demo could not run.**

| Capability | Test | Status |
|------------|------|--------|
| `Scene.music_mood` + `Theme.music_default_mood` schema (inherit-on-blank, back-compat defaults) | `tests/unit/test_storyboard_music_mood.py` | ✅ |
| Mood resolution (`resolve_effective_moods` walk; unknown mood raises) + library load (blank `file` skipped) | `tests/unit/test_music_resolve.py` | ✅ |
| Cue planning (`plan_cues`: scenes.json spans → merged cues; `"none"` breaks a run) | `tests/unit/test_music_cues.py` | ✅ |
| `build_bed` full-length 48k/stereo bed, crossfades at abutting cues, **clamped to total video length** (two-axes fence: bed cannot extend runtime) | `tests/integration/test_music_bed.py` | ✅ |
| `duck_bed` sidechain-duck measurable (bed >8 dB below speech, recovers >4 dB in pauses) + `mux_music_onto_final` idempotent (no music doubling) + video stream preserved | `tests/integration/test_music_duck.py` | ✅ |
| `pipeline compose music` CLI (dry-run cue plan; loud `Exit(1)` + suggested_fix on missing bed/scenes.json/storyboard) | `tests/unit/test_cli_compose_music.py` | ✅ |
| **Real-scene demo (spec point 5, gating for 🟢):** baby-walker s19→s23 dark→hopeful arc rendered with real free tracks; narration stays intelligible under the bed; artifact saved | _manual REVIEW evidence (TBD — needs licensed tracks; was empty-library at REVIEW)_ | 🔲 planned |

_(The two older E7 items — SFX asset registry, SFX layer-visibility dashboard surface — remain
designed-not-built with no rows; their first sprints populate them when proposed.)_

## Cross-cutting

| Capability | Test | Status |
|------------|------|--------|
| Animation-review harness | `tests/unit/test_animation_review.py` | ✅ |
| Composer base dispatch (all visual types) | `tests/unit/test_composer_base.py` | ✅ |
| Real-scene demonstration harness (canonical-scene picker + run a new capability against it) — _tooling half of Idea A; the REVIEW-gate requirement itself is in `standards.md`, this row tracks the picker/runner if/when it's built_ | _(test TBD — `tests/unit/test_demo_harness.py`)_ | 🔲 planned |
