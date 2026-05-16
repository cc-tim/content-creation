# MLA Resilience — Make English Track Adapt Efficiently When Storyboard Changes

**Status:** Phase 1 applied 2026-05-16 (uncommitted). Phases 2–4 designed; implement in a follow-up session.

**Problem context:** During the baby-walker storyboard restructure (38 → 40 scenes, 5 scenes rewritten, 2 new), the MLA gate failed twice. Run 1: EN overshot zh-TW by 3.13s. Run 2 (after trimming EN): zh-TW overshot EN by 6.49s — Fish Audio non-determinism on unchanged zh-TW text contributed ~5.9s. The hard ±2s gate, the lack of a targeted EN-only repair path, and the lack of length-budgeted EN-alt authoring combined to force a full TTS+compose re-run for each manual trim. End-to-end this cost 3 full render cycles and ultimately required disabling MLA to ship.

This plan addresses three independent failure surfaces so a future "add scene / rewrite scene" never triggers this cascade again.

---

## Phase 1 — Adaptive MLA drift gate (APPLIED 2026-05-16)

**Status:** Code is in tree, uncommitted on `master`.

### What changed

- `src/pipeline/stages/tts.py`:
  - New `compute_mla_tolerance_ms(total_primary_ms, override_ms=None) -> int` returns `max(2000, int(total_primary_ms * 0.015))` by default. Override short-circuits the default when positive.
  - `_check_secondary_durations` now accepts `tolerance_ms_override`, calls `compute_mla_tolerance_ms`, and includes a remediation hint in the failure message (`pipeline mla rebalance ...` / `--allow-mla-drift`).
- `src/pipeline/stages/base.py`: `PipelineContext.mla_drift_tolerance_ms: int | None = None` added in the MLA block.
- `src/pipeline/cli.py`: `produce --allow-mla-drift <seconds>` flag; on resume it patches `ctx.mla_drift_tolerance_ms`, on fresh runs it threads into the `PipelineContext(...)` constructor.

### Tolerance table

| Total primary | Tolerance | Old hard ±2s |
|---|---|---|
| 2 min (120s) | 2.0s (floor) | 2.0s |
| 5 min (300s) | 4.5s | 2.0s |
| 7 min (420s) | 6.3s | 2.0s |
| 10 min (600s) | 9.0s | 2.0s |
| 12 min (720s) | 10.8s | 2.0s |

Per-scene `ratio > 1.15` warning is unchanged — still useful as an early hint without forcing a hard fail.

### What remains in Phase 1

- Unit test for `compute_mla_tolerance_ms` in `tests/pipeline/test_tts.py` (or similar). Cover: floor, scaling, override-when-positive, override-zero-ignored.
- Add `--allow-mla-drift` to README.md "Pipeline Commands" section under MLA.

---

## Phase 2 — `pipeline mla rebalance` command

**Status:** Not started. Full design below.

### Goal

When MLA gate fails (or operator wants to tighten alignment proactively), provide a focused command that retargets only the secondary (EN) narration to match primary durations, without touching zh-TW or compose.

### CLI surface

```
pipeline mla rebalance [--work-dir <path> | --project-id <id>]
                       [--max-iterations 3] [--apply]
                       [--per-scene-target-ratio 0.95]
                       [--secondary-locale en]
```

- `--work-dir` or `--project-id`: project selector (mirrors `pipeline proofread run`)
- `--max-iterations`: cap on Haiku→re-synth→check loop iterations. Default 3.
- `--apply`: without it, dry-run mode shows proposed rewrites + projected drift; with it, writes storyboard + re-synths
- `--per-scene-target-ratio`: how aggressively to undershoot primary per scene. Default 0.95 = aim for 95% of primary_ms per offending scene (5% safety margin).
- `--secondary-locale`: which `narration_alt[locale]` to rebalance. Default reads from `ctx.secondary_locale`.

### Algorithm

