# Content-Creation Arsenal & Infrastructure Roadmap

> **System of record** for visual-arsenal and pipeline-infrastructure development.
> Owned and maintained by the **engineering-manager** subagent
> (`.claude/agents/engineering-manager.md`, dispatched via the `engineering-manager`
> skill). This is the *capability* backlog — what the pipeline can render, validate,
> and surface. Producing individual videos is **not** tracked here; that is content
> work. When this file and a `tmp/*-handoff.md` design doc disagree, the handoff is the
> detailed spec and this file is the prioritized plan of record.

**Last updated:** 2026-05-22 (Sprint 4 shipped; Sprint 5 = E3 callout overlay v1 proposed after Tim's pivot; E4 Slice 3 rolled to Sprint 6) · **Maintainer:** engineering-manager subagent

---

## North star

Quality is the only north star (`CLAUDE.md` → "Ultimate Goal"). The visual **arsenal is
a variable, not a fixed set**: when a beat's best-fit visual is a category we have not
built, we *build the category* rather than downgrading the content to fit current
weapons (know-fountains `CLAUDE.md` → "Elevating the visual arsenal").

**Two axes, always kept distinct** (producer loop-4 lesson, baby-walker):

| Axis | What moves it | What does NOT move it |
|------|---------------|------------------------|
| **Visual quality / slideshow-risk** | richer rendering — charts, animation, overlays | — |
| **Runtime** | more distinct beats (more story / more sources) | richer rendering. A 4–5 min story rendered beautifully is still 4–5 min. |

Every sprint states which axis it serves. We never promise runtime from an arsenal item.

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
- **Compose-time loud failures (🟢):** `composer/base.py` raises `SceneRenderError`
  (reason + suggested_fix) for a missing-or-corrupt `article_image`/`image` path (the old
  silent `text_card` fallback was removed in 5a33f0a). **Remaining silent degradation:**
  `namecard`/`map` still fall back to `text_card` (`base.py:413-422`) — a narrow E5
  follow-on, not sprint-sized; fix while next in `base.py`.
- **Known gaps (the demand):** Ken Burns on stills · true book-page-turn animation ·
  animated overlays (lower-thirds, callouts, CapCut subtitles) · niche `visual_style`
  medium-clash root refactor (E4 Slice 3 — actively producing surreal output on
  baby-walker, currently masked by the `skip_niche_style` per-scene workaround) · coarse
  recompose loop · `namecard`/`map` silent `text_card` fallback.

See `.agent-memory/engineering-manager/arsenal-state.md` for the living inventory.

---

## Status legend

🔵 designed, not built · 🟡 in progress · 🟢 shipped · ⚪ idea / unscoped · 🔴 blocked

---

## Epics

Three are the **arsenal-direction** epics (the demand-driven backlog: programmatic charts,
programmatic animation, animated overlays). Three are **cross-cutting infrastructure** that
the arsenal needs in order to be traceable, safe, and iterable.

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
  `comparison`; Ken Burns push/zoom on stills; a *true* book-page-turn (current is an
  approximation).
- **Source:** chart handoff open-Q1; narrative-history handoff; future-tasks.
- **Depends on:** E1 (animated reveal needs the static chart substrate). ✅
- **Unblocks:** the decline-curve; count-up + bar-grow on stat-heavy beats; trend-over-time
  beats via `line`. **Does NOT** add runtime — `reveal_duration_sec` validated
  ≤ `scene_duration − 0.5s` (the two-axes rule, in code).

### E3 — Animated overlays  `[arsenal]`  🟡 *v1 proposed (Sprint 5, after Tim's 2026-05-22 pivot)*
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
- **Sprint 5 (v1):** a manifest-registered, pure-renderer `callout` primitive with
  collision-avoidance placement, consumed by `chart.py` for marker labels. **v2+:** animated
  entrance for the callout, lower-thirds, CapCut word-by-word subtitles (static→animated
  split mirrors E1→E2).

### E4 — Style Manifest & traceability  `[infra · cross-cutting]`  🟡 *Slices 1–2 + 4 shipped (Sprint 3); Slice 3 sketched as Sprint 6 (rolled from Sprint 5 per Tim's pivot)*
A first-class inventory of every style element active on a project — where it came from,
which scenes it applies to, how to remove it. Surfaces today's *silent globals*
(`frame_style`, niche `visual_style`, the unused anchor PNG, seed, rich_slide bg default).
- **Source:** `tmp/style-traceability-handoff.md` (5 slices). **Foundational:** animation
  (E2) and overlays (E3) register here as elements instead of new silent globals.
- **Shipped (Sprint 3):** `src/pipeline/style/` package; `pipeline style list/add/remove`;
  append-only `style_log.json`; `anchor_image` dead-code removed (Slice 4 — the no-op was
  deleted; img2img re-implementation explicitly deferred).
- **Remaining:** **Slice 3** — niche `visual_style` medium-clash root refactor (split into
  `medium_hint`/`palette`/`subject_bias`/`universal_rules`; the prompt assembler in
  `composer/base.py:328-340` consumes them at element granularity instead of the
  all-or-nothing `skip_niche_style` symptom-fix) — **sketched as Sprint 6** (was the prior
  Sprint-5 proposal; rolled per Tim's 2026-05-22 E3 pivot). **Slice 5** — dashboard Style
  panel (rolls to E6 surfaces).
- **Concrete bug still open:** niche `visual_style` contradicts photo-realistic prompts
  (surreal output on baby-walker; the Slice 3 target).

### E5 — Scene validation & visual-decision checkpoint  `[infra · quality gate]`  🟢 *v1 shipped (Sprints 1, 4) — handoff doc no longer on disk*
Defense-in-depth: a storyboard-write-time validator (per-type checks, taxonomy drift
detection) + compose-time hard failures replacing the old silent `text_card` fallbacks +
a `confidence`/`rationale` decision table the user reviews before TTS.
- **Shipped:** all-type `storyboard_validator.py` incl. the `chart` branch (Sprint 4),
  wired into `direct.py`; standalone `pipeline validate` CLI (Sprint 4); compose-time
  `SceneRenderError` for missing/corrupt `article_image` (5a33f0a); the decision table.
- **Remaining (narrow, not sprint-sized):** `namecard`/`map` still silently fall back to
  `text_card` in `composer/base.py:413-422` — make loud or scope-validate when next in
  that file.
- **Interface with E1:** chart validation hooks (`chart_type` in set, `data` matches
  schema) live here; the chart branch delegates to `composer/chart.py:validate_chart_visual`.

### E6 — Compose efficiency & dashboard surfaces  `[infra · feedback loop]`  🔵
Tighten the iteration loop so new visuals can be tuned without full re-renders:
`compose transitions` / `compose frame`, contract-aware cache invalidation, Production
Contract panel, render-freshness warnings, transition UI redesign, preview contact sheets,
and (later) Style/Decision panels feeding from E4/E5.
- **Source:** `tmp/dashboard-transition-workflow-improvement-plan.md` (5 phases). Some
  transition/frame groundwork already shipped (`book-page-turn-v2`, open-book frame).

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

### ▶ Sprint 5 — Callout overlay primitive v1 (chart marker-label placement)  `[E3]`  🔵 *next — PROPOSED, awaiting greenlight*
Open E3 with a **manifest-registered `callout` overlay primitive** — a pure renderer
`(callout, base_image, width, height, palette) → PIL.Image` (chart_anim purity precedent)
plus collision-avoidance placement (vertical dodge to the next free row up to N rows, with
leader lines). `composer/chart.py` consumes it for line-chart marker labels, **replacing
the inline 2-row-stagger `draw.text` at `chart.py:529-539`** that overlaps when markers sit
<5yr apart on a long span (the observed baby-walker s21 decline-curve bug). In-area:
convert the silent `apply_overlay` `try/except`→`logger.warning` at `compose.py:1060` into a
loud failure. Animated entrance deferred to **v2** — the static→animated split mirrors E1
(Sprint 1) → E2 (Sprint 2), the sequencing Tim greenlit for charts. **Visual-quality axis
(removes degradation + new primitive); zero runtime; no code-level fence in v1 (no
animation yet — the fence lands with v2).** Tim pivoted to E3 on 2026-05-22; the E4 Slice 3
refactor rolls to Sprint 6 (sketched below). Full 11-part proposal in `sprint-log.md`.

### Sprint 6 (sketched) — Niche `visual_style` medium-clash refactor (E4 Slice 3)  `[E4]`  🔵 *sketched — rolled from the prior Sprint-5 proposal per Tim's 2026-05-22 pivot*
Split the niche template's monolithic `visual_style` into `medium_hint` / `palette` /
`subject_bias` / `universal_rules` so the assembler at `composer/base.py:328-340` stops
fusing a medium descriptor onto photo-realistic prompts (surreal baby-walker s25 output,
today masked by the blunt `skip_niche_style` toggle). Backwards-compat `visual_style`
composite preserved. Visual-quality axis (fixes existing degradation); zero runtime. The
full 11-part proposal is preserved in `sprint-log.md` (annotated "superseded as Sprint 5;
rolled to Sprint 6").

### Later / unscoped backlog
- Animated overlays v2+ (E3): **animated entrance** for the callout primitive + lower-thirds
  + CapCut-style word-by-word subtitles `🔵` — follow-ons to Sprint 5's static v1.
- Dashboard surfaces (E6): Production Contract panel, recompose buttons, Style panel,
  Decision table, transition preview sheets `🔵` — **partly in flight** by another agent
  (`docs/superpowers/plans/2026-05-16-dashboard-timeline-draggable-sections.md` + uncommitted
  job_queue/server edits); do not double-schedule.
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

`future-tasks.md` remains the catch-all idea bin. **Arsenal/visual-rendering capabilities
are tracked here**, not there — its "Visual & Rendering" entries that are rendering
capabilities (Ken Burns, transition effects, animated subtitles) are absorbed into E1–E3/E6
above. Material-acquisition and non-rendering items (B-roll sourcing, channel-brand
templates, SQLite, discovery/observability) stay in `future-tasks.md`.
