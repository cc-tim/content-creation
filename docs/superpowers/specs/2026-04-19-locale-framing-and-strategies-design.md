---
date: 2026-04-19
topic: Locale-framing promotional strategies + ja-JP reproduction of project 1776356443
status: draft
---

# Locale-framing promotional strategies

## Problem

When a video is produced in locale `L_target` but its source material originates from locale `L_source`, the fact that the material is "foreign" is itself an engagement hook. Taiwanese audiences click on "a US university study…" more readily than on the same claim stripped of its origin. Japanese audiences are drawn to "Canadian parents do X…" framings.

The current scriptwrite stage localizes language and adds per-locale cultural bridges, but does not treat source-origin as a framing device. The first concrete gap: there is no easy way to reproduce project `output/projects/1776356443` (an original parenting piece grounded in US research — BYU + Central Michigan) as a ja-JP video that leads with its US origin as the hook.

Secondary problem: per-video metadata maintenance (e.g., adding `source_locale` to every `knowledge.json`) is friction the owner does not want. Promotional framings should live as reusable strategy docs, not as per-project bookkeeping.

## Non-goals

- Contrast material about target-locale norms (e.g., "here's how Japanese parents handle this") — out of scope; no sourcing pipeline for target-side material.
- On-screen `[OVERLAY:title]` changes — script and YouTube metadata only.
- Per-source locale fields in `knowledge.json` — affiliations already present there are enough.
- A generic plugin architecture for strategies — single loader, plain markdown files.

## Scope

1. **Strategy docs as runtime config.** New directory `configs/promo-strategies/` holds `.md` files. Each file is a short, reusable promotional strategy with frontmatter describing when it applies.
2. **First strategy: locale source provenance.** One file — `locale-source-provenance.md` — implements the hook described above.
3. **Strategies auto-loaded into scriptwrite.** On every scriptwrite run, matching strategies are injected into the Claude prompt. No per-project bookkeeping.
4. **Scriptwrite also emits title + description.** A single Claude call produces narration *plus* a YAML front-matter block with `title` and `description`, so promotional framings can shape YouTube metadata without a separate stage.
5. **Reference-script fallback.** Scriptwrite accepts a prior-locale script (e.g., `script_en.md`) as structural reference when `story_structure` is null — needed for `origin: "original"` projects like 1776356443.
6. **Reproduce project 1776356443 as ja-JP.** Concrete, reproducible command path documented in §7.

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

1. Name the origin region or institution in the HOOK section (e.g., "A US university study found…", "Researchers at Brigham Young University…", "Canadian parents do X differently…").
2. Include the origin hint in the YouTube title. Taiwanese-Chinese / Japanese / Spanish audiences click more readily on titles that signal locale-distinct material.
3. Before finalizing, list any locale-specific assumptions in the source material (legal system, geography, norms) the target audience may not share, and address them inline.

Keep it factual. Do not exaggerate credentials or geographic origin.
```

### Frontmatter fields

- `name` (required, string) — stable slug, used only for logging.
- `description` (required, string) — one-line summary; used in logs and in the prompt so the LLM knows *why* a given strategy was injected.
- `applies_when` (required, mapping) — named predicates; the loader evaluates them against `PipelineContext`. See §2 for supported predicates.

### Body

- Plain markdown, injected verbatim into the scriptwrite prompt under a `LOADED STRATEGIES` section.
- Keep bodies short (under ~400 tokens). Long strategies dilute the rest of the prompt and compete with each other.

## 2. Strategy loader

New module: `src/pipeline/strategies.py`.

```python
def load_strategies(ctx: PipelineContext) -> str:
    """Load all strategy files whose applies_when matches ctx. Return concatenated text."""
```

Behavior:

- Reads every `*.md` file under `configs/promo-strategies/`.
- Parses frontmatter with `PyYAML` (already a transitive dep; pin if not).
- For each file, evaluates each `applies_when` predicate; all must be true for the strategy to apply.
- Returns a single string of the form:

```
LOADED STRATEGIES (apply these when writing the script, title, and description):

### {name} — {description}
{body}

### {name} — {description}
{body}
```

- If no strategies match, returns an empty string (caller decides how to handle).

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
source_locale: str | None = None            # origin/region token for source material
reference_script_path: Path | None = None   # existing-locale script used as structural reference
```

`source_locale` is intentionally a free-form origin token, not a strict BCP-47 code. Expected values are short strings like `"US"`, `"CA"`, `"UK"`, `"JP"` or — when a language code is more meaningful — `"en"`, `"ja"`. What matters is only that it is comparable as a string to `ctx.locale` inside `applies_when` predicates. For the initial use case (research-based originals), populate it manually. Future work: the `analyze` stage can infer this from affiliations.

- Both are optional; default `None`.
- `reference_script_path` added to `path_fields` in `from_dict` so serialization round-trips.
- No migration needed for existing `context.json` files; unknown-at-load-time fields default cleanly.

## 4. Scriptwrite changes

Edit `src/pipeline/stages/scriptwrite.py`:

### 4.1 Loosen the story-structure requirement

Replace:

```python
if not ctx.story_structure or not ctx.knowledge_graph:
    raise ValueError("No analysis available — run analyze stage first")
```

with:

```python
if not ctx.knowledge_graph:
    raise ValueError("Knowledge graph is required for scriptwrite")
if not ctx.story_structure and not ctx.reference_script_path:
    raise ValueError(
        "scriptwrite needs either story_structure (from analyze) or "
        "reference_script_path (for origin=original projects)"
    )
```

### 4.2 Extend the prompt builder

`build_scriptwrite_prompt` gains two inputs: `strategies_text: str` and `reference_script: str | None`.

Prompt skeleton (omitting unchanged sections):

