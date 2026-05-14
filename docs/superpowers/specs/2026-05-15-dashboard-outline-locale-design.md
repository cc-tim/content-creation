# Dashboard Outline View + Per-Locale Narration — Design

**Date:** 2026-05-15
**Status:** Approved (design), pending implementation plan

## Problem

Two gaps surfaced while working on project `20260504-115232-baby-walker-story`:

1. **No higher-level view.** The dashboard only shows per-scene narration and
   subtitle. There is no way to read the storyline / outline / section structure
   to judge whether scene-to-scene flow is clunky.
2. **No per-locale review.** The project is MLA (`mla=True`,
   `secondary_locale=en`). `narration_en.mp3` and `subtitles_en.srt` exist, but
   the dashboard has no control to switch to the English version and preview it.
   Separately, the per-locale narration today is a literal translation, not a
   genuine locale adaptation.

## Decisions (locked during brainstorming)

- **Scope:** one plan covering schema, pipeline, migration, and dashboard.
- **Authoring model:** *beat-first, locales as peers*. The storyboard stage emits
  a language-neutral `beat` per scene; each locale's narration is scriptwritten
  independently from the beat + that locale's cultural prompt — not translated.
- **Migration:** auto-migrate existing storyboards to the new schema *and*
  backfill beats, so projects like baby-walker become fully usable immediately.
- **Dashboard editing:** extend the existing Edit-mode `data-edit-token` pattern
  to the new elements (beats, per-locale narration, outline rows). No direct
  inline text editing; no scene reordering (explicitly out of scope — the
  dashboard is for reading + tagging edit instructions).
- **Locale model:** MLA stays the shipping model (one video render + alternate
  audio tracks uploaded manually to YouTube Studio). The dashboard previews other
  locales via *audio-swap*: the shared video plays muted while the locale's
  `narration_<locale>.mp3` plays and `subtitles_<locale>.srt` displays. No
  separate per-locale video is ever rendered. baby-walker's MLA output was
  correct as produced — no `/produce` change is needed for the locale model.
- **Pipeline structure:** Approach A — split `DirectStage` (structure + beats)
  from a revived `ScriptwriteStage` (per-locale narration).

## Section 1 — Storyboard schema & model

`Scene` dataclass (`src/pipeline/storyboard.py:141`):

- `narration: str` → `narration: dict[str, str]` — locale-keyed map, e.g.
  `{"zh-TW": "…", "en": "…"}`. The `narration_en: str | None` special-case field
  is removed.
- New `beat: str` — a language-neutral one-line statement of what the scene must
  accomplish (e.g. "establishes the 600-year design stasis").
- `narration_est_sec` stays, but its meaning becomes the *shared duration budget*
  for the beat — every locale targets it. This is correct for MLA, where all
  locales share one timeline.
- `Scene.from_dict` accepts both shapes: old flat (`narration: str` +
  optional `narration_en`) is folded into the locale map keyed by the project's
  primary locale and `"en"`. `to_dict` always writes the new shape.
- Helper methods that read narration (`narration_for_tts`, duration sums) take a
  `locale` argument and read `narration[locale]`.

Storyboard top-level `title` / `description` also become locale maps (they are
already generated per-locale today, merely stored flat).

## Section 2 — Pipeline restructure (Approach A)

`DirectStage` stops writing narration. It emits the storyboard skeleton: `id`,
`section`, `beat`, `visual`, `narration_est_sec`, `pause_after_sec`, transitions,
theme. One Claude call, language-neutral (beats may be written in English as a
working language but represent intent, not narration text).

`ScriptwriteStage` is revived from the existing dead file
(`src/pipeline/stages/scriptwrite.py`). It runs after `DirectStage`, reads
`ctx.locale` + `ctx.secondary_locale` (and any future locale list), and for each
locale makes one Claude call: write narration for these beats, in this locale,
with this cultural framing, each scene within its `narration_est_sec` budget. It
writes `narration[locale]` for every scene. The existing `LOCALE_INSTRUCTIONS`
dict in that file is the cultural-prompt input.

