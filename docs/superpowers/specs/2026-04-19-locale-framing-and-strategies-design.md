---
date: 2026-04-19
topic: Locale-framing promotional strategies + ja-JP reproduction of project 1776356443
status: revised (v2 targets DirectStage instead of the dead ScriptwriteStage)
---

# Locale-framing promotional strategies

## Problem

When a video is produced in locale `L_target` but its source material originates from locale `L_source`, the fact that the material is "foreign" is itself an engagement hook. Taiwanese audiences click on "a US university study…" more readily than on the same claim stripped of its origin. Japanese audiences are drawn to "Canadian parents do X…" framings.

The current directing stage (`DirectStage` in `src/pipeline/stages/direct.py`) localizes language via a small `LOCALE_INSTRUCTIONS` dict but does not treat source-origin as a framing device. First concrete gap: no easy way to reproduce project `output/projects/1776356443` (an original parenting piece grounded in US research — BYU + Central Michigan) as a ja-JP video that leads with its US origin as the hook.

Secondary problem: per-video metadata maintenance (e.g., adding `source_locale` to every `knowledge.json`) is friction the owner does not want. Promotional framings should live as reusable strategy docs, not as per-project bookkeeping.

Third issue surfaced during design: regenerating `storyboard.json` in a second locale overwrites the first-locale storyboard and, because the new JA storyboard might have a different scene count or structure than EN, breaks reuse of `compose/scenes/*_visual.mp4`. A "parallel-locale" mode for `DirectStage` is required.

## Non-goals

- Contrast material about target-locale norms (e.g., "here's how Japanese parents handle this") — out of scope; no sourcing pipeline for target-side material.
- On-screen `[OVERLAY:title]` changes — script and YouTube metadata only.
- Per-source locale fields in `knowledge.json` — affiliations already present there are enough.
- A generic plugin architecture for strategies — single loader, plain markdown files.
- Deleting dead `scriptwrite.py`. Separate cleanup.

## Scope

1. **Strategy docs as runtime config.** New directory `configs/promo-strategies/` holds `.md` files. Each file is a short reusable promotional strategy with frontmatter describing when it applies.
2. **First strategy: locale source provenance.** One file — `locale-source-provenance.md` — implements the hook described above.
3. **Strategies auto-loaded into DirectStage.** On every direct-stage run, matching strategies are injected into the Claude prompt. No per-project bookkeeping.
4. **DirectStage emits title + description.** Its JSON response is extended to include top-level `title` and `description`, written into the storyboard for use by downstream metadata/publish code.
5. **Locale-suffixed storyboard path.** `storyboard_{locale}.json` replaces `storyboard.json` so EN and JA versions coexist.
6. **Parallel-locale mode.** When a `reference_storyboard_path` is set on the `PipelineContext`, DirectStage is instructed to produce a *parallel-structured* storyboard in the target locale: same scene count, same scene ids, same visuals and facts_ref — only narration changes. This lets `compose/scenes/*_visual.mp4` be reused across locales.
7. **Reproduce project 1776356443 as ja-JP.** Concrete, reproducible command path documented in §7.

## 1. Strategy file format

Strategy files live at `configs/promo-strategies/<slug>.md` with YAML frontmatter and markdown body.

```markdown
---
name: locale-source-provenance
description: Frame source-material origin when target audience differs from source locale
applies_when:
  target_locale_differs_from_source: true
---

# Source Provenance Framing

When the target audience's locale differs from the locale where the research / source material originates, treat the source origin as an engagement hook:

1. Name the origin region or institution in the HOOK scene (e.g., "A US university study found…", "Researchers at Brigham Young University…").
2. Include the origin hint in the video title. Taiwanese-Chinese / Japanese / Spanish audiences click more readily on titles that signal locale-distinct material.
3. Before finalizing, list any locale-specific assumptions in the source material (legal system, geography, norms) the target audience may not share, and address them inline in early scenes.

Keep it factual. Do not exaggerate credentials or geographic origin.
```

### Frontmatter fields

- `name` (required, string) — stable slug, used only for logging.
- `description` (required, string) — one-line summary; also injected into the prompt so the LLM knows *why* the strategy was loaded.
- `applies_when` (required, mapping) — named predicates; the loader evaluates them against `PipelineContext`. See §2.

### Body

- Plain markdown, injected verbatim into the direct-stage prompt under a `LOADED STRATEGIES` section.
- Keep bodies short (under ~400 tokens). Long strategies dilute the rest of the prompt.

## 2. Strategy loader

New module: `src/pipeline/strategies.py`.

```python
def load_strategies(ctx: PipelineContext) -> str:
    """Load all strategy files whose applies_when matches ctx. Return concatenated text."""
```

Behavior:

