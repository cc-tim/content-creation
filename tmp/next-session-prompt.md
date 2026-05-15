Execute the implementation plan at `docs/superpowers/plans/2026-05-15-dashboard-outline-locale.md`.

Use the `superpowers:subagent-driven-development` skill — dispatch a fresh subagent
per task, review between tasks. The plan is 11 tasks across 3 phases; Tasks 8–11
are the remaining work (Phase C — Dashboard).

## Progress so far (completed this session)

**HEAD:** `d1df0fc`

Phase A — complete:
- ✅ Task 1: `Scene.beat`, `Scene.narration_alt`, `Scene.narration_for()` — `src/pipeline/storyboard.py`
- ✅ Task 2: `Storyboard.primary_locale`, `title_alt`, `description_alt`, locale-aware `derive_script(locale=None)` — `src/pipeline/storyboard.py`
- ✅ Task 3: `migrate_storyboard_file()` + `pipeline storyboard migrate` CLI — `src/pipeline/cli_storyboard.py`
- ✅ Task 3b: `backfill_beats_file()` + `_generate_beats()` + `--backfill-beats` flag — `src/pipeline/cli_storyboard.py`
  - Baby-walker project (`20260504-115232-baby-walker-story`) migrated + beats backfilled; storyboard.json committed

Phase B — complete:
- ✅ Task 4: `DirectStage` updated to emit beats skeleton (no narration), inject empty `narration`, add `primary_locale`, remove script derivation, update `story_structure` and synopsis to use beats — `src/pipeline/stages/direct.py`
- ✅ Task 5: New `ScriptwriteStage` — beat-driven per-locale narration stage — `src/pipeline/stages/scriptwrite.py`
  - `build_scriptwrite_prompt`, `_write_narration_for_locale`, `ScriptwriteStage`
  - Missing-scene warning, JSON error handling, explicit locale in `derive_script()`
- ✅ Task 6: `ScriptwriteStage` wired into produce chain — `src/pipeline/cli.py`
  - Order: acquire → analyze → direct → scriptwrite → tts → compose
  - `pre_review = {"acquire", "analyze", "direct", "scriptwrite"}`
- ✅ Task 7: TTS + verifier read `narration_alt` — `src/pipeline/stages/tts.py`, `src/pipeline/verifier.py`
  - `tts.py:136`: log key renamed to `"tts.secondary.missing_narration"` (locale-generic)
  - `verifier.py:75`: reads `narration_alt` dict values instead of `narration_en`
  - Test files updated; all 930 tests pass

**Remaining tasks (start from Task 8):**

- [ ] Task 8: Scanner exposes beat, locale map, locales, primary_locale — `src/pipeline/dashboard/scanner.py`
- [ ] Task 9: Outline view panel — `src/pipeline/dashboard/static/index.html`
- [ ] Task 10: Locale switcher + audio-swap preview — `src/pipeline/dashboard/static/index.html`
- [ ] Task 11: Locale-aware narration edits in mutation runtime — `src/pipeline/dashboard/mutation_runtime.py`

## Key context

- **Design constraint:** `scene.narration` stays `str` (primary locale). Secondary locales in `narration_alt: dict[str, str]`. ~15 call sites read `scene.narration` as string — do NOT collapse into a dict.
- **Tasks 9 and 10** are dashboard JS with manual in-browser verification (`https://dashboard.keeppro.io`). If unreachable, say so explicitly.
- **Final step:** `docs/workflows.html` needs updating (stage chain changed: added `scriptwrite`). Per `CLAUDE.md`, **ask the user before editing that file**.

## How to start

1. Load the plan: `docs/superpowers/plans/2026-05-15-dashboard-outline-locale.md`
2. Start with Task 8 (Scanner update)
3. Use `superpowers:subagent-driven-development` — dispatch implementer → spec review → code quality review per task
