# Shared Agent Memory Design

**Date:** 2026-05-13  
**Status:** Approved  
**Scope:** `content-creation` project (extensible to other projects in v2)

## Goal

Give Claude and Codex a shared, project-scoped memory store so that what either agent learns — from Tim's corrections, session work, or auto-synthesis — is available to the other agent at the start of its next session. This mirrors the `skill-sync` pattern already in place for skills.

## Storage Layout

```
<project>/.agent-memory/
├── MEMORY.md                    ← index only; loaded by both agents every session
├── config.yml                   ← budget and archive rules
├── feedback/                    ← Tim's corrections and behavioral guidance
│   └── <slug>.md
├── project/                     ← project facts, goals, constraints
│   └── <slug>.md
├── reference/                   ← pointers to external resources
│   └── <slug>.md
├── user/                        ← Tim's profile, expertise, preferences
│   └── <slug>.md
├── codex/
│   └── codex-learnings.md       ← Codex-extracted preferences + reusable knowledge
└── archive/
    └── YYYY/                    ← entries rotated out when live count exceeds cap
```

### `MEMORY.md` — index contract

- One line per live entry: `- [type/slug.md](type/slug.md) — ≤12-word description`
- Hard cap: **80 lines / 35 live entries / ≤500 tokens**
- Claude loads first 200 lines at session start (system constraint); 80-line cap keeps it well inside
- Codex reads it explicitly via Session Startup instruction in `AGENTS.md`

### Topic file format (shared across agents)

```markdown
---
id: <kebab-slug>
name: <short human name>
description: <one sentence — what this memory is for>
type: feedback | project | reference | user | codex
source_agents: [claude] | [codex] | [claude, codex]
updated: YYYY-MM-DD
---

<concise rule or fact — lead sentence>

**Why:** <reason or incident that produced this>

**How to apply:** <when and where this kicks in>
```

Existing Claude memories (currently stored without typed subdirs) migrate to this format during `memory-sync init`. Content is preserved; only frontmatter and path change.

### `config.yml`

```yaml
startup_index:
  max_lines: 80
  max_live_entries: 35
topics:
  required_frontmatter: [id, name, description, type, updated]
archive:
  when_live_entries_over: 35
  destination: archive/YYYY/
  keep_archive_pointer: true   # one-liner stub remains in MEMORY.md pointing to archive
normalization:
  model: claude-haiku-4-5-20251001
  cost_per_bullet: ~$0.001
```

## How Each Agent Reads and Writes

### Claude

**Read:** `autoMemoryDirectory` cannot be set per-project (security restriction — accepted only from user/policy settings). Instead, a one-time init step replaces Claude's native memory directory with a symlink:

```
~/.claude/projects/-home-tim-huang-content-creation/memory/
  → /home/tim-huang/content-creation/.agent-memory/   (symlink)
```

Claude writes natively and sees nothing different. Zero ongoing overhead.

**Write:** Claude's existing auto-memory behavior continues unchanged. It writes topic files directly to `.agent-memory/` (via the symlink) using its established memory format, which matches the shared topic file schema above.

### Codex

**Read:** Add one line to `AGENTS.md` under `## Session Startup`:

```
5. Read `.agent-memory/MEMORY.md` — shared agent memories (feedback, project facts, preferences)
```

Codex reads the index explicitly at session start. This is the established pattern in `AGENTS.md` (already reads `~/.openclaw/workspace/memory/` the same way). Topic files are read on-demand when Codex needs detail.

**Write:** `memory-sync extract-codex` runs after each Codex session. It:
1. Parses `~/.codex/memories/rollout_summaries/` for entries with `cwd=/home/tim-huang/content-creation` newer than the last run timestamp
2. Extracts `## User preferences` and `## Reusable knowledge` bullets from each
3. Calls Claude Haiku to normalize each bullet into the shared topic file format
4. Appends to `codex/codex-learnings.md` (deduplicating by semantic similarity)
5. Updates `MEMORY.md` index if the codex entry is new

Codex's raw `MEMORY.md` (742 lines, ~19,500 tokens) is **never imported**. Only distilled bullets (~145 today, ~20 tokens each) flow to `.agent-memory/`.

## `memory-sync` Script

Lives at `~/.claude/bin/memory-sync` (shared bin, available in all projects).

```
memory-sync init                  one-time: migrate + symlink + create config.yml
memory-sync extract-codex         pull + normalize new Codex learnings
  --project <path>                target project (default: cwd)
memory-sync doctor                report: token count, line count, stale entries, frontmatter issues
memory-sync doctor --fix          auto-archive oldest entries when live count > 35
memory-sync migrate               re-run migration (idempotent)
```

### `init` sequence

1. Create `.agent-memory/` with typed subdirs
2. Move existing `~/.claude/projects/-home-tim-huang-content-creation/memory/*.md` files into typed subdirs, adding required frontmatter
3. Rebuild `MEMORY.md` index with new relative paths
4. Remove native memory directory, replace with symlink
5. Write `config.yml`

### `extract-codex` sequence

1. Read `.agent-memory/.last-codex-sync` timestamp (or epoch if missing)
2. Scan `~/.codex/memories/rollout_summaries/` for files newer than timestamp
3. Filter to `cwd=/home/tim-huang/content-creation` entries
4. Extract user-preference and reusable-knowledge bullets
5. For each bullet: call Haiku to produce normalized topic-file body
6. Append to `codex/codex-learnings.md`; update `MEMORY.md` if first entry
7. Write current timestamp to `.last-codex-sync`

### `doctor` checks

