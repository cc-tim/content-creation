# Skill Management — Cross-Agent Source-of-Truth

**Status:** Draft for review
**Date:** 2026-05-12
**Author:** brainstorm session (Tim + Claude)

## Context

User-authored skills exist today in three locations on this machine, with no shared source of truth:

| Location | Format | Count |
|---|---|---|
| `~/.claude/skills/*.md` | Flat single file | 4 |
| `~/.codex/skills/<name>/SKILL.md` | Dir-per-skill | 5 |
| `content-creation/skills/<name>/SKILL.md` | Dir-per-skill, registered via `.claude-plugin/marketplace.json` | 16 |

The four user-level "shared" skills already drift between Claude and Codex (e.g., `checkpoint-commit.md` carries `version` + `user-invocable` keys in the Claude copy but not the Codex copy). There is no discoverability layer, no dedup, no migration story between scopes.

System-supplied or plugin-supplied skills (`superpowers:*`, `plugin:context7:*`, etc.) are out of scope — they're managed by their installers.

## Goals

1. **Single source of truth** — one git repo (private GitHub) holds every user-authored skill. Both Claude Code and Codex CLI consume from it.
2. **Cross-agent portability** — skills written once work on both platforms wherever the platforms' features overlap. Platform-specific features (Claude subagents, `context: fork`, etc.) degrade gracefully on the other platform.
3. **Scope is decided at install time** — the repo is flat. Whether a given skill lives at user or project scope on this machine is decided per-install, not per-repo-entry. Migration between scopes is one command.
4. **Token-efficient management** — Tim talks to the agent in natural language ("find a skill that does X", "upload this one"); the agent translates intent to a CLI call. Heavy work (search, dedup, fetch, install) runs in a Python CLI that returns terse output. Management never burns main-session tokens on bulk reads.
5. **Doc-grounded authoring** — official skill+subagent docs from Anthropic and OpenAI are synced into a local `KNOWLEDGE/` directory and consulted before authoring decisions.

## Non-goals

- Managing plugin-supplied skills (`superpowers:*`, MCP-tool skills).
- A public skill marketplace. The repo is private to Tim.
- Cross-user sharing. (Not blocked, but not designed for it.)
- Authoring discipline beyond format compliance — the CLI lints frontmatter and structure; it does not judge skill quality.

## Architecture

A flat git repo `~/skill-repo/` is the canonical store. User-level skills are exposed to both agents by **symlinking each agent's user-skills directory to the repo's `skills/` subdir** — edits are instantly visible to both. Project-level skills are **snapshot copies** tracked by `.skills.toml`, so a project repo travels self-contained: a clone of `content-creation` works on a machine that doesn't have `~/skill-repo/` checked out.

A single Python CLI (`skill-sync`) handles all operations: search, sync, push, install, migrate, knowledge fetch, doctor.

```
~/skill-repo/                        # private GitHub repo
├── skills/                          # flat catalog, alphabetic
│   ├── checkpoint-commit/
│   │   ├── SKILL.md
│   │   ├── agents/openai.yaml       # optional, Codex sidecar
│   │   └── subagents/               # optional, only if skill orchestrates subagents
│   │       ├── claude/<name>.md
│   │       └── codex/<name>.toml
│   └── ...
├── KNOWLEDGE/                       # synced from official docs (re-runnable)
│   ├── claude-code-skills.md
│   ├── claude-api-skills-overview.md
│   ├── claude-api-skills-best-practices.md
│   ├── codex-skills.md
│   ├── claude-code-agents.md
│   ├── claude-code-agent-teams.md
│   ├── codex-subagents.md
│   ├── _urls.txt                    # extensible URL list
│   └── _last-sync.json              # url → fetched_at, sha256
├── index.json                       # capability tags + summaries (generated)
├── bin/skill-sync                   # CLI entrypoint
└── README.md

~/.claude/skills/  →  symlink to  ~/skill-repo/skills/
~/.codex/skills/   →  symlink to  ~/skill-repo/skills/

# Project layout:
content-creation/
├── .claude/skills/produce/          # COPY (snapshot)
├── .codex/skills/produce/           # COPY (snapshot)
├── .skills.toml                     # manifest of installed skills + shas
└── CLAUDE.md                        # contains: skill-repo: <url>
```

