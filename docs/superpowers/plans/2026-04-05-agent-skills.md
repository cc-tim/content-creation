# Agent Skills — Implementation Plan (Plan B1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Claude Code agent skills that let the user interact with the pipeline conversationally — the agent does the creative work (analysis, storyboard generation) directly instead of API calls, at $0 extra cost.

**Architecture:** Each skill is a `.md` file in `.claude/commands/` that instructs Claude Code how to handle the workflow. Skills use existing pipeline utilities (knowledge.py, storyboard.py) to read/write JSON artifacts, and shell commands (yt-dlp, ffprobe) for media operations. The agent performs the AI work (fact extraction, storyboard creation) in-conversation instead of calling the Anthropic API.

**Tech Stack:** Claude Code custom commands (markdown), existing pipeline Python modules (knowledge.py, storyboard.py), yt-dlp, ffprobe, uv

**Spec:** `docs/superpowers/specs/2026-04-05-v2-compose-engine-design.md` (Section 8: Agent Skills)

---

## File Structure

```
.claude/commands/
  evaluate-video.md          # Already exists — no changes
  produce.md                 # Full pipeline: acquire → analyze → direct → review → render
  shorts.md                  # Generate Short storyboards from knowledge base
  knowledge.md               # Show/edit Layer 1 knowledge base
  storyboard.md              # Show/edit/regenerate Layer 2 storyboard
  render.md                  # Compose video from storyboard
  status.md                  # Show project state and artifacts
```

Each skill is a standalone markdown file. No Python code changes needed — skills use existing modules via `uv run python -c "..."` and `uv run pipeline ...` commands.

---

### Task 1: /status skill

**Files:**
- Create: `.claude/commands/status.md`

- [ ] **Step 1: Create the status skill**

```markdown
# Project Status

Show the current state of a pipeline project.

## Input

- **Project ID:** $ARGUMENTS
- If no project ID provided, list recent projects from `output/projects/` and ask which one.

## Process

### Step 1: Find the project

```bash
ls -lt output/projects/ | head -10
```

If a project ID was given, verify it exists:
```bash
ls output/projects/<PROJECT_ID>/
```

### Step 2: Show artifact inventory

Check which files exist and show their status:

```bash
# Check each artifact
for f in knowledge.json storyboard.json script/script_*.md; do
  if [ -f "output/projects/<ID>/$f" ]; then
    echo "OK: $f ($(stat -c%s output/projects/<ID>/$f) bytes)"
  else
    echo "MISSING: $f"
  fi
done
```

Also check for shorts storyboards:
```bash
ls output/projects/<ID>/storyboard_short_*.json 2>/dev/null
```

And final video:
```bash
ls -lh output/projects/<ID>/compose/final_*.mp4 2>/dev/null
```

### Step 3: Summarize knowledge if available

If knowledge.json exists:
```bash
uv run python3 -c "
from pipeline.knowledge import Knowledge
k = Knowledge.load(Path('output/projects/<ID>/knowledge.json'))
print(f'Facts: {len(k.facts)} ({sum(1 for f in k.facts if f.verified)} verified)')
print(f'Entities: {len(k.entities)}')
print(f'Timeline: {len(k.timeline)} events')
print(f'Context bridges: {len(k.context_bridges)}')
"
```

### Step 4: Summarize storyboard if available

If storyboard.json exists:
```bash
uv run python3 -c "
from pipeline.storyboard import Storyboard
sb = Storyboard.load(Path('output/projects/<ID>/storyboard.json'))
print(f'Scenes: {len(sb.scenes)} | Format: {sb.format} | Aspect: {sb.aspect_ratio}')
print(f'Estimated duration: {sb.estimated_duration_sec():.0f}s')
visuals = {}
for s in sb.scenes:
    t = s.visual.get('type', 'unknown')
    visuals[t] = visuals.get(t, 0) + 1
print(f'Visual mix: {visuals}')
"
```

### Step 5: Present summary

Show a clear table:
- Project ID and source URL (from context.json)
- Which layers exist (knowledge / storyboard / script / video)
- Key stats (fact count, scene count, duration)
- Shorts count if any
- What the next step is (e.g. "Ready for TTS" or "Needs human review")
```

