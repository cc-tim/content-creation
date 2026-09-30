---
name: generate-video
description: Generate short videos using the existing Claude video script with text-to-video or image-to-video, tiered models, caching, and automatic key rotation.
scope: project
---

# Generate Video

Use the existing shared Claude script; do not duplicate keys or caches into Codex.

```bash
python3 ~/.claude/bin/gen-video.py "prompt" [options]
```

## Tiers

| Tier | Model | Cost | Use when |
|---|---|---|---|
| `budget` | Kling v3 | ~$0.029/sec | Volume content, quick iterations (text-to-video paid-verified) |
| `standard` | Wan 2.5 | ~$0.050/sec | Default quality, social media (id corrected; not paid-verified) |

At 5 seconds, that's $0.15 / $0.25 per clip (budget / standard).

> Premium (Runway Gen-4 Turbo) was removed — fal does not host it. To restore a premium
> tier, add a fal-hosted model (e.g. Veo 3.1, Kling 3.0 Pro) in `gen-video.py`.

Common options:

- `--tier budget|standard`
- `--duration INT`
- `--image PATH_OR_URL`
- `--no-cache`
- `--output PATH`

For image-to-video workflows, generate or locate the still image first, then pass it with `--image`.

If output contains `[KEY EXHAUSTED]`, tell the user which provider/key ran out and how to reset it:

```bash
python3 ~/.claude/bin/keymanager.py status
python3 ~/.claude/bin/keymanager.py reset-all fal
```
