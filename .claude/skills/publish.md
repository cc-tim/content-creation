---
name: publish
description: Upload a produced project to YouTube with preflight checks, metadata review, OAuth verification, and the 3-phase upload sequence (video → thumbnail → disclosure).
---

# Publish Video

Upload a produced project to YouTube. Handles preflight checks, metadata review, OAuth verification, and the 3-phase upload sequence (video → thumbnail → disclosure).

## Input

- **Arguments:** $ARGUMENTS
- Formats: `<project-id>`, `<project-id> --profile ideal-parents-tw`, `<project-id> --schedule 2026-04-25T19:00:00+08:00`
- If no project ID provided, ask for one.

## Process

### Step 1: Check project state

```bash
uv run python3 -c "
import json
from pathlib import Path
pid = '<ID>'
ctx = json.loads(Path(f'output/projects/{pid}/context.json').read_text())
print(f'project_id : {ctx[\"project_id\"]}')
print(f'locale     : {ctx[\"locale\"]}')
print(f'niche      : {ctx.get(\"niche\")}')
print(f'video_id   : {ctx.get(\"youtube_video_id\", \"(not uploaded)\")}')
print(f'thumbnail  : {ctx.get(\"thumbnail_uploaded\", False)}')
print(f'disclosure : {ctx.get(\"disclosure_set\", False)}')
"
```

Check required files exist:

```bash
ls -lh output/projects/<ID>/compose/final_*.mp4 2>/dev/null || echo "MISSING: final video"
ls -lh output/projects/<ID>/thumbnail.png 2>/dev/null || echo "MISSING: thumbnail.png"
ls -lh output/projects/<ID>/metadata.json 2>/dev/null || echo "MISSING: metadata.json"
```

**If final video missing:** tell user to run `/render` first.

**If thumbnail missing:** tell user to create one (1280×720 PNG, ≤ 2MB) and save at `output/projects/<ID>/thumbnail.png`.

**If metadata.json missing:** generate it yourself in Step 2 — no API call needed.

### Step 2: Review / generate metadata

Show current metadata if it exists:

```bash
uv run pipeline metadata show --work-dir output/projects/<ID>
```

**If metadata.json is missing**, read storyboard + knowledge and write it yourself:

```bash
# Read context for niche/locale/source_url
uv run python3 -c "
import json; from pathlib import Path
ctx = json.loads(Path('output/projects/<ID>/context.json').read_text())
print('niche:', ctx.get('niche')); print('locale:', ctx.get('locale')); print('source_url:', ctx.get('source_url'))
"

# Read storyboard narrations for title/tag inspiration
cat output/projects/<ID>/storyboard.json | python3 -c "
import json, sys
sb = json.load(sys.stdin)
for s in sb.get('scenes', [])[:5]:
    print(f\"{s['id']}: {s.get('narration','')[:100]}\")
"
```

Then YOU write `metadata.json` directly (no API):

```bash
uv run python3 -c "
import json, datetime
from pathlib import Path

ctx = json.loads(Path('output/projects/<ID>/context.json').read_text())
metadata = {
    'title': '<WRITE_TITLE_IN_ZH_TW_MAX_100_CHARS>',
    'description': '',
    'tags': ['育兒', '親子', '<ADD_TOPIC_TAGS>'],
    'category_id': 27,
    'default_language': 'zh-TW',
    'default_audio_language': 'zh-TW',
    'made_for_kids': False,
    'altered_or_synthetic_content': 'none',
    '_generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    '_source_url': ctx.get('source_url', ''),
    '_profile': ctx.get('publish_profile') or 'ideal-parents-tw',
}
path = Path('output/projects/<ID>/metadata.json')
path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
print('metadata.json written:', metadata['title'])
"
```

**If the user wants a refresh** of existing metadata, do the same — read the storyboard
and rewrite the file. No need to call `pipeline metadata regenerate`.

Ask the user: "Title, tags, and description look good? Anything to edit before upload?"

If edits needed, use:

```bash
uv run pipeline metadata set title="新標題" --work-dir output/projects/<ID>
uv run pipeline metadata set 'tags=["育兒","親子","幼兒教育"]' --work-dir output/projects/<ID>
```

### Step 3: Verify OAuth token

Check token exists for the target profile:

```bash
uv run pipeline publish accounts list
```

If the required profile shows `✗ missing token`, run auth first:

```bash
uv run pipeline publish auth --profile <profile>
# Opens browser → Google OAuth → saves token
```

### Step 4: Dry-run preflight

Always do a dry-run first to catch issues before any API quota is consumed:

```bash
uv run pipeline publish <ID> --dry-run
```

The dry-run validates:
- final.mp4 exists and is ≤ 128 GB
- metadata.json is valid (title ≤ 100 chars, tags ≤ 500 chars total, etc.)
- thumbnail.png exists and is ≤ 2 MB
- schedule timestamp (if given) is in the future and timezone-aware
- channel config can route `niche/locale` to a profile

If any preflight error appears, fix it before proceeding.

### Step 5: Upload

Upload as **private** (default) — only you can see it in YouTube Studio. You manually change it to public when ready.

```bash
# Basic upload (auto-routes via niche+locale) — uploads as private
uv run pipeline publish <ID>

# Or with explicit options:
uv run pipeline publish <ID> --profile ideal-parents-tw
uv run pipeline publish <ID> --schedule 2026-04-25T19:00:00+08:00  # scheduled publish
uv run pipeline publish <ID> --privacy unlisted                      # unlisted (link-only)
uv run pipeline publish <ID> --privacy public                        # public immediately (not recommended)
```

**If upload is interrupted** (network drop, quota exceeded), just re-run the same command — it resumes from the last completed phase (video / thumbnail / disclosure).

### Step 6: Post-upload verification

```bash
uv run pipeline publish status <ID>
uv run pipeline publish status <ID> --remote   # check live YouTube state (1 quota unit)
```

The `--remote` flag confirms:
- Video is actually live on YouTube (not deleted/failed)
- Privacy status matches what you requested
- Title and metadata took effect

Tell the user the Studio URL:
`https://studio.youtube.com/video/<video_id>/edit`

The video is **private** — only visible to you in YouTube Studio. Review thumbnail, chapters, and description, then flip it to Public when ready.

## Resuming a stuck publish

If a previous publish attempt partially completed (e.g., video uploaded but thumbnail failed):

```bash
# Check what phase failed
uv run pipeline publish status <ID>

# Re-run — it skips completed phases automatically
uv run pipeline publish <ID>

# If you need to force-redo the thumbnail even if marked done:
uv run pipeline publish <ID> --force-thumbnail

# If metadata changed after upload and you need to resync:
uv run pipeline publish <ID> --force-metadata
```

## Telegram notifications

If `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` env vars are set, any publish failure triggers a Telegram alert with the error and the resume command. No configuration needed beyond the env vars.

## Important

- Always dry-run before uploading — catches all local issues without spending quota
- Upload as **private** by default — only you can see it. Flip to public manually in YouTube Studio when ready
- Thumbnail must be hand-designed (1280×720, ≤ 2MB PNG/JPG) — pipeline does not generate thumbnails
- YouTube quota resets at Pacific midnight — if you hit `quotaExceeded`, retry next day
- Each channel has its own OAuth token; `pipeline publish accounts list` shows auth status
- Adding a new channel = edit `configs/youtube_channels.toml` + `pipeline publish auth --profile <name>` — no code changes needed
