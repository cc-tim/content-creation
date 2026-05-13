---
name: shorts
description: Generate a YouTube Shorts storyboard from an existing project. Use when asked to make a Short, create a 60-second version, or generate vertical video from a project.
version: 1.0.0
metadata:
  openclaw:
    requirements:
      binaries: [uv]
---

# Shorts — Generate YouTube Shorts Storyboard

Generates a 45-60s, 9:16 vertical storyboard from an existing project's knowledge base.
Best standalone facts only — no assumed series context.

## Input

Project ID with an existing `knowledge.json` and `storyboard.json`.

## Step 1 — Read project context

```bash
cd /home/tim-huang/content-creation
cat output/projects/<ID>/knowledge.json | python3 -c "
import json, sys
k = json.load(sys.stdin)
print('Top facts:')
for f in k.get('facts',[])[:8]:
    print(f'  {f[\"id\"]}: {f[\"text\"][:100]}')
"
```

## Step 2 — Select the best standalone hook

Pick the single most compelling, self-contained fact from the knowledge base:
- Must make sense without watching the full video
- Should provoke curiosity or surprise
- Ideally < 15 words to state

## Step 3 — Write the Shorts storyboard

Shorts structure (45-60s total):
- `s1`: Hook — most dramatic fact, text_card or generated_image (0-8s)
- `s2`: Setup — one sentence context (8-18s)
- `s3`: Rising — the key tension (18-30s)
- `s4`: Payoff — resolution or twist (30-45s)
- `s5`: CTA — "看完整版" call to action (45-55s)

Format: 9:16 aspect ratio. No sidebar compartments. Keep narration ≤ 12s per scene.

## Step 4 — Save

```bash
uv run python3 - <<'EOF'
import json
from pathlib import Path

shorts_sb = <YOUR_SHORTS_STORYBOARD_DICT>
shorts_sb['aspect_ratio'] = '9:16'
shorts_sb['target_duration_sec'] = 55

path = Path('output/projects/<ID>/storyboard_shorts.json')
path.write_text(json.dumps(shorts_sb, indent=2, ensure_ascii=False))
print(f'Saved: {len(shorts_sb["scenes"])} scenes')
EOF
```

## Step 5 — Render

```bash
uv run pipeline produce --url "<URL>" --project-id <ID>-shorts \
  --locale zh-TW --start-from tts --skip-review
```

(Pass the shorts storyboard path if the CLI supports it, otherwise copy it to `storyboard.json` in a fresh project dir.)