## Canonical SKILL.md format

The repo's canonical format is **directory-with-SKILL.md**, with portable frontmatter:

```yaml
---
name: skill-name                    # ≤64 chars, [a-z0-9-], no "anthropic"/"claude"
description: |                      # ≤1024 chars; third-person; what + when triggers
  Use when the user asks to X, mentions Y, or needs Z.
  Triggers on phrases like "...".
# Optional Claude-Code-only keys — silently ignored by Codex:
when_to_use: ...
allowed-tools: [Read, Bash]
disable-model-invocation: false
context: fork                       # marks skill as Claude-only (uses subagent fork)
agent: <subagent-name>              # references subagents/claude/<name>.md
---

# Skill body — ≤500 lines per best-practice; progressive disclosure one level deep
```

**Portability principle:** SKILL.md body uses platform-neutral language ("dispatch a subagent", "read the file") rather than tool-specific syntax. Platform-specific configuration goes in sidecar files (`agents/openai.yaml` for Codex; extra inline frontmatter for Claude).

Combined `description` + `when_to_use` must stay ≤1536 chars (Claude Code listing cap).

## CLI surface (`skill-sync`)

```
skill-sync init                              # one-time per machine: clone repo, create symlinks
skill-sync init --migrate                    # one-time: import existing skills into the repo
skill-sync init (in a project)               # one-time per project: read .skills.toml, copy snapshots

skill-sync sync                              # bidirectional dedup user↔repo, verify project manifests
skill-sync search <query>                    # capability search across index.json + grep
skill-sync list [--scope user|project|all]   # what's installed where
skill-sync push <name>                       # promote local skill into repo (interactive if conflict)
skill-sync install <name> [--scope user|project] [--project-path .]
skill-sync move <name> --to user|project
skill-sync knowledge                         # re-fetch official docs into KNOWLEDGE/
skill-sync doctor [--quiet]                  # validate symlinks, format, drift
```

Implementation: single-file Python (~500 lines), depends on stdlib + `tomli`/`tomllib` + `pyyaml` (already on system). Lives in `~/skill-repo/bin/skill-sync` with a stable PATH entry via `~/.local/bin/skill-sync` symlink.

## Sync semantics

**`skill-sync sync` (interactive by default; `--yes` for non-interactive):**

1. Walk `~/skill-repo/skills/` — every entry should resolve from `~/.claude/skills/<name>/` and `~/.codex/skills/<name>/` via symlink.
2. Find user-level skills present on disk but NOT in repo → "local-only, push?".
3. Find repo skills not symlinked locally → "repo has X, not symlinked".
4. For each detected project's `.skills.toml` (configurable list): compare snapshot sha against current repo sha → "drift detected on `<project>/<name>`, pull or push?".
5. Cross-platform format drift: if both `~/.claude/skills/<name>.md` (flat, legacy) and `~/.codex/skills/<name>/SKILL.md` exist with different content, show diff, prompt for canonical merge.

Conflict resolution: per-skill prompt with diff. Three choices: keep local, keep repo, merge interactively (opens `$EDITOR` with conflict markers). No silent overwrites.

**Project snapshot model:**

`.skills.toml` example:
```toml
skill-repo = "git@github.com:tim-huang/skill-repo.git"

[skills]
produce       = { sha = "abc123def456", installed = "2026-05-12" }
render        = { sha = "789..." }
voice-variant = {}                  # empty = track latest, re-pinned on next sync
```

