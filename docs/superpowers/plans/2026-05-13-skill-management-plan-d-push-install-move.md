# Skill-Management Plan D — push / install / move + .skills.toml

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `push`, `install`, and `move` subcommands to `skill-sync`, backed by a `.skills.toml` project-manifest, and grow `list`, `doctor`, and `sync` to understand project scope.

**Architecture:** All project-scope logic is built on a new `snapshot.py` utility module (sha computation, TOML I/O, dir-copy). Each command module is self-contained (`push_cmd.py`, `install_cmd.py`, `move_cmd.py`). Existing modules (`list_cmd.py`, `doctor.py`, `sync_cmd.py`) are extended with optional `project_dir` params so they remain fully testable with `tmp_path`. TOML is read via stdlib `tomllib` (Python 3.11+); writing uses a minimal hand-rolled serializer (no new dep).

**Tech Stack:** Python 3.11+, `tomllib` (stdlib), `hashlib` (stdlib), `shutil` (stdlib), existing `skillsync.*` modules, `pytest`.

**Repo:** `~/skill-repo/` — all work happens there. Tests live in `tests/`, source in `src/skillsync/`.

---

## File Map

| Action | Path |
|--------|------|
| **Create** | `src/skillsync/snapshot.py` |
| **Create** | `src/skillsync/push_cmd.py` |
| **Create** | `src/skillsync/install_cmd.py` |
| **Create** | `src/skillsync/move_cmd.py` |
| **Modify** | `src/skillsync/cli.py` (add push/install/move/list --scope wiring) |
| **Modify** | `src/skillsync/list_cmd.py` (add `--scope`, `collect_project`) |
| **Modify** | `src/skillsync/doctor.py` (add `_check_project_drift`, `project_dir` param) |
| **Modify** | `src/skillsync/sync_cmd.py` (add `_reconcile_project`, `project_dir` param) |
| **Create** | `tests/test_snapshot.py` |
| **Create** | `tests/test_push_cmd.py` |
| **Create** | `tests/test_install_cmd.py` |
| **Create** | `tests/test_move_cmd.py` |
| **Modify** | `tests/test_list_cmd.py` (new tests for --scope project/all) |
| **Modify** | `tests/test_doctor.py` (new tests for sha-drift check) |
| **Modify** | `tests/test_sync_cmd.py` (new tests for project reconciliation) |

---

## Task 1: snapshot.py — sha, TOML I/O, dir-copy

**Files:**
- Create: `src/skillsync/snapshot.py`
- Create: `tests/test_snapshot.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_snapshot.py
"""Tests for skillsync.snapshot."""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from skillsync import snapshot


def _skill(tmp_path: Path, name: str, content: str = "body") -> Path:
    d = tmp_path / name
    d.mkdir()
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n{content}")
    return d


class TestSkillSha:
    def test_returns_12_hex_chars(self, tmp_path):
        d = _skill(tmp_path, "alpha")
        s = snapshot.skill_sha(d)
        assert len(s) == 12
        assert all(c in "0123456789abcdef" for c in s)

    def test_same_content_same_sha(self, tmp_path):
        d1 = _skill(tmp_path / "a", "alpha", "same")
        d2 = _skill(tmp_path / "b", "alpha", "same")
        assert snapshot.skill_sha(d1) == snapshot.skill_sha(d2)

    def test_different_content_different_sha(self, tmp_path):
        d1 = _skill(tmp_path / "a", "alpha", "aaa")
        d2 = _skill(tmp_path / "b", "alpha", "bbb")
        assert snapshot.skill_sha(d1) != snapshot.skill_sha(d2)

    def test_missing_skill_md_raises(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        with pytest.raises(FileNotFoundError):
            snapshot.skill_sha(d)


class TestToml:
    def test_read_missing_returns_empty_structure(self, tmp_path):
        data = snapshot.read_toml(tmp_path / ".skills.toml")
        assert data == {"skill-repo": "", "skills": {}}

    def test_write_then_read_roundtrip(self, tmp_path):
        p = tmp_path / ".skills.toml"
        data = {
            "skill-repo": "git@github.com:example/repo.git",
            "skills": {
                "alpha": {"sha": "abc123def456", "installed": "2026-05-13"},
                "beta": {"sha": "999000111222"},
            },
        }
        snapshot.write_toml(p, data)
        got = snapshot.read_toml(p)
        assert got["skill-repo"] == data["skill-repo"]
        assert got["skills"]["alpha"]["sha"] == "abc123def456"
        assert got["skills"]["alpha"]["installed"] == "2026-05-13"
        assert got["skills"]["beta"]["sha"] == "999000111222"

    def test_write_no_repo_url(self, tmp_path):
        p = tmp_path / ".skills.toml"
        data = {"skill-repo": "", "skills": {"foo": {"sha": "aabbcc112233"}}}
        snapshot.write_toml(p, data)
        raw = p.read_text()
        assert "skill-repo" not in raw
        with open(p, "rb") as f:
            parsed = tomllib.load(f)
        assert parsed["skills"]["foo"]["sha"] == "aabbcc112233"

    def test_write_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "a" / "b" / ".skills.toml"
        snapshot.write_toml(p, {"skill-repo": "", "skills": {}})
        assert p.exists()

    def test_write_atomic_on_failure(self, tmp_path, monkeypatch):
        """No partial file left if write raises."""
        p = tmp_path / ".skills.toml"
        original = "original"
        p.write_text(original)

        def _bad_replace(src, dst):
            raise OSError("disk full")

        monkeypatch.setattr("os.replace", _bad_replace)
        with pytest.raises(OSError):
            snapshot.write_toml(p, {"skill-repo": "", "skills": {}})
        assert p.read_text() == original


class TestCopySkill:
    def test_copies_directory(self, tmp_path):
        src = _skill(tmp_path / "src", "alpha")
        dst = tmp_path / "dst" / "alpha"
        snapshot.copy_skill(src, dst)
        assert (dst / "SKILL.md").is_file()

    def test_raises_if_dst_exists(self, tmp_path):
        src = _skill(tmp_path / "src", "alpha")
        dst = tmp_path / "dst"
        dst.mkdir()
        with pytest.raises(FileExistsError):
            snapshot.copy_skill(src, dst)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/skill-repo && uv run pytest tests/test_snapshot.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'skillsync.snapshot'` or similar import failure.

- [ ] **Step 3: Implement snapshot.py**

