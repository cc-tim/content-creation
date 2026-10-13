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
`uv run pytest tests/unit/test_chart.py tests/unit/test_chart_anim.py tests/unit/test_callout.py tests/unit/test_style_manifest.py tests/director/test_storyboard_validator.py tests/unit/test_cli_validate.py tests/unit/toon tests/unit/test_composer_toon.py tests/unit/test_compose_v2.py tests/unit/test_image_sequence.py tests/unit/test_media_paths.py tests/unit/test_loud_failure_fence.py tests/unit/test_cli_compose.py tests/unit/test_clip_renderer.py tests/director/still_gate -q`
then `uv run ruff check src/ tests/ && uv run mypy src/`.
Toon integration (run on the hub for goldens + parity + cadence):
`uv run pytest --integration tests/integration/toon tests/unit/toon tests/unit/test_composer_toon.py tests/unit/test_cli_doctor.py -q`.
E10 LLM facade (merged to master `2add7c2`, 2026-09-29):
`uv run pytest tests/unit/test_llm.py tests/unit/test_llm_guard.py tests/unit/test_llm_call_sites.py tests/unit/test_conftest_tripwire.py tests/unit/test_direct_metadata.py tests/unit/test_direct.py tests/unit/test_analyze.py tests/unit/test_config.py tests/unit/test_cli_doctor.py -q`.
The real-CLI half, `uv run pytest --integration tests/integration/test_llm_cli.py -q`, spends a
trivial amount of subscription quota: 3 Haiku calls.

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

## E5 — Validation / checkpoint 🟢 (v1) · render-truth still-gate 🟢 SHIPPED (Sprint 7 — TWO-LAYER, Tim-approved descope; EM REVIEW PASS 2026-05-31)

> **Shipped 2026-05-31 (EM REVIEW PASS, re-review of the reworked build)** as the as-built,
> Tim-approved, constraint-forced design: a **two-layer gate** wired into
> `.claude/skills/storyboard-review/SKILL.md` after the JSON-critic PASS, before TTS. **Layer 1** =
> deterministic CLI `pipeline storyboard still-gate <id>` running `duplicate_frame` (phash+colorhash)
> + `blank_substrate` (content-INSET dominant-color); exit 0 clean / 1 tool-error / 2 findings.
> **Layer 2** = in-session vision pass (zero extra Anthropic billing, the `visual-review` pattern)
> judging meaningfulness / wrong-language / clipping — the scoped model-vision use Tim authorized,
> reversing the blanket "NO model-vision" guard for THIS use only. Deterministic OCR (ex-check-3) +
> bbox-overflow (ex-check-4) are **superseded by Layer 2**; tesseract is unprovisioned here (no
> passwordless sudo). Variant-at-gen-time (piece C) is **deferred** (the principled form of the
> variant fix; the `no_overlay` default is the accepted minimal fix). The original REWORK gap (gate
> defaulted to `plain`, missing the seed reused-map defect) is **FIXED** — `resolve_variant` now
> defaults to `no_overlay`, demonstrated to fire `duplicate_frame` on the defect snapshot via the
> wired path. See sprint-log 2026-05-31 RE-REVIEW PASS.

| Capability | Test | Status |
|------------|------|--------|
| `validate_storyboard` branches all visual types incl. chart | `tests/director/test_storyboard_validator.py` (26 tests) | ✅ |
| `pipeline validate <id>` CLI exit codes (0/1/2) | `tests/unit/test_cli_validate.py` | ✅ |
| Unknown `visual.type` → error | `tests/director/test_storyboard_validator.py` | ✅ |
| **Sprint 7 (Layer 1)** — still-composite renderer is DETERMINISTIC (render twice → byte-identical via `+bitexact`) | `tests/director/still_gate/test_render.py` (`test_render_scene_still_is_deterministic`) | ✅ |
| **Sprint 7 (Layer 1)** — `Finding` is a frozen dataclass with the issue shape (M-4: `Severity = Literal["error","warning"]`) | `tests/director/still_gate/test_model.py` | ✅ |
| **Sprint 7 (Layer 1)** — contact-sheet assembler emits labeled sheet (scene id · type · path) | `tests/director/still_gate/test_sheet.py` | ✅ |
| **Sprint 7 (Layer 1)** — check 1 duplicate-frame (phash+colorhash) is pure + FIRES on identical stills | `tests/director/still_gate/test_checks.py` (dup-positive) | ✅ |
| **Sprint 7 (Layer 1)** — check 1 TRUE-NEGATIVE: two visibly-distinct frames → NO dup finding | `tests/director/still_gate/test_checks.py` (dup-negative) | ✅ |
| **Sprint 7 (Layer 1)** — check 2 blank/flat-substrate is pure + FIRES on a content-empty frame | `tests/director/still_gate/test_checks.py` (blank-positive) | ✅ |
| **Sprint 7 (Layer 1)** — check 2 measured on the **content INSET** (book border excluded), not the whole frame | `tests/director/still_gate/test_checks.py` (`test_blank_substrate_measures_inset_not_whole_frame`) | ✅ (the `fe89cc1` post-plan correction) |
| **Sprint 7 (Layer 1)** — check 2 TRUE-NEGATIVE: a sparse-but-valid frame (busy/photo) → NO blank finding (cry-wolf guard) | `tests/director/still_gate/test_checks.py` (blank-negative) | ✅ |
| **Sprint 7 (Layer 1)** — `pipeline storyboard still-gate <id>` CLI exit codes (0 clean / 1 tool-error / 2 findings); I-1 missing-asset → exit 1, no traceback | `tests/director/still_gate/test_cli.py` | ✅ (exit-1 hardening verified live at REVIEW) |
| **Sprint 7 (Layer 1)** — END-TO-END CLEAN PASS: gate on a clean storyboard → exit 0, zero findings | `tests/director/still_gate/test_cli.py` (`test_still_gate_exits_0_when_clean`) | ✅ |
| **Sprint 7 — WIRED DEFAULT VARIANT (was the REWORK blocker, now FIXED):** gate driven through `resolve_variant` with NO `preferred_variant` in `context.json` (the real Phase-3.5 state) defaults to **`no_overlay`** (NOT `plain`) → `duplicate_frame` FIRES on the defect-snapshot reused map. Malformed/unreadable context.json also falls back to `no_overlay` (M-3 guard). | `tests/director/still_gate/test_real_scene_demo.py` (`test_wired_default_variant_catches_dup_on_snapshot`) + `test_render.py` (`test_resolve_variant_defaults_to_no_overlay`) | ✅ (demonstrated firing via the wired path at REVIEW) |
| **Sprint 7 (Layer 2 wiring)** — `storyboard-review/SKILL.md` Step 8 invokes Layer-1 CLI THEN the in-session vision pass (meaningfulness / wrong-language / clipping) before TTS; reads per-scene stills from `still_gate_scenes/<id>.png` (M-5); refuses TTS on any non-zero exit (0/1/2 documented) | manual REVIEW evidence (SKILL Step 8 re-read + exit-1 branch tightened 2026-05-31) | ✅ (acceptance = the SKILL wiring; the human/vision judgment is by-design not unit-testable) |
| **Sprint 7 — REAL-SCENE DEMO (gating, DoD step-6):** gate on baby-walker DEFECT-STATE snapshot (`tmp/storyboard.BEFORE-quality-pass.json` — s24/s25/s26 carry the identical `north_america_blank_map.png`) → **`duplicate_frame` FIRES on the reuse** via the wired default path. `blank_substrate` does NOT fire on this bordered ~62%-dominant map (honest known gap — Layer-2 meaningfulness covers it). s23 English labels + s25 clip covered by Layer-2, NOT deterministic checks. | `tests/director/still_gate/test_real_scene_demo.py` | ✅ (both the forced-`no_overlay` demo and the wired-default regression assert dup fires) |
| **Sprint 7 — deterministic OCR wrong-language (ex-check-3)** — Latin-script block on a zh-TW scene fires a deterministic finding | _superseded — covered by the Layer-2 vision pass; tesseract unprovisioned (no passwordless sudo)_ | ⏸️ superseded by Layer-2 |
| **Sprint 7 — deterministic OCR skip-if-absent (ex-check-3, Q4)** | _superseded — no deterministic OCR shipped_ | ⏸️ superseded by Layer-2 |
| **Sprint 7 — deterministic overflow/clipping (ex-check-4)** — laid-out text bbox vs inner-panel inset fires on s25-style clip | _superseded — covered by the Layer-2 vision pass; the novel text-bbox instrumentation was high-risk/low-verifiability here_ | ⏸️ superseded by Layer-2 |
| **Sprint 7 — overlay-variant field at gen-time (piece C)** — single-source-of-truth with `context.json` `preferred_variant`, authoritative pre-TTS | `tests/director/still_gate/` (variant) — when built | ⏸️ deferred (the gate currently reads existing `preferred_variant` via `resolve_variant`; moving the decision to gen-time is NOT done — and is one of the fix options for the BLOCKING row above) |

