---
name: align-guidelines
description: Use when setting up or tidying a project's agent guideline files (CLAUDE.md, AGENTS.md) — onboarding a new repo, slimming a CLAUDE.md that has grown long, making guideline files token-lean / index-shaped, or ensuring the standing resume-trail, session-start, and shared-memory rules are present and consistent across repos.
version: 1.3.0
---

# Align Guidelines

## Overview

A project's `CLAUDE.md` / `AGENTS.md` should be an **index of standing rules + pointers**, not a reference dump. Always-on behavioral rules stay inline; anything needed only *sometimes* (commands, env vars, architecture, API notes) is extracted to a `doc/` file and referenced — so the guideline costs few tokens every session and the detail loads only when a task needs it.

This skill aligns a project's guideline files to that shape and guarantees the two standing rules below are present with consistent wording across every repo.

## When to use

- Onboarding a new repo (no CLAUDE.md, or a thin one).
- A CLAUDE.md has grown long / mixes reference detail with rules.
- You want the resume-trail + session-start rules present in *this* repo too.
- After installing this skill into a new project via `/skill-management`.

**Not for:** writing project-specific reference content itself (that goes in the extracted `doc/` file), or enforcing the rules at runtime (a doc can't enforce; that's a hook's job).

## The target shape

```
CLAUDE.md
  # CLAUDE.md
  ## Project Overview      ← inline (orientation: module map, 1 screen max)
  ## Project Split         ← inline IF multi-repo
  ## Session start         ← inline  (standing rule — template A)
  ## Workflow: progress fragments (resume trail)  ← inline (standing rule — template B)
  ## Key Docs              ← pointer index; incl. dev-reference + the
                             project-conventions autopilot trigger (template E)

doc/dev-reference.md          ← extracted: commands, env vars, architecture, etc.
docs/project-conventions.md   ← autopilot: standing decisions the agent honors
                                without re-asking (template E)
AGENTS.md                     ← delegates to CLAUDE.md, names the standing rules
```

**Index rule:** if a section is needed only on *some* tasks, move it to a `doc/` file and leave a one-line pointer under `## Key Docs`. Keep inline only what every session needs.

## Steps

1. Read the project's `CLAUDE.md` and `AGENTS.md` (create if absent).
2. **Classify** each section: *always-on rule* → keep inline; *sometimes-needed detail* (commands, env vars, architecture, API/tool notes) → extract.
3. **Extract** the sometimes-needed sections into `doc/dev-reference.md` (or an existing doc), and replace them in CLAUDE.md with a one-line `## Key Docs` pointer.
4. **Ensure the two standing-rule blocks are present** (templates below). Paste them verbatim, then adapt the *paths/tool names* to this repo (see Adapt).
5. **Make AGENTS.md delegate** to CLAUDE.md and name the standing rules (template C).
6. **Establish the local memory store** (most repos want it — this is where the
   per-repo memory setup lives, so it isn't a separate chore). Run `memory-sync
   init`: it creates `.agent-memory/`, gitignores it, and is idempotent. If the
   repo committed `.agent-memory/` under the old model, untrack it (keeps the
   files; stops it travelling with git):
   ```bash
   git ls-files --error-unmatch .agent-memory >/dev/null 2>&1 \
     && git rm -r --cached .agent-memory   # then commit the removal
   ```
   Then ensure the shared-memory block (template D) is in AGENTS.md so Codex
   writes durable learnings into the store at write time; promote facts that must
   travel into committed docs. Skip only if the repo explicitly shouldn't use
   agent memory.
7. **Ensure `docs/project-conventions.md` + its Key-Docs trigger** (template E):
   create the doc stub if absent, and add the one-line always-on pointer under
   `## Key Docs` so the agent consults it before asking the user to confirm a
   routine decision. Seed any conventions the user has already stated.
8. Summarize the diff: what moved, what was added, what you recommend the user verify.

## Standing-rule templates (paste, then adapt)

### Template A — `## Session start`
```markdown
## Session start

Involve the `product-manager` skill when the task is in its scope — capturing an
idea/feature/task, scoping "what's next", tracking production status, or reviewing
finished work against a brief. **Skip PM for pure process/thinking sessions** —
brainstorming, tracing how something works, or meta/workflow design (e.g. refining
these guidelines).

For feature work or big/complex changes, use a dedicated git worktree before
starting implementation.
```

### Template B — `## Workflow: progress fragments (resume trail)`
```markdown
## Workflow: progress fragments (resume trail)

When working against a brief in `docs/briefs/`, keep a live trail so any session
can resume without re-reading the transcript.

**Record a one-line fragment when you:**
- complete a TodoWrite item / finish a logical unit   → tag `done`
- root-cause a bug or hit an unexpected twist          → tag `twist`
- make a decision that deviates from the brief         → tag `decision`
- get a verification result (pass / fail / pending)    → tag `verify`

**Commit granularly (this is the trail):**
- Commit each completed unit on its OWN — many small commits, never one batch at
  the end. Message follows the repo convention `type(scope): …` so `git log`
  reads as a trail.
- The same commit includes the brief's appended `done:` line, so its `[sha]`
  resolves. Do NOT push (push stays manual / wrap-up).
- This is finer-grained than `/checkpoint-commit` (which only fires at pivots) —
  they stack, they don't replace each other.
- No brief? Still commit per unit; the worklog is the only optional part.

**Worklog — keep it cheap (anti-bloat contract):**
- Append ONE line to the brief's `## Progress log`. Append-only — do NOT re-read
  the brief to write it.
- Format: `- HH:MM <tag>: <what> [<sha>]`  (sha only on `done`).
- Size TodoWrite items so finishing one is a meaningful, recordable unit.

**Memory files — maintain, don't hoard:**
- Keep main-agent and subagent memory files compact enough to scan. If
  `.agent-memory/`, native project memory, or role memory like
  `.agent-memory/<subagent>/` grows noisy, summarize stale detail, archive useful
  history, or prune instead of appending forever.
- `.agent-memory/` is **machine-local** (gitignored). Promote any durable fact
  that must reach another machine or survive a fresh clone into a committed doc
  (`docs/`, a workflow file, `CLAUDE.md`); raw memory does not travel with git.

**On resume**, read in this order — stop as soon as you have enough:
brief ACs + Progress log → `git log` / `git status` → handoff memory →
session JSONL (last resort, never read whole).
```

### Template C — `AGENTS.md` delegation
```markdown
# AGENTS.md

Use `CLAUDE.md` in this directory as the project guide. The standing rules live
there — read it first:
- **Session start** — when to involve the `product-manager` skill.
- **Workflow: progress fragments** — the commit-per-unit + `## Progress log`
  resume trail, and the order to read on resume.
- **Key Docs** — index of on-demand references.
```

### Template D — `AGENTS.md` shared agent memory (only if `.agent-memory/` exists)
```markdown
## Shared agent memory

Durable learnings (user preferences, project constraints, reusable knowledge)
go in `./.agent-memory/codex/` — one fact per file with frontmatter
(id, name, description, type: feedback|project, updated), then add an index
line to `./.agent-memory/MEMORY.md`. Write them when you learn them; do not
wait for session end. Read `./.agent-memory/MEMORY.md` at session start.
`.agent-memory/` is machine-local (gitignored) — promote facts that must reach
another machine into a committed doc (docs/, a workflow file, CLAUDE.md).

Other agents' raw session memory (search on demand, never sync):
- Codex rollouts: `grep -l 'cwd: <this repo>' ~/.codex/memories/rollout_summaries/*.md`
- Claude transcripts: `~/.claude/projects/<slug>/*.jsonl`
```

Write-time capture + promote-to-docs replaced the retired extraction pipeline
(see skill-repo `docs/shared-memory.md`); the store is local and gitignored, and
memory sync is never wired into lifecycle hooks.

### Template E — `docs/project-conventions.md` autopilot preferences

A per-repo list of standing decisions the agent honors **without re-asking**, so
the user isn't pinged for routine, repeatable choices. Create the doc from this
stub, and add the always-on trigger line under `## Key Docs` in CLAUDE.md — that
inline pointer is what makes an on-demand doc actually fire before the agent asks.

`docs/project-conventions.md`:
```markdown
# Project conventions (autopilot)

Standing decisions for this repo. When a situation below matches, the agent
proceeds **without re-asking**. Each line: `<situation> ⇒ <standing decision>`.

## Verification
- <e.g. feature branch dev-done ⇒ verify in **prod** (this is a PDP), not just dev>

## Deploy / release
- <e.g. `main` green ⇒ deploy to staging automatically; prod deploy stays manual>

## Workflow
- <e.g. feature work ⇒ start in a dedicated git worktree without asking>

## Not pre-authorized (still ask)
- Destructive / outward-facing / irreversible actions are NOT waived here unless a
  line above explicitly says so (deleting data, force-push, publishing externally,
  spending money).
```

Key-Docs trigger line to add to CLAUDE.md (always-on — the piece that fires the doc):
```markdown
- `docs/project-conventions.md` — **autopilot.** Before asking the user to confirm
  a routine or repeatable decision, check here for a standing preference and follow
  it without re-asking.
```

## Adapt to the repo (don't paste blindly)

- **Brief location:** if the project keeps briefs somewhere other than `docs/briefs/`, fix the path in template B. If the project has no brief workflow at all, keep the commit-per-unit rule and drop the `## Progress log` worklog half.
- **PM skill:** if `product-manager` isn't installed in this project, keep template A but note PM is optional, or trim to "scope the task before building."
- **`/checkpoint-commit`:** drop the line if that skill isn't present.
- **Commit convention:** match the repo's existing `git log` style (`type(scope):`, ticket prefixes, etc.).

## Common mistakes

- **Leaving reference inline "because it's short."** If it's only sometimes needed, extract it — the point is per-session token cost, not file length.
- **Pasting `docs/briefs/` when the repo uses another path.** Always adapt paths.
- **Deleting reference instead of moving it.** Extract to `doc/` and leave a pointer; never drop content silently.
- **Treating the doc as enforcement.** These rules are best-effort guidance; if a project needs guaranteed firing (e.g. record-on-todo-complete), that's a hook, not this skill.
