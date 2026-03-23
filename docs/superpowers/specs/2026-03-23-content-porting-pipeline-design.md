# Content Porting Pipeline — Design Spec

**Date:** 2026-03-23
**Status:** Approved (brainstorming)

## 1. Problem Statement

Popular English-language YouTube content (bodycam footage, true crime, suspense/drama) has massive viewership, but equivalent content in zh-TW, Japanese, and Spanish (LatAm) markets is scarce. This represents a porting opportunity — not translation, but cultural adaptation: find what's trending in English, verify a market gap exists in the target locale, then create an original restructured video for that audience.

The system must:
- Detect market gaps automatically (EN views vs target-locale coverage)
- Produce ported videos with original scripts, TTS narration, and composed video
- Keep humans in the loop for creative decisions
- Learn from its own channel performance to improve future decisions
- Operate within a $50/month API budget

## 2. Architecture Overview

Three interconnected subsystems sharing a single SQLite database:

```
┌─────────────────────────────────────────────────────────────────┐
│  DISCOVERY ENGINE (src/discovery/)                              │
│  Monitor EN channels → Gap check vs target locale → Score →    │
│  Present ranked candidates to human                            │
│  Runs: daily cron + on-demand                                  │
├─────────────────────────────────────────────────────────────────┤
│  PRODUCTION PIPELINE (src/pipeline/)                            │
│  Acquire → Analyze → Scriptwrite → [Human] → TTS → Compose →  │
│  [Human] → Publish                                             │
│  Runs: triggered per selected candidate                        │
├─────────────────────────────────────────────────────────────────┤
│  OBSERVABILITY (src/observe/)                                   │
│  Collect YouTube Analytics → Content Knowledge Graph →         │
│  Correlate tags × metrics → Feed insights back to Discovery    │
│  and Scriptwriting                                             │
│  Runs: daily cron                                              │
└─────────────────────────────────────────────────────────────────┘
         ▲                    │                    │
         │         SQLite DB (output/pipeline.db)  │
         └────────────────────┴────────────────────┘
```

All three subsystems are accessed via a single Typer CLI with subcommand groups:
```
uv run pipeline discover ...
uv run pipeline produce ...
uv run pipeline observe ...
```

## 3. Data Model

### SQLite Tables

**candidates** — Written by Discovery Engine
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| source_url | TEXT | YouTube URL |
| source_channel | TEXT | Channel name/ID |
| title | TEXT | Original EN title |
| en_views | INTEGER | View count at discovery time |
| en_published_at | DATETIME | When EN video was published |
| target_locale | TEXT | zh-TW, ja, es-MX |
| locale_views | INTEGER | Best competing video's views |
| opportunity_ratio | REAL | en_views / locale_views |
| portability_score | REAL | Weighted visual + narrative + cultural |
| status | TEXT | new → selected → rejected → produced |
| discovered_at | DATETIME | When we found it |

**projects** — Written by Production Pipeline
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| candidate_id | FK → candidates | Source candidate |
| locale | TEXT | Target locale |
| stage | TEXT | Current stage: acquire / analyze / scriptwrite / tts / compose / publish |
| status | TEXT | in_progress / paused_for_review / completed / failed |
| work_dir | PATH | output/projects/{id}/ |
| context_json | TEXT | Serialized PipelineContext (for resume) |
| youtube_video_id | TEXT | Set after publish |
| created_at | DATETIME | |
| updated_at | DATETIME | |

**tags** — Written by Analyze stage + human edits
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| project_id | FK → projects | Which video |
| category | TEXT | niche / topic / story_element / tone / hook_style / entity |
| value | TEXT | e.g. "bodycam", "traffic-stop", "dramatic-hook" |
| source | TEXT | auto / human |

**metrics** — Written by Observability (daily poll)
| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| project_id | FK → projects | Which video |
| recorded_at | DATETIME | Snapshot time |
| views | INTEGER | Cumulative views |
| watch_time_hours | REAL | Total watch time |
| avg_view_duration_sec | REAL | Retention quality |
| ctr | REAL | Click-through rate |
| subscribers_gained | INTEGER | From this video |
| impressions | INTEGER | Times shown by YouTube |

