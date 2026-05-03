# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Full reference docs:** `README.md` — tech stack, commands, workflows, voice IDs, channel config.

## Project Identity

**content-creation** is a YouTube content porting pipeline: find trending EN content → cross-check target locale for gaps → create original, restructured video for that market. This is 搬運 (independent research + rebuild), NOT translation/dubbing.

**Target locales:** zh-TW → Japanese → Spanish (Latin American). Start with zh-TW.
**Budget constraint:** $50/month for all paid APIs.

**Codex guard (token budget):** Codex is installed and authenticated on this machine — `codex:setup` is a one-time check, never reload it. `gpt-5-4-prompting` loads inside codex subagents automatically — never load it in the main session. When dispatching to codex, go straight to `codex:codex-rescue` without loading setup or prompting skills first.

## Architecture

Three subsystems:
1. **Discovery Engine** (`src/discovery/`) — finds and scores porting candidates via YouTube Data API + pytrends
2. **Production Pipeline** (`src/pipeline/`) — linear stage pipeline (`PipelineStage.run(ctx) -> ctx`), serializable `PipelineContext` for resume
3. **Observability** (`src/observe/`) — polls YouTube Analytics, correlates tags × metrics, feeds insights back to discovery/scoring

Human-in-the-loop at 3 gates: story selection → script review → final video review.
Full directory tree in README.md.

## Key Design Decisions (runtime rules)

- **"scriptwrite" not "translate"** — the script adaptation stage writes a NEW script inspired by the source, not a translation. This is the core creative/value-add step.
- **Publish is always explicit** — `PublishStage` is never in the orchestrator auto-chain. Every upload requires an explicit `pipeline publish <id>` call after human review.
- **Idempotent upload** — `PipelineContext` tracks `youtube_video_id`, `thumbnail_uploaded`, `disclosure_set`. Re-running `publish` resumes from the last successful phase.
- **TTS abstraction** — swap between edge-tts (free), Google Cloud TTS, or OpenAI TTS via config. Voice IDs in README.md.
- **Discovery and Production are separate subsystems** — discovery runs continuously; production triggered per-video.

## Skills (project plugin)

Project skills at `skills/<name>/SKILL.md`, registered via `.claude-plugin/` manifest as `content-creation:<skill>`.

**One-time activation per machine:**
```
/plugin marketplace add /home/tim-huang/content-creation
/plugin install content-creation@content-creation-local
```

## Pipeline Commands

Essential commands only. Full reference + natural-language triggers in README.md.

```bash
# Discovery
uv run pipeline discover --region US --target-locale zh-TW
uv run pipeline discover --trending --days 7

# Production
uv run pipeline produce <video-url> --locale zh-TW [--niche parenting|none]
uv run pipeline produce <video-url> --locale zh-TW --start-from tts  # resume after review gate

# Storyboard
uv run pipeline storyboard show [--scene scene_003]
uv run pipeline storyboard set scene_003 narration="新文字"

# Compose iteration (variant-focus workflow)
uv run pipeline compose set-variant --project-id <ID> --variant subtitles_no_overlay
uv run pipeline compose rescene --project-id <ID> --scene s9
uv run pipeline compose reburn --project-id <ID>
# Safety: rescene errors if --scene covers >50% storyboard. Use reburn for wide rebuilds.
# Overlay text appears ONLY in overlay variants; use visual_text for no_overlay visibility.

# Proofreading
uv run pipeline proofread run --project-id <ID> [--apply]

# Visual review
uv run pipeline visual-review extract-frames --project-id <ID>

# Publish (see README.md for full publish/metadata/outro commands)
uv run pipeline publish <project-id> [--profile <name>] [--dry-run]
uv run pipeline publish status <project-id> [--remote]

# Dashboard
./scripts/start-dashboard.sh [--local-only]

# Testing
uv run pytest; uv run ruff check src/ tests/; uv run mypy src/
```

## Review Gate Flow