### E5 Sprint 10 — loud-failure sweep, part 1 🟢 (EM REVIEW PASS 2026-09-29, `bb16aa0`; merged to master `53b1df3`)

Spec: `docs/superpowers/specs/2026-09-29-e5-loud-failure-sweep-design.md` (§9 acceptance, §10
tests). Every row was run by the EM at REVIEW on the Mac worktree. The red-first ledger is in
`docs/superpowers/plans/2026-09-29-e5-loud-failure-sweep.md`.

"Mutation → red" means the EM broke that fence in a `git archive` scratch copy of `bb16aa0` and
the named test failed. 18 of 18 went red; the scratch source matched HEAD afterwards.

| Capability | Test | Status |
|------------|------|--------|
| T1: a generic visual failure refuses assembly; the reason names the `visual` step and the exception; no `s1_final*.mp4`, no `s1_black.mp4` | `tests/unit/test_compose_v2.py::test_generic_visual_failure_refuses_assembly_without_black` | ✅ (mutation → red: black fallback re-added) |
| T2: an overlay-rule collision (`text_top` on a `text_card`, real `check_overlay_allowed`) refuses assembly with the collision reason | `tests/unit/test_compose_v2.py::test_overlay_rule_violation_refuses_assembly` | ✅ (mutation → red: black fallback re-added) |
| T3: a compartment failure refuses assembly (no silent drop) | `tests/unit/test_compose_v2.py::test_compartment_failure_refuses_assembly` | ✅ (mutation → red: compartment exception suppressed) |
| T4: a post-visual failure on a framed scene raises `SceneRenderError` and leaves neither frame-suffixed cache path | `tests/unit/test_compose_v2.py::test_render_one_scene_post_visual_failure_raises_and_leaves_no_cache` | ✅ (mutation → red: black fallback re-added) |
| T5: an exception escaping `_render_one_scene` leaves no cached black stand-in | `tests/unit/test_compose_v2.py::test_escaped_scene_exception_leaves_no_cached_black` | ✅ (mutation → red: gather loop writes black; gather cleanup removed) |
| T6: a refused compose re-run doesn't cache-hit; it renders again and refuses again | `tests/unit/test_compose_v2.py::test_refused_compose_rerun_does_not_cache_hit` | ✅ (mutation → red: black fallback re-added) |
| T7: a failed `image_sequence` image raises `SceneRenderError` naming the image and the provider error; no black lavfi source | `tests/unit/test_image_sequence.py::test_failed_image_raises_scene_render_error_not_black` | ✅ (mutation → red: the failed image silently skipped) |
| T8: one media-path resolver (absolute / project / repo / cwd / missing / expanduser / dedupe), and the validator and renderers agree on project-relative clip and image paths | `tests/unit/test_media_paths.py` (11 tests) | ✅ (mutation → red: clip cwd resolver restored; refit raw path; no repo-root candidate) |
| T9: a project-relative clip renders from the project root end to end (the Sprint 9 smoke defect) | `tests/unit/test_compose_v2.py::test_project_relative_clip_renders_from_project_root` | ✅ (mutation → red: clip cwd resolver restored) |
| T10: the still-gate forwards `project_root` to `render_scene` | `tests/director/still_gate/test_render.py::test_render_scene_still_forwards_project_root` | ✅ (mutation → red: forwarding dropped) |
| T11: fence: no `_black_screen` / `_black_clip`; `color=c=black` only inside `_silence_gap` (AST); no `Path.cwd()` in clip / refit / compose / validator | `tests/unit/test_loud_failure_fence.py` (3 tests) | ✅ (mutation → red: black fallback re-added; a new black source in `text_card.py`; clip and validator cwd resolvers restored) |
| Red-first holds: the EM re-adds the black fallback → T1, T2 and T11 go red; restores the cwd resolver → T8 and T9 go red | EM mutation in a `git archive` scratch copy | ✅ Black fallback (P1+P2) → T1, T2, T4, T6, T11b, T11c red. cwd resolver → T8, T9, T11a red. Also: re-run at red commit `a7a113b` → 9 failed; `045c5d6` and `54b3f69` red |
| Live fault-injection smoke (Mac, scratch `PIPELINE_OUTPUT_DIR`): assembles with a non-black project-relative clip → a corrupt clip refuses with step, reason and fix, and leaves no `s1_final*` → re-run refuses again → restored file assembles → an overlay collision refuses | manual evidence `tmp/e5-sweep/smoke/` (builder, `f4f0854`) + `tmp/e5-sweep/smoke/em-review-bb16aa0/` (EM re-run at HEAD) | ✅ 5 of 5 at `bb16aa0`; s1 luma 124.4 (testsrc bars, eyeballed). The builder's `PIPELINE_CLAUDE_BIN` tripwire was vacuous (the branch predates E10). No Claude call happened by construction: there is no source video |
| Hub path audit: no clip or article_image path in any hub storyboard resolves differently under the new resolver | EM-run read-only script on the hub (the hub's `git status` was unchanged) | ✅ 18 storyboards in 12 projects; 42 `article_image.path`, 22 `refit_path` and 6 `clip.path` fields; **0 disagreements** for existing files. The 3 `TBD/` placeholders differ only in the path the error names (the validator blocks them) |
| Regression suites green (compose_v2, validator, refit, still_gate, cli_compose*, clip_renderer, compose_dup_guard, composer_base, composer_toon, chart); full suite 0 failed; ruff and mypy clean | `uv run pytest -q` + ruff + mypy | ✅ Touched suites 157 passed / 8 skipped (environment and golden-policy skips only). Branch 1378 passed / 59 skipped. **Merged tree** (post-E10 master `2add7c2` + branch) 1440 / 62. ruff clean; mypy clean (160 files on the branch, 161 merged) |

**Regressions added by the build's review rounds** (red first, in the ledger; the EM ran and
mutation-checked each):

| Capability | Test | Status |
|------------|------|--------|
| RF1: an unreadable cached scene is deleted and refused as `cached scene` | `tests/unit/test_compose_v2.py::test_unreadable_cached_scene_is_deleted_and_refused` | ✅ |
| RF2: an ffmpeg failure in the second mux leaves neither cache file; the reason carries the stderr tail | `tests/unit/test_compose_v2.py::test_second_mux_failure_leaves_neither_cache_file` | ✅ (mutation → red: I1 cleanup removed) |
| RF3: several failed scenes are all named; a good `s10` stays cached | `tests/unit/test_compose_v2.py::test_several_failed_scenes_all_reported_and_good_scene_stays_cached` | ✅ |
| RF4: a rerun after a failed image regenerates only that image | `tests/unit/test_image_sequence.py::test_rerun_after_failed_image_regenerates_only_that_image` | ✅ (mutation → red: the failed image skipped) |
| RF5: `storyboard still-gate` with cwd elsewhere renders a project-relative `article_image` | `tests/director/still_gate/test_cli.py::test_still_gate_resolves_project_relative_image_with_cwd_elsewhere` | ✅ (mutation → red: refit raw path; still-gate forwarding dropped) |
| RF6: a legacy `{sid}_black.mp4` marker is dropped on cache hit; the scene re-renders | `tests/unit/test_compose_v2.py::test_legacy_black_standin_dropped_and_rerendered` | ✅ (mutation → red: marker ignored). Live: EM smoke run 7 |
| RF7: the cache-hit gate probes **both** cached files; a truncated `no_overlay` file forces a re-render | `tests/unit/test_compose_v2.py::test_unreadable_no_overlay_cache_file_forces_rerender` | ✅ (mutation → red: probe only `scene_final`). Live: EM smoke run 8 |
| RF8: `reburn` refuses while legacy black markers exist | `tests/unit/test_cli_compose.py::test_reburn_refuses_when_legacy_black_standins_exist` | ✅ (mutation → red: refusal removed). Live: EM smoke run 6; proceeds after the rebuild |
| RF9: refusal text has no doubled scene-id prefix | `tests/unit/test_compose_v2.py::test_scene_failure_reason_has_no_duplicate_scene_id_prefix` | ✅ (mutation → red) |
| RF10: image_sequence's `suggested_fix` names the real project id | `tests/unit/test_image_sequence.py::test_failed_image_suggested_fix_uses_real_project_id` | ✅ (mutation → red) |
| RF11: `restore` invalidates the frame-suffixed cache finals too | `tests/unit/test_cli_compose.py::test_restore_invalidates_frame_suffixed_cache_variants` | ✅ (mutation → red) |
| C1/C2: a missing clip source raises `SceneRenderError` listing the candidates it tried (was `FileNotFoundError`) | `tests/unit/test_clip_renderer.py` (`test_render_clip_no_source`, `test_render_clip_missing_path_lists_the_candidates_it_tried`) | ✅ |
| Part 1b (planned, not built): an interrupted scene-cache write never leaves a file where the cache check reads (temp file + `os.replace`) | _(test TBD, e.g. a kill-mid-mux test)_ | 🔲 planned (ROADMAP Later, top) |

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

