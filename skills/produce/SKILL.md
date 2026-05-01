---
name: produce
description: Run the full YouTube porting pipeline from a URL to a rendered video. Use when the user wants to produce, port, or make a video from a YouTube URL. Covers: acquire → analyze → storyboard → TTS → compose.
version: 1.0.0
metadata:
  openclaw:
    requirements:
      binaries: [uv, ffmpeg]
---

# Produce — Full Pipeline

Full pipeline from YouTube URL to rendered video. You (the agent) do the creative work
(knowledge extraction, storyboard writing) directly — no separate API calls needed for those stages.

## Input
- YouTube URL (required)
- Locale (default: zh-TW)
- Project ID (optional — to resume an existing project)
- Voice ID (optional — default uses locale default from registry)

## Phase 1 — Acquire

```bash
cd /home/tim-huang/content-creation
uv run pipeline acquire --url "<URL>"
```

Note the project ID printed in output. Then read the transcript:
```bash
uv run python3 -c "
import json; from pathlib import Path
data = json.loads(Path('output/projects/<ID>/source/transcript.json').read_text())
text = ' '.join(d['text'] for d in data)
print(text[:4000])
"
```

## Phase 2 — Analyze (you do this)

Read the transcript and build a knowledge base:
- **Facts** — atomic statements with IDs (f1, f2...), timestamps, tags
- **Entities** — people, orgs, locations (e1, e2...)
- **Timeline** — key events referencing fact IDs
- **Context bridges** — cultural context zh-TW audience needs (explain US legal system, geography, etc.)

Save as `output/projects/<ID>/knowledge.json`. Show the user a summary and ask for feedback.

## Phase 3 — Storyboard (you do this)

Design the narrative arc: hook → context → rising action → climax → aftermath → analysis.
Write narration in zh-TW (Traditional Chinese, Taiwan usage). Target: 20-24 scenes, 8-15s each.

Visual type priority:
1. `generated_image` — concepts, moods (use flat minimalist illustration style)
2. `article_image` — source images that directly illustrate the point
3. `slide` — structured info, comparisons (max 2 in a row)
4. `text_card` — key quotes, dramatic statements (use sparingly)
5. `clip` — only when source footage clearly matches narration

Rules:
- No 3+ consecutive same visual type
- Overlays ONLY on image-based visuals (not on text_card or slide)
- s1 must be visually striking — use generated_image with a strong concept
- Overlay y position must be ≤ 0.70 (avoid subtitle collision)

Save storyboard and derive script:
```bash
uv run python3 -c "
from pipeline.storyboard import Storyboard; from pathlib import Path; import json
sb = Storyboard.from_dict(<YOUR_DICT>)
sb.save(Path('output/projects/<ID>/storyboard.json'))
script = sb.derive_script()
Path('output/projects/<ID>/script').mkdir(parents=True, exist_ok=True)
Path('output/projects/<ID>/script/script_zh-TW.md').write_text(script, encoding='utf-8')
print(f'{len(sb.scenes)} scenes, ~{sb.estimated_duration_sec():.0f}s')
"
```

Show the user the storyboard summary. Ask: "Ready to render, or want to adjust anything?"

## Phase 4 — Render

After user approves storyboard:
```bash
uv run pipeline produce --url "<URL>" --project-id <ID> --locale zh-TW --start-from tts --skip-review
```

## Phase 5 — Verify

```bash
ls -lh output/projects/<ID>/compose/final_*.mp4
ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \
  output/projects/<ID>/compose/final_zh-TW.mp4
```

## Checkpoint

After rendering, suggest:
- `storyboard` skill to review/edit scenes
- `publish` skill when ready to upload
- `shorts` skill to generate a Shorts cut
