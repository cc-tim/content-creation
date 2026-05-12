# content-creation — YouTube Content Porting Pipeline

"Porting" means: find what's trending in English → cross-check if a target locale market has a gap → create an original, restructured video for that market using the source as reference material. This is NOT translation/dubbing — it's 搬運: independent research and rebuild as original content.

**Target locales:** zh-TW → Japanese → Spanish (Latin American). Start with zh-TW.

## Setup

```bash
uv sync                                    # Install all dependencies
uv run pipeline --help                     # Show CLI help

# One-time plugin activation (per machine)
/plugin marketplace add /home/tim-huang/content-creation
/plugin install content-creation@content-creation-local
# Restart Claude Code session after installing
```

## The Porting Workflow

```
Phase 1: DISCOVER (automated)
  YouTube Data API + pytrends → find trending EN videos
  Cross-check target locale → calculate opportunity ratio
  (EN views / target-lang views > 10:1 = high opportunity)
  Score: visual intensity, narrative completeness, cultural portability
  Output: ranked candidate list

Phase 2: EVALUATE (human, ~10 min)
  Human picks which stories to port from candidate list
  Considers: cultural fit, ethical concerns, competitive timing

Phase 3: ACQUIRE (automated)
  yt-dlp → download source video
  youtube-transcript-api → extract transcript
  faster-whisper (fallback) → transcribe if no subs available
  Collect additional reference material (news articles, court docs)

Phase 4: RESTRUCTURE (AI + human review)
  Claude API → analyze transcript, extract story structure
  Claude API → build knowledge graph (who, what, when, where, why, conflicts)
  Claude API → write NEW script for target locale
    - NOT literal translation — cultural adaptation
    - Add context target audience needs (explain US legal system, geography, etc.)
    - Restructure for engagement (hook → context → rising action → climax → aftermath)
  Human reviews and edits the adapted script

Phase 5: PRODUCE (automated)
  edge-tts / Google Cloud TTS → generate narration audio
  FFmpeg → compose video (source clips as reference + new narration + subtitles + overlays)
  Original content must be 50-70%+ of final video

Phase 6: PUBLISH (semi-automated)
  Claude API → generate localized title, description, tags
  Human reviews final video before upload
  YouTube Data API → upload with optimized metadata
```

## Architecture

### Three Subsystems

**Discovery Engine** (`src/discovery/`) — finds and scores porting candidates
- Monitors trending EN channels via YouTube Data API v3 + pytrends
- Cross-references target-locale YouTube to find gaps
- Scores candidates and presents ranked list to human
- Runs on a schedule (daily or on-demand)

**Production Pipeline** (`src/pipeline/`) — produces the ported video
- Linear stage pipeline: each stage implements `PipelineStage.run(ctx) -> ctx`
- `PipelineContext` dataclass carries mutable state between stages
- Serializable context enables resuming from last successful stage
- Human checkpoints at: story selection, script review, final video review

**Observability** (`src/observe/`) — learns what works
- Polls YouTube Analytics API daily for channel metrics
- Maintains content knowledge graph (tags per video)
- Correlates tags × metrics to find what elements drive views
- Feeds insights back into discovery scoring and scriptwriting prompts

### Directory Structure

