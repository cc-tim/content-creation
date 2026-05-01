---
name: status
description: Check the current state, progress, or stage of a pipeline project. Use when asked "where are we on project X", "what's done", "what step comes next", or "show me project status".
version: 1.0.0
metadata:
  openclaw:
    requirements:
      binaries: [uv]
---

# Status — Project State Check

## Find the project

If the user gives a project ID, use it directly. Otherwise list recent projects:
```bash
ls -lt /home/tim-huang/content-creation/output/projects/ | head -10
```

## Read context

```bash
cat output/projects/<ID>/context.json
```

Key fields: `stage` (last completed), `locale`, `source_url`, `youtube_video_id`

## Check artifacts

```bash
# What files exist?
ls output/projects/<ID>/source/   2>/dev/null && echo "source: OK" || echo "source: missing"
ls output/projects/<ID>/knowledge.json 2>/dev/null && echo "knowledge: OK" || echo "knowledge: missing"
ls output/projects/<ID>/storyboard.json 2>/dev/null && echo "storyboard: OK" || echo "storyboard: missing"
ls output/projects/<ID>/script/ 2>/dev/null && echo "script: OK" || echo "script: missing"
ls output/projects/<ID>/audio/ 2>/dev/null | wc -l | xargs -I{} echo "audio: {} files"
ls output/projects/<ID>/compose/final_*.mp4 2>/dev/null && echo "compose: DONE" || echo "compose: not yet"
ls output/projects/<ID>/metadata.json 2>/dev/null && echo "metadata: OK" || echo "metadata: missing"
```

## Video info (if rendered)

```bash
ffprobe -v quiet -show_entries format=duration,size -of default=noprint_wrappers=1 \
  output/projects/<ID>/compose/final_zh-TW.mp4 2>/dev/null
```

## Publish state

```bash
uv run pipeline publish status <ID> 2>/dev/null
```

## Summary output

Report: project ID, locale, last completed stage, what artifacts exist, what's missing, recommended next step.
