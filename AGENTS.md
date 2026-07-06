# AGENTS.md

Use `CLAUDE.md` in this directory as the project guide — read it first. The standing rules live there:

- **Multi-Agent Git Hygiene** — checkpoint commits before editing over uncommitted state, dedicated git worktrees for feature work, commit-per-unit discipline.
- **Knowledge Base Map** — where specs, plans, workflows, and future work live under `docs/`.
- **Quick Reference** — pointer index for commands, tech stack, and workflow details kept in `README.md`, including `docs/project-conventions.md` for standing autopilot decisions.

## Shared agent memory

Durable learnings (user preferences, project constraints, reusable knowledge) live in
`.agent-memory/` — one fact per file with frontmatter, indexed in `.agent-memory/MEMORY.md`.
Write them when you learn them; read the index at session start. `.agent-memory/` is
machine-local except for the committed `engineering-manager/` and `storyboard-critic/`
subdirectories (see `.gitignore`) — promote any fact that must reach another machine into
a committed doc (`docs/`, `CLAUDE.md`).
