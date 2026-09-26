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

**Last updated:** 2026-09-27 (INTAKE: **new epic E9 — Toon engine & resource bank** [own-show character animation: deterministic 2.5D hand-drawn cairo rig + YAML bank of Tim's picks + wordless scene files + new `toon` visual type]; spec `docs/superpowers/specs/2026-09-27-toon-bank-v0-design.md` Tim-approved 2026-09-27; **v0 = Sprint 9, now the recommended next sprint** (Tim's direction), ahead of E8 item 2; 18 test-plan rows 🔲; non-goal held: no EP1 scene/story composition until Tim gives the outline) · Prior: 2026-09-24 (REVIEW: **Sprint 8 hub (A) gate ADVISE** — all 12 hub rows green [83 unit + 8 render-truth integration + 74 golden, full suite 1224 passed/21 skipped/0 errors, ruff+mypy clean, doctor 16/16, resolver = TC index 3]; merge cleared; E8 item 1 stays 🔵 pending Mac (B)) · Prior: 2026-09-24 (SPRINT: **Sprint 8 = E8 item 1 proposed + Tim-greenlit** — font resolver + Linux-assumption audit; spec `docs/superpowers/specs/2026-09-24-e8-cross-platform-fonts-design.md`; hub/Mac split acceptance; golden policy = hub-canonical, darwin skip; found HK-face `_TC_INDEX` + JP-face outro bugs; E8 item 3 hub encoder corrected to nvenc) · Prior: 2026-09-24 (INTAKE: **new epic E8 — Two-machine workflow & render portability** [Hub Linux box + Workshop M3 Mac]; three items in Tim's order: (1) cross-platform font resolver + Linux-assumption audit [Mac-render blocker; folds `cli_storyboard.py:428` + `output/gallery` path fixes + the silent `load_default()` font fallback], (2) project checkout/checkin + hub ownership lock, (3) draft/preview encode profile [hw encoders, non-publishable flag, bitrate-check aware]. Item 1 recommended as next sprint slot. Iteration-speed axis — neither quality nor runtime.) · Prior: 2026-05-31 (**Sprint 7 SHIPPED 🟢 — EM RE-REVIEW PASS** after one REWORK round — render-truth still-gate, a **two-layer gate** [Tim-approved descope 2026-05-30 + hard constraint: tesseract unprovisioned, no passwordless sudo]: Layer 1 deterministic CLI [`duplicate_frame` phash+colorhash + `blank_substrate` content-INSET; exit 0 clean / 1 tool-error / 2 findings] + Layer 2 scoped in-session vision pass [meaningfulness / wrong-language / clipping] wired into `storyboard-review/SKILL.md`. Deterministic OCR + bbox-overflow SUPERSEDED by Layer 2; variant-at-gen-time [piece C] DEFERRED [principled form of the variant fix]; the blanket "NO model-vision" guard LIFTED for the scoped Layer-2 use only. **REWORK→PASS:** first REVIEW caught the gate defaulting to `plain` [overlays burned] at Phase-3.5, missing the seed reused-map defect; both fixes landed — #1 `resolve_variant` defaults to `no_overlay` [+malformed-context guard], demonstrated firing dup on the defect snapshot via the wired path + regression test; #2 independent code review done, its I-1 render-crash finding fixed [per-scene try/except → exit 1, persisted Layer-2 stills]. EM ran pytest [16 still-gate + 143 regression], ruff, mypy, live I-1 exit-1 check — all clean. Prior 2026-05-30: Sprint 7 GREENLIT; 2026-05-29 still-gate→E5; Sprint 6 REVIEW PASS) · Prior: 2026-05-29 (REVIEW post-hoc: **E7 music/audio-axis** — first E7 sprint, built off-roadmap and merged to master `12bfce3` without a pre-merge gate; EM acceptance verdict **ADVISE, NOT PASS** [engineering clean + invariants held: schema, `composer/music.py` mix engine with an in-code length-clamp two-axes fence, `pipeline compose music` CLI, loud failure, 19 measurable tests + ruff/mypy green — but the music library is **empty**, so the spec's named s19→s23 real-scene intelligibility demo could not run]. E7 item **stays 🔵**; flip to 🟢 needs licensed tracks + the demo + a separate code review + EM re-REVIEW.) · Prior: 2026-05-29 (INTAKE: **locale-portability authoring principle folded** — prefer language-neutral visuals [numeric/chart → image-only → icon/emoji], default unavoidable on-screen text to English/en-US; cross-cutting bar → `standards.md` step 8 + the next `direct.py` sprint, lint-enforcement half → E5 🔵 [NOT next]; orthogonal to both axes; visual-side complement to shipped MLA. Recommended next sprint UNCHANGED.) · Prior: 2026-05-27 (REVIEW PASS: **Sprint 6 (E4 Slice 3) shipped** — niche `visual_style` medium-clash refactor split `medium_hint` / `palette` / `subject_bias` / `universal_rules`, preserved the back-compat composite, and passed EM REVIEW on `feat/niche-visual-style-split`; s25 demo evidence saved under `tmp/niche-visual-style-split/`. Prior: Sprint 6 formally proposed; production-project greenlight gate added [sibling `production-projects.md`, childhood-bloating explainer parked/not-greenlit]; E7 Audio arsenal epic created) · **Maintainer:** engineering-manager subagent

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