Drift detection: `skill-sync sync` (inside a project) compares each entry's `sha` to the repo's current sha at `skills/<name>/`. Drift triggers a "pull (overwrite local with repo) / push (replace repo with local) / leave" prompt.

## Onboarding flow

**Per-machine, once:**
```bash
git clone git@github.com:tim-huang/skill-repo.git ~/skill-repo
~/skill-repo/bin/skill-sync init           # creates the two user-level symlinks
```

**Per-project, once:**
Project's `CLAUDE.md` (and/or `AGENTS.md`) has at the top:
```markdown
---
skill-repo: git@github.com:tim-huang/skill-repo.git
---
```

Project's `.skills.toml` lists the skills to install at project scope. Then:
```bash
cd content-creation/
skill-sync init                            # reads .skills.toml, copies to .claude/skills/ and .codex/skills/
```

**Continuous (SessionStart hook):**
```bash
skill-sync doctor --quiet || true          # one-line warning if anything is off; silent if clean
```

Token cost: ~50 characters per session start when healthy; up to ~200 chars when warning. Hook activates only in projects that contain `.skills.toml`.

## Subagent handling

Skills that orchestrate subagents bundle BOTH formats in the repo:

```
skills/research-pdfs/
├── SKILL.md
└── subagents/
    ├── claude/pdf-researcher.md          # YAML + markdown
    └── codex/pdf-researcher.toml         # TOML
```

Installer behavior:
- **Both formats present** → install to both platforms.
- **Claude format only** → install only on Claude; `index.json` records `platforms: ["claude"]`; `skill-sync install` warns "X is Claude-only".
- **Codex format only** → symmetric.

Claude-only frontmatter keys (`context: fork`, `allowed-tools`, etc.) on SKILL.md are tolerated by Codex (it only reads `name`+`description`). No special stripping needed.

**Authoring guidance for portability:** keep skill body in platform-neutral language ("dispatch a subagent for X"); both platforms understand subagent invocation conceptually. Only fork into separate subagent files when the subagent's tool surface or behavior must differ.

## Knowledge sync

`skill-sync knowledge` re-fetches a configurable URL list and stores HTML→markdown in `KNOWLEDGE/`:

Default URLs (`KNOWLEDGE/_urls.txt`):
```
https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
https://code.claude.com/docs/en/skills
https://code.claude.com/docs/en/agents
https://code.claude.com/docs/en/agent-teams
https://developers.openai.com/codex/skills
https://developers.openai.com/codex/subagents
```

Per-URL: fetch → markdownify → sha256 → skip if sha matches `_last-sync.json` → write file. Output is plain markdown, suitable for `cat`/grep/Read inside an authoring session.

Cadence: manual or weekly cron. Token cost: zero (all CLI).

## Migration plan

`skill-sync init --migrate` runs once on this machine:

1. **Conflict scan.** Build a name-keyed table of every skill found in `~/.claude/skills/`, `~/.codex/skills/`, and (optionally) `content-creation/skills/`. For each name with multiple sources, show a diff and prompt: keep Claude / keep Codex / keep project / merge interactively. Default canonical format = Codex's dir-with-SKILL.md (accommodates sidecars; matches best-practice).
2. **Format conversion.** Flat `~/.claude/skills/<name>.md` → `~/skill-repo/skills/<name>/SKILL.md`. Frontmatter preserved verbatim (Codex ignores unknown keys; Claude reads its own). Body unchanged.
3. **Commit to repo.** Initial commit per-skill, so history is meaningful.
4. **Symlink wiring.** Back up existing `~/.claude/skills/` and `~/.codex/skills/` to `*.bak.YYYY-MM-DD`, then create symlinks. Verify by listing both via the agents' own discovery (test by inspection — not automated in v1).
5. **Project skills.** For `content-creation/skills/`: prompt whether to import each into the repo (some may be project-private and stay outside). For imported ones, generate `.skills.toml` with current shas. Existing `.claude-plugin/marketplace.json` stays intact — it works and doesn't conflict.
6. **Knowledge bootstrap.** Run `skill-sync knowledge` to populate `KNOWLEDGE/`.

