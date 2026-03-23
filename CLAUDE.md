# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**content-creation** is a YouTube content porting pipeline. "Porting" means: find what's trending in English → cross-check if the zh-TW (or other locale) market has a gap → create an original, restructured video for that market using the source as reference material.

This is NOT translation/dubbing. It's closer to what the zh-TW community calls 搬運 — taking a concept that works in one market, researching it independently, and rebuilding it as original content for another audience. The pipeline automates the mechanical parts (transcript extraction, TTS, video composition) while keeping humans in the loop for creative decisions (which stories to port, how to adapt the narrative).

**Target locales (priority order):** zh-TW → Japanese → Spanish (Latin American). Start with zh-TW; expand only after validating quality.

**Budget constraint:** $50/month for all paid APIs.

## The Porting Workflow

```
Phase 1: DISCOVER (automated)
  YouTube Data API + pytrends → find trending EN videos
  Cross-check target locale → calculate opportunity ratio
  (EN views / target-lang views on same topic > 10:1 = high opportunity)
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

**1. Discovery Engine** (`src/discovery/`) — finds and scores porting candidates
- Monitors trending EN channels via YouTube Data API v3 + pytrends
- Cross-references target-locale YouTube to find gaps
- Scores candidates and presents ranked list to human
- Runs on a schedule (daily or on-demand)

**2. Production Pipeline** (`src/pipeline/`) — produces the ported video
- Linear stage pipeline: each stage implements `PipelineStage.run(ctx) -> ctx`
- `PipelineContext` dataclass carries mutable state between stages
- Serializable context enables resuming from last successful stage
- Human checkpoints at: story selection, script review, final video review

**3. Observability** (`src/observe/`) — learns what works
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
    scorer.py            # Opportunity scoring (gap ratio, portability, KG boost)
    presenter.py         # CLI ranked list display, human selection
    config.py            # Discovery-specific config
  pipeline/              # Video production pipeline
    cli.py               # Typer CLI entry point
    config.py            # pydantic-settings (env → .env → TOML → defaults)
    models.py            # Shared Pydantic models
    orchestrator.py      # Chains stages, handles state/resume
    stages/
      base.py            # PipelineStage ABC + PipelineContext dataclass
      acquire.py         # yt-dlp download + transcript extraction
      analyze.py         # Claude API story structure + knowledge graph
      scriptwrite.py     # Claude API script adaptation (NOT translation)
      tts.py             # TTS generation (edge-tts, Google Cloud, OpenAI)
      compose.py         # FFmpeg video composition
      publish.py         # Metadata generation + YouTube upload
    utils/
      ffmpeg.py          # FFmpeg command wrappers
      srt.py             # SRT/VTT parsing
  observe/               # Observability & feedback loop
    collector.py         # YouTube Analytics API polling
    correlator.py        # Tag × metrics queries, boost calculation
    dashboard.py         # CLI rich-table channel health display
    reporter.py          # Periodic summary reports
    suggest.py           # Claude Haiku → next-video suggestions
tests/
  unit/                  # Mock external APIs, test logic in isolation
  integration/           # Tests requiring FFmpeg binary
  fixtures/              # Sample .srt files, short audio clips
configs/                 # TOML presets per locale/workflow
scripts/                 # One-off helpers (model downloads, backfill)
output/                  # Default output dir (gitignored)
docs/superpowers/specs/  # Design specs
```

### Key Design Decisions

- **Discovery and Production are separate subsystems** — discovery runs continuously to build a candidate queue; production is triggered per-video
- **"scriptwrite" not "translate"** — the script adaptation stage writes a NEW script inspired by the source, not a translation. This is the core creative/value-add step.
- **Human-in-the-loop at 3 gates**: story selection, script review, final video review
- **PipelineContext serialization** enables resume from any stage after failure or human review pause
- **TTS abstraction** — swap between edge-tts (free), Google Cloud TTS, or OpenAI TTS via config

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
| Subtitle parsing | **pysrt** | Simple SRT read/write |
| Logging | **structlog** | Structured JSON per stage |
| Linting/formatting | **Ruff** | Replaces black + isort + flake8 |
| Testing | **pytest** | Markers: `slow`, `integration`, `network` |

