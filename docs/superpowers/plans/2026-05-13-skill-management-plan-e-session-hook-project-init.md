# Skill Management Plan E — SessionStart Hook + Project Init Extension

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire a `skill-sync doctor --quiet || true` SessionStart hook in Claude Code, add a `skill-repo:` frontmatter declaration to `content-creation/CLAUDE.md`, and extend `skill-sync init` to handle project-scope snapshot installation when `.skills.toml` is present in the working directory.

**Architecture:** `init_cmd.run()` gains a `cwd` parameter; when `.skills.toml` is found there and `--migrate` is not set, it delegates to a new `run_project()` helper that calls `install_cmd.run()` for each skill listed in the toml (reusing all copy + toml logic already built in Plan D). The SessionStart hook is a global `~/.claude/settings.json` addition. The CLAUDE.md change is pure documentation.

**Tech Stack:** Python 3.12, stdlib `tomllib`, `shutil`, `argparse`; `uv run pytest`; JSON (settings.json); bash.

---

## File Map

| File | Change |
|------|--------|
| `~/skill-repo/src/skillsync/init_cmd.py` | Add `run_project()`; update `run()` to accept `cwd` and detect project mode |
| `~/skill-repo/src/skillsync/cli.py` | Pass `cwd=Path.cwd()` to `init_run` |
| `~/skill-repo/tests/test_init_cmd.py` | Add project-mode tests (class `TestProjectInit`) |
| `~/.claude/settings.json` | Append `skill-sync doctor --quiet || true` to SessionStart hooks |
| `~/content-creation/CLAUDE.md` | Add YAML frontmatter block with `skill-repo:` key |

---

## Task 1: Write failing tests for project init mode

**Files:**
- Modify: `~/skill-repo/tests/test_init_cmd.py`

- [ ] **Step 1.1: Append `TestProjectInit` class to the test file**

Open `~/skill-repo/tests/test_init_cmd.py` and append the following class after the last existing test:

