# Content-Creation Arsenal & Infrastructure Roadmap

> **System of record** for visual-arsenal and pipeline-infrastructure development.
> Owned and maintained by the **engineering-manager** subagent
> (`.claude/agents/engineering-manager.md`, dispatched via the `engineering-manager`
> skill). This is the *capability* backlog — what the pipeline can render, validate,
> and surface. Producing individual videos is **not** tracked here; that is content
> work. When this file and a `tmp/*-handoff.md` design doc disagree, the handoff is the
> detailed spec and this file is the prioritized plan of record.
>
> **Production-project queue (sibling, 2026-05-26):** candidate *videos* parked for a
> future sprint slot are tracked separately in
> `.agent-memory/engineering-manager/production-projects.md`, gated by an explicit
> **video-producer greenlight** (a content/quality call Tim makes; the EM tracks and
> surfaces the gate and nominates greenlit projects, but does not clear it or produce the
> video). Rule: `standards.md` → "Production-project greenlight gate". This roadmap stays
> the *capability* backlog; production projects do not get roadmap lines.

**Last updated:** 2026-10-13 (INTAKE + SPRINT, Tim: "yes, do both". **New epic E11, the 3D toy engine**, the production engine for the locked own-show look. **Sprint 12 = E11 v0** is proposed, not greenlit; spec `docs/superpowers/specs/2026-10-13-toy3d-engine-v0-design.md`; rows S12-1…S12-21. EM probes on both machines found that the hub is **not** SwiftShader-only: headless Chrome gets WebGL2 on its GTX 1050 through ANGLE GL-EGL. Frame time at 1080p is ~85 ms on the Mac (Metal) and ~188 ms on the hub. Byte-exact goldens can't hold across machines (Mac vs hub: mean 0.14/255, max 129 on edges and fur tips). Hub ANGLE-Vulkan silently renders **black** frames. E9's held items and item 3 are re-homed to E11; E9 is now the backup engine, in maintenance. Sprint 11 is merged (`55670c9`). Queue: Sprint 12 → E5 part 1b → E8 item 2. E11 bank-fill sprints jump ahead of E8 item 2 once Tim's EP1 script names what it needs.) · Prior: 2026-10-13 (follow-up REVIEW: **Sprint 11 = PASS → 🟢, cleared to merge**, `feat/e9-sprint11` at `d1c346c`. R1–R4 are closed. The fresh code review found 0 Critical, 2 Important and 9 Minor; all are fixed red first, and spec §11.6 records the rulings. The EM ran everything itself. Mac: 1506 passed / 62 skipped; ruff and mypy are clean (161 files). All 9 new red commits are red when re-run. 25 of 25 mutations go red, including M13, M17b and M18. Scene 001 is byte-identical to master (41 of 41 frames). Hub, at the exact HEAD: 205 passed / 0 skipped, goldens 4/4, parity worst 0.058, no churn. The demo's resolved cuts are unchanged. **Style lock (Tim, 2026-10-13: 3D toy):** the 2.5D toon engine is now the backup style's engine. The 3D engine needs an INTAKE after the merge; see E9.) · Prior: 2026-10-13 (REVIEW: **Sprint 11 = REWORK (narrow)** on `feat/e9-sprint11` at `2feed6e`. The EM re-ran everything. The full suite gives 1483 passed / 62 skipped; ruff and mypy are clean. All 9 red commits are red when re-run. 22 of 25 mutations go red. Scene 001 is byte-identical to master (12 of 12 frames). On the hub: goldens 4/4, parity worst 0.058, no fixture churn, and the two-take demo reproduces with every cut on its resolved frame. Four things must change before merge: R1, the separate code review has not happened; R2, compose's `storyboard_file` wiring is not pinned by any test; R3, the drift tolerance's upper side is not pinned; R4, `over: 0` on a `show` and a negative `over` still load silently. Filed in Later: edge-tts returns 403, a production blocker (7.2.8 is already the latest on PyPI); the toon cache key hashes the bank files, not the `Bank` object; prerecorded MP3 padding.) · Prior: 2026-10-13 (SPRINT: **Sprint 11 = E9 item 2, finishing own-show step 3**, Tim-greenlit: "for step three, could you complete?". Only the style-independent scene-contract residuals are built. Laptop ✓/✗ screens, `style.yaml` wiring and contact sheets are held, because Tim reopened step 1 (style). Spec addendum: toon spec §11. Test-plan rows S11-1…S11-16. Sprint 11 goes ahead of E5 part 1b.) · Prior: 2026-09-29 (follow-up REVIEW on master `53b1df3`: **E10 v1 = PASS → 🟢**. The F1 and F2 tests are green, 3 of 3 mutations went red, and the full suite gives 1440 / 62. Sprint 10 is merged as `53b1df3`. The Pillow `getdata` deprecation is filed with the dark-image item in Later: removal would silently disable the dark check.) · Prior: 2026-09-29 (REVIEW: **Sprint 10 (E5 loud-failure sweep, part 1) = PASS → 🟢**, `feat/e5-loud-failure-sweep` at `bb16aa0`, merge cleared. The EM ran everything itself: the branch suite gave 1378 passed / 59 skipped, and the merged tree (post-E10 master + branch) gave 1440 / 62; ruff and mypy were clean. 18 of 18 mutations went red, and the A4 smoke was re-run at HEAD with 3 extra live checks. The hub path audit found 0 disagreements. It also found that hub project `1776850327_B`'s final holds 5 black runs (~61 s) and the project was published; see Sprint 10. Parked items are placed in Later, with atomic scene-cache writes at the top.) · Prior: 2026-09-29 (REVIEW: E10 v1 = ADVISE, cleared to merge; it has since merged to master `2add7c2` with F1 and F2). · 2026-09-29 (SPRINT + INTAKE: Sprint 10 greenlit; new infra epic E10). · 2026-09-28 (third REVIEW, master `2f6fb35`: **Sprint 9 (E9 v0) = PASS → 🟢 shipped**). Earlier history: `.agent-memory/engineering-manager/sprint-log.md` and `sprint-log-archive.md`. · **Maintainer:** engineering-manager subagent

---

## North star

Quality is the only north star (`CLAUDE.md` → "Ultimate Goal"). The visual **arsenal is
a variable, not a fixed set**: when a beat's best-fit visual is a category we have not
built, we *build the category* rather than downgrading the content to fit current
weapons (know-fountains `CLAUDE.md` → "Elevating the visual arsenal").

**Two axes, always kept distinct** (producer loop-4 lesson, baby-walker):

| Axis | What moves it | What does NOT move it |
|------|---------------|------------------------|
| **Production quality (visual + audio)** | richer rendering — charts, animation, overlays — **and** richer audio — SFX/ambient layering, mix legibility (E7) | — |
| **Runtime** | more distinct beats (more story / more sources) | richer rendering OR richer audio. A 4–5 min story rendered beautifully — or scored beautifully — is still 4–5 min. |

Every sprint states which axis it serves. We never promise runtime from an arsenal item.
(The quality axis spans **both** visual and audio capability; the runtime invariant is
unchanged by either.)

---

## Current arsenal (baseline, reconciled 2026-09-29)

- **Visual types:** `generated_image`, `article_image`, `clip`, `slide`, `rich_slide`,
  `chart` (6 static chart_types — Sprint 1 + line in Sprint 2 🟢), `text_card`,
  `still_frame`, `image_sequence`, `toon` (Sprint 9 🟢). `namecard`/`map` are accepted
  but render as a `text_card` (see Known gaps).
- **Camera motion on stills (🟢):** `image_to_video` applies a slow Ken Burns zoom to every
  still by default; `slow_push_pan`/`ken_burns` are configurable (E2).
- **Frames:** `open_book_page` (project-level wrap)
- **Transitions:** `page-turn` (weak — aliased to xfade slideleft), `book-page-turn-v2`
- **Reveals (Sprint 2 🟢):** animated `line` left-to-right draw (with markers synced
  to draw progress) · animated `bar` sequential grow with stagger · `stat_big_number`
  digit count-up with preserved formatting. PIL multi-frame → ffmpeg, mirrors
  `composer/base.py:_camera_motion_to_video`. Two-axes guardrail in code:
  `reveal_duration_sec ≤ scene_duration − 0.5s` enforced by validator.
- **Style manifest (Sprint 3 🟢):** `src/pipeline/style/` package — `pipeline style
  list/add/remove` CLI; per-project append-only `style_log.json` at
  `output/projects/{id}/style_log.json`; surfaces `frame_style`, `visual_style`,
  `intro_transition_style`, `_anchor_image` (INACTIVE) + per-scene
  `skip_niche_style`/`style_modifier` overrides. `anchor_image` dead-code removed from
  `render_generated_image` + call site (upstream `style_anchor.py` chain preserved).
- **Storyboard validator (Sprint 4 🟢):** `director/storyboard_validator.py`
  validates `article_image`/`image`, `slide`, `rich_slide`, `generated_image`,
  `text_card`, `clip`, `still_frame`, `namecard`, `map`, **and `chart`** (the chart
  branch delegates to `composer/chart.py:validate_chart_visual`, a pure list-returning
  function, so chart errors block the review gate at storyboard-write time, not only at
  render time); produces `confidence`/`rationale` decision table; wired into `direct.py`
  after storyboard save. Standalone `pipeline validate <project-id>` CLI
  (`src/pipeline/cli_validate.py`) re-checks an edited storyboard without rerunning
  `direct` (exit 0 clean / 1 load-failure / 2 validation-errors; auto-discovers a lone
  `storyboard_<locale>.json`, requires `--locale` when multiple exist). 26 validator
  tests (up from 9) cover chart + smoke tests for rich_slide/text_card/still_frame/
  namecard/map.
- **Callout overlay primitive (Sprint 5 🟢):** `composer/callout.py` — pure
  `place_callouts` (vertical dodge to the next free row + leader lines; row budget capped by
  header space; raises on exhaustion) + `_draw_placed_callouts` + `render_callouts` image
  wrapper. Consumed by BOTH the static `chart._render_line` and the animated
  `chart_anim._animate_line_frame` for collision-free line-chart marker labels (fixes the
  s21 decline-curve overlap). Registered as a `kind="overlay"` aggregate Style Manifest
  element. The PIL-composite callout layer is distinct from the ffmpeg `overlay.py`
  drawtext layer; v1 adds placement intelligence (animated entrance is E3 v2).
- **Compose-time loud failures (🟢):** `composer/base.py` raises `SceneRenderError`
  (reason + suggested_fix) for a missing-or-corrupt `article_image`/`image` path (the old
  silent `text_card` fallback was removed in 5a33f0a). **`apply_overlay` failures in
  `compose.py` now also raise `SceneRenderError`** (Sprint 5) instead of a silent warning.
  **Sprint 10 🟢 (2026-09-29): no silent black scenes.**
  - Every scene failure now raises `SceneRenderError` and refuses assembly. That covers a
    visual, compartment, overlay-rule or frame/mux error, an unreadable cached file and a
    failed `image_sequence` image. The error carries the step, the reason and a `suggested_fix`.
  - No scene-cache file is left behind, so the next run re-renders.
  - A legacy `{sid}_black.mp4` stand-in is dropped on cache hit, and `reburn` refuses while one
    exists.
  - `pipeline.utils.paths` is the one media-path resolver (project → repo root → cwd), shared by
    validate, compose and the still-gate.
  - AST fences keep `_black_screen`/`_black_clip` out; `_silence_gap` is the only black source.

  Silent `text_card` downgrades (`namecard`/`map`, `generated_image` provider failure) are E5
  part 2.
- **Toon (Sprint 9 🟢, 2026-09-28):** the `toon` visual type (`composer/toon.py` → `src/toon`)
  renders a wordless YAML scene file from the bank of Tim's picks (`assets/toon/bank/`) as
  deterministic 2.5D hand-drawn animation. It renders at 30 fps (`COMPOSE_FPS`), camera on
  ones, drawings at 12/s, soft line boil by default. Clip length = narration (two-axes fence
  in code). Every failure is a `SceneRenderError`. `pipeline toon validate|render|sheet`; a
  doctor toon check. See E9.
  - **Sprint 11 🟢 (2026-10-13, merged `55670c9`)** added the scene contract. Every field means what
    it renders or fails at load. Errors name the scene file or the storyboard file. Shots take
    `at: {sentence: n, plus: s}` and follow the narration. There is a drift warning, and
    `toon validate --narration/--duration` prints sentences and shot windows.
  - **Since the 2026-10-13 style lock (3D toy), this is the backup style's engine.** Its bank
    still holds the retired v0 doodle look, not the r8 soft-cel backup (see E9 item 4). The locked
    look's engine is **E11** (🔵, Sprint 12 proposed).
- **Known gaps (the demand):** **the locked own-show 3D toy look isn't a pipeline visual yet; only
  a throwaway tryout renders it (E11, Sprint 12 proposed)** · true book-page-turn animation · animated overlay *entrance*
  (E3 v2), lower-thirds, CapCut subtitles · coarse recompose loop (E6) · `namecard`/`map` and
  `generated_image` silent `text_card` downgrades (E5 part 2) · non-atomic scene-cache writes (an
  interrupted mux costs one refused run; Later, top). *(Claude-backed stages are restored on
  master: E10 merged at `2add7c2` and is 🟢, 2026-09-29.)*
  *(Reconciled 2026-09-29: Ken Burns on stills shipped with E2 camera motion; the E4 Slice 3
  medium-clash refactor shipped in Sprint 6.)*

See `.agent-memory/engineering-manager/arsenal-state.md` for the living inventory.

---

## Status legend

🔵 designed, not built · 🟡 in progress · 🟢 shipped · ⚪ idea / unscoped · 🔴 blocked

---

## Epics

Six are **arsenal-direction** epics (the demand-driven backlog: programmatic charts,
programmatic animation, animated overlays, the **audio arsenal** (E7), the **toon engine** for
Tim's own hosted shows (E9, 2026-09-27; now the backup style's engine), and, newest, the **3D toy
engine** for the locked own-show look (E11, 2026-10-13)). Five are **cross-cutting
infrastructure** that the arsenal needs in order to be traceable, safe, and iterable (E4–E6,
**E8** two-machine workflow & render portability, 2026-09-24, and **E10** Claude calls on the
subscription, 2026-09-29).