## Commands

```bash
# Setup
uv sync                                    # Install all dependencies
uv run pipeline --help                     # Show CLI help

# Discovery
uv run pipeline discover --region US --target-locale zh-TW  # Find porting candidates
uv run pipeline discover --trending --days 7                # Trending last 7 days

# Production pipeline
uv run pipeline produce <video-url> --locale zh-TW          # Full pipeline for one video
uv run pipeline acquire <video-url>                          # Download + extract only
uv run pipeline analyze <transcript-path>                    # Story structure only
uv run pipeline scriptwrite <analysis-path> --locale zh-TW   # Generate adapted script
uv run pipeline tts <script-path> --locale zh-TW             # Generate narration
uv run pipeline compose <project-dir>                        # Final video composition

# Testing
uv run pytest                              # All tests
uv run pytest tests/unit/                  # Unit tests only
uv run pytest -m "not slow and not network" # Fast tests only
uv run pytest tests/unit/test_scriptwrite.py # Single test file
uv run pytest -k "test_story_structure"    # Single test by name

# Lint & format
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
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

## YouTube Policy Compliance

YouTube's "inauthentic content" policy (renamed July 2025) targets mass-produced, template-like content. Our content must pass these bars:

- **Not just translation** — each video is a new script with original analysis and cultural context
- **Significant original value** — narration, commentary, graphics, restructured narrative
- **Source clips used sparingly** — 5-15 second segments, never continuous stretches
- **Synthetic content disclosure** — must check "Altered or Synthetic Content" box for AI-generated voiceover (mandatory 2026 policy)
- **Credit sources** — in description + on-screen overlay when source footage appears

## Content Strategy

### Opportunity Detection Formula
```
Opportunity Score = (EN_views / target_locale_views) * portability_score
```
Where `portability_score` considers: visual intensity (bodycam/dashcam > talking head), self-contained narrative (clear arc > ongoing saga), universal emotions (justice/survival > local politics).

### Target Niches (by locale)
- **zh-TW**: US bodycam, court/legal drama, scam exposes (few competitors, strong demand)
- **Japanese**: True crime deep dives, disaster/survival (cultural fascination, few creators)
- **Spanish (LatAm)**: Suspense narratives (huge audience, more competition — need quality edge)

### Video Structure
Hook (0-30s, most dramatic moment out of context) → Context (30s-2min, map + people + setting) → Rising Action (2-6min) → Climax (6-8min) → Aftermath + Resolution (8-10min) → Analysis (10-12min). Target: 12-18 minutes.

### Timing
Trending content must be ported within 48-72 hours of the EN original going viral. The discovery engine's job is to catch this window.

## Edge-TTS Voice IDs

| Locale | Female | Male |
|--------|--------|------|
| zh-TW | `zh-TW-HsiaoChenNeural`, `zh-TW-HsiaoYuNeural` | `zh-TW-YunJheNeural` |
| ja-JP | `ja-JP-NanamiNeural` | `ja-JP-KeitaNeural` |
| es-MX | `es-MX-DaliaNeural` | `es-MX-JorgeNeural` |

## CJK Subtitle Rendering

```bash
sudo apt install fonts-noto-cjk
ffmpeg -i input.mp4 -vf "subtitles=subs.srt:force_style='FontName=Noto Sans CJK TC,FontSize=24'" output.mp4
```

## Script Adaptation Prompting

When using Claude API for script adaptation (not translation), always:
- zh-TW: "Write in Traditional Chinese (zh-TW), Taiwan usage conventions. Explain US-specific context (legal system, geography, policing norms) that Taiwanese audiences need."
- Japanese: "Write in Japanese. Specify appropriate keigo level. Add cultural context bridging US and Japanese norms."
- Spanish: "Write in Latin American Spanish (specify country variant if relevant). Explain US cultural context."
- Include a terminology glossary in system prompts for series consistency
- The script should be a NEW narrative, not a translation — restructure for the target audience's storytelling preferences