### File System (per project)

```
output/
  pipeline.db
  projects/{project_id}/
    source/
      video.mp4
      transcript.srt
    analysis/
      structure.json         # Story beats, timestamps, emotional arc
      knowledge_graph.json   # Entities, relationships, conflicts
    script/
      script_zh-TW.md        # Adapted script (human-editable)
    audio/
      narration_zh-TW.mp3
    compose/
      final_zh-TW.mp4
    context.json              # Serialized PipelineContext
```

## 4. Discovery Engine

### Pipeline Flow

**Step 1: MONITOR** (daily)
- Channel Watch: poll curated EN channel list via YouTube Data API → detect uploads in last 24h
- Keyword Sweep (weekly): broad YouTube search for topic keywords, filter by published <7 days and views >50K
- Trend Signals: pytrends (Google Trends API) → detect rising search terms in target niches before they peak on YouTube
- Config: channel list, keywords, and trend topics defined in `configs/channels.toml`

**Step 2: GAP CHECK**
- For each EN video found, extract topic keywords from title
- Search YouTube in target locale for same topic
- Find best competing video in target locale
- Calculate opportunity ratio: `EN_views / locale_best_views`
- Threshold: ratio >10:1 = HIGH, 3:1-10:1 = MEDIUM, <3:1 = LOW (skip)

**Step 3: SCORE & RANK**
- Portability score (0-1), weighted:
  - visual_intensity (0.4): bodycam/dashcam=1.0, news=0.6, talking_head=0.2
  - narrative_completeness (0.3): clear arc=1.0, ongoing=0.3
  - cultural_portability (0.3): universal emotions=1.0, local politics=0.1
- Knowledge Graph boost: if topic tags match high-performing past videos, multiply by 1.2-1.5x
- Final score: `opportunity_ratio × portability_score × kg_boost`

**Step 4: PRESENT**
- Save to `candidates` table with status=new
- CLI displays ranked list with score, gap ratio, and KG boost info
- Human selects/rejects each candidate

### API Quota Budget (daily, 1 locale)
- Channel polls (20 channels): ~100 units
- Video stat lookups (50 videos): ~50 units
- Gap check searches (50 videos): ~5,000 units
- Weekly keyword sweep (10 keywords): ~1,000 units
- **Total: ~5,150 units/day** (51% of free 10K quota)

### Multi-locale quota scaling
Adding a second locale roughly doubles gap-check cost (~10,300 units/day = at quota limit). Mitigations: stagger locales across days (zh-TW Mon/Wed/Fri, ja Tue/Thu/Sat), reduce gap-check frequency, or prioritize locale with best ROI. Build zh-TW only first; add ja/es after validating the pipeline works.

### Source Modules
```
src/discovery/
  monitor.py       # ChannelMonitor + KeywordSweeper
  trends.py        # pytrends integration: rising search terms
  gap.py           # GapChecker: cross-locale search, opportunity ratio
  scorer.py        # CandidateScorer: portability + KG boost
  presenter.py     # CLI ranked list display, human selection UI
  config.py        # Discovery-specific config
```

## 5. Production Pipeline

### Stage Architecture

Each stage implements `PipelineStage.run(ctx: PipelineContext) -> PipelineContext`. After each stage, context is serialized to `context.json` for resume capability.

### Stage 1: ACQUIRE (~2 min, $0)
- **Input:** YouTube URL from selected candidate
- **Process:** yt-dlp downloads video (720p max); youtube-transcript-api extracts EN subtitles; faster-whisper as fallback if no subs
- **Output:** `ctx.video_path`, `ctx.transcript_path`, `ctx.transcript_text`

