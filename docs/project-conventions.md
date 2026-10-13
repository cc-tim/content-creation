# Project conventions (autopilot)

Standing decisions for this repo. When a situation below matches, the agent
proceeds **without re-asking**. Each line: `<situation> ⇒ <standing decision>`.

## Workflow
- Feature work or larger changes ⇒ start in a dedicated git worktree (`.worktrees/<branch>`) rather than working directly on a shared branch.
- Completing a logical unit of work ⇒ commit it on its own with a `type(scope): message` commit; don't batch changes into one commit at the end.
- Minor / routine steps (Tim, 2026-10-13: "minor things don't need my permit") ⇒ proceed without asking, then report what was done. This covers committing to `master` and pushing for:
  - doc updates that record Tim's decisions or project status (`docs/own-show.md`, roadmap/spec records written by the EM);
  - housekeeping, such as removing merged worktrees and branches, or cleaning up the agent's own scratch artifacts;
  - merging and pushing a branch whose required review has already passed: an EM PASS for a greenlit sprint, or a clean independent code review for a fix Tim asked for;
  - dispatching review/fix rounds and follow-ups within scope Tim already approved.

  Leave other sessions' uncommitted files alone.

## Not pre-authorized (still ask)
- Committing to `master` anything outside the minor/routine list above ⇒ ask first (see CLAUDE.md Multi-Agent Git Hygiene). This includes code that hasn't passed its required review, and ambiguous diffs owned by another session.
- Creative picks for Tim's own show (characters, style, scene elements) ⇒ options → Tim picks (`docs/own-show.md`).
- Greenlighting a new sprint, epic or scope change ⇒ Tim decides.
- Updating `docs/workflows.html` ⇒ ask before updating, even after implementing the underlying change.
- Destructive / outward-facing / irreversible actions (deleting data, force-push, publishing externally, spending money) are never pre-authorized here.
