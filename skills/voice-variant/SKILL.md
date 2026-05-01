---
name: voice-variant
description: Build a variant of an existing project with a different TTS voice. Use when asked to try a custom voice, build a voice variant, promote a variant, or discard one.
version: 1.0.0
metadata:
  openclaw:
    requirements:
      binaries: [uv, ffmpeg]
---

# Voice Variant — Try a Different Voice

Builds a copy of an existing project's compose stage using a different voice engine,
without re-running the expensive acquire/analyze/storyboard stages.

## List available voices

```bash
cd /home/tim-huang/content-creation
uv run pipeline voice list
```

Key voices:
- `zh-TW-YunJheNeural` — edge-tts, free, zh-TW male
- `zh-TW-HsiaoChenNeural` — edge-tts, free, zh-TW female
- `tim-zhtw` — prerecorded/cloned voice

## Build a voice variant

```bash
# Re-run TTS with a different voice, then compose
uv run pipeline produce --url "<URL>" --project-id <ID> \
  --locale zh-TW --start-from tts --voice <voice-id> --skip-review
```

This creates audio in `output/projects/<ID>/audio/` using the new voice
and re-composes the video. Previous variant files are preserved with
suffixes.

## Compare variants

```bash
ls -lh output/projects/<ID>/compose/final_*.mp4
# Play both to compare:
# mpv output/projects/<ID>/compose/final_zh-TW_<voice1>.mp4
# mpv output/projects/<ID>/compose/final_zh-TW_<voice2>.mp4
```

## Check recording status (prerecorded voice)

```bash
uv run pipeline storyboard recordings --voice tim-zhtw
```

Scenes without a recording fall back to edge-tts automatically.

## Promote a variant

Once the user picks a preferred voice variant, update context.json:
```bash
uv run python3 - <<'EOF'
import json
from pathlib import Path
ctx = json.loads(Path('output/projects/<ID>/context.json').read_text())
ctx['preferred_voice'] = '<voice-id>'
Path('output/projects/<ID>/context.json').write_text(
    json.dumps(ctx, indent=2, ensure_ascii=False)
)
print('Voice preference saved')
EOF
```
