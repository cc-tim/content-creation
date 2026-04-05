# Storyboard Manager

View, edit, and regenerate the Layer 2 storyboard for a project.

## Input

- **Arguments:** $ARGUMENTS
- Formats: `<project-id>`, `show <project-id>`, `regenerate <project-id>`
- If no project ID, ask for one.

## Show (default)

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
    vtype = s.visual.get('type', '?')
    overlay = f' + overlay:{s.overlay[\"type\"]}' if s.overlay else ''
    pause = f' + pause:{s.pause_after_sec}s' if s.pause_after_sec > 0 else ''
    narr = s.narration[:70] + '...' if len(s.narration) > 70 else s.narration
    print(f'[{s.id}] {s.section.upper():12} | {vtype:16} | {s.narration_est_sec}s{overlay}{pause}')
    print(f'     {narr}')
    print(f'     facts: {s.facts_ref}')
    print()
"
```

## Swap Visual

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

Visual type options:
- clip: {"type": "clip", "source": "primary", "start_sec": N, "end_sec": N}
- text_card: {"type": "text_card", "text": "...", "background": "#1a1a2e"}
- map: {"type": "map", "query": "Location", "style": "satellite"}
- generated_image: {"type": "generated_image", "prompt": "...", "style": "cinematic"}
- slide: {"type": "slide", "title": "...", "bullets": ["..."]}
- still_frame: {"type": "still_frame", "source": "primary", "timestamp_sec": N}
- namecard: {"type": "namecard", "name": "...", "role": "..."}

## Regenerate (agent-driven)

When the user wants a new storyboard from the same knowledge base:

1. Load knowledge.json for the project
2. Ask the user about tone/angle preferences
3. YOU (the agent) generate the storyboard directly — do NOT call the pipeline API
4. Read all facts, entities, timeline from knowledge.json
5. Create scenes following standard structure (hook, context, rising, climax, aftermath, analysis)
6. Assign visual types per scene based on content
7. Write narration in the target locale
8. Save as storyboard.json (or storyboard_v{N}.json for A/B testing)
9. Derive script.md:

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

## Compare

Compare two storyboard versions side-by-side. Load both files and show scene-by-scene differences in section, visual type, and narration approach.

## Important

- After any storyboard change, remind the user to re-derive the script before rendering
- When the user says "make scene 5 more dramatic", edit the narration directly
- Show the updated scene after each edit
- For A/B testing, save as storyboard_v2.json instead of overwriting