## E8 — Two-machine workflow & render portability 🔵 (Sprint 8 = item 1: hub (A) gate ADVISE 2026-09-24, cleared to merge; (B) Mac rows pending)

Spec: `docs/superpowers/specs/2026-09-24-e8-cross-platform-fonts-design.md`. Acceptance is split:
**(A) hub rows gate merge**, **(B) Mac rows gate 🔵→🟢** (Tim supplies the artifacts; the EM
follow-up REVIEW flips them). Golden policy: hub-canonical, golden compare SKIPPED on darwin,
determinism tests everywhere.

| Capability | Test | Status |
|------------|------|--------|
| (A) Resolver resolves by NAME: all 4 role×weight → `Noto {Sans,Serif} CJK TC {Regular,Bold}`; hub sans-bold = `NotoSansCJK-Bold.ttc` **index 3** (locks HK→TC fix) | `tests/unit/test_fonts.py` | ✅ (hub gate, EM REVIEW 2026-09-24) |
| (A) Resolver precedence (`PIPELINE_FONT_DIRS` > fc-match > known dirs) + TTC face scan by name + accepts Super-OTC/per-weight/.otf packaging | `tests/unit/test_fonts.py` | ✅ (hub gate, EM REVIEW 2026-09-24) |
| (A) Loud failure: nothing found → `FontResolutionError` with platform `suggested_fix`; `verify_fontconfig_family` rejects fc-match substitution (`Nonexistent Font XYZ`) | `tests/unit/test_fonts.py` | ✅ (hub gate, EM REVIEW 2026-09-24) |
| (A) Call sites raise, never degrade: `_title_font`, `running_out`, `rich_slide`/chart/callout propagate `FontResolutionError`; compose-start verifies theme font family once | `tests/unit/test_font_callsites.py` | ✅ (hub gate, EM REVIEW 2026-09-24) |
| (A) Static fence: no `/usr/share/fonts`, `/System/Library/Fonts`, `load_default(`, stray `ImageFont.truetype(`, drawtext `fontfile=`, or `Path("output/` literals in `src/pipeline` | `tests/unit/test_font_callsites.py` | ✅ (hub gate, EM REVIEW 2026-09-24) |
| (A) Outro drawtext uses `drawtext_font_arg` (fontconfig TC pattern), no absolute font path | `tests/unit/test_font_callsites.py` (or `tests/unit/test_outro_builder.py`) | ✅ (hub gate, EM REVIEW 2026-09-24) |
| (A) Render truth: glyph-distinctness probes (PIL / drawtext / libass) — two CJK strings differ and neither equals the .notdef render | `tests/integration/test_cjk_render_truth.py` (`--integration`) | ✅ (hub gate, EM REVIEW 2026-09-24) |
| (A) Golden policy: darwin → skip w/ hub-canonical reason; `UPDATE_GOLDENS` on non-linux → error; `PIPELINE_GOLDEN_STRICT=1` compares; chart/chart_anim/callout migrated to shared helper, fixtures unchanged | `tests/unit/test_golden_policy.py` + `tests/golden_policy.py` | ✅ (hub gate, EM REVIEW 2026-09-24) |
| (A) `pipeline doctor` exit 0/1 per check; `--out` saves probe PNGs | `tests/unit/test_cli_doctor.py` | ✅ (hub gate, EM REVIEW 2026-09-24) |
| (A) Output paths honour `PipelineConfig().OUTPUT_DIR` (migrate CLI, gallery index, composer gallery path) | `tests/unit/test_output_paths.py` | ✅ (hub gate, EM REVIEW 2026-09-24) |
| (A) Full suite collects cleanly (`test_memory_sync.py` importorskip) — 0 errors, 0 failures | `uv run pytest -q` | ✅ (hub gate, EM REVIEW 2026-09-24) |
| (A) Hub real-scene before/after: baby-walker s11/s31/s24 + outro | manual evidence `tmp/e8-fonts/hub/` | ✅ (hub gate, EM REVIEW 2026-09-24) |
| (B) Mac: ffmpeg buildconf has freetype/fontconfig/libass/harfbuzz; drawtext + subtitles filters | manual evidence (Tim, spec §8B step 1) | 🔲 planned |
| (B) Mac: `pipeline doctor` exit 0 + probe PNGs | manual evidence `tmp/e8-fonts/mac/` | 🔲 planned |
| (B) Mac: `pytest -q -rs` 0 failed/0 errors, only golden-policy skips new; render-truth integration passes | manual evidence (Tim) | 🔲 planned |
| (B) Mac real-scene: s11/s31/s24 frames show Noto TC glyphs (no tofu, not PingFang), layout matches hub | manual evidence `tmp/e8-fonts/mac/` | 🔲 planned |
| (B, informational — does not gate) Mac `PIPELINE_GOLDEN_STRICT=1` golden match result | recorded in sprint-log | ⏸️ informational |

## E9 — Toon engine & resource bank 🟢 v0 SHIPPED (Sprint 9; EM REVIEW PASS 2026-09-28, master `2f6fb35`, after two REWORK rounds)

Spec: `docs/superpowers/specs/2026-09-27-toon-bank-v0-design.md`. §8 is the source for these
rows; the duration-fence row comes from §5 and the cache row from §6. The golden policy follows
E8: goldens are hub-canonical, compared on linux only via `tests/golden_policy.py`, skipped
elsewhere with a counted reason, and minted with `UPDATE_GOLDENS=1` on the hub only.

**History:**
- REVIEW 1 (Mac, feature branch) = REWORK: three test gaps.
- REVIEW 2 (hub pass, `af00aa9`) = REWORK:
  - R1: 24→30 fps judder in compose;
  - R2: the doctor-hint assertion.
- REVIEW 3 (`2f6fb35`, EM-run on both machines) = **PASS**. Every row below is ✅, except
  two Tim-acked ⏸️ deferrals that don't gate.
- The R1/R2 fixes were mutation-checked by the EM in a `git archive` scratch copy:
  - bank fps 24 → the guard and cadence tests go red;
  - `COMPOSE_FPS` 25 → the guard goes red;
  - doctor hint deleted → the doctor test goes red;
  - restored → all green.