### Stage 2: ANALYZE (~$0.10, Claude Sonnet)
- **Input:** ctx.transcript_text
- **Process:**
  - Claude call 1: Story structure — narrative beats, key timestamps, emotional arc
  - Claude call 2: Knowledge graph — entities, relationships, conflicts, context needed for target audience
  - Auto-generate tags → write to `tags` table
- **Output:** `ctx.story_structure`, `ctx.knowledge_graph`, `ctx.clip_timestamps`

### Stage 3: SCRIPTWRITE (~$0.10, Claude Sonnet)
- **Input:** ctx.story_structure, ctx.knowledge_graph, target locale, KG insights from past videos
- **Process:** Claude writes a NEW script (not translation). System prompt includes locale-specific instructions, terminology glossary, video structure template, and "what elements worked" from KG correlations.
- **Output format:** Markdown with markers:
  ```
  [HOOK]
  [CLIP:01:23-01:35]
  這起事件發生在德州的一個小鎮...
  [OVERLAY:map:Texas]
  [CONTEXT]
  值班警員在深夜接到一通報案電話...
  ```
- **Output:** `ctx.script_path` (human-editable .md file)

### HUMAN GATE: Script Review & Edit
- Pipeline pauses with `status = paused_for_review`
- Human opens script in any editor, tweaks cultural nuances, adjusts [CLIP] references
- Resume: `uv run pipeline approve {project_id}`
- Expected: 20-40 min (core creative contribution)

### Stage 4: TTS ($0 edge-tts primary)
- **Input:** Approved script (narration text stripped of markers)
- **Process:** edge-tts generates audio per segment, concatenate with natural pauses, generate word-level timestamps for subtitle sync
- **Output:** `ctx.narration_path`, `ctx.subtitle_path`, `ctx.segment_timings`

### Stage 5: COMPOSE (~3 min, FFmpeg)
- **Input:** narration audio, subtitles, source video, clip timestamps, script overlay cues
- **Process (Strategy A — source clips + overlays):**
  1. Extract short clips (5-15s) at [CLIP:ts] references
  2. Generate overlay cards: title card, name cards, map screenshots, context text
  3. Interleave clips with overlay cards
  4. Mix narration audio track
  5. Burn CJK subtitles (Noto Sans CJK TC font)
  6. Encode final video (H.264, 1080p)
- **Output:** `ctx.final_video_path` (12-18 min, 1080p)
- **Future:** Strategy B (screenshot + Ken Burns), Strategy C (mixed media collage)

### HUMAN GATE: Final Video Review
- Watch video, approve or request re-render
- `uv run pipeline approve {project_id}` or `uv run pipeline reject {project_id} --reason "..."`
- Expected: 15 min

### Stage 6: PUBLISH (~$0.02, Claude Haiku)
- **Input:** final video, script, knowledge graph
- **Process:** Claude Haiku generates localized title/description/tags; YouTube Data API uploads; checks "Synthetic Content" disclosure box
- **Output:** `ctx.youtube_video_id`, project status → completed, triggers observability tracking

### Cost per Video
| Stage | Cost |
|-------|------|
| Acquire | $0 |
| Analyze | ~$0.10 |
| Scriptwrite | ~$0.10 |
| TTS (edge-tts) | $0 |
| Compose | $0 |
| Publish | ~$0.02 |
| **Total** | **~$0.22/video** |

At $50/month budget: **~225 videos/month theoretical max** (in practice limited by human review time, not API cost).

### Source Modules
```
src/pipeline/
  cli.py               # Typer CLI entry point
  config.py            # pydantic-settings
  models.py            # Shared Pydantic models
  orchestrator.py      # Stage chaining, state/resume
  stages/
    base.py            # PipelineStage ABC + PipelineContext dataclass
    acquire.py         # yt-dlp + transcript extraction
    analyze.py         # Claude API story structure + knowledge graph
    scriptwrite.py     # Claude API script adaptation
    tts.py             # TTS generation
    compose.py         # FFmpeg video composition
    publish.py         # Metadata generation + YouTube upload
  utils/
    ffmpeg.py          # FFmpeg command wrappers
    srt.py             # SRT/VTT parsing
```