- [ ] **Step 2: Commit**

```bash
git add .claude/commands/status.md
git commit -m "feat: add /status skill — show project state and artifacts"
```

---

### Task 2: /knowledge skill

**Files:**
- Create: `.claude/commands/knowledge.md`

- [ ] **Step 1: Create the knowledge skill**

```markdown
# Knowledge Base Manager

View and edit the Layer 1 knowledge base for a project.

## Input

- **Arguments:** $ARGUMENTS
- Formats: `<project-id>`, `show <project-id>`, `edit <project-id>`
- If no project ID, ask for one.

## Commands

### show (default)

Display the knowledge base contents in a readable format.

```bash
uv run python3 -c "
from pathlib import Path
from pipeline.knowledge import Knowledge
k = Knowledge.load(Path('output/projects/<ID>/knowledge.json'))
print(f'Source: {k.meta.source_url}')
print(f'Title: {k.meta.title}')
print()
print('=== FACTS ===')
for f in k.facts:
    status = 'VERIFIED' if f.verified else 'unverified'
    print(f'  [{f.id}] ({status}) {f.text}')
    if f.tags:
        print(f'        tags: {', '.join(f.tags)}')
print()
print('=== ENTITIES ===')
for e in k.entities:
    print(f'  [{e.id}] {e.name} — {e.role}')
print()
print('=== TIMELINE ===')
for t in k.timeline:
    print(f'  {t.time}: {t.event} (refs: {', '.join(t.facts)})')
print()
print('=== CONTEXT BRIDGES ===')
for c in k.context_bridges:
    print(f'  - {c}')
"
```

Present this to the user and ask what they'd like to change.

### Editing

When the user wants to edit, use Python to load, modify, and save:

**Update a fact:**
```bash
uv run python3 -c "
from pathlib import Path
from pipeline.knowledge import Knowledge
k = Knowledge.load(Path('output/projects/<ID>/knowledge.json'))
k.update_fact('<FACT_ID>', text='<NEW_TEXT>', verified=True)
k.save(Path('output/projects/<ID>/knowledge.json'))
print('Updated <FACT_ID>')
"
```

**Add a fact:**
```bash
uv run python3 -c "
from pathlib import Path
from pipeline.knowledge import Knowledge
k = Knowledge.load(Path('output/projects/<ID>/knowledge.json'))
f = k.add_fact(text='<TEXT>', source='manual', tags=['<tag1>', '<tag2>'])
k.save(Path('output/projects/<ID>/knowledge.json'))
print(f'Added {f.id}: {f.text}')
"
```

**Remove a fact:**
```bash
uv run python3 -c "
from pathlib import Path
from pipeline.knowledge import Knowledge
k = Knowledge.load(Path('output/projects/<ID>/knowledge.json'))
k.remove_fact('<FACT_ID>')
k.save(Path('output/projects/<ID>/knowledge.json'))
print('Removed <FACT_ID>')
"
```

**Verify a fact:**
```bash
uv run python3 -c "
from pathlib import Path
from pipeline.knowledge import Knowledge
k = Knowledge.load(Path('output/projects/<ID>/knowledge.json'))
k.update_fact('<FACT_ID>', verified=True)
k.save(Path('output/projects/<ID>/knowledge.json'))
print('Verified <FACT_ID>')
"
```

## Important

- Always show the current state after any edit
- Ask for confirmation before removing facts
- When the user describes a change in natural language, map it to the right operation
- Multiple edits in one interaction are fine — save after each one
```

- [ ] **Step 2: Commit**

```bash
git add .claude/commands/knowledge.md
git commit -m "feat: add /knowledge skill — view and edit Layer 1 facts"
```

---

### Task 3: /storyboard skill

**Files:**
- Create: `.claude/commands/storyboard.md`

- [ ] **Step 1: Create the storyboard skill**

