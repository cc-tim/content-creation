# Pipeline Workflows

Quick reference for the two main use cases. Open this before starting any session.

---

## Use Case 1: `produce` — Make a Video

### Command

```bash
uv run pipeline produce \
  --url "https://youtube.com/watch?v=..." \
  --locale zh-TW \                        # zh-TW | ja | es-MX
  --niche parenting \                     # auto-detected from channels.toml; use "none" to skip metadata
  --voice tim-zhtw \                      # optional; auto-selects per locale
  --start-from tts \                      # skip to a stage (see resume table below)
  --skip-review \                         # bypass human review gate (auto-fix proofreading)
  --subtitles                             # burn subtitles into final video
```

---

### Stage Flow

```mermaid
flowchart TD
    INPUT(["`**Input**
    --url YouTube URL
    --locale zh-TW
    --niche parenting`"])

    ACQUIRE["**1 · ACQUIRE**
    yt-dlp + youtube-transcript-api
    ───────────────
    📥 source/video.mp4
    📥 source/transcript.json"]

    ANALYZE["**2 · ANALYZE**
    Claude Sonnet — knowledge graph
    ───────────────
    📤 knowledge.json
    (entities, timeline, context_bridges)"]

    DIRECT["**3 · DIRECT**
    Claude Sonnet — storyboard + script
    ───────────────
    📤 storyboard.json
    📤 script/script_zh-TW.md
    📤 metadata.json  ← YouTube title/tags"]

    REVIEW{"**⏸ HUMAN REVIEW GATE**
    edit storyboard.json
    edit script/script_zh-TW.md
    edit metadata.json"}

    TTS["**4 · TTS**
    edge-tts / Google Cloud / OpenAI
    ───────────────
    📤 audio/segment_NNN.mp3
    📤 audio/narration_zh-TW.mp3
    📤 audio/subtitles_zh-TW.srt"]

    COMPOSE["**5 · COMPOSE**
    FFmpeg — assemble final video
    ───────────────
    📤 compose/scenes/s1_final.mp4 …
    📤 compose/raw.mp4
    📤 compose/final_zh-TW.mp4  ✅"]

    PUBLISH["**6 · PUBLISH** (explicit, never auto)
    pipeline publish &lt;project-id&gt;
    ───────────────
    Phase A: videos.insert → youtube_video_id
    Phase B: thumbnails.set
    Phase C: disclosure update"]

    INPUT --> ACQUIRE --> ANALYZE --> DIRECT --> REVIEW --> TTS --> COMPOSE --> PUBLISH
```

---

### Output Directory (per project)

```
output/projects/{project_id}/
├── context.json                  ← pipeline state; enables resume
├── metadata.json                 ← YouTube title, description, tags
├── source/
│   ├── video.mp4                 ← downloaded source
│   └── transcript.json
├── knowledge.json                ← story facts, entities, gaps
├── storyboard.json               ← scene-by-scene plan  ← EDIT HERE
├── script/
│   └── script_zh-TW.md          ← narration text        ← EDIT HERE
├── audio/
│   ├── segment_000.mp3 …        ← per-scene clips
│   ├── narration_zh-TW.mp3      ← full narration
│   └── subtitles_zh-TW.srt
└── compose/
    ├── scenes/                   ← intermediate renders
    ├── raw.mp4
    └── final_zh-TW.mp4          ← FINAL OUTPUT ✅
```

---

### Resume / Re-run a Specific Stage

| I want to redo… | Command |
|---|---|
| Everything from scratch | `uv run pipeline produce --url "…" --locale zh-TW` |
| From analyze onward | `uv run pipeline produce --url "…" --locale zh-TW --project-id <ID> --start-from analyze` |
| From direct onward (re-script) | `… --start-from direct` |
| TTS only (re-voice after edits) | `… --start-from tts` |
| Compose only (re-render) | `… --start-from compose` |
| Just the storyboard text | `uv run pipeline storyboard set scene_003 narration="新文字"` then `--start-from tts` |

> **Note:** `--start-from tts` and `--start-from compose` load `context.json` automatically — no `--url` needed if you provide `--project-id`.

---

### Storyboard editing helpers

```bash
uv run pipeline storyboard show                        # list all scenes
uv run pipeline storyboard show --scene scene_003      # one scene's full text
uv run pipeline storyboard recordings --voice tim-zhtw # recording status per scene
uv run pipeline storyboard set scene_003 narration="…" # edit field in-place
```

---

### Metadata editing helpers

```bash
uv run pipeline metadata show --work-dir output/projects/<ID>
uv run pipeline metadata set title="新標題" --work-dir output/projects/<ID>
uv run pipeline metadata regenerate --work-dir output/projects/<ID>
```

---

## Use Case 2: Dashboard — Check & Preview Videos

### Flow

```mermaid
flowchart TD
    START(["Start dashboard"])

    SERVER["**FastAPI server**
    localhost:8765
    scripts/start-dashboard.sh"]

    TUNNEL["**Cloudflare tunnel**
    (auto-started by start-dashboard.sh)
    prints public URL for remote access"]

    SCANNER["**Scanner** reads output/projects/*/
    ─────────────────────────────
    context.json  → status, locale, youtube_video_id
    metadata.json → title, tags
    compose/final_*.mp4 → video variants"]

    UI["**Browser UI**
    Table of all projects
    Auto-refreshes every 30s"]

    STATUS["**Status badges**
    new → acquired → analyzed →
    storyboard → rendered → published"]

    PREVIEW["**▶ Preview button**
    (visible when has_video = true)
    ─────────────
    Expands inline &lt;video&gt; player
    HTTP Range requests — seeking works
    Tab per variant (e.g. with/without subtitles)"]

    START --> SERVER --> TUNNEL
    SERVER --> SCANNER --> UI
    UI --> STATUS
    UI --> PREVIEW
```

### Commands

```bash
# Remote access (starts tunnel, prints public URL)
./scripts/start-dashboard.sh

# Local only
./scripts/start-dashboard.sh --local-only

# Custom port
./scripts/start-dashboard.sh --port 9000

# Or direct (no tunnel, no auto-browser open)
uv run pipeline dashboard --no-browser --port 8765
```

### What the scanner exposes per project

| Field | Source |
|---|---|
| `status` | file existence: `video.mp4` → `knowledge.json` → `storyboard.json` → `final_*.mp4` → `youtube_video_id` |
| `title` | `metadata.json` |
| `tags` | `metadata.json` (first 5 shown) |
| `video_variants` | all `compose/final_{locale}*.mp4` files |
| `youtube_video_id` | `context.json` |
| `source_url` | `context.json` |

---

## Isolation Map — What to Edit for Each Problem

| Problem | Edit this file | Then re-run from |
|---|---|---|
| Wrong facts / missing context | `knowledge.json` | `--start-from direct` |
| Bad scene structure / story arc | `storyboard.json` | `--start-from tts` |
| Wrong narration text | `storyboard.json` or `script/script_zh-TW.md` | `--start-from tts` |
| Bad voice / audio timing | TTS config or `--voice` flag | `--start-from tts` |
| Bad video composition / subtitles | compose config or `--subtitles` flag | `--start-from compose` |
| Wrong YouTube title/tags | `metadata.json` | `pipeline metadata set …` then re-publish |