```
src/
  discovery/             # Trend monitoring + gap analysis
    monitor.py           # YouTube API channel/video tracking
    trends.py            # pytrends integration
    gap.py               # Cross-locale gap checking
    scorer.py            # Opportunity scoring
    presenter.py         # CLI ranked list display, human selection
    config.py            # Discovery-specific config
  pipeline/              # Video production pipeline
    cli.py               # Typer CLI entry point
    cli_metadata.py      # `pipeline metadata` sub-app
    config.py            # pydantic-settings
    models.py            # Shared Pydantic models
    orchestrator.py      # Chains stages, handles state/resume
    stages/
      base.py            # PipelineStage ABC + PipelineContext
      acquire.py         # yt-dlp download + transcript extraction
      analyze.py         # Claude API story structure + knowledge graph
      direct.py          # Agent-driven storyboard + metadata.json
      tts.py             # TTS generation (edge-tts, Google Cloud, OpenAI)
      compose.py         # FFmpeg video composition
    publish/             # YouTube upload subpackage
      auth.py            # OAuth flow + token mgmt
      channels.py        # TOML config loader; (niche,locale) → profile
      client.py          # YouTubeClient wrapper
      cli.py             # `pipeline publish` sub-app
      metadata.py        # Metadata Pydantic model
      stage.py           # PublishStage: idempotent 3-phase upload (A/B/C)
    notify/
      telegram.py        # Failure notifier via Telegram Bot API
    utils/
      ffmpeg.py          # FFmpeg command wrappers
      srt.py             # SRT/VTT parsing
  observe/               # Observability & feedback loop
    collector.py         # YouTube Analytics API polling
    correlator.py        # Tag × metrics queries
    dashboard.py         # CLI rich-table channel health
    reporter.py          # Periodic summary reports
    suggest.py           # Claude Haiku → next-video suggestions
tests/
  unit/                  # Mock external APIs
  integration/           # Tests requiring FFmpeg binary
  fixtures/              # Sample .srt files, short audio clips
configs/                 # TOML presets per locale/workflow
scripts/                 # One-off helpers
output/                  # Default output dir (gitignored)
docs/superpowers/specs/  # Design specs
```

### Key Design Decisions

- **Discovery and Production are separate subsystems** — discovery runs continuously to build a candidate queue; production is triggered per-video
- **"scriptwrite" not "translate"** — the script adaptation stage writes a NEW script inspired by the source, not a translation
- **Human-in-the-loop at 3 gates**: story selection, script review, final video review
- **PipelineContext serialization** enables resume from any stage after failure or human review pause
- **TTS abstraction** — swap between edge-tts (free), Google Cloud TTS, or OpenAI TTS via config
- **Publish is always explicit** — `PublishStage` is never in the orchestrator auto-chain
- **Idempotent upload** — `PipelineContext` tracks `youtube_video_id`, `thumbnail_uploaded`, `disclosure_set`

## Tech Stack

| Component | Tool | Why |
|-----------|------|-----|
| Package manager | **uv** | Fast, PEP 621 native, built-in Python version mgmt |
| CLI | **Typer** | Type-hint-driven, subcommands per stage |
| Config | **pydantic-settings** | Layered config with validation |
| YouTube download | **yt-dlp** | Handles subtitles, audio extraction natively |
| Transcript extraction | **youtube-transcript-api** | Free, no API key, any public video |
| Transcription fallback | **faster-whisper** | 4x faster than openai-whisper |
| Story analysis + scriptwriting | **Claude Sonnet API** | Best reasoning for narrative restructuring |
| TTS (primary/free) | **edge-tts** | Free, covers zh-TW/ja/es |
| TTS (premium) | **Google Cloud TTS Neural2** | 1M chars/month free tier |
| Video composition | **FFmpeg** via ffmpeg-python | Industry standard |
| Trend monitoring | **YouTube Data API v3** + **pytrends** | Free tiers sufficient |
| YouTube upload | **google-api-python-client** + **google-auth-oauthlib** | YouTube Data API v3 resumable upload |
| Subtitle parsing | **pysrt** | Simple SRT read/write |
| Failure notifications | **httpx** → Telegram Bot API | Lightweight, no extra dep |
| Logging | **structlog** | Structured JSON per stage |
| Linting/formatting | **Ruff** | Replaces black + isort + flake8 |
| Testing | **pytest** | Markers: `slow`, `integration`, `network` |

## Skills (project plugin)

This project ships skills at `skills/<name>/SKILL.md`. They are read by **openclaw** (directly) and **Claude Code** (via `.claude-plugin/` manifest as `content-creation:<skill>`).

Deprecated flat-form skills at `.claude/skills/*.md` are not loaded by either system.

## Commands

### Discovery
```bash
uv run pipeline discover --region US --target-locale zh-TW  # Find porting candidates
uv run pipeline discover --trending --days 7                # Trending last 7 days
```