## 6. Observability & Feedback Loop

### Component 1: Metrics Collector
- Runs daily via cron
- Polls YouTube Analytics API (free) for each published video
- Stores snapshots in `metrics` table
- Derived metrics computed on read: views_24h, views_48h, views_7d, views_30d, growth_rate, retention_ratio

### Component 2: Content Knowledge Graph
- Tags auto-generated during ANALYZE stage (niche, topic, story_element, tone, hook_style, entity)
- Production metadata added during pipeline (locale, duration, tts_voice, source_channel, time_to_port_hours)
- Stored in flat `tags` table — simple, queryable, no graph DB overhead

### Component 3: Correlation Engine
- SQL queries joining `tags × metrics` to find patterns
- No ML needed at this scale (~30-50 videos/month) — just aggregations
- Example: "Among zh-TW bodycam videos, which tag combos correlate with >20K views at 48h?"

### Feedback Outputs
1. **→ Discovery scoring:** high-performing tag combos become `kg_boost` multipliers
2. **→ Scriptwriting prompts:** top elements injected into Claude system prompt
3. **→ Human dashboard:** CLI displays channel health, best/worst tags, AI-powered suggestions

### Source Modules
```
src/observe/
  collector.py      # YouTube Analytics API polling
  correlator.py     # Tag × metrics queries, boost calculation
  dashboard.py      # CLI rich-table channel health display
  reporter.py       # Periodic summary reports
  suggest.py        # Claude Haiku → suggestions
```

## 7. Error Handling & Resilience

### Stage-level resume
Each stage either completes fully or fails. On failure, the stage is re-run from scratch on `resume` (no mid-stage checkpointing). The `context.json` is only updated after a stage succeeds.

### External service failures
| Service | Failure mode | Handling |
|---------|-------------|----------|
| YouTube Data API | 403 quota exceeded | Stop discovery run, log remaining quota, retry next day |
| YouTube Data API | 429 rate limit | Exponential backoff (1s, 2s, 4s, max 60s), max 5 retries |
| yt-dlp | Geo-blocked / age-restricted / deleted | Mark candidate as `rejected` with reason, skip to next |
| youtube-transcript-api | No transcript available | Fall back to faster-whisper (local) or OpenAI Whisper API |
| Claude API | 429 rate limit | Exponential backoff, max 3 retries |
| Claude API | Content filtered | Log warning, mark project as `failed`, human investigates |
| edge-tts | Service unavailable | Retry 3x, then fall back to Google Cloud TTS Neural2 |
| FFmpeg | Encoding failure | Log full stderr, mark project as `failed` |
| YouTube Upload API | Auth expired | Prompt user to re-authenticate, pause pipeline |

### Idempotency
Re-running a completed stage overwrites its output files but does not create duplicates in the database. The `projects.stage` field is the single source of truth for progress.

## 8. Authentication & Secrets

### Required credentials
| Credential | Used by | How to obtain |
|------------|---------|---------------|
| YouTube Data API key | Discovery (search, stats) | Google Cloud Console → API key |
| YouTube OAuth 2.0 | Publish (upload), Observe (analytics) | Google Cloud Console → OAuth client ID → user consent flow |
| Anthropic API key | Analyze, Scriptwrite, Publish, Suggest | console.anthropic.com |
| Google Cloud TTS key | TTS (premium fallback) | Google Cloud Console → service account (optional) |

### Storage
- All secrets in `.env` file (gitignored) or environment variables
- Never in config TOML files or committed code
- pydantic-settings loads from env vars with `PIPELINE_` prefix: `PIPELINE_ANTHROPIC_API_KEY`, `PIPELINE_YOUTUBE_API_KEY`, etc.
- `.env.example` committed with placeholder values for documentation

### OAuth 2.0 setup (one-time)
YouTube upload and analytics require OAuth with channel owner consent. First run triggers browser-based auth flow, stores refresh token in `.env`. Token auto-refreshes thereafter.