New orchestrator chain: `acquire → analyze → direct → scriptwrite → tts → compose`.

`--start-from` gains `scriptwrite` as a resume point, so "re-adapt just the
narration" re-runs `scriptwrite → tts → compose` without regenerating structure.
`TtsStage` already loops locales for MLA; it now reads `narration[locale]`
instead of `narration` / `narration_en`.

## Section 3 — Migration & backfill

A one-time migration over every `output/projects/*/storyboard.json`:

- **Schema migration** (mechanical, no LLM): flat `narration` →
  `{primary_locale: narration}`; fold `narration_en` → `narration["en"]`; same
  for `title` / `description`. Idempotent — detects already-migrated files and
  skips them.
- **Beat backfill** (one LLM call per project): for storyboards with no `beat`
  fields, send all scenes' narration + section to Claude and get back a `beat`
  per scene.

Exposed as `pipeline storyboard migrate [--project-id X | --all]`. The dual-shape
`Scene.from_dict` support (Section 1) is the safety net so old files always load;
the migration is what makes old projects *fully* featured rather than merely
loadable.

## Section 4 — Dashboard: scanner, outline view, locale switcher

**Scanner** (`src/pipeline/dashboard/scanner.py`): expose `beat` per scene;
expose `narration` as the full locale map (not just primary); detect available
locales from `narration` keys plus which have `narration_<locale>.mp3` /
`subtitles_<locale>.srt` on disk. Add a `locales` list to the project record.

**Outline view** — a new collapsible panel above the scene strip:

- Scenes grouped into section bands (hook / context / rising / climax /
  aftermath / analysis / …), each header showing scene count + summed duration.
- One row per scene: `id · duration · visual type · beat`. Reads top-to-bottom
  as the storyline.
- Read-focused; rows are Edit-mode taggable (Section 5).

**Locale switcher** — a control on the detail panel, beside the existing variant
tabs. Switching locale:

- Swaps the outline + per-scene narration + subtitle panels to that locale's text.
- Audio-swap preview: the shared video plays muted; a paired `<audio>` element
  plays `narration_<locale>.mp3`; subtitle display swaps to
  `subtitles_<locale>.srt`.
- The two existing variant tabs (overlay / no-overlay) stay — locale is an
  independent axis from compose variant.

## Section 5 — Edit-mode integration

New `data-edit-token` values, consistent with the existing `@<scene>/<field>`
scheme:

- `@<scene>/beat` — on each outline row's beat text.
- `@<scene>/narration/<locale>` — locale-scoped narration token, replacing
  today's locale-blind `@<scene>/narration`.
- `@<scene>` — on the outline row itself, for scene-level instructions.

The Edit-mode agent runner (`agent_runner.py` / `mutation_runtime.py`) routes
`@<scene>/narration/<locale>` to a narration edit scoped to that locale, and
`@<scene>/beat` to a beat edit. Editing a beat does **not** auto-rewrite
narration — it flags the affected locales' narration as stale in the UI so the
user can deliberately re-issue a scriptwrite instruction.

## Section 6 — Testing

- **Schema:** `from_dict` round-trips both old flat and new map shapes; `to_dict`
  always emits the new shape.
- **Migration:** old fixture → migrated fixture; idempotent on re-run; beat
  backfill with mocked LLM.
- **Pipeline:** `DirectStage` output has no narration and has beats;
  `ScriptwriteStage` fills every locale; `--start-from scriptwrite` resumes
  correctly.
- **Scanner:** locale map + `locales` list + `beat` surface correctly; an
  un-migrated project still scans without error.
- **Dashboard:** outline groups by section; locale switch swaps text + audio
  source; edit tokens present on the new elements.

Tests follow the existing layout (`tests/unit/test_dashboard_*`, stage tests).

## Out of scope

- Scene reordering (any UI or CLI).
- Rendering separate per-locale video files.
- Changes to the MLA shipping / upload workflow.
- New locales beyond the existing zh-TW / en / ja / es-MX set.
