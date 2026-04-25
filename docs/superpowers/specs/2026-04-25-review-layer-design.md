# Review Layer: Proofreader Fix + Storyteller Agent

**Date:** 2026-04-25
**Status:** Approved

## Problem

The pipeline's review layer has two gaps:

1. **Proofreader hallucinates** — when no scenes have overlay text, Claude Haiku invents "missing overlay" findings because the system prompt ranks OVERLAY as most important. All 5 findings on the first real run were false positives; `--apply` would have silently no-op'd.

2. **No narrative-level review** — the proofreader checks sentence-level grammar and text quality. Nobody checks whether topic transitions between scenes are smooth, whether payoffs arrive before premises, or whether scenes redundantly restate the same idea.

## Change 1: Proofreader Fix

**File:** `src/pipeline/cli_proofread.py`

### What changes

`_format_for_review` detects whether any scenes contain overlay text. It passes this context to the model:

- **No overlays present:** appends `（本腳本無 OVERLAY 文字，請只審閱 NARRATION）` to the user message.
- **Overlays present:** no change to current behaviour.

The system prompt softens the OVERLAY priority line from "OVERLAY 標題（最重要）" to "如有 OVERLAY，審閱標題語法" so the model does not invent overlay findings when none exist in the input.

No changes to function signatures, apply logic, or CLI interface.

## Change 2: Storyteller Agent

### New file: `src/pipeline/cli_storyteller.py`

Registered as the `pipeline storytell` sub-app (same pattern as `pipeline proofread`).

### Scope

Checks narrative structure only — not grammar, not text quality (those belong to the proofreader):

- **Abrupt topic jumps** — scene N ends on concept X, scene N+1 opens mid-thought on concept Y with no bridge
- **Missing setup before payoff** — punchline or conclusion arrives before the premise is established
- **Redundant restatement** — the same idea stated twice in consecutive scenes without adding depth

### Model

Claude Haiku (`claude-haiku-4-5-20251001`) — budget-consistent with the proofreader.

### Output format

The model returns one line per issue:

```
ISSUE|scene_id|MINOR|original_sentence|suggested_replacement|reason
ISSUE|scene_id|MAJOR|original_sentence|suggested_replacement|reason
```

The model classifies severity. System prompt guidance:

- **MINOR** — add or tweak a bridge sentence that doesn't change what the scene says; safe to auto-apply
- **MAJOR** — suggestion reorders ideas, changes the hook, or shifts the audience's interpretation of a scene; requires human confirmation

If no issues: model returns `OK`.

### Apply behaviour

| Flag | MINOR | MAJOR |
|---|---|---|
| *(no flag)* | display only | display only |
| `--apply` | auto-applied silently | prints suggestion, prompts `Apply? [y/N]` per issue |

### CLI

```bash
pipeline storytell run --project-id X           # show issues, no changes
pipeline storytell run --project-id X --apply   # auto MINOR, confirm MAJOR
```

### Review gate integration

After the existing proofread step at the review gate, storyteller runs automatically with `--apply`. The gate already pauses for human input, so MAJOR confirmations fit naturally into that flow.

### Registration

`cli_storyteller.py` exports `storytell_app` (a `typer.Typer`). `cli.py` registers it:

```python
app.add_typer(storytell_app, name="storytell")
```

## File list

| File | Change |
|---|---|
| `src/pipeline/cli_proofread.py` | fix hallucination (prompt + input format) |
| `src/pipeline/cli_storyteller.py` | new — storyteller agent |
| `src/pipeline/cli.py` | register `storytell_app` |
| `src/pipeline/cli.py` (review gate at line ~144 and ~174) | wire storyteller after existing proofread block |
| `tests/unit/test_cli_storyteller.py` | unit tests for parse + apply logic |
| `tests/unit/test_cli_proofread.py` | add regression test for no-overlay case |
