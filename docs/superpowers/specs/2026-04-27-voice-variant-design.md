# Voice Variant Workflow — Design Spec

**Date:** 2026-04-27
**Status:** Approved

## Problem

Creating a video with a custom voice (e.g. `tim-zhtw-fish`) on top of an
already-produced project currently requires manually:

1. Creating a new project directory
2. Crafting a `context.json` that cross-references the source project's
   storyboard/script/knowledge files with a different `voice_id`
3. Running `produce --start-from tts`

This is error-prone and undiscoverable. The workflow should be a single
command with a post-render decision prompt.

---

## Decisions

| Question | Decision |
|---|---|
| Independent copy or linked? | Independent — variant gets its own storyboard, script, knowledge copies |
| Directory naming | `{parent-project-id}_{voice-id}` e.g. `1776997800_tim-zhtw-fish` |
| `project_id` schema | Stays `int`; add `parent_project_id: int \| None` + `variant_label: str \| None` to `PipelineContext` |
| "Replace original" mechanic | Option C — copy variant's `compose/scenes/*.mp4` + `audio/` + SRT + segment_timings into parent, then `reburn` (no re-render) |
| Post-render prompt | Soft hint: Promote / Delete / Keep both |

---

## Architecture

### New CLI subcommands (under `pipeline compose`)

#### `pipeline compose voice-variant`

```
uv run pipeline compose voice-variant --from-project <ID> --voice <voice-id>
```

Steps:
1. Resolve source project work_dir from `--from-project`
2. Compute variant dir name: `output/projects/{parent-id}_{voice-id}/`
3. Error if that directory already exists (idempotency guard — user must
   `--force` to overwrite)
4. `mkdir` the variant dir
5. Copy into variant dir:
   - `storyboard.json`
   - `script/` directory
   - `knowledge.json`
   - `metadata.json` (if present)
   - `thumbnail.png` (if present)
   - **Not copied:** `audio/`, `compose/`, `source/`
6. Write `context.json` from parent's context with these overrides:
   - `project_id` = `int(time.time())` (fresh int)
   - `work_dir` = variant dir path
   - `parent_project_id` = parent's `project_id`
   - `variant_label` = voice-id string
   - `voice_id` = `--voice` value
   - `storyboard_path`, `script_path`, `knowledge_path` → paths inside variant dir
   - `audio/` fields reset: `narration_path = None`, `segment_timings = None`, `subtitle_path = None`
   - `compose/` fields reset: `final_video_path = None`
   - YouTube upload fields reset: `youtube_video_id = None`, `thumbnail_uploaded = None`, `disclosure_set = None`, `published_at = None`
7. Run TTS + compose stages (equivalent to `produce --project-id <variant-id> --start-from tts`)
8. On success, print the soft prompt (see below)

#### `pipeline compose promote-voice`

```
uv run pipeline compose promote-voice --from-project <variant-dir-name>
```

`--from-project` here accepts the variant directory name as a string
(e.g. `1776997800_tim-zhtw-fish`), not the numeric project ID. The CLI
resolves it to `output/projects/{variant-dir-name}/`.

Steps:
1. Read variant's `context.json` → get `parent_project_id`
2. Resolve parent work_dir = `output/projects/{parent_project_id}/`
3. Copy from variant → parent:
   - `audio/` directory (all files)
   - `compose/scenes/*.mp4` (all rendered scene files)
   - SRT file (from `ctx.subtitle_path`)
4. Update parent's `context.json`:
   - `voice_id` = variant's `voice_id`
   - `segment_timings` = variant's `segment_timings`
   - `subtitle_path` = new path inside parent dir
   - `narration_path` = new path inside parent dir
5. Run `compose reburn` on parent (re-concatenates scene files + burns subtitles)
6. Print confirmation with output path
7. Offer to delete the variant: "Delete variant directory? [y/N]"

### Soft prompt (printed after `voice-variant` render completes)

```
Voice variant ready:
  output/projects/1776997800_tim-zhtw-fish/compose/final_zh-TW_subtitles_no_overlay.mp4

Make tim-zhtw-fish the permanent voice for project 1776997800?
  [P] Promote  — copy audio to original, reburn (fast, no scene re-render)
  [D] Delete   — discard this variant, keep original as-is
  [K] Keep both — decide later
```

If the user types K, presses Enter, or Ctrl-C, the command exits cleanly.
Both projects remain on disk. The original stays the default for publish.
The prompt does not repeat — it is only shown once, at render-complete time.

---

## Schema Changes

Two new optional fields on `PipelineContext` (`src/pipeline/stages/base.py`):

```python
parent_project_id: int | None = None
variant_label: str | None = None
```

Both default to `None`. No existing code paths are affected. Regular projects
never set these fields. Variant projects always have both set.

---

## Skill: `voice-variant`

Location: `.claude/skills/voice-variant.md`

Triggers: user says "build a voice variant", "try X voice on project Y",
"make a tim-zhtw-fish version of project Z".

Workflow (mirrors scene-update autonomy contract):

1. Resolve `--from-project` and `--voice` from conversation context
2. Check variant dir doesn't already exist; warn user if it does
3. Run `pipeline compose voice-variant --from-project <ID> --voice <voice-id>`
4. After render, show the soft prompt and wait for user choice
5. Act on choice immediately — no further confirmation:
   - P → run `pipeline compose promote-voice --from-project <variant-dir-name>`,
     then ask once whether to delete the variant
   - D → `rm -rf output/projects/<variant-dir-name>/`
   - K → exit, remind user of the promote command for later

Gates where the skill pauses for human input:
1. Showing the soft prompt (P / D / K)
2. "Delete variant?" after promote (ask once, then act)
3. Unexpected failure

---

## File Locations

| Artifact | Path |
|---|---|
| CLI command | `src/pipeline/cli_compose.py` — two new `@compose_app.command()` functions |
| Schema fields | `src/pipeline/stages/base.py` — `PipelineContext` dataclass |
| Skill | `.claude/skills/voice-variant.md` |
| Tests | `tests/unit/test_voice_variant.py` |

---

## Test Cases

- `voice-variant` creates correct directory structure and context.json fields
- `voice-variant --force` overwrites an existing variant directory
- `promote-voice` copies correct files and updates parent context.json
- `promote-voice` on a project without `parent_project_id` raises a clear error
- Variant dir already exists without `--force` → exits with clear error message
- `parent_project_id` and `variant_label` round-trip through JSON serialization

---

## Out of Scope

- Multiple variants of the same voice (re-running `voice-variant` with the same
  voice on the same parent is an error unless `--force` is passed)
- Variant-of-variant (promoting a variant makes the parent canonical again; no
  nested variant chains)
- Dashboard UI changes (variants appear as separate project entries naturally)
