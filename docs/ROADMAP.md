# Content-Creation Arsenal & Infrastructure Roadmap

> **System of record** for visual-arsenal and pipeline-infrastructure development.
> Owned and maintained by the **engineering-manager** subagent
> (`.claude/agents/engineering-manager.md`, dispatched via the `engineering-manager`
> skill). This is the *capability* backlog — what the pipeline can render, validate,
> and surface. Producing individual videos is **not** tracked here; that is content
> work. When this file and a `tmp/*-handoff.md` design doc disagree, the handoff is the
> detailed spec and this file is the prioritized plan of record.

**Last updated:** 2026-05-21 · **Maintainer:** engineering-manager subagent

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

## Current arsenal (baseline, 2026-05-21)

- **Visual types:** `generated_image`, `article_image`, `clip`, `slide`, `rich_slide`,
  `text_card`, `still_frame`
- **Frames:** `open_book_page` (project-level wrap)
- **Transitions:** `page-turn` (weak — aliased to xfade slideleft), `book-page-turn-v2`
- **Known gaps (the demand):** no `chart` type · no programmatic animation (reveals,
  Ken Burns) · no animated overlays · style globals are silent & untraceable · no
  storyboard-write-time validator · coarse recompose loop (full re-render for small edits)

See `.agent-memory/engineering-manager/arsenal-state.md` for the living inventory.

---

## Status legend

🔵 designed, not built · 🟡 in progress · 🟢 shipped · ⚪ idea / unscoped · 🔴 blocked

---

## Epics

Three are the **arsenal-direction** epics (the demand-driven backlog: programmatic charts,
programmatic animation, animated overlays). Three are **cross-cutting infrastructure** that
the arsenal needs in order to be traceable, safe, and iterable.

