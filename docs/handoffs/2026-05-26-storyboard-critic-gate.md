# Handoff: storyboard-critic gate — new editor subagent + auto-apply loop

**Date:** 2026-05-26
**Branch:** master (content-creation) / main (know-fountains)
**Last commit (content-creation):** 507231a feat(em): three-mode engineering-manager with lean dispatch + acceptance gate
**Status:** active

## Goal

The video-producer subagent in know-fountains correctly gates *explainers* before production, but the `/produce` pipeline was routinely collapsing rich visual material into text_card/slide scenes at storyboard generation time. The baby-walker storyboard hit 46% text-heavy (22/47 scenes) despite a fully-equipped video_brief. Goal: add a second editor gate that runs *after* Phase 3 (storyboard) and *before* Phase 4 (TTS), auto-applies fixable demands directly to storyboard.json, and loops until the storyboard passes.

## Progress so far

**New files created (content-creation):**

- `.claude/agents/storyboard-critic.md` — the supervising picture editor persona. Reads storyboard.json + video_brief + asset directory; returns per-scene demands with machine-applicable `patch` dicts for rewrite/merge and `null` for cut/acquire.
- `.claude/skills/storyboard-review/SKILL.md` — the loop wrapper skill. Dispatches the critic as a general-purpose (opus) subagent, separates auto-applicable demands (rewrite/cut/merge) from blocking ones (acquire), applies patches directly to storyboard.json, re-derives script, and loops until PASS. Pauses only on `acquire` demands.
- `.agent-memory/storyboard-critic/standards.md` — standing bar accrued from real loops. Grounded in baby-walker failure.
- `.agent-memory/storyboard-critic/reviews/20260504-115232-baby-walker-story.md` — loop 1 review written.

**Modified (content-creation):**

- `.claude/skills/produce/SKILL.md` — added Phase 3.5 block directing the agent to run `storyboard-review` between storyboard generation and TTS.
- `output/projects/20260504-115232-baby-walker-story/storyboard.json` — loop 1 auto-applied: 7 demands, 46 scenes (was 47, s46 removed). Text-heavy rate: 46% → 30%.
- `output/projects/20260504-115232-baby-walker-story/script/script_zh-TW.md` — re-derived after storyboard edits.

**Modified (know-fountains):**

- `.claude/agents/video-producer.md` — fixed broken path reference (`skills/storyboard/SKILL.md` → `.claude/skills/storyboard/SKILL.md`); added note about the new storyboard-critic gate downstream.

**Baby-walker loop 1 result — 7 auto-applied rewrites:**
- s6: Sloan verbatim → article_image (Learning_to_walk.png) + namecard overlay
- s25: Shin verbatim → article_image (north_america_blank_map.png) + namecard overlay
- s29: AAP verbatim → article_image (Baby_by_Vignesh.jpg) + namecard overlay
- s35: "still legal/sold" text_card → article_image (Baby_by_Vignesh.jpg) + text_emphasis
- s37: mechanical-inverse slide → comparison chart
- s44: 3-product summary slide → comparison chart
- s45+s46 merge: rule verbatim → article_image (Baby_Walker.jpg) + namecard; s46 removed

**Key learnings from loop 1:**
- The critic invented `quote_bottom` overlay type which doesn't exist in the renderer. Fall back is `namecard` (`name`=quote, `role`=attribution). This is now documented in `standards.md`.
- The agent schema diverged slightly (used `REVISE`/`stage_critique`/`what` instead of `REWORK`/`dimension_notes`/`fix`) — the demands were still parseable but the JSON didn't match the spec exactly. The skill's Step 6 parse logic needs to be robust to field aliases.

## Next step

**Run loop 2 of storyboard-review on the baby-walker project.** 14 text-heavy scenes remain (30%). The critic explicitly called out s42 and s43 (slides in the closing product section) as the prime candidates. Before dispatching loop 2, check: is the storyboard-critic schema drift (wrong field names in loop 1) worth fixing in the agent file first?