```python
# ---------------------------------------------------------------------------
# Project init mode (auto-detected by .skills.toml in cwd)
# ---------------------------------------------------------------------------

class TestProjectInit:
    """Tests for skill-sync init when run inside a project with .skills.toml."""

    @pytest.fixture
    def world(self, tmp_path: Path):
        """Minimal fixture: one repo skill + a project dir with .skills.toml."""
        from skillsync.snapshot import write_toml, skill_sha

        repo_skills = tmp_path / "repo" / "skills"
        repo_skills.mkdir(parents=True)
        for name in ("alpha", "beta"):
            d = repo_skills / name
            d.mkdir()
            (d / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: test {name}\n---\n"
            )

        project = tmp_path / "project"
        project.mkdir()

        sha_alpha = skill_sha(repo_skills / "alpha")
        sha_beta = skill_sha(repo_skills / "beta")
        write_toml(
            project / ".skills.toml",
            {
                "skill-repo": "git@github.com:timhuang1018/skill-repo.git",
                "skills": {
                    "alpha": {"sha": sha_alpha, "installed": "2026-05-01"},
                    "beta": {"sha": sha_beta, "installed": "2026-05-01"},
                },
            },
        )
        return repo_skills, project

    def test_project_mode_detected_by_skills_toml(self, world, capsys) -> None:
        repo_skills, project = world
        rc = init_cmd.run(
            repo_skills_dir=repo_skills,
            cwd=project,
        )
        assert rc == 0
        out = capsys.readouterr().out
        # Should not print "Wiring per-skill symlinks" (user-mode output)
        assert "Wiring per-skill symlinks" not in out

    def test_project_mode_installs_to_claude_skills(self, world) -> None:
        repo_skills, project = world
        init_cmd.run(repo_skills_dir=repo_skills, cwd=project)
        assert (project / ".claude" / "skills" / "alpha" / "SKILL.md").exists()
        assert (project / ".claude" / "skills" / "beta" / "SKILL.md").exists()

    def test_project_mode_installs_to_codex_skills(self, world) -> None:
        repo_skills, project = world
        init_cmd.run(repo_skills_dir=repo_skills, cwd=project)
        assert (project / ".codex" / "skills" / "alpha" / "SKILL.md").exists()
        assert (project / ".codex" / "skills" / "beta" / "SKILL.md").exists()

    def test_project_mode_idempotent(self, world, capsys) -> None:
        repo_skills, project = world
        init_cmd.run(repo_skills_dir=repo_skills, cwd=project)
        capsys.readouterr()  # clear
        rc = init_cmd.run(repo_skills_dir=repo_skills, cwd=project)
        assert rc == 0

    def test_project_mode_missing_skill_warns_and_continues(self, tmp_path: Path, capsys) -> None:
        """If a skill in .skills.toml is not in the repo, warn and continue."""
        from skillsync.snapshot import write_toml, skill_sha

        repo_skills = tmp_path / "repo" / "skills"
        repo_skills.mkdir(parents=True)
        d = repo_skills / "real-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: real-skill\ndescription: exists\n---\n")

        project = tmp_path / "project"
        project.mkdir()
        write_toml(
            project / ".skills.toml",
            {
                "skill-repo": "",
                "skills": {
                    "real-skill": {"sha": skill_sha(d)},
                    "ghost-skill": {},  # not in repo
                },
            },
        )

        rc = init_cmd.run(repo_skills_dir=repo_skills, cwd=project)
        # real-skill installed; ghost-skill should trigger an error exit
        assert rc == 1
        assert (project / ".claude" / "skills" / "real-skill" / "SKILL.md").exists()

    def test_project_mode_empty_toml_prints_message(self, tmp_path: Path, capsys) -> None:
        from skillsync.snapshot import write_toml

        project = tmp_path / "project"
        project.mkdir()
        write_toml(project / ".skills.toml", {"skill-repo": "", "skills": {}})

        repo_skills = tmp_path / "repo" / "skills"
        repo_skills.mkdir(parents=True)

        rc = init_cmd.run(repo_skills_dir=repo_skills, cwd=project)
        assert rc == 0
        out = capsys.readouterr().out
        assert out.strip()  # some output

    def test_user_mode_unchanged_when_no_skills_toml(self, world, tmp_path: Path, capsys) -> None:
        """When cwd has no .skills.toml, user-level symlink wiring still runs."""
        repo_skills, _ = world
        no_toml_dir = tmp_path / "noproject"
        no_toml_dir.mkdir()
        claude_dir = tmp_path / "claude_skills"
        codex_dir = tmp_path / "codex_skills"

        rc = init_cmd.run(
            repo_skills_dir=repo_skills,
            claude_dir=claude_dir,
            codex_dir=codex_dir,
            cwd=no_toml_dir,
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "Wiring per-skill symlinks" in out

    def test_migrate_flag_bypasses_project_mode(self, world, tmp_path: Path, capsys) -> None:
        """--migrate always triggers user-level path even when .skills.toml is present.

        migrate.discover() finds nothing in the empty tmp dirs → prints "(none found)"
        → falls through to wire_symlinks. The git commit block is in the else branch of
        `if not found` so it doesn't fire. This path is non-obvious; the comment keeps
        future readers from thinking the test is broken.
        """
        repo_skills, project = world
        claude_dir = tmp_path / "claude_skills"
        codex_dir = tmp_path / "codex_skills"

        rc = init_cmd.run(
            migrate_flag=True,
            repo_skills_dir=repo_skills,
            claude_dir=claude_dir,
            codex_dir=codex_dir,
            cwd=project,
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "Wiring per-skill symlinks" in out
```

- [ ] **Step 1.2: Run tests to confirm they fail**

```bash
cd ~/skill-repo && uv run pytest tests/test_init_cmd.py::TestProjectInit -v
```

