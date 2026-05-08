# AGENTS.md — content-creation workspace

This is the home directory for the content-creation pipeline — a YouTube porting system
that finds trending EN videos and rebuilds them as original zh-TW (and eventually ja/es)
content for under-served markets.

Treat this file as the Codex table of contents for the workspace. The repository's durable
knowledge base lives in the structured `docs/` directory, which is the system of record for
specs, plans, workflows, and future work. Keep this file as a concise map to that knowledge
rather than duplicating the docs.

## Ultimate Goal

**Every task in this project serves one purpose: produce the highest-quality video possible.** Quality is the north star — not speed, not automation coverage, not code elegance. Claude and Codex must keep this in mind on every task: script choices, pacing decisions, image prompts, narration edits, and render settings all exist to make the final video better for the viewer.

## Session Startup

Before anything else:
1. Read `~/.openclaw/workspace/SOUL.md` — who you are
2. Read `~/.openclaw/workspace/USER.md` — who you're helping
3. Read `CLAUDE.md` — full project architecture, commands, and design decisions
4. Read `~/.openclaw/workspace/memory/` recent files for conversation continuity

## Project at a Glance

```
output/projects/<ID>/          ← one directory per produced video
  source/                      ← downloaded video, transcript, keyframes
  knowledge.json               ← facts, entities, timeline, context bridges
  storyboard.json              ← scene-by-scene production plan
  script/script_zh-TW.md       ← derived narration script
  audio/                       ← TTS audio per scene
  compose/final_zh-TW.mp4      ← rendered output
  metadata.json                ← YouTube title, tags, description
  context.json                 ← pipeline state (locale, project_id, stage)
```

## Knowledge Base Map

Use `docs/` as the canonical project memory before making design-sensitive changes:

- `docs/superpowers/specs/` — design specs and architectural intent
- `docs/superpowers/plans/` — implementation plans and historical execution context
- `docs/workflows.md` and `docs/workflows.html` — workflow model and visual diagram
- `docs/future-tasks.md` — deferred work and follow-up ideas

`AGENTS.md` should stay as the Codex-facing map. When new durable project knowledge is created,
place it under `docs/` and add a pointer here only when Codex needs faster orientation.

## Active Pipeline CLI

All commands run from this directory with `uv run`:

```bash
# Production
uv run pipeline produce <URL> --locale zh-TW          # full pipeline
uv run pipeline produce <URL> --project-id <ID> --start-from tts  # resume from TTS

# Inspection
uv run pipeline storyboard show                        # list all scenes
uv run pipeline storyboard show --scene <id>           # one scene detail
uv run pipeline storyboard recordings --voice tim-zhtw

# Edit + Re-render
uv run pipeline storyboard set <scene_id> narration="新文字"
uv run pipeline compose rescene --project-id <ID> --scene <id>
uv run pipeline compose reburn --project-id <ID>

# Publish
uv run pipeline publish <project-id>
uv run pipeline metadata show --work-dir output/projects/<ID>
uv run pipeline metadata set title="..." --work-dir output/projects/<ID>
```

## Skills Available

Skills in `skills/` are auto-loaded. Use them for pipeline operations:
- `produce` — full pipeline from URL to video
- `status` — check project state and artifacts
- `storyboard` — view/edit storyboard scenes
- `render` — TTS + compose from existing storyboard
- `publish` — YouTube upload workflow
- `evaluate-video` — score a video for porting potential
- `knowledge` — view/edit the knowledge base
- `scene-update` — fix narration, overlays, or audio in a scene
- `shorts` — generate a Shorts storyboard
- `voice-variant` — build a variant with a different voice

## Skills → OpenClaw Tool Mapping

Skills in `skills/` are written with Claude Code terminology. When a loaded skill references
Claude Code concepts, translate to OpenClaw equivalents:

| Claude Code concept | OpenClaw equivalent |
|---|---|
| "dispatch a subagent" / `Agent` tool | `sessions_spawn` with `context: "isolated"` |
| `subagent_type=general-purpose` | Default sub-agent spawn (no special runtime) |
| `subagent_type=Explore` | `sessions_spawn` with a read-only task prompt |
| `subagent_type=Plan` | `sessions_spawn` with a planning-only task prompt |
| "invoke superpowers:dispatching-parallel-agents" | Spawn multiple `sessions_spawn` calls in parallel, aggregate results |
| "invoke superpowers:code-reviewer" | `sessions_spawn` with a code-review task prompt |

Sub-agents use `agents.defaults.subagents.model` (currently `openai-codex/gpt-5.5`) and get
up to 15 min timeout. They start with isolated context — the task prompt must be self-contained.
Results are announced back to this session automatically.

For heavy visual review tasks (reading many frames), prefer `sessions_spawn` to keep the main
session context clean. The spawned agent reads frame files from disk and reports issues.

## Key Rules

- Working directory is `/home/tim-huang/content-creation`
- Package manager is `uv` — always `uv run` not `python` directly
- Never commit to master without user confirmation
- Don't update `docs/workflows.html` without asking first
- Output goes to `output/projects/` (gitignored)