### Production Pipeline
```bash
uv run pipeline produce <video-url> --locale zh-TW
uv run pipeline produce <video-url> --locale zh-TW --niche parenting
uv run pipeline produce <video-url> --locale zh-TW --niche none       # skip metadata gen
uv run pipeline acquire <video-url>                                    # Download + extract only
```

### Storyboard Editing
```bash
uv run pipeline storyboard show                              # list all scenes
uv run pipeline storyboard show --scene scene_003            # one scene's full text
uv run pipeline storyboard recordings --voice tim-zhtw       # recording status per scene
uv run pipeline storyboard set scene_003 narration="新文字"  # edit a safe field
```

Natural-language triggers:
```
"show me scene X's narration"       → storyboard show --scene X
"which scenes still need recording" → storyboard recordings
"fix scene X's text to Y"           → storyboard set X narration="Y"
"change scene X's pause to Ns"      → storyboard set X pause_after_sec=N
```

### Compose Iteration

Variant-focus workflow:
- Phase 1: initial produce → all 4 variants built (preferred_variant=null)
- Phase 2: pick winner with `set-variant`; rescene/reburn now only build that variant
- Phase 3: edit loop — rescene + reburn operate on locked variant only

```bash
uv run pipeline compose set-variant --project-id <ID> --variant subtitles_no_overlay
uv run pipeline compose rescene --project-id <ID> --scene s9 [--scene s12]
uv run pipeline compose transitions --project-id <ID>    # rebuild transition clips + concat/finals only
uv run pipeline compose frame --project-id <ID>          # rewrap cached scene visuals in current frame_style
uv run pipeline compose reburn --project-id <ID>
```

Safety: `compose rescene` errors if `--scene` covers more than half the storyboard. Use `compose reburn` for wide rebuilds. Pass `--force` to override.

Transition asset workflow: seam transitions in `storyboard.json` can now declare `renderer_mode` plus optional stock metadata such as `asset_path`, `asset_source`, and `asset_license`. Use `renderer_mode=generated` for built-in transitions, `licensed_clip` for full-frame licensed stock clips, and `overlay` for alpha/green-screen overlay assets that sit on top of a generated base transition.

Overlay vs. no_overlay: overlay text (`type: text_top`, `text_emphasis`) appears ONLY in overlay variants (plain, subtitles). Use `visual_text` in storyboard for visibility in `subtitles_no_overlay`.

Natural-language triggers:
```
"s9 overlay is unclear / wrong"          → edit storyboard.json, then compose rescene --project-id X --scene s9
"fix wording in scene X"                 → storyboard set + compose rescene --project-id X --scene X
"subtitles too small / wrong color"      → edit theme in storyboard.json, then compose reburn --project-id X
"lock this variant / I've decided"       → pipeline compose set-variant --project-id X --variant <name>
"what variant is locked?"                → check context.json preferred_variant field
"unlock variant / build all 4 again"     → edit context.json preferred_variant to null
"re-render just the compose step"        → produce --project-id X --url <url> --start-from compose
```

### Proofreading
```bash
uv run pipeline proofread run --project-id <ID>              # show issues (Claude Haiku)
uv run pipeline proofread run --project-id <ID> --apply      # show + apply all fixes
```

### Visual Review
```bash
uv run pipeline visual-review extract-frames --project-id <ID>
```
Natural-language triggers: "review the rendered video", "check for visual issues", "look at the rendered scenes", "judge the scene image"

### Dashboard (always-on)

The dashboard runs as a systemd user service and is permanently accessible at **https://dashboard.keeppro.io** (Google auth required — `t8522192@gmail.com`).

```bash
# Status / manage
systemctl --user status content-dashboard          # check dashboard
systemctl --user status cloudflared-named-tunnel   # check tunnel
dashrs                                             # manual restart shortcut

# Local access (no auth)
curl http://localhost:8765/api/projects

# Logs
tail -f /tmp/dashboard-8765.log
journalctl --user -u content-dashboard -f
journalctl --user -u cloudflared-named-tunnel -f
```

**Auto-restart on AI sessions:** `scripts/restart-dashboard-if-changed.sh` is wired to the Claude Code and Codex `Stop` hooks. When a session ends with changes in `src/pipeline/`, the dashboard restarts automatically.

