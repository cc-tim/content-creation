---
name: engineering-manager
description: Use when Tim wants the next development sprint proposed for the content-creation visual-arsenal / pipeline-infrastructure work, wants docs/ROADMAP.md reviewed or updated, asks "what's next on the roadmap", "propose a sprint", "where are we on the arsenal", or wants to fold a new capability demand (a handoff doc, a producer acquire-demand, a future-task) into the roadmap. The engineering-manager subagent owns the roadmap; this skill dispatches it with its memory fed in. Not for building capabilities — that's a separate greenlit sprint.
---

# Engineering-manager — dispatch the roadmap owner

The arsenal-expansion program has an owner: the **engineering-manager** subagent
(`.claude/agents/engineering-manager.md`). It carries arsenal-development context, owns
`docs/ROADMAP.md`, and proposes the next sprint. It spawns cold with no native memory, so
this skill feeds its file-based memory in, dispatches it, and records the outcome — the
same skill-managed-subagent pattern as know-fountains `video-pitch` ↔ `video-producer`.

Use this skill to **plan and sequence**, never to build. Building a capability is a
separate session that happens only after Tim greenlights the proposed sprint.

## Dispatch

This harness does **not** register project `.claude/agents/` as Agent `subagent_type`s, so
inline the persona into a `general-purpose` (opus) subagent:

1. **Read the EM's memory first** (it's a cold spawn — feed it in):
   - `.agent-memory/engineering-manager/charter.md` — mission + context map
   - `.agent-memory/engineering-manager/standards.md` — accrued engineering bar
   - `.agent-memory/engineering-manager/arsenal-state.md` — living capability inventory
   - `.agent-memory/engineering-manager/sprint-log.md` — sprint history
2. Read `.claude/agents/engineering-manager.md`, strip its YAML frontmatter, use the body
   as the persona.
3. Call the Agent tool with `subagent_type: "general-purpose"`, `model: "opus"`, a
   `description` like `"EM: propose sprint N"` (or `"EM: update ROADMAP for <demand>"`), and
   a prompt that concatenates, in order: (a) the persona body; (b) a `MEMORY` section = the
   four memory files' contents, labelled; (c) `CURRENT ROADMAP` = `docs/ROADMAP.md`
   contents; (d) the task — `"Read the live demand (tmp/*-handoff.md, docs/future-tasks.md,
   any producer acquire-demand named below, Tim's note below), reconcile ROADMAP status with
   reality, and propose exactly ONE next sprint in your defined format. Do not build. Tim's
   note: <…>. New demand since last dispatch: <… or none>."`
   - Give the subagent the tools to do its job: it may Read the repo and Edit
     `docs/ROADMAP.md` + its own memory directly when the task is "update", or return the
     proposal for this skill to apply when the task is "propose only". State which in the task.
   - (If a future harness registers project agents, prefer `subagent_type:
     "engineering-manager"` — same owner, no inlining.)

## After the EM responds

1. **Relay the proposed sprint to Tim verbatim-in-substance** — the full format (goal,
   demand source, scope IN, scope OUT, dependencies, unblocks/does-not, acceptance, cost,
   size, roadmap deltas). Don't soften scope or over-promise; keep the two-axes distinction
   intact (visual-quality vs runtime).
2. **Record to memory (every dispatch):** append a `## Sprint N — <today> — <decision>`
   block to `sprint-log.md` (what changed since the last entry, the proposal, open
   questions). If the EM surfaced a generalizable engineering lesson, propose adding a line
   to `standards.md` — lean, Tim-confirmed. Refresh `arsenal-state.md` when a sprint ships.
3. **Apply roadmap deltas** to `docs/ROADMAP.md` (status moves, re-ordering, "Last
   updated") — either the EM did it directly, or apply the deltas it returned.
4. **Stop at the proposal.** Tim steers. Greenlighting a sprint → its build is a separate
   session (`superpowers:writing-plans` / `executing-plans`), not this skill.

## Don'ts

- Don't build a capability here — this skill plans and sequences only.
- Don't propose more than one "next" sprint; the EM commits to one and sketches the rest.
- Don't let a proposal claim an arsenal item adds runtime (it doesn't — see the EM's
  `standards.md`).
- Don't create a parallel backlog; the EM absorbs `future-tasks.md` rendering items into
  the roadmap epics.
