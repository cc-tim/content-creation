---
name: publish
description: Upload a produced project to YouTube. Use when asked to upload, publish, or schedule a video. Covers preflight checks, metadata review, OAuth verification, and the 3-phase upload.
version: 1.0.0
metadata:
  openclaw:
    requirements:
      binaries: [uv]
---

# Publish — YouTube Upload

## Preflight check (always run first)

```bash
cd /home/tim-huang/content-creation
uv run pipeline publish <project-id> --dry-run
```

This verifies: OAuth token valid, video file exists, metadata complete, disclosure set.

## Review metadata before upload

```bash
uv run pipeline metadata show --work-dir output/projects/<ID>
```

Edit if needed:
```bash
uv run pipeline metadata set title="新標題" --work-dir output/projects/<ID>
uv run pipeline metadata set description="..." --work-dir output/projects/<ID>
```

## Upload (unlisted by default)

```bash
# Auto-route via niche+locale
uv run pipeline publish <project-id>

# Explicit channel profile
uv run pipeline publish <project-id> --profile ideal-parents-tw

# Scheduled publish
uv run pipeline publish <project-id> --schedule 2026-05-01T19:00:00+08:00
```

## Check upload state

```bash
uv run pipeline publish status <project-id>              # local state
uv run pipeline publish status <project-id> --remote     # live YouTube state
```

## Three-phase upload

Phase A: `videos.insert` → stores `youtube_video_id` in context.json
Phase B: `thumbnails.set` → requires `thumbnail.png` (≤2MB) in project dir
Phase C: `videos.update` → sets synthetic media disclosure

Each phase is idempotent — re-running `publish` resumes from last completed phase.

## OAuth setup (one-time per channel)

```bash
uv run pipeline publish auth --profile ideal-parents-tw
uv run pipeline publish accounts list
```

## Channel profiles

Defined in `configs/youtube_channels.toml`. Current profiles:
- `ideal-parents-tw` — parenting / zh-TW