**Static asset freshness:** Dashboard HTML and `/static/*.js` responses are served with `Cache-Control: no-store`, and HTML injects an mtime `?v=` token into JS URLs. Browser refresh should pick up frontend edits without restarting Cloudflare or manually clearing cache.

**Service files:** `infra/systemd/user/` — copy to `~/.config/systemd/user/` and run `systemctl --user daemon-reload` to redeploy on a new machine.

**Cloudflare tunnel:** Named tunnel `content-dashboard` → `dashboard.keeppro.io`. Config at `~/.cloudflared/config.yml`. Cloudflare Access restricts access to `t8522192@gmail.com`.

Natural-language triggers: "show me the dashboard", "check video status", "what projects are rendered?", "is the dashboard running?"

### Publish and Metadata
```bash
uv run pipeline publish <project-id>                               # auto-routes via niche+locale
uv run pipeline publish <project-id> --profile ideal-parents-tw    # explicit channel
uv run pipeline publish <project-id> --schedule 2026-04-25T19:00:00+08:00
uv run pipeline publish <project-id> --dry-run                     # preflight only

uv run pipeline publish auth --profile ideal-parents-tw
uv run pipeline publish accounts list
uv run pipeline publish accounts show ideal-parents-tw

uv run pipeline publish status <project-id>
uv run pipeline publish status <project-id> --remote               # live state from YouTube

uv run pipeline metadata show --work-dir <project-dir>
uv run pipeline metadata set title="新標題" --work-dir <project-dir>
uv run pipeline metadata regenerate --work-dir <project-dir>
```

### Outro
```bash
uv run pipeline outro build --profile ideal-parents-tw
uv run pipeline outro build --profile ideal-parents-tw --force
uv run pipeline outro build --profile ideal-parents-tw --music /path/to/file.mp3 --force
uv run pipeline outro build --profile ideal-parents-tw --aspect-ratio 9:16
uv run pipeline outro status
```

Channel outro assets: `configs/channels/<profile>/` — `profile.png`, `outro_music.mp3`, `outro.mp4`

### Testing & Lint
```bash
uv run pytest
uv run pytest tests/unit/
uv run pytest -m "not slow and not network"
uv run pytest -k "test_story_structure"
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
```

## Channel Config + Niche Routing

Channel profiles: `configs/youtube_channels.toml` (committed, no secrets). Token files: `~/.config/content-creation/youtube/<profile>.json` (mode 0600, gitignored).

```toml
[profiles.ideal-parents-tw]
niche      = "parenting"
locale     = "zh-TW"
channel_id = "UC..."          # fill in after first auth
voice_guide = "..."            # shapes Claude's metadata generation
default_tags = ["育兒", "親子"]
category_id  = 27

[routing]
"parenting/zh-TW" = "ideal-parents-tw"
```

**Niche auto-detection**: `produce --locale zh-TW` → looks up routing → if exactly one niche for that locale, uses it automatically; errors if ambiguous; warns if no config. Override with `--niche parenting` or opt-out with `--niche none`.

**Metadata generation**: `DirectStage` emits `metadata.json` (title, description, tags, disclosure) using Claude + channel's `voice_guide`. Skipped when niche is `none` or config missing.

**Three-phase upload (A → B → C)**:
- Phase A: `videos.insert` (resumable, returns `youtube_video_id`)
- Phase B: `thumbnails.set` (requires `thumbnail.png` ≤ 2MB)
- Phase C: `videos.update` with `containsSyntheticMedia` disclosure

Each phase persisted to `context.json` — partial failure resumes cleanly.

**One-time OAuth**:
```bash
uv run pipeline publish auth --profile ideal-parents-tw
# Opens browser → Google consent → writes token file
```

## Review Gate Flow

```
produce (phase 1: acquire → analyze → direct)
  ↓
HUMAN REVIEW GATE
  • Shows storyboard / knowledge / script paths
  • Auto-runs proofread (Claude Haiku) — lists text issues
  • If issues: "uv run pipeline proofread run --project-id X --apply"
  ↓ (user edits storyboard if needed, then resumes)
produce --start-from tts  (phase 2: tts → compose)
```