| Capability | Test | Status |
|------------|------|--------|
| Bank loader: every v0 YAML under `assets/toon/bank/` loads into a typed `Bank`; every item carries `picked:` provenance; a missing or unknown field fails with the file and the field path | `tests/unit/toon/test_bank.py` | ✅ |
| Scene validation: an unknown bank item / set spot / camera / icon name → error naming the scene file and the path inside it | `tests/unit/toon/test_scene.py` | path: ✅ · scene-file name: ✅ via **Sprint 11 row S11-8** (follow-up REVIEW PASS `d1c346c`) |
| Wordless rule (locale-portability fence in code): any free-text field or unknown field in a scene → error; graphics, bubbles and screens accept icon-registry names only | `tests/unit/toon/test_scene.py` + `tests/unit/toon/test_kit.py::test_engine_and_kit_draw_no_text` | ✅ (a few non-text timing and flicker fields are still ignored; not a wordless breach; E9 item 2a) |
| Timing: a beat outside its shot → error; `at: {sentence: n}` anchors resolve (narration split into sentences, audio duration shared out by character count) | `tests/unit/toon/test_scene.py` | ✅ |
| **Two-axes fence (spec §5):** the rendered toon clip lasts exactly as long as the narration. Narration longer → the last shot holds, still boiling. Narration shorter than the last beat → load warning, and the clip is cut at the narration's end. A toon scene cannot extend runtime | `tests/unit/toon/test_scene.py` + `tests/unit/test_composer_toon.py` + `tests/unit/toon/test_render.py::test_clip_has_exact_frame_count_and_cache_hits` (`--integration`; 38 frames = round(1.25 s × 30)) | ✅ |
| Engine: projection and IK maths; draw-order cases from the tryout (desk between camera and character or not; arms raised behind the head); the per-shot layer override is honoured | `tests/unit/toon/test_engine_math.py` + `tests/unit/toon/test_character.py` + `tests/unit/toon/test_order.py` | ✅ (draw order mutation-checked 3/3 at REVIEW 2) |
| Determinism: `frame(scene, bank, t)` rendered twice gives identical bytes, and identical bytes again from a worker process; no global random state (boil seeds from item keys + `floor(t·12)`) | `tests/unit/toon/test_render.py` (`test_frame_is_deterministic`, `test_parallel_equals_serial`) + `tests/unit/toon/test_pen.py` | ✅ (plus: `frame(t)` is byte-identical at bank fps 24 and 30, EM-checked at REVIEW 3) |
| Clip cache key (spec §6) covers the scene file, the bank files it uses, the `src/toon` sources, the engine version and `fps`: editing a used bank YAML or an engine source re-renders | `tests/unit/toon/test_render.py` | ✅ |
| **Golden frames, hub-only:** three scene-001 key frames plus the Tim model sheet via `assert_matches_golden`; skipped off-linux with the hub-canonical reason; minted on the hub only and eyeballed; hub cairo version recorded next to the fixtures | `tests/unit/toon/test_goldens.py` + `tests/fixtures/toon/goldens/` | ✅ Hub 4/4 with `UPDATE_GOLDENS` unset, no fixture churn (REVIEW 3). `PROVENANCE.md` corrected: the Mac differs by 1 px / 1 level on `s001_01.50` only (informational) |
| Pipeline adapter: `render_scene` dispatches `toon` for both a `scene:` reference and inline `shots`; any load/render failure raises `SceneRenderError` with a `suggested_fix` (no `text_card` fallback, no cached black stand-in); `toon` is **not** in `overlay_rules._TEXT_VISUALS` (narration subtitle kept) | `tests/unit/test_composer_toon.py` + `tests/unit/test_compose_v2.py::test_scene_render_error_leaves_no_cached_black_fallback` | ✅ |
| Storyboard validator `toon` branch: a storyboard toon scene with a bad bank name or a free-text field fails at the review gate (`pipeline validate` exit 2) | `tests/unit/test_composer_toon.py` (validator cases) + EM live run | ✅ |
| CLI `pipeline toon validate\|render\|sheet` is registered on the pipeline CLI; `validate` exits 0 when clean and non-zero on errors; `sheet` writes the bank review sheets (model sheet, pose and prop contact sheets) | `tests/unit/toon/test_cli.py` | validate/render/sheet (model sheet): ✅ · pose/prop contact sheets: ⏸️ deferred to E9 item 2d (Tim acked 2026-09-28; does not gate); **held** past Sprint 11 until Tim's new style pick (spec §11.4) |
| `pipeline doctor` toon check: cairo loads and a one-frame smoke render works; a missing cairo gives a loud FAIL with a platform `suggested_fix` | `tests/unit/toon/test_cli.py::test_check_toon_passes_here` + `tests/unit/test_cli_doctor.py::test_check_toon_fails_with_install_hint_when_cairo_is_missing` | ✅ (R2 fixed: the test injects `OSError("dlopen failed")` and asserts `brew install cairo` + `libcairo2`; it goes red with the hint deleted) |
| `pipeline doctor` toon check passes (exit 0) **on both machines** | EM-run doctor, both machines | ✅ Mac 17/17 (cairo 1.18.4), hub 17/17 (cairo 1.18.0), REVIEW 3 at `2f6fb35` |
| **Pipeline smoke (hub):** a two-scene storyboard (a `clip` plus a `toon` scene) composes end to end; the final contains both scenes with subtitles; the toon segment matches its narration length; the join into compose's concat doesn't judder | manual evidence, hub `tmp/toon-v0/compose-smoke/` (`rescene-30fps.log`, `judder-30fps.txt`) + EM probe `/tmp/em-judder.sh` | ✅ (REVIEW 3) `toon_s2` 30/1, 403 frames = 13.433 s against 13.44 s of narration. EM whole-segment probe: the final tracks the raw cadence step for step (corr 0.93); every moving step keeps ≥72% of its raw size (median 88%); no introduced duplicates; zh-TW subtitles kept |
| **R1 fps fence:** the toon clip renders at the compose concat rate; a test fails if either rate changes alone | `tests/unit/test_composer_toon.py::test_toon_fps_matches_compose_concat` | ✅ (mutation-checked in both directions) |
| **R1 cadence, measurable judder:** a scene-001 shot-1 camera push, rendered at the bank fps and run through compose's exact concat normalisation, has no near-duplicate step; red on 24 fps | `tests/integration/toon/test_cadence.py` (`--integration`) | ✅ Green on both machines. EM mutation to 24: red, 8/45 steps at 1, 6, 11, …, 36 (every 5th). Rendered via `render_frames`, not the adapter; the adapter's 30 fps is pinned by the 38-frame count test and the hub smoke's ffprobe |
| **Acceptance: scene 001 (real-scene demo, gating):** `assets/toon/scenes/001-lioness-dishes.yaml` renders a clip that matches `output/own-show/scenes/001-lioness-dishes/animatic_v2_bulb.mp4` in shots, timing and look (key-frame side-by-side), and **Tim confirms it still meets his bar** | `tests/integration/toon/test_parity_001.py` (`--integration`) + `tmp/toon-v0/scene001/side_*.png` + Tim's words in the sprint-log | ✅ Parity worst **0.058** (12.2 s; limit 0.5), unchanged since `c29fc52`; the earlier "0.0435" was an EM mis-record. Tim 2026-09-28: "looks good" (trembling → soft boil), then picked 30 fps / drawings 12/s |
| Non-goal fence (spec §1): the bank holds only picked items (no campfire, no unpicked items), and `assets/toon/scenes/` holds only `001-lioness-dishes.yaml` (no EP1 scenes) | `tests/unit/toon/test_scene_001.py` + `tests/unit/toon/test_bank.py::test_v0_bank_holds_exactly_the_picked_items` + diff | ✅ (re-checked at REVIEW 3) |
| Full suite collects and passes with `src/toon` packaged (`cairocffi` in deps, `src/toon` in hatch `packages`); `ruff check src/ tests/` and `mypy src/` clean | `uv run pytest -q` + ruff + mypy | ✅ REVIEW 3 at `2f6fb35`: hub 1380 passed / 22 skipped / 0 failed (its first run hit the unrelated trust-gate flake, see arsenal-state); Mac 1343 / 59 / 0; ruff clean; mypy clean (159 files) on both machines |

### E9 Sprint 11: finishing own-show step 3 (v0 residuals, scene contract) 🟢 (Tim-greenlit 2026-10-13; REVIEW 1 at `2feed6e` = REWORK, R1–R4 → follow-up REVIEW at `d1c346c` = **PASS**, cleared to merge)