Expected: 8 FAILED (AttributeError or TypeError because `init_cmd.run` has no `cwd` parameter yet).

---

## Task 2: Implement project init in `init_cmd.py` and wire the CLI

**Files:**
- Modify: `~/skill-repo/src/skillsync/init_cmd.py`
- Modify: `~/skill-repo/src/skillsync/cli.py`

- [ ] **Step 2.1: Add `run_project()` helper to `init_cmd.py`**

Open `~/skill-repo/src/skillsync/init_cmd.py`. After the `_autopilot_prompt` function and before `def run(`, insert:

```python
def run_project(
    cwd: Path,
    repo_skills_dir: Path = SKILLS_DIR,
) -> int:
    """Project init: read .skills.toml and install each skill into .claude/skills/ and .codex/skills/.

    Delegates to install_cmd.run() for each skill in the toml, reusing all
    copy + sha-tracking logic from Plan D.
    """
    from skillsync import install_cmd
    from skillsync.snapshot import read_toml

    toml_path = cwd / ".skills.toml"
    data = read_toml(toml_path)
    skills = data.get("skills", {})

    if not skills:
        print("(no skills listed in .skills.toml)", flush=True)
        return 0

    print(f"Installing {len(skills)} skill(s) from .skills.toml…", flush=True)
    errors = 0
    for name in sorted(skills):
        rc = install_cmd.run(
            name=name,
            project_dir=cwd,
            repo_skills_dir=repo_skills_dir,
            yes=True,
        )
        if rc != 0:
            errors += 1

    if errors:
        print(f"{errors} skill(s) failed to install.", file=sys.stderr)
        return 1

    print("Done.", flush=True)
    return 0
```

- [ ] **Step 2.2: Add `cwd` parameter to `run()` and add project-mode dispatch**

In the same file, change the `run()` signature from:

```python
def run(
    migrate_flag: bool = False,
    yes: bool = False,
    keep: Optional[str] = None,
    repo_skills_dir: Path = SKILLS_DIR,
    claude_dir: Path = CLAUDE_USER_SKILLS_DIR,
    codex_dir: Path = CODEX_USER_SKILLS_DIR,
) -> int:
    """Orchestrate `skill-sync init [--migrate]`. Returns exit code."""
    if migrate_flag:
```

to:

```python
def run(
    migrate_flag: bool = False,
    yes: bool = False,
    keep: Optional[str] = None,
    repo_skills_dir: Path = SKILLS_DIR,
    claude_dir: Path = CLAUDE_USER_SKILLS_DIR,
    codex_dir: Path = CODEX_USER_SKILLS_DIR,
    cwd: Optional[Path] = None,
) -> int:
    """Orchestrate `skill-sync init [--migrate]`. Returns exit code.

    Project mode: when cwd contains .skills.toml and --migrate is not set,
    copies repo skills into .claude/skills/ and .codex/skills/ (no symlinks).
    User mode: wires per-skill symlinks; --migrate imports existing skills first.
    """
    if cwd is None:
        cwd = Path.cwd()

    if not migrate_flag and (cwd / ".skills.toml").is_file():
        return run_project(cwd=cwd, repo_skills_dir=repo_skills_dir)

    if migrate_flag:
```

- [ ] **Step 2.3: Update `cli.py` to pass `cwd` to `init_run`**

Open `~/skill-repo/src/skillsync/cli.py`. Find the `init` dispatch block:

```python
    if args.cmd == "init":
        from skillsync.init_cmd import run as init_run
        return init_run(migrate_flag=args.migrate, yes=args.yes, keep=args.keep)
```

Replace it with:

```python
    if args.cmd == "init":
        from skillsync.init_cmd import run as init_run
        from pathlib import Path
        return init_run(migrate_flag=args.migrate, yes=args.yes, keep=args.keep, cwd=Path.cwd())
```

- [ ] **Step 2.4: Run the new tests to confirm they pass**