- Reads every `*.md` file under `configs/promo-strategies/`.
- Parses frontmatter with `PyYAML` (added as a project dependency by this plan).
- For each file, evaluates each `applies_when` predicate; all must be true for the strategy to apply.
- Returns a single string of the form:

```
LOADED STRATEGIES (apply these when writing narration, title, and description):

### {name} — {description}
{body}

### {name} — {description}
{body}
```

- If no strategies match, returns an empty string.

### Supported predicates (initial set)

| Predicate | Semantics |
|---|---|
| `always: true` | Always matches. |
| `target_locale_differs_from_source: true` | Matches when `ctx.source_locale` is set and differs from `ctx.locale`. If `source_locale` is None, predicate is false (no claim, no assumption). |
| `target_locale_in: [list]` | Matches when `ctx.locale` is in the list. |
| `source_locale_in: [list]` | Matches when `ctx.source_locale` is in the list. |

New predicates are added by extending the dispatch table in `strategies.py`. Deliberately avoids eval / expression languages for safety.

### Error handling

- Malformed frontmatter → log a warning, skip that file. Do not crash the pipeline.
- Unknown predicate key → log a warning, predicate evaluates to false. Do not crash.
- Missing `configs/promo-strategies/` directory → return empty string; log at debug level.

## 3. PipelineContext changes

Add two optional fields to `src/pipeline/stages/base.py::PipelineContext`:

```python
source_locale: str | None = None                # origin/region token for source material
reference_storyboard_path: Path | None = None   # existing-locale storyboard used for parallel-locale generation
```

`source_locale` is intentionally a free-form origin token, not a strict BCP-47 code. Expected values are short strings like `"US"`, `"CA"`, `"UK"`, `"JP"` or — when a language code is more meaningful — `"en"`, `"ja"`. What matters is only that it is comparable as a string to `ctx.locale` inside `applies_when` predicates. Populate it manually for the initial use case. Future work: the `analyze` stage can infer it from affiliations.

`reference_storyboard_path` added to `path_fields` in `from_dict` so serialization round-trips. Defaults `None`.

## 4. Storyboard model changes

Edit `src/pipeline/storyboard.py::Storyboard`:

- Add two optional top-level fields: `title: str | None = None` and `description: str | None = None`.
- `to_dict` emits them only when non-None.
- `from_dict` reads them with `.get()`.
- Existing storyboards without these fields load cleanly.

## 5. DirectStage changes

Edit `src/pipeline/stages/direct.py`:

### 5.1 Locale-suffixed output path

Replace:

```python
storyboard_path = ctx.work_dir / "storyboard.json"
```

with:

```python
storyboard_path = ctx.work_dir / f"storyboard_{ctx.locale}.json"
```

Existing projects with unsuffixed `storyboard.json` continue to work because `ctx.storyboard_path` is already saved in `context.json`; downstream TTS and compose read from that field.

### 5.2 Strategy injection

At the top of `run`, call `load_strategies(ctx)` and pass the result into `build_direct_prompt` as a new parameter `strategies_text`.

### 5.3 Reference-storyboard injection (parallel-locale mode)

If `ctx.reference_storyboard_path` is set and the file exists, load it and include its contents in the prompt under a `REFERENCE STORYBOARD` section. Add an instruction:

> You are producing a parallel-locale version. Preserve scene count, scene ids, `facts_ref`, `visual`, and `overlay` from the reference. Only rewrite `narration` (and `narration_est_sec`) in the target locale, applying any loaded strategies.

The LLM returns the same scene skeleton with translated/adapted narration.

### 5.4 Title + description

Extend the JSON contract in `build_direct_prompt` so Claude must return:

```json
{
  "title": "YouTube title in target locale (~60 chars), applying loaded strategies",
  "description": "YouTube description in target locale (2-3 paragraphs), crediting sources",
  "scenes": [ ... ]
}
```

Parse both into the Storyboard object. Persist them as part of `storyboard_{locale}.json`.

### 5.5 Script file derivation unchanged

`script_{locale}.md` continues to be derived from the storyboard and written to `ctx.work_dir / "script" / f"script_{ctx.locale}.md"`.

### 5.6 Prompt skeleton

```
You are a video director...

LOCALE: {locale}
LANGUAGE INSTRUCTION: {locale_instruction}

{strategies_text}              ← injected when non-empty

{reference_storyboard_block}   ← injected when reference_storyboard_path is set

{structure}                    ← existing "VIDEO STRUCTURE" section

VISUAL TYPES: ...
OVERLAY: ...

Each scene references fact IDs from the knowledge base.

Return ONLY valid JSON:
{
  "title": "...",
  "description": "...",
  "scenes": [ ... ]
}

KNOWLEDGE BASE:
{knowledge_json}
```

## 6. Data flow

