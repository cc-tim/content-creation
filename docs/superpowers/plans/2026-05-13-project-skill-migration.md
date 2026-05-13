# Content-Creation Project-Skill Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate 11 content-creation plugin skills from `skills/<name>/SKILL.md` into `~/skill-repo/skills/<name>/`, install them as project-scope directory snapshots, and generate `.skills.toml` for sha tracking.

**Architecture:** `skill-sync push --source` copies each skill to skill-repo and auto-commits there; `skill-sync install --scope project` creates directory snapshots in `.claude/skills/<name>/` and `.codex/skills/<name>/`, writing sha + date into `.skills.toml`. The 9 stale flat `.md` files currently in `.claude/skills/` (legacy install format) must be removed before install runs. The original `skills/<name>/SKILL.md` files are kept so that `.claude-plugin/marketplace.json` (which reads from `skills/<name>/SKILL.md`) continues to work. The 4 user-scope skills (checkpoint-commit, generate-image, generate-video, workflow-scout) live in skill-repo already and need no migration.

**Tech Stack:** skill-sync CLI (`cd ~/content-creation && skill-sync ...`), bash, Python 3.12, git

---

## Skill scope decision

All 11 skills go **repo-managed** (pushed to skill-repo). They are project-specific in their `uv run pipeline` commands, but putting them in skill-repo gives version tracking and sha-drift detection for free. They'll also appear as user-scope symlinks in `~/.claude/skills/` — that's harmless since their trigger descriptions only fire in a content-creation context.

The 4 skipped skills (checkpoint-commit, generate-image, generate-video, workflow-scout) already live in skill-repo; their `skills/<name>/SKILL.md` is a symlink to `~/.claude/skills/<name>.md`. No action needed for them.

---

## Files

| Action | Path |
|--------|------|
| Delete (9 stale flat files) | `content-creation/.claude/skills/{evaluate-video,knowledge,produce,publish,render,shorts,status,storyboard,voice-variant}.md` |
| Create (11 new dirs in skill-repo) | `~/skill-repo/skills/{evaluate-video,knowledge,produce,publish,render,scene-update,shorts,status,storyboard,visual-review,voice-variant}/SKILL.md` |
| Create (11 dirs, project .claude scope) | `content-creation/.claude/skills/<name>/SKILL.md` |
| Create (11 dirs, project .codex scope) | `content-creation/.codex/skills/<name>/SKILL.md` |
| Create | `content-creation/.skills.toml` |
| Untouched | `content-creation/skills/<name>/SKILL.md` (originals, for marketplace compat) |
| Untouched | `content-creation/.claude-plugin/marketplace.json` |

---

## Task 1: Verify starting state

**Files:** none modified

- [ ] **Step 1: Confirm 11 project skills exist with SKILL.md**

```bash
cd ~/content-creation
for name in evaluate-video knowledge produce publish render scene-update shorts status storyboard visual-review voice-variant; do
  test -f "skills/$name/SKILL.md" && echo "OK $name" || echo "MISSING $name"
done
```

Expected: 11 `OK` lines, zero `MISSING`.

- [ ] **Step 2: Confirm 9 stale flat files exist**

```bash
ls .claude/skills/
```

Expected output (order may vary):
```
evaluate-video.md  knowledge.md  produce.md  publish.md  render.md
shorts.md  status.md  storyboard.md  voice-variant.md
```

(scene-update and visual-review are absent — they were never installed as flat files.)

- [ ] **Step 3: Confirm skill-repo health**

```bash
cd ~/skill-repo && uv run pytest -q 2>&1 | tail -3
skill-sync doctor
skill-sync list
```

Expected: 171 passed, doctor "all checks passed", 5 user symlinks.

- [ ] **Step 4: No .skills.toml yet**

```bash
test ! -f ~/content-creation/.skills.toml && echo "absent (correct)" || echo "exists — check contents before proceeding"
```

Expected: `absent (correct)`.

---

## Task 2: Remove stale flat files from .claude/skills/

**Files:** Delete 9 files from `content-creation/.claude/skills/`

- [ ] **Step 1: Remove the 9 legacy flat files**

```bash
cd ~/content-creation
rm .claude/skills/evaluate-video.md \
   .claude/skills/knowledge.md \
   .claude/skills/produce.md \
   .claude/skills/publish.md \
   .claude/skills/render.md \
   .claude/skills/shorts.md \
   .claude/skills/status.md \
   .claude/skills/storyboard.md \
   .claude/skills/voice-variant.md
```

- [ ] **Step 2: Confirm .claude/skills/ is now empty (no .md files)**

```bash
ls .claude/skills/
```

Expected: empty output (the directory exists but has no entries).

---