## 9. PipelineContext Schema

```python
@dataclass
class PipelineContext:
    # Set at creation
    project_id: int
    candidate_id: int
    source_url: str
    locale: str                          # zh-TW, ja, es-MX
    work_dir: Path                       # output/projects/{project_id}/

    # Stage 1: Acquire
    video_path: Path | None = None
    transcript_path: Path | None = None
    transcript_text: str | None = None

    # Stage 2: Analyze
    story_structure: dict | None = None  # beats, timestamps, emotional arc
    knowledge_graph: dict | None = None  # entities, relationships, conflicts
    clip_timestamps: list[tuple[float, float]] | None = None

    # Stage 3: Scriptwrite
    script_path: Path | None = None

    # Stage 4: TTS
    narration_path: Path | None = None
    subtitle_path: Path | None = None    # .srt generated from TTS word timings
    segment_timings: list[dict] | None = None

    # Stage 5: Compose
    final_video_path: Path | None = None

    # Stage 6: Publish
    youtube_video_id: str | None = None
```

## 10. Script Marker Format

The scriptwrite stage outputs markdown with embedded markers that the compose stage parses.

### Supported markers
| Marker | Syntax | Compose action |
|--------|--------|---------------|
| Section | `[HOOK]`, `[CONTEXT]`, `[RISING]`, `[CLIMAX]`, `[AFTERMATH]`, `[ANALYSIS]` | Structure markers; used for chapter timestamps |
| Clip reference | `[CLIP:MM:SS-MM:SS]` | Extract segment from source video at given timestamps |
| Overlay | `[OVERLAY:type:content]` | Generate overlay card |
| | `[OVERLAY:map:Texas]` | Map screenshot (static image) |
| | `[OVERLAY:namecard:John Smith, 32, Officer]` | Name/role card |
| | `[OVERLAY:text:重要背景資訊]` | Text card with content |
| | `[OVERLAY:title:事件標題]` | Title card |
| Pause | `[PAUSE:2s]` | Insert silence (for dramatic effect) |

Plain text between markers is narration (sent to TTS).

### Subtitle generation flow
1. TTS stage splits script into narration segments (text between markers)
2. edge-tts generates audio + word-level timing data per segment
3. Timings are compiled into an SRT file (`ctx.subtitle_path`)
4. Compose stage burns SRT into video using FFmpeg subtitle filter with Noto Sans CJK TC font

## 11. Tech Stack

| Component | Tool | Why |
|-----------|------|-----|
| Package manager | uv | Fast, PEP 621, built-in Python version mgmt |
| CLI | Typer | Type-hint-driven, Rich integration |
| Config | pydantic-settings | Layered: CLI > env > .env > TOML > defaults |
| Database | SQLite | $0, no infra, sufficient for hundreds of videos |
| YouTube download | yt-dlp | Industry standard |
| Transcript extraction | youtube-transcript-api | Free, no API key |
| Transcription fallback (local) | faster-whisper | 4x faster than openai-whisper, no cost |
| Transcription fallback (cloud) | OpenAI Whisper API | $0.006/min, no GPU needed |
| Story analysis + scriptwriting | Claude Sonnet API | Best reasoning for narrative work |
| Metadata generation | Claude Haiku API | Cheapest per token |
| TTS (primary) | edge-tts | Free, covers all target locales |
| TTS (premium) | Google Cloud TTS Neural2 | 1M chars/month free tier |
| TTS (special) | OpenAI TTS | $15/1M chars, highest naturalness |
| Video composition | FFmpeg via ffmpeg-python | Industry standard |
| Trend monitoring | YouTube Data API v3 + pytrends | Free tiers sufficient |
| Subtitle parsing | pysrt | Simple SRT read/write |
| Logging | structlog | Structured JSON per stage |
| Linting | Ruff | Replaces black + isort + flake8 |
| Testing | pytest | Markers: slow, integration, network |