```markdown
# Storyboard Manager

View, edit, and regenerate the Layer 2 storyboard for a project.

## Input

- **Arguments:** $ARGUMENTS
- Formats: `<project-id>`, `show <project-id>`, `regenerate <project-id>`
- If no project ID, ask for one.

## Commands

### show (default)

Display the storyboard scene-by-scene:

```bash
uv run python3 -c "
from pathlib import Path
from pipeline.storyboard import Storyboard
sb = Storyboard.load(Path('output/projects/<ID>/storyboard.json'))
print(f'Format: {sb.format} | Aspect: {sb.aspect_ratio} | Version: {sb.version}')
print(f'Scenes: {len(sb.scenes)} | Est. duration: {sb.estimated_duration_sec():.0f}s')
print()
for s in sb.scenes:
    visual_type = s.visual.get('type', '?')
    overlay_info = f' + overlay:{s.overlay[\"type\"]}' if s.overlay else ''
    pause = f' + pause:{s.pause_after_sec}s' if s.pause_after_sec > 0 else ''
    print(f'[{s.id}] {s.section.upper():12} | {visual_type:16} | {s.narration_est_sec}s{overlay_info}{pause}')
    print(f'     {s.narration[:70]}...' if len(s.narration) > 70 else f'     {s.narration}')
    print(f'     facts: {s.facts_ref}')
    print()
"
```

### swap-visual

When the user wants to change a scene's visual type:

```bash
uv run python3 -c "
from pathlib import Path
from pipeline.storyboard import Storyboard
sb = Storyboard.load(Path('output/projects/<ID>/storyboard.json'))
sb.swap_visual('<SCENE_ID>', <NEW_VISUAL_DICT>)
sb.save(Path('output/projects/<ID>/storyboard.json'))
print('Swapped visual for <SCENE_ID>')
"
```

Visual type options to suggest:
- clip: {"type": "clip", "source": "primary", "start_sec": N, "end_sec": N}
- text_card: {"type": "text_card", "text": "...", "background": "#1a1a2e"}
- map: {"type": "map", "query": "Location", "style": "satellite"}
- generated_image: {"type": "generated_image", "prompt": "description", "style": "cinematic"}
- slide: {"type": "slide", "title": "...", "bullets": ["..."]}
- still_frame: {"type": "still_frame", "source": "primary", "timestamp_sec": N}
- namecard: {"type": "namecard", "name": "...", "role": "..."}

### regenerate (agent-driven)

When the user wants a new storyboard from the same knowledge base:

1. Load knowledge.json
2. Ask the user about tone/angle preferences
3. YOU (the agent) generate the storyboard directly:
   - Read all facts, entities, timeline from knowledge.json
   - Create scenes following the standard structure (hook → context → rising → climax → aftermath → analysis)
   - Assign visual types per scene based on content
   - Write narration in the target locale
4. Save as storyboard.json (or storyboard_v{N}.json for A/B)
5. Derive script.md from the new storyboard

```bash
uv run python3 -c "
from pathlib import Path
from pipeline.storyboard import Storyboard
sb = Storyboard.load(Path('output/projects/<ID>/storyboard.json'))
script = sb.derive_script()
script_path = Path('output/projects/<ID>/script/script_<LOCALE>.md')
script_path.parent.mkdir(parents=True, exist_ok=True)
script_path.write_text(script, encoding='utf-8')
print(f'Script derived: {script_path}')
"
```

### compare

Compare two storyboard versions side-by-side:

Load both storyboard.json and storyboard_v2.json, show scene-by-scene differences in section, visual type, and narration approach.

## Important

- After any storyboard change, remind the user to re-derive the script if they plan to render
- When the user describes changes in natural language ("make scene 5 more dramatic"), edit the narration directly
- Show the updated scene after each edit
```

- [ ] **Step 2: Commit**

```bash
git add .claude/commands/storyboard.md
git commit -m "feat: add /storyboard skill — view, edit, swap visuals, regenerate"
```

---

### Task 4: /produce skill (agent-driven)

**Files:**
- Create: `.claude/commands/produce.md`

- [ ] **Step 1: Create the produce skill**