```
produce (phase 1: acquire → analyze → direct)
  ↓
HUMAN REVIEW GATE
  • Auto-runs proofread (Claude Haiku) — lists text issues
  • If issues found: "uv run pipeline proofread run --project-id X --apply"
  ↓ (user edits storyboard if needed, then resumes)
produce --start-from tts  (phase 2: tts → compose)
```

With `--skip-review`, proofread fixes are applied automatically before TTS.

## Channel Config + Niche Routing

Profiles in `configs/youtube_channels.toml` (committed). Tokens in `~/.config/content-creation/youtube/<profile>.json` (mode 0600).

**Niche auto-detection**: `produce --locale zh-TW` → looks up routing → auto-selects if exactly one niche for that locale; errors if ambiguous; warns if none. Override with `--niche` or opt-out with `--niche none`.

**Metadata generation**: `DirectStage` emits `metadata.json` via Claude + channel's `voice_guide`. Skipped when niche is `none`.

**Three-phase upload**: A) `videos.insert` → B) `thumbnails.set` → C) `videos.update` with disclosure. Each phase persisted — partial failure resumes cleanly.

Full channel config, publish, metadata, and outro details in README.md.

## Workflow Diagram

**File:** `docs/workflows.html` — open with `xdg-open docs/workflows.html`. After any implementation, **ask before updating**. Update rules + HTML patterns in README.md.

## Budget Allocation ($50/month)

| Service | Budget | Coverage |
|---------|--------|----------|
| Claude Sonnet API | ~$10 | ~100 story analyses + scripts |
| Edge-TTS | $0 | Unlimited narration (primary) |
| Google Cloud TTS Neural2 | $0 | 1M chars/month free tier |
| OpenAI Whisper API | ~$3 | ~500 min transcription |
| OpenAI TTS | ~$5 | ~333K chars special narration |
| YouTube Data API | $0 | 10K quota units/day |
| pytrends | $0 | Free |
| **Buffer** | ~$32 | Scaling headroom |

## YouTube Policy Compliance

These are runtime rules that shape all output:

- **Not just translation** — each video is a new script with original analysis and cultural context
- **Significant original value** — narration, commentary, graphics, restructured narrative
- **Source clips used sparingly** — 5-15 second segments, never continuous stretches
- **Synthetic content disclosure** — must check "Altered or Synthetic Content" box for AI voiceover (mandatory 2026 policy)
- **Credit sources** — in description + on-screen overlay when source footage appears

## Content Strategy

- **Opportunity Score** = (EN_views / target_locale_views) × portability_score (visual intensity, narrative completeness, cultural portability)
- **Target niches**: zh-TW (bodycam/court/scam), Japanese (true crime/disaster), Spanish LatAm (suspense)
- **Video**: 12-18 min, Hook→Context→Rising Action→Climax→Aftermath→Analysis
- **Timing**: Port within 48-72 hours of EN original going viral

Full strategy details in README.md.

## Script Adaptation Prompting

When using Claude API for script adaptation, always:
- zh-TW: "Write in Traditional Chinese (zh-TW), Taiwan usage conventions. Explain US-specific context (legal system, geography, policing norms) that Taiwanese audiences need."
- Japanese: "Write in Japanese. Specify appropriate keigo level. Add cultural context bridging US and Japanese norms."
- Spanish: "Write in Latin American Spanish (specify country variant if relevant). Explain US cultural context."
- Include a terminology glossary in system prompts for series consistency
- The script should be a NEW narrative, not a translation — restructure for the target audience's storytelling preferences

## Quick Reference

| Need | Where |
|------|-------|
| Full command list + triggers | README.md |
| Tech stack table | README.md |
| Directory structure | README.md |
| Voice IDs (edge-tts) | README.md |
| CJK subtitle rendering | README.md |
| Prerecorded voice workflow | README.md |
| Channel config TOML | README.md |
| Outro build commands | README.md |
| Publish/metadata full workflow | README.md |
| Design specs | `docs/superpowers/specs/` |