```python
# src/skillsync/snapshot.py
"""Shared snapshot utilities: sha, .skills.toml I/O, skill dir copy."""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import tomllib
from pathlib import Path


def skill_sha(skill_dir: Path) -> str:
    """SHA256 of SKILL.md bytes; returns first 12 hex chars."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise FileNotFoundError(f"No SKILL.md in {skill_dir}")
    return hashlib.sha256(skill_md.read_bytes()).hexdigest()[:12]


def read_toml(toml_path: Path) -> dict:
    """Read .skills.toml. Returns {'skill-repo': str, 'skills': dict}.
    Returns empty structure if the file does not exist.
    """
    if not toml_path.is_file():
        return {"skill-repo": "", "skills": {}}
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    return {
        "skill-repo": data.get("skill-repo", ""),
        "skills": data.get("skills", {}),
    }


def write_toml(toml_path: Path, data: dict) -> None:
    """Write .skills.toml atomically. data keys: 'skill-repo', 'skills'."""
    lines: list[str] = []
    repo_url = data.get("skill-repo", "")
    if repo_url:
        lines.append(f'skill-repo = "{repo_url}"\n\n')
    lines.append("[skills]\n")
    for name, attrs in sorted(data.get("skills", {}).items()):
        sha = attrs.get("sha", "")
        installed = attrs.get("installed", "")
        if installed:
            lines.append(f'{name} = {{ sha = "{sha}", installed = "{installed}" }}\n')
        elif sha:
            lines.append(f'{name} = {{ sha = "{sha}" }}\n')
        else:
            lines.append(f'{name} = {{}}\n')
    content = "".join(lines)
    toml_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".skills.", suffix=".tmp", dir=str(toml_path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, toml_path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def copy_skill(src: Path, dst: Path) -> None:
    """Copy skill directory tree recursively. dst must not already exist."""
    if dst.exists():
        raise FileExistsError(f"Destination already exists: {dst}")
    shutil.copytree(src, dst)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/skill-repo && uv run pytest tests/test_snapshot.py -v
```
Expected: all 13 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/skill-repo && git add src/skillsync/snapshot.py tests/test_snapshot.py
git commit -m "feat(snapshot): sha computation + TOML I/O + dir-copy utilities"
```

---

## Task 2: push_cmd.py — promote local skill into repo

**Files:**
- Create: `src/skillsync/push_cmd.py`
- Create: `tests/test_push_cmd.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_push_cmd.py
"""Tests for skillsync.push_cmd."""
from __future__ import annotations

from pathlib import Path

import pytest

from skillsync import push_cmd


def _skill(base: Path, name: str, content: str = "body") -> Path:
    d = base / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n{content}")
    return d


@pytest.fixture
def world(tmp_path):
    repo = tmp_path / "repo_skills"
    repo.mkdir()
    claude = tmp_path / "claude_skills"
    claude.mkdir()
    codex = tmp_path / "codex_skills"
    codex.mkdir()
    return repo, claude, codex


class TestFindSource:
    def test_returns_real_dir_in_claude(self, world):
        repo, claude, codex = world
        _skill(claude, "alpha")
        found = push_cmd._find_source("alpha", claude, codex)
        assert found == claude / "alpha"

    def test_skips_symlinks(self, world, tmp_path):
        repo, claude, codex = world
        real = _skill(tmp_path / "real", "alpha")
        (claude / "alpha").symlink_to(real, target_is_directory=True)
        found = push_cmd._find_source("alpha", claude, codex)
        assert found is None  # symlink skipped

    def test_returns_none_if_not_found(self, world):
        repo, claude, codex = world
        assert push_cmd._find_source("missing", claude, codex) is None


class TestRun:
    def test_push_new_skill_to_repo(self, world):
        repo, claude, codex = world
        _skill(claude, "alpha")
        code = push_cmd.run(
            name="alpha",
            source_dir=claude / "alpha",
            repo_skills_dir=repo,
            claude_dir=claude,
            codex_dir=codex,
            yes=True,
        )
        assert code == 0
        assert (repo / "alpha" / "SKILL.md").is_file()

    def test_push_same_sha_is_noop(self, world, capsys):
        repo, claude, codex = world
        _skill(claude, "alpha", "same")
        _skill(repo, "alpha", "same")
        code = push_cmd.run(
            name="alpha",
            source_dir=claude / "alpha",
            repo_skills_dir=repo,
            claude_dir=claude,
            codex_dir=codex,
            yes=True,
        )
        assert code == 0
        out = capsys.readouterr().out
        assert "sha matches" in out or "nothing to do" in out

    def test_push_conflict_yes_overwrites_repo(self, world):
        repo, claude, codex = world
        _skill(claude, "alpha", "local-version")
        _skill(repo, "alpha", "repo-version")
        code = push_cmd.run(
            name="alpha",
            source_dir=claude / "alpha",
            repo_skills_dir=repo,
            claude_dir=claude,
            codex_dir=codex,
            yes=True,
        )
        assert code == 0
        assert "local-version" in (repo / "alpha" / "SKILL.md").read_text()

    def test_push_missing_source_returns_1(self, world):
        repo, claude, codex = world
        code = push_cmd.run(
            name="ghost",
            source_dir=claude / "ghost",
            repo_skills_dir=repo,
            claude_dir=claude,
            codex_dir=codex,
            yes=True,
        )
        assert code == 1

    def test_push_source_without_skill_md_returns_1(self, world):
        repo, claude, codex = world
        (claude / "bad").mkdir()
        code = push_cmd.run(
            name="bad",
            source_dir=claude / "bad",
            repo_skills_dir=repo,
            claude_dir=claude,
            codex_dir=codex,
            yes=True,
        )
        assert code == 1

    def test_push_conflict_skip_leaves_repo_unchanged(self, world, monkeypatch):
        repo, claude, codex = world
        _skill(claude, "alpha", "local-version")
        _skill(repo, "alpha", "repo-version")
        monkeypatch.setattr("builtins.input", lambda _: "skip")
        code = push_cmd.run(
            name="alpha",
            source_dir=claude / "alpha",
            repo_skills_dir=repo,
            claude_dir=claude,
            codex_dir=codex,
            yes=False,
        )
        assert code == 0
        assert "repo-version" in (repo / "alpha" / "SKILL.md").read_text()

    def test_push_conflict_keep_repo_returns_0(self, world, monkeypatch):
        repo, claude, codex = world
        _skill(claude, "alpha", "local-version")
        _skill(repo, "alpha", "repo-version")
        monkeypatch.setattr("builtins.input", lambda _: "repo")
        code = push_cmd.run(
            name="alpha",
            source_dir=claude / "alpha",
            repo_skills_dir=repo,
            claude_dir=claude,
            codex_dir=codex,
            yes=False,
        )
        assert code == 0
        assert "repo-version" in (repo / "alpha" / "SKILL.md").read_text()

    def test_auto_detect_source_from_claude_dir(self, world):
        repo, claude, codex = world
        _skill(claude, "alpha")  # real dir, not symlink
        code = push_cmd.run(
            name="alpha",
            source_dir=None,
            repo_skills_dir=repo,
            claude_dir=claude,
            codex_dir=codex,
            yes=True,
        )
        assert code == 0
        assert (repo / "alpha" / "SKILL.md").is_file()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/skill-repo && uv run pytest tests/test_push_cmd.py -v 2>&1 | head -15
