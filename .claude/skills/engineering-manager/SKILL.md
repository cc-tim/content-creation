---
name: engineering-manager
description: Dispatch the engineering-manager — the roadmap owner and adversarial acceptance gate for content-creation's visual-arsenal / pipeline-infrastructure work. Three modes. INTAKE — Tim has an idea/feature/task/enhancement to fold into docs/ROADMAP.md ("add this to the roadmap", "where should this live"). SPRINT — propose the next sprint or spec a feature ("what's next on the roadmap", "propose a sprint", "start Sprint N", "where are we on the arsenal"). REVIEW — an arsenal implementation is done or at a checkpoint and must be verified against requirements + the test plan before merge ("review the X work", "did this meet the sprint", "verify against the test plan", "is this done"). The EM spawns cold and reads its own memory + roadmap itself — dispatch lean, do NOT pre-read its memory. Not for building capabilities (that's a separate greenlit sprint).
---

# Engineering-manager — dispatch the roadmap owner + acceptance gate

The arsenal-expansion program has an owner: the **engineering-manager** subagent
(`.claude/agents/engineering-manager.md`). It owns `docs/ROADMAP.md` and the arsenal
regression `test-plan.md`, and it is the **adversarial acceptance gate** for greenlit work.

**This skill is a thin router. It is deliberately lean — that is the whole point.** The EM
is a registered subagent type that **reads its own memory and the roadmap itself**, inside
its own isolated context. Your job here is to (1) pick the mode, (2) dispatch with a small
task prompt, (3) relay the result. **Do not read the EM's memory, the roadmap, or the
persona into your own context before dispatching** — that pre-read is the token/time waste
this design removes, and it grows every sprint. Trust the EM; summon it directly.

You plan, sequence, and gate here — you never build. Building a greenlit sprint is a
separate session (`superpowers:writing-plans` / `executing-plans`).

## Step 1 — pick the mode

| Mode | Use when Tim… | The EM will… |
|------|---------------|--------------|
| **INTAKE** | hands you one idea / feature / task / engineering enhancement to capture | place it in the right epic, dedup, cross-link, report where it landed |
| **SPRINT** | asks for the next sprint, "what's next", "start Sprint N", or to spec a feature | propose ONE sprint (format + spec + test-plan rows), log it |
| **REVIEW** | says an implementation is done / at a checkpoint, or you are about to finish an arsenal-sprint branch | run the tests, verify against acceptance criteria + test-plan, return REWORK/ADVISE/PASS, advance ROADMAP only on PASS |

If Tim's intent spans two (e.g. "fold this in AND tell me if it's the next sprint"), pick
the primary mode and say so in the task; don't split into two dispatches.

**REVIEW is the antagonist role and it matters most when it's least convenient.** Treat
the close of any greenlit arsenal sprint as a REVIEW trigger — summon the EM before
`superpowers:finishing-a-development-branch` / merge. That's the definition-of-done
(`standards.md` → "Definition of done"). Use judgment on timing; don't skip it under
pressure.

## Step 2 — dispatch (lean)

The `engineering-manager` agent is registered as a native `subagent_type`, so the harness
loads its persona automatically and it self-reads its memory. Build a **small** task prompt:

```
MODE: <INTAKE | SPRINT | REVIEW>

<the task for this mode — see below>

Read your memory (charter, standards, arsenal-state, test-plan, sprint-log) and
docs/ROADMAP.md yourself before reasoning, per your persona. Edit the roadmap, test-plan,
and your memory directly; don't hand deltas back for me to apply.

Tim's note: <verbatim, or "none">
New demand since last dispatch (paths only, do not paste contents): <e.g.
tmp/<x>-handoff.md, docs/future-tasks.md line N, know-fountains producer review, or "none">
```

Per-mode task line:
- **INTAKE:** "Fold this into the roadmap: `<the idea, verbatim>`. Classify it (epic / new
  epic / future-tasks / known-bug), dedup, place + order it, and report where it landed and
  whether it shifts the recommended next sprint. Do not expand it into a full sprint."
- **SPRINT:** "Reconcile ROADMAP status with reality and propose exactly ONE next sprint in
  your defined format, with test-plan rows. <If a feature is named: also write its short
  spec.> Do not build."
- **REVIEW:** "Acceptance-gate the following completed work: `<branch / commit range /
  files>`, which claims to satisfy `<Sprint N / the criterion>`. Recover the acceptance
  criteria + test-plan rows, RUN the targeted pytest + ruff + mypy yourself, check the
  two-axes and loud-failure invariants, confirm a separate code review happened, and return
  REWORK / ADVISE / PASS. Advance ROADMAP + test-plan + arsenal-state only on PASS."

Dispatch path by runtime:

- **Claude (default):** call the **Agent** tool with `subagent_type: "engineering-manager"`,
  `model: "opus"`, a `description` like `"EM INTAKE: <idea>"` / `"EM SPRINT: propose next"` /
  `"EM REVIEW: Sprint N"`, and `prompt:` = the task prompt above. The persona comes from the
  registered agent — **do not inline it**.
- **Codex (fallback only, if `subagent_type` isn't registered or you're in Codex):** read
  `.claude/agents/engineering-manager.md`, strip its YAML frontmatter, pass the body as
  `system_prompt`, and call `spawn_agent(system_prompt=persona_body, tools=["Read","Edit",
  "Write","Bash","Glob","Grep"], message=<the task prompt above>)`. Still lean — pass demand
  as paths; the agent self-reads its memory.

## Step 3 — relay

1. **Relay the EM's output to Tim faithfully** — the full proposal format (SPRINT), the
   placement summary (INTAKE), or the verdict + evidence (REVIEW). Don't soften scope,
   over-promise, or collapse a REWORK into a PASS. Keep the two-axes distinction intact
   (visual-quality vs runtime).
2. **You record nothing.** The EM logs to `sprint-log.md`, edits `docs/ROADMAP.md`, updates
   `test-plan.md` / `arsenal-state.md` itself. If it reports it could not write a file
   (permissions), apply that one delta and say so — otherwise leave bookkeeping to the EM.
3. **Stop at the EM's output.** Tim steers. A greenlit sprint → its build is a separate
   session; a PASS verdict → merge is Tim's call.

## Don'ts

- **Don't pre-read the EM's memory, roadmap, or persona into your context before
  dispatching.** Lean dispatch is the feature. The EM reads its own state.
- Don't build a capability here — this skill plans, sequences, and gates only.
- Don't perform the acceptance review yourself — that's the EM's REVIEW mode. (You may run a
  separate code-quality reviewer; the EM requires one happened but doesn't redo it.)
- Don't propose more than one "next" sprint; the EM commits to one and sketches the rest.
- Don't let a proposal claim an arsenal item adds runtime (it doesn't — see `standards.md`).
- Don't create a parallel backlog; the EM absorbs `future-tasks.md` rendering items.
