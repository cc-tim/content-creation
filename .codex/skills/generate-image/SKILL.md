---
name: generate-image
description: Generate images using the existing Claude media scripts with tiered models, prompt caching, and automatic key rotation. Use for image generation tasks across content, design, and media work.
scope: project
---

# Generate Image

Use the existing shared Claude script; do not duplicate keys or caches into Codex.

```bash
python3 ~/.claude/bin/gen-image.py "prompt" [options]
```

Start with `--tier draft` unless the user explicitly asks for final quality.

## Tiers

| Tier | Model | Cost | Use when |
|---|---|---|---|
| `draft` | Flux Schnell | ~$0.003 | First pass, reviewing composition, quick iterations |
| `production` | Flux 1.1 Pro | ~$0.040 | Final content, published assets |
| `premium` | GPT-Image-1.5 (high) | ~$0.133 | Hero images, when text-in-image precision matters |

Common options:

- `--tier draft|production|premium`
- `--size square|landscape|portrait`
- `--seed INT`
- `--no-cache`
- `--output PATH`
- `--provider fal|openai`

The script prints the generated image path on success. Generated media and prompt cache remain in `~/.claude/media-cache/`.

If output contains `[KEY EXHAUSTED]`, tell the user which provider/key ran out and how to reset it:

```bash
python3 ~/.claude/bin/keymanager.py status
python3 ~/.claude/bin/keymanager.py reset <provider> <key-name>
python3 ~/.claude/bin/keymanager.py reset-all fal
```