```
Expected: `ModuleNotFoundError: No module named 'skillsync.push_cmd'`

- [ ] **Step 3: Implement push_cmd.py**

```python
# src/skillsync/push_cmd.py
"""skill-sync push: copy a local skill into ~/skill-repo/skills/ and commit."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from skillsync import init_cmd
from skillsync.paths import (
    CLAUDE_USER_SKILLS_DIR,
    CODEX_USER_SKILLS_DIR,
    SKILLS_DIR,
)
from skillsync.snapshot import copy_skill, skill_sha


def _find_source(name: str, claude_dir: Path, codex_dir: Path) -> Path | None:
    """Return the first real (non-symlink) skill dir for this name."""
    for d in (claude_dir, codex_dir):
        p = d / name
        if p.is_dir() and not p.is_symlink():
            return p
    return None


def run(
    name: str,
    source_dir: Path | None = None,
    repo_skills_dir: Path = SKILLS_DIR,
    claude_dir: Path = CLAUDE_USER_SKILLS_DIR,
    codex_dir: Path = CODEX_USER_SKILLS_DIR,
    yes: bool = False,
) -> int:
    if source_dir is None:
        source_dir = _find_source(name, claude_dir, codex_dir)
    if source_dir is None or not source_dir.is_dir():
        print(f"error: skill '{name}' not found as a real directory", file=sys.stderr)
        return 1
    if not (source_dir / "SKILL.md").is_file():
        print(f"error: {source_dir} has no SKILL.md", file=sys.stderr)
        return 1

    dest = repo_skills_dir / name

    if dest.exists():
        local_sha = skill_sha(source_dir)
        repo_sha = skill_sha(dest)
        if local_sha == repo_sha:
            print(f"'{name}' already in repo (sha matches) — nothing to do.")
            return 0

        if yes:
            choice = "local"
        else:
            print(f"Conflict: '{name}' exists in repo with different content.")
            print(f"  local sha: {local_sha}  repo sha: {repo_sha}")
            raw = input("  [local=overwrite repo / repo=keep repo / skip]: ").strip().lower()
            choice = "local" if raw == "local" else ("repo" if raw == "repo" else "skip")

        if choice == "skip":
            print(f"  skipped '{name}'.")
            return 0
        if choice == "repo":
            print(f"  keeping repo version of '{name}'.")
            return 0
        shutil.rmtree(dest)

    copy_skill(source_dir, dest)
    sha = skill_sha(dest)
    print(f"pushed '{name}' → {dest} (sha={sha})")

    try:
        subprocess.run(
            ["git", "-C", str(repo_skills_dir.parent), "add", f"skills/{name}"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_skills_dir.parent), "commit",
             "-m", f"feat(skills): push {name}"],
            check=True, capture_output=True,
        )
        print("committed to repo.")
    except subprocess.CalledProcessError as e:
        print(f"  (git commit skipped: {e.stderr.decode().strip()})", file=sys.stderr)

    for d in (claude_dir, codex_dir):
        init_cmd.wire_symlinks(repo_skills_dir=repo_skills_dir, target_dir=d)

    return 0
```

- [ ] **Step 4: Wire push into cli.py**

In `src/skillsync/cli.py`, add after the existing `sub.add_parser("list", ...)` line:

```python
    p_push = sub.add_parser("push", help="Copy local skill into repo")
    p_push.add_argument("name", help="Skill name")
    p_push.add_argument("--source", help="Source directory (default: auto-detect from ~/.claude/skills/)")
    p_push.add_argument("--yes", action="store_true", help="Non-interactive; overwrite repo on conflict")
```

And add the dispatch at the end of the if-chain:

```python
    if args.cmd == "push":
        from skillsync.push_cmd import run as push_run
        from pathlib import Path
        return push_run(
            name=args.name,
            source_dir=Path(args.source) if args.source else None,
            yes=args.yes,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ~/skill-repo && uv run pytest tests/test_push_cmd.py -v
```
Expected: 9 tests PASS.

- [ ] **Step 6: Smoke-test CLI**

```bash
skill-sync push --help
```
Expected: help text showing `push <name> [--source PATH] [--yes]`.

- [ ] **Step 7: Commit**

```bash
cd ~/skill-repo && git add src/skillsync/push_cmd.py tests/test_push_cmd.py src/skillsync/cli.py
git commit -m "feat(push): promote local skill into repo with conflict resolution"
```

---

## Task 3: install_cmd.py — snapshot skill into project scope

**Files:**
- Create: `src/skillsync/install_cmd.py`
- Create: `tests/test_install_cmd.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_install_cmd.py
"""Tests for skillsync.install_cmd."""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from skillsync import install_cmd
from skillsync.snapshot import skill_sha


def _skill(base: Path, name: str, content: str = "body") -> Path:
    d = base / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n{content}")
    return d


@pytest.fixture
def world(tmp_path):
    repo = tmp_path / "repo_skills"
    repo.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    return repo, project


class TestRun:
    def test_installs_to_claude_and_codex(self, world):
        repo, project = world
        _skill(repo, "alpha")
        code = install_cmd.run(
            name="alpha",
            project_dir=project,
            repo_skills_dir=repo,
            yes=True,
        )
        assert code == 0
        assert (project / ".claude" / "skills" / "alpha" / "SKILL.md").is_file()
        assert (project / ".codex" / "skills" / "alpha" / "SKILL.md").is_file()

    def test_writes_skills_toml(self, world):
        repo, project = world
        _skill(repo, "alpha")
        install_cmd.run(name="alpha", project_dir=project, repo_skills_dir=repo, yes=True)
        p = project / ".skills.toml"
        assert p.is_file()
        with open(p, "rb") as f:
            data = tomllib.load(f)
        assert "alpha" in data["skills"]
        assert len(data["skills"]["alpha"]["sha"]) == 12

    def test_sha_in_toml_matches_repo_skill(self, world):
        repo, project = world
        src = _skill(repo, "alpha")
        install_cmd.run(name="alpha", project_dir=project, repo_skills_dir=repo, yes=True)
        with open(project / ".skills.toml", "rb") as f:
            data = tomllib.load(f)
        assert data["skills"]["alpha"]["sha"] == skill_sha(src)

    def test_up_to_date_snapshot_skips_copy(self, world, capsys):
        repo, project = world
        _skill(repo, "alpha")
        install_cmd.run(name="alpha", project_dir=project, repo_skills_dir=repo, yes=True)
        capsys.readouterr()
        # Second install — same sha — should not recopy
        code = install_cmd.run(name="alpha", project_dir=project, repo_skills_dir=repo, yes=True)
        out = capsys.readouterr().out
        assert code == 0
        assert "up to date" in out

    def test_missing_repo_skill_returns_1(self, world):
        repo, project = world
        code = install_cmd.run(name="ghost", project_dir=project, repo_skills_dir=repo, yes=True)
        assert code == 1

    def test_updates_existing_toml_entry(self, world):
        repo, project = world
        _skill(repo, "alpha", "v1")
        install_cmd.run(name="alpha", project_dir=project, repo_skills_dir=repo, yes=True)
        # Modify repo skill
        (repo / "alpha" / "SKILL.md").write_text("---\nname: alpha\ndescription: x\n---\nv2")
        install_cmd.run(name="alpha", project_dir=project, repo_skills_dir=repo, yes=True)
        with open(project / ".skills.toml", "rb") as f:
            data = tomllib.load(f)
        assert data["skills"]["alpha"]["sha"] == skill_sha(repo / "alpha")

    def test_installed_date_recorded(self, world):
        repo, project = world
        _skill(repo, "alpha")
        install_cmd.run(name="alpha", project_dir=project, repo_skills_dir=repo, yes=True)
        with open(project / ".skills.toml", "rb") as f:
            data = tomllib.load(f)
        installed = data["skills"]["alpha"].get("installed", "")
        assert installed  # e.g. "2026-05-13"
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2}", installed)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/skill-repo && uv run pytest tests/test_install_cmd.py -v 2>&1 | head -15
```
Expected: `ModuleNotFoundError: No module named 'skillsync.install_cmd'`

- [ ] **Step 3: Implement install_cmd.py**

```python
# src/skillsync/install_cmd.py
"""skill-sync install: snapshot a repo skill into project scope."""
from __future__ import annotations

import shutil
import sys
from datetime import date
from pathlib import Path

from skillsync.paths import SKILLS_DIR
from skillsync.snapshot import copy_skill, read_toml, skill_sha, write_toml

_CLAUDE_REL = Path(".claude") / "skills"
_CODEX_REL = Path(".codex") / "skills"
_TOML_REL = Path(".skills.toml")


def run(
    name: str,
    project_dir: Path | None = None,
    repo_skills_dir: Path = SKILLS_DIR,
    yes: bool = False,
) -> int:
    if project_dir is None:
        project_dir = Path.cwd()

    src = repo_skills_dir / name
    if not src.is_dir() or not (src / "SKILL.md").is_file():
        print(f"error: skill '{name}' not found in repo", file=sys.stderr)
        return 1

    sha = skill_sha(src)
    today = date.today().isoformat()

    for rel_dir in (_CLAUDE_REL, _CODEX_REL):
        dst = project_dir / rel_dir / name
        if dst.exists():
            try:
                existing_sha = skill_sha(dst)
            except FileNotFoundError:
                existing_sha = ""
            if existing_sha == sha:
                print(f"  {rel_dir}/{name}: already up to date (sha={sha})")
                continue
            if not yes:
                raw = input(f"  {rel_dir}/{name}: exists with different sha. Overwrite? [y/N]: ")
                if raw.strip().lower() != "y":
                    print(f"  skipped {rel_dir}/{name}")
                    continue
            shutil.rmtree(dst)
        copy_skill(src, dst)
        print(f"  installed → {dst} (sha={sha})")

    toml_path = project_dir / _TOML_REL
    data = read_toml(toml_path)
    data["skills"][name] = {"sha": sha, "installed": today}
    write_toml(toml_path, data)
    print(f"  updated {toml_path}")
    return 0
```

- [ ] **Step 4: Wire install into cli.py**

Add to the subparsers block in `src/skillsync/cli.py`:

```python
    p_install = sub.add_parser("install", help="Snapshot a repo skill into project scope")
    p_install.add_argument("name", help="Skill name")
    p_install.add_argument("--scope", default="project", choices=["project"],
                           help="Scope (only 'project' supported)")
    p_install.add_argument("--project-path", default=".", help="Project root (default: .)")
    p_install.add_argument("--yes", action="store_true", help="Non-interactive")
```

And dispatch:

```python
    if args.cmd == "install":
        from skillsync.install_cmd import run as install_run
        from pathlib import Path
        return install_run(
            name=args.name,
            project_dir=Path(args.project_path),
            yes=args.yes,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ~/skill-repo && uv run pytest tests/test_install_cmd.py -v
```
Expected: 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd ~/skill-repo && git add src/skillsync/install_cmd.py tests/test_install_cmd.py src/skillsync/cli.py
git commit -m "feat(install): snapshot repo skill into project scope with .skills.toml tracking"
```

---

## Task 4: move_cmd.py — migrate a skill between user and project scope

**Files:**
- Create: `src/skillsync/move_cmd.py`
- Create: `tests/test_move_cmd.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_move_cmd.py
"""Tests for skillsync.move_cmd."""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from skillsync import move_cmd


def _skill(base: Path, name: str, content: str = "body") -> Path:
    d = base / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n{content}")
    return d


@pytest.fixture
def world(tmp_path):
    repo = tmp_path / "repo_skills"
    repo.mkdir()
    claude = tmp_path / "claude_skills"
    claude.mkdir()
    codex = tmp_path / "codex_skills"
    codex.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    _skill(repo, "alpha")
    return repo, claude, codex, project


class TestMoveToProject:
    def test_installs_project_snapshot(self, world):
        repo, claude, codex, project = world
        code = move_cmd.run(
            name="alpha",
            to="project",
            project_dir=project,
            repo_skills_dir=repo,
            claude_dir=claude,
            codex_dir=codex,
        )
        assert code == 0
        assert (project / ".claude" / "skills" / "alpha" / "SKILL.md").is_file()
        assert (project / ".skills.toml").is_file()

    def test_toml_records_sha(self, world):
        repo, claude, codex, project = world
        move_cmd.run(
            name="alpha", to="project", project_dir=project,
            repo_skills_dir=repo, claude_dir=claude, codex_dir=codex,
        )
        with open(project / ".skills.toml", "rb") as f:
            data = tomllib.load(f)
        assert "alpha" in data["skills"]
        assert data["skills"]["alpha"]["sha"]


class TestMoveToUser:
    def _install(self, world):
        repo, claude, codex, project = world
        for rel in (Path(".claude") / "skills", Path(".codex") / "skills"):
            dst = project / rel / "alpha"
            dst.mkdir(parents=True)
            (dst / "SKILL.md").write_text("---\nname: alpha\ndescription: x\n---\nbody")
        from skillsync.snapshot import write_toml
        write_toml(
            project / ".skills.toml",
            {"skill-repo": "", "skills": {"alpha": {"sha": "abc123def456"}}},
        )

    def test_removes_project_snapshot(self, world):
        repo, claude, codex, project = world
        self._install(world)
        code = move_cmd.run(
            name="alpha", to="user", project_dir=project,
            repo_skills_dir=repo, claude_dir=claude, codex_dir=codex,
        )
        assert code == 0
        assert not (project / ".claude" / "skills" / "alpha").exists()
        assert not (project / ".codex" / "skills" / "alpha").exists()

    def test_removes_from_skills_toml(self, world):
        repo, claude, codex, project = world
        self._install(world)
        move_cmd.run(
            name="alpha", to="user", project_dir=project,
            repo_skills_dir=repo, claude_dir=claude, codex_dir=codex,
        )
        with open(project / ".skills.toml", "rb") as f:
            data = tomllib.load(f)
        assert "alpha" not in data.get("skills", {})

    def test_wires_user_symlink(self, world):
        repo, claude, codex, project = world
        self._install(world)
        move_cmd.run(
            name="alpha", to="user", project_dir=project,
            repo_skills_dir=repo, claude_dir=claude, codex_dir=codex,
        )
        assert (claude / "alpha").is_symlink()
        assert (codex / "alpha").is_symlink()

    def test_no_project_snapshot_still_wires_symlink(self, world):
        repo, claude, codex, project = world
        code = move_cmd.run(
            name="alpha", to="user", project_dir=project,
            repo_skills_dir=repo, claude_dir=claude, codex_dir=codex,
        )
        assert code == 0
        assert (claude / "alpha").is_symlink()


class TestInvalidTo:
    def test_returns_1_on_invalid_to(self, world):
        repo, claude, codex, project = world
        code = move_cmd.run(
            name="alpha", to="invalid",
            project_dir=project, repo_skills_dir=repo,
            claude_dir=claude, codex_dir=codex,
        )
        assert code == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/skill-repo && uv run pytest tests/test_move_cmd.py -v 2>&1 | head -15
```
Expected: `ModuleNotFoundError: No module named 'skillsync.move_cmd'`

- [ ] **Step 3: Implement move_cmd.py**

```python
# src/skillsync/move_cmd.py
"""skill-sync move: migrate a skill between user and project scope."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from skillsync import init_cmd, install_cmd
from skillsync.paths import (
    CLAUDE_USER_SKILLS_DIR,
    CODEX_USER_SKILLS_DIR,
    SKILLS_DIR,
)
from skillsync.snapshot import read_toml, write_toml