**History:**
- REVIEW 1 (`2feed6e`, the EM ran everything on both machines) = **REWORK**, narrow. 14 rows are green; S11-8 and S11-14 have gaps (R2, R3); new row S11-17 (R4).
  - R1: no separate code review has happened. The sprint's acceptance requires one.
  - Mutations ran in a `git archive` scratch copy: 22 of 25 went red. The three survivors are M13 (R2), M17b (R3), and M18 (the compose `toon.scene.drift` log, which is recommended but doesn't gate).
  - Each mutation was restored after its run.
- Follow-up REVIEW (`d1c346c`) = **PASS**. All rows S11-1…S11-18 are ✅.
  - R1: the fresh review found 0 Critical, 2 Important and 9 Minor; all are fixed red first.
  - Mac: 1506 passed / 62 skipped; ruff and mypy are clean.
  - All 9 new red commits re-run red at their own SHA.
  - 25 of 25 new mutations go red, M13, M17b and M18 included.
  - Scene 001 is byte-identical to master (41 of 41 frames).
  - Hub, at the exact HEAD: 205 passed / 0 skipped, goldens 4/4, parity worst 0.058, no churn.
  - Row S11-18 is new; it registers the R1 fix tests in the contract.
  - Since the 2026-10-13 style lock, these rows guard the **backup** (2.5D) engine. The scene-contract rows (S11-1…S11-3, S11-5, S11-7…S11-9, S11-12…S11-14, S11-17) are the ones the 3D engine INTAKE should re-target.
  - **Re-targeted at the E11 INTAKE (2026-10-13):** row **S12-5** (E11 section) runs those cases as a conformance suite against both engines' catalogs. The S11 rows stay as they are.

Spec: `docs/superpowers/specs/2026-09-27-toon-bank-v0-design.md` **§11** (the addendum). Every
row gates PASS at a single REVIEW. Behaviour rows land **red first**: a test-only commit, then the
fix. The EM mutation-checks the fences. EM probes on master `a2e9b55` (2026-10-13) show S11-1,
S11-3, S11-5, S11-7, S11-8 and S11-12 red in behaviour today. Held items (laptop ✓/✗ screens,
`style.yaml` wiring, contact sheets) have no rows; they wait for Tim's style pick.

Sprint 11 run command:
`uv run pytest tests/unit/toon tests/unit/test_composer_toon.py tests/director/test_storyboard_validator.py -q`.
On the hub, also run `uv run pytest --integration tests/integration/toon tests/unit/toon -q`
(goldens and parity).

| Id | Capability | Test | Status |
|----|------------|------|--------|
| S11-1 | 2a: a timing field the timeline ignores fails at load with the beat path. That covers `ease` on `show`; `over`/`ease` on `hide` and `camera`; `over`/`ease` on a `prop` beat without `to:` | `tests/unit/toon/test_scene.py::test_beat_timing_fields_rejected_where_ignored` (parametrised) | ✅ (EM-run at REVIEW 1 `2feed6e` and the follow-up `d1c346c`); red re-run at `ee11844`; mutations M1 (show takes ease), M4 (ease without over) → red |
| S11-2 | 2a fence: every optional `Beat` field on every verb is either read by the timeline (listed in one table) or rejected. `over`/`ease` are `None` when not given | `tests/unit/toon/test_scene.py::test_every_beat_field_is_read_or_rejected` | ✅ (EM-run at REVIEW 1 `2feed6e` and the follow-up `d1c346c`); M1, M2 (timeline drops `bob`), M3 (an unlisted `Beat` field) → red |
| S11-3 | 2a: `flicker`/`blink`/`out` on a `plate` or `plate_stack` beat fails, naming the kind (`PROP_KINDS` carries the flags each kind honours) | `tests/unit/toon/test_scene.py::test_prop_beat_flags_rejected_on_kinds_that_ignore_them` | ✅ (EM-run at REVIEW 1 `2feed6e` and the follow-up `d1c346c`); M5 (plate honours flags) → red |
| S11-4 | 2a: top-level `hair` keys beside `layers:` fail with a `BankError` naming the file and the key | `tests/unit/toon/test_bank.py::test_hair_keys_beside_layers_rejected` | ✅ (EM-run at REVIEW 1 `2feed6e` and the follow-up `d1c346c`); red re-run at `f4f91d3`; M7 (`none:` allowed) → red |
| S11-5 | 2b: a `show` whose key is still visible in the shot fails, naming both beats; showing it again after a `hide` loads | `tests/unit/toon/test_scene.py::test_show_of_a_visible_graphic_key_is_rejected` | ✅ (EM-run at REVIEW 1 `2feed6e` and the follow-up `d1c346c`); M8 (visible-key show allowed), M9 (second hide allowed) → red |
| S11-6 | 2b: two cards with one icon and distinct `id:` slugs both draw; `hide: x_card:<id>` hides only that one; a non-slug `id` fails | `tests/unit/toon/test_timeline.py::test_two_cards_one_icon_with_ids_both_show` | ✅ (EM-run at REVIEW 1 `2feed6e` and the follow-up `d1c346c`); M10 (card `id` ignored in the key) → red |
| S11-7 | 2b splitter: closing quotes attach to the left (`他說：「我走了。」然後離開。` → `他說：「我走了。」` + `然後離開。`; `「走吧！」「好。」` → 2; `「A。B。」` → 2; no sentence starts with a closer); "U.S.", "Dr.", "e.g.", "J. K.", "Sr." don't split; an abbreviation at the end of the text ends it; every v0 case is unchanged | `tests/unit/toon/test_scene.py::test_sentences_count_real_breaks_only` (extended cases) | ✅ (EM-run at REVIEW 1 `2feed6e` and the follow-up `d1c346c`); red re-run at `aba8e00` (12 failed / 7 passed); M11a closers, M11b "I", M11c abbreviation list → red |
| S11-8 | 2b: `SceneError` names its source. A scene file gives its path; an inline storyboard visual gives the storyboard file + scene id; a `scene:` reference gives the scene file (from the storyboard + scene id). The `pipeline validate` issue and compose's `SceneRenderError` reason carry it | `tests/unit/toon/test_scene.py::test_scene_error_names_its_source` + `tests/unit/test_composer_toon.py::test_render_error_and_validator_name_the_scene_source` | ✅ (follow-up `d1c346c`): R2 closed by `tests/unit/test_compose_v2.py::test_compose_passes_the_storyboard_file_to_render_scene` (`aabd8ef`); EM M13 (compose passes `None`) → red. The R1 M10 still-gate pins also hold (EM M38, M39 → red) |
| S11-9 | 2d: `toon validate --narration --duration` prints the sentence table, each shot's resolved start and `WARN` lines; exit 0 with warnings, 1 on errors. An anchored scene without `--narration` exits 1, naming the flag | `tests/unit/toon/test_cli.py::test_validate_with_narration_prints_the_sentence_table` + `::test_validate_anchored_scene_without_narration_names_the_flag` | ✅ (EM-run at REVIEW 1 `2feed6e` and the follow-up `d1c346c`); M19 (flag hint removed) → red |
| S11-10 | 2e: `PROP_KINDS` keys equal the `PropDef.kind` literals | `tests/unit/toon/test_bank.py::test_prop_kinds_match_bank_prop_kinds` | ✅ (EM-run at REVIEW 1 `2feed6e` and the follow-up `d1c346c`) (a fence: green on master by design); M6 (an extra kind) → red |
| S11-11 | 2e: render workers use the caller's `Bank`, not a disk reload. A bank loaded from a temp copy, which is then edited, gives worker frames identical to in-process `frame()` from the loaded bank | `tests/unit/toon/test_render.py::test_workers_use_the_callers_bank` | ✅ (EM-run at REVIEW 1 `2feed6e` and the follow-up `d1c346c`); red re-run at `b23352d`; M20 (workers reload from disk) → red |
| S11-12 | 2f: `shots[i].at: {sentence: n, plus: s}` resolves to the sentence start + `plus`. At two narration durations the cuts move with the sentence starts, and beats given in seconds keep their shot-relative times (no stretch) | `tests/unit/toon/test_scene.py::test_shot_sentence_anchor_follows_the_narration` | ✅ (EM-run at REVIEW 1 `2feed6e` and the follow-up `d1c346c`); M15 (`plus` ignored), M22 (beat anchor not shot-relative) → red |
| S11-13 | 2f: anchors that resolve out of order fail loudly, naming each shot, its anchor and its resolved time. Cases: two shots on one sentence; an absolute shot overtaken under a slower narration; a first shot not at 0 | `tests/unit/toon/test_scene.py::test_shot_anchors_resolving_out_of_order_fail_loudly` | ✅ (EM-run at REVIEW 1 `2feed6e` and the follow-up `d1c346c`); M16 (order check off) → red |
| S11-14 | 2f: drift warning. An authored `duration`, later shots in seconds and a narration off by > 0.5 s give a validator `warn` (and a `toon validate` `WARN`). ≤ 0.5 s, or anchored shots, give none | `tests/unit/test_composer_toon.py::test_validator_warns_when_seconds_timed_shots_drift_from_narration` | ✅ (follow-up `d1c346c`): R3 closed (`02658a3`: 13.4/12.6 s give none, 13.6/12.4 s warn). EM M17b (3.0), 0.7 and 0.3 → red. The compose `toon.scene.drift` log is pinned by `::test_render_scene_logs_drift_for_seconds_timed_shots` (`991dcff`); EM M18 → red |
| S11-15 | Regression + fences. **Scene 001 unchanged:** hub goldens 4/4 with `UPDATE_GOLDENS` unset and no fixture churn; parity worst ≤ 0.058; determinism and the two-axes fence tests green. **Non-goal:** `assets/toon/scenes/` holds only 001; the bank gains no item. Full suite, ruff and mypy clean | `tests/unit/toon/test_goldens.py`, `tests/integration/toon/test_parity_001.py`, `tests/unit/toon/test_scene_001.py`, `tests/unit/toon/test_bank.py::test_v0_bank_holds_exactly_the_picked_items`, `uv run pytest -q` + ruff + mypy | ✅ Follow-up `d1c346c` (EM-run): Mac 1506 passed / 62 skipped, ruff and mypy clean (161 files); scene 001 byte-identical to master (41 of 41 frames); hub isolated clone at the exact HEAD: `--integration` toon 205 passed / 0 skipped, goldens 4/4 with `UPDATE_GOLDENS` unset, parity worst 0.058, no fixture churn. REVIEW 1 `2feed6e`: Mac full suite 1483 passed / 62 skipped, ruff clean, mypy clean (161 files); scene 001 byte-identical to master `a2e9b55` (12 of 12 frames, 960×540); hub isolated clone `/tmp/em-s11-review/repo`: `--integration` toon 185 passed / 0 skipped, goldens 4/4 with `UPDATE_GOLDENS` unset, parity `[0, 0, 0.004, 0, 0, 0.058]`, no fixture churn; non-goal fence holds |
| S11-16 | **Real-scene demo (hub):** a throwaway smoke project rebuilt from the Sprint 9 recipe (`tmp/toon-v0/compose-smoke/REPORT.md`; `9920260928` is gone), s2 as an inline sentence-anchored copy of scene 001, against two real narration takes of different length. Each cut lands within one frame of its resolved start; the clip lasts exactly as long as the narration; key frames at each cut eyeballed. Not an EP1 scene | manual evidence `tmp/toon-s11/demo/` (EM re-runs on the hub) | ✅ (EM re-ran it at REVIEW 1 `2feed6e`; it stands at `d1c346c`: N3's resolved cuts at 12.456 s and 14.928 s are identical at both SHAs, and compose is unchanged). The EM re-ran `s11_demo.py` on the hub (same takes). Take A 12.456 s → cuts at frames 104/236/296; take B 14.928 s → 125/282/342; 0 frames off; clip frames = narration (374, 448); contact sheet eyeballed. The takes are macOS `say` through the prerecorded path (edge-tts 403): accepted. The ~5-frame-short `s2_final` is compose + MP3 padding, filed in Later |
| S11-17 | **R4 (REVIEW 1):** `over` values mean what they render. A negative `over` fails on any verb, and `over: 0` on a `show` either fails or renders an instant pop. The builder rules which and records it in spec §11.6. Scene 001 is unchanged | `tests/unit/toon/test_scene.py::test_over_values_mean_what_they_render` | ✅ (follow-up `d1c346c`): red re-run at `73c1f0b`, fixed `9bebb74`, ruling in spec §11.6. EM M23 (`ge=0` dropped), M24 (show `over: 0` pops again), M25 (blink `gt=0` dropped) → red. EM probe: camera `over: -1` fails too; `over: 0` show k = 1.0 at its start |
| S11-18 | **R1 code-review fixes** (registered at the follow-up REVIEW). es-419 accented words, `EE. UU.`, `»`/`›` closers; `……」` + text ends a sentence; a straight `"` closes only an open one; a retake that pushes a seconds beat out of an anchored shot names the anchor and window; the CLI prints each problem whole and names `--duration`; `out` only true, `bob` needs `over`, `to: {}` fails; hair `layers: []` and `none:` beside layers fail; still-gate errors name the storyboard file; a same-time hide says it is listed before its show | `tests/unit/toon/test_scene.py::test_sentences_count_real_breaks_only` (R1 cases), `::test_a_seconds_beat_outside_an_anchored_shot_names_its_window`, `::test_no_op_beat_fields_are_rejected`, `::test_falsy_beat_fields_mean_what_they_render`, `::test_a_hide_before_its_show_says_which_comes_first`; `tests/unit/toon/test_cli.py::test_validate_prints_each_problem_whole`, `::test_validate_narration_without_a_duration_names_the_flag`; `tests/unit/toon/test_bank.py::test_empty_hair_layers_rejected`, `::test_hair_keys_beside_layers_rejected`; `tests/director/still_gate/test_cli.py::test_still_gate_toon_error_names_the_storyboard_file`, `test_render.py::test_render_scene_still_forwards_project_root` | ✅ (follow-up `d1c346c`): 8 red commits re-run red at their own SHA (`01c4ca7` 6/20, `f1da508` 2/27, `95fd16d` 2, `92c17d1` 2, `abf398a` 4/1, `69e195f` 2/2, `6b59206` 2, `c8726ed` 1). EM M26–M41 → red (16 of 16) |

## E10 — Claude calls on the subscription 🟢 (REVIEW 2026-09-29 = ADVISE at `f13c783`; merged to master `2add7c2` with F1 `09fa1c6` + F2 `b51efb3`; EM follow-up on master `53b1df3` = PASS)

Spec: `docs/superpowers/specs/2026-09-29-claude-cli-llm-backend-design.md` (Tim approved the
written spec: "looks good, proceed"). The rows come from spec §5 (tests) and §6 (done criteria).
The EM added them at REVIEW and ran them on both machines at `f13c783`.

"Mutation → red" means the EM broke that fence in a `git archive` scratch copy and the named test
failed. Each mutation was restored, and the scratch source matched HEAD afterwards.

| Capability | Test | Status |
|------------|------|--------|
| §5 argv and isolation: tier → model; `--system-prompt` always passed (a neutral default); `--tools ""`, `--setting-sources ""`, `--strict-mcp-config`, `--no-session-persistence`, `--disable-slash-commands`; prompt via stdin, never argv; cwd a temp dir | `tests/unit/test_llm.py` (`test_text_call_builds_isolated_argv_and_stdin`, `test_creative_tier_uses_opus_and_passes_system`) | ✅ (mutation → red: prompt on argv; `--strict-mcp-config` dropped) |
| §5 envelope: stream-json parsed, noise lines skipped, the last result event wins | `tests/unit/test_llm.py` (`test_last_result_event_wins` and others) | ✅ |
| §5 `--json-schema` passed through; `structured_output` read; falls back to parsing the result text; garbage → `LLMError` | `tests/unit/test_llm.py` (`test_json_schema_*`, `schema_garbage`) | ✅ |
| §5 image calls: the content blocks reach stdin unchanged (image, then text) | `tests/unit/test_llm.py::test_content_blocks_pass_through_unchanged` + image-site tests in `tests/unit/test_llm_call_sites.py` | ✅ (mutation → red: visual-review drops its images) |
| §5 no silent API billing: `ANTHROPIC_*` and `CLAUDE_CODE_USE_*` stripped from the child env; `CLAUDE_CODE_OAUTH_TOKEN` kept (ruling R2) | `tests/unit/test_llm.py` (`test_billing_switching_env_is_stripped_from_child_env` ×7, `test_oauth_token_passes_through_to_child_env`) | ✅ (mutation → red: no strip, 7 fail) |
| §5 **loud failure**: `is_error`, non-zero exit, timeout (with the stderr tail), empty result, missing binary (an explicit path is named), launch failure, bad JSON under a schema → `LLMError` quoting the real reason; quota and login hints match whole words | `tests/unit/test_llm.py` (`test_failures_raise_*`, `test_error_reason_survives_*`, `test_timeout_*`, `test_missing_binary_*`, `test_launch_failure_*`, `test_hint_*`) | ✅ (mutation → red: a CLI failure returns empty, 4 fail; an empty result accepted) |
| §5 **no silent backend fallback**: an unknown backend raises | `tests/unit/test_llm.py::test_unknown_backend_is_loud` | ✅ (mutation → red: an unknown backend falls back to `cli`) |
| §5 concurrency cap; default timeouts creative 1200 s / check 600 s, explicit wins (ruling R4) | `tests/unit/test_llm.py` (`test_concurrency_is_capped`, `test_*_default_timeout`, `test_explicit_timeout_*`) | ✅ |
| §5 binary resolution under a minimal systemd `PATH`: `PIPELINE_CLAUDE_BIN` → `which` → `~/.local/bin/claude` | `tests/unit/test_llm.py::test_resolve_falls_back_to_local_bin` | ✅ |
| §5 API backend behind the same interface (mocked SDK; the forced tool takes `schema_name`, R4; SDK errors → `LLMError`) | `tests/unit/test_llm.py` (`test_api_backend_*`) | ✅ |
| §5 call sites mock `pipeline.llm.complete` and assert their tier (all 12) | `tests/unit/test_llm_call_sites.py`, `tests/unit/test_analyze.py`, `tests/unit/test_direct.py`, `tests/unit/test_direct_metadata.py` | ✅ 12 of 12: each tier flip → red. Site 5 (`direct.metadata`) was green under the flip at REVIEW (F2); it went red at the `53b1df3` follow-up |
| §5 site 5 sends the metadata schema and the `emit_metadata` name | `tests/unit/test_direct_metadata.py::test_write_metadata_creates_file` | ✅ |
| §5 guard: outside `llm.py` and `utils/anthropic_key.py`, no `anthropic` import, no `messages.create`/`messages.stream`, no `get_anthropic_api_key` | `tests/unit/test_llm_guard.py` | ✅ (mutation → red: `import anthropic` in `cli_proofread.py`) |
| Suite tripwire: no unit test can reach the real `claude` (R4) | `tests/unit/test_conftest_tripwire.py` + `tests/conftest.py` | ✅ (mutation → red: tripwire removed) |
| Folded-in bug fix: visual-review `extract-frames` registered (also through the top-level app); `print_visual_issues_table` doesn't raise | `tests/unit/test_llm_call_sites.py` (`test_visual_review_extract_frames_*`, `test_print_visual_issues_table_does_not_raise`) | ✅ |
| §5 doctor `check_llm`: backend, resolved binary and `--version`, no model call; FAIL when the binary is missing, `--version` exits non-zero, or the backend is unknown | `tests/unit/test_cli_doctor.py` (`test_check_llm_*`) | ✅ (mutation → red: doctor passes with no binary) |
| §5 integration: one real Haiku text call, one image call, one schema call | `tests/integration/test_llm_cli.py` (`--integration`) | ✅ 3 passed on the Mac and 3 on the hub (EM-run) |
| §6.1 Mac: suite, ruff and mypy clean | `uv run pytest -q` + ruff + mypy | ✅ 1404 passed / 62 skipped; targeted 108; ruff clean; mypy clean (160 files) |
| §6.2 hub: doctor `llm` passes; integration passes | EM-run, hub worktree `f13c783` | ✅ doctor 18/18 on the hub and the Mac. Hub suite 1439 passed / 27 skipped |
| §6.3 hub real calls, at least 3 sites: proofread (check), one creative call, one image site (visual-review or image-alignment) | hub `.worktrees/llm-cli-backend/tmp/claude-cli-backend/` (`evidence.txt`, `em-review-visual.txt`) | ✅ proofread: Haiku, 142.3 s, 14 issues. beats: Opus, 5.3 s. metadata: Opus with a schema, 16.7 s, valid. Image: **EM-run visual-review (site 9)**, 27 frames, 61.9 s, 2 issues parsed. The builder's `style_anchor` call isn't a §6.3 site; see F1 |
| §6.4 budget tables in README and CLAUDE.md show the subscription; README documents the env settings | diff | ✅ README lacks `PIPELINE_LLM_TIMEOUT_CREATIVE_SEC`, a non-gating doc gap |
| §6.5 a separate code review happened | SDD ledger `.superpowers/sdd/2026-09-29-claude-cli-llm-backend/progress.md` | ✅ Per-task reviews, then a final Opus review ("with fixes", 2 Important + 11 minor), then a 12-item fix wave, then a scoped re-review ("all addressed") |
| **F1 (REVIEW finding, gates 🟢):** site 12 `style_anchor` parses the real CLI answer shape. `"Medium\n\nSerif typography, cream background, …"` must give `('medium', 'Serif typography, cream background, …')`, so blank lines are skipped. Today the hint is `""` in 3 of 3 hub runs | `tests/unit/test_llm_call_sites.py::test_style_anchor_skips_blank_lines_in_the_answer` | ✅ fix `09fa1c6`; green on `53b1df3` (mutation → red: the pre-fix parser keeps blank lines; the hint dropped) |
| **F2 (REVIEW finding, gates 🟢):** site 5 asserts `tier == "creative"`; the tier-flip mutation goes red | `tests/unit/test_direct_metadata.py::test_write_metadata_creates_file` | ✅ `b51efb3`; green on `53b1df3` (mutation → red: site 5 flipped to `check`) |

## E11 — 3D toy engine & bank 🔵 (INTAKE 2026-10-13; Sprint 12 = v0, **proposed, not greenlit**)

Spec: `docs/superpowers/specs/2026-10-13-toy3d-engine-v0-design.md`. Every row gates PASS. Phase 1
(S12-1…S12-5) gates an **EM checkpoint REVIEW** before Phase 2. Behaviour rows land **red first**
(a test-only commit, then the fix), and the EM mutation-checks the fences.

**Golden policy for GPU renders (spec §8; a departure from E8's byte-exact skip-on-Mac policy, for
toy3d only, pending Tim's OK):**
- **Layer A:** the symbolic timeline, exact, default suite.
- **Layer B:** the applied scene graph, ≤ 1e-6 on both machines.
- **Layer C:** pixels at 960×540, **hub-canonical**, compared on **both** machines with a calibrated
  tolerance, minted on the hub only.

The EM's probe baseline (2026-10-13, tryout t = 4.6 s, 1080p):
- the Mac (Metal) is byte-identical run to run;
- the hub (GL-EGL, GTX 1050) wobbles ≤ 1 level;
- Mac vs hub: mean 0.14/255, 0.05% of pixels > 8, max 129 (edges, fur tips);
- hub ANGLE-Vulkan gives all-black frames;
- the default flags fall back to SwiftShader.

Sprint 12 run command (planned): `uv run pytest tests/unit/toon tests/unit/toy3d tests/unit/test_composer_toon.py tests/unit/test_golden_policy.py tests/director/test_storyboard_validator.py -q`.
On **both** machines also run `uv run pytest --integration tests/integration/toy3d tests/integration/toon -q`.

| Id | Capability | Test | Status |
|----|------------|------|--------|
| S12-1 | **Seam:** `load_scene` validates against any `SceneCatalog` (names + capabilities); the 2.5D `Bank` adapts; a toy3d catalog loads a toy3d scene; `toon.scene` has no module-level import of `toon.bank` or the 2.5D kit | `tests/unit/toon/test_contract_seam.py::test_load_scene_takes_any_catalog`, `::test_scene_module_does_not_import_the_2d_bank` (AST fence) | 🔲 planned (Phase 1) |
| S12-2 | **Engine-relative "means what it renders":** a verb, beat field, prop kind, show kind, place field (`layer`) or fx the chosen engine doesn't render fails at load, naming the engine and the path; parametrised over both engines | `tests/unit/toon/test_contract_seam.py::test_field_the_engine_does_not_render_fails_naming_the_engine` | 🔲 planned (Phase 1) |
| S12-3 | **`engine:` key:** optional, default `toon2d` (every existing scene and storyboard is unchanged); an unknown engine fails, listing the engines; compose and the validator dispatch by it | `tests/unit/toon/test_contract_seam.py::test_engine_key_defaults_and_unknown_fails` + `tests/unit/test_composer_toon.py::test_dispatches_by_scene_engine` | 🔲 planned (Phase 1) |
| S12-4 | **Symbolic timeline:** `beats_at(scene, t)` is engine-neutral (names + eased k + camera preset/local time) and pure. The 2.5D `state_at` is rebuilt on it, and **scene 001 is byte-identical**: 41 of 41 frames against the sprint base, hub goldens 4/4 with no churn, parity ≤ 0.058 | `tests/unit/toon/test_symbolic_timeline.py` + `tests/unit/toon/test_goldens.py` + `tests/integration/toon/test_parity_001.py` + EM byte-identity check | 🔲 planned (Phase 1) |
| S12-5 | **Contract conformance:** the Sprint 11 contract cases (S11-1…S11-3, S11-5, S11-7…S11-9, S11-12…S11-14, S11-17) fail the same way against both engines' catalogs where the field is engine-neutral | `tests/unit/toon/test_contract_conformance.py` | 🔲 planned (Phase 1) |
| S12-6 | **Bank v0:** `assets/toy3d/bank/**` YAML loads into a typed `Toy3DBank`; every item carries `picked:` provenance; a missing or unknown field fails, naming the file and the field path; the bank holds **exactly** the frozen tryout picks (Tim H3, GuoGuo, the lioness, office + hall, the tryout props, the camera presets, look A) | `tests/unit/toy3d/test_bank.py` (incl. `::test_v0_bank_holds_exactly_the_picked_items`) | 🔲 planned |
| S12-7 | **Look is bank data:** `style.yaml` (tone map, exposure, GTAO, shadows, bloom, env) and the palettes drive the render, so a changed value changes pixels; the engine modules hold no look constants (static fence, with an allow-list for tooling such as the mask key colour) | `tests/integration/toy3d/test_style_wiring.py` + `tests/unit/toy3d/test_engine_source_fences.py::test_no_look_constants_in_engine_js` | 🔲 planned |
| S12-8 | **Runtime pin + backend allow-list (loud):** a pinned CfT build through Python `playwright`; darwin `metal` and linux `gl-egl` only; the WebGL renderer string is read at start; SwiftShader, Vulkan, an unlisted string or a missing build → `Toy3DRenderError`, naming the string and the fix (surfacing as `SceneRenderError` in compose) | `tests/unit/toy3d/test_runner.py::test_backend_allow_list_refuses_swiftshader_vulkan_and_unknown` + integration on both machines | 🔲 planned |
| S12-9 | **Blank-frame guard:** a uniform frame (the hub ANGLE-Vulkan symptom) fails the render, and nothing is encoded or cached; EM mutation: force Vulkan on the hub → loud failure, not a black mp4 | `tests/unit/toy3d/test_runner.py::test_uniform_frame_fails_loud` | 🔲 planned |
| S12-10 | **Determinism fences:** engine JS has no unseeded `Math.random`, `Date`, `performance.now`, `requestAnimationFrame`, or `fillText`/`strokeText` (wordless). The same frame rendered twice is byte-identical on the Mac and within the noise floor on the hub | `tests/unit/toy3d/test_engine_source_fences.py` + `tests/integration/toy3d/test_determinism.py` | 🔲 planned |
| S12-11 | **Layers A and B:** symbolic state of the worked scene is exact (default suite). `applyState` in `mode: "state"` creates **no WebGL context**, and its named world matrices, visibility, decal ids and camera match `tests/fixtures/toy3d/state/*.json` to ≤ 1e-6 **on both machines** | `tests/unit/toy3d/test_state_symbolic.py` + `tests/integration/toy3d/test_state_goldens.py` | 🔲 planned |
| S12-12 | **Layer C pixel goldens:** key frames of the worked scene + a cast model sheet at 960×540, hub-canonical, compared on **both** machines with a tolerant helper in `tests/golden_policy.py`; `UPDATE_GOLDENS` off-linux is an error; `PROVENANCE.md` records the browser build, both renderer strings, the driver, the noise floor and the thresholds. **Sensitivity set goes red:** an expression-decal swap on a close-up, a 5° shoulder rotation, one material colour shift, GuoGuo hidden, the fur shell count halved | `tests/integration/toy3d/test_goldens.py` + `tests/unit/test_golden_policy.py` + `tests/fixtures/toy3d/goldens/` | 🔲 planned |
| S12-13 | **Cache key:** covers the scene, the **Bank object** (`model_dump_json`), the engine JS, the vendored three hash, the browser build, the renderer string, the size and the fps; any change re-renders; a hit doesn't launch the browser | `tests/unit/toy3d/test_render.py::test_cache_key_covers_every_input`, `::test_cache_hit_launches_no_browser` | 🔲 planned |
| S12-14 | **Two-axes fence:** the clip has exactly round(duration × `COMPOSE_FPS`) frames. A longer narration holds the last shot; a shorter one warns and cuts (the same contract as E9). The mp4 is written as `.part` → rename | `tests/integration/toy3d/test_render.py::test_clip_frame_count_equals_narration` | 🔲 planned |
| S12-15 | **fps fence + cadence (standards anatomy 9):** toy3d renders at `COMPOSE_FPS` (the guard fails if either rate changes alone); a camera move through compose's concat normalisation has no near-duplicate steps | `tests/unit/test_composer_toon.py::test_toy3d_fps_matches_compose_concat` + `tests/integration/toy3d/test_cadence.py` | 🔲 planned |
| S12-16 | **Adapter + validator:** `render_scene` renders a `toon` visual with `engine: toy3d`. Any failure → `SceneRenderError` with a `suggested_fix`, and **never a silent render on the 2.5D engine**. The validator branch fails a bad toy3d name at the review gate (`pipeline validate` exit 2). `toon` stays out of `_TEXT_VISUALS` | `tests/unit/test_composer_toon.py` (toy3d cases) + `tests/director/test_storyboard_validator.py` (toy3d cases) | 🔲 planned |
| S12-17 | **CLI + doctor:** `pipeline toon validate\|render` handle toy3d scenes (engine read from the file); the `pipeline doctor` toy3d check (pinned build present, renderer allow-listed, a one-frame non-blank smoke) fails loudly with an install hint; **doctor passes on both machines** | `tests/unit/toy3d/test_cli.py` + `tests/unit/test_cli_doctor.py::test_check_toy3d_*` + EM-run doctor on both machines | 🔲 planned |
| S12-18 | **Acceptance: parity with the locked look (gating):** `assets/toy3d/scenes/001-beat2-break-in.yaml` matches reference frames frozen from the r7-3d snapshot at greenlight (`tests/fixtures/toy3d/tryout_ref/`, Mac Metal, ≥ 6 key times): within the parity tolerance on the Mac, and the cross-machine tolerance on the hub. A side-by-side sheet goes to Tim, and **Tim confirms it still meets his bar** | `tests/integration/toy3d/test_parity_tryout.py` + `tmp/toy3d-v0/parity/side_*.png` + Tim's words in the sprint-log | 🔲 planned |
| S12-19 | **Real-scene demo (gating, standards anatomy 6):** a throwaway two-scene smoke project (a `clip` + the toy3d scene; prerecorded narration in two takes of different length) composes **on both machines**. The toy3d frames = narration × 30; `blackdetect` is clean; subtitles are kept; the cadence is clean; ms per frame is recorded for each machine | evidence `tmp/toy3d-v0/compose-smoke/` (`REPORT.md`, ffprobe, blackdetect, frame timings) | 🔲 planned |
| S12-20 | **Non-goal fence:** `assets/toy3d/scenes/` holds only the worked scene (no EP1 scenes); the bank holds only picked items; the 2.5D render paths are unchanged except the seam; `assets/toon/**` and `tests/fixtures/toon/**` are unchanged | `tests/unit/toy3d/test_scenes.py::test_only_the_worked_scene` + S12-6 + EM diff | 🔲 planned |
| S12-21 | Full suite, `ruff check src/ tests/` and `mypy src/` clean **on both machines**, with `src/toy3d` packaged (web assets included); **a separate code review has happened** | `uv run pytest -q` + ruff + mypy (both machines) + the review ledger | 🔲 planned |

## Cross-cutting

| Capability | Test | Status |
|------------|------|--------|
| Animation-review harness | `tests/unit/test_animation_review.py` | ✅ |
| Composer base dispatch (all visual types) | `tests/unit/test_composer_base.py` | ✅ |
| Real-scene demonstration harness (canonical-scene picker + run a new capability against it) — _tooling half of Idea A; the REVIEW-gate requirement itself is in `standards.md`, this row tracks the picker/runner if/when it's built_ | _(test TBD — `tests/unit/test_demo_harness.py`)_ | 🔲 planned |