```
┌──────────────────┐      ┌──────────────────────┐
│ configs/promo-   │      │ PipelineContext      │
│ strategies/*.md  │      │  locale=ja           │
└────────┬─────────┘      │  source_locale=US    │
         │                │  knowledge_path=…    │
         ▼                │  reference_          │
    load_strategies ──────┤    storyboard_path=… │
         │                └──────────┬───────────┘
         ▼                           │
    strategies_text                  │
         └──────────┬─────────────── │
                    ▼                │
          build_direct_prompt(…) ◀───┘
                    │
                    ▼
            Claude messages.create
                    │
                    ▼
       Storyboard{title, description, scenes}
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
    storyboard_   script/    (title & description stored
    ja.json       script_    inside storyboard_ja.json)
                  ja.md
```

## 7. Reproducing project 1776356443 as ja-JP

1. **Prepare reference storyboard.** The project currently has `storyboard.json` (EN). Rename it to `storyboard_en.json` so both locales can coexist.
2. **Update context.** Edit `output/projects/1776356443/context.json`:
   - `"locale": "ja"`
   - `"source_locale": "US"`
   - `"reference_storyboard_path": "output/projects/1776356443/storyboard_en.json"`
   - `"storyboard_path": "output/projects/1776356443/storyboard_en.json"` (temporary — will be overwritten by DirectStage)
   - `"voice_id": "ja-JP-NanamiNeural"`
3. **Regenerate storyboard in JA.** Run DirectStage with the updated context. Output: `storyboard_ja.json` (with `title` / `description` / JA narration).
4. **Regenerate TTS and compose.** Run TTS and compose stages; they pick up `ctx.storyboard_path` (now the JA storyboard) and produce JA audio + final video.
5. **Outputs (co-located with English):**
   - `storyboard_ja.json`
   - `script/script_ja.md`
   - `audio/segment_*` regenerated, `audio/narration_ja.mp3`, `audio/subtitles_ja.srt`
   - `compose/final_ja.mp4`
   - Title and description available via `storyboard_ja.json["title"]` / `["description"]`.

Scene visuals (`compose/scenes/*_visual.mp4`) are reused across locales because parallel-locale mode preserves scene ids and visuals. Only narration-derived assets (audio segments, subtitles, final concat) are re-produced.

If the existing CLI does not thread the extended context fields cleanly through a stage-only re-run, that plumbing is part of the implementation plan.

## 8. Testing strategy

- `tests/unit/test_strategies.py` — new.
  - Fixture dir with three strategy files (one always-on, one `target_locale_differs_from_source`, one `target_locale_in: [ja]`).
  - Asserts filtering produces the right subset for different `PipelineContext` values.
  - Asserts malformed frontmatter yields a warning and is skipped (no crash).
- `tests/unit/test_direct.py` — extend.
  - With `reference_storyboard_path` set, the prompt contains a `REFERENCE STORYBOARD` block.
  - Without `reference_storyboard_path`, no such block.
  - Storyboard output path is `storyboard_{locale}.json`.
  - Claude response including `title`/`description` is parsed into the Storyboard and persisted.
  - Missing `title`/`description` in response is handled gracefully (Storyboard field is `None`, run does not fail).
  - When a matching strategy is present in a test-fixture dir, the prompt contains the `LOADED STRATEGIES` block.
- `tests/unit/test_base.py` — extend.
  - `PipelineContext` round-trips `source_locale` and `reference_storyboard_path` through `to_dict` / `from_dict`.
- No new integration tests; existing pipeline integration tests cover the direct-through-compose flow.

## 9. Risks & open questions

- **LLM inference of locale differences.** If a strategy file says "address locale-specific assumptions," the LLM decides which ones apply. Mitigation: the `locale-source-provenance.md` body includes an explicit checklist (legal system, geography, norms) so the LLM has concrete prompts.
- **Prompt bloat.** Each strategy adds tokens to every DirectStage call. Mitigation: body length soft-cap of ~400 tokens; `applies_when` filtering keeps irrelevant strategies out of the prompt entirely.
- **`source_locale` remains a hand-populated field** for `origin: "original"` projects. Acceptable because the field is one-time-per-project. For future projects coming from `acquire` + `analyze`, the analyze stage can populate it automatically — follow-up, not in scope.
- **Parallel-locale drift.** The LLM might still invent extra scenes or renumber ids despite being told not to. Mitigation: after receiving the response, validate that scene ids and counts match the reference storyboard; log a warning if not. Do not crash — the human review gate catches it.
- **`storyboard.json` vs `storyboard_{locale}.json`.** Existing projects have unsuffixed filenames. They continue to work because `ctx.storyboard_path` is stored in `context.json`. New DirectStage runs write the suffixed form. No migration script needed.
- **Multiple strategies interacting.** If two strategies apply simultaneously and give conflicting instructions, the LLM has to arbitrate. Initial mitigation: only one strategy file to start. Future: add priority or explicit "conflicts_with" metadata if it becomes a real issue.