_CLAUDE_REL = Path(".claude") / "skills"
_CODEX_REL = Path(".codex") / "skills"
_TOML_REL = Path(".skills.toml")


def run(
    name: str,
    to: str,
    project_dir: Path | None = None,
    repo_skills_dir: Path = SKILLS_DIR,
    claude_dir: Path = CLAUDE_USER_SKILLS_DIR,
    codex_dir: Path = CODEX_USER_SKILLS_DIR,
) -> int:
    if project_dir is None:
        project_dir = Path.cwd()

    if to == "project":
        return install_cmd.run(
            name=name,
            project_dir=project_dir,
            repo_skills_dir=repo_skills_dir,
            yes=True,
        )

    if to == "user":
        for rel in (_CLAUDE_REL, _CODEX_REL):
            p = project_dir / rel / name
            if p.exists() and not p.is_symlink():
                shutil.rmtree(p)
                print(f"  removed project snapshot: {p}")

        toml_path = project_dir / _TOML_REL
        data = read_toml(toml_path)
        if name in data["skills"]:
            del data["skills"][name]
            write_toml(toml_path, data)
            print(f"  removed '{name}' from .skills.toml")

        for d in (claude_dir, codex_dir):
            init_cmd.wire_symlinks(repo_skills_dir=repo_skills_dir, target_dir=d)
        print("  user-level symlinks refreshed")
        return 0

    print(f"error: --to must be 'user' or 'project', got {to!r}", file=sys.stderr)
    return 1
