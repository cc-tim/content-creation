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
| Scene validation: an unknown bank item / set spot / camera / icon name → error naming the scene file and the path inside it | `tests/unit/toon/test_scene.py` | path: ✅ · scene-file name: ⏸️ deferred to E9 item 2b (Tim acked 2026-09-28; does not gate) |
| Wordless rule (locale-portability fence in code): any free-text field or unknown field in a scene → error; graphics, bubbles and screens accept icon-registry names only | `tests/unit/toon/test_scene.py` + `tests/unit/toon/test_kit.py::test_engine_and_kit_draw_no_text` | ✅ (a few non-text timing and flicker fields are still ignored; not a wordless breach; E9 item 2a) |
| Timing: a beat outside its shot → error; `at: {sentence: n}` anchors resolve (narration split into sentences, audio duration shared out by character count) | `tests/unit/toon/test_scene.py` | ✅ |
| **Two-axes fence (spec §5):** the rendered toon clip lasts exactly as long as the narration. Narration longer → the last shot holds, still boiling. Narration shorter than the last beat → load warning, and the clip is cut at the narration's end. A toon scene cannot extend runtime | `tests/unit/toon/test_scene.py` + `tests/unit/test_composer_toon.py` + `tests/unit/toon/test_render.py::test_clip_has_exact_frame_count_and_cache_hits` (`--integration`; 38 frames = round(1.25 s × 30)) | ✅ |
| Engine: projection and IK maths; draw-order cases from the tryout (desk between camera and character or not; arms raised behind the head); the per-shot layer override is honoured | `tests/unit/toon/test_engine_math.py` + `tests/unit/toon/test_character.py` + `tests/unit/toon/test_order.py` | ✅ (draw order mutation-checked 3/3 at REVIEW 2) |
| Determinism: `frame(scene, bank, t)` rendered twice gives identical bytes, and identical bytes again from a worker process; no global random state (boil seeds from item keys + `floor(t·12)`) | `tests/unit/toon/test_render.py` (`test_frame_is_deterministic`, `test_parallel_equals_serial`) + `tests/unit/toon/test_pen.py` | ✅ (plus: `frame(t)` is byte-identical at bank fps 24 and 30, EM-checked at REVIEW 3) |
| Clip cache key (spec §6) covers the scene file, the bank files it uses, the `src/toon` sources, the engine version and `fps`: editing a used bank YAML or an engine source re-renders | `tests/unit/toon/test_render.py` | ✅ |
| **Golden frames, hub-only:** three scene-001 key frames plus the Tim model sheet via `assert_matches_golden`; skipped off-linux with the hub-canonical reason; minted on the hub only and eyeballed; hub cairo version recorded next to the fixtures | `tests/unit/toon/test_goldens.py` + `tests/fixtures/toon/goldens/` | ✅ Hub 4/4 with `UPDATE_GOLDENS` unset, no fixture churn (REVIEW 3). `PROVENANCE.md` corrected: the Mac differs by 1 px / 1 level on `s001_01.50` only (informational) |
| Pipeline adapter: `render_scene` dispatches `toon` for both a `scene:` reference and inline `shots`; any load/render failure raises `SceneRenderError` with a `suggested_fix` (no `text_card` fallback, no cached black stand-in); `toon` is **not** in `overlay_rules._TEXT_VISUALS` (narration subtitle kept) | `tests/unit/test_composer_toon.py` + `tests/unit/test_compose_v2.py::test_scene_render_error_leaves_no_cached_black_fallback` | ✅ |
| Storyboard validator `toon` branch: a storyboard toon scene with a bad bank name or a free-text field fails at the review gate (`pipeline validate` exit 2) | `tests/unit/test_composer_toon.py` (validator cases) + EM live run | ✅ |
| CLI `pipeline toon validate\|render\|sheet` is registered on the pipeline CLI; `validate` exits 0 when clean and non-zero on errors; `sheet` writes the bank review sheets (model sheet, pose and prop contact sheets) | `tests/unit/toon/test_cli.py` | validate/render/sheet (model sheet): ✅ · pose/prop contact sheets: ⏸️ deferred to E9 item 2d (Tim acked 2026-09-28; does not gate) |
| `pipeline doctor` toon check: cairo loads and a one-frame smoke render works; a missing cairo gives a loud FAIL with a platform `suggested_fix` | `tests/unit/toon/test_cli.py::test_check_toon_passes_here` + `tests/unit/test_cli_doctor.py::test_check_toon_fails_with_install_hint_when_cairo_is_missing` | ✅ (R2 fixed: the test injects `OSError("dlopen failed")` and asserts `brew install cairo` + `libcairo2`; it goes red with the hint deleted) |
| `pipeline doctor` toon check passes (exit 0) **on both machines** | EM-run doctor, both machines | ✅ Mac 17/17 (cairo 1.18.4), hub 17/17 (cairo 1.18.0), REVIEW 3 at `2f6fb35` |
| **Pipeline smoke (hub):** a two-scene storyboard (a `clip` plus a `toon` scene) composes end to end; the final contains both scenes with subtitles; the toon segment matches its narration length; the join into compose's concat doesn't judder | manual evidence, hub `tmp/toon-v0/compose-smoke/` (`rescene-30fps.log`, `judder-30fps.txt`) + EM probe `/tmp/em-judder.sh` | ✅ (REVIEW 3) `toon_s2` 30/1, 403 frames = 13.433 s against 13.44 s of narration. EM whole-segment probe: the final tracks the raw cadence step for step (corr 0.93); every moving step keeps ≥72% of its raw size (median 88%); no introduced duplicates; zh-TW subtitles kept |
| **R1 fps fence:** the toon clip renders at the compose concat rate; a test fails if either rate changes alone | `tests/unit/test_composer_toon.py::test_toon_fps_matches_compose_concat` | ✅ (mutation-checked in both directions) |
| **R1 cadence, measurable judder:** a scene-001 shot-1 camera push, rendered at the bank fps and run through compose's exact concat normalisation, has no near-duplicate step; red on 24 fps | `tests/integration/toon/test_cadence.py` (`--integration`) | ✅ Green on both machines. EM mutation to 24: red, 8/45 steps at 1, 6, 11, …, 36 (every 5th). Rendered via `render_frames`, not the adapter; the adapter's 30 fps is pinned by the 38-frame count test and the hub smoke's ffprobe |
| **Acceptance: scene 001 (real-scene demo, gating):** `assets/toon/scenes/001-lioness-dishes.yaml` renders a clip that matches `output/own-show/scenes/001-lioness-dishes/animatic_v2_bulb.mp4` in shots, timing and look (key-frame side-by-side), and **Tim confirms it still meets his bar** | `tests/integration/toon/test_parity_001.py` (`--integration`) + `tmp/toon-v0/scene001/side_*.png` + Tim's words in the sprint-log | ✅ Parity worst **0.058** (12.2 s; limit 0.5), unchanged since `c29fc52`; the earlier "0.0435" was an EM mis-record. Tim 2026-09-28: "looks good" (trembling → soft boil), then picked 30 fps / drawings 12/s |
| Non-goal fence (spec §1): the bank holds only picked items (no campfire, no unpicked items), and `assets/toon/scenes/` holds only `001-lioness-dishes.yaml` (no EP1 scenes) | `tests/unit/toon/test_scene_001.py` + `tests/unit/toon/test_bank.py::test_v0_bank_holds_exactly_the_picked_items` + diff | ✅ (re-checked at REVIEW 3) |
| Full suite collects and passes with `src/toon` packaged (`cairocffi` in deps, `src/toon` in hatch `packages`); `ruff check src/ tests/` and `mypy src/` clean | `uv run pytest -q` + ruff + mypy | ✅ REVIEW 3 at `2f6fb35`: hub 1380 passed / 22 skipped / 0 failed (its first run hit the unrelated trust-gate flake, see arsenal-state); Mac 1343 / 59 / 0; ruff clean; mypy clean (159 files) on both machines |

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

## Cross-cutting

| Capability | Test | Status |
|------------|------|--------|
| Animation-review harness | `tests/unit/test_animation_review.py` | ✅ |
| Composer base dispatch (all visual types) | `tests/unit/test_composer_base.py` | ✅ |
| Real-scene demonstration harness (canonical-scene picker + run a new capability against it) — _tooling half of Idea A; the REVIEW-gate requirement itself is in `standards.md`, this row tracks the picker/runner if/when it's built_ | _(test TBD — `tests/unit/test_demo_harness.py`)_ | 🔲 planned |
