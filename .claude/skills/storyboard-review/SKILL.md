---
name: storyboard-review
description: Gate between storyboard generation (Phase 3) and TTS (Phase 4) in /produce. Dispatches the storyboard-critic subagent, auto-applies rewrite/cut/merge demands to storyboard.json, and loops until the critic issues PASS. Pauses only for acquire demands (assets that don't exist yet). Use when Phase 3 is complete and the user is about to proceed to TTS, or when asked to review/critique the current storyboard.
version: 1.0.0
---

# Storyboard Review — Editor gate before TTS

This skill runs between Phase 3 (storyboard written) and Phase 4 (TTS) in the `/produce` workflow. It dispatches the storyboard-critic subagent, reads its scene-level verdict, auto-applies fixable demands directly to storyboard.json, and loops. The only thing that stops the loop is an `acquire` demand (an asset that doesn't exist yet) or a PASS verdict.

## When this runs vs. the video-pitch skill

- **video-pitch** (know-fountains) — gates the *explainer*: "does the raw material exist for a real video?"
- **storyboard-review** (content-creation, this) — gates the *storyboard*: "did the storyboard use that material, or collapse it into text?"

## The loop

```
dispatch critic
  ↓
parse verdict
  ↓
PASS → done
  ↓
REWORK/RETHINK
  ↓
separate: auto-demands (rewrite/cut/merge) vs. blocking-demands (acquire)
  ↓
apply auto-demands to storyboard.json → re-derive script → write review to memory
  ↓
any blocking-demands? → pause, tell user what assets are needed → wait for confirmation
  ↓
loop (max 5 iterations before asking user to intervene)
```

---

## Step 1 — Locate the project

Confirm the project ID and find:
- `output/projects/<ID>/storyboard.json`
- `output/projects/<ID>/source/explainer.md`

Determine the current loop number:
```bash
grep -c "^## Loop" .agent-memory/storyboard-critic/reviews/<ID>.md 2>/dev/null || echo 0
```

---

## Step 2 — Load memory

Read these files to feed into the critic:

```bash
cat /home/tim-huang/content-creation/.agent-memory/storyboard-critic/standards.md
cat /home/tim-huang/content-creation/.agent-memory/storyboard-critic/reviews/<ID>.md 2>/dev/null || echo "none — first review"
```

---

## Step 3 — Read the agent persona

```bash
cat /home/tim-huang/content-creation/.claude/agents/storyboard-critic.md
```

Strip the YAML frontmatter (lines from `---` to the second `---`). The body is the persona.

---

## Step 4 — Build the task prompt

Concatenate:
1. The persona body
2. A `STANDING STANDARDS` section = standards.md contents
3. A `PRIOR REVIEWS (this project)` section = reviews/<ID>.md contents, or "none — first review"
4. The task:

```
This is loop <N>. Re-review from scratch AND verify whether prior demands were addressed.
Storyboard path: /home/tim-huang/content-creation/output/projects/<ID>/storyboard.json
Explainer path: /home/tim-huang/content-creation/output/projects/<ID>/source/explainer.md

Read both files and the asset directory referenced in required_images before judging.
Return your verdict as a single JSON block with patch fields for all rewrite/merge demands.
```

---

## Step 5 — Dispatch the storyboard-critic

Dispatch as a **general-purpose (opus) subagent** using the Agent tool. Tools available to the critic: Read, Glob, Grep, Bash. The task_prompt is the full concatenated prompt from Step 4.

The critic will read the storyboard.json, video_brief, and asset directories, then return a single JSON block.

---

## Step 6 — Parse the verdict

Extract the JSON block from the critic's response. Parse:
- `decision`: PASS | REWORK | RETHINK
- `demands`: array of `{scene_id, kind, fix, patch, merge_removes, why}`

If the JSON block is missing or malformed, ask the critic to re-run.

---

## Step 7 — Write the review to agent memory

Append this loop's verdict to `.agent-memory/storyboard-critic/reviews/<ID>.md`:

```markdown
## Loop <N> — <YYYY-MM-DD> — <decision>

**Arc read:** <first_pass_arc>

**Verdict:** <verdict_summary>

**Dimensions:**
- Messaging: <messaging>
- Structure: <structure>
- Pacing: <pacing>
- Visual coverage: <visual_coverage>

**Demands:**
<for each demand: - [scene_id] (kind) fix — why>

**Greenpass terms:** <greenpass_terms or "n/a">
```

---

## Step 8 — Act on the verdict

### If PASS

Tell the user: "Storyboard cleared by the editor (loop N). Greenpass terms: <terms>. Proceed to Phase 4 (fit-image → TTS → compose)."
Done.

---

### If REWORK or RETHINK

**Separate demands by kind:**

- **Auto-applicable**: `rewrite`, `cut`, `merge` — apply directly to storyboard.json
- **Blocking**: `acquire` — asset doesn't exist; cannot proceed until the user resolves it

**Apply auto-demands now:**

Read storyboard.json, apply each auto-demand, write back:

```python
import json
from pathlib import Path

proj = Path('output/projects/<ID>')
data = json.loads((proj / 'storyboard.json').read_text())
scenes = data['scenes']
removed_ids = set()   # every scene id removed by cut/merge — needed to keep transitions[] consistent

for demand in auto_demands:
    sid = demand['scene_id']
    kind = demand['kind']
    patch = demand.get('patch')

    if kind == 'cut':
        scenes = [s for s in scenes if s['id'] != sid]
        removed_ids.add(sid)

    elif kind == 'rewrite' and patch:
        for s in scenes:
            if s['id'] == sid:
                for k, v in patch.items():
                    s[k] = v
                break

    elif kind == 'merge' and patch:
        merge_removes = demand.get('merge_removes', [])
        remove_set = set(merge_removes)
        for s in scenes:
            if s['id'] == sid:
                for k, v in patch.items():
                    s[k] = v
                break
        scenes = [s for s in scenes if s['id'] not in remove_set]
        removed_ids |= remove_set


def reconcile_transitions(data, scenes, removed_ids):
    """Keep the top-level transitions[] array consistent with scenes[] after cut/merge.

    cut/merge edit only the scene list, so transitions can still reference a removed
    scene id. The main compose seam-lookup (by_seam.get((scene_id, next_id))) silently
    ignores dangling entries, BUT consumers that iterate transitions directly break —
    e.g. animation_review resolves transition.from_scene to a scene clip that no longer
    exists. So: drop every transition touching a removed scene, then bridge each gap
    with a straight cut (style:none) between the removed scene's surviving neighbours
    (following chains through consecutively-removed scenes). This is exactly the s46
    orphan that loop 1's s45+s46 merge left behind and a human had to fix by hand.
    """
    if not removed_ids:
        return
    transitions = data.get('transitions') or []
    final_ids = [s['id'] for s in scenes]
    adj_set = set(zip(final_ids, final_ids[1:]))             # surviving adjacent seams
    inbound  = {t['to']:   t['from'] for t in transitions if t['to']   in removed_ids}
    outbound = {t['from']: t['to']   for t in transitions if t['from'] in removed_ids}
    kept = [t for t in transitions
            if t['from'] not in removed_ids and t['to'] not in removed_ids]
    kept_seams = {(t['from'], t['to']) for t in kept}

    def survive_back(x):
        g = set()
        while x in removed_ids and x not in g:
            g.add(x); x = inbound.get(x)
        return x

    def survive_fwd(x):
        g = set()
        while x in removed_ids and x not in g:
            g.add(x); x = outbound.get(x)
        return x

    bridges = {}
    for r in removed_ids:
        a, b = survive_back(inbound.get(r)), survive_fwd(outbound.get(r))
        if (a and b and a not in removed_ids and b not in removed_ids
                and (a, b) in adj_set and (a, b) not in kept_seams):
            bridges[(a, b)] = {'from': a, 'to': b, 'style': 'none', 'duration_sec': 0.0}
    data['transitions'] = kept + list(bridges.values())


reconcile_transitions(data, scenes, removed_ids)

data['scenes'] = scenes
(proj / 'storyboard.json').write_text(
    json.dumps(data, ensure_ascii=False, indent=2)
)
print(f"Applied {len(auto_demands)} fixes. Scenes remaining: {len(scenes)}. "
      f"Removed: {sorted(removed_ids) or 'none'}.")
```

> **Why the transitions reconciliation matters:** `cut`/`merge` demands only touch
> `scenes[]`. Without `reconcile_transitions`, the `transitions[]` array keeps dangling
> references to removed scene ids — invisible to the main compose seam-lookup but fatal
> to `animation_review` (which iterates transitions and resolves each `from_scene` to a
> clip). Loop 1's s45+s46 merge left exactly this orphan, and it had to be repaired by
> hand. This function is verified against single-cut, merge-removal, and
> consecutive-removal-chain scenarios.

**Re-derive the script after changes:**

```bash
cd /home/tim-huang/content-creation
uv run python3 -c "
from pipeline.storyboard import Storyboard; from pathlib import Path; import json
sb = Storyboard.from_dict(json.loads(Path('output/projects/<ID>/storyboard.json').read_text()))
script = sb.derive_script()
Path('output/projects/<ID>/script/script_zh-TW.md').write_text(script, encoding='utf-8')
print(f'{len(sb.scenes)} scenes after edits')
"
```

**Report what was done:**

Show the user a compact summary:
```
Auto-applied N fixes:
  ✓ s25 [rewrite] → article_image + overlay (map with BANNED/STILL SOLD)
  ✓ s21 [cut] → removed (filler)
  ✓ s41+s42 [merge] → s41 article_image (combined)
```

**Handle blocking (acquire) demands:**

If any acquire demands exist, pause:
```
⚠ Waiting for assets before next loop:
  • s20 [acquire] — bar chart not yet authored: two bars, Recorded 230,676 vs
    Estimated (taller, ?, iceberg reveal). Author via chart tool then re-run.
  • s40 [acquire] — stationary activity center image needed. Ingest or generate.
```

Wait for the user to resolve them, then proceed to loop N+1.

**If no blocking demands** — loop automatically (go back to Step 2 with loop N+1).

**Safety limit:** After 5 loops with unresolved demands, stop and ask the user to intervene:
```
Reached 5 loops without PASS. Remaining demands: [list]. Please review storyboard.json 
manually or override.
```

---

## Override

The user may say "proceed anyway." Record the override:
```bash
echo "## Override — <YYYY-MM-DD>\nUser overrode storyboard-critic gate at loop <N>. Unresolved demands: [list]." \
  >> .agent-memory/storyboard-critic/reviews/<ID>.md
```
Then proceed to Phase 4.

---

## Editing scene visuals manually (if needed)

For complex changes the loop can't auto-apply, use direct JSON editing:

```bash
# After editing storyboard.json manually, re-derive script:
cd /home/tim-huang/content-creation
uv run python3 -c "
from pipeline.storyboard import Storyboard; from pathlib import Path; import json
sb = Storyboard.from_dict(json.loads(Path('output/projects/<ID>/storyboard.json').read_text()))
script = sb.derive_script()
Path('output/projects/<ID>/script/script_zh-TW.md').write_text(script, encoding='utf-8')
print(f'{len(sb.scenes)} scenes')
"
```

Note: the `pipeline storyboard set` CLI is intentionally restricted to safe fields (narration, pause_after_sec, section, style_modifier). Use direct JSON edit for visual.type, visual.path, overlay, and chart_spec changes.