## Current arsenal (baseline, 2026-05-22)

- **Visual types:** `generated_image`, `article_image`, `clip`, `slide`, `rich_slide`,
  `chart` (6 static chart_types — Sprint 1 + line in Sprint 2 🟢), `text_card`,
  `still_frame`
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
  **Remaining silent degradation:** `namecard`/`map` still fall back to `text_card`
  (`base.py:413-422`) — a narrow E5 follow-on, not sprint-sized; fix while next in `base.py`.
- **Known gaps (the demand):** Ken Burns on stills · true book-page-turn animation ·
  animated overlay *entrance* (E3 v2), lower-thirds, CapCut subtitles · niche `visual_style`
  medium-clash root refactor (E4 Slice 3 — actively producing surreal output on
  baby-walker, currently masked by the `skip_niche_style` per-scene workaround) · coarse
  recompose loop · `namecard`/`map` silent `text_card` fallback.

See `.agent-memory/engineering-manager/arsenal-state.md` for the living inventory.

---

## Status legend

🔵 designed, not built · 🟡 in progress · 🟢 shipped · ⚪ idea / unscoped · 🔴 blocked

---

## Epics

Five are **arsenal-direction** epics (the demand-driven backlog: programmatic charts,
programmatic animation, animated overlays, the **audio arsenal** (E7), and, newest, the
**toon engine** for Tim's own hosted shows (E9, 2026-09-27)). Four are **cross-cutting
infrastructure** that the arsenal needs in order to be traceable, safe, and iterable (E4–E6,
plus **E8** two-machine workflow & render portability, 2026-09-24).

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
    queue. *(Idea B, INTAKE 2026-05-26.)*
  - **🔵 AI image-to-video motion (beyond camera moves)** — true generated motion
    (parallax, subject/element animation) for beats where a static image + Ken Burns
    still reads as a slide. Uses the `generate-video` skill tier ($0.029/sec budget →
    $0.050/sec premium; cache by prompt hash). **Distinct from the shipped camera-motion
    path above** — this is generated motion, not a zoom/pan over a fixed frame.
    Demand-future, not demand-now. *(Idea C, INTAKE 2026-05-26.)* **First concrete demand
    (2026-09-27):** the own-show Seedance accent-shot test (restyle a toon animatic, ~$1, needs
    Tim's BytePlus ModelArk account; `docs/own-show.md` next step 3). It stays here and is **not**
    part of E9 v0.
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

### E5 — Scene validation & visual-decision checkpoint  `[infra · quality gate]`  🟢 *v1 shipped (Sprints 1, 4); render-truth still-gate shipped (Sprint 7 — two-layer, EM REVIEW PASS 2026-05-31)*
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
- **🔵 Locale-portability lint** — flag scenes with locale-locked (non-English) baked-in
  on-screen text and surface them in the decision table (visual-side complement to the MLA
  `--secondary-locale` audio path). Authoring principle in `standards.md` (Anatomy step 8).
  Ordered below current priorities — NOT next. (INTAKE 2026-05-29.)
- **Remaining (narrow, not sprint-sized):** `namecard`/`map` still silently fall back to
  `text_card` in `composer/base.py:413-422` — make loud or scope-validate when next in
  that file.
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

### E9 — Toon engine & resource bank (own-show character animation)  `[arsenal]`  🔵 *new epic (INTAKE 2026-09-27); v0 spec Tim-approved 2026-09-27 → Sprint 9 (next)*
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
- **Items:**
  1. **🔵 v0: engine + bank + scene file + `toon` visual type** (Sprint 9, next; see below).
  2. **⚪ After v0 (spec §10, unscoped):**
     - word-level timing (Whisper word timestamps)
     - more characters and sets, from Tim's picks only
     - explainer-graphic kinds (map, timeline, arrows between cards). These are wordless and
       drawn in line A; E1 chart types can inform them, but they don't reuse the PIL chart
       renderer.
     - host A-roll ↔ toon transitions
     - Shorts/vertical framing
     - a `stages/direct.py` taxonomy entry, only if EP1's scene breakdown shows the director
       should emit `toon`
- **Non-goal (Tim, 2026-09-27):** no EP1 scene or story composition until Tim gives the
  outline and plot. Composing EP1 scenes is content work (`own-show.md` step 6) and does not
  belong on this roadmap. Scene 001 appears only as v0's worked example and acceptance test.

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

### Sprint 9 — E9 v0: toon engine + resource bank + `toon` visual type  `[E9]`  🔵 *spec Tim-approved 2026-09-27 · recommended next · implementation plan being written · 🟢 only at EM REVIEW PASS*
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
- **Then:** E8 item 2 (checkout/checkin + hub lock) → E8 item 3 (draft encoder profile).

### Later / unscoped backlog
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
- Ken Burns on stills; true stock-quality book-page-turn (E2 remaining) `🔵`
- Animated reveal for `proportion_blocks` / `timeline` / `comparison` (E2 remaining) `🔵`
- Stock-footage transition asset path (E6 Phase 5) `🔵`
- `namecard`/`map` silent `text_card` fallback → loud or scope-validated (E5 follow-on) `🔵`

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
