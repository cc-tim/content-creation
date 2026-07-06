# Project conventions (autopilot)

Standing decisions for this repo. When a situation below matches, the agent
proceeds **without re-asking**. Each line: `<situation> ⇒ <standing decision>`.

## Workflow
- Feature work or larger changes ⇒ start in a dedicated git worktree (`.worktrees/<branch>`) rather than working directly on a shared branch.
- Completing a logical unit of work ⇒ commit it on its own with a `type(scope): message` commit; don't batch changes into one commit at the end.

## Not pre-authorized (still ask)
- Committing to `master` ⇒ ask for confirmation first (see CLAUDE.md Multi-Agent Git Hygiene).
- Updating `docs/workflows.html` ⇒ ask before updating, even after implementing the underlying change.
- Destructive / outward-facing / irreversible actions (deleting data, force-push, publishing externally, spending money) are never pre-authorized here.