```

- [ ] **Step 4: Wire move into cli.py**

Add to subparsers block in `src/skillsync/cli.py`:

```python
    p_move = sub.add_parser("move", help="Migrate a skill between user and project scope")
    p_move.add_argument("name", help="Skill name")
    p_move.add_argument("--to", required=True, choices=["user", "project"],
                        help="Target scope")
    p_move.add_argument("--project-path", default=".", help="Project root (default: .)")
```

And dispatch:

```python
    if args.cmd == "move":
        from skillsync.move_cmd import run as move_run
        from pathlib import Path
        return move_run(
            name=args.name,
            to=args.to,
            project_dir=Path(args.project_path),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ~/skill-repo && uv run pytest tests/test_move_cmd.py -v
```
Expected: 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd ~/skill-repo && git add src/skillsync/move_cmd.py tests/test_move_cmd.py src/skillsync/cli.py
git commit -m "feat(move): migrate skills between user and project scope"
```

---

## Task 5: list --scope — show project-scope skills

**Files:**
- Modify: `src/skillsync/list_cmd.py`
- Modify: `src/skillsync/cli.py`
- Modify: `tests/test_list_cmd.py`

- [ ] **Step 1: Write the failing tests (append to existing test file)**

```python
# Append to tests/test_list_cmd.py

from skillsync.list_cmd import collect_project, ProjectRow
from skillsync.snapshot import skill_sha


def _make_repo_skill(base: Path, name: str, content: str = "body") -> Path:
    d = base / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n{content}")
    return d


class TestCollectProject:
    def test_returns_empty_for_missing_toml(self, tmp_path):
        rows = collect_project(project_dir=tmp_path, repo_skills_dir=tmp_path / "repo")
        assert rows == []

    def test_returns_row_per_toml_entry(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_repo_skill(repo, "alpha")
        from skillsync.snapshot import write_toml, skill_sha
        sha = skill_sha(repo / "alpha")
        write_toml(tmp_path / ".skills.toml", {
            "skill-repo": "", "skills": {"alpha": {"sha": sha, "installed": "2026-05-13"}},
        })
        rows = collect_project(project_dir=tmp_path, repo_skills_dir=repo)
        assert len(rows) == 1
        assert rows[0]["name"] == "alpha"
        assert rows[0]["status"] == "ok"

    def test_detects_sha_drift(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_repo_skill(repo, "alpha", "v1")
        from skillsync.snapshot import write_toml
        write_toml(tmp_path / ".skills.toml", {
            "skill-repo": "", "skills": {"alpha": {"sha": "000000000000"}},
        })
        rows = collect_project(project_dir=tmp_path, repo_skills_dir=repo)
        assert rows[0]["status"] == "drift"

    def test_missing_in_repo_marked_as_missing(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        from skillsync.snapshot import write_toml
        write_toml(tmp_path / ".skills.toml", {
            "skill-repo": "", "skills": {"ghost": {"sha": "aabbcc112233"}},
        })
        rows = collect_project(project_dir=tmp_path, repo_skills_dir=repo)
        assert rows[0]["status"] == "missing"


class TestRunScope:
    def _setup(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_repo_skill(repo, "alpha")
        claude = tmp_path / "claude"
        claude.mkdir()
        codex = tmp_path / "codex"
        codex.mkdir()
        return repo, claude, codex

    def test_scope_user_shows_user_skills(self, tmp_path, capsys):
        repo, claude, codex = self._setup(tmp_path)
        from skillsync.list_cmd import run
        run(repo_skills_dir=repo, claude_dir=claude, codex_dir=codex, scope="user")
        out = capsys.readouterr().out
        assert "alpha" in out

    def test_scope_project_shows_toml_entries(self, tmp_path, capsys):
        repo, claude, codex = self._setup(tmp_path)
        from skillsync.snapshot import write_toml, skill_sha
        sha = skill_sha(repo / "alpha")
        write_toml(tmp_path / ".skills.toml", {
            "skill-repo": "", "skills": {"alpha": {"sha": sha}},
        })
        from skillsync.list_cmd import run
        run(repo_skills_dir=repo, claude_dir=claude, codex_dir=codex,
            scope="project", project_dir=tmp_path)
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "ok" in out.lower() or "drift" in out.lower() or "missing" in out.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/skill-repo && uv run pytest tests/test_list_cmd.py -k "TestCollectProject or TestRunScope" -v 2>&1 | head -20
```
Expected: `ImportError: cannot import name 'collect_project'`

- [ ] **Step 3: Add collect_project and scope to list_cmd.py**

At the end of `src/skillsync/list_cmd.py` (after the existing `run` function), add:

```python
from typing import Literal as _Literal


class ProjectRow(TypedDict):
    name: str
    sha_pinned: str
    sha_current: str
    status: _Literal["ok", "drift", "missing"]
    installed: str


def collect_project(
    project_dir: Path = Path("."),
    repo_skills_dir: Path = SKILLS_DIR,
) -> list[ProjectRow]:
    """Read .skills.toml and compare each pinned sha against current repo."""
    from skillsync.snapshot import read_toml, skill_sha
    data = read_toml(project_dir / ".skills.toml")
    rows: list[ProjectRow] = []
    for name, attrs in sorted(data["skills"].items()):
        sha_pinned = attrs.get("sha", "")
        installed = attrs.get("installed", "")
        repo_dir = repo_skills_dir / name
        if not repo_dir.is_dir():
            rows.append(ProjectRow(
                name=name, sha_pinned=sha_pinned, sha_current="",
                status="missing", installed=installed,
            ))
            continue
        try:
            sha_current = skill_sha(repo_dir)
        except FileNotFoundError:
            sha_current = ""
        status: _Literal["ok", "drift", "missing"] = (
            "ok" if sha_current == sha_pinned else "drift" if sha_current else "missing"
        )
        rows.append(ProjectRow(
            name=name, sha_pinned=sha_pinned, sha_current=sha_current,
            status=status, installed=installed,
        ))
    return rows
```

Also modify the existing `run` function signature to accept `scope` and `project_dir`:

```python
def run(
    repo_skills_dir: Path = SKILLS_DIR,
    claude_dir: Path = CLAUDE_USER_SKILLS_DIR,
    codex_dir: Path = CODEX_USER_SKILLS_DIR,
    scope: str = "user",
    project_dir: Path | None = None,
) -> int:
    if scope in ("user", "all"):
        rows = collect(repo_skills_dir=repo_skills_dir, claude_dir=claude_dir, codex_dir=codex_dir)
        if not rows:
            print("(no user-scope skills found)")
        else:
            print(f"  {'in-repo':<5} {'name':<30} {'claude':<14} {'codex'}")
            for row in rows:
                print(_fmt_row(row))

    if scope in ("project", "all"):
        pd = project_dir if project_dir is not None else Path.cwd()
        proj_rows = collect_project(project_dir=pd, repo_skills_dir=repo_skills_dir)
        if not proj_rows:
            print("(no project-scope skills in .skills.toml)")
        else:
            print(f"\n  {'name':<30} {'status':<8} {'sha_pinned':<14} {'installed'}")
            for r in proj_rows:
                print(f"  {r['name']:<30} {r['status']:<8} {r['sha_pinned']:<14} {r['installed']}")

    if scope not in ("user", "project", "all"):
        import sys
        print(f"error: --scope must be user|project|all, got {scope!r}", file=sys.stderr)
        return 1
    return 0
```

- [ ] **Step 4: Update list subparser in cli.py**

Replace the existing `sub.add_parser("list", ...)` line with:

```python
    p_list = sub.add_parser("list", help="List skills across repo / ~/.claude / ~/.codex")
    p_list.add_argument("--scope", default="user", choices=["user", "project", "all"],
                        help="Which scope to show (default: user)")
    p_list.add_argument("--project-path", default=".", help="Project root for --scope project|all")
```

And update the dispatch:

```python
    if args.cmd == "list":
        from skillsync.list_cmd import run as list_run
        from pathlib import Path
        return list_run(scope=args.scope, project_dir=Path(args.project_path))
```

- [ ] **Step 5: Run full test suite to verify no regressions**

```bash
cd ~/skill-repo && uv run pytest -v 2>&1 | tail -20
```
Expected: all previous tests + new tests PASS.

- [ ] **Step 6: Commit**

```bash
cd ~/skill-repo && git add src/skillsync/list_cmd.py src/skillsync/cli.py tests/test_list_cmd.py
git commit -m "feat(list): add --scope user|project|all with .skills.toml project view"
```

---

## Task 6: doctor sha-drift — check .skills.toml against repo

**Files:**
- Modify: `src/skillsync/doctor.py`
- Modify: `src/skillsync/cli.py`
- Modify: `tests/test_doctor.py`

- [ ] **Step 1: Write the failing tests (append to existing test file)**

```python
# Append to tests/test_doctor.py

from skillsync.snapshot import skill_sha, write_toml


class TestCheckProjectDrift:
    def _make_repo_skill(self, base: Path, name: str, content: str = "body") -> Path:
        d = base / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n{content}")
        return d

    def test_no_toml_returns_no_findings(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        from skillsync.doctor import _check_project_drift
        findings = _check_project_drift(project_dir=tmp_path, repo_skills_dir=repo)
        assert findings == []

    def test_matching_sha_returns_no_findings(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        self._make_repo_skill(repo, "alpha")
        sha = skill_sha(repo / "alpha")
        write_toml(tmp_path / ".skills.toml", {
            "skill-repo": "", "skills": {"alpha": {"sha": sha}},
        })
        from skillsync.doctor import _check_project_drift
        findings = _check_project_drift(project_dir=tmp_path, repo_skills_dir=repo)
        assert findings == []

    def test_sha_drift_emits_warn(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        self._make_repo_skill(repo, "alpha", "v1")
        write_toml(tmp_path / ".skills.toml", {
            "skill-repo": "", "skills": {"alpha": {"sha": "000000000000"}},
        })
        from skillsync.doctor import _check_project_drift
        findings = _check_project_drift(project_dir=tmp_path, repo_skills_dir=repo)
        assert len(findings) == 1
        assert findings[0]["severity"] == "warn"
        assert "drift" in findings[0]["message"].lower()

    def test_skill_missing_from_repo_emits_warn(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        write_toml(tmp_path / ".skills.toml", {
            "skill-repo": "", "skills": {"ghost": {"sha": "abc123def456"}},
        })
        from skillsync.doctor import _check_project_drift
        findings = _check_project_drift(project_dir=tmp_path, repo_skills_dir=repo)
        assert len(findings) == 1
        assert findings[0]["severity"] == "warn"

    def test_check_includes_project_drift_when_project_dir_given(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        self._make_repo_skill(repo, "alpha", "v1")
        write_toml(tmp_path / ".skills.toml", {
            "skill-repo": "", "skills": {"alpha": {"sha": "000000000000"}},
        })
        claude = tmp_path / "claude"
        claude.mkdir()
        codex = tmp_path / "codex"
        codex.mkdir()
        from skillsync.doctor import check
        findings = check(
            repo_skills_dir=repo, claude_dir=claude, codex_dir=codex,
            project_dir=tmp_path,
        )
        drift_findings = [f for f in findings if "drift" in f["message"].lower()]
        assert drift_findings
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/skill-repo && uv run pytest tests/test_doctor.py -k "TestCheckProjectDrift" -v 2>&1 | head -20
```
Expected: `ImportError: cannot import name '_check_project_drift'`

- [ ] **Step 3: Add _check_project_drift to doctor.py**

After the `_check_duplicate_names` function, add:

```python
def _check_project_drift(
    project_dir: Path,
    repo_skills_dir: Path,
) -> list[Finding]:
    """WARN for each .skills.toml entry whose pinned sha differs from the repo's current sha."""
    from skillsync.snapshot import read_toml, skill_sha
    toml_path = project_dir / ".skills.toml"
    if not toml_path.is_file():
        return []
    data = read_toml(toml_path)
    findings: list[Finding] = []
    for name, attrs in data["skills"].items():
        sha_pinned = attrs.get("sha", "")
        repo_dir = repo_skills_dir / name
        if not repo_dir.is_dir():
            findings.append(Finding(
                severity="warn", name=name,
                message=f".skills.toml references '{name}' but skill not in repo",
            ))
            continue
        try:
            sha_current = skill_sha(repo_dir)
        except FileNotFoundError:
            findings.append(Finding(
                severity="warn", name=name,
                message=f"'{name}' in repo but has no SKILL.md",
            ))
            continue
        if sha_pinned and sha_current != sha_pinned:
            findings.append(Finding(
                severity="warn", name=name,
                message=f"sha drift in .skills.toml: pinned={sha_pinned} current={sha_current}",
            ))
    return findings
```

Also update the `check` function signature to accept `project_dir`:

```python
def check(
    repo_skills_dir: Path = SKILLS_DIR,
    claude_dir: Path = CLAUDE_USER_SKILLS_DIR,
    codex_dir: Path = CODEX_USER_SKILLS_DIR,
    project_dir: Path | None = None,
) -> list[Finding]:
    """Run all checks; return findings in stable order."""
    findings: list[Finding] = []
    if repo_skills_dir.is_dir():
        for child in sorted(repo_skills_dir.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            findings.extend(_check_skill(child))
        findings.extend(_check_duplicate_names(repo_skills_dir))
    findings.extend(_check_symlinks(claude_dir, "~/.claude/skills", repo_skills_dir))
    findings.extend(_check_symlinks(codex_dir, "~/.codex/skills", repo_skills_dir))
    if project_dir is not None:
        findings.extend(_check_project_drift(project_dir, repo_skills_dir))
    return findings
```

And update `run` to pass `project_dir`:

```python
def run(
    quiet: bool = False,
    repo_skills_dir: Path = SKILLS_DIR,
    claude_dir: Path = CLAUDE_USER_SKILLS_DIR,
    codex_dir: Path = CODEX_USER_SKILLS_DIR,
    project_dir: Path | None = None,
) -> int:
    findings = check(
        repo_skills_dir=repo_skills_dir, claude_dir=claude_dir, codex_dir=codex_dir,
        project_dir=project_dir,
    )
    # ... rest unchanged
```

- [ ] **Step 4: Update doctor CLI to auto-detect .skills.toml**

In `src/skillsync/cli.py`, update the doctor dispatch to pass `project_dir`:

```python
    if args.cmd == "doctor":
        from skillsync.doctor import run as doctor_run
        from pathlib import Path
        pd = Path.cwd()
        return doctor_run(
            quiet=args.quiet,
            project_dir=pd if (pd / ".skills.toml").is_file() else None,
        )
```

- [ ] **Step 5: Run full test suite**

```bash
cd ~/skill-repo && uv run pytest -v 2>&1 | tail -20
```
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
cd ~/skill-repo && git add src/skillsync/doctor.py src/skillsync/cli.py tests/test_doctor.py
git commit -m "feat(doctor): add project .skills.toml sha-drift check"
```

---

## Task 7: sync project reconciliation — pull/push/leave on sha drift

**Files:**
- Modify: `src/skillsync/sync_cmd.py`
- Modify: `src/skillsync/cli.py`
- Modify: `tests/test_sync_cmd.py`

- [ ] **Step 1: Write the failing tests (append to existing test file)**

```python
# Append to tests/test_sync_cmd.py

from skillsync.snapshot import skill_sha, write_toml


def _make_skill(base: Path, name: str, content: str = "body") -> Path:
    d = base / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n{content}")
    return d


class TestReconcileProject:
    @pytest.fixture
    def proj_world(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        project = tmp_path / "project"
        project.mkdir()
        _make_skill(repo, "alpha", "v1")
        sha = skill_sha(repo / "alpha")
        # Install project snapshot with matching sha
        for rel in (Path(".claude") / "skills", Path(".codex") / "skills"):
            dst = project / rel / "alpha"
            dst.mkdir(parents=True)
            (dst / "SKILL.md").write_text(f"---\nname: alpha\ndescription: x\n---\nv1")
        write_toml(project / ".skills.toml", {
            "skill-repo": "", "skills": {"alpha": {"sha": sha, "installed": "2026-05-13"}},
        })
        return repo, project

    def test_no_drift_prints_nothing(self, proj_world, capsys):
        repo, project = proj_world
        from skillsync import sync_cmd
        sync_cmd._reconcile_project(project_dir=project, repo_skills_dir=repo, yes=True)
        out = capsys.readouterr().out
        # No drift, so nothing should be pulled or pushed
        assert "pulled" not in out
        assert "pushed" not in out

    def test_drift_pull_updates_project_snapshot(self, proj_world):
        repo, project = proj_world
        # Update repo to v2 (creates drift)
        (repo / "alpha" / "SKILL.md").write_text("---\nname: alpha\ndescription: x\n---\nv2")
        from skillsync import sync_cmd
        sync_cmd._reconcile_project(project_dir=project, repo_skills_dir=repo, yes=True)
        # Project snapshot should now contain v2
        assert "v2" in (project / ".claude" / "skills" / "alpha" / "SKILL.md").read_text()

    def test_drift_pull_updates_toml_sha(self, proj_world):
        repo, project = proj_world
        (repo / "alpha" / "SKILL.md").write_text("---\nname: alpha\ndescription: x\n---\nv2")
        from skillsync import sync_cmd
        sync_cmd._reconcile_project(project_dir=project, repo_skills_dir=repo, yes=True)
        import tomllib
        with open(project / ".skills.toml", "rb") as f:
            data = tomllib.load(f)
        assert data["skills"]["alpha"]["sha"] == skill_sha(repo / "alpha")

    def test_no_toml_returns_silently(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        project = tmp_path / "project"
        project.mkdir()
        from skillsync import sync_cmd
        sync_cmd._reconcile_project(project_dir=project, repo_skills_dir=repo, yes=True)
        # Should not raise

    def test_drift_leave_action_keeps_snapshot_unchanged(self, proj_world, monkeypatch):
        repo, project = proj_world
        (repo / "alpha" / "SKILL.md").write_text("---\nname: alpha\ndescription: x\n---\nv2")
        monkeypatch.setattr("builtins.input", lambda _: "leave")
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        from skillsync import sync_cmd
        sync_cmd._reconcile_project(
            project_dir=project, repo_skills_dir=repo, yes=False,
        )
        # Snapshot still v1
        assert "v1" in (project / ".claude" / "skills" / "alpha" / "SKILL.md").read_text()

    def test_run_calls_reconcile_when_toml_present(self, proj_world, capsys, tmp_path):
        repo, project = proj_world
        from skillsync import sync_cmd
        from skillsync.index_cmd import INDEX_PATH
        index_path = tmp_path / "index.json"
        claude = tmp_path / "claude"
        claude.mkdir()
        codex = tmp_path / "codex"
        codex.mkdir()
        code = sync_cmd.run(
            repo_skills_dir=repo,
            claude_dir=claude,
            codex_dir=codex,
            index_path=index_path,
            yes=True,
            project_dir=project,
        )
        assert code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/skill-repo && uv run pytest tests/test_sync_cmd.py -k "TestReconcileProject" -v 2>&1 | head -20
```
Expected: `AttributeError: module 'skillsync.sync_cmd' has no attribute '_reconcile_project'`

- [ ] **Step 3: Add _reconcile_project to sync_cmd.py**

After the `_heal_symlinks` function, add:

```python
def _reconcile_project(
    project_dir: Path,
    repo_skills_dir: Path,
    yes: bool = False,
) -> None:
    """Compare .skills.toml pinned shas against repo; prompt pull/push/leave per drift."""
    import shutil
    from skillsync.snapshot import copy_skill, read_toml, skill_sha, write_toml

    toml_path = project_dir / ".skills.toml"
    if not toml_path.is_file():
        return
    data = read_toml(toml_path)
    if not data["skills"]:
        return

    print("Checking .skills.toml sha drift…", flush=True)
    interactive = (not yes) and sys.stdin.isatty()
    updated = False

    for name, attrs in list(data["skills"].items()):
        sha_pinned = attrs.get("sha", "")
        repo_dir = repo_skills_dir / name
        if not repo_dir.is_dir():
            print(f"  warn: '{name}' in .skills.toml but not in repo — skipping")
            continue
        try:
            sha_current = skill_sha(repo_dir)
        except FileNotFoundError:
            print(f"  warn: '{name}' has no SKILL.md in repo — skipping")
            continue
        if sha_current == sha_pinned:
            continue

        print(f"  drift: {name} (pinned={sha_pinned} current={sha_current})")

        if yes:
            action = "pull"
        elif interactive:
            raw = input("    [pull=overwrite local / push=replace repo / leave]: ").strip().lower()
            action = raw if raw in ("pull", "push", "leave") else "leave"
        else:
            action = "leave"

        if action == "pull":
            for rel in (Path(".claude") / "skills", Path(".codex") / "skills"):
                p = project_dir / rel / name
                if p.exists() and not p.is_symlink():
                    shutil.rmtree(p)
                copy_skill(repo_dir, p)
            data["skills"][name] = {"sha": sha_current, "installed": attrs.get("installed", "")}
            updated = True
            print(f"  pulled '{name}' (sha={sha_current})")

        elif action == "push":
            project_snapshot = None
            for rel in (Path(".claude") / "skills", Path(".codex") / "skills"):
                p = project_dir / rel / name
                if p.is_dir() and not p.is_symlink():
                    project_snapshot = p
                    break
            if project_snapshot is None:
                print(f"  error: no project snapshot for '{name}' — cannot push", file=sys.stderr)
                continue
            shutil.rmtree(repo_dir)
            copy_skill(project_snapshot, repo_dir)
            new_sha = skill_sha(repo_dir)
            data["skills"][name] = {"sha": new_sha, "installed": attrs.get("installed", "")}
            updated = True
            print(f"  pushed '{name}' to repo (sha={new_sha})")

        else:
            print(f"  left '{name}' as is")

    if updated:
        write_toml(toml_path, data)
        print(f"  updated {toml_path}")
```

Also update `run` in sync_cmd.py to accept and use `project_dir`:

```python
def run(
    yes: bool = False,
    repo_skills_dir: Path = SKILLS_DIR,
    claude_dir: Path = CLAUDE_USER_SKILLS_DIR,
    codex_dir: Path = CODEX_USER_SKILLS_DIR,
    index_path: Path = INDEX_PATH,
    project_dir: Path | None = None,
) -> int:
    print("Healing per-skill symlinks…", flush=True)
    # ... existing healing code unchanged ...

    print("Regenerating index.json…", flush=True)
    # ... existing index code unchanged ...

    print("Scanning for local-only skills…", flush=True)
    # ... existing local-only code unchanged ...

    if project_dir is not None:
        _reconcile_project(project_dir=project_dir, repo_skills_dir=repo_skills_dir, yes=yes)

    return 0
```

- [ ] **Step 4: Update sync CLI dispatch to pass project_dir**

In `src/skillsync/cli.py`, update sync dispatch:

```python
    if args.cmd == "sync":
        from skillsync.sync_cmd import run as sync_run
        from pathlib import Path
        pd = Path.cwd()
        return sync_run(
            yes=args.yes,
            project_dir=pd if (pd / ".skills.toml").is_file() else None,
        )
```

- [ ] **Step 5: Run full test suite**

```bash
cd ~/skill-repo && uv run pytest -v 2>&1 | tail -25
```
Expected: all previous + new tests PASS. Count should be ~110+ total.

- [ ] **Step 6: Commit**

```bash
cd ~/skill-repo && git add src/skillsync/sync_cmd.py src/skillsync/cli.py tests/test_sync_cmd.py
git commit -m "feat(sync): add project .skills.toml reconciliation with pull/push/leave"
```

---

## Task 8: Live smoke test + push to remote

- [ ] **Step 1: Full test run from clean state**

```bash
cd ~/skill-repo && uv run pytest -q
```
Expected: all tests pass, 0 failures.

- [ ] **Step 2: doctor sanity check**

```bash
skill-sync doctor
```
Expected: `skill-sync doctor: all checks passed.`

- [ ] **Step 3: list smoke test**

```bash
skill-sync list
skill-sync list --scope user
```
Expected: 5 skills shown with symlink status.

- [ ] **Step 4: help smoke test for new commands**

```bash
skill-sync push --help
skill-sync install --help
skill-sync move --help
skill-sync list --help
```
Expected: each prints a help block with documented args.

- [ ] **Step 5: Push to remote**

```bash
cd ~/skill-repo && git push
```
Expected: remote updated with all Plan D commits.

---

## Self-Review

**Spec coverage:**
- `push` — covered (Task 2)
- `install` — covered (Task 3)
- `move --to user|project` — covered (Task 4)
- `.skills.toml` read/write/sha-pin — covered (Task 1 + Task 3)
- `list --scope user|project|all` — covered (Task 5)
- `doctor` sha-drift check — covered (Task 6)
- `sync` project reconciliation with pull/push/leave — covered (Task 7)
- Conflict resolution on `push` (three choices) — covered (Task 2)
- Drift detection prompt on `sync` (three choices) — covered (Task 7)
- Auto-detect `.skills.toml` in cwd for `doctor` and `sync` — covered (Tasks 6+7)
- SHA computed as SKILL.md SHA256[:12] — consistent across snapshot.py

**Gaps checked:** None found. YAGNI applied: `--scope all` for `list` is included (one extra elif branch, no extra logic). Semantic version pinning is explicitly out of scope per spec.

**Type consistency:** `skill_sha` returns `str`, used identically across `snapshot.py`, `install_cmd.py`, `push_cmd.py`, `list_cmd.py`, `doctor.py`, `sync_cmd.py`. `read_toml` / `write_toml` use `dict` with consistent `{"skill-repo": str, "skills": {name: {"sha": str, "installed": str}}}` shape throughout.
