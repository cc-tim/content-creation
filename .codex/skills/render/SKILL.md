---
name: render
description: Compose video from an existing storyboard. Run TTS + compose stages. Use when asked to render, re-render, reburn, or rescene a project.
version: 1.0.0
metadata:
  openclaw:
    requirements:
      binaries: [uv, ffmpeg]
---

# Render — TTS + Compose

## Full render from storyboard

```bash
cd /home/tim-huang/content-creation
uv run pipeline produce --url "<URL>" --project-id <ID> --locale zh-TW --start-from tts --skip-review
```

## Re-render specific scenes only

```bash
# Re-render one or more scenes (faster than full reburn)
uv run pipeline compose rescene --project-id <ID> --scene s3
uv run pipeline compose rescene --project-id <ID> --scene s3 --scene s7 --scene s12
```

## Re-burn final video from existing scene renders

```bash
# Re-assemble final video from already-rendered scene .mp4s (no TTS re-run)
uv run pipeline compose reburn --project-id <ID>
```

## Variant management

Four variants are built by default on first produce:
- `plain` — no subtitles, no overlay
- `subtitles` — subtitles + overlays
- `plain_no_overlay` — no subtitles, no overlays
- `subtitles_no_overlay` — subtitles, no per-scene overlays (default preferred)

Lock a variant (after picking a winner):
```bash
uv run pipeline compose set-variant --project-id <ID> --variant subtitles_no_overlay
```

Once locked, `rescene` and `reburn` only build that variant.

## Verify output

```bash
ls -lh output/projects/<ID>/compose/final_*.mp4
ffprobe -v quiet -show_entries format=duration,size -of default=noprint_wrappers=1 \
  output/projects/<ID>/compose/final_zh-TW.mp4
```

## Common edit triggers

| Problem | Fix |
|---------|-----|
| Wrong narration text | `storyboard set` → `rescene` |
| Subtitle styling wrong | Edit theme in storyboard.json → `reburn` |
| Single scene looks bad | Edit storyboard.json → `rescene --scene X` |
| Wrong overlay wording | Edit storyboard.json → `rescene --scene X` |