```
1. Load ctx + storyboard.
   Require ctx.segment_timings present (project must have run TTS at least once).
   Require ctx.secondary_locale set OR --secondary-locale provided.

2. Resolve the secondary voice engine the same way TtsStage._run_secondary_tts does
   (ctx.secondary_voice_id || registry.default_for_locale(secondary_locale)).

3. Synthesize a "current state" secondary pass (uses existing _synthesize_pass).
   This gives us sec_timings with current EN audio durations per scene.
   Caching: see Phase 3 — for now, every call re-synthesizes. The cost is ~1s/scene
   for cached-hash text on Fish Audio. Acceptable.

4. Identify offending scenes:
   - Per-scene: secondary_ms > primary_ms × 1.15 (overshoot) OR
                secondary_ms < primary_ms × 0.85 (undershoot, only flag if drift
                also exceeds tolerance)
   - Total drift: abs(sum(secondary) - sum(primary)) > tolerance (using
     compute_mla_tolerance_ms from Phase 1)

5. If no offenders AND drift under tolerance → print "already balanced" and exit 0.

6. Build a single batched Haiku request listing all offending scenes:
   - For each offender: zh-TW narration, current EN text, target word budget
   - Target word budget per scene =
        max(3, round(current_en_words × (primary_ms × ratio / current_secondary_ms)))
     This auto-calibrates to each scene's actual TTS speech rate rather than
     assuming a global words/sec constant.

7. Parse Haiku response (one rewrite per scene). Validate:
   - Word count is within ±2 of target_words (Haiku tends to overshoot by 1-3 words)
   - No factual changes vs current (numbers, dates, proper nouns must appear verbatim
     in original OR be present in zh-TW reference)

8. Dry-run (no --apply):
   - Print proposed table (scene_id, current_words → new_words, current_ms → projected_ms)
   - Estimate new total drift (linear extrapolation from word ratio); print
   - Do NOT modify storyboard, do NOT re-synth. Exit.

9. Apply mode (--apply):
   a. Update storyboard.scenes[i].narration_alt[secondary_locale] for each offender.
      Save storyboard.json.
   b. Re-synthesize secondary pass (call _synthesize_pass with the updated EN texts).
      Cache hits will happen at the file-write layer for unchanged segments — see
      Phase 3 for proper hash-based caching that survives re-runs.
   c. Update ctx.secondary_narration_path and ctx.secondary_subtitle_path.
      Save ctx.
   d. Run _check_secondary_durations with the new sec_timings and ctx tolerance.
   e. If pass → exit 0. If still fail and iteration < max_iterations →
      recurse from step 4 (re-identify offenders, ask Haiku again). Each
      iteration uses a tighter target_ratio (e.g. 0.95, 0.90, 0.85).
   f. If hit max_iterations and still failing → print the residual drift and exit 1;
      surface the offenders that didn't converge so the operator can hand-edit.
```

### Haiku prompt sketch

```
SYSTEM:
You rewrite English narration for educational documentary TTS to match a target
word budget. Constraints:
- Preserve the exact meaning of the zh-TW reference. Names, numbers, dates verbatim.
- Maintain documentary register: declarative, even pacing, no rhetorical flourish.
- Hit the target word count within ±2. Prefer fewer words to more.
- Output ONLY the rewritten EN text, prefixed with the scene id and a pipe.

OUTPUT FORMAT (one line per scene, no other text):
s7|<rewritten EN>
s38|<rewritten EN>

USER:
Rewrite the following scenes:

[s7] zh-TW reference: 要再等六十年。一九六零、七零年代...
     current EN (46 words): Another sixty years. In the 1960s and 70s...
     target words: 26 (5% safety margin under primary duration)

[s38] zh-TW reference: 規則其實非常簡單...
     current EN (15 words, but ran long at 10.25s): The rule is simple. One line:...
     target words: 12
```

### File layout

```
src/pipeline/cli_mla.py            # new — mla_app typer namespace
src/pipeline/cli.py                # register: app.add_typer(mla_app, name="mla")
tests/pipeline/test_cli_mla.py     # new — covers word-budget math + offender ID
```