```bash
cd ~/skill-repo && uv run pytest tests/test_init_cmd.py::TestProjectInit -v
```

Expected: 8 PASSED.

- [ ] **Step 2.5: Run full test suite to confirm no regressions**

```bash
cd ~/skill-repo && uv run pytest -q
```

Expected: 171 passed (163 existing + 8 new), 0 failed.

- [ ] **Step 2.6: Smoke-test the CLI**

```bash
cd ~/skill-repo && skill-sync init --help
```

Expected: help text shows `--migrate`, `--yes`, `--keep` (no visible change — `cwd` is internal).

- [ ] **Step 2.7: Commit**

```bash
cd ~/skill-repo && git add src/skillsync/init_cmd.py src/skillsync/cli.py tests/test_init_cmd.py
git commit -m "feat(init): extend init to project mode when .skills.toml present"
```

---

## Task 3: Add SessionStart hook to Claude Code settings

**Files:**
- Modify: `~/.claude/settings.json`

The hook command: `{ test -f .skills.toml && skill-sync doctor --quiet; } || true`

- The leading `test -f .skills.toml` gates the doctor run: in projects without `.skills.toml` the hook is a silent no-op. This matches spec line 174 ("Hook activates only in projects that contain `.skills.toml`"). Without the gate, doctor would run repo-wide symlink + frontmatter checks in every Claude Code session regardless of project — a drift in `~/skill-repo/` would spam warnings across unrelated projects.
- `--quiet` suppresses output on success, reduces failures to a single line.
- `|| true` prevents the hook from blocking Claude Code startup even if doctor exits 1.
- Braces are required: `test -f .skills.toml && skill-sync doctor --quiet || true` has wrong precedence — `|| true` would eat `skill-sync doctor`'s non-zero exit before it reaches the shell, not the whole compound command.

- [ ] **Step 3.1: Read current settings.json to get the full file**

Read `~/.claude/settings.json`.

- [ ] **Step 3.2: Add the hook to the `SessionStart` array**

The current `SessionStart` array has one entry (the `keymanager.py` check). Add a second hook to the same array. The new entry goes at the end of the array, making `SessionStart` look like:

```json
"SessionStart": [
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "python3 ~/.claude/bin/keymanager.py check-exhausted"
      }
    ]
  },
  {
    "matcher": "",
    "hooks": [
      {
        "type": "command",
        "command": "{ test -f .skills.toml && skill-sync doctor --quiet; } || true"
      }
    ]
  }
]
```

Use the Edit tool to make this change — find the existing SessionStart block and extend it.

- [ ] **Step 3.3: Verify JSON is valid**

```bash
python3 -c "import json; json.load(open(os.path.expanduser('~/.claude/settings.json')))" && echo "JSON valid"
```

(If that gives a NameError on `os`, use:)

```bash
python3 -c "import json, os; json.load(open(os.path.expanduser('~/.claude/settings.json'))); print('JSON valid')"
```

Expected: `JSON valid`

- [ ] **Step 3.4: Smoke-test the hook command manually**

```bash
skill-sync doctor --quiet; echo "exit: $?"
```

Expected: silent output (no findings in the current skill repo), `exit: 0`.

Also test from the content-creation project dir (no `.skills.toml` yet — should still exit 0):

```bash
cd ~/content-creation && skill-sync doctor --quiet; echo "exit: $?"
```

Expected: `exit: 0` (or `exit: 1` with a warning if skills have frontmatter issues).

---

## Task 4: Add `skill-repo:` frontmatter to `content-creation/CLAUDE.md`

**Files:**
- Modify: `~/content-creation/CLAUDE.md`

The spec (`docs/superpowers/specs/2026-05-12-skill-management-design.md`, "Onboarding flow") specifies that project CLAUDE.md should have a YAML frontmatter block at the top:

```markdown
---
skill-repo: git@github.com:timhuang1018/skill-repo.git
---
```