```markdown
# Produce Video (Agent-Driven)

Full pipeline from URL to video. The agent does the creative work (analysis, storyboard) directly in conversation — no API calls needed for the creative stages.

## Input

- **Arguments:** $ARGUMENTS (YouTube URL)
- If no URL provided, ask for one.
- Default locale: zh-TW (unless specified)

## Process

### Step 1: Acquire

Download video and extract transcript using the pipeline CLI:

```bash
uv run pipeline acquire --url "<URL>"
```

Note the project ID from the output.

Then read the transcript:
```bash
cat output/projects/<ID>/source/transcript.json | uv run python3 -c "
import json, sys
data = json.load(sys.stdin)
text = ' '.join(d['text'] for d in data)
print(text[:3000])
print(f'... ({len(text)} total chars)')
"
```

Also fetch metadata:
```bash
uv run yt-dlp --dump-json --no-download "<URL>" 2>/dev/null | uv run python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'Title: {d[\"title\"]}')
print(f'Channel: {d[\"channel\"]}')
print(f'Views: {d[\"view_count\"]:,}')
print(f'Duration: {d[\"duration\"]//60}m{d[\"duration\"]%60}s')
"
```

### Step 2: Analyze (agent-driven)

YOU (the agent) analyze the transcript directly. Do NOT call the pipeline analyze stage.

Read the full transcript and extract:

1. **Facts** — individual factual statements with timestamps, IDs (f1, f2...), and tags
2. **Entities** — people, organizations, locations with IDs (e1, e2...)
3. **Timeline** — key events in chronological order, referencing fact IDs
4. **Context bridges** — cultural context the target locale audience needs

Save as knowledge.json:
```bash
uv run python3 -c "
import json
from pathlib import Path
knowledge = <YOUR_KNOWLEDGE_DICT>
Path('output/projects/<ID>/knowledge.json').write_text(
    json.dumps(knowledge, indent=2, ensure_ascii=False), encoding='utf-8'
)
"
```

Present the knowledge summary to the user:
- Show top facts
- Show entities
- Show context bridges
- Ask: "Anything to correct or add before I create the storyboard?"

### Step 3: Human review of knowledge

Wait for user feedback. Apply any edits using /knowledge skill operations.
If the user says it looks good, proceed.

### Step 4: Direct (agent-driven)

YOU create the storyboard directly. Do NOT call the pipeline direct stage.

Based on the knowledge base:

1. Plan the narrative arc (hook → context → rising → climax → aftermath → analysis)
2. Assign narration text in the target locale for each scene
3. Choose visual type per scene (clip, map, text_card, generated_image, slide, etc.)
4. Reference fact IDs for each scene
5. Add overlays where useful (title cards, namecards, text overlays)

Save as storyboard.json using the Storyboard schema.

Derive script.md from the storyboard:
```bash
uv run python3 -c "
from pathlib import Path
from pipeline.storyboard import Storyboard
sb = Storyboard.load(Path('output/projects/<ID>/storyboard.json'))
script = sb.derive_script()
Path('output/projects/<ID>/script').mkdir(parents=True, exist_ok=True)
Path('output/projects/<ID>/script/script_<LOCALE>.md').write_text(script, encoding='utf-8')
print('Script derived')
"
```

Present the storyboard summary:
- Scene-by-scene with visual types
- Estimated duration
- Ask: "Ready to render, or want to adjust anything?"

### Step 5: Human review of storyboard

Wait for user feedback. Apply edits using /storyboard skill operations.

### Step 6: Render

Run TTS + compose via CLI:
```bash
uv run pipeline produce --url "<URL>" --project-id <ID> --locale <LOCALE> --start-from tts --skip-review
```

### Step 7: Show result

```bash
ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 output/projects/<ID>/compose/final_<LOCALE>.mp4
ls -lh output/projects/<ID>/compose/final_<LOCALE>.mp4
```

Tell the user the video is ready and suggest:
- Play it: `mpv output/projects/<ID>/compose/final_<LOCALE>.mp4`
- Generate shorts: `/shorts <ID>`
- Review storyboard: `/storyboard <ID>`

## Important

- The key advantage: YOU do the analysis and storyboard creation, not an API call
- This means you can ask questions, the user can guide in real-time, quality is higher
- You have full conversation context — use it to make better creative decisions
- Save knowledge.json and storyboard.json using the proper schema (import from pipeline modules)
- Always let the user review and edit between stages
- Cost: $0 for analysis + storyboard (only TTS + compose run via pipeline)
```