## Task 3: Push 11 skills to skill-repo (group A — 6 skills)

**Files:** Creates `~/skill-repo/skills/{evaluate-video,knowledge,produce,publish,render,scene-update}/` and auto-commits each to skill-repo. Also wires user-scope symlinks in `~/.claude/skills/` and `~/.codex/skills/`.

- [ ] **Step 1: Push evaluate-video**

```bash
cd ~/content-creation
skill-sync push evaluate-video --source skills/evaluate-video --yes
```

Expected: `pushed evaluate-video @ <sha12>` followed by git commit output.

- [ ] **Step 2: Push knowledge**

```bash
skill-sync push knowledge --source skills/knowledge --yes
```

Expected: `pushed knowledge @ <sha12>`.

- [ ] **Step 3: Push produce**

```bash
skill-sync push produce --source skills/produce --yes
```

Expected: `pushed produce @ <sha12>`.

- [ ] **Step 4: Push publish**

```bash
skill-sync push publish --source skills/publish --yes
```

Expected: `pushed publish @ <sha12>`.

- [ ] **Step 5: Push render**

```bash
skill-sync push render --source skills/render --yes
```

Expected: `pushed render @ <sha12>`.

- [ ] **Step 6: Push scene-update**

```bash
skill-sync push scene-update --source skills/scene-update --yes
```

Expected: `pushed scene-update @ <sha12>`.

- [ ] **Step 7: Verify 6 new entries in skill-repo**

```bash
ls ~/skill-repo/skills/
```

Expected: the 5 original user skills plus 6 new ones (11 total at this point).

---

## Task 4: Push 11 skills to skill-repo (group B — 5 skills)

**Files:** Creates `~/skill-repo/skills/{shorts,status,storyboard,visual-review,voice-variant}/` and auto-commits.

- [ ] **Step 1: Push shorts**

```bash
cd ~/content-creation
skill-sync push shorts --source skills/shorts --yes
```

Expected: `pushed shorts @ <sha12>`.

- [ ] **Step 2: Push status**

```bash
skill-sync push status --source skills/status --yes
```

Expected: `pushed status @ <sha12>`.

- [ ] **Step 3: Push storyboard**

```bash
skill-sync push storyboard --source skills/storyboard --yes
```

Expected: `pushed storyboard @ <sha12>`.

- [ ] **Step 4: Push visual-review**

```bash
skill-sync push visual-review --source skills/visual-review --yes
```

Expected: `pushed visual-review @ <sha12>`.

- [ ] **Step 5: Push voice-variant**

```bash
skill-sync push voice-variant --source skills/voice-variant --yes
```

Expected: `pushed voice-variant @ <sha12>`.

- [ ] **Step 6: Verify skill-repo has 16 skills (5 original + 11 new)**

```bash
ls ~/skill-repo/skills/ | wc -l
```

Expected: `16`.

- [ ] **Step 7: Verify user-scope symlinks updated**

```bash
skill-sync list
```

Expected: 16 skill entries (was 5, now 16), all showing `claude=symlink codex=symlink`.

- [ ] **Step 8: Confirm skill-repo tests still pass**

```bash
cd ~/skill-repo && uv run pytest -q 2>&1 | tail -3
```

Expected: 171 passed (count may increase if new tests exist).

---

## Task 5: Install all 11 skills as project-scope snapshots

**Files:** Creates `content-creation/.claude/skills/<name>/`, `content-creation/.codex/skills/<name>/`, and `content-creation/.skills.toml`.

All 11 installs write their entry into `.skills.toml` automatically.

- [ ] **Step 1: Install evaluate-video**

```bash
cd ~/content-creation
skill-sync install evaluate-video --scope project --yes
```

Expected:
```
installed → .claude/skills/evaluate-video (sha=...)
installed → .codex/skills/evaluate-video (sha=...)
updated .skills.toml
```

- [ ] **Step 2: Install knowledge**

```bash
skill-sync install knowledge --scope project --yes
```

- [ ] **Step 3: Install produce**

```bash
skill-sync install produce --scope project --yes
```

- [ ] **Step 4: Install publish**

```bash
skill-sync install publish --scope project --yes
```

- [ ] **Step 5: Install render**

```bash
skill-sync install render --scope project --yes
```

- [ ] **Step 6: Install scene-update**

```bash
skill-sync install scene-update --scope project --yes
```

- [ ] **Step 7: Install shorts**

```bash
skill-sync install shorts --scope project --yes
```

- [ ] **Step 8: Install status**

```bash
skill-sync install status --scope project --yes
```

- [ ] **Step 9: Install storyboard**

```bash
skill-sync install storyboard --scope project --yes
```

- [ ] **Step 10: Install visual-review**

