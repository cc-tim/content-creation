---
name: produce
description: Run the full YouTube porting pipeline OR the wiki-explainer porting pipeline. For YouTube: pass a URL. For wiki explainers: pass a path to a `.md` file with `intent: video` frontmatter. Covers: acquire → analyze → storyboard → TTS → compose.
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
- YouTube URL OR explainer path (one is required)
  - YouTube URL → existing flow (acquire → analyze)
  - Path to `.md` with `intent: video` frontmatter → explainer flow (manifest review → analyze)
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

## Phase 1 (alternate) — Explainer path

When the input is a path to a `.md` file (not a URL), use this branch instead.

### Load the manifest

```bash
cd /home/tim-huang/content-creation
uv run python3 -c "
from pathlib import Path
import json
from pipeline.explainer import load_explainer
ex = load_explainer(Path('<EXPLAINER_PATH>'))
print(json.dumps({
  'title': ex.title,
  'domain': ex.domain,
  'manifest': ex.manifest.model_dump(),
}, indent=2, ensure_ascii=False))
"
```

### Create project + copy explainer in

```bash
PROJECT_ID="$(date +%Y%m%d-%H%M%S)-$(basename '<EXPLAINER_PATH>' .md)"
PROJ="output/projects/$PROJECT_ID"
mkdir -p "$PROJ/source"
cp '<EXPLAINER_PATH>' "$PROJ/source/explainer.md"
echo "$PROJECT_ID"
```

### Interactive manifest review (in chat, no extra API)

Show the user a structured summary:
- Title, domain, intent
- `video_brief` (full text)
- count of: verbatim_lines, key_facts, required_images, required_clips, required_sequence
- first 3 of each list as a sample

Then raise questions where the manifest is ambiguous. Always check:
- Required images with no `role` hint → ask role (`intro_candidate`,
  `historical`, `comparison`, `aftermath`, etc.)
- `verbatim_lines` longer than ~25 words → flag (will break narration cadence)
- Conflicting `required_sequence` vs prose section order → ask which wins
- Long explainer (>2000 words body) with empty `video_brief` → ask for direction
- Required images with no caption → ask for one (used for storyboard scene generation)

If the user wants changes, edit the manifest block(s) in the **wiki**
explainer (the source of truth), then re-copy into `output/projects/<ID>/source/`.

When the user approves, continue with Phase 2.

## Phase 2 — Analyze (you do this)

Read the transcript and build a knowledge base:
- **Facts** — atomic statements with IDs (f1, f2...), timestamps, tags
- **Entities** — people, orgs, locations (e1, e2...)
- **Timeline** — key events referencing fact IDs
- **Context bridges** — cultural context zh-TW audience needs (explain US legal system, geography, etc.)

Save as `output/projects/<ID>/knowledge.json`. Show the user a summary and ask for feedback.

**For explainer-path projects:** the manifest is the analyze input. Build
`knowledge.json` from the explainer body + manifest (entities, facts cited
in `key_facts`, etc.) — do NOT extract from a transcript (there isn't one).

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

**For explainer-path projects (manifest-aware):** treat the manifest as
hard input — see `skills/storyboard/SKILL.md` "Manifest constraints" section.
In short: every `verbatim_lines` entry must appear unmodified somewhere
(narration/overlay/subtitle); every `required_images` path must appear in
at least one scene's visual; `required_sequence` shapes scene order;
`video_brief` shapes pacing and intro feel.

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