- [ ] **Step 2: Commit**

```bash
git add .claude/commands/produce.md
git commit -m "feat: add /produce skill — agent-driven pipeline with interactive review"
```

---

### Task 5: /shorts skill

**Files:**
- Create: `.claude/commands/shorts.md`

- [ ] **Step 1: Create the shorts skill**

```markdown
# Generate Shorts

Create YouTube Shorts storyboards from an existing knowledge base. The agent selects the most interesting standalone facts and creates mini-storyboards.

## Input

- **Arguments:** $ARGUMENTS
- Formats: `<project-id>`, `<project-id> --count 5`, `<url>`
- If no arguments, ask for a project ID or URL.

## Process

### If URL provided (no existing project)

Run acquire + analyze first, or suggest using /produce to build the full project:
"I see you provided a URL. Want me to run the full /produce pipeline first, or just acquire + analyze for shorts generation?"

### If project ID provided

#### Step 1: Load and review knowledge

```bash
uv run python3 -c "
from pathlib import Path
from pipeline.knowledge import Knowledge
k = Knowledge.load(Path('output/projects/<ID>/knowledge.json'))
print(f'Found {len(k.facts)} facts')
print()
for f in k.facts:
    print(f'  [{f.id}] {f.text}')
    print(f'       tags: {f.tags}')
"
```

#### Step 2: Select facts for Shorts

YOU (the agent) score each fact on:
- **Standalone interest** — understandable without full context?
- **Surprise factor** — counterintuitive > obvious
- **Visual potential** — can we show something compelling?
- **Brevity** — explainable in 15 seconds?

Present the top N facts with your reasoning:
"Here are the top 3 facts for Shorts:
1. [f8] Chicago police rarely engage in high-speed chases — surprising policy angle
2. [f4] Vehicle exceeded 100mph — dramatic, visually compelling
3. [f12] Suspect used 'stingray' network — mysterious tech angle

Want to use these, or swap any out?"

#### Step 3: Generate storyboards

For each selected fact, YOU create a Short storyboard:
- format: "short"
- aspect_ratio: "9:16"
- target_duration_sec: 45-60
- 2-4 scenes: hook → content → punchline
- Visual types: prefer text_card, generated_image, slide (more variety than clips)

Save each as `storyboard_short_01.json`, `storyboard_short_02.json`, etc.

```bash
uv run python3 -c "
import json
from pathlib import Path
from pipeline.storyboard import Storyboard
sb_data = <YOUR_STORYBOARD_DICT>
sb = Storyboard.from_dict(sb_data)
sb.save(Path('output/projects/<ID>/storyboard_short_<NN>.json'))
print(f'Saved: {len(sb.scenes)} scenes, ~{sb.estimated_duration_sec():.0f}s')
"
```

#### Step 4: Present results

Show each Short's hook line and structure. Ask if the user wants to:
- Edit any Short's storyboard
- Render one or all Shorts
- Generate more Shorts from different facts

## Important

- Each Short focuses on ONE interesting fact
- Hook must be surprising — a question or counterintuitive statement
- Punchline should be witty or thought-provoking, with CTA
- Variety in visual types across Shorts (don't make them all look the same)
- The user can always edit via /storyboard before rendering
```

- [ ] **Step 2: Commit**

```bash
git add .claude/commands/shorts.md
git commit -m "feat: add /shorts skill — agent-driven Short storyboard generation"
```

---

### Task 6: /render skill

**Files:**
- Create: `.claude/commands/render.md`

- [ ] **Step 1: Create the render skill**

