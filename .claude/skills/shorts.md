---
name: shorts
description: Generate YouTube Shorts storyboards from an existing project knowledge base. Selects the most interesting standalone facts and creates mini-storyboards (45-60s, 9:16).
---

# Generate Shorts

Create YouTube Shorts storyboards from an existing knowledge base. The agent selects the most interesting standalone facts and creates mini-storyboards.

## Input

- **Arguments:** $ARGUMENTS
- Formats: `<project-id>`, `<project-id> --count 5`, `<url>`
- If no arguments, ask for a project ID or URL.

## Process

### If URL provided (no existing project)

Suggest: "I see a URL. Want me to run /produce first to build the full project, or just acquire + analyze for shorts?"

### If project ID provided

#### Step 1: Load knowledge

```bash
uv run python3 -c "
from pathlib import Path
from pipeline.knowledge import Knowledge
k = Knowledge.load(Path('output/projects/<ID>/knowledge.json'))
print(f'Found {len(k.facts)} facts')
print()
for f in k.facts:
    tags = ', '.join(f.tags) if f.tags else 'none'
    print(f'  [{f.id}] {f.text}')
    print(f'       tags: {tags}')
"
```

#### Step 2: Select facts for Shorts

YOU (the agent) score each fact on:
- **Standalone interest** — understandable without full context?
- **Surprise factor** — counterintuitive > obvious
- **Visual potential** — can we show something compelling?
- **Brevity** — explainable in 15 seconds?

Present top N facts with reasoning:
"Here are the top 3 facts for Shorts:
1. [f8] Fact text — reason it's interesting
2. [f4] Fact text — reason it's interesting
3. [f12] Fact text — reason it's interesting

Want to use these, or swap any out?"

#### Step 3: Generate storyboards

For each selected fact, YOU create a Short storyboard:
- format: "short", aspect_ratio: "9:16", target_duration_sec: 45-60
- 2-4 scenes: hook → content → punchline
- Visual types: prefer text_card, generated_image, slide for variety

Save each:
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

Show each Short's hook line and scene structure. Ask if user wants to:
- Edit any Short via /storyboard
- Render one or all via /render
- Generate more from different facts

## Important

- Each Short focuses on ONE interesting fact
- Hook must be surprising — a question or counterintuitive statement
- Punchline should be witty or thought-provoking with CTA
- Variety in visual types across Shorts
- The user can edit via /storyboard before rendering