```bash
cd /home/tim-huang/content-creation
# Manually follow storyboard-review SKILL.md starting at Step 2
# (skill not yet registered in new sessions — was created mid-session)
# Loop 2: loop_n=2, load standards + loop1 review, dispatch critic
```

Or just proceed to render the corrected storyboard and validate visually before loop 2:

```bash
cd /home/tim-huang/content-creation
uv run pipeline produce \
  --project-id 20260504-115232-baby-walker-story \
  --locale zh-TW \
  --start-from tts \
  --skip-review
```

## Open questions / pending decisions

- **Schema drift in critic output:** Loop 1 critic used `REVISE` (not `REWORK`), `stage_critique` (not `dimension_notes`), `what` (not `fix`). The auto-apply loop in the skill relies on `kind`/`patch` which were correct. Should the agent file be tightened, or should the skill be more tolerant? (Lean: tighten the agent file — the schema is the contract.)
- **Loop 2 or render first?** The 30% text-heavy is better but still has 7 slides (some defensible as content-type bridges). Running loop 2 may not change much. Could validate by rendering the corrected 46-scene storyboard and watching the output before doing another critic pass.
- **content-creation storyboard-review skill registration:** The skill was created mid-session so it's not in the session's skills registry. It will self-register in the next session from the SKILL.md file. No action needed.
- **know-fountains changes uncommitted:** Several M files in know-fountains (video-producer.md, wiki pages, etc.) — most are from prior sessions, not this session. Only `.claude/agents/video-producer.md` was changed this session.

## Files touched + WIP state

**content-creation (untracked — not yet committed):**
- `.claude/agents/storyboard-critic.md` — complete, ready to commit
- `.claude/skills/storyboard-review/SKILL.md` — complete, ready to commit
- `.agent-memory/storyboard-critic/standards.md` — complete, ready to commit
- `.agent-memory/storyboard-critic/reviews/20260504-115232-baby-walker-story.md` — loop 1 written

**content-creation (modified):**
- `.claude/skills/produce/SKILL.md` — Phase 3.5 gate added, ready to commit
- `output/projects/20260504-115232-baby-walker-story/storyboard.json` — loop 1 applied, 46 scenes
- `output/projects/20260504-115232-baby-walker-story/script/script_zh-TW.md` — re-derived

**know-fountains (modified):**
- `.claude/agents/video-producer.md` — path fix + storyboard-critic cross-reference

## Gotchas / learnings

- **The storyboard-review skill can't be invoked via `Skill` tool in the same session it was created** — the skills registry is loaded at session start. Works fine in any new session.
- **`quote_bottom` overlay type does not exist.** Use `namecard` for quote+attribution overlays. Documented in standards.md.
- **The critic's output JSON schema drifted from spec in loop 1.** Watch for `REVISE`/`RECONSIDER` (producer-schema) vs `REWORK`/`RETHINK` (critic-schema), and `stage_critique` vs `dimension_notes`. The `patch` and `scene_id` fields were correct. If parsing fails, look for field aliases.
- **`refit_path` should not be copied from other scenes.** When a rewrite changes `visual.path` to a different image, don't carry over an existing `refit_path` from another scene — the compose stage uses it as a pre-processed image and it may not match the new asset. Leave `refit_path` absent; fit-image will regenerate.
- **Scene IDs are stable after cuts** — removing s46 doesn't renumber other scenes. The pipeline uses string `id` fields, not array indices.

## How to resume

```bash
# content-creation work
cd /home/tim-huang/content-creation
git status   # confirm untracked new files

# Commit the new subagent and skill
git add .claude/agents/storyboard-critic.md \
        .claude/skills/storyboard-review/ \
        .claude/skills/produce/SKILL.md \
        .agent-memory/storyboard-critic/
git commit -m "feat(storyboard): add storyboard-critic editor gate with auto-apply loop"

# know-fountains: commit video-producer path fix
cd /home/tim-huang/know-fountains
git add .claude/agents/video-producer.md
git commit -m "fix(video-producer): correct storyboard skill path + note storyboard-critic gate"

# Then: decide loop 2 vs render first (see Open questions)
```