## 8. YouTube Policy Compliance

- Each video has a NEW script with original analysis and cultural context (not translation)
- Source clips used in 5-15 second segments, never continuous stretches
- Original content (narration, graphics, analysis) is 50-70%+ of final video
- "Altered or Synthetic Content" checkbox enabled for AI voiceover (mandatory 2026)
- Source credits in description + on-screen overlay when source footage appears

## 9. CLI Interface

```bash
# Discovery
uv run pipeline discover --region US --target-locale zh-TW
uv run pipeline discover --trending --days 7
uv run pipeline discover select {candidate_id}
uv run pipeline discover reject {candidate_id}

# Production (normal flow: from selected candidate)
uv run pipeline produce {candidate_id} --locale zh-TW
# Production (ad-hoc: bypass discovery, useful for dev/testing)
uv run pipeline produce --url "https://youtube.com/watch?v=..." --locale zh-TW
uv run pipeline produce resume {project_id}
uv run pipeline produce approve {project_id}
uv run pipeline produce reject {project_id} --reason "..."
uv run pipeline produce status {project_id}

# Observability
uv run pipeline observe collect
uv run pipeline observe dashboard
uv run pipeline observe correlate
uv run pipeline observe report --days 30
uv run pipeline observe suggest
```

## 10. Decisions Made During Brainstorming

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Source content discovery | Hybrid (curated channels + keyword sweeps) | Best coverage; build channel-based first, add keyword sweeps later |
| Human involvement at script gate | Review & Edit (Option 2) | Human tweaks cultural nuances; AI output is first draft not final |
| Human involvement at video gate | Review & Approve (Option 1) | If script is good, video composition is mechanical |
| Knowledge graph storage | SQLite + JSON tags | Zero cost, no infra, sufficient for hundreds of videos |
| Video composition strategy | Strategy A (source clips + overlays) | Automatable with FFmpeg; upgrade to mixed media later |
| System architecture | Three-subsystem split in single package | Clean separation via Typer subcommand groups, shared SQLite DB |
| Target locale priority | zh-TW first | Fewest competitors, strong demand; validate before expanding |

## 15. Testing Strategy

### Test categories (pytest markers)
| Marker | What it tests | External deps | When to run |
|--------|--------------|---------------|-------------|
| (default) | Pure logic: scoring, parsing, config | None | Every commit |
| `slow` | Whisper model loading, large file processing | Local models | Pre-release |
| `integration` | FFmpeg composition, full stage pipelines | FFmpeg binary | Pre-release |
| `network` | YouTube API, Claude API, edge-tts | Network + API keys | Manual / CI nightly |

### Mocking strategy per stage
- **Discovery:** Mock YouTube Data API responses with fixture JSON. Test scoring math, gap ratio calculation.
- **Acquire:** Mock yt-dlp and youtube-transcript-api. Test fallback logic (no subs → whisper).
- **Analyze:** Mock Claude API. Assert prompt structure, test JSON parsing of response.
- **Scriptwrite:** Mock Claude API. Test marker format in output, locale-specific prompt injection.
- **TTS:** Mock edge-tts. Test segment splitting, subtitle timing generation.
- **Compose:** Test FFmpeg command generation (not execution). Integration tests with short clips for actual rendering.
- **Orchestrator:** Stub all stages. Test chaining, resume from failure, human gate pausing.

### Fixtures
- `tests/fixtures/sample.srt` — short subtitle file for parsing tests
- `tests/fixtures/sample_audio.wav` — 5-second clip for TTS tests
- `tests/fixtures/transcript.json` — sample youtube-transcript-api output
- `tests/fixtures/claude_response.json` — sample Claude API analysis/scriptwrite responses

## 16. System Dependencies

```bash
# Required
sudo apt install ffmpeg fonts-noto-cjk

# Python
uv sync  # installs all Python dependencies from pyproject.toml

# Optional (for local whisper)
# Requires CUDA-capable GPU with ≥6GB VRAM for large-v3 model
```