```bash
skill-sync install visual-review --scope project --yes
```

- [ ] **Step 11: Install voice-variant**

```bash
skill-sync install voice-variant --scope project --yes
```

- [ ] **Step 12: Verify .skills.toml was created with 11 entries**

```bash
cat .skills.toml
```

Expected format:
```toml
[skills]
evaluate-video = { sha = "...", installed = "2026-05-13" }
knowledge = { sha = "...", installed = "2026-05-13" }
produce = { sha = "...", installed = "2026-05-13" }
publish = { sha = "...", installed = "2026-05-13" }
render = { sha = "...", installed = "2026-05-13" }
scene-update = { sha = "...", installed = "2026-05-13" }
shorts = { sha = "...", installed = "2026-05-13" }
status = { sha = "...", installed = "2026-05-13" }
storyboard = { sha = "...", installed = "2026-05-13" }
visual-review = { sha = "...", installed = "2026-05-13" }
voice-variant = { sha = "...", installed = "2026-05-13" }
```

- [ ] **Step 13: Verify .claude/skills/ now has 11 subdirectories (no flat .md files)**

```bash
ls .claude/skills/
```

Expected: 11 directory names (evaluate-video, knowledge, produce, …), no `.md` files.

- [ ] **Step 14: Verify .codex/skills/ also has 11 subdirectories**

```bash
ls .codex/skills/
```

Expected: same 11 directory names.

---

## Task 6: Run doctor and commit content-creation changes

**Files:** Commits `.skills.toml`, `.claude/skills/` directories, `.codex/skills/` directories; removes deleted flat files.

- [ ] **Step 1: Run skill-sync doctor from content-creation**

```bash
cd ~/content-creation
skill-sync doctor
```

Expected: `skill-sync doctor: all checks passed.` — the 11 new skills should appear with `claude=symlink codex=symlink` for user scope.

Note: doctor checks user-scope state (`~/.claude/skills/`), not project-scope. The 11 skills will appear as symlinks there (wired by push). The project-scope directories in `.claude/skills/` and `.codex/skills/` are separate from the user-scope symlinks.

- [ ] **Step 2: Verify marketplace still works (skills/<name>/SKILL.md originals intact)**

```bash
for name in evaluate-video knowledge produce publish render scene-update shorts status storyboard visual-review voice-variant; do
  test -f "skills/$name/SKILL.md" && echo "OK $name" || echo "MISSING $name"
done
```

Expected: 11 `OK` lines — originals untouched.

- [ ] **Step 3: Stage and commit all changes in content-creation**

```bash
cd ~/content-creation
git add .skills.toml .claude/skills/ .codex/skills/
git status
```

Verify staged diff shows:
- `.skills.toml` new file
- `.claude/skills/evaluate-video.md` deleted (9 deletions)
- `.claude/skills/evaluate-video/SKILL.md` added (11 additions per scope × 2 scopes)
- `.codex/skills/<name>/SKILL.md` added (11 additions)

- [ ] **Step 4: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat: migrate 11 plugin skills to skill-repo managed snapshots

Pushed to ~/skill-repo and installed as project-scope copies via
skill-sync. Generates .skills.toml for sha tracking. Legacy flat
.claude/skills/*.md files replaced by directory snapshots.

Co-Authored-By: Codex <noreply@openai.com>
EOF
)"
```

Expected: commit succeeds, lists ~33 files changed.

- [ ] **Step 5: Final sanity check**

```bash
skill-sync doctor
skill-sync list
cat .skills.toml | grep -c "installed"
```

Expected:
- doctor: all checks passed, 16 skills shown
- list: 16 skills, all symlinks
- `11` (eleven installed entries in .skills.toml)

---

## Self-Review

**Spec coverage check:**

| Requirement | Task |
|-------------|------|
| Push 11 skills to skill-repo | Tasks 3–4 |
| Decide repo-managed vs project-private | Scope section (all 11 = repo-managed) |
| Install as project scope → .skills.toml | Task 5 |
| Skip 4 user skills (already in skill-repo) | Documented in scope section + Task 1 |
| Keep marketplace.json intact | Task 6 Step 2 verification |
| Commit content-creation .skills.toml | Task 6 |

**Placeholder scan:** None found.

**Type consistency:** All `skill-sync` commands are consistent with actual CLI help output verified during planning.

**Edge case — scene-update and visual-review missing from old .claude/skills/:** These two were never installed as flat files, so Task 2 only removes 9 files (not 11). Tasks 3–5 push and install all 11, so they get proper directory snapshots for the first time.

**Edge case — push auto-commits to skill-repo:** Each `skill-sync push` creates its own git commit. This produces 11 commits in skill-repo (one per skill). This is intentional and gives granular history per skill.
