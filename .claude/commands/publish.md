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

**If metadata.json missing:** run `pipeline metadata regenerate` (see Step 2).

### Step 2: Review / generate metadata

Show current metadata:

```bash
uv run pipeline metadata show --work-dir output/projects/<ID>
```

If metadata.json is missing or the user wants to refresh it:

```bash
uv run pipeline metadata regenerate --work-dir output/projects/<ID>
uv run pipeline metadata show --work-dir output/projects/<ID>
```

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