### E1 — Programmatic charts  `[arsenal]`  🟢 *v1 shipped (Sprint 1)*
Render data as **styled editorial graphics** (warm sepia / book-page feel), never a Plotly
dashboard. New `chart` visual type, two-pass like `rich_slide` (Flux draft background +
Pillow composite). chart_types: `stat_big_number`, `proportion_blocks`, `timeline`, `bar`,
`comparison` — all five in v1 (Tim's call, 2026-05-21).
- **Demand:** director keeps forcing real datapoints into `slide` because no stat-friendly
  type exists (baby-walker s10/s12/s13).
- **Source:** `tmp/chart-renderer-handoff.md`. **Precedent:** `composer/rich_slide.py`.
- **Unblocks:** stat beats render as real visualizations. **Does NOT** add runtime.

### E2 — Programmatic animation  `[arsenal]`  🟢 *v1 shipped (Sprint 2)*
Motion generated in-pipeline. v1 covers animated chart reveals for `line` / `bar` /
`stat_big_number` via PIL multi-frame → ffmpeg, mirroring
`composer/base.py:_camera_motion_to_video`. New `chart_type: "line"` (sixth static type)
+ animated `animate: {enabled, reveal_duration_sec, easing}` modifier. The baby-walker
**merged animated decline-curve** (1990→2014 with six regulation markers) is wired into
s21 as the acceptance vehicle.
- **Remaining in epic:** animated reveals for `proportion_blocks` / `timeline` /
  `comparison`; a *true* book-page-turn (current is an approximation).
  - **NOTE — already shipped (not "remaining"):** camera-motion image-to-motion is
    *done* — `image_to_video` applies a slow Ken Burns zoom to every still by default,
    `_camera_motion_to_video` supports `slow_push_pan` / `ken_burns` with configurable
    zoom (`composer/base.py`), and `composer/image_sequence.py` is a per-image
    Ken-Burns sequencer. Do not re-scope these as new work.
  - **🔵 3D scene renderer (Blender backend)** — true 3D geometry / mesh / physical
    lighting for video segments or still frames, the quality tier Pillow/FFmpeg 2.5D
    cannot reach. **First application:** a stock-quality book-page-turn (the current
    `book-page-turn-v2` is a 2.5D approximation). Spec already on disk:
    `docs/superpowers/plans/2026-05-13-3d-book-page-renderer-evaluation.md` (Blender
    headless, analytic page-curl mesh, reuses the `BookSceneSpec` geometry contract,
    Pillow v2 kept as fallback; "test example" = the benchmark/review-sheet harness in
    that plan's Slice 1). Demand-future, not demand-now — sits below Sprint 6 in the
    queue. *(Idea B, INTAKE 2026-05-26.)* **Cross-link (E11 INTAKE, 2026-10-13):** Blender still
    isn't installed. E11 will put a headless Three.js runner in the pipeline (pinned Chrome, GPU
    on both machines), so a future page-turn should weigh reusing that runner before adopting
    Blender. Decide when the page-turn has demand.
  - **🔵 AI image-to-video motion (beyond camera moves)** — true generated motion
    (parallax, subject/element animation) for beats where a static image + Ken Burns
    still reads as a slide. Uses the `generate-video` skill tier ($0.029/sec budget →
    $0.050/sec premium; cache by prompt hash). **Distinct from the shipped camera-motion
    path above** — this is generated motion, not a zoom/pan over a fixed frame.
    Demand-future, not demand-now. *(Idea C, INTAKE 2026-05-26.)* **First concrete demand
    (2026-09-27):** the own-show Seedance accent-shot test (restyle a toon animatic, ~$1, needs
    Tim's BytePlus ModelArk account; `docs/own-show.md` next step 3). It stays here and is **not**
    part of E9 v0. **Since the 2026-10-13 style lock**, the input to restyle would be an **E11** (3D
    toy) render rather than a 2.5D animatic. The test is still on hold for Tim's account, and it
    stays in E2, not E11.
- **Source:** chart handoff open-Q1; narrative-history handoff; future-tasks; 3D
  book-page renderer eval plan (2026-05-13); `generate-video` skill (image→video tier).
- **Depends on:** E1 (animated reveal needs the static chart substrate). ✅
- **Unblocks:** the decline-curve; count-up + bar-grow on stat-heavy beats; trend-over-time
  beats via `line`. **Does NOT** add runtime — `reveal_duration_sec` validated
  ≤ `scene_duration − 0.5s` (the two-axes rule, in code).

### E3 — Animated overlays  `[arsenal]`  🟡 *v1 shipped (Sprint 5, 2026-05-23); v2+ remaining*
Text/graphic layers composited *on top of* images / charts / slides: lower-thirds,
callouts, chart annotations, CapCut-style word-by-word subtitles. **Not greenfield** — a
*static* overlay layer already exists (`composer/overlay.py`: `title` / `namecard` /
`text_top` / `text_left` / `text_emphasis` / `corner_label`, all ffmpeg `drawtext`/`drawbox`;
collision-checker in `overlay_rules.py`). E3 adds **placement intelligence and motion**.
- **Demand:** the Sprint-2 chart marker-label horizontal overlap (`chart.py:529-539`, a
  crude 2-row `draw.text` stagger that overlaps when markers sit <5yr apart on a long span —
  observed on baby-walker s21) is the **named blocked beat**; plus know-fountains arsenal
  posture and future-tasks "center-screen animated subtitles for Shorts". Overlays register
  as **Style Manifest elements** (see E4).
- **Depends on:** E4 **Slices 1–2 (shipped Sprint 3)** so overlays register as traceable
  elements rather than new silent globals — the hard blocker is **cleared**. Overlays do
  *not* consume niche `visual_style`, so E4 Slice 3 (Sprint 6) is **not** a blocker.
- **Sprint 5 (v1) 🟢 shipped:** `composer/callout.py` — pure `place_callouts` geometry
  (vertical dodge + leader lines, row budget capped by header space, raises on exhaustion)
  + `_draw_placed_callouts` + `render_callouts` image wrapper. BOTH line paths route through
  it: static `chart._render_line` AND animated `chart_anim._animate_line_frame` (the path
  that actually renders s21 — same overlap bug, fixed via one shared primitive). Registered
  as a `kind="overlay"` Style Manifest element (aggregate-by-type). `apply_overlay` failures
  now raise `SceneRenderError` (loud). **v2+:** animated entrance for the callout,
  lower-thirds, CapCut word-by-word subtitles (static→animated split mirrors E1→E2).

### E4 — Style Manifest & traceability  `[infra · cross-cutting]`  🟢 *Slices 1–4 shipped; Slice 5 dashboard surface rolled to E6*
A first-class inventory of every style element active on a project — where it came from,
which scenes it applies to, how to remove it. Surfaces today's *silent globals*
(`frame_style`, niche `visual_style`, the unused anchor PNG, seed, rich_slide bg default).
- **Source:** `tmp/style-traceability-handoff.md` (5 slices). **Foundational:** animation
  (E2) and overlays (E3) register here as elements instead of new silent globals.
- **Shipped (Sprint 3):** `src/pipeline/style/` package; `pipeline style list/add/remove`;
  append-only `style_log.json`; `anchor_image` dead-code removed (Slice 4 — the no-op was
  deleted; img2img re-implementation explicitly deferred).
- **Shipped (Sprint 6):** **Slice 3** — niche `visual_style` medium-clash root refactor
  split template style into `medium_hint`/`palette`/`subject_bias`/`universal_rules`; the
  prompt assembler consumes palette + universal rules for all generated-image prompts and
  suppresses medium/subject hints when the scene prompt already specifies a photographic
  medium or strong subject. `visual.skip_niche_style` remains the explicit all-style escape
  hatch. EM REVIEW returned PASS on `feat/niche-visual-style-split`.
- **Rolled:** **Slice 5** — dashboard Style panel (E6 surfaces).
- **Concrete bug fixed:** niche `visual_style` no longer forces sketch/open-book medium
  contamination onto photo-realistic generated-image prompts.

### E5 — Scene validation & visual-decision checkpoint  `[infra · quality gate]`  🟢 *v1 shipped (Sprints 1, 4); render-truth still-gate shipped (Sprint 7 — two-layer, EM REVIEW PASS 2026-05-31); loud-failure sweep part 1 shipped (Sprint 10 — EM REVIEW PASS 2026-09-29)*
Defense-in-depth: a storyboard-write-time validator (per-type checks, taxonomy drift
detection) + compose-time hard failures replacing the old silent `text_card` fallbacks +
a `confidence`/`rationale` decision table the user reviews before TTS.
- **Shipped:** all-type `storyboard_validator.py` incl. the `chart` branch (Sprint 4),
  wired into `direct.py`; standalone `pipeline validate` CLI (Sprint 4); compose-time
  `SceneRenderError` for missing/corrupt `article_image` (5a33f0a); the decision table.
- **🟢 Render-truth still-gate (pixel-grounded pre-render quality gate) — Sprint 7, built
  two-layer on `feat/baby-walker-quality-pass`; EM REVIEW 2026-05-31 = PASS (shipped, after one
  REWORK round).** Today's defense-in-depth has TWO tiers — JSON-write-time validator (Sprint 4)
  → full ~10-min compose. There is **no third tier that judges the *composited frame***. So
  render-truth defects (clipped verbatim text, English labels on a zh-TW chart, a blank-grey
  map composite, as-rendered image duplicates) surface only AFTER an expensive full compose —
  the documented cause of the month-long baby-walker churn. This item adds the missing tier as a
  **two-layer gate** (Tim-approved descope 2026-05-30, forced by a hard constraint): a
  **still-composite path** (`render_scene` at minimal duration → 1 frame → `composite_scene_frame`
  book-wrap → overlays in the project variant → labeled contact sheet) feeding **Layer 1**
  (deterministic pure `(still, scene_meta) → list[Finding]` checks, the `validate_chart_visual`
  shape) + **Layer 2** (a scoped in-session model-vision pass). **As built:** Layer 1 ships
  `duplicate_frame` (phash+colorhash, `imagehash`) + `blank_substrate` (content-INSET dominant
  color, pure PIL). Layer 2 (in `storyboard-review/SKILL.md`) judges **meaningfulness** (the
  bordered-blank-map case Layer 1 cannot catch), **wrong-language text** (supersedes ex-check-3
  OCR — `tesseract` unprovisioned here, no passwordless sudo), and **clipping/overflow**
  (supersedes ex-check-4 bbox — the novel text-bbox instrumentation was high-risk/low-verifiability).
  **NO blanket model-vision ban for this scoped Layer-2 use** — Tim lifted the guard for it only
  (zero extra Anthropic billing, the `visual-review` pattern). **Variant-at-gen-time (piece C) is
  DEFERRED** (the principled form of the variant fix) — the gate reads `preferred_variant` via
  `resolve_variant`, which now **defaults to `no_overlay`** (judge the bare frame) when none is set.
  Slots into the existing Phase-3.5 `storyboard-review` skill gate (a skill that dispatches the
  `storyboard-critic` subagent — NOT a `direct.py` Python phase), AFTER the JSON-critic PASS,
  BEFORE TTS. Source: `docs/handoffs/2026-05-27-baby-walker-render.md` (the 4-defect fix-prompt),
  `tmp/baby-walker-visual-review-report.md` (s25 clip + s23 English-label render-truth defects),
  storyboard-critic standards (`.agent-memory/storyboard-critic/standards.md` — the no_overlay
  step-0 + blank-substrate + reuse lessons this gate enforces in code). **REWORK→PASS:** the first
  REVIEW caught that the gate defaulted to `plain` (overlays burned) at Phase-3.5 and missed the seed
  reused-map defect; the fix (default `no_overlay` + malformed-context guard + the I-1 render-error
  exit-1 hardening + persisted per-scene stills for Layer-2) landed and re-REVIEW PASSED, with the
  dup catch demonstrated on the defect snapshot via the wired path. CLI exit codes: 0 clean /
  1 tool-error / 2 findings; the SKILL refuses TTS on any non-zero. **Two-axes:** pure quality-gate
  (visual sub-axis); **ZERO runtime** — it inspects frames, never adds beats.
- **🟢 Loud-failure sweep, part 1: Sprint 10** (EM REVIEW PASS 2026-09-29, `bb16aa0`). No
  silent black scenes in compose or `image_sequence`, and one media-path resolver shared by
  validate, compose and the still-gate. See Sprint 10.
- **🔵 Loud-failure sweep, part 1b: atomic scene-cache writes** (parked by Sprint 10's final
  review; top of Later). `_mux` writes the scene finals in place. A SIGTERM or Ctrl-C bypasses
  Python cleanup, so Sprint 10's invariant I1 can't cover it. Today it is **loud, never black**:
  RF7 probes both cached files, so the next run refuses with `cached scene failed` and deletes
  them, and the run after that re-renders. Write to a temp file, then `os.replace`. That turns
  "one refused run" into "a clean re-render". The spec's deferral premise ("I1's cleanup covers
  the failure case") was wrong for signals. **Queue (E11 INTAKE, 2026-10-13):** it comes after
  Sprint 12, or before it if Tim's GuoGuo freeze lags the greenlight (about 0.25 session, and
  independent of Sprint 12's files).
- **🔵 Loud-failure sweep, part 2: silent `text_card` downgrades** (split out of Sprint 10).
  `namecard`/`map` render as a text card (`composer/base.py:461-470`), and a `generated_image`
  provider failure renders the narration as a text card (`composer/image.py:177-181`); the
  image edit-mode fallback (`image.py:129-133`) also stays silent. Not sprint 10 material: the
  director taxonomy emits `map`/`namecard` (`direct.py:216-217, 257`; 6 `map` + 1 `namecard`
  in hub storyboards), so going loud needs a taxonomy decision (retire `namecard` to
  `overlay.namecard`; a real `map` type or route to `generated_image`). It rides the next
  `stages/direct.py`-touching sprint; the provider-failure half is a budget-policy call for Tim.
- **🔵 Locale-portability lint** (Tim 2026-05-29, designed-not-built, **NOT next** — below
  current priorities): flag scenes whose visual carries **locale-locked (non-English)
  baked-in on-screen text**, surfaced in the decision table, so a video stays portable to
  future multi-language audio tracks (we already ship MLA — `--mla --secondary-locale`;
  this is the visual-side complement). The standing authoring principle — prefer
  language-neutral visuals (numeric/chart → image-only → icon/emoji), and when on-screen
  text is unavoidable default it to **English (en-US first)** — lives in the EM
  `standards.md` "Anatomy of a new visual type" (step 8) as a cross-cutting bar; the
  director-prompt-bias half rides the next `stages/direct.py`-touching sprint. **Orthogonal
  to both axes** (portability/i18n — neither slideshow-quality nor runtime).
- **Interface with E1:** chart validation hooks (`chart_type` in set, `data` matches
  schema) live here; the chart branch delegates to `composer/chart.py:validate_chart_visual`.

### E6 — Compose efficiency & dashboard surfaces  `[infra · feedback loop]`  🔵
Tighten the iteration loop so new visuals can be tuned without full re-renders:
`compose transitions` / `compose frame`, contract-aware cache invalidation, Production
Contract panel, render-freshness warnings, transition UI redesign, preview contact sheets,
and (later) Style/Decision panels feeding from E4/E5.
- **Source:** `tmp/dashboard-transition-workflow-improvement-plan.md` (5 phases). Some
  transition/frame groundwork already shipped (`book-page-turn-v2`, open-book frame).

### E7 — Audio arsenal & SFX legibility  `[arsenal · audio]`  🔵 *new epic (2026-05-26, Tim-approved); first sprint (music/audio-axis) engineering on master `12bfce3` but EM REVIEW 2026-05-29 = ADVISE — stays 🔵 pending real-scene demo + licensed tracks*
The **audio axis** of the quality north star. Until now the EM mandate was visual-only; E7
formally extends it to what the pipeline can *score, layer, and surface* in sound — SFX,
ambient, music — with the same standards (traceability, loud failure, two-axes discipline).
Quality now spans visual **and** audio; the **runtime invariant is unchanged** — SFX/ambient
over a 4-min scene adds zero seconds, exactly as richer rendering does not.
- **Audio baseline today (what ships):** SFX is **transition-scoped** (`Transition.sfx`,
  `src/pipeline/storyboard.py:27`); the only multi-cue mixing is
  `book_scene._build_paged_sfx_track` (`src/pipeline/composer/book_scene.py:554`, `amix` of N
  page-turn hits). Asset pool: `assets/sfx/` (today `page_turn.wav` + `.gitkeep`). Dashboard
  substrate: `/api/sfx/list` + `/api/sfx/upload` (`src/pipeline/dashboard/server.py:55-796`).
  A general per-scene SFX / ambient / music layer does **not** exist yet.
- **Source / design spec:** `docs/superpowers/specs/2026-05-15-book-page-turn-sfx-design.md`
  (the existing page-turn SFX design). Demand raised 2026-05-26 (INTAKE); Tim approved the
  formal epic.
- **Folded-in backlog (both 🔵 designed-not-built — neither is "next"):**
  1. **SFX asset registry / config legibility + cross-project reuse** — a catalog over
     `assets/sfx/` with per-asset metadata (name, source, license, default volume/role) so
     SFX choices are legible in storyboard/config and reusable across projects instead of
     re-discovered per video. *(Migrated 2026-05-26 from `docs/future-tasks.md` → Pipeline &
     Infrastructure.)*
  2. **SFX layer / overlap visibility (dashboard surface)** — surface the SFX cues active on
     a project (and where they overlap) so layering is manageable from the dashboard rather
     than hand-traced through the storyboard. **Scope caveat:** today's "overlap" is
     transition-SFX bleeding into adjacent narration — a general per-scene SFX layer does not
     exist yet, so this partly anticipates demand. *(Migrated 2026-05-26 from the E6
     "Later/unscoped backlog"; it sits in E7 now, not E6, because audio is its own axis even
     though item 2 is delivered as a dashboard surface.)*
- **Depends on:** none blocking for the registry (item 1); item 2 leans on the E6 dashboard
  surface machinery. **Unblocks:** legible, reusable, traceable audio — an **audio-quality**
  lift. **Does NOT** add runtime.
- **Music / audio-axis (first E7 sprint — engineering on master `12bfce3`; 🔵 pending demo):**
  built off-roadmap (no SPRINT proposal / no pre-merge greenlight; merged to master locally),
  EM gated it post-hoc 2026-05-29 = **ADVISE, NOT PASS**. **Shipped engineering:**
  `Scene.music_mood` + `Theme.music_default_mood` schema; `src/pipeline/composer/music.py`
  (`plan_cues` → `build_bed` full-length 48k bed clamped to total length → `duck_bed`
  sidechain → idempotent `mux_music_onto_final`); `pipeline compose music --project-id`
  (re-mux, no scene re-render); `assets/music/` scaffold + `library.json` license manifest.
  **Two-axes fence in code** (bed clamped to existing video length; video stream-copied; mix
  keyed to narration duration — music cannot extend runtime). **Loud failure** on a
  used-but-unstocked mood. **Why still 🔵, not 🟢:** the music library is **empty** (no
  license-clear tracks), so the spec's named real-scene demo (baby-walker s19→s23 dark→hopeful
  arc, narration intelligible under the bed — `docs/superpowers/specs/2026-05-29-music-audio-axis-prompt.md`
  point 5) **could not run**. 🟢 requires proof on real content. **To advance:** source free
  tracks → populate `library.json` → run the demo + save the intelligibility artifact → a
  separate code-correctness review → summon EM REVIEW again.

### E8 — Two-machine workflow & render portability  `[infra · iteration loop]`  🔵 *new epic (INTAKE 2026-09-24, Tim-decided topology)*
The pipeline now runs on **two machines**: the **Hub** (this Linux box — i5-7400, 4 cores, HDD
system disk, always on; owns dashboard, tunnel, Telegram, discovery, publish, YouTube tokens;
project data on the SSD volume via the `output/` → `/mnt/windows_ssd/content-creation/output`
symlink, NTFS/ntfs3, commit `97cb4b9`) and the **Workshop** (M3 MacBook Pro, 18 GB, daytime only;
dev + fast iteration). Tim wants the Mac to render **both quick previews AND full finals**.
Standing rule: **code syncs via git/GitHub only; project data (`output/projects/<id>`) syncs by
copy; a project is owned by exactly one machine at a time.**
- **Two-axes:** neither axis directly — this is an **iteration-speed / portability** lift. It
  adds zero runtime and zero rendered capability; it shortens the look-fix-rerender loop, which
  serves quality indirectly. Never cite E8 as a quality or runtime gain.
- **Relationship to E6:** E6 = fewer/cheaper re-renders (scoping); E8 item 3 = cheaper *each*
  render (encode profile). Complementary, not duplicates — cross-link, do not merge.
- **Items (priority order, Tim 2026-09-24):**
  1. **🔵 Cross-platform font resolution + Linux-assumption audit — BLOCKER for any Mac render.** *(Sprint 8, proposed 2026-09-24 — spec `docs/superpowers/specs/2026-09-24-e8-cross-platform-fonts-design.md`.)*
     Hardcoded Linux Noto CJK paths: `composer/rich_slide.py:22-25`, `outro/builder.py:13-14`,
     `composer/compartment_renderers/running_out.py:17-20`. Also `stages/compose.py:248`
     `_title_font` **silently falls back to `ImageFont.load_default()`** (no CJK glyphs → tofu,
     no error) — convert to loud failure under the same resolver. One resolver
     (`utils/fonts.py`-style: config override → `fc-match` → known macOS paths → raise
     `FontResolutionError`), consumed by every PIL call site; ffmpeg `drawtext` family names
     (`"Noto Sans CJK TC"` in `storyboard.py:262`, `overlay.py`, `slide.py`, `text_card.py`,
     `utils/ffmpeg.py`) must resolve via fontconfig on macOS too (Homebrew ffmpeg + installed
     Noto CJK) — verify, don't assume. Audit scope: ffmpeg flags/filters, `animation_review.py`
     playwright/chromium path, any other `/usr/...` literals. **Folded consistency fixes:**
     `cli_storyboard.py:428` `Path("output/projects")` → `PipelineConfig().OUTPUT_DIR`; same
     class `utils/gallery.py:23` + `composer/base.py:365,391` `Path("output/gallery")`.
     **Acceptance must include a render-truth check on macOS** (a zh-TW `rich_slide` +
     `text_card` + overlay still actually showing CJK glyphs, artifact saved) — the EM cannot
     run the Mac, so the build supplies the artifact. **Golden-PNG risk:** freetype/font-build
     differences will make PIL goldens diverge on darwin — decide explicitly (hub-canonical
     goldens + darwin tolerance/skip), don't let the suite go red-on-Mac silently.
     *Depends on:* none. *Unblocks:* any Mac render (previews and finals).
  2. **🔵 Project checkout/checkin between machines.** `pipeline project checkout <id> --from hub`
     / `pipeline project checkin <id>` over Tailscale rsync; an **ownership lock on the hub**
     (lock file in the project dir: owner machine, timestamp, git SHA) that the **dashboard
     shows** and that **blocks hub-side edits/renders/job-queue actions** while checked out
     (loud refusal, explicit `--force-release` escape). Must support **Mac renders the final →
     checkin pushes it back → hub publishes** (checkin carries `final*.mp4` + `context.json` +
     storyboard; hub verifies integrity + that the final is not a draft — see item 3). NTFS
     target: rsync without perms/owner, `--modify-window` for mtime, symlink behavior checked.
     *Depends on:* item 1 for the render half to be useful (the sync/lock mechanics themselves
     don't). *Interim:* manual rsync + "don't touch it on the hub" convention until this lands.
  3. **🔵 Draft/preview render mode.** An **encoder-profile seam** (today ~44 `libx264`/preset
     call sites across `src/pipeline/`) with profiles `final` (libx264 medium, unchanged) and
     `draft` (720p + fast encode; hardware encoder when available — `h264_videotoolbox` on M3,
     `h264_nvenc` on the hub's GTX 1050 [measured ~4.5× libx264 medium at 1080p per `docs/mac-setup.md`; supersedes the earlier `h264_qsv` guess] —
     probed at runtime, logged fallback to libx264 `veryfast`). Draft output must be **marked
     non-publishable** (filename suffix + `context.json` flag) and `compose.py:_validate_bitrate`
     must be profile-aware (skip or draft threshold — not trip, not silently pass a draft as a
     final). **Publish refuses a draft-flagged final** (loud). Draft must not poison the final
     render cache (separate cache keys per profile). *Depends on:* item 1 (to matter on the Mac);
     item 2 for the publish-guard handoff path, but can ship before it.
- **Recommended order:** **1 → 2 → 3** (Tim's order holds). Item 1 is a hard blocker and small.
  Item 2 before 3 because a full-quality Mac render is already fast on an M3 and the real risk
  of two machines is **divergent project state** (hub dashboard edits vs Mac edits), which only
  the lock prevents; item 3 is a pure speed multiplier and is safe to follow.
  **Re-ordered 2026-09-27:** E9 v0 (Sprint 9) goes ahead of item 2 on Tim's direction. Toon
  bank and scene files live in git and renders are deterministic and regenerable, so toon work
  does not add to the divergent-state risk; the interim manual-rsync convention still holds.
  **Re-ordered 2026-09-29:** Sprint 10 (E5 loud-failure sweep, Tim-greenlit) and then E10
  (Claude calls on the subscription, which unblocks production) go ahead of item 2.
  Sprint 10 and E10 have both shipped (🟢). The small E5 part 1b
  slice (atomic scene-cache writes) is recommended just ahead of item 2.
  **Re-ordered 2026-10-13:** Sprint 11 (E9 item 2, Tim-greenlit) goes first, then E5 part 1b,
  then item 2.
  **Re-ordered 2026-10-13 (E11 INTAKE):** Sprint 11 merged. Sprint 12 (E11 v0, proposed) is next,
  then E5 part 1b, then item 2. E5 part 1b fills the gap if GuoGuo isn't frozen when Tim
  greenlights. E11 bank-fill sprints go ahead of item 2 once Tim's EP1 script names what they need.
  - **E8 cross-links for E11:** the 3D engine renders on both machines, Mac Metal ~85 ms and hub
    GL-EGL ~188 ms a frame at 1080p. So own-show finals render wherever the project lives (the Mac
    today), and item 2's ownership lock governs any move.
  - Item 3's draft profile is where an E11 draft render (960×540, GTAO off) would be marked
    non-publishable.

### E9 — Toon engine & resource bank (own-show character animation)  `[arsenal]`  🟢 *v0 shipped (Sprint 9; EM REVIEW PASS 2026-09-28 after two REWORK rounds); item 2 = **Sprint 11** 🟢 (merged `55670c9`); **style LOCKED 2026-10-13 on a 3D toy look: this 2.5D engine is now the backup style's engine, in maintenance**. The production look is **E11**. The held items and item 3 were re-homed at the E11 INTAKE (2026-10-13)*
A deterministic **2.5D hand-drawn character-animation** visual type for Tim's own hosted videos
(`docs/own-show.md` is the top guideline for those videos and overrides the porting defaults).
A code rig (cairo) draws the frozen character (Tim: likeness 2, short crop A, navy hoodie,
line A marker) and other picked characters, ghosted sets, props and wordless explainer graphics:
3D joints, props and camera, flat boiling linework, drawings on twos and camera on ones. Scenes
are YAML files that name bank items and always render the same frames. The pipeline gains a
`toon` visual type; Tim's A-roll stays an ordinary `clip`.
- **Demand:** `docs/own-show.md` order of work, step 2 (resource bank) and step 3 (scene
  scripts reference bank items by name and render consistently by construction); scene library
  001 (`docs/own-show-scenes.md`), which Tim says meets his quality bar. Tim, 2026-09-27: build
  v0 next.
- **Spec:** `docs/superpowers/specs/2026-09-27-toon-bank-v0-design.md` (commit `9baf4dc`,
  approved 2026-09-27). **Precedent (port, don't rewrite):** the throwaway r4 rig
  (`output/projects/20260724-hybrid-ai-agent-controller/style-tryouts/r4/rig_r4.py`,
  `character_tim.py`) and `output/own-show/scenes/001-lioness-dishes/scene_lioness.py`.
- **Why a new epic, not an E2 item:** E2 covers motion over existing pipeline visuals (chart
  reveals, camera moves). E9 is a separate subsystem (`src/toon`: engine, kit, bank, scene
  model, renderer) with its own data bank and scene format, its own demand line (Tim's hosted
  show, not ports) and its own follow-on backlog. It is still programmatic animation, so the E2
  lessons apply: `frame()` is pure, and determinism is tested before any golden.
- **Two axes:** production quality (visual). **Zero runtime.** A toon scene lasts exactly as
  long as its narration (spec §5). If the narration is longer, the last shot holds, still
  boiling. If it is shorter than the last beat, loading warns and the scene is cut at the
  narration's end. That rule is the in-code fence. EP1's runtime comes from Tim's script,
  never from the engine.
- **Locale-portable by construction:** no words are drawn. The scene loader rejects free-text
  fields and graphics take icon names only (standards step 8, enforced in code).
- **Cross-links (not merged):**
  - **E2:** the Seedance accent-shot test is E2's AI image-to-video line.
  - **E3:** toon-kit graphics (pictogram bubble, ✗ card, ✓ pill, pop-ins) are drawn inside the
    toon renderer; they are not the E3 overlay layer.
  - **E4/E6:** registering toon as a Style Manifest element and giving it a dashboard surface
    are deferred.
  - **E8:** hub-canonical goldens use `tests/golden_policy.py`; the toon check extends
    `pipeline doctor`.
  - Retargeting the audience-lens critics is `own-show.md` step 5 (content/critic work, not
    tracked here).
- **Style LOCKED (own-show step 1, Tim 2026-10-13): 3D toy, in the smooth Animal Crossing look**
  (the r7-3d look A Three.js tryout). The drawn soft-cel look (`r8/`) is the backup style, and
  **this 2.5D `toon` engine is now the backup style's engine.** Earlier, Tim rejected the v0
  doodle look (2026-09-28) and the editorial cut-paper look (2026-10-13). `docs/own-show.md`
  step 4b holds the record. What the lock changes here (the EM noted it at the Sprint 11
  follow-up REVIEW):
  - **The production engine for the locked look is E11** (INTAKE 2026-10-13; Sprint 12 = v0,
    proposed).
  - **Sprint 11's scene contract carries over, as one scene language.** That contract is the
    scene schema, sentence anchors, the splitter, drift warnings, loud load errors and
    source-named `SceneError`. Sprint 12's Phase 1 makes `toon.scene` validate against a
    `SceneCatalog` protocol (names plus per-engine capabilities) instead of the 2.5D `Bank`. It
    adds an `engine:` key (default `toon2d`) and splits an engine-neutral symbolic timeline out
    of `state_at`. Scene 001 stays byte-identical. From then on the contract is shared code that
    E11 actively extends; E9 keeps the 2.5D engine.
  - **Own-show step 3 is met for the backup engine only.** The locked look meets it when E11
    v0 passes.
  - **Held items and item 3, re-homed (E11 INTAKE):**
    - 2c laptop ✓/✗ → E11 item 3, a 3D bank item from Tim's pick.
    - 2b `style.yaml` wiring → designed in for the locked look: the E11 look is bank data
      (Sprint 12 row S12-7). For the backup engine it waits on item 4.
    - 2d contact sheets → E11 item 4 for the 3D bank; for the backup, item 4.
    - Item 3 (after v0) → E11 items 3, 8 and 9. Those are word-level timing, A-roll
      transitions, vertical framing, a `direct.py` entry, explainer graphics, and more
      characters and sets.
  - **The two-axes fence is unchanged.** Any engine's scene lasts exactly as long as its
    narration.
- **Items:**
  1. **🟢 v0: engine + bank + scene file + `toon` visual type** (Sprint 9). Shipped on master
     `2f6fb35`; EM REVIEW PASS 2026-09-28. It renders at 30 fps with drawings at 12/s (Tim's
     pick A), which matches compose's concat rate. See Sprint 9.
  2. **🟢 v0 residuals → Sprint 11** (parked by the v0 final review, 2026-09-28; **Tim greenlit
     finishing step 3 on 2026-10-13**; EM follow-up REVIEW = PASS at `d1c346c`; merged
     `55670c9`). The demand is EP1 scene authoring. Sprint 11 built the style-independent part:
     a, the 2b splitter / card key / `SceneError` file name, the 2d `validate` flags, e and f.
     **Held:** c (laptop ✓/✗), the 2b `style.yaml` wiring and the 2d contact sheets. They were
     re-homed at the E11 INTAKE (see "Style LOCKED" above). Scope table: spec §11.1. The items as
     filed:
     - **a. Loud-failure debt.** Some fields are still accepted and silently ignored: `ease` on
       `show`, `over`/`ease` on `hide`, `flicker`/`blink`/`out` on plates, and top-level hair
       keys beside `layers:`. Spec §5 documents them; they should fail at load (standards:
       no silent fallbacks).
     - **b. Correctness:**
       - Two cards with the same icon collide on one key.
       - The sentence splitter mishandles 「」 quotes and abbreviations like "U.S.". This
         matters once zh-TW narration drives `at: {sentence: n}`.
       - `SceneError` names the path inside the file but not the scene file; spec §5 says both.
         Deferred out of v0; Tim acked 2026-09-28.
       - `style.yaml` `line`/`palette` aren't wired into renders. The engine uses constants that
         a test holds equal, so an edit fails CI instead of changing the look.
     - **c. Kit gap with named demand:** the laptop has no ✓/✗ screen states, and EP1's "agent
       errors" beat needs them. This needs Tim's pick (options → pick → freeze).
     - **d. Tooling:**
       - Pose and prop contact sheets (spec §4). v0's `sheet` writes the model sheet only.
         Deferred out of v0; Tim acked 2026-09-28.
       - `toon validate --narration/--duration`.
     - **e. Hygiene:**
       - a `PROP_KINDS`↔`PropDef.kind` sync test;
       - the camera `over`/`ease` rejection relies on `model_fields_set`;
       - render workers reload the bank from disk.
     - **f. Timing:** shot boundaries don't scale with the TTS duration; only the last shot
       holds or is cut. **Sprint 11 fixes it without word-level timing:** shots take
       `at: {sentence: n, plus: s}`, plus a drift warning (spec §11.2 f). Word-level timing
       stays in item 3 and later swaps in behind the same `sentence_starts` seam.
     - **g. ~~Frame rate~~ → fixed in Sprint 9 as REWORK R1** (30 fps, drawings 12/s; guard +
       cadence tests). ~~The leftover "on twos" wording in spec §4/§5~~ was fixed in the
       Sprint 11 spec edit (2026-10-13).
  3. **→ re-homed to E11 (INTAKE 2026-10-13).** ~~After v0 (spec §10, unscoped)~~. Word-level
     timing, host A-roll ↔ toon transitions, Shorts/vertical framing and the conditional
     `stages/direct.py` entry don't depend on the engine; they are now E11 item 9. More
     characters and sets come from Tim's picks for the locked look (E11 item 3). Explainer
     graphics are E11 item 8. As filed:
     - word-level timing (Whisper word timestamps)
     - more characters and sets, from Tim's picks only
     - explainer-graphic kinds (map, timeline, arrows between cards). These are wordless and
       drawn in line A; E1 chart types can inform them, but they don't reuse the PIL chart
       renderer.
     - host A-roll ↔ toon transitions
     - Shorts/vertical framing
     - a `stages/direct.py` taxonomy entry, only if EP1's scene breakdown shows the director
       should emit `toon`
  4. **⚪ Dormant: a backup restyle** (filed at the E11 INTAKE, 2026-10-13). The 2.5D bank still
     renders the **retired v0 doodle look**. The backup style, the r8 drawn soft-cel, exists only
     as a throwaway tryout (`style-tryouts/r8/`). So today the backup is a cross-check sketch,
     not a pipeline-renderable style.
     - If Tim ever activates it: port r8 into `assets/toon/bank/`, with Tim's picks; wire
       `style.yaml` `line`/`palette` (the held 2b item); add the pose and prop contact sheets
       (2d); and re-mint the scene 001 goldens with Tim's eyeball. The ⚪ `bob` lift fix (Later)
       rides along.
     - **Trigger:** Tim activates the backup. Not before.
- **Non-goal (Tim, 2026-09-27):** no EP1 scene or story composition until Tim gives the
  outline and plot. Composing EP1 scenes is content work (`own-show.md` step 6) and does not
  belong on this roadmap. Scene 001 appears only as v0's worked example and acceptance test.

### E10 — Claude calls on the subscription  `[infra · production unblock]`  🟢 *v1 shipped: merged to master `2add7c2` (2026-09-29) after EM REVIEW = ADVISE; F1 (`09fa1c6`) and F2 (`b51efb3`) verified at the EM follow-up on master `53b1df3` (both tests green, 3 of 3 mutations red) → **PASS***
Every Claude-backed step calls the Anthropic API directly through the `anthropic` SDK, and the
API credit is exhausted (`400 credit balance too low`, found at the Sprint 9 hub smoke,
2026-09-28). Tim, 2026-09-29, verbatim: "replace with main agent or subagent ability or "claude
-p" to do, we have extra quota in subscription". Model pick (Tim, per the spec): "Creative on
Opus, checks on Haiku". Claude Code CLI 2.1.283 is installed on both machines.
- **Spec (v1):** `docs/superpowers/specs/2026-09-29-claude-cli-llm-backend-design.md` (commit
  `e65f8fa`; Tim approved the written spec, "looks good, proceed"). It uses a `pipeline.llm.complete`
  facade with a `claude -p` backend by default and the SDK as an opt-in `api` backend, and it
  migrates 12 call sites. Agent mode (main agent or subagent answering a prompt file) is a spec
  non-goal. The spec, not this entry, is the design.
- **Demand: production is blocked today.** Down: `analyze`, `scriptwrite`, `direct` (storyboard,
  shorts, `metadata.json`), storyboard beats, `proofread` at the review gate, `storyteller`,
  `visual-review` / the post-compose QC, `image-alignment`, the `mla` rewrite and compose's
  `style_anchor` source assessment. Unaffected: every renderer and the toon engine (E9), which
  cost $0.
- **Axis:** neither quality nor runtime. It restores the Claude-backed stages and moves their
  cost from the API budget (`CLAUDE.md` Budget table, "Claude Sonnet API ~$10") to subscription
  quota. The creative-tier move from Sonnet to Opus is Tim's model pick; do not cite E10 as a
  quality-axis gain.
- **Loud-failure posture (EM note):** the spec raises `LLMError` with the real CLI or quota
  message, with no silent backend fallback, and **keeps each call site's fatal-vs-advisory
  behaviour**. So `style_anchor._assess_source` still falls back to `"medium"` and the
  post-compose QC stays advisory; both now print the real reason. That is Tim's call in the spec,
  not a gap. The QC **opt-out flag** is not in the spec and stays a Later item.
- **Cross-links:** ROADMAP Later "Post-compose Haiku visual-QC opt-out" (same call site; it
  stays). The `visual-review` decorator bug (`c.print(table)@visual_review_app.command(...)`) was
  **folded into E10 and fixed** (`94c24ba`, test `12aed26`): `extract-frames` is registered and
  `print_visual_issues_table` no longer raises. Still open, outside E10: `--project-id` is typed
  `int` in `cli_visual_review.py`, so real string ids only work through `--work-dir`.
- **Order:** built in parallel with Sprint 10. Merged to master `2add7c2` (2026-09-29), with F1
  and F2. Sprint 10 passed REVIEW the same day and merged on top as `53b1df3`.
- **Follow-up REVIEW 2026-09-29 (EM, Mac master `53b1df3`) = PASS → 🟢.**
  - Both F1/F2 tests pass. The E10 targeted suite gives 109 passed. The full suite gives 1440
    passed / 62 skipped; ruff and mypy are clean (161 files).
  - Mutations in a `git archive` copy of `53b1df3` all went red:
    - F1, the pre-fix parser (blank lines kept): red;
    - F1, the hint dropped: red;
    - F2, the metadata site flipped to `check`: red. At the first REVIEW this mutation left
      everything green.
  - With F2 pinned, all 12 call sites now go red on a tier flip.
- **REVIEW 2026-09-29 (EM, both machines, `f13c783`) = ADVISE, cleared to merge.**
  - **Done criteria (spec §6):**
    - §6.1: Mac suite 1404 passed / 62 skipped; targeted 108 passed; ruff and mypy clean.
    - §6.2: hub doctor 18/18 with the `llm` check passing (the Mac too); real-CLI integration 3/3
      on both machines. Hub suite 1439 passed / 27 skipped.
    - §6.3, the builder's hub calls: proofread (Haiku, 142 s, 14 issues), beats (Opus, 5 s) and
      metadata (Opus with a JSON schema, 17 s).
    - §6.3, the image site: the builder called `style_anchor`, which §6.3 doesn't name, so **the
      EM ran visual-review (site 9) itself**. On a sandbox copy of baby-walker: 27 frames, 61.9 s,
      2 issues parsed. Evidence on the hub: `.worktrees/llm-cli-backend/tmp/claude-cli-backend/em-review-visual.txt`.
    - §6.4 budget tables ✓. §6.5: per-task reviews, a final Opus review and a re-review of its
      fix wave ✓.
  - **Loud failure holds**, checked by mutation in a `git archive` copy. Each of these went red:
    - a CLI failure returning empty;
    - an unknown backend falling back to the CLI;
    - no billing-env strip;
    - an `anthropic` import at a call site;
    - the prompt on argv;
    - `--strict-mcp-config` dropped;
    - an empty result accepted;
    - image blocks dropped;
    - doctor passing with no binary;
    - the tripwire removed.
  - **Axis:** neither quality nor runtime (held).
- **Items:**
  1. **🟢 v1: the `claude -p` backend and the 12 call-site migrations** (spec §2–§6). Merged
     `2add7c2`. Test-plan rows are under E10.
  2. **🟢 F1 + F2, fixed and verified** (history below; EM follow-up PASS on `53b1df3`):
     - **F1: `style_anchor` loses its style hint on every CLI answer.** Haiku replies
       `"Medium\n\nSerif typography, …"`, 3 of 3 runs on the hub. The unchanged parser takes the
       blank line 2 as the hint, so it is always `""`, and nothing logs it.
       - Effect: the hint never reaches `style_descriptor` (the lowest-precedence
         `style_prefix`, used for non-niche projects and dup-guard replacement prompts).
       - The suitability value still parses.
       - Fix: skip blank lines when parsing, plus a test pinned on the real answer shape.
     - **F2: the metadata site (5) doesn't assert its tier.** Flipping it to `check` leaves every
       test green; the other 11 sites go red. Spec §5 asks for each site's tier.
  3. **🔵 Follow-ups (not gating):**
     - **Extended thinking is on.** `claude -p` runs Haiku with thinking on: every check call
       tested emitted a `thinking` block, 289–806 output tokens for a two-line answer. That
       explains the 142 s proofread, about a quarter of the 600 s timeout; a timeout raises
       loudly. Log each call's duration and output tokens, and check whether thinking can be
       turned off for the check tier. Verify the setting against CLI 2.1.283 first (spec §3: "don't
       improvise").
     - ~~README's env table lacks `PIPELINE_LLM_TIMEOUT_CREATIVE_SEC`~~: done in `b51efb3`.
     - Spec §3 asks for `asyncio.to_thread` at async call sites. `scriptwrite`, `metadata` and
       `style_anchor` still call synchronously from async stages. There is no effect today:
       stages run one at a time, and the dashboard runs jobs off its event loop. Wrap them or
       amend the spec wording.
     - `docs/workflows.html` still says "Claude Sonnet API". Ask Tim before editing it (CLAUDE.md).

### E11 — 3D toy engine & bank (the locked own-show look)  `[arsenal]`  🔵 *new epic (INTAKE 2026-10-13, Tim: "yes, do both"); v0 = **Sprint 12**, proposed, not greenlit*
The production engine for the own-show style Tim **locked on 2026-10-13: a 3D toy in the smooth
Animal Crossing look** (r7-3d look A). Characters, sets, props, poses, expressions and camera feels
become bank data from Tim's picks. Scenes are files in the **same scene contract** as E9. Renders
are headless and deterministic, run through compose like any scene, and are guarded by goldens on
both machines.
- **Demand:** `docs/own-show.md` next step 4b ("production 3D toy engine … driven by the same
  scene-file contract, rendered headless and deterministic, with compose integration and
  cross-machine goldens"). The style-lock record is under "Style exploration — status". Tim's
  direction (2026-10-13): pan, tilt and zoom must be easy, and GuoGuo appears in every scene.
- **Precedent:** the throwaway r7-3d tryout
  (`output/projects/20260724-hybrid-ai-agent-controller/style-tryouts/r7-3d/`: `scene.js`,
  `render.mjs`, `stage.html`, README "With more time I'd…") for the look and the builders. `src/toon`
  for the bank/scene/render/goldens shape.
- **Why a new epic, not E9:** a different runtime (Three.js in headless Chrome, not cairo), a
  different bank (3D meshes, joint poses, face decals, materials), different determinism physics
  (GPU rasterisation) and its own backlog. The scene contract is **shared**, through a seam that
  doesn't depend on either bank, not a second scene format. E9 keeps the 2.5D backup engine.
- **Two axes:** production quality (visual). **Zero runtime**: the clip lasts exactly as long as
  the narration (the shared contract's fence, plus a frame-count test). **Locale-portable:** it is
  wordless. The contract rejects free text, and the engine JS has a no-`fillText` fence.
- **Engineering decisions (INTAKE 2026-10-13; EM probes on both machines, scratch only):**

  | Question | Decision | Evidence / why |
  |---|---|---|
  | Render runtime | Headless Chrome + **Three.js r170**, vendored (MIT, `SHA256SUMS`). Driven from Python by a uv-locked **`playwright`**, which launches a **pinned Chrome for Testing** build. No Node on the render path; no Remotion; no Blender. | The locked look *is* this renderer's output (vinyl materials, GTAO, bloom, Neutral tone mapping), so another renderer would change what Tim locked. Blender isn't installed. CfT 151 (playwright build 1234) is already on both machines. The hub's Node is nvm-only and not on a systemd `PATH`. |
  | GPU backend | Allow-list: Mac `--use-angle=metal`, hub `--use-angle=gl-egl` (GTX 1050). Read the WebGL renderer string at start and **refuse** SwiftShader, Vulkan or anything unlisted, loudly. A **blank-frame guard** means a uniform frame is never encoded or cached. | The hub is **not** SwiftShader-only: GL-EGL gives WebGL2 on the GTX 1050. Default flags silently fall back to SwiftShader on both machines, and it didn't finish one 1080p frame in 10 min on the Mac. Hub ANGLE-Vulkan returns all-black frames with no error. |
  | Determinism and cross-machine goldens | **Three layers.** A: the symbolic timeline state, Python, exact, default suite. B: the applied scene graph from JS (no GL context), ≤ 1e-6 on both machines. C: pixel goldens, **hub-canonical**, 960×540, compared **on both machines** with a calibrated tolerance; minted on the hub only. | Mac Metal is byte-identical run to run, and across Chrome 155 and CfT 151. Hub GL-EGL wobbles ≤ 1 level. Mac vs hub: mean 0.14/255, 0.05% of pixels > 8, max 129 on silhouette edges and fur tips. So byte-exact `golden_policy` can't hold. A tolerance alone could miss a small decal swap, so layers A and B catch logic exactly. |
  | Render speed vs compose | Fine as is. At 1080p, including the PNG transfer, the Mac takes ~85 ms a frame (~12 fps) and the hub ~188 ms (~5 fps). 3 min of toy footage ≈ 8 min on the Mac or 17 min on the hub; the scene cache makes re-renders free. Speed work and a draft profile are deferred (item 7). | Measured over 30-frame runs. |
  | Bank format | **YAML with `picked:` provenance** (the E9 precedent). Python validates it, and the page gets resolved JSON. Geometry is **code-built** (the tryout's builders, parameterised by bank data). A **`gltf:` part source** (frozen GLB + sha256) is reserved for sculpted parts, built when the first pick needs one. **Expressions** are per-character named face decals drawn in code. **Poses** are per-character named joint rotations, with a class and optional loops; they blend on the beat's `over`/`ease`. **The look** (palette, post, lights) is `style.yaml` bank data, with no look constants in engine code. | Picks frozen as diffable data. Sculpts come later as GLBs: AI 3D-gen options → Tim picks → frozen, which fits own-show's "randomness at design time". The E9 `style.yaml` residual is closed by design. |
  | Scene-contract seam | One scene language. `toon.scene` validates against a **`SceneCatalog` protocol**: names plus **per-engine capability tables** (verbs, beat fields, prop kinds, show kinds, `layer`, fx). An optional **`engine:`** key (default `toon2d`). A field the chosen engine doesn't render fails at load, naming the engine. An **engine-neutral symbolic timeline** is split out of `state_at`. Scene 001 stays byte-identical. | The EM's Sprint 11 REVIEW 2 note. Sprint 11's "means what it renders" is engine-relative: `layer:` and `fx: glow` are 2.5D-only. |
  | Compose integration | Keep the `toon` visual type; `composer/toon.py` dispatches on the scene's `engine`. It keeps the same duration fence, `SceneRenderError`, validator branch, fps guard and cadence. **No engine fallback**: a toy3d failure never quietly renders on 2.5D. | One storyboard contract. No duplicated validator, still-gate or overlay wiring. |
  | Fur and cost hot spots | GuoGuo's shell fur (22 shells per part) is the per-frame and cross-machine-variance hot spot. v0 keeps the tryout's fidelity and records ms per frame. **Fur LOD** by on-screen size comes later: GuoGuo is mostly a small background easter egg. GTAO, MSAA 4× half-float and bloom → a draft profile later (item 7). **$0 per render** (local GPU). The only possible spend is design-time AI 3D-mesh options, Tim-gated. | The diff map concentrates on fur tips. The fur code is in the tryout. |

- **Cross-links (not merged):**
  - **E9:** the shared scene contract (Sprint 11), and 2.5D is the backup engine. E9's held
    items and item 3 are re-homed here.
  - **E2:** the Seedance accent-shot test would now restyle an E11 render; it stays E2.
  - **E4:** the look's `style.yaml` as a Style Manifest element (deferred).
  - **E6:** a bank browser and scene preview (deferred).
  - **E8:**
    - hub-canonical goldens via `tests/golden_policy.py`, gaining a tolerant compare;
    - a `pipeline doctor` toy3d check;
    - item 2's ownership lock decides where a project renders;
    - item 3's draft profile marks draft renders non-publishable.
- **Items:**
  1. **🔵 v0 = Sprint 12 (proposed).** Phase 1: the contract seam, with an EM checkpoint. Phase 2:
     - the bank v0 from the frozen tryout picks (Tim H3, GuoGuo, the lioness, office + hall);
     - the runner;
     - `toon` dispatch;
     - three-layer goldens;
     - parity with the locked clip;
     - the two-machine compose demo.
  2. **⚪ Camera verbs in scene files** (pan, tilt, zoom and orbit with `over`/`ease`). Tim:
     "the camera must turn easily". This extends the contract; the 2.5D engine rejects the verbs
     through its capability table. **First post-v0 candidate.**
  3. **⚪ Bank fill from Tim's picks, driven by EP1's scene breakdown:** more poses, expressions,
     props and sets, including the **laptop ✓/✗ screen states** (re-homed from E9 2c). Options →
     Tim picks → frozen. **Trigger:** Tim's EP1 script.
  4. **⚪ Bank tooling:** model, expression, pose and prop contact sheets for picks (re-homed from
     E9 2d). Probably rides item 3's first sprint.
  5. **⚪ Motion quality:** IK (planted hands, paws on hips), secondary motion (overshoot and
     settle), and hands that clear the big head. Tryout note 2.
  6. **⚪ Sculpted parts through `gltf:`** (hair, apron, hoodie, a non-primitive lioness), from AI
     3D-gen options or Blender if it is installed later; plus lighting polish (light probes, a
     window area light, contact shadows). Tryout notes 3–4.
  7. **⚪ Speed and drafts:**
     - raw `readPixels` instead of PNG + base64;
     - a 960×540 draft with GTAO off, using E8 item 3's non-publishable flag;
     - fur LOD.
  8. **⚪ Explainer graphics in 3D** (map, timeline, arrows between cards; wordless). Re-homed from
     E9 item 3.
  9. **⚪ Contract-level, engine-independent** (re-homed from E9 item 3; applies to both engines):
     - word-level timing, behind the `sentence_starts` seam;
     - host A-roll ↔ toy transitions (compose-side);
     - Shorts/vertical framing, per engine (in 3D it's a camera aspect change);
     - a `stages/direct.py` taxonomy entry, only if EP1's breakdown shows the director should emit
       toon scenes (it would ride E5 part 2's `direct.py`-touching sprint).
- **Non-goal (Tim):** no EP1 scene or story composition until Tim gives the script. That is
  content work (`own-show.md` step 6). The only scene v0 ships is the worked example: the locked
  r7-3d beat.

---

## Sprint backlog (ordered)

One sprint is "next" at a time. Each is a focused, demand-backed, independently shippable
slice. Format below; the engineering-manager refines and re-orders this on each dispatch.

**Sprint format:** Goal · Demand source · Scope IN · Scope OUT (deferred) · Dependencies ·
Unblocks (and what it does NOT) · Acceptance · Cost · Size.

---

### Sprint 1 — Chart Renderer v1 (static, full type set)  `[E1]`  🟢 *shipped 2026-05-21*

- **Goal:** ship the `chart` visual type rendering all five static chart_types
  (`stat_big_number`, `proportion_blocks`, `timeline`, `bar`, `comparison`) as
  styled-editorial graphics, continuous with the project's art direction.
- **Scope decision (Tim, 2026-05-21):** v1 includes the **full type set** — the handoff's
  "build first" three *plus* `bar`/`comparison` — rather than deferring the latter to a v2.
- **Demand source:** `tmp/chart-renderer-handoff.md`; baby-walker stat beats (s10 "~20,650
  ER visits", s12 "74% / 91%", s13 "230,676 children") currently mis-rendered as `slide`.
- **Scope IN:**
  - `src/pipeline/composer/chart.py` — two-pass renderer (Flux draft bg cached by
    `md5(prompt)` + Pillow composite), copying the `rich_slide.py` pattern; all 5
    chart_types; consume `theme.image_style`; wrap with the `book_scene` frame; themed-flat
    fallback on provider failure.
  - Dispatch branch in `composer/base.py` between `slide` and `rich_slide`.
  - Director taxonomy entry + **worked examples with real numbers** in
    `stages/direct.py` (~line 213) so the model learns each data schema by demonstration.
  - `composer/overlay_rules.py` wiring (chart carries its own title text).
  - **Minimal inline validation** (precursor to E5): reject chart scenes missing
    `chart_type`/`data`; reject `stat_big_number` value > 8 chars; reject `bar`/`comparison`
    whose `data` shape doesn't match schema.
  - Golden-PNG tests per chart_type in `tests/unit/test_chart.py` (fixtures under
    `tests/fixtures/chart/golden/`).
- **Scope OUT (deferred):** animated reveal (→ E2) · Style Manifest element registration
  (→ E4; chart consumes `theme` directly for now) + dashboard surface (→ E6) · full
  storyboard validator (→ E5) · "small multiples" grid (chart handoff v2 idea).
- **Dependencies:** none blocking. Parallel `slide` schema-mismatch fix is **landed**
  (b8715c4, on this branch + master); Sprint-0 open item cleared.
- **Unblocks:** baby-walker stat beats render as real charts instead of text slides — a
  **visual-quality** lift. **Does NOT** unblock the 6–8 min runtime (that needs more
  material), nor the merged animated decline-curve (that needs E2 / Sprint 2).
- **Acceptance:** all 5 chart_types render to stable golden PNGs; director selects `chart`
  over `slide` for the baby-walker stat scenes on regen; `pytest` + `ruff` + `mypy` green.
- **Cost:** ~$0.003 per unique background, cached forever; ~$0.015 for the whole
  baby-walker project. Re-renders free.
- **Size:** ~1–1.5 build sessions (full type set; `bar`/`comparison` add layout + tests).

---

### Sprint 2 — Animated chart reveal + the decline-curve  `[E2]`  🟢 *shipped 2026-05-22*
Shipped on `feat/chart-animation-v1`. Plan:
`docs/superpowers/plans/2026-05-21-animated-chart-reveal.md`.

- **Landed:** new `src/pipeline/composer/chart_anim.py` (pure frame generators
  `_animate_line_frame` / `_animate_bar_frame` / `_animate_stat_frame` + easing helpers
  `_progress_linear` / `_progress_ease_out_cubic` + `_count_up_value` parser +
  `render_animated_chart` orchestrator with hold-tail caching). New
  `chart_type: "line"` in `composer/chart.py` (sixth static type + animated variant).
  `animate: {enabled, reveal_duration_sec, easing}` block on the visual. Director
  taxonomy in `stages/direct.py` updated with `line` worked example + ANIMATION
  subsection. Baby-walker s21 wired to the animated decline-curve (1990 → 1999 → 2007
  → 2014, six regulation markers). End-to-end verified by sampling rendered mp4 frames.
- **Tests (`tests/unit/test_chart_anim.py`, 32 tests):** purity contract per variant
  (byte-identical repeat), 9 sampled-frame goldens (3 variants × progress 0.0/0.5/1.0)
  under `tests/fixtures/chart_anim/golden/`, ffmpeg-mock test (run_ffmpeg called once,
  frame count = `duration_sec * FPS`), hold-tail caching test (generator called
  ≤ `reveal_frames` times, not `total_frames`), dispatch test through `render_chart`.
- **Two-axes rule, enforced in code:** `_validate_chart` raises `ValueError` if
  `reveal_duration_sec > duration_sec − HOLD_TAIL_MIN_SEC (= 0.5s)`. Animation cannot
  extend a scene — runtime stays a story-axis concern.
- **Cost:** $0 incremental — animation re-uses the static chart's cached Flux background;
  pure CPU PIL + ffmpeg. Per-project = same $0.015 as Sprint 1.
- **Static `line` golden:** `tests/fixtures/chart/golden/line.png`. The marker-label
  horizontal overlap (Voluntary standard / ASTM F977, 2 years apart on a 32-year span)
  is the named demand for **Sprint 5** (E3 callout overlay primitive v1 / collision-aware
  placement).

### Sprint 3 — Style Manifest Slices 1–2  `[E4]`  🟢 *shipped 2026-05-22*

- **Landed on `feat/style-manifest-v1`.** New `src/pipeline/style/` package:
  `manifest.py` (StyleElement / PerSceneOverride / StyleManifest dataclasses;
  `build_manifest(storyboard_path)` reads theme + per-scene overrides), `log.py`
  (append-only `style_log.json`), `cli.py` (Typer `style_app` with `list` / `add` /
  `remove`). Registered in `cli.py` via `app.add_typer(style_app, name="style")`.
- **Bug fix:** `anchor_image: Path | None = None` removed from
  `composer/image.py:render_generated_image` signature; corresponding read + pass-through
  stripped from `composer/base.py`. The upstream `style_anchor.py` → `compose.py` chain
  that *generates* the PNG is preserved; manifest surfaces it as `active=False` with an
  INACTIVE warning so users see it exists but does nothing (img2img deferred to a later
  E4 sprint).
- **Tests:** `tests/unit/test_style_manifest.py` — 28 tests (data-structure smoke,
  build_manifest branches incl. medium-descriptor warning + word-boundary false-positive
  guard + non-ASCII, log append, CLI list/remove/add, dead-code absence). 1016 unit
  tests pass; ruff + mypy clean on sprint files. Smoke test on baby-walker confirmed.
- **Unblocks:** charts/animation/future overlays register as traceable elements rather
  than silent globals — **foundational for E3 (animated overlays)**.

### Sprint 4 — Storyboard validator: chart branch + `pipeline validate` CLI  `[E5]`  🟢 *shipped 2026-05-22*

- **Landed on master** (commits `9687169` → `c36b4b1`). `composer/chart.py` now exposes
  `validate_chart_visual(visual, scene_id, *, duration_sec)` as a pure, list-returning
  function (extracted from the inline render-time `_validate_chart`). The
  `storyboard_validator.py` `_validate_scene` dispatch gained a `chart` branch
  (`_validate_chart_visual`, lines 206/401) that delegates to it, so chart-schema errors
  block the review gate at storyboard-write time, not only at render time.
- **CLI:** `src/pipeline/cli_validate.py` adds `pipeline validate <project-id>` (registered
  in `cli.py` via `app.add_typer(validate_app, name="validate")`). Prints
  `format_visual_decision_table` and exits 0 clean / 1 load-failure (missing project /
  storyboard / bad usage) / 2 validation-errors. Locale resolution auto-discovers a lone
  `storyboard_<locale>.json`, prefers canonical `storyboard.json`, and requires `--locale`
  when multiple locale files exist. Error output carries `suggested_fix`.
- **Tests:** `tests/director/test_storyboard_validator.py` grew from 9 → 26 tests — chart
  branch (missing/unknown chart_type, missing data, stat value length, bar xy mismatch,
  comparison missing side, line malformed points/markers, animate variant/easing/reveal
  duration) + smoke tests for the previously-untested
  rich_slide/text_card/still_frame/namecard/map branches.
- **Scope OUT (confirmed still deferred):** the compose-side silent-fallback replacement
  for `article_image` was *already* shipped separately (5a33f0a → loud `SceneRenderError`).
  The only remaining silent degradation is `namecard`/`map` → `text_card`
  (`base.py:413-422`), now reclassified as a narrow non-sprint E5 follow-on.
- **Cost:** $0 (pure validation logic; no provider calls).

### Sprint 5 — Callout overlay primitive v1 (chart marker-label placement)  `[E3]`  🟢 *shipped 2026-05-23*
Shipped on `feat/callout-overlay-v1`. Plan:
`docs/superpowers/plans/2026-05-23-callout-overlay-v1.md`.
- **Landed:** `composer/callout.py` — pure `place_callouts` (vertical dodge to the next free
  row, row budget capped by available header space, raises `CalloutPlacementError` on
  exhaustion) + `_draw_placed_callouts` (leader lines on dodged rows) + `render_callouts`
  image wrapper (golden-test surface). Routed through BOTH line paths: static
  `chart._render_line` and animated `chart_anim._animate_line_frame` — the latter is the
  path that actually renders s21, and it carried the *same* 2-row-stagger overlap bug, so
  the proposal's static-only scope was corrected to fix both via one shared primitive (the
  animated wipe was widened to `top + 2` to clear the taller label stack). `callout`
  registered as a `kind="overlay"` aggregate Style Manifest element. Silent `apply_overlay`
  fallback at `compose.py` converted to a loud `SceneRenderError` (reason + suggested_fix,
  feeds the existing refuse-assembly machinery).
- **Tests:** `tests/unit/test_callout.py` (7 geometry + determinism + 4 placement goldens);
  regenerated `chart/golden/line.png` + 3 `chart_anim/golden/line_p{00,05,10}.png`; 2
  manifest tests; 1 compose loud-failure test. 1108 unit tests pass (2 pre-existing
  `test_memory_sync.py` failures unrelated, left per multi-agent hygiene); ruff + mypy clean
  on sprint files. baby-walker s21 verified end-to-end (real markers place collision-free).
- **Two-axes:** visual-quality lift (removes overlap degradation + first reusable E3
  primitive); **zero runtime**; no code-level fence in v1 (no animation yet — that fence
  lands with the E3 v2 animated entrance).

### Sprint 6 — Niche `visual_style` medium-clash refactor (E4 Slice 3)  `[E4]`  🟢 *shipped 2026-05-27 — EM REVIEW PASS*
Shipped on `feat/niche-visual-style-split`. Split the niche template's monolithic
`visual_style` into `medium_hint` / `palette` / `subject_bias` / `universal_rules` so the
assembler applies palette + universal rules to all generated-image prompts, but suppresses
medium and subject hints when the scene prompt already specifies a photo-realistic medium or
strong explicit subject. Backwards-compat `visual_style` composite preserved: per-video
`theme.visual_style` still wins, style-anchor/direct/validator references remain compatible,
and `pipeline style add image_prompt_prefix` still maps to the composite for v1. `skip_niche_style`
remains the explicit hard override.

Tests: `uv run pytest tests/unit/test_niche_templates.py tests/unit/test_image_style.py
tests/unit/test_style_manifest.py -q` (61 passed), `uv run ruff check src/ tests/`, and
`uv run mypy src/`. Extra guard: compose forwards split niche fields into `render_scene`.
Real-scene demo evidence saved at `tmp/niche-visual-style-split/`: the old baby-walker s25
product-shot prompt now assembles without `medium_hint`, retains palette/rules, and sampled
frames show a clean product shot without the previous open-book/sketch contamination.

### Sprint 7 — Render-truth still-gate: TWO-LAYER gate (deterministic + scoped in-session vision)  `[E5]`  🟢 *shipped 2026-05-31 — EM REVIEW PASS (after one REWORK round) on `feat/baby-walker-quality-pass`*
Pixel-grounded pre-render quality gate. **As-built design (Tim-approved descope, 2026-05-30 +
hard machine constraint):** the greenlit four-deterministic-check plan was reduced to a
**two-layer gate**, because (a) a bordered-but-informationally-empty map (the baby-walker
`north_america_blank_map.png`, ~62% dominant color) cannot be caught by any cheap deterministic
metric, so the SEMANTIC defects move to a **scoped in-session model-vision pass** (zero extra
Anthropic billing, the `visual-review` pattern — Tim reversed the blanket "NO model-vision" guard
for THIS use only); and (b) `tesseract` is not installed and there is no passwordless sudo here, so
deterministic OCR (ex-check-3) could not be built/verified, and the novel text-bbox instrumentation
for overflow (ex-check-4) was high-risk/low-verifiability.
- **Layer 1 (deterministic, CLI `pipeline storyboard still-gate <id>`):** `duplicate_frame`
  (phash + colorhash; VERIFIED firing on the real reused baby-walker map) + `blank_substrate`
  (content-INSET dominant-color ≥0.85; catches genuinely-flat/missing-image panels; correctly does
  NOT fire on the bordered map). Renders a still per scene + a labeled contact sheet.
- **Layer 2 (in-session vision pass, documented in `storyboard-review/SKILL.md`):** the agent looks
  at the contact sheet and judges **meaningfulness** (the blank-map case), **wrong-language text**
  (covers ex-check-3), and **clipping/overflow** (covers ex-check-4). Deterministic OCR + bbox are
  **superseded by Layer 2**; variant-at-gen-time (piece C) is **deferred**.
- **REVIEW HISTORY (2026-05-31).** First REVIEW = **REWORK**: the wired gate defaulted to `plain`
  at the Phase-3.5 gate (no `preferred_variant` until post-TTS), burning overlays so the seed
  reused-map defect (s24/s25/s26) rendered as three DISTINCT stills and `duplicate_frame` did NOT
  fire — the gate missed its own churn class at its real invocation point. **Both fixes landed and
  RE-REVIEW = PASS (shipped):** (#1) `resolve_variant` now defaults to **`no_overlay`** (the
  storyboard-critic step-0 posture — judge the bare frame), with a malformed-context guard;
  demonstrated firing `duplicate_frame` on the defect snapshot via the wired path; regression test
  `test_wired_default_variant_catches_dup_on_snapshot` added. (#2) An independent code review ran; its
  Important finding I-1 (render-loop crash before fit-image on a missing asset) + minors were fixed —
  per-scene `try/except` → clean **exit 1** (codes 0 clean / 1 tool-error / 2 findings), temp-dir
  intermediates, per-scene stills persisted to `<proj>/still_gate_scenes/<id>.png` for Layer-2, and
  the SKILL refuses TTS on any non-zero exit. Variant-at-gen-time (piece C) remains the principled
  form of #1 and stays **deferred** on the E5 backlog; the `no_overlay` default is the accepted
  minimal fix. Full verdict + commands run: sprint-log 2026-05-31 (RE-REVIEW PASS).
- **Goal:** add the missing third defense-in-depth tier — a deterministic still-composite
  quality gate that judges the *composited frame* in the delivered overlay variant, BEFORE the
  ~10-min compose, so render-truth defects are caught cheaply at the Phase-3.5 review gate.
- **Demand source:** `docs/handoffs/2026-05-27-baby-walker-render.md` (4 render-truth defects);
  `tmp/baby-walker-visual-review-report.md` (s25 clip, s23 English labels); storyboard-critic
  standards (the no_overlay step-0 + blank-substrate + 3+-reuse lessons — this gate enforces
  them in code instead of relying on a human/LLM remembering them).
- **Scope IN:** (A spine) `src/pipeline/director/still_gate.py` — deterministic still-composite
  path (`render_scene` at minimal duration → extract 1 frame → `composite_scene_frame` book-wrap
  → `apply_overlay` per the variant → `scene_<id>.png`) + labeled contact-sheet assembler (scene
  id · `visual.type` · `visual.path`); pure check registry `(still, scene_meta) → list[Finding]`
  mirroring `validate_chart_visual`. **All four checks:** **(1)** duplicate-frame (perceptual
  hash, Hamming threshold, `imagehash`); **(2)** blank/flat substrate (content-region
  edge-density / dominant-color %, pure PIL); **(3)** wrong-language text (OCR — `tesseract`
  system binary + `pytesseract` dep, **declare-dep + skip-if-absent** per Q4; flag Latin-script
  blocks on a zh-TW target); **(4)** layout overflow/clipping (instrument `text_card`/overlay to
  report the laid-out text bbox — or pixel-detect text extent — and compare against the
  `frame.py` inner-panel inset `inset_x/y/w/h`; fires on the s25 verbatim clip). (C) one
  overlay-variant field at storyboard-generation time + plumbing + the critic reads it —
  **storyboard/Theme field authoritative at gen-time, `context.json` `preferred_variant` syncs
  from it** (single-source-of-truth, Q2). New **`pipeline storyboard still-gate <id>`** CLI (Q3).
  Wire the `storyboard-review` skill to invoke it after JSON-critic PASS. (B) regression fixtures
  for all four checks, seeded from baby-walker's REAL defects via the **defect-state snapshot
  `tmp/storyboard.BEFORE-quality-pass.json`** (code-verified: s24/s25/s26 carry the identical
  `north_america_blank_map.png`): blank map → check 2; 3+-reuse map → check 1; s23 English labels
  → check 3; s25 clip → check 4. (Do NOT demo on the LIVE storyboard — Sprint 6 already rewrote
  s25, so it no longer reproduces the defect.)
- **Scope OUT (deferred):** animated/over-time frame inspection (still-gate is single-frame by
  design — motion is out of scope); a dashboard surface for the contact sheet (→ E6); model-vision
  judgment of the sheet (**explicitly excluded by Tim** — deterministic checks + human glance only);
  director-emitted variant taxonomy beyond the single gen-time field.
- **Dependencies:** none blocking — `render_scene` (`composer/base.py:325`),
  `composite_scene_frame` (`composer/frame.py:17`), `apply_overlay` (`composer/overlay.py:18`),
  and `imagehash` (declared dep) all exist. `validate_chart_visual` is the pure-check precedent.
  Check 3 requires provisioning `tesseract` (+ zh/eng packs) on the build/run machine; check 4
  requires the text-bbox instrumentation (no renderer-reported bbox exists today — `text_card` is
  ffmpeg `drawtext` with fixed `font_size`).
- **Unblocks:** all four baby-walker defect classes the JSON-critic structurally cannot see
  (blank substrate, as-rendered dup, wrong-language labels, clipped verbatim) are caught
  pre-render — directly attacks the "we keep failing to create a quality video" loop. **Does
  NOT** add runtime (inspects frames; adds zero beats). **No model-vision** (Tim's call).
- **Acceptance:** still-composite renderer is **deterministic** (render twice → byte-identical,
  tested before any golden); contact sheet assembles with labels; all four checks are pure +
  list-returning, each with a **firing case AND a true-negative** (esp. check 2's cry-wolf guard:
  a sparse-but-valid `stat_big_number`/photo frame must NOT fire) + an end-to-end clean-pass
  (known-good storyboard → exit 0, zero findings); OCR test asserts the **finding fires** (not a
  byte-exact transcript — tesseract is not byte-stable); **real-scene demo** = run the gate on the
  defect-state snapshot and confirm checks 1–4 each fire on the real defect they target (prove it
  would have caught the churn); variant field is single-source with `context.json`;
  `storyboard-review` skill invokes the gate after JSON PASS; `pytest` + `ruff` + `mypy` green.
- **Cost:** ~$0 incremental — the still-sheet reuses prompt-hash-cached Flux backgrounds (any
  generation is generation you'd pay at compose anyway, pulled earlier; no h264 encode);
  `imagehash` is a declared dep; `tesseract`/`pytesseract` are free local deps; no
  provider/model-vision calls.
- **Size:** ~3 build sessions (spine + 4 pure checks incl. the tesseract provisioning + the
  check-4 bbox instrumentation + variant field/plumbing + skill wiring + fixtures + determinism
  test).

### Sprint 8 — E8 item 1: cross-platform font resolver + Linux-assumption audit  `[E8]`  🔵 *built on `feat/e8-cross-platform-fonts`; hub (A) gate **ADVISE** 2026-09-24 (EM REVIEW) → cleared to merge; stays 🔵 until Tim's Mac (B) evidence + EM follow-up REVIEW*
**Spec (build from this):** `docs/superpowers/specs/2026-09-24-e8-cross-platform-fonts-design.md`.
- **Goal:** make every renderer use one font resolver that fails loudly, so a Mac render draws the same zh-TW glyphs as the hub. Also close the other Linux- and machine-specific assumptions.
- **Axis:** neither. This is portability (E8). It is not a quality gain and not a runtime gain. The HK→TC and JP→TC glyph corrections below count as bug fixes.
- **Grounding findings (2026-09-24):** `rich_slide._TC_INDEX = 4` is actually the **HK** face (TC = 3), so all zh-TW PIL text drew HK glyph forms. The outro's drawtext `fontfile=` on a TTC loads face 0, which is **JP**. fontconfig silently substitutes missing families. `tests/unit/test_memory_sync.py` fails collection even on the hub because it depends on a `~/.claude/bin` import. On the Mac, a missing `~/.claude/bin/gen-image.py` quietly degrades rich_slide backgrounds to flat.
- **Scope IN:** `utils/fonts.py` resolver (name-verified TTC face scan; `PIPELINE_FONT_DIRS` → fc-match → known dirs → `FontResolutionError`; no cross-family substitution). Migrate rich_slide, chart_anim, callout, running_out, compose `_title_font` and the outro to it. Verify the fontconfig family once at compose start. Fix the `output/` literals. Add a minimal `pipeline doctor` (font resolution, ffmpeg capabilities, glyph-distinctness probes, home-dir tools). Add a shared golden-policy helper. Add a static-audit fence test. Make `test_memory_sync` use importorskip. Update `docs/mac-setup.md`.
- **Golden policy (decided):** hub/Linux goldens are canonical. Golden compares are **skipped on darwin** with a counted reason. `UPDATE_GOLDENS` on non-linux is an error. `PIPELINE_GOLDEN_STRICT=1` forces a compare (the Mac runs this once, for information only). Determinism tests run everywhere. Expected hub golden churn: zero (the goldens are Latin-only, and Latin is identical across the HK and TC faces).
- **Scope OUT:** locale → region plumbing (ja/es); making the rich_slide flat-bg fallback loud (E5); item 2 checkout/lock; item 3 encoders.
- **Acceptance:** split. **(A) hub** criteria gate the merge; the EM runs them. **(B) Mac** criteria Tim runs after merge (doctor, suite, render-truth integration, real-scene s11/s31/s24 frames). Item flips 🔵→🟢 only at an EM follow-up review of the (B) evidence.
- **Cost:** $0. **Size:** ~1.5 sessions. **Then:** ~~E8 item 2 → item 3~~ **Sprint 9 (E9 v0)
  first** (re-ordered 2026-09-27, Tim), then E8 item 2 (~2 sessions) → item 3 (~1 session).
- **(B) status (2026-09-27, not yet adjudicated):** Mac evidence was collected 2026-09-25 (hub
  `tmp/e8-fonts/mac/EVIDENCE.md`). B1–B4 pass. **B5 s31 fails:** `text_card` splits on the
  escaped `"\\n"`, so a raw newline reaches drawtext and ffmpeg 8 draws a .notdef box. The EM
  follow-up REVIEW is still pending. The evidence also reports two unfiled bugs affecting both
  machines: `visual-review extract-frames` is unregistered, and burned subtitles lead the
  picture by up to ~18 s. Both are in arsenal-state "Known capability bugs". None of this
  blocks Sprint 9.

### Sprint 9 — E9 v0: toon engine + resource bank + `toon` visual type  `[E9]`  🟢 *shipped, master `2f6fb35` · EM REVIEW 2026-09-28 = REWORK (3 test gaps) → hub-pass re-REVIEW = REWORK (R1 fps judder, R2 one test assertion) → third REVIEW = **PASS***
- **EM REVIEW #3 2026-09-28 (master `2f6fb35`, EM-run on the Mac and the hub): PASS.**
  - **R1, judder: fixed.**
    - Tim picked **A: `fps: 30`, `drawing_fps: 12`** from the 3-way side-by-side of the
      shot-1 push (`tmp/toon-v0/fps/fps_grid.mp4`). The pick is recorded in `style.yaml` and
      spec §2.
    - `COMPOSE_FPS = 30` is wired at the `_concat_scenes` resample.
    - `test_toon_fps_matches_compose_concat` compares the real bank value with the real
      constant. It goes red when either changes alone (EM mutation: bank 24; `COMPOSE_FPS` 25).
    - `tests/integration/toon/test_cadence.py` runs compose's exact filter chain. EM mutation to
      bank 24: red, with 8/45 near-duplicate steps at 1, 6, 11, …, 36 (the every-5th
      signature). At 30: green on both machines.
    - Hub smoke re-run (`compose rescene --scene s2`): `toon_s2.mp4` and `s2_final.mp4` are 30/1
      with 403 frames (13.433 s against 13.44 s of narration; the final runs 17.600 s against
      17.592 s). The fence holds.
    - EM whole-segment measurement: the final's frame steps track the raw clip's (alignment
      corr 0.93). Every step where the raw moves keeps at least 72% of its size in the final
      (median 88%), so no duplicates are introduced. The one flagged step is a slow camera drift
      that is just as small in the raw. Eyeballed frames at t 5.5 and 9.0: the bulb beat and
      the lioness entrance, with zh-TW subtitles kept.
    - `frame(t)` is byte-identical at bank fps 24 and 30 for all six key times, under both full
      and soft boil. So the goldens and parity are untouched, and option A needed no re-mint.
  - **R2: fixed.** The injected `OSError("dlopen failed")` names no library. With the hint
    deleted from `check_toon`, the test goes red (EM mutation); restored, it is green.
  - **Ride-along:** `PROVENANCE.md` corrected. It matches the EM's strict compare: the Mac
    differs from the hub on `s001_01.50` only, by 1 pixel and 1 colour level.
  - **Gates (EM-run):**
    - Hub full suite 1380 passed / 22 skipped / 0 failed.
    - The first hub run had one failure: `tests/integration/test_trust_gate_round_trip.py`. It
      is a pre-existing dashboard thread/sleep race that doesn't touch this diff: it failed 1 of
      9 isolated hub runs and passed 10 of 10 on the Mac.
    - Mac 1343 passed / 59 skipped / 0 failed.
    - Toon `--integration`: hub 172 passed / 0 skipped (parity and cadence ran); Mac 168 passed
      / 4 skipped (goldens, darwin).
    - Hub goldens 4/4, with `UPDATE_GOLDENS` unset and no fixture churn.
    - ruff clean and mypy clean (159 files) on both machines. Doctor 17/17 on both (cairo
      1.18.0 on the hub, 1.18.4 on the Mac).
  - **Parity record corrected:** the true worst is **0.058** (12.2 s; 4.7 s is 0.004), against
    a 0.5 limit. It has been that value since `c29fc52`, as the test comment says. The first
    REVIEW's "0.0435" was an EM mis-record, not drift.
  - **Code review:** a separate reviewer covered `12b83d9..2f6fb35` (attested by the build
    session): 0 Critical, 0 Important. Its one minor point is carried as a follow-on below.
  - **Follow-ons (not gating):**
    - (a) Spec §4/§5 "on twos" wording (E9 item 2g).
    - (b) Compose frame-rate single source (Later backlog).
    - (c) The trust-gate flake (arsenal-state, "Known capability bugs").
- **EM RE-REVIEW 2026-09-28 (hub pass, master `af00aa9`): REWORK, narrow.**
  - **The first REWORK is closed:**
    - Draw-order tests `tests/unit/toon/test_order.py`. The EM disabled each rule in a scratch
      copy (arm tuck, desk mid-layer sandwich, `layer: low` override); each turned its test red.
    - The model-sheet golden is minted and compared.
    - The doctor FAIL-path test exists and pins `ok=False` (but see R2).
  - **EM-run, hub:**
    - Goldens 4/4 compared with `UPDATE_GOLDENS` unset. libcairo 1.18.0 is recorded in
      `PROVENANCE.md`, and the EM eyeballed all four.
    - Full suite 1379 passed / 21 skipped / 0 failed.
    - Toon `--integration` plus the composer and doctor tests: 170 passed, parity included.
    - ruff clean; mypy clean (159 files); `pipeline doctor` 17/17.
  - **EM-run, Mac:**
    - Suite 1342 passed / 58 skipped.
    - Toon `--integration`: 166 passed / 4 skipped (goldens, darwin).
    - ruff and mypy clean; doctor 17/17.
  - **Compose smoke** (hub project `9920260928`):
    - `pipeline validate` exit 0.
    - The toon `s2_final` lasts 13.440 s, exactly the narration, so the two-axes fence holds.
      The final runs 17.621 s against 17.592 s of narration; the difference is 30 fps frame
      padding.
    - zh-TW subtitles are kept over the toon, and there is no black segment.
  - **Must fix before PASS:**
    1. **R1: 24→30 fps judder.** The smoke row names this criterion, and it fails. The EM
       measured the whole toon segment of the hub final: the raw 24 fps render is clean, and the
       30 fps final repeats every 5th frame, so camera moves freeze 6×/s. Fix: render toon at
       the concat rate, 30 fps with the camera on ones. The drawing rate is **Tim's pick**, from
       a 2-up of the shot-1 camera push:
       - **A (EM lean): `fps: 30`, `drawing_fps: 12`.** Keeps the drawing and boil rate Tim
         approved; holds alternate 3/2 frames. `frame(t)` doesn't read `fps`, so the goldens and
         parity stay valid unchanged.
       - **B (builder's lean): `fps: 30`, `drawing_fps: 15`.** Even twos, but drawings and boil
         run 25% faster than the look Tim approved and tuned. Re-mint the goldens on the hub and
         pin parity to 12.
       - Not taken: moving the pipeline off 30 fps, which touches every visual type.

       **Acceptance:**
       - a default-suite test that fails if the toon clip rate and the compose concat rate
         disagree;
       - an `--integration` cadence test: a shot-1 push through the concat's `fps=30`
         normalisation shows no repeated camera step, and the test is red on today's 24 fps;
       - the hub smoke re-run, with the every-5th repeat gone;
       - Tim's pick recorded;
       - goldens re-minted if B;
       - spec §4/§6 updated;
       - a separate code review of the fix.
    2. **R2: pin the doctor install hint.** The test asserts `"libcairo" in detail`, but the
       injected exception text already contains `libcairo`. With the hint deleted from
       `check_toon`, the test still passes (EM mutation run). Inject a message without the hint
       text and assert `brew install cairo` and `libcairo2`.
  - **Ride-along (not gating):** `PROVENANCE.md` says the Mac renders the goldens
    byte-identically. Under the EM's strict compare, s001@1.5 differs by 1 px / 1 LSB (cairo
    1.18.4 vs 1.18.0), and the other three are identical. Correct the sentence.
  - **Tim acked both v0 deferrals (2026-09-28):** pose/prop contact sheets → E9 item 2d; the
    scene-file name in `SceneError` → E9 item 2b.
  - **Path to PASS:** land R1 and R2, then an EM re-REVIEW runs the two new tests, the hub smoke
    cadence and, if B, the golden compare.
- **EM REVIEW 2026-09-28: REWORK.**
  - **What holds:**
    - Scene 001 on the engine matches the approved tryout. The worst key-frame mean diff is
      0.04 against a 0.5 limit, and four of six frames are identical.
    - Tim confirmed the look. His one caveat, the constant trembling, became the boil modes,
      with soft as the default by his pick.
    - The two-axes fence is in code: clip frames = narration × fps.
    - Every toon failure is a `SceneRenderError`, and compose no longer caches a black stand-in
      after one.
    - A separate code review happened: per-task reviews, then a final Opus review whose 9
      Important findings were fixed.
    - Suite 1337 passed / 57 skipped; toon `--integration` 135 passed / 3 skipped (goldens,
      darwin); ruff clean; mypy clean (159 files); Mac `pipeline doctor` 17/17.
  - **Must fix before merge (all small):**
    1. **Draw-order unit tests** (spec §8; the draw order is spec §9's top risk). Cover the
       arm-tuck rule, the desk in front of or behind the character, and the per-shot
       `layer: low` override. Each test must fail when its rule is disabled. Today only the
       `--integration` parity test covers them, and it needs a gitignored tryout file.
    2. **A `check_toon` FAIL-path test.** When cairo won't load, the check returns `ok=False`
       with the macOS and hub install hints. The EM verified this by hand, but the contract
       needs a test.
    3. **A model-sheet case in `tests/unit/toon/test_goldens.py`** (spec §8), so the hub pass
       mints it together with the scene-001 frames.
  - **Merge:** cleared to merge to master locally once items 1–3 are committed and
    `uv run pytest -q`, ruff and mypy are clean. The merge needs no EM dispatch; the EM re-runs
    items 1–3 at the hub pass.
  - **Hub pass** (needs Tim's OK to push), then an EM re-REVIEW for PASS:
    - Mint the goldens with `UPDATE_GOLDENS=1` on the hub only. Eyeball each one, and record
      the hub cairo version next to the fixtures.
    - The EM re-runs the golden compare, the full suite, toon `--integration` (including
      parity) and `pipeline doctor` → `tmp/toon-v0/hub/doctor.txt`.
    - Run the Task 10 Step 6 compose smoke: a `clip` plus scene 001. Check that subtitles are
      present, the toon segment lasts as long as the narration, and the 24↔30 fps join doesn't
      judder.
  - **Deviations accepted:**
    - Laptop and mug are office-set elements, not bank props.
    - The phone is deferred, because no picked scene uses it.
    - `glum` and `stand_sink_idle` join the bank with scene-001 provenance.
    - The compose smoke is manual evidence rather than a `test_toon_compose_smoke.py`.
    - Spec §4's table should be amended to match.
  - **Descopes that need Tim's ack** (moved to E9 item 2): pose and prop contact sheets
    (spec §4), and the scene-file name in `SceneError` (spec §5).
**Spec (build from this):** `docs/superpowers/specs/2026-09-27-toon-bank-v0-design.md`. This
block is the sprint shape. The spec is the design and is not restated here.
- **Goal:** promote the r4 tryout rig into a tested `src/toon` package and a bank of Tim's
  picks, so that a wordless scene file renders deterministically as an ordinary pipeline
  `toon` scene.
- **Axis:** production quality (visual). **Zero runtime**; the fence is duration = narration
  (E9 above, spec §5).
- **Demand:** own-show order of work, steps 2 and 3. Scene library 001 is the acceptance bar.
- **Scope IN, in spec §9 delivery order.** Use one worktree, with one small commit per unit:
  1. **Engine port + tests** (`src/toon/engine/`): pen (line A, ghost pen), camera and
     projection, rig + IK, sphere-projected head/face/hair, 2.5D draw order with a small rule
     set plus an explicit per-shot layer override, paper composite. The rig's global
     `FACE/HAIR/BODY/HIP` become per-character arguments.
  2. **Bank loader + v0 YAML** (`src/toon/bank.py`, `assets/toon/bank/**`): only the items the
     spec §4 table lists, each with `picked:` provenance. `src/toon/kit/` holds the drawing
     kinds (props, graphics, icon registry, sets).
  3. **Scene model + validation** (`src/toon/scene.py`, Pydantic): every name resolves (errors
     report file and path), the wordless rule (no free-text fields, unknown fields rejected),
     beats stay inside their shot, `at: {sentence: n}` anchors resolve, and the duration
     hold/cut rule applies.
  4. **Renderer** (`src/toon/render.py`): pure `frame(scene, bank, t) → RGBA` with boil seeds
     taken from item keys and `floor(t·12)` (never global random state); `render_clip` renders
     in parallel workers, streams to ffmpeg (libx264, yuv420p, 1920×1080, 24 fps), and caches
     by a hash of the scene file, the bank files it uses, and the engine version. 16:9 only.
  5. **Scene 001 + acceptance** (`assets/toon/scenes/001-lioness-dishes.yaml`). **Checkpoint:**
     Tim looks at the scene-001 side-by-side before step 6, so the pipeline adapter isn't
     built on an engine that misses his bar.
  6. **Pipeline adapter:**
     - `composer/toon.py:render_toon_scene`, with `"toon"` added to `VISUAL_TYPES` and a
       `render_scene` branch. It accepts a `scene:` reference or inline `shots`, and on any
       load or render failure it raises `SceneRenderError` with a `suggested_fix` (no
       `text_card` fallback).
     - A `toon` branch in `storyboard_validator.py` that runs the scene loader's validation,
       so bad names fail at the review gate.
  7. **CLI + doctor:** `pipeline toon validate|render|sheet` (`src/toon/cli.py`, registered on
     the pipeline CLI; `sheet` renders the bank review sheets) and a toon check in
     `pipeline doctor` (cairo loads, a one-frame smoke render works).

  **Plumbing (don't miss):**
  - `cairocffi` goes into `[project] dependencies`.
  - `src/toon` goes into `[tool.hatch.build.targets.wheel] packages`. Today that list is only
    `["src/pipeline"]`, so `import toon` would fail from an installed build.
  - macOS loader shim pointing cairocffi at `/opt/homebrew/lib`.
- **Scope OUT (deferred):**
  - **EP1 scenes or story** (waits for Tim's outline; content work, `own-show.md` step 6).
  - Any bank item Tim hasn't picked (the campfire stays a library idea).
  - Word-level sync (→ E9 after v0).
  - Remotion.
  - AI video / Seedance (→ E2 AI image-to-video; `own-show.md` step 3).
  - Shorts/vertical; lip-sync.
  - A `direct.py` taxonomy entry (→ E9 after v0).
  - Style Manifest element (→ E4); dashboard surface (→ E6).
- **New-visual-type anatomy (standards), mapped:**
  1. Dispatch: in scope.
  2. Director taxonomy + worked example: **deferred, named** (own-show scenes are authored
     with Tim, not generated by the director).
  3. Validation: validator branch.
  4. Goldens: hub-only.
  5. `overlay_rules`: toon draws no text, so it stays **out** of `_TEXT_VISUALS` and the
     narration subtitle is kept. Locked by a test.
  6. Real-scene demo: scene 001 confirmed by Tim, plus the clip + toon compose smoke.
  7. Style Manifest / dashboard: deferred, named.
  8. Locale: wordless, enforced in code.
- **Dependencies:** none blocking.
  - E8 item 1 infrastructure (`tests/golden_policy.py`, `pipeline doctor`) is merged on master.
  - The cairo runtime is on both machines (hub `libcairo.so.2`, Mac Homebrew; checked
    2026-09-27).
  - The tryout sources are on the Mac (`r4/`, `scene_lioness.py`, `animatic_v2_bulb.mp4`).
  - Toon draws no text, so it has no CJK-font exposure, and the open E8 (B) s31 drawtext bug
    doesn't touch it.
  - **Before any hub row: push master.** The spec commits are local to the Mac (ahead of
    origin), and the branch must reach the hub.
  - Don't lean on `visual-review extract-frames` for evidence (it is unregistered; see
    Sprint 8 (B)). Extract key frames with `extract_review_frames` or ffmpeg directly. Spec
    §7's "works unchanged" holds only once that bug is fixed.
- **Unblocks:** Tim's own-show videos can use deterministic, on-model animated scenes as an
  ordinary visual type, and later EP1 scenes are authored from the bank rather than one-off
  code. **Does NOT** add runtime, and does **not** produce any EP1 scene.
- **Acceptance:** the E9 rows in `test-plan.md`. There is a single REVIEW and **every row gates
  PASS**:
  - unit, determinism and CLI rows green on the build machine;
  - hub rows (goldens compared, compose smoke, doctor) green on the hub, re-run by the EM;
  - Mac doctor evidence;
  - **Tim's recorded confirmation that scene 001 still meets his bar**;
  - `uv run pytest` + `uv run ruff check src/ tests/` + `uv run mypy src/` clean;
  - `assets/toon/scenes/` contains only `001-lioness-dishes.yaml` (the non-goal fence);
  - a separate code-correctness review has happened.
- **Cost:** $0. Local cairo and ffmpeg only, no provider calls. Render time is about 20 s per
  13 s scene on the Mac (11 workers) and about 45 s on the hub (4 cores).
- **Size:** ~4 build sessions (engine; bank + scene model; renderer + scene 001; adapter + CLI
  + doctor), plus a short hub pass (mint goldens with `UPDATE_GOLDENS=1` on Linux only, run the
  smoke) and Tim's scene-001 look.
- **Risks (spec §9):**
  - The draw order is heuristic (mitigated by the per-shot layer override).
  - Goldens can drift between cairo versions: they are hub-only, and the hub cairo version
    should be recorded next to the fixtures.
  - The cairocffi loader path on macOS (covered by the doctor check).
  - The spec header still reads "draft for Tim's review". Flip it to approved before the build
    cites it.
- **Then:** Sprint 10 (E5 loud-failure sweep, part 1). Tim greenlit it on 2026-09-29, ahead
  of E8 item 2, as the EM recommended.

### Sprint 10 — E5 loud-failure sweep, part 1: no silent black scenes + one media-path resolver  `[E5]`  🟢 *shipped: EM REVIEW **PASS** 2026-09-29 on `feat/e5-loud-failure-sweep` at `bb16aa0` (27 commits over master `329ff46`); **merged to master `53b1df3`** (pushed; hub synced; 1440 passed / 62 skipped, ruff and mypy clean)*
**Spec (build from this):** `docs/superpowers/specs/2026-09-29-e5-loud-failure-sweep-design.md`.
- **Goal:** a scene that fails to render never reaches a final as black and is never served from
  the scene cache as a black stand-in. Every failure refuses assembly with the step, the reason
  and a `suggested_fix`. `pipeline validate`, compose and the still-gate resolve media paths the
  same way.
- **Demand source:** the Sprint 9 hub smoke (a project-relative clip validated clean, then
  rendered black in an assembled final); the v0 final review (cached black stand-ins); the Sprint 9
  REVIEW 2 intake. **EM probes on master `3693b09` (2026-09-29): four draft tests are red today**
  (generic visual failure, overlay-rule collision, escaped exception, project-relative clip).
- **Axis:** production quality, defect prevention. **Zero runtime:** a failed scene stops
  assembly instead of shipping black at the same length. No new capability.
- **Scope IN:**
  1. One loud scene boundary in `ComposeStage._render_one_scene`: it raises `SceneRenderError`
     and leaves no scene-cache file. It covers the visual, compartment, overlay-rule and
     frame/mux steps and the cache check.
  2. The gather loop writes no black and deletes a failed scene's cache files through one
     shared `scene_final_cache_paths` helper (moved from `cli_compose.py`).
  3. `ComposeStage._black_screen` and `image_sequence._black_clip` are deleted; a failed
     `image_sequence` image raises.
  4. A new `utils/paths.py` resolver (project root → repo root → cwd), used by the validator,
     `clip.py`, `refit.py`, `render_scene`, compose's duplicate guard and the still-gate.
  5. A fence test: no black-fallback helpers; `color=c=black` only in `_silence_gap`; no
     `Path.cwd()` outside the resolver.
- **Scope OUT:** part 2, the silent `text_card` downgrades (E5 🔵); the visual-QC opt-out (Later,
  cross-linked to E10); `style_anchor`'s advisory default (the E10 spec keeps it); a validator-side overlay-collision check (⚪); atomic
  scene-cache writes (⚪); the `transitions` resolver and `_REPO_ROOT` duplicates (hygiene);
  `COMPOSE_FPS` single source (⚪).
- **Dependencies:** none blocking. No provider or Claude calls, no goldens, no hub step. The
  exhausted API credit doesn't block it.
- **Unblocks:** a final can't carry a silent black scene; a storyboard that validates clean
  renders the paths it validated; the first finals produced after E10 are protected. **Does NOT**
  add runtime or a capability, and leaves the text_card downgrades to part 2.
- **Acceptance (spec §9):**
  - red-first tests T1–T11: a test-only commit, then the fix; the EM mutation-checks them at
    REVIEW;
  - full suite, ruff and mypy clean;
  - a live fault-injection smoke on the Mac in a scratch `PIPELINE_OUTPUT_DIR` (assembles →
    corrupt clip refuses → re-run refuses again → restored file assembles → overlay collision
    refuses), evidence in `tmp/e5-sweep/smoke/`;
  - the EM re-runs the hub path audit (no live project changes resolution);
  - a separate code review; no scope creep.
- **Cost:** $0. **Size:** ~1 session (five subagent tasks, spec §11).
- **REVIEW 2026-09-29 (EM, Mac, `bb16aa0`) = PASS; merge cleared.** Every acceptance
  criterion (A1–A7) was run by the EM:
  - **A1 red first:** the ledger has observed red, a red SHA and a fix SHA for 29 rows (T1–T11,
    C1–C2, RF1–RF11).
    - The red commits touch only tests and the plan. The fix commits touch no tests, except
      `357fd3a` (the pinned fix text).
    - Re-run at the red commits: `a7a113b` gave 9 failed (T1–T6, RF1–RF3); `045c5d6` and
      `54b3f69` were red.
    - **18 of 18 mutations went red** in a `git archive` scratch copy. The spec's two:
      re-adding the black fallback turned T1, T2, T4, T6 and both T11 fences red; restoring the
      cwd resolver turned T8, T9 and T11a red. Plus 16 more (the 16 are listed in the sprint log).
  - **A2:** branch suite 1378 passed / 59 skipped, exit 0. The skip count equals the base, so
    there are no new skips. The **merged tree** (post-E10 master `2add7c2` + branch; `git
    merge-tree` clean) gave 1440 / 62. ruff and mypy were clean on both.
  - **A3:** the touched suites gave 157 passed / 8 skipped (environment and golden-policy skips
    only).
  - **A4:** the builder's 5-run smoke ran at `f4f0854`, before the final fix wave, so the EM
    **re-ran it at `bb16aa0`**: 5 of 5 pass. The EM also ran three live checks:
    - RF8: `reburn` refuses on a legacy marker;
    - RF6: the marker is dropped on cache hit, the scene re-renders, and the final assembles;
    - RF7: a truncated `no_overlay` cache file refuses as `cached scene`, and the next run
      re-renders.

    Evidence: `tmp/e5-sweep/smoke/em-review-bb16aa0/`.
  - **A5 hub audit** (read-only): 18 storyboards in 12 projects, with 42 `article_image.path`,
    22 `refit_path` and 6 `clip.path` fields. **0 disagreements** for any path that resolves to a
    file. The 3 `TBD/` placeholders differ only in the path the error names.
  - **A6:** a separate code review happened. It covered per-task reviews (Opus on Task 3), an
    Opus whole-branch review ("Ready to merge"), a fix wave for RF7–RF11 and a scoped re-review.
  - **A7:** the diff stays inside §6 IN. The `namecard`/`map`/`generated_image` fallbacks and
    `_silence_gap` are untouched.

  Two notes on the evidence:
  - The smoke's `PIPELINE_CLAUDE_BIN` "tripwire" was vacuous, because that variable is E10's and
    this branch never reads it. The no-Claude guarantee held by construction instead: there is no
    source video, so `_assess_source` never runs.
  - The fix report's claim that RF2 covers a mux interrupted mid-write is wrong for signals.
    RF7's read-side probe covers that case (part 1b).
- **Hub finding (content/ops, not a build gap):** project `1776850327_B` holds legacy black
  stand-ins for s5, s12, s21, s23 and s28. All five are `clip` scenes that use the primary source
  video. **Its on-disk `final_zh-TW.mp4` (2026-04-23) has 5 black runs of 10–16 s each (~61 s
  total), and the project carries a `youtube_video_id`.**
  - The source video is **missing** on the hub, so `rescene` will now refuse loudly
    (`clip source not found`) instead of rebuilding.
  - Rebuilding needs the source re-acquired or those five scenes re-authored: a content
    decision for Tim.
  - Also check whether the published cut carries the black.
- **Then:** the E10 🟢 follow-up is done (PASS on `53b1df3`). Next comes the capability slot:
  **E5 part 1b, atomic scene-cache writes**, a small hardening slice
  recommended at the head of the queue. **Superseded 2026-10-13:** Tim greenlit Sprint 11
  (E9 item 2) for the slot, and E5 part 1b follows it. Then E8 item 2 (checkout/checkin + hub lock), then E8
  item 3 (draft encoder profile). The E8 item 1 (B) follow-up REVIEW (the s31 tofu) is still
  pending.

### Sprint 11 — E9 item 2: finishing own-show step 3 (scene contract: loud failures, splitter, source names, sentence-anchored shots)  `[E9]`  🟢 *greenlit by Tim 2026-10-13; built on `feat/e9-sprint11`; EM REVIEW 1 at `2feed6e` = REWORK (narrow, R1–R4) → follow-up REVIEW at `d1c346c` = **PASS**; **merged to master `55670c9`** and pushed (`a2eb6cc`)*

**EM follow-up REVIEW (2026-10-13, `d1c346c`) = PASS.** R1–R4 are closed, and every claim was
re-run by the EM.
- **R1:** a fresh reviewer read `d1d4ca2..2feed6e` and found 0 Critical, 2 Important (I1 es-419
  splitter, I2 retake window) and 9 Minor (M3–M11). All 11 were fixed red first. Spec §11.6
  records the rulings.
  - The two judgement calls are accepted. I2 stays a load error, which is the loud-failure
    posture, and the message now names the anchor and the window. M8 follows Tim's 。」 rule.
  - The raw review text isn't archived. The plan's R1 ledger is the record.
- **R2/R3/M18:** the mutations that survived REVIEW 1 now go red: M13 compose `storyboard_file`
  → `None`; M17b tolerance 3.0, plus 0.7 and 0.3; M18 drift log removed.
- **R4 → S11-17:** a negative `over` fails on every verb (the EM probed camera too). `over: 0`
  on a show gives k = 1.0 at its start. A `blink` with `over: 0` fails. Scene 001 uses none of
  these.
- **Gates (EM-run).**
  - Mac at `d1c346c`: 1506 passed / 62 skipped. ruff is clean, and mypy is clean on 161 files.
  - Red first: the 9 new red commits touch tests plus the plan only, and all re-run red at their
    own SHA.
  - Mutations: 25 of 25 go red (R2/R3/R4/M18 and every R1 fix).
  - Scene 001 is byte-identical to master `a2e9b55`: 41 of 41 frames at 960×540.
- **Hub.** The builder said it wasn't needed, but `timeline.py` changed after the REVIEW 1 hub
  pass (the show `over` semantics), so the EM re-ran it. An isolated clone at the exact HEAD
  gives `--integration` toon 205 passed / 0 skipped. Goldens are 4/4 with `UPDATE_GOLDENS`
  unset, parity is `[0, 0, 0.004, 0, 0, 0.058]`, and there is no fixture churn.
- **S11-16 demo:** not re-run. The resolved cut starts for N3 at 12.456 s and 14.928 s are
  identical at `2feed6e` and HEAD, and compose is unchanged, so the hub demo from REVIEW 1
  stands.
- **Two-axes claim held.** No new silent fallback.

**EM REVIEW 1 (2026-10-13) = REWORK, narrow.** The build is sound, but the acceptance list
includes "a separate code review has happened", and it hasn't. Three small pins or gaps came out
of the EM's mutation run and probes.
- **What the EM ran itself:**
  - Mac at `2feed6e`: the full suite gives 1483 passed / 62 skipped. ruff is clean, and mypy is
    clean on 161 files. The S11 tests give 50 passed.
  - All 9 red commits contain only tests plus the plan ledger, and each one's tests fail when
    re-run at that commit (13/2, 3, 2, 12/7, 2, 2, 1, 2, 1, matching the ledger).
  - Scene 001 renders byte-identically to master `a2e9b55`: 12 of 12 frames at 960×540.
  - Hub, in an isolated bundle clone at `/tmp/em-s11-review/repo`: `--integration` toon gives
    185 passed / 0 skipped. Goldens are 4/4 with `UPDATE_GOLDENS` unset. Cadence passes. Parity
    measures `[0, 0, 0.004, 0, 0, 0.058]`, worst 0.058. There is no fixture churn.
  - The S11-16 demo was re-run on the hub and reproduces exactly. Take A is 12.456 s, cuts at
    frames 104, 236 and 296; take B is 14.928 s, cuts at 125, 282 and 342. Every cut is measured
    on its expected frame, and the clip frame counts equal the narration (374 and 448).
  - Contact sheet eyeballed: each cut reads as the shot change.
  - The non-goal fence holds: `assets/` and `tests/fixtures/` are unchanged, and the scenes
    directory holds only 001.
- **Mutations:** 25 in a `git archive` scratch copy; **22 went red**. The fences held:
  - the `BEAT_FIELDS` table, the timeline dropping `bob`, and a new unlisted `Beat` field;
  - `PROP_KINDS` sync and the plate flags;
  - the visible-key check, the second hide, and the card id;
  - all three splitter rules;
  - source naming, `plus:`, the order check and shot-relative beat anchors;
  - the CLI flag hint and the workers' bank.

  Three survived:
  - **M13:** compose dropping `storyboard_file=ctx.storyboard_path`;
  - **M17b:** a drift tolerance of 3.0 instead of 0.5;
  - **M18:** the `toon.scene.drift` log removed.
- **Rulings §11.6, all accepted.** Each closes a silently ignored field or follows Tim's quote
  rule:
  - `ease` without `over`;
  - a second `hide`;
  - `none:` beside `layers:`;
  - the "I" exclusion;
  - ASCII and CJK closers;
  - `drift_warnings` kept separate;
  - order checked after resolution.

  Ruling 7 is in the plan but missing from spec §11.6; add it.
- **Changed tests, accepted.**
  - The two validator tests expect 2 warnings: 001 at 8.0 s against 13.0 s authored really
    does drift.
  - The six fakes gained the kwarg because compose now passes it. None of them asserts its
    value, which is how M13 survives.
- **S11-11:** the false first draft was replaced before the red commit. The committed red is
  real (re-run red at `b23352d`; M20 is red).
- **Two-axes claim held.** The clip is exactly the narration in both takes. Anchors move cuts
  inside it, and nothing stretches.
- **Must change before merge, then a short follow-up REVIEW:**
  - **R1:** a separate code review of `d1d4ca2..HEAD`, by a fresh reviewer, not the builder.
    Fix its Critical and Important findings, red first where they change behaviour.
  - **R2 (S11-8):** pin compose's wiring. A compose test asserts that `render_scene` receives
    `storyboard_file == ctx.storyboard_path`, or that a bad inline toon scene's
    `SceneRenderError` names the storyboard file through `ComposeStage`. M13 must go red.
  - **R3 (S11-14):** pin the upper side of the 0.5 s tolerance. Add a case just over it (for
    example est 13.6 → warns). M17b must go red.
  - **R4 (new row S11-17, the sprint's own goal):** two cases still load silently.
    - `over: 0` on a `show` loads and renders a 0.25 s pop: EM probe, k = 0.2 at +50 ms.
    - A negative `over` (for example `door ... over: -1`) loads and acts as instant.

    Reject both, or honour `over: 0` on a show as an instant pop. The builder decides and
    records it as a ruling. Red first. Scene 001 uses neither.
  - **Docs:** add ruling 7 to spec §11.6. Spec §11.2 e says the workers' bank is the one
    "hashed into the cache key", but `cache_key` hashes the bank *files* (see Later). Reword it.
- **Accepted as is:**
  - The S11-16 takes are macOS `say` (Meijia, default rate and `-r 95`) through the prerecorded
    path, because edge-tts is down. That is a real pipeline path with two lengths, which is what
    the row asks for.
  - s2_final comes out about 5 frames short. The cause is compose and MP3 padding, not toon, and
    it is pre-existing. Filed in Later.
- **Recommended, not gating:** a caplog pin for `toon.scene.drift` (M18).

**Then:** R1–R4 passed the follow-up REVIEW, so Sprint 11 is 🟢 and merged (`55670c9`).
- ~~**Next:** the 3D toy engine INTAKE~~. **Done 2026-10-13: new epic E11, with Sprint 12
  proposed.** The queue is now Sprint 12 → E5 part 1b → E8 item 2 (see Sprint 12).
- ~~edge-tts is down on both machines, so TTS would jump the queue~~. An off-roadmap fix merged at
  `ce9e4b8` (see Later 🔴); the jump is suspended unless a port run still fails.
**Spec (build from this):** `docs/superpowers/specs/2026-09-27-toon-bank-v0-design.md` §11 (the
addendum). This block is the sprint shape.
- **Greenlight:** Tim, 2026-10-13: "for step three, could you complete?" Own-show step 3 is
  "scene scripts reference bank elements by name and render consistently by construction".
- **Goal:** a scene file either means exactly what it renders or fails at load, naming its file.
  Its shot cuts follow the narration when the narration's length changes.
- **Demand source:** `docs/own-show.md` step 3; the E9 item 2 residuals parked by the v0 final
  review (2026-09-28); the two v0 deferrals Tim acked. **EM probes on master `a2e9b55`
  (2026-10-13), all wrong today:**
  - `ease` on a `show`, `over` on a `hide` and `flicker` on a `plate` all load silently;
  - a second `x_card: bulb` silently replaces the first;
  - 「我走了。」然後離開。 splits into a fragment that starts with 」, and "The U.S. economy grew."
    becomes 3 sentences;
  - `SceneError` never names the file;
  - `shots[i].at` can't take a sentence anchor.
- **Axis:** production quality (visual) via defect prevention. **Zero runtime:** the duration =
  narration fence is untouched. Sentence anchors move cuts *inside* the narration and never
  lengthen a scene.
- **Scope IN** (spec §11.1–§11.2). One worktree; red-first commits, then the fix commits:
  1. **2a, no silently ignored field:**
     - `Beat.over`/`ease` become optional;
     - one per-verb table of the fields the timeline reads;
     - prop-kind beat flags;
     - hair keys beside `layers:` rejected.
  2. **2b correctness:**
     - optional card `id:` and visible-key collision errors;
     - the splitter: closing quotes attach to the left, abbreviations;
     - `SceneError(problems, source)` through `read_scene`, `load_scene`, the validator and the
       composer.
  3. **2d:** `pipeline toon validate --narration --duration`, printing the sentence table and
     the resolved shot starts.
  4. **2e:** the `PROP_KINDS` sync test; the camera check uses `is not None`; workers get the
     caller's `Bank`.
  5. **2f:** `Shot.at` takes `{sentence: n, plus: s}`. Shot anchors resolve first, an
     out-of-order result fails loudly, and a drift warning fires for seconds-timed shots.
- **Scope OUT / held:**
  - **Held until Tim's style pick** (spec §11.4): 2c laptop ✓/✗ screens, the 2b `style.yaml`
    `line`/`palette` wiring, and the 2d pose and prop contact sheets. They become the first
    slice of the restyle sprint.
  - **Word-level timing** stays E9 item 3. Sentence anchors fix the defect, and the
    `sentence_starts` seam is where it plugs in later.
  - A uniform stretch of seconds-timed shots is rejected: it would silently re-time authored
    comic timing.
  - EP1 scenes or story (the non-goal stands; `own-show.md` step 6).
  - New bank items; a `direct.py` taxonomy entry; Style Manifest / dashboard surfaces.
- **Dependencies:** none blocking. Master has the v0 engine, and the cairo runtime is on both
  machines. The demo rebuilds a throwaway smoke project from the Sprint 9 recipe
  (`tmp/toon-v0/compose-smoke/REPORT.md`), because `9920260928` is gone from the hub. **Push
  master before any hub row.**
- **Unblocks:** authoring the first EP1 scene file against a contract that can't silently drop a
  field. Re-recording narration (TTS draft → Tim's voice) moves the cuts with it instead of
  stranding them. **Does NOT** add runtime, give a new look, add bank items or compose any EP1
  scene.
- **Acceptance:** test-plan rows **S11-1…S11-16** (E9 section), all gating at a single REVIEW:
  - red first, with the EM mutation-checking the fences;
  - **scene 001 byte-identical**: hub goldens 4/4 with no churn, parity ≤ 0.058;
  - the non-goal fence holds;
  - the hub real-scene demo: two narration takes, cuts on their resolved starts;
  - `uv run pytest -q`, `ruff check src/ tests/` and `mypy src/` clean;
  - a separate code review has happened.
- **Cost:** $0. Local cairo and ffmpeg; the demo's second take is free edge-tts.
- **Size:** ~1.5 sessions, plus a short hub pass (goldens compare, parity, demo).
- **Needs Tim before the build starts:** see the sprint-log entry for 2026-10-13. Briefly:
  confirm the held set; accept sentence anchors in place of word-level timing; the zh-TW quote
  convention (default: a terminator inside 「」 still breaks; the closer stays with its sentence).
- **Then:** ~~E5 part 1b (atomic scene-cache writes, with the dark-retry cache key), then E8
  item 2. The held E9 items return as the restyle sprint once Tim picks a style.~~ Superseded at
  the E11 INTAKE (2026-10-13). Sprint 12 comes first, and the held items are re-homed (E9, "Style
  LOCKED").

### Sprint 12 — E11 v0: the locked 3D toy look as a pipeline visual (contract seam + engine + bank v0 + goldens)  `[E11]`  🔵 *proposed by the EM 2026-10-13 (Tim asked for the plan: "yes, do both"); **not greenlit**; not built*

**Spec (build from this):** `docs/superpowers/specs/2026-10-13-toy3d-engine-v0-design.md`. This
block is the sprint shape. It has two phases and an **EM checkpoint REVIEW after Phase 1**.
- **Goal:** a scene file with `engine: toy3d` renders the locked look deterministically through
  compose on both machines. It uses the same scene contract as the 2.5D engine, and its goldens
  hold on both machines.
- **Demand source:** `docs/own-show.md` step 4b; the style lock (2026-10-13); the EM's Sprint 11
  REVIEW 2 notes (a bank-neutral seam, one scene format); Tim, 2026-10-13: "yes, do both".
- **Axis:** production quality (visual). **Zero runtime:** clip frames = round(narration ×
  `COMPOSE_FPS`), the shared contract's fence (S12-14).
- **Scope IN, Phase 1 (contract seam; red first; 2.5D byte-identical):**
  1. `load_scene` takes a `SceneCatalog` protocol, and the 2.5D `Bank` adapts to it. `toon.scene`
     no longer imports `toon.bank` or the 2.5D kit at module level.
  2. Per-engine capability tables: verbs, beat fields, prop kinds, show kinds, place fields and fx.
     A field the chosen engine doesn't render fails at load, naming the engine.
  3. An optional `engine:` scene key (default `toon2d`). An unknown engine fails, listing the
     engines.
  4. `toon.timeline.beats_at`: the engine-neutral symbolic state. The 2.5D `state_at` is rebuilt on
     it, and scene 001 stays byte-identical.
  5. A contract conformance suite: the Sprint 11 malformed-scene cases fail the same way against
     both engines' catalogs.
- **Scope IN, Phase 2 (engine):**
  6. `assets/toy3d/bank/` holds the frozen tryout picks only:
     - Tim (H3);
     - GuoGuo (frozen by Tim at greenlight);
     - the lioness;
     - the office + hall set with its props;
     - camera presets as keyframe paths;
     - look A as `style.yaml`.

     Every item carries `picked:` provenance. `src/toy3d/bank.py` holds the Pydantic models and the
     catalog.
  7. `src/toy3d/web/`:
     - the engine, cast and set modules ported from `scene.js`, parameterised by bank data;
     - vendored three r170;
     - `stage.html` with the seeded RNG;
     - a page API: `init`, `renderState`, `applyState`, `info`.
  8. `src/toy3d/render.py`:
     - Python `playwright` launches the pinned CfT build;
     - the backend allow-list and renderer-string assertion;
     - the blank-frame guard;
     - frames piped into ffmpeg at `COMPOSE_FPS`, with an atomic `.part` → rename;
     - the cache key, which hashes the Bank object.
  9. `composer/toon.py` dispatches on `engine`; the validator branch, `pipeline toon validate|render`
     and a `pipeline doctor` toy3d check.
  10. Goldens in three layers (spec §8), with the tolerant helper in `tests/golden_policy.py`.
  11. The worked scene `assets/toy3d/scenes/001-beat2-break-in.yaml`: the locked r7-3d beat, 8.0 s.
      Parity references are frozen from the r7-3d snapshot at greenlight.
  12. Real-scene demo: a two-scene compose (a `clip` + toy3d, two narration takes) on both machines.
- **Scope OUT (deferred):**
  - camera verbs in scene files (E11 item 2);
  - more bank items, including laptop ✓/✗ (item 3);
  - contact sheets (item 4);
  - IK and secondary motion, and fixing the tryout's weak points (item 5). v0 **reproduces the
    locked clip faithfully, weak points included**;
  - glTF/sculpted parts and lighting polish (item 6);
  - speed, draft and fur LOD (item 7);
  - explainer graphics (item 8);
  - word-level timing, transitions, vertical and `direct.py` (item 9);
  - a `pipeline toon render --engine` cross-check override;
  - the Style Manifest element (E4) and the dashboard surface (E6);
  - EP1 scenes (non-goal).
- **Dependencies:**
  - Sprint 11 merged ✅ (`55670c9`).
  - Frozen picks: Tim H3 ✅, the lioness and the set as in the tryout ✅, **GuoGuo ⏳** (Tim
    freezes him at greenlight; until then E5 part 1b fills the slot).
  - The pinned CfT build is on both machines ✅. The hub GPU path is proven by the EM probe ✅.
  - New dependency: Python `playwright`.
  - **Sync the hub to master** before any hub row. The hub checkout is at `68c14ad`, behind the
    Sprint 11 merge and `ce9e4b8`.
- **Unblocks:** own-show scenes in the locked look through the pipeline (step 4b). Once Tim's
  script names what EP1 needs, it lets bank-fill sprints add picks as data. It **does NOT**:
  - add runtime;
  - compose any EP1 scene;
  - add bank items beyond the frozen tryout picks;
  - give authorable camera moves (item 2);
  - improve on the tryout's motion or sculpting.
- **Acceptance:** test-plan rows **S12-1…S12-21** (E11 section), all gating:
  - Phase 1 rows S12-1…S12-5 at the checkpoint;
  - red first, with the EM mutation-checking the fences;
  - **scene 001 byte-identical** (41 of 41 frames; hub goldens 4/4, no churn; parity ≤ 0.058);
  - goldens on both machines with the calibrated tolerance and the sensitivity set red;
  - parity with the locked clip, and **Tim confirms it still meets his bar**;
  - the two-machine demo;
  - `uv run pytest -q`, `ruff check src/ tests/` and `mypy src/` clean on both machines;
  - a separate code review has happened.
- **Cost:** $0 (local GPU, free dependencies; no API calls). The demo narration uses the
  prerecorded path (`say` takes, as in S11-16) or the TTS fallback.
- **Size:** about 3 sessions plus a hub pass: Phase 1 about 0.75; Phase 2 about 2; goldens,
  calibration and the demo about 0.5. Sprint 9 is the scale reference.
- **Needs Tim before the build:**
  1. Greenlight the scope, including the lioness, so the worked scene *is* the locked clip and
     parity covers all of it. The cheaper option is Tim + GuoGuo + the set only, with parity on
     the lioness-free windows, about 0.3 session less.
  2. Freeze GuoGuo, or say "freeze at the greenlight snapshot".
  3. Accept the Python `playwright` dependency and vendored three.js r170 (~1.5 MB, MIT).
  4. Accept the toy3d golden policy: tolerance, compared on both machines, three layers. This is
     a departure from E8's byte-exact skip-on-Mac policy, for GPU renders only.
- **Then:** E5 part 1b (or before Sprint 12, if the GuoGuo freeze lags), then E8 item 2. E11
  bank-fill sprints go ahead of E8 item 2 once Tim's EP1 script names its needs. E11 item 2
  (camera verbs) is the first post-v0 E11 candidate.

### Later / unscoped backlog
- **🔴 edge-tts returns 403, a production blocker (filed 2026-10-13 at the Sprint 11 REVIEW;
  infra, next to E10).**
  - Every default-voice TTS run fails on both machines: `WSServerHandshakeError: 403` from
    `speech.platform.bing.com`. The EM reproduced it on the Mac.
  - The failure is loud, not silent.
  - The lock pins `edge-tts 7.2.8`, which is already the latest on PyPI (2026-03-22), so there
    is no bump to take. Upstream breakage.
  - Ports can't be produced with the default voice. Own-show is unaffected, because Tim's
    recorded voice uses the prerecorded path, which the S11-16 demo exercised.
  - Options (Tim decides):
    - switch the default TTS to Google Neural2 (free tier, 1M chars a month) through the
      existing provider config;
    - pin an upstream fix when one ships;
    - both.
  - About 0.25 session. It jumps the queue the moment a port video is due.
  - **Update 2026-10-13 (seen at the E11 INTAKE):** master `ce9e4b8` merged a TTS outage fix
    off-roadmap. It moves the edge endpoint and adds retries. It adds a loud Kokoro local fallback
    for zh-TW, with an `audio/tts_fallback.json` marker, and publish preflight refuses fallback
    narration. The commit cites two code reviews. **Not EM-reviewed;** the status stays 🔴 until a
    real port TTS run is seen green. The queue jump is suspended meanwhile. Check also whether it
    touches the ⚪ "prerecorded narration silently falls back to TTS" item below.
- **⚪ Toon cache key hashes the bank files, not the `Bank` the workers draw from (E9 hygiene;
  Sprint 11 follow-up).**
  - Since S11-11, the workers render from the caller's `Bank` object.
  - `cache_key` re-reads `bank_files(bank.root)` from disk when it runs. An edit landing between
    `load_bank()` and `cache_key()` (milliseconds apart) would key old frames under new files.
  - The bank is all YAML and fully modelled, so the fix is to hash `bank.model_dump_json()`.
  - `test_cache_key_changes_when_a_bank_file_changes` must then change a value, not just a
    comment.
  - Since the 2026-10-13 style lock this is backup-engine hygiene. The 3D engine's cache key
    hashes its bank object from the start (E11, Sprint 12 row S12-13).
- **⚪ A timed `move` with `bob` leaves a residual lift (E9 hygiene, backup engine; found by the
  Sprint 11 code review R1 and noted in spec §11.6).**
  - At the end of the move the character sits above its spot. Scene 001's lioness ends 0.025
    above `doorway`.
  - The fix churns the scene 001 goldens, so it was not made in Sprint 11. It goes with any
    later golden regeneration of the backup engine, with Tim eyeballing the change. That would be
    E9 item 4, the dormant backup restyle. Sprint 12 must keep scene 001 byte-identical, so it
    does **not** take this fix.
- **⚪ Prerecorded MP3 padding skews scene timing (E6 compose; own-show relevant; found by the
  S11-16 demo).**
  - The pipeline times a prerecorded take by the transcoded MP3's container duration, which
    includes encoder padding: 12.456 s, where the WAV is 12.393 s.
  - So the toon clip renders 374 frames, and `s2_final`'s video is 369 frames (12.300 s)
    against 12.393 s of audio. Every scene's video ends 1–3 frames before its audio. In the
    two-scene final, the video is 16.000 s and the audio 16.128 s.
  - Sentence anchors scale to the padded length, so the cuts land about 0.5% late (about 50 ms
    at 10 s). That is small next to the character-share approximation.
  - Fix: measure the decoded duration, or the source WAV. Check A/V sync on a long multi-scene
    final before Tim's recorded-voice EP1.
- **E5 loud-failure sweep** → part 1 🟢 shipped (Sprint 10). Part 2 (silent `text_card`
  downgrades) is an E5 🔵 item.
- **Items parked by Sprint 10, placed at its REVIEW (2026-09-29), in priority order:**
  1. **🔵 Atomic scene-cache writes (E5 part 1b), top of the queue.**
     - `_mux` and the other scene-cache writers write in place.
     - After a SIGTERM (a dashboard restart) or Ctrl-C, the next run refuses with
       `cached scene failed`, and the run after that re-renders. That is loud and never black,
       but it wastes a run.
     - Fix: a temp file plus `os.replace`, with a kill-mid-mux test.
     - About 0.25 session.
     - The natural companion is item 2 (both are cache correctness).
  2. **🔵 image_sequence dark-image retry cache key (budget; E6 cache correctness).** Pre-existing.
     - When an image is too dark, `_fetch_image` unlinks it and caches the retry under the
       *light* prompt's hash. Every later run looks up the *original* hash and misses.
     - So a dark-retried image costs 2 provider calls on **every** rerun.
     - It also makes image_sequence's `suggested_fix` ("only image N is regenerated") inexact.
     - Fix: look up the light key too, or store the retry under the original key.
     - **Same function, a silent-off hazard (filed 2026-09-29, E10/Sprint 10 follow-up):**
       - `_is_too_dark` exists twice, at `composer/image_sequence.py:58` and
         `composer/image.py:36`. Both call `Image.getdata()`, which Pillow deprecates; it is
         removed in Pillow 14 (2027-10-15).
       - Both wrap the call in `except Exception: return False`. `pyproject` pins
         `pillow>=12.2.0` with no upper bound, so a lock upgrade to Pillow 14 would **silently
         disable the dark-image check** in both renderers, with nothing logged. Today it is
         only a `DeprecationWarning` in the suite (the new Sprint 10 tests reach it).
       - Fix: one shared helper using `ImageStat.Stat(img).mean[0]`, and narrow the except so
         an API error is loud. Delete the duplicate.
     - Rides with item 1.
  3. **⚪ `compose frame` rebuilds from stale `_visual`/`_overlay` files (E6).** After a refused
     visual step, the previous `{sid}_visual.mp4` stays. `compose frame` re-muxes it into finals,
     which then cache-hit. The result is a *stale* visual, not black. This is an edge case for
     E6's contract-aware invalidation.
  4. **⚪ Failure-message polish (E5).** Rides with E5 part 2.
     - frame/mux reasons quote the full ffmpeg command;
     - `TimeoutExpired` gets no stderr tail;
     - the overlay-rule `suggested_fix` repeats the collision message the reason already
       carries. The spec asked for that, but it is noisy.
- **⚪ Prerecorded narration silently falls back to TTS (E5; own-show relevant, filed
  2026-10-13).** In `stages/tts.py` `_synthesize_pass`, a scene whose `narration_source`
  names a missing recording only logs `tts.prerecorded.missing_file_falling_back_to_default`
  and synthesises TTS instead. Tim's own-show narration is his recorded voice, so a moved
  file would ship a synthetic voice without anyone deciding to. Make it loud: raise with the
  path and a `suggested_fix`, or require an explicit opt-in to fall back. Rides with E5 part 2.
- **Post-compose Haiku visual-QC opt-out** `🔵`, **cross-linked to E10** (same call site). The E10
  spec keeps the QC advisory and moves it to the subscription; the opt-out flag is not in it, so
  this line stays. Found by the Sprint 9 hub smoke, 2026-09-28.
  - `produce` always runs a Claude Haiku visual-QC after compose (`cli.py` ~431) and has no skip
    flag. After E10 it spends subscription quota, not API credit: about 62 s for 27 frames on
    baby-walker (EM, 2026-09-29).
  - When the call fails, it prints only a parenthetical "(visual review skipped: …)" and
    reports "Pipeline complete!".
  - Add an opt-out flag, and make a QC that didn't run say so prominently.
  - Consider the zero-billing in-session pattern that Layer 2 of the still-gate uses.
  - *(The `print_visual_issues_table` TypeError is fixed in E10, `94c24ba`.)*
- **Compose frame-rate single source** `⚪` (hygiene; from the Sprint 9 R1 code review,
  2026-09-28). `COMPOSE_FPS` governs only the concat resample. Fresh renders still hardcode
  30: `composer/clip.py` `-r 30`, `composer/compartment.py` `fps=30`, the compose.py
  silence-gap generator (`_black_screen` is gone, Sprint 10), and the dashboard
  preview transitions. Route them through `COMPOSE_FPS` if the timeline rate ever changes.
  Related limitation, with no demand yet: a 24p or 25p **source clip** gets the same
  nearest-frame duplicates in the 30p timeline that toon had. Motion-heavy source footage would
  stutter; revisit if a real source shows it.
- Animated overlays v2+ (E3): **animated entrance** for the callout primitive + lower-thirds
  + CapCut-style word-by-word subtitles `🔵` — follow-ons to Sprint 5's static v1.
- Dashboard surfaces (E6): Production Contract panel, recompose buttons, Style panel,
  Decision table, transition preview sheets `🔵` — **partly in flight** by another agent
  (`docs/superpowers/plans/2026-05-16-dashboard-timeline-draggable-sections.md` + uncommitted
  job_queue/server edits); do not double-schedule.
- **SFX layer visibility / overlap panel** → **migrated to E7** (Audio arsenal & SFX
  legibility, 2026-05-26). Tim approved the formal audio epic, so this dashboard-surface
  half moved out of the E6 backlog into E7 item 2 alongside its paired asset-registry half.
  See the E7 epic above.
- True stock-quality book-page-turn (E2 remaining) `🔵`. *(Ken Burns on stills shipped with
  the E2 camera-motion path; struck 2026-09-29.)*
- Animated reveal for `proportion_blocks` / `timeline` / `comparison` (E2 remaining) `🔵`
- Stock-footage transition asset path (E6 Phase 5) `🔵`
- `namecard`/`map` silent `text_card` fallback → now **E5 part 2** (see E5).

---

## How this roadmap is maintained

The **engineering-manager** subagent owns this file. On each dispatch (via the
`engineering-manager` skill, which feeds its memory in) it:

1. Reads its memory (`charter`, `standards`, `arsenal-state`, `sprint-log`) + this file +
   the demand sources (`tmp/*-handoff.md`, `docs/future-tasks.md`, producer `acquire`
   demands from know-fountains, Tim's direction).
2. Reconciles status (moves shipped items 🔵→🟢, updates the baseline arsenal), folds in
   new demand as epics/items, and re-orders the backlog by leverage × readiness.
3. Proposes exactly **one** next sprint (the format above), records it in `sprint-log.md`,
   and brings it to Tim. Tim steers; the EM does not start building.

## Relationship to `docs/future-tasks.md`

`future-tasks.md` remains the catch-all idea bin. **Arsenal capabilities are tracked here**,
not there — its "Visual & Rendering" rendering entries (Ken Burns, transition effects,
animated subtitles) are absorbed into E1–E3/E6, and **audio-arsenal items** (the SFX asset
registry / reuse, migrated 2026-05-26) are absorbed into **E7**. Material-acquisition and
non-rendering items (B-roll sourcing, channel-brand templates, SQLite,
discovery/observability) stay in `future-tasks.md`.