- MEMORY.md line count > 80 → warn; > 35 live entries → auto-archive if `--fix`
- Missing required frontmatter in any topic file → list violations
- Entries with `updated` > 6 months ago → flag as candidate for review
- Token estimate (characters ÷ 4) > 500 → warn
- Symlink validity: `~/.claude/projects/-home-tim-huang-content-creation/memory` → `.agent-memory/`

## Session-End Hooks

### Claude — `SessionEnd`

Add to `~/.claude/settings.json` `SessionEnd` array. Uses background subprocess to beat the 1.5s timeout (same pattern as existing `session-end.py`):

```python
# ~/.claude/hooks/memory-sync-session-end.py
import subprocess, sys, os

subprocess.Popen(
    ["memory-sync", "extract-codex",
     "--project", "/home/tim-huang/content-creation"],
    start_new_session=True,
    stdin=subprocess.DEVNULL,
    stdout=open(os.path.expanduser("~/.local/state/memory-sync.log"), "a"),
    stderr=subprocess.STDOUT,
)
```

Settings entry:
```json
{
  "type": "command",
  "command": "python3 /home/tim-huang/.claude/hooks/memory-sync-session-end.py"
}
```

### Codex — `Stop`

Codex has no separate SessionEnd event. `Stop` is used; `extract-codex` is idempotent (timestamp check exits immediately if no new rollout summaries since last run). Add to `~/.codex/hooks.json`:

```json
{
  "type": "command",
  "command": "memory-sync extract-codex --project /home/tim-huang/content-creation",
  "timeout": 30
}
```

## Scheduled Maintenance

Weekly cron, following the `scheduled-agent-task` wrapper pattern proven on this machine.

**Crontab entry** (every Sunday 9am):
```
0 9 * * 0 /home/tim-huang/.local/bin/memory-weekly-maintenance.sh
```

**Wrapper script** (`~/.local/bin/memory-weekly-maintenance.sh`):

```bash
#!/usr/bin/env bash
HOME="/home/tim-huang"
PATH="/home/tim-huang/.local/bin:/home/tim-huang/.nvm/versions/node/v24.14.0/bin:/usr/bin:/bin"
LOG="$HOME/.local/state/memory-maintenance.log"
PROJECT="$HOME/content-creation"

echo "START $(date)" >> "$LOG"

# Phase 1: mechanical — enforce cap, archive entries over limit
memory-sync doctor --fix --project "$PROJECT" >> "$LOG" 2>&1

# Phase 2: intelligent audit via Claude Haiku
# Reports stale and duplicate entries; does not make changes (human reviews log)
"$HOME/.local/bin/claude" -p \
  "Review $PROJECT/.agent-memory/MEMORY.md and all topic files. Identify: (1) entries with updated date >3 months ago that appear unreferenced, (2) semantically duplicate entries that should be merged. Output a markdown list of recommended actions only — do not modify any files." \
  --model claude-haiku-4-5-20251001 \
  --no-session-persistence >> "$LOG" 2>&1

# Phase 3: Codex extract — catch any missed session-end extractions
"$HOME/.nvm/versions/node/v24.14.0/bin/codex" exec \
  --skip-git-repo-check --ignore-rules --ephemeral \
  --cd "$PROJECT" \
  "Run: memory-sync extract-codex --project $PROJECT and report how many new entries were added to .agent-memory/codex/codex-learnings.md." \
  >> "$LOG" 2>&1

echo "EXIT=$? $(date)" >> "$LOG"
```

To switch to biweekly: change `0 9 * * 0` → `0 9 1,15 * *`.

The maintenance log at `~/.local/state/memory-maintenance.log` is the audit trail. Claude Haiku's report is human-readable — Tim reviews it and applies recommendations manually or via `memory-sync` subcommands.

## Token Budget

| What loads at startup | Tokens today | Tokens at cap (35 entries) |
|---|---|---|
| Claude: `.agent-memory/MEMORY.md` | ~135 | ~350 |
| Codex: same file via AGENTS.md | ~135 | ~350 |
| Topic files | 0 (on-demand) | 0 (on-demand) |
| `codex-learnings.md` | 0 (on-demand) | 0 (on-demand) |

Total per-session overhead: **≤350 tokens**. Well under 1% of a 100K context window.

Codex's internal `~/.codex/memories/MEMORY.md` (742 lines, ~19,500 tokens) is never touched by this system.

## Migration Plan

One-time command from the project root:

```bash
cd /home/tim-huang/content-creation
memory-sync init
```

The 14 existing Claude memory files migrate without content changes. The `Why:` / `How to apply:` structure already used in most files maps directly to the shared format. Only additions are `id`, `updated`, `source_agents` frontmatter fields.

After init, `git status` will show `.agent-memory/` as a new untracked directory. Add to `.gitignore` (memories are machine-local, like `~/.codex/memories/`) unless team sharing is desired.

## What This Is Not

- Not a replacement for `CLAUDE.md` or `AGENTS.md` — those carry instructions and rules; this carries learned facts and preferences
- Not a sync of Codex's full `~/.codex/memories/` — only distilled project-relevant bullets
- Not cloud-synced — machine-local, same as both agents' native memory stores
- Not enforced configuration — both agents treat memory as context, not hard rules

## v2 Scope (deferred)

- `memory-sync` packaged into `~/skill-repo/bin/` with `init`, `push`, `pull`, `doctor`, `sync` subcommands (full `skill-sync` analogy)
- `.memory.toml` manifest per project (sha + installed date, analogous to `.skills.toml`)
- Multi-project support: `memory-sync init --project <path>` from any directory
- Cross-machine sync via skill-repo or a dedicated memory-repo