- [ ] **Step 4.1: Read the current top of `CLAUDE.md`**

Read the first 5 lines of `~/content-creation/CLAUDE.md` to see the current opening.

- [ ] **Step 4.2: Insert YAML frontmatter**

The current file begins with `# CLAUDE.md`. Prepend a YAML frontmatter block so the file starts with:

```markdown
---
skill-repo: git@github.com:timhuang1018/skill-repo.git
---

# CLAUDE.md
```

Use the Edit tool: replace the opening `# CLAUDE.md` with the frontmatter + heading.

- [ ] **Step 4.3: Commit to content-creation**

```bash
cd ~/content-creation && git add CLAUDE.md
git commit -m "docs: add skill-repo frontmatter to CLAUDE.md"
```

---

## Task 5: End-to-end verification of all Plan E deliverables

- [ ] **Step 5.1: Run full skill-repo test suite one final time**

```bash
cd ~/skill-repo && uv run pytest -q
```

Expected: 171 passed, 0 failed.

- [ ] **Step 5.2: Verify `skill-sync init` project mode end-to-end**

Create a temporary test project with a `.skills.toml` entry pointing at `checkpoint-commit` (which is in the repo):

```bash
TMPDIR=$(mktemp -d)
python3 - "$TMPDIR" <<'EOF'
import sys; sys.path.insert(0, "/home/tim-huang/skill-repo/src")
from skillsync.snapshot import write_toml, skill_sha
from pathlib import Path
proj = Path(sys.argv[1])
repo_skill = Path.home() / "skill-repo/skills/checkpoint-commit"
sha = skill_sha(repo_skill)
write_toml(proj / ".skills.toml", {"skill-repo": "git@github.com:timhuang1018/skill-repo.git", "skills": {"checkpoint-commit": {"sha": sha, "installed": "2026-05-13"}}})
EOF
cd "$TMPDIR" && skill-sync init
ls .claude/skills/ .codex/skills/
```

Expected: `skill-sync init` prints "Installing 1 skill(s) from .skills.toml…", both `.claude/skills/checkpoint-commit/` and `.codex/skills/checkpoint-commit/` exist.

- [ ] **Step 5.3: Verify `doctor --quiet` is silent when healthy**

```bash
skill-sync doctor --quiet && echo "OK: silent exit 0"
```

Expected: `OK: silent exit 0` (no other output).

- [ ] **Step 5.4: Verify `settings.json` hook is syntactically correct**

```bash
python3 -c "import json, os; d=json.load(open(os.path.expanduser('~/.claude/settings.json'))); hooks=[h['hooks'][0]['command'] for e in d['hooks']['SessionStart'] for h in e['hooks']]; print(hooks)"
```

Expected: a list that contains both `'python3 ~/.claude/bin/keymanager.py check-exhausted'` and `'{ test -f .skills.toml && skill-sync doctor --quiet; } || true'`.

- [ ] **Step 5.5: Commit the final skill-repo state**

```bash
cd ~/skill-repo && git status
```

If there are any uncommitted changes (there shouldn't be after Task 2's commit), commit them now.

- [ ] **Step 5.6: Push skill-repo to remote**

```bash
cd ~/skill-repo && git push
```

Expected: 1 new commit pushed.

---

## Post-plan: Project-skill migration (separate decision)

The 15 project-local skills in `content-creation/skills/` can now be migrated into the repo using `skill-sync push` + `skill-sync install --scope project`. This requires a human decision per-skill (repo-managed vs. project-private) and would be a separate plan. Deferring until the user decides.

The migration workflow when ready:
```bash
# Per skill to migrate:
cd ~/content-creation
skill-sync push <name> --source skills/<name>          # copies to ~/skill-repo/skills/<name>
skill-sync install <name> --scope project              # snapshots back to .claude/skills/ and .codex/skills/
# skills/<name>/SKILL.md can then be removed (now lives in ~/skill-repo/skills/)
```