```
You are a scriptwriter...

LOCALE: {locale}
LANGUAGE INSTRUCTION: {locale_instruction}

{strategies_text}            ← injected here when non-empty

STORY STRUCTURE:             ← included if present
{story_structure_json}

KNOWLEDGE GRAPH:
{knowledge_graph_json}

REFERENCE SCRIPT (existing version in a different locale — use as structural reference, not for translation):
{reference_script}           ← included if present

VIDEO STRUCTURE: ...
USE THESE MARKERS: ...

OUTPUT FORMAT:
Return a single markdown file starting with a YAML frontmatter block:
---
title: <YouTube title in the target locale, ~60 chars, incorporating loaded strategies>
description: <YouTube description in the target locale, 2-3 paragraphs,
              incorporating loaded strategies and crediting sources>
---

Then the script with markers (as today).
```

### 4.3 Parse and persist title/description

After the Claude call:

1. Split the response at the first `---` / `---` frontmatter block.
2. Write the frontmatter block and script body together to `script_{locale}.md` (unchanged file layout; frontmatter is stored alongside).
3. Also write a sidecar `metadata_{locale}.json` containing `{title, description}` for programmatic access by future publish code.
4. If frontmatter parsing fails, log and continue — title/description become empty strings. The run does not fail.

### 4.4 parse_script_markers update

The existing marker parser must tolerate the new optional frontmatter block. If the file starts with `---`, strip everything up to and including the matching closing `---` before tokenizing. If no frontmatter is present (older scripts like today's `script_en.md`), fall through unchanged. The parser must remain backward-compatible with frontmatter-less scripts.

## 5. Data flow

```
┌──────────────────┐      ┌─────────────────────┐
│ configs/promo-   │      │ PipelineContext     │
│ strategies/*.md  │      │  locale=ja          │
└────────┬─────────┘      │  source_locale=US   │
         │                │  knowledge_graph=…  │
         ▼                │  reference_script=… │
    load_strategies(ctx) ─┤                     │
         │                └──────────┬──────────┘
         ▼                           │
    strategies_text                  │
         │                           │
         └──────────┬────────────────┘
                    ▼
          build_scriptwrite_prompt(...)
                    │
                    ▼
            Claude messages.create
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
   script_ja.md           metadata_ja.json
   (frontmatter +          {title,
    narration markers)      description}
```

## 6. Testing

- `tests/unit/test_strategies.py` —
  - Loads a fixture directory with three strategy files (one always-on, one `target_locale_differs_from_source`, one `target_locale_in: [ja]`).
  - Asserts filtering produces the right subset for different `PipelineContext` values.
  - Asserts malformed frontmatter yields a warning and is skipped (no crash).
- `tests/unit/test_scriptwrite.py` — extend:
  - With `story_structure=None, reference_script_path=<path>`, the prompt contains the reference script and the call succeeds (mocked Claude client).
  - With `story_structure=None, reference_script_path=None`, the stage raises.
  - Title/description parsing: given a mocked Claude response with a valid frontmatter block, assert `metadata_{locale}.json` is written with the expected keys.
  - Title/description parsing: given a malformed frontmatter response, assert the run still completes and metadata file contains empty strings.
- No new integration tests; existing pipeline integration tests cover the scriptwrite-through-compose flow.

## 7. Reproducing project 1776356443 as ja-JP

Concrete steps after implementation lands:

1. **Add source_locale to the existing context.** Edit `output/projects/1776356443/context.json`: set `"source_locale": "US"`, `"reference_script_path": "output/projects/1776356443/script/script_en.md"`.
2. **Produce the new locale in the same project dir** via a new CLI sub-command (or reuse existing scriptwrite+tts+compose):
   ```
   uv run pipeline scriptwrite --project 1776356443 --locale ja
   uv run pipeline tts         --project 1776356443 --locale ja --voice ja-JP-NanamiNeural
   uv run pipeline compose     --project 1776356443 --locale ja
   ```
3. **Outputs (co-located with English):**
   - `script/script_ja.md`
   - `audio/narration_ja.mp3`, `audio/segment_*_ja.mp3`, `audio/subtitles_ja.srt`
   - `compose/final_ja.mp4`
   - `metadata_ja.json`

Scene visuals (`compose/scenes/*_visual.mp4`) are reused across locales since the reference-script mode keeps the narrative beats aligned. Only narration, subtitles, and the final concat are locale-specific.

If the existing CLI does not yet thread `--locale` cleanly through re-invocation of individual stages on a pre-existing project, that plumbing is part of the implementation plan.

## 8. Risks & open questions

- **LLM inference of locale differences.** If a strategy file says "address locale-specific assumptions," the LLM decides which ones apply. Mitigation: the `locale-source-provenance.md` body includes an explicit checklist (legal system, geography, norms) so the LLM has concrete prompts.
- **Prompt bloat.** Each strategy adds tokens to every scriptwrite call. Mitigation: body length soft-cap of ~400 tokens; `applies_when` filtering keeps irrelevant strategies out of the prompt entirely.
- **source_locale remains a hand-populated field** for `origin: "original"` projects. Acceptable because the field is one-time-per-project, not per-video. For future projects coming from `acquire` + `analyze`, the analyze stage can populate it automatically from affiliations — follow-up, not in scope here.
- **Metadata sidecar format.** Initial `metadata_{locale}.json` has just `title` and `description`. A future publish stage will add tags, thumbnail hints, etc. The schema is intentionally minimal to stay flexible.
- **Multiple strategies interacting.** If two strategies apply simultaneously and give conflicting instructions, the LLM has to arbitrate. Initial mitigation: only one strategy file to start. Future: add priority or explicit "conflicts_with" metadata if it becomes a real issue.