### E1 — Programmatic charts  `[arsenal]`  🔵
Render data as **styled editorial graphics** (warm sepia / book-page feel), never a Plotly
dashboard. New `chart` visual type, two-pass like `rich_slide` (Flux draft background +
Pillow composite). chart_types: `stat_big_number`, `proportion_blocks`, `timeline`, `bar`,
`comparison` — all five in v1 (Tim's call, 2026-05-21).
- **Demand:** director keeps forcing real datapoints into `slide` because no stat-friendly
  type exists (baby-walker s10/s12/s13).
- **Source:** `tmp/chart-renderer-handoff.md`. **Precedent:** `composer/rich_slide.py`.
- **Unblocks:** stat beats render as real visualizations. **Does NOT** add runtime.

### E2 — Programmatic animation  `[arsenal]`  🔵
Motion generated in-pipeline: animated chart reveals (bar grow, number count-up, line
draw), Ken Burns push/zoom on stills, and a *true* book-page-turn (current one is an
approximation). PIL multi-frame → ffmpeg, or zoompan filter.
- **Demand:** the baby-walker greenlit storyboard (producer loop 3) calls for a **merged
  animated decline-curve** that replaces two tables — no renderer exists for it. Plus
  Ken Burns / transition quality from `docs/future-tasks.md`.
- **Source:** chart handoff open-Q1; narrative-history handoff; future-tasks.
- **Depends on:** E1 (an animated chart reveal needs the chart first).
- **Unblocks:** the decline-curve; livelier stills. **Does NOT** add runtime.

### E3 — Animated overlays  `[arsenal]`  ⚪
Text/graphic layers composited *on top of* images / charts / slides: lower-thirds,
callouts, chart annotations, CapCut-style word-by-word subtitles.
- **Demand:** know-fountains arsenal posture; future-tasks "center-screen animated
  subtitles for Shorts". Overlays will be **Style Manifest elements** (see E4).
- **Depends on:** E4 (so overlays are traceable, not new silent globals).

### E4 — Style Manifest & traceability  `[infra · cross-cutting]`  🔵
A first-class inventory of every style element active on a project — where it came from,
which scenes it applies to, how to remove it. Surfaces today's *silent globals*
(`frame_style`, niche `visual_style`, the unused anchor PNG, seed, rich_slide bg default).
- **Source:** `tmp/style-traceability-handoff.md` (5 slices). **Foundational:** animation
  (E2) and overlays (E3) register here as elements instead of new silent globals.
- **Concrete bugs in scope:** `anchor_image` plumbed-but-never-used no-op; niche
  `visual_style` contradicts photo-realistic prompts.

### E5 — Scene validation & visual-decision checkpoint  `[infra · quality gate]`  🔵
Defense-in-depth: a storyboard-write-time validator (per-type checks, taxonomy drift
detection) + compose-time hard failures replacing today's silent `text_card` fallbacks +
a `confidence`/`rationale` decision table the user reviews before TTS.
- **Source:** `tmp/scene-validation-handoff.md` (Phase B + Phase C).
- **Interface with E1:** chart validation hooks (`chart_type` in set, `data` matches
  schema) live here; chart v1 ships with *minimal inline* validation, full validator later.

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

### ▶ Sprint 1 — Chart Renderer v1 (static, full type set)  `[E1]`  🔵 *proposed*

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
  - Golden-PNG tests per chart_type in `tests/composer/test_chart.py`.
- **Scope OUT (deferred):** animated reveal (→ E2) · full Style Manifest integration
  (→ E4; chart consumes `theme` directly for now) · full storyboard validator (→ E5) ·
  "small multiples" grid (chart handoff v2 idea).
- **Dependencies:** none blocking. (Parallel `slide` schema-mismatch fix is independent.)
- **Unblocks:** baby-walker stat beats render as real charts instead of text slides — a
  **visual-quality** lift. **Does NOT** unblock the 6–8 min runtime (that needs more
  material), nor the merged animated decline-curve (that needs E2 / Sprint 2).
- **Acceptance:** all 5 chart_types render to stable golden PNGs; director selects `chart`
  over `slide` for the baby-walker stat scenes on regen; `pytest` + `ruff` + `mypy` green.
- **Cost:** ~$0.003 per unique background, cached forever; ~$0.015 for the whole
  baby-walker project. Re-renders free.
- **Size:** ~1–1.5 build sessions (full type set; `bar`/`comparison` add layout + tests).

---

### Sprint 2 — Animated chart reveal + the decline-curve  `[E2]`  🔵
Add an animated variant: line-draw / timeline reveal and `stat_big_number` count-up
(PIL multi-frame → ffmpeg). Delivers the baby-walker **merged animated decline-curve**
(1990→2014 with regulation milestone markers) the producer greenlit in loop 3.
Visual-quality axis only — no runtime.

### Sprint 3 — Style Manifest Slices 1–2  `[E4]`  🔵
Inventory (`pipeline style list`) + `style add`/`remove` (+ per-scene) with append-only
`style_log.json`; fix the `anchor_image` no-op. Makes charts/animation/overlays traceable
elements rather than silent globals — foundational before E3.

### Sprint 4 — Storyboard validator + visual-decision checkpoint  `[E5]`  🔵
Layer-1 write-time validator (incl. chart schema checks promoted from Sprint 1's inline
stub) + `confidence`/`rationale` decision table before TTS. CLI-first; dashboard view later.

### Later / unscoped backlog
- Animated overlays (E3): lower-thirds, chart annotations, CapCut subtitles `⚪`
- Dashboard surfaces (E6): Production Contract panel, recompose buttons, Style panel,
  Decision table, transition preview sheets `🔵`
- Niche-template refactor: split `visual_style` → `medium_hint`/`palette`/`subject_bias`/
  `universal_rules` (E4 Slice 3) `🔵`
- Ken Burns on stills; true stock-quality book-page-turn (E2) `🔵`
- Stock-footage transition asset path (E6 Phase 5) `🔵`

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
