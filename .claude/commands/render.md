# Render Video

Compose video from an existing storyboard. Runs TTS + compose stages.

## Input

- **Arguments:** $ARGUMENTS
- Formats: `<project-id>`, `<project-id> --short 1`, `<project-id> --version 2`
- If no arguments, ask for a project ID.

## Process

### Step 1: Verify prerequisites

Check that required files exist:

```bash
ls output/projects/<ID>/storyboard*.json 2>/dev/null
ls output/projects/<ID>/source/video.mp4 2>/dev/null
ls output/projects/<ID>/script/script_*.md 2>/dev/null
```

If storyboard exists but script doesn't, derive it first.

### Step 2: Derive script if needed

If script is missing or storyboard was modified after script:

```bash
uv run python3 -c "
from pathlib import Path
from pipeline.storyboard import Storyboard
sb_path = 'output/projects/<ID>/storyboard.json'
sb = Storyboard.load(Path(sb_path))
script = sb.derive_script()
script_path = Path('output/projects/<ID>/script/script_<LOCALE>.md')
script_path.parent.mkdir(parents=True, exist_ok=True)
script_path.write_text(script, encoding='utf-8')
print(f'Script derived: {len(script)} chars from {len(sb.scenes)} scenes')
"
```

### Step 3: Get source URL from context

```bash
uv run python3 -c "
import json
from pathlib import Path
ctx = json.loads(Path('output/projects/<ID>/context.json').read_text())
print(ctx.get('source_url', 'unknown'))
"
```

### Step 4: Run TTS + Compose

```bash
uv run pipeline produce --url "<SOURCE_URL>" --project-id <ID> --locale <LOCALE> --start-from tts --skip-review
```

### Step 5: Show result

```bash
ls -lh output/projects/<ID>/compose/final_*.mp4
ffprobe -v quiet -show_entries stream=codec_type,duration,width,height -of default=noprint_wrappers=1 output/projects/<ID>/compose/final_*.mp4
```

Report file size, duration, resolution. Suggest playing with mpv.

## Important

- Always derive script from the latest storyboard before rendering
- If rendering a Short, the current compose stage produces 16:9 video
  (9:16 vertical rendering requires compose engine v2, coming later)
- Shorts render as standard aspect ratio for now — known limitation
- If TTS or compose fails, show the error and suggest fixes
