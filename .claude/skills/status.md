---
name: status
description: Use when the user asks about the current state, progress, or stage of a pipeline project; when checking what artifacts exist, what's been completed, or what step comes next; when asking "where are we on project X" or "what's done so far".
---

# Project Status

Show the current state of a pipeline project.

## Input

- **Project ID:** $ARGUMENTS
- If no project ID provided, list recent projects from `output/projects/` and ask which one.

## Process

### Step 1: Find the project

If no project ID given, list available projects:
```bash
ls -lt output/projects/ | head -10
```

If a project ID was given, verify it exists:
```bash
ls output/projects/<PROJECT_ID>/
```

### Step 2: Show artifact inventory

Check which files exist and report their status:

```bash
for f in knowledge.json storyboard.json context.json; do
  [ -f "output/projects/<ID>/$f" ] && echo "OK: $f" || echo "MISSING: $f"
done
ls output/projects/<ID>/script/script_*.md 2>/dev/null && echo "OK: script" || echo "MISSING: script"
ls output/projects/<ID>/compose/final_*.mp4 2>/dev/null && echo "OK: final video" || echo "MISSING: final video"
ls output/projects/<ID>/storyboard_short_*.json 2>/dev/null | wc -l | xargs -I{} echo "Shorts storyboards: {}"
```

### Step 3: Summarize knowledge if exists

If knowledge.json exists, load it and show:
```bash
uv run python3 -c "
from pathlib import Path
from pipeline.knowledge import Knowledge
k = Knowledge.load(Path('output/projects/<ID>/knowledge.json'))
print(f'Facts: {len(k.facts)} ({sum(1 for f in k.facts if f.verified)} verified)')
print(f'Entities: {len(k.entities)}')
print(f'Timeline: {len(k.timeline)} events')
print(f'Context bridges: {len(k.context_bridges)}')
print(f'Source: {k.meta.source_url}')
"
```

### Step 4: Summarize storyboard if exists

If storyboard.json exists:
```bash
uv run python3 -c "
from pathlib import Path
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

### Step 5: Show final video info if exists

```bash
ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 output/projects/<ID>/compose/final_*.mp4 2>/dev/null
ls -lh output/projects/<ID>/compose/final_*.mp4 2>/dev/null
```

### Step 6: Present summary

Show a clear summary table with:
- Project ID and source URL
- Which layers exist (knowledge / storyboard / script / video)
- Key stats (fact count, scene count, duration)
- Shorts storyboard count
- Suggested next action (e.g. "Ready for TTS" or "Needs storyboard review")
