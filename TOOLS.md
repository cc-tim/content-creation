# TOOLS.md — Pipeline Tools Reference

## Environment

| Tool | Version check | Purpose |
|------|--------------|---------|
| `uv` | `uv --version` | Package manager + task runner |
| `ffmpeg` | `ffmpeg -version` | Video composition |
| `ffprobe` | `ffprobe -version` | Video inspection |
| Python | `uv run python3 --version` | 3.11+ |

## Pipeline CLI (all via `uv run pipeline`)

```bash
# Discovery
uv run pipeline discover --region US --target-locale zh-TW

# Full produce (acquire → analyze → direct → tts → compose)
uv run pipeline produce <URL> --locale zh-TW
uv run pipeline produce <URL> --locale zh-TW --niche parenting
uv run pipeline produce <URL> --project-id <ID> --start-from tts

# Storyboard management
uv run pipeline storyboard show
uv run pipeline storyboard show --scene <id>
uv run pipeline storyboard recordings --voice <voice-id>
uv run pipeline storyboard set <scene_id> <field>="<value>"

# Compose
uv run pipeline compose set-variant --project-id <ID> --variant subtitles_no_overlay
uv run pipeline compose rescene --project-id <ID> --scene <id>
uv run pipeline compose reburn --project-id <ID>

# Proofread
uv run pipeline proofread run --project-id <ID>
uv run pipeline proofread run --project-id <ID> --apply

# Publish
uv run pipeline publish <project-id>
uv run pipeline publish <project-id> --dry-run
uv run pipeline publish status <project-id>
uv run pipeline metadata show --work-dir output/projects/<ID>
uv run pipeline metadata set title="..." --work-dir output/projects/<ID>

# Voices
uv run pipeline voice list
uv run pipeline outro build --profile ideal-parents-tw

# Dashboard
./scripts/start-dashboard.sh
```

## Output Locations

```
output/projects/<ID>/context.json          ← pipeline state
output/projects/<ID>/source/video.mp4      ← downloaded source
output/projects/<ID>/source/transcript.json
output/projects/<ID>/source/keyframes/     ← extracted frames
output/projects/<ID>/knowledge.json        ← facts + entities
output/projects/<ID>/storyboard.json       ← scene plan
output/projects/<ID>/script/               ← narration scripts
output/projects/<ID>/audio/                ← TTS per scene
output/projects/<ID>/compose/              ← final videos
output/projects/<ID>/metadata.json         ← YouTube metadata
```

## Voice IDs

| Voice | Type | Locale |
|-------|------|--------|
| `zh-TW-YunJheNeural` | edge-tts (free) | zh-TW male |
| `zh-TW-HsiaoChenNeural` | edge-tts (free) | zh-TW female |
| `tim-zhtw` | prerecorded/cloned | zh-TW male |

## API Keys Location

`~/.claude/api-keys.json` — fal.ai, OpenAI image gen
`~/.openclaw/openclaw.json` — OpenClaw provider keys

## Config Files

```
configs/youtube_channels.toml     ← channel profiles + routing
configs/niche_anchors/            ← per-niche defaults
voices/registry.json              ← voice registry
```