### Integration points / reused code

- `pipeline.stages.tts._synthesize_pass` — synthesis loop with file caching by segment_NNN path
- `pipeline.stages.tts.compute_mla_tolerance_ms` — Phase 1
- `pipeline.stages.tts._check_secondary_durations` — Phase 1
- `pipeline.voices.registry.VoiceRegistry.{resolve,default_for_locale}` — engine resolution
- `pipeline.cli_proofread._get_api_key` — Anthropic key resolution (extract to shared util)
- `pipeline.storyboard.Storyboard.{load,save}` — storyboard I/O

### Edge cases to handle

- Scene has no EN alt at all (skipped in `_synthesize_pass`): excluded from offender list. Print a warning at end if any skipped scenes contribute to drift gap.
- All offenders are undershoots (sec total < primary total): Haiku rewrites with padding instruction ("expand to ~N words while preserving meaning, allowed: examples, qualifiers, restated nouns").
- Storyboard.json was edited between sessions and segment_timings is stale (timings reference scene IDs that no longer exist): error out with hint to re-run TTS first.
- Voice engine for secondary locale unavailable / API key missing: error early before any work.
- No `--secondary-locale` and `ctx.secondary_locale` is None: error early.

---

## Phase 3 — Persisted per-scene durations (optional, raises ceiling)

**Status:** Not started. Lighter than Phase 2 but lower priority.

### Problem

Fish Audio (and other TTS engines) regenerate audio between runs for unchanged text, producing slightly different durations each time. The MLA gate sees this as drift even when nothing changed. Phase 1's adaptive tolerance covers most of it but isn't a real fix.

### Design

Persist measured duration in storyboard after every successful TTS:

```python
# pipeline/storyboard.py — Scene dataclass
@dataclass
class Scene:
    ...
    narration_durations_ms: dict[str, int] = field(default_factory=dict)
    # keyed by locale: {"zh-TW": 11337, "en": 13080}
    narration_text_hashes: dict[str, str] = field(default_factory=dict)
    # SHA1 of narration text per locale at the time durations were measured.
    # On reload: if current text hash differs, drop the duration entry.
```

After TTS:
```python
# In TtsStage.run, after primary synthesis:
for scene_idx, scene in enumerate(storyboard.scenes):
    timing = segment_timings[scene_idx]
    if timing.get("duration_ms"):
        scene.narration_durations_ms[ctx.locale] = timing["duration_ms"]
        scene.narration_text_hashes[ctx.locale] = hashlib.sha1(
            scene.narration.encode()
        ).hexdigest()[:12]
# Same for secondary, but reading scene.narration_alt[sec_locale]
storyboard.save(ctx.storyboard_path)
```

On reload (`Storyboard.from_dict`): for each locale entry in `narration_text_hashes`, verify the current text still hashes to the stored value. If not, drop the matching entry from `narration_durations_ms`. This keeps stale durations from being used.

Gate update: if both primary and secondary scenes have persisted, in-sync durations, prefer those over the just-synthesized values. This means the gate is comparing **canonical** durations rather than this-run-of-Fish-Audio durations — engine noise drops out entirely.

This also lets `pipeline mla rebalance` make decisions based on persisted durations without re-synthesizing first, cutting one iteration's worth of synth time.

### Estimated cost

- Scene model + storyboard model: 30 LOC
- TTS stage write-back: 20 LOC
- Gate update to prefer persisted: 15 LOC
- Migration: existing storyboards naturally backfill on first TTS post-deploy. No explicit migration step.

---

## Phase 4 — Upstream length constraints (prevention)

**Status:** Not started.

Three writers create EN alts today; each needs an explicit length-target instruction so the problem doesn't occur in the first place.

### 4a. DirectStage prompt

`src/pipeline/stages/direct.py` already has the talking-points/proportional-dwell block. Add a separate "MLA discipline" block near the JSON schema spec:

```
MLA / NARRATION_ALT.EN GUIDELINES:
When the project has MLA enabled (this is the case unless told otherwise), every
scene needs a narration_alt.en that will be synthesized to TTS audio aligned with
the zh-TW primary track. The English TTS audio for a scene must fit within ±10%
of the zh-TW audio duration.

Practical rule: Mandarin packs ~1.4× the info per character that English packs
per word. Estimate: English word count ≈ zh-TW char count × 0.55.

For each scene's narration_alt.en:
- Target word count = round(zh-TW char count × 0.55)
- If meaning requires more words, compress: drop articles, use shorter synonyms,
  cut hedges. Keep names/numbers/dates intact.
- NEVER exceed: english_word_count > zh-TW_char_count × 0.75 (this is the
  threshold above which the audio is statistically guaranteed to overshoot).
- If the line includes a verbatim English quote (proofread `verbatim: true` facts),
  exempt that quote's word count from the budget — record it separately.

Example:
  zh-TW (45 chars): 一九零一年，第一次有人試著把它變成大眾商品。加拿大旅館老闆湯瑪斯·斯隆...
  Target EN words: 25 (45 × 0.55)
  Good EN: "1901, the first attempt to commercialize it: Canadian hotelier Thomas Sloan ran an ad..." (~18 words)
  Bad EN: "In the year 1901, this was the first time someone tried to make it into..." (~30 words; will overshoot)
```

### 4b. scene-update skill

`.claude/skills/scene-update/SKILL.md` (project skill) — add a step after the wording-enhancement block:

```
## After approving zh-TW changes that have an EN alt

If the scene has a `narration_alt.en` entry, regenerate it with the length budget:
- zh-TW char count × 0.55 = target EN words
- Maintain meaning, drop articles/hedges as needed to fit
- Quote-verbatim segments (from facts marked `verbatim: true`) are exempt from the
  budget — record their word count separately and add to the budget

After this step, the regular TTS+compose chain handles the rest. No need to manually
run mla rebalance unless you batch-edited several scenes and want to verify.
```

### 4c. Manual restructure convention

Codify in `docs/workflows.md` (and link from CLAUDE.md) under a new "MLA discipline" section: any code path that writes a new `narration_alt.en` must compute the length budget. If a human is hand-editing the storyboard, point them at `pipeline mla rebalance --dry-run` to preview drift before committing the edit.

---

## Sequencing & dependencies

```
Phase 1 (adaptive gate)           ← APPLIED, just needs tests + README note
  └─ Phase 2 (mla rebalance)      ← Main automation win. Reuses Phase 1's compute_mla_tolerance_ms.
       └─ Phase 3 (persisted)     ← Optimization: skips a synth pass in Phase 2 per iteration.
Phase 4 (prompts)                 ← Independent. Reduces but doesn't eliminate need for Phase 2.
```

Recommended order for the follow-up session:
1. Phase 1 finish: tests + README. (~30 min)
2. Phase 2: `pipeline mla rebalance` with `--apply` and `--max-iterations`. (~4-6 hours including tests)
3. Phase 4: prompt updates. (~30 min)
4. Phase 3: persisted durations. (~2 hours)

Phases 2 and 4 are the two changes that directly answer the user's question ("if future this happen again — ex. add scene — the English track could efficiently do changes needed accordingly"). Phase 4 prevents the problem upstream; Phase 2 fixes it cheaply when prevention fails.

---

## Acceptance criteria for the work-as-a-whole

Run the same baby-walker restructure scenario from scratch (add a scene, rewrite three):

1. With Phase 4 in place: the initial render passes the MLA gate without manual intervention. Per-scene ratios stay under 1.15 for the new scenes.
2. Without Phase 4 (deliberately break it by writing a long EN alt): `pipeline mla rebalance --apply` resolves the drift in ≤ 3 iterations, takes < 30s wall clock (vs the current ~3 full TTS+compose cycles ≈ 15 min), and produces a `secondary_narration_path` that passes the gate.
3. The pre-existing `--allow-mla-drift 30` escape hatch works for one-off renders where MLA correction can be deferred.