Rollback: backup directories from step 4 allow `rm ~/.claude/skills && mv ~/.claude/skills.bak.<date> ~/.claude/skills` to restore the pre-migration state.

## Testing & verification

`skill-sync doctor` checks (exit 0 if all pass, exit 1 if any warn/fail):

| Check | Severity |
|---|---|
| Symlinks resolve to existing targets | Fail |
| Every SKILL.md has valid frontmatter (`name` regex, `description` non-empty) | Fail |
| `name` ≤64 chars, no "anthropic"/"claude" substring | Fail |
| `description` ≤1024 chars | Fail |
| `description` + `when_to_use` combined ≤1536 chars | Fail |
| No duplicate skill names within `~/skill-repo/skills/` | Fail |
| Project `.skills.toml` shas match current repo shas | Warn |
| SKILL.md body line count ≤500 | Warn |
| Skill with `agent:` in frontmatter has a corresponding `subagents/claude/<name>.md` | Warn |
| Description in first person ("I can...") | Warn (style) |

`--quiet` mode: silent on success, single-line warning on first failure (used by SessionStart hook).

## Natural-language UX (the actual usage pattern)

This is what makes the system token-efficient. Tim speaks intent; the agent translates to a CLI call.

| User intent | Agent action | Token cost |
|---|---|---|
| "find skill that can render video" | `skill-sync search "render video"` | tiny |
| "do we have a skill for FishAudio?" | `skill-sync search fish-audio` | tiny |
| "sync my skills with the repo" | `skill-sync sync` | small (status lines) |
| "upload this skill to repo" | `skill-sync push <inferred-name>` | tiny |
| "install render at project scope" | `skill-sync install render --scope project` | tiny |
| "move workflow-scout to project scope" | `skill-sync move workflow-scout --to project` | tiny |
| "refresh skill docs" | `skill-sync knowledge` | tiny |
| "are my skills healthy?" | `skill-sync doctor` | small |
| "review my skills for overlap/quality" | dispatch background subagent → tight summary | medium (subagent burns its own tokens; main session sees ~300 words) |

For routine ops the agent only sees the CLI's terse output. For analysis-grade tasks (which are rare), a background subagent isolates the token cost.

## Open questions / future work

- **Path verification.** Doc-fetcher reported Codex user-level path as `~/.agents/skills/`, but installed Codex on this machine uses `~/.codex/skills/`. Confirm during implementation; spec assumes `~/.codex/skills/` until disproven.
- **Cross-machine sync.** This spec is single-machine. If Tim adds a second workstation, both machines clone the same repo independently. No additional design needed.
- **Skill quality evals.** Best-practice doc recommends building eval scenarios before each skill. Out of scope for v1 of this management system — but `skill-sync doctor` could grow an "eval status" check later.
- **Skill versioning beyond sha.** Currently `.skills.toml` pins by sha. Semantic version pinning (`render = "^1.2"`) would need a release tagging convention. Defer.
- **Migration of `content-creation/skills/` plugin marketplace.** This spec leaves it intact. If we later want a single discovery layer, we'd convert it to use `.skills.toml` only and drop the marketplace.json — but that's a separate cleanup task.

## Implementation phasing (preview for writing-plans)

Recommended order for the implementation plans that follow:

1. Repo bootstrap: create `~/skill-repo/`, skeleton dirs, README.
2. `skill-sync knowledge` (smallest, useful immediately).
3. `skill-sync init` + symlink mechanism.
4. `skill-sync init --migrate` to absorb existing skills.
5. `skill-sync sync` + `doctor` + `search` + `list`.
6. `skill-sync push` + `install` + `move`.
7. SessionStart hook + project onboarding.

Each phase is small (1–3 hours of work) and runs in a separate session if you prefer maximum token isolation.
