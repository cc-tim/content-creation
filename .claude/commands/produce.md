# Produce Video (Agent-Driven)

Full pipeline from URL to video. The agent does the creative work (analysis, storyboard creation) directly in conversation — no separate API calls needed.

## Input

- **Arguments:** $ARGUMENTS (YouTube URL)
- If no URL provided, ask for one.
- Default locale: zh-TW (unless user specifies otherwise)

## Process

### Step 1: Acquire

Download video and extract transcript:

```bash
uv run pipeline acquire --url "<URL>"
```

Note the project ID from the output. Then read the transcript:

```bash
uv run python3 -c "
import json
from pathlib import Path
data = json.loads(Path('output/projects/<ID>/source/transcript.json').read_text())
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

### Step 1b: Visual analysis (clip confidence)

Extract keyframes and detect scene changes to inform clip decisions later:

```bash
uv run python3 -c "
from pathlib import Path
from pipeline.utils.video_analysis import extract_keyframes, detect_scene_changes

video = Path('output/projects/<ID>/source/video.mp4')
kf_dir = Path('output/projects/<ID>/source/keyframes')
frames = extract_keyframes(video, kf_dir, interval_sec=15)
print(f'Extracted {len(frames)} keyframes (every 15s)')

scenes = detect_scene_changes(video, threshold=0.3)
print(f'Detected {len(scenes)} scene changes: {[f\"{t:.1f}s\" for t in scenes[:10]]}')"
```

**IMPORTANT:** Read the keyframe images to understand what's visually happening at each timestamp. This is how you decide which moments are safe to use as clips:
- Look at each keyframe — what does it show? Action? Static graphic? Talking head? Map?
- Note timestamps where visually compelling footage occurs
- Only use `clip` visual type for timestamps where you've confirmed the footage matches the narration
- Prefer designed visuals (text_card, slide, generated_image) for everything else

Scene change timestamps indicate visual transitions — these are natural cut points for clips.

### Step 2: Analyze (agent-driven — YOU do this)

Read the full transcript and extract:

1. **Facts** — individual factual statements with IDs (f1, f2...), timestamps, tags
2. **Entities** — people, organizations, locations with IDs (e1, e2...)
3. **Timeline** — key events in chronological order, referencing fact IDs
4. **Context bridges** — cultural context the target locale audience needs

Save as knowledge.json using the Knowledge schema:
```bash
uv run python3 -c "
import json
from pathlib import Path
knowledge = <YOUR_KNOWLEDGE_DICT>
Path('output/projects/<ID>/knowledge.json').write_text(
    json.dumps(knowledge, indent=2, ensure_ascii=False), encoding='utf-8'
)
print('Saved knowledge.json')
"
```

Present the knowledge summary to the user. Show top facts, entities, context bridges.
Ask: "Anything to correct or add before I create the storyboard?"

### Step 3: Human review of knowledge

Wait for user feedback. Apply edits using /knowledge operations.
If user approves, proceed.

### Step 4: Direct (agent-driven — YOU do this)

Create the storyboard directly based on the knowledge base:

1. Plan narrative arc (hook → context → rising → climax → aftermath → analysis)
2. Write narration text in target locale for each scene
3. Choose visual type per scene — IMPORTANT visual guidelines:
   - **Prefer designed visuals over clips** (text_card, slide, generated_image > clip)
   - Use clips ONLY for moments you're confident the source video visually matches the narration
   - Use slide for explaining concepts, structures, comparisons
   - Use text_card for key quotes, statistics, dramatic statements
   - Use generated_image for mood, transitions, scenes hard to show with clips
   - Target: ~30% clips, ~70% designed visuals
4. Reference fact IDs for each scene
5. Add overlays where useful (title, namecard, text lower-thirds)
6. Keep each scene's narration concise — aim for 8-15 seconds per scene for good pacing

Save as storyboard.json and derive script.md:
```bash
uv run python3 -c "
import json
from pathlib import Path
from pipeline.storyboard import Storyboard
sb_data = <YOUR_STORYBOARD_DICT>
sb = Storyboard.from_dict(sb_data)
sb.save(Path('output/projects/<ID>/storyboard.json'))
script = sb.derive_script()
Path('output/projects/<ID>/script').mkdir(parents=True, exist_ok=True)
Path('output/projects/<ID>/script/script_<LOCALE>.md').write_text(script, encoding='utf-8')
print(f'Storyboard: {len(sb.scenes)} scenes, ~{sb.estimated_duration_sec():.0f}s')
print('Script derived')
"
```

Present the storyboard summary. Ask: "Ready to render, or want to adjust anything?"

### Step 5: Human review of storyboard

Wait for user feedback. Apply edits using /storyboard operations.

### Step 6: Render

Run TTS + compose:
```bash
uv run pipeline produce --url "<URL>" --project-id <ID> --locale <LOCALE> --start-from tts --skip-review
```

### Step 7: Post-render review

Check the output and verify visual quality:

```bash
ls -lh output/projects/<ID>/compose/final_*.mp4
ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 output/projects/<ID>/compose/final_*.mp4
```

Extract review frames from the final video to spot-check visual quality:
```bash
uv run python3 -c "
from pathlib import Path
from pipeline.utils.video_analysis import extract_review_frames
video = Path('output/projects/<ID>/compose/final_<LOCALE>.mp4')
review_dir = Path('output/projects/<ID>/compose/review_frames')
frames = extract_review_frames(video, review_dir, count=8)
for f in frames:
    print(f'{f[\"timestamp_sec\"]:.0f}s: {f[\"path\"]}')
"
```

**Read the review frames** to verify:
- Are text cards readable? Font size OK?
- Do clip segments show relevant footage?
- Are overlays visible and properly positioned?
- Is there visual variety across scenes?

If issues found, suggest specific storyboard edits (swap visuals, adjust timestamps) and offer to re-render.

Suggest: play with mpv, generate shorts with /shorts, review storyboard with /storyboard.

## Important

- YOU do the analysis and storyboard creation directly — no API calls
- This means you can ask questions, the user guides in real-time, quality is higher
- You have full conversation context — use it for better creative decisions
- Always let the user review between stages
- Cost: $0 for analysis + storyboard (only TTS + compose cost compute time)

## Seeking more materials

Before creating the storyboard, actively seek additional context:
- Search the web for related news articles, background info, or expert analysis about the topic
- Look for additional data points, statistics, or context that would strengthen the narrative
- For complex topics (politics, science, history), verify key claims against reliable sources
- Add any new facts found to knowledge.json with `source: "enrichment"`
- This enrichment makes the knowledge layer more robust and enables better storytelling
- Tell the user what additional context you found and why it matters

## Visual design philosophy

- **Designed visuals > raw clips**: A well-designed text card or slide is more impactful than a mismatched clip
- Clips should only be used when the source footage clearly matches the narration moment
- Each scene should be short (8-15s narration) for good pacing
- Visual variety across scenes — don't repeat the same visual type 3+ times in a row
- Overlays add context without requiring a visual change (use them liberally)
