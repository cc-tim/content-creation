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

## E8 — Two-machine workflow & render portability 🔵 (Sprint 8 = item 1, proposed 2026-09-24)

Spec: `docs/superpowers/specs/2026-09-24-e8-cross-platform-fonts-design.md`. Acceptance is split:
**(A) hub rows gate merge**, **(B) Mac rows gate 🔵→🟢** (Tim supplies the artifacts; the EM
follow-up REVIEW flips them). Golden policy: hub-canonical, golden compare SKIPPED on darwin,
determinism tests everywhere.

| Capability | Test | Status |
|------------|------|--------|
| (A) Resolver resolves by NAME: all 4 role×weight → `Noto {Sans,Serif} CJK TC {Regular,Bold}`; hub sans-bold = `NotoSansCJK-Bold.ttc` **index 3** (locks HK→TC fix) | `tests/unit/test_fonts.py` | 🔲 planned |
| (A) Resolver precedence (`PIPELINE_FONT_DIRS` > fc-match > known dirs) + TTC face scan by name + accepts Super-OTC/per-weight/.otf packaging | `tests/unit/test_fonts.py` | 🔲 planned |
| (A) Loud failure: nothing found → `FontResolutionError` with platform `suggested_fix`; `verify_fontconfig_family` rejects fc-match substitution (`Nonexistent Font XYZ`) | `tests/unit/test_fonts.py` | 🔲 planned |
| (A) Call sites raise, never degrade: `_title_font`, `running_out`, `rich_slide`/chart/callout propagate `FontResolutionError`; compose-start verifies theme font family once | `tests/unit/test_font_callsites.py` | 🔲 planned |
| (A) Static fence: no `/usr/share/fonts`, `/System/Library/Fonts`, `load_default(`, stray `ImageFont.truetype(`, drawtext `fontfile=`, or `Path("output/` literals in `src/pipeline` | `tests/unit/test_font_callsites.py` | 🔲 planned |
| (A) Outro drawtext uses `drawtext_font_arg` (fontconfig TC pattern), no absolute font path | `tests/unit/test_font_callsites.py` (or `tests/unit/test_outro_builder.py`) | 🔲 planned |
| (A) Render truth: glyph-distinctness probes (PIL / drawtext / libass) — two CJK strings differ and neither equals the .notdef render | `tests/integration/test_cjk_render_truth.py` (`--integration`) | 🔲 planned |
| (A) Golden policy: darwin → skip w/ hub-canonical reason; `UPDATE_GOLDENS` on non-linux → error; `PIPELINE_GOLDEN_STRICT=1` compares; chart/chart_anim/callout migrated to shared helper, fixtures unchanged | `tests/unit/test_golden_policy.py` + `tests/golden_policy.py` | 🔲 planned |
| (A) `pipeline doctor` exit 0/1 per check; `--out` saves probe PNGs | `tests/unit/test_cli_doctor.py` | 🔲 planned |
| (A) Output paths honour `PipelineConfig().OUTPUT_DIR` (migrate CLI, gallery index, composer gallery path) | `tests/unit/test_output_paths.py` | 🔲 planned |
| (A) Full suite collects cleanly (`test_memory_sync.py` importorskip) — 0 errors, 0 failures | `uv run pytest -q` | 🔲 planned |
| (A) Hub real-scene before/after: baby-walker s11/s31/s24 + outro | manual evidence `tmp/e8-fonts/hub/` | 🔲 planned |
| (B) Mac: ffmpeg buildconf has freetype/fontconfig/libass/harfbuzz; drawtext + subtitles filters | manual evidence (Tim, spec §8B step 1) | 🔲 planned |
| (B) Mac: `pipeline doctor` exit 0 + probe PNGs | manual evidence `tmp/e8-fonts/mac/` | 🔲 planned |
| (B) Mac: `pytest -q -rs` 0 failed/0 errors, only golden-policy skips new; render-truth integration passes | manual evidence (Tim) | 🔲 planned |
| (B) Mac real-scene: s11/s31/s24 frames show Noto TC glyphs (no tofu, not PingFang), layout matches hub | manual evidence `tmp/e8-fonts/mac/` | 🔲 planned |
| (B, informational — does not gate) Mac `PIPELINE_GOLDEN_STRICT=1` golden match result | recorded in sprint-log | ⏸️ informational |

## Cross-cutting

| Capability | Test | Status |
|------------|------|--------|
| Animation-review harness | `tests/unit/test_animation_review.py` | ✅ |
| Composer base dispatch (all visual types) | `tests/unit/test_composer_base.py` | ✅ |
| Real-scene demonstration harness (canonical-scene picker + run a new capability against it) — _tooling half of Idea A; the REVIEW-gate requirement itself is in `standards.md`, this row tracks the picker/runner if/when it's built_ | _(test TBD — `tests/unit/test_demo_harness.py`)_ | 🔲 planned |