With `--skip-review`, proofread fixes are applied automatically before TTS.

## Workflow Reference Diagram

**File:** `docs/workflows.html` — open with `xdg-open docs/workflows.html`.

Update rules: after completing any implementation, ask before editing. Changes that warrant asking: new component, status change, new skill integration, new stage, new commands. Bug fixes, config tweaks, and refactors do NOT need a diagram update.

### How to update `docs/workflows.html`

**Component Status table** — add/modify `<tr>` in `<tbody>` under `<h2>Component Status</h2>`:
```html
<tr>
  <td><span class="stage s-tts">TTS</span></td>
  <td>Component display name</td>
  <td><code>tool/path or API name</code></td>
  <td>$cost or free</td>
  <td><span class="badge b-stable">stable</span></td>
  <td>One-line description</td>
</tr>
```
Stage classes: `s-acquire` `s-analyze` `s-direct` `s-tts` `s-compose` `s-publish` `s-external` `s-monitor`
Badge classes: `b-stable` `b-new` `b-wip` `b-planned`

**Stage Flow diagram** — edit Mermaid block inside `<pre class="mermaid">`.

**Meta line** — update `Last updated:` date in `<div class="meta">`.

Natural-language triggers:
```
"open the workflow diagram"     → xdg-open docs/workflows.html
"update the workflow diagram"   → edit docs/workflows.html (confirm first)
"mark X as stable"              → update badge in status table
"add Y component"               → add row + node
```

## Budget Allocation ($50/month)

| Service | Monthly budget | What it covers |
|---------|---------------|----------------|
| Claude Sonnet API | ~$10 | ~100 story analyses + script adaptations |
| Edge-TTS | $0 | Unlimited narration (primary) |
| Google Cloud TTS Neural2 | $0 | 1M chars/month free tier (premium voice) |
| OpenAI Whisper API | ~$3 | ~500 min transcription (fallback) |
| OpenAI TTS | ~$5 | ~333K chars for special narration |
| YouTube Data API | $0 | 10K quota units/day |
| pytrends | $0 | Free Google Trends access |
| **Buffer** | ~$32 | Scaling headroom |

## Content Strategy

### Opportunity Detection Formula
```
Opportunity Score = (EN_views / target_locale_views) * portability_score
```
portability_score: visual intensity (bodycam/dashcam > talking head), self-contained narrative (clear arc > ongoing saga), universal emotions (justice/survival > local politics).

### Target Niches
- **zh-TW**: US bodycam, court/legal drama, scam exposes (few competitors, strong demand)
- **Japanese**: True crime deep dives, disaster/survival (cultural fascination, few creators)
- **Spanish (LatAm)**: Suspense narratives (huge audience, more competition — need quality edge)

### Video Structure
Hook (0-30s) → Context (30s-2min) → Rising Action (2-6min) → Climax (6-8min) → Aftermath + Resolution (8-10min) → Analysis (10-12min). Target: 12-18 minutes.

### Timing
Trending content must be ported within 48-72 hours of the EN original going viral.

## Edge-TTS Voice IDs

| Locale | Female | Male |
|--------|--------|------|
| zh-TW | `zh-TW-HsiaoChenNeural`, `zh-TW-HsiaoYuNeural` | `zh-TW-YunJheNeural` |
| ja-JP | `ja-JP-NanamiNeural` | `ja-JP-KeitaNeural` |
| es-MX | `es-MX-DaliaNeural` | `es-MX-JorgeNeural` |

## Prerecorded Voice Workflow

Drop scene recordings into `voices/prerecorded/<voice_id>/<scene_id>.wav`. The pipeline's `PrerecordedEngine` picks them up and falls back to Edge-TTS for missing scenes. See `scripts/record_voice.md`.

## CJK Subtitle Rendering

```bash
sudo apt install fonts-noto-cjk
ffmpeg -i input.mp4 -vf "subtitles=subs.srt:force_style='FontName=Noto Sans CJK TC,FontSize=24'" output.mp4
```