```markdown
# Render Video

Compose video from an existing storyboard. Runs TTS + compose stages.

## Input

- **Arguments:** $ARGUMENTS
- Formats: `<project-id>`, `<project-id> --short 1`, `<project-id> --version 2`
- If no arguments, ask for a project ID.

## Process

### Step 1: Verify prerequisites

Check that the required files exist:
- storyboard.json (or the specified version/short)
- For full video: source video file
- Script will be derived from storyboard if not present

```bash
ls output/projects/<ID>/storyboard*.json
ls output/projects/<ID>/source/video.mp4 2>/dev/null
```

### Step 2: Derive script if needed

If script doesn't exist or storyboard was modified after script:

```bash
uv run python3 -c "
from pathlib import Path
from pipeline.storyboard import Storyboard
sb_path = 'output/projects/<ID>/storyboard.json'  # or storyboard_short_01.json
sb = Storyboard.load(Path(sb_path))
script = sb.derive_script()
script_path = Path('output/projects/<ID>/script/script_<LOCALE>.md')
script_path.parent.mkdir(parents=True, exist_ok=True)
script_path.write_text(script, encoding='utf-8')
print(f'Script derived: {len(script)} chars, from {len(sb.scenes)} scenes')
"
```

### Step 3: Run TTS + Compose

```bash
uv run pipeline produce --url "<SOURCE_URL>" --project-id <ID> --locale <LOCALE> --start-from tts --skip-review
```

### Step 4: Show result

```bash
ls -lh output/projects/<ID>/compose/final_*.mp4
ffprobe -v quiet -show_entries stream=codec_type,duration,width,height -of default=noprint_wrappers=1 output/projects/<ID>/compose/final_<LOCALE>.mp4
```

Report: file size, duration, resolution. Suggest playing with mpv.

## Important

- If rendering a Short, the current compose stage will produce a 16:9 video
  (9:16 vertical rendering requires compose engine v2 — coming in Plan B2)
- For now, Shorts render as standard aspect ratio. This is a known limitation.
- Always derive script from the latest storyboard before rendering
```

- [ ] **Step 2: Commit**

```bash
git add .claude/commands/render.md
git commit -m "feat: add /render skill — compose video from storyboard"
```

---

### Task 7: Update /evaluate-video skill

**Files:**
- Modify: `.claude/commands/evaluate-video.md`

- [ ] **Step 1: Update evaluate-video to use new youtube-transcript-api**

The current skill references the old API (`YouTubeTranscriptApi.get_transcript`). Update to the new v1.x API:

Replace the transcript extraction section:
```python
from youtube_transcript_api import YouTubeTranscriptApi
api = YouTubeTranscriptApi()
transcript = api.fetch('<VIDEO_ID>', languages=['en'])
for entry in transcript:
    print(entry.text)
```

Also add at the end: "If this video looks good, run `/produce <URL>` to start the full pipeline."

- [ ] **Step 2: Commit**

```bash
git add .claude/commands/evaluate-video.md
git commit -m "fix: update evaluate-video skill for youtube-transcript-api v1.x"
```

---

### Task 8: Lint + test + final commit

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: 45 tests PASS (no Python changes, only skill .md files)

- [ ] **Step 2: Run ruff lint**

```bash
uv run ruff check src/ tests/
```

Expected: All checks passed

- [ ] **Step 3: Verify skills are discoverable**

```bash
ls -la .claude/commands/
```

Expected: 7 .md files (evaluate-video, produce, shorts, knowledge, storyboard, render, status)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat: complete agent skills suite — interactive pipeline management"
```

---

## Verification

1. `ls .claude/commands/*.md` — 7 skill files exist
2. `uv run pytest tests/ -v` — 45 tests pass (no regressions)
3. Test `/status 1774765300` — shows project artifacts
4. Test `/knowledge 1774765300` — shows facts, entities, timeline
5. Test `/storyboard 1774765300` — shows scene-by-scene breakdown
6. Test `/produce <url>` — agent-driven full pipeline works
7. Test `/shorts 1774765300` — agent selects facts, generates storyboards
