# Skill Management — Plan B: Init, Symlinks, Migration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up `skill-sync init` and `skill-sync init --migrate` so that on a fresh machine `~/skill-repo/` becomes the single source of truth for user-level skills consumed by both Claude Code (`~/.claude/skills/`) and Codex CLI (`~/.codex/skills/`).

**Architecture:**
- **Per-skill symlinks** (not parent-directory symlinks). For each `~/skill-repo/skills/<name>/`, create `~/.claude/skills/<name>` and `~/.codex/skills/<name>` as symlinks. This preserves Codex's `~/.codex/skills/.system/` (auto-managed bundled skills) and any unrelated content in either dir.
- **Migration is one-shot import**: scan `~/.claude/skills/*.md` (flat legacy) + `~/.codex/skills/<name>/SKILL.md` (dir-per-skill) → normalize to canonical `dir-with-SKILL.md` → write into the repo's `skills/` → commit.
- **Conflict resolution is interactive by default**, with a `--yes` flag plus `--keep claude|codex|skip` for non-interactive runs and tests.
- **Project-scope skills (`content-creation/skills/*`) are out of scope.** The existing `.claude-plugin/marketplace.json` registration keeps working untouched. (See spec Open Questions §5.)

**Tech Stack:** Same as Plan A (Python 3.11, `uv`, `requests`, `markdownify`, `pytest`). No new dependencies.

**Reference spec:** `content-creation/docs/superpowers/specs/2026-05-12-skill-management-design.md`
**Reference plan (predecessor, completed):** `2026-05-12-skill-management-plan-a-bootstrap-knowledge.md`

---

## Design decisions locked in this plan (divergences from spec)

1. **Per-skill symlinks instead of parent-dir symlink.** Spec's `Architecture` shows `~/.codex/skills/ → ~/skill-repo/skills/` (whole-dir symlink). On this machine `~/.codex/skills/.system/` exists with `.codex-system-skills.marker` — it's auto-managed by the Codex CLI for bundled skills (`skill-creator`, `plan-skill`, etc.). Whole-dir symlink would hide it. **Decision: symlink each skill folder individually.** Same for `~/.claude/skills/`.

2. **Codex user path = `~/.codex/skills/` (resolves spec Open Question #3).** Official OpenAI doc (`KNOWLEDGE/developers-openai-com-codex-skills-30cff081.md`) says `$HOME/.agents/skills` for USER scope. Reality on this machine (Codex CLI 0.130.0): `~/.agents/` does not exist; Codex actively reads/writes `~/.codex/skills/`. The five existing user skills there are picked up by Codex today. **Decision: target `~/.codex/skills/`.** Task 7 includes a manual smoke-test to confirm Codex resolves a symlinked skill there. If a future Codex version requires `~/.agents/skills/` only, we extend `init` to write both symlinks; Plan B does not pre-emptively dual-write.

3. **Defer project-scope migration.** Spec Plan A also references `content-creation/skills/` (16 skills via plugin marketplace). Plan B does not touch them. Rationale: the marketplace works; importing into `~/skill-repo/` would duplicate without giving anything new until `skill-sync install --scope project` exists (Plan D). Re-evaluate when Plan D lands.

---

## File Structure (deltas from Plan A)

```
~/skill-repo/
├── bin/skill-sync                       # MODIFY (followup #1: capture ORIG_CWD)
├── src/skillsync/
│   ├── cli.py                           # MODIFY: drop unreachable return; add `init` subcommand
│   ├── knowledge.py                     # MODIFY (followup #3: hoist os/tempfile to module top)
│   ├── paths.py                         # MODIFY: add CLAUDE_USER_SKILLS_DIR, CODEX_USER_SKILLS_DIR
│   ├── migrate.py                       # CREATE: discover + normalize + conflict-resolve
│   └── init_cmd.py                      # CREATE: backup + per-skill symlink wiring
└── tests/
    ├── conftest.py                      # CREATE (followup #4: shared tmp fixtures)
    ├── test_cli_smoke.py                # CREATE (followup #5: --help smoke test)
    ├── test_migrate.py                  # CREATE
    └── test_init_cmd.py                 # CREATE
```

Live filesystem effects (Task 7 only, on this machine):

```
~/.claude/skills/                        # 4 flat *.md → backed up → replaced by 4 symlinks
~/.claude/skills/<name>/                 # → symlink → ~/skill-repo/skills/<name>/
~/.codex/skills/                         # 5 dirs → backed up → replaced by 5 symlinks
~/.codex/skills/<name>/                  # → symlink → ~/skill-repo/skills/<name>/
~/.codex/skills/.system/                 # UNTOUCHED
~/.claude/skills.bak.YYYY-MM-DD/         # backup of pre-migration state
~/.codex/skills.bak.YYYY-MM-DD/          # backup of pre-migration state
```

---

## Task 1: Plan A followups (5 small fixes, single commit)

**Files:**
- Modify: `~/skill-repo/bin/skill-sync`
- Modify: `~/skill-repo/src/skillsync/cli.py`
- Modify: `~/skill-repo/src/skillsync/knowledge.py`
- Create: `~/skill-repo/tests/conftest.py`
- Create: `~/skill-repo/tests/test_cli_smoke.py`

- [ ] **Step 1: Capture `ORIG_CWD` in `bin/skill-sync` before `cd`**

Read the current file first to know the exact content:

```bash
cat ~/skill-repo/bin/skill-sync
```

Then edit so the body becomes:

```bash
#!/usr/bin/env bash
# bin/skill-sync — entry point for skill-sync CLI
set -euo pipefail
export SKILL_SYNC_ORIG_CWD="$PWD"
REPO_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
cd "$REPO_DIR"
exec uv run python -m skillsync "$@"
```

(`readlink -f` is already there from the prior fix `22eeb0c`. The new line is `export SKILL_SYNC_ORIG_CWD="$PWD"` placed before `cd`.)

- [ ] **Step 2: Replace `parser.error` + unreachable `return 2` in `cli.py`**

Open `src/skillsync/cli.py`. The current tail of `main()` looks like:

```python
    parser.error(f"unknown command: {args.cmd}")
    return 2
```

Replace with:

```python
    raise AssertionError(f"unreachable: argparse should have rejected {args.cmd!r}")
```

Rationale: `add_subparsers(..., required=True)` already rejects unknown/missing subcommands at parse time, so this branch can never execute. Replacing with `AssertionError` makes the dead-code intent explicit and fails loudly if invariants ever break.

- [ ] **Step 3: Hoist `os, tempfile` imports to module top in `knowledge.py`**

Open `src/skillsync/knowledge.py`. Find any function-local `import os` / `import tempfile` (introduced by the atomic-write fix in commit `25aab82`) and move them to the module's import block at the top (alongside `hashlib`, `json`, etc.).

Final import block at the top should look like:

```python
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from markdownify import markdownify as md_convert

from skillsync.paths import KNOWLEDGE_DIR, URLS_FILE, LAST_SYNC_FILE
```

Remove the function-local imports.

- [ ] **Step 4: Create `tests/conftest.py` with shared fixture**

```python
"""Shared pytest fixtures for skillsync tests."""
from __future__ import annotations
import pytest

from skillsync import knowledge


@pytest.fixture
def tmp_knowledge_dir(tmp_path, monkeypatch):
    """Redirect knowledge module paths into a tmp dir."""
    urls_file = tmp_path / "_urls.txt"
    urls_file.write_text("https://example.com/docs/skills\n")
    last_sync = tmp_path / "_last-sync.json"
    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", tmp_path)
    monkeypatch.setattr(knowledge, "URLS_FILE", urls_file)
    monkeypatch.setattr(knowledge, "LAST_SYNC_FILE", last_sync)
    return tmp_path
```

Then open `tests/test_knowledge.py` and **delete** its now-redundant local `tmp_knowledge_dir` fixture (the `@pytest.fixture` block plus its function body). The tests reference the fixture by name, so they automatically pick up the conftest version.

- [ ] **Step 5: Create `tests/test_cli_smoke.py`**

```python
"""Smoke tests for the skill-sync CLI dispatcher."""
from __future__ import annotations
import subprocess
import sys


def test_cli_help_lists_subcommands():
    """`python -m skillsync --help` exits 0 and mentions every registered subcommand."""
    result = subprocess.run(
        [sys.executable, "-m", "skillsync", "--help"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout + result.stderr
    assert "knowledge" in out
```

- [ ] **Step 6: Run all tests**

```bash
cd ~/skill-repo
uv run pytest -v
```

Expected: all existing tests + the new `test_cli_help_lists_subcommands` pass. If any knowledge-test fails because the local fixture removal broke imports, restore the local fixture as a one-line `from tests.conftest import tmp_knowledge_dir` import or move the import order.

- [ ] **Step 7: Commit**

```bash
cd ~/skill-repo
git add bin/skill-sync src/skillsync/cli.py src/skillsync/knowledge.py tests/conftest.py tests/test_cli_smoke.py tests/test_knowledge.py
git commit -m "chore: Plan A followups (orig cwd, dead code, import hoist, shared fixtures, cli smoke)"
```

---

## Task 2: Path constants for user-level skill directories

**Files:**
- Modify: `~/skill-repo/src/skillsync/paths.py`

- [ ] **Step 1: Add constants**

Open `src/skillsync/paths.py` and append:

```python
HOME = Path.home()
CLAUDE_USER_SKILLS_DIR = HOME / ".claude" / "skills"
CODEX_USER_SKILLS_DIR = HOME / ".codex" / "skills"
```

The full file should now be:

```python
"""Filesystem path constants for skill-repo."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = REPO_ROOT / "KNOWLEDGE"
SKILLS_DIR = REPO_ROOT / "skills"
URLS_FILE = KNOWLEDGE_DIR / "_urls.txt"
LAST_SYNC_FILE = KNOWLEDGE_DIR / "_last-sync.json"

HOME = Path.home()
CLAUDE_USER_SKILLS_DIR = HOME / ".claude" / "skills"
CODEX_USER_SKILLS_DIR = HOME / ".codex" / "skills"
```

- [ ] **Step 2: Commit**

```bash
cd ~/skill-repo
git add src/skillsync/paths.py
git commit -m "feat(paths): add Claude/Codex user-level skill dir constants"
```

---

## Task 3: Migration discovery — failing tests

**Files:**
- Create: `~/skill-repo/tests/test_migrate.py`

- [ ] **Step 1: Write failing tests for `migrate.discover`**

```python
"""Tests for skillsync.migrate."""
from __future__ import annotations
from pathlib import Path

import pytest

from skillsync import migrate


@pytest.fixture
def tmp_dirs(tmp_path):
    """Build claude-flat / codex-dir / repo dirs under tmp_path."""
    claude = tmp_path / "claude_skills"
    codex = tmp_path / "codex_skills"
    repo = tmp_path / "repo_skills"
    claude.mkdir()
    codex.mkdir()
    repo.mkdir()
    return claude, codex, repo


def _write_flat(claude_dir: Path, name: str, body: str) -> None:
    (claude_dir / f"{name}.md").write_text(body)


def _write_dir(codex_dir: Path, name: str, body: str) -> None:
    d = codex_dir / name
    d.mkdir()
    (d / "SKILL.md").write_text(body)


def test_discover_finds_claude_flat_skills(tmp_dirs):
    claude, codex, _ = tmp_dirs
    _write_flat(claude, "alpha", "---\nname: alpha\ndescription: A\n---\nbody\n")
    _write_flat(claude, "beta", "---\nname: beta\ndescription: B\n---\n")
    found = migrate.discover(claude_dir=claude, codex_dir=codex)
    assert set(found.keys()) == {"alpha", "beta"}
    assert found["alpha"]["claude"] is not None
    assert found["alpha"]["codex"] is None
    assert "body" in found["alpha"]["claude"]["body"]


def test_discover_finds_codex_dir_skills(tmp_dirs):
    claude, codex, _ = tmp_dirs
    _write_dir(codex, "gamma", "---\nname: gamma\ndescription: G\n---\nbody\n")
    found = migrate.discover(claude_dir=claude, codex_dir=codex)
    assert set(found.keys()) == {"gamma"}
    assert found["gamma"]["claude"] is None
    assert found["gamma"]["codex"] is not None


def test_discover_skips_codex_system_dir(tmp_dirs):
    """`.system/` and any dotted-prefix dirs are bundled by Codex; never import."""
    claude, codex, _ = tmp_dirs
    sys_dir = codex / ".system"
    sys_dir.mkdir()
    (sys_dir / "skill-creator").mkdir()
    (sys_dir / "skill-creator" / "SKILL.md").write_text("system\n")
    _write_dir(codex, "delta", "---\nname: delta\ndescription: D\n---\n")
    found = migrate.discover(claude_dir=claude, codex_dir=codex)
    assert set(found.keys()) == {"delta"}


def test_discover_merges_overlapping_names(tmp_dirs):
    """A skill present in both claude and codex shows up once with both sources populated."""
    claude, codex, _ = tmp_dirs
    _write_flat(claude, "shared", "---\nname: shared\ndescription: from claude\n---\nclaude body\n")
    _write_dir(codex, "shared", "---\nname: shared\ndescription: from codex\n---\ncodex body\n")
    found = migrate.discover(claude_dir=claude, codex_dir=codex)
    assert set(found.keys()) == {"shared"}
    assert "claude body" in found["shared"]["claude"]["body"]
    assert "codex body" in found["shared"]["codex"]["body"]


def test_discover_ignores_non_md_in_claude_dir(tmp_dirs):
    claude, codex, _ = tmp_dirs
    (claude / "README.txt").write_text("not a skill")
    _write_flat(claude, "real", "---\nname: real\ndescription: R\n---\n")
    found = migrate.discover(claude_dir=claude, codex_dir=codex)
    assert set(found.keys()) == {"real"}
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd ~/skill-repo
uv run pytest tests/test_migrate.py -v
```

Expected: ImportError on `from skillsync import migrate`.

---

## Task 4: Migration discovery + format conversion implementation

**Files:**
- Create: `~/skill-repo/src/skillsync/migrate.py`

- [ ] **Step 1: Implement `migrate.discover` + helpers**

```python
"""Migration: import existing user-level skills into the repo."""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from skillsync.paths import (
    CLAUDE_USER_SKILLS_DIR,
    CODEX_USER_SKILLS_DIR,
    SKILLS_DIR,
)

# A discovered skill is keyed by name; each entry has optional "claude" and "codex" sources.
# Each source is {"path": Path, "body": str}.
Source = dict  # {"path": Path, "body": str}
Discovered = dict[str, dict[str, Optional[Source]]]


def discover(
    claude_dir: Path = CLAUDE_USER_SKILLS_DIR,
    codex_dir: Path = CODEX_USER_SKILLS_DIR,
) -> Discovered:
    """Walk both user-level dirs, return {name: {"claude": Source|None, "codex": Source|None}}."""
    found: Discovered = {}

    if claude_dir.is_dir():
        for entry in sorted(claude_dir.iterdir()):
            if entry.is_symlink():
                continue  # already linked — not a migration candidate
            if entry.is_file() and entry.suffix == ".md":
                name = entry.stem
                found.setdefault(name, {"claude": None, "codex": None})
                found[name]["claude"] = {"path": entry, "body": entry.read_text()}
            elif entry.is_dir():
                skill_md = entry / "SKILL.md"
                if skill_md.is_file():
                    name = entry.name
                    found.setdefault(name, {"claude": None, "codex": None})
                    found[name]["claude"] = {"path": skill_md, "body": skill_md.read_text()}

    if codex_dir.is_dir():
        for entry in sorted(codex_dir.iterdir()):
            if entry.name.startswith("."):
                continue  # .system/ etc. are bundled by Codex
            if entry.is_symlink():
                continue
            if entry.is_dir():
                skill_md = entry / "SKILL.md"
                if skill_md.is_file():
                    name = entry.name
                    found.setdefault(name, {"claude": None, "codex": None})
                    found[name]["codex"] = {"path": skill_md, "body": skill_md.read_text()}

    return found


def normalize_body(body: str) -> str:
    """Strip Claude-only frontmatter keys that Codex doesn't read (version, user-invocable).

    Returns the body unchanged if no such keys present. Used for equality comparison
    between claude and codex copies of the same skill.
    """
    lines = body.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != "---":
        return body
    # Find closing ---
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip() == "---":
            end = i
            break
    if end is None:
        return body
    fm = lines[1:end]
    skip = re.compile(r"^\s*(version|user-invocable)\s*:")
    fm_kept = [ln for ln in fm if not skip.match(ln)]
    return "".join([lines[0], *fm_kept, lines[end], *lines[end + 1 :]])
```

- [ ] **Step 2: Run discovery tests — expect pass**

```bash
cd ~/skill-repo
uv run pytest tests/test_migrate.py -v
```

Expected: 5 tests pass.

- [ ] **Step 3: Append failing tests for conflict resolution + import**

Add to `tests/test_migrate.py`:

```python
def test_resolve_chooses_codex_when_only_codex_present(tmp_dirs):
    claude, codex, _ = tmp_dirs
    _write_dir(codex, "x", "---\nname: x\ndescription: X\n---\nbody\n")
    found = migrate.discover(claude_dir=claude, codex_dir=codex)
    decisions = migrate.resolve(found, prompt_fn=lambda *_a, **_kw: "skip")
    assert decisions["x"]["chosen"] == "codex"


def test_resolve_chooses_claude_when_only_claude_present(tmp_dirs):
    claude, codex, _ = tmp_dirs
    _write_flat(claude, "y", "---\nname: y\ndescription: Y\n---\nbody\n")
    found = migrate.discover(claude_dir=claude, codex_dir=codex)
    decisions = migrate.resolve(found, prompt_fn=lambda *_a, **_kw: "skip")
    assert decisions["y"]["chosen"] == "claude"


def test_resolve_auto_picks_when_normalized_bodies_match(tmp_dirs):
    """If claude body normalizes to the same content as codex body, no prompt."""
    claude, codex, _ = tmp_dirs
    claude_body = "---\nname: z\ndescription: Z\nversion: 1\nuser-invocable: true\n---\nshared\n"
    codex_body = "---\nname: z\ndescription: Z\n---\nshared\n"
    _write_flat(claude, "z", claude_body)
    _write_dir(codex, "z", codex_body)
    found = migrate.discover(claude_dir=claude, codex_dir=codex)

    called = []
    def prompt_fn(*a, **kw):
        called.append((a, kw))
        return "claude"

    decisions = migrate.resolve(found, prompt_fn=prompt_fn)
    assert decisions["z"]["chosen"] == "codex"  # canonical format wins on tie
    assert called == []  # no prompt fired


def test_resolve_prompts_on_real_conflict_and_honours_keep_claude(tmp_dirs):
    claude, codex, _ = tmp_dirs
    _write_flat(claude, "w", "---\nname: w\ndescription: W\n---\nfrom claude\n")
    _write_dir(codex, "w", "---\nname: w\ndescription: W different\n---\nfrom codex\n")
    found = migrate.discover(claude_dir=claude, codex_dir=codex)
    decisions = migrate.resolve(found, prompt_fn=lambda *_a, **_kw: "claude")
    assert decisions["w"]["chosen"] == "claude"


def test_apply_writes_canonical_dir_with_skill_md(tmp_dirs):
    claude, codex, repo = tmp_dirs
    _write_flat(claude, "alpha", "---\nname: alpha\ndescription: A\n---\nbody A\n")
    _write_dir(codex, "beta", "---\nname: beta\ndescription: B\n---\nbody B\n")
    found = migrate.discover(claude_dir=claude, codex_dir=codex)
    decisions = migrate.resolve(found, prompt_fn=lambda *_a, **_kw: "skip")
    written = migrate.apply(decisions, repo_skills_dir=repo)
    assert sorted(written) == ["alpha", "beta"]
    assert (repo / "alpha" / "SKILL.md").read_text() == "---\nname: alpha\ndescription: A\n---\nbody A\n"
    assert (repo / "beta" / "SKILL.md").read_text() == "---\nname: beta\ndescription: B\n---\nbody B\n"


def test_apply_skips_decisions_marked_skip(tmp_dirs):
    claude, codex, repo = tmp_dirs
    _write_flat(claude, "a", "---\nname: a\ndescription: A\n---\n")
    _write_dir(codex, "b", "---\nname: b\ndescription: B\n---\n")
    found = migrate.discover(claude_dir=claude, codex_dir=codex)
    decisions = migrate.resolve(found, prompt_fn=lambda *_a, **_kw: "skip")
    decisions["a"]["chosen"] = "skip"  # operator overrode
    written = migrate.apply(decisions, repo_skills_dir=repo)
    assert written == ["b"]
    assert not (repo / "a").exists()
```

- [ ] **Step 4: Run — expect failures (resolve/apply not implemented)**

```bash
cd ~/skill-repo
uv run pytest tests/test_migrate.py -v
```

Expected: previous 5 pass; 6 new fail with `AttributeError: module 'skillsync.migrate' has no attribute 'resolve'`.

- [ ] **Step 5: Implement `resolve` and `apply` in `migrate.py`**

Append to `src/skillsync/migrate.py`:

```python
PromptFn = Callable[[str, str, str], str]
"""prompt_fn(name, claude_body, codex_body) -> 'claude' | 'codex' | 'skip'"""


def resolve(
    discovered: Discovered,
    prompt_fn: PromptFn,
    default_keep: str = "codex",
) -> dict[str, dict]:
    """Decide canonical source for each skill. Returns {name: {chosen, source}}."""
    decisions: dict[str, dict] = {}
    for name, sources in sorted(discovered.items()):
        claude = sources.get("claude")
        codex = sources.get("codex")

        if claude and not codex:
            decisions[name] = {"chosen": "claude", "source": claude}
            continue
        if codex and not claude:
            decisions[name] = {"chosen": "codex", "source": codex}
            continue
        if not claude and not codex:
            continue  # nothing to import

        # Both present — compare normalized bodies.
        if normalize_body(claude["body"]) == normalize_body(codex["body"]):
            # Equivalent content; codex format is canonical (dir/SKILL.md), pick it.
            decisions[name] = {"chosen": "codex", "source": codex}
            continue

        # Real conflict — prompt operator.
        choice = prompt_fn(name, claude["body"], codex["body"])
        if choice not in ("claude", "codex", "skip"):
            choice = default_keep
        if choice == "skip":
            decisions[name] = {"chosen": "skip", "source": None}
        elif choice == "claude":
            decisions[name] = {"chosen": "claude", "source": claude}
        else:
            decisions[name] = {"chosen": "codex", "source": codex}
    return decisions


def apply(decisions: dict[str, dict], repo_skills_dir: Path = SKILLS_DIR) -> list[str]:
    """Write each decided skill into repo_skills_dir as <name>/SKILL.md. Returns names written."""
    repo_skills_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name, decision in sorted(decisions.items()):
        if decision["chosen"] == "skip" or decision["source"] is None:
            continue
        target_dir = repo_skills_dir / name
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "SKILL.md").write_text(decision["source"]["body"])
        written.append(name)
    return written


@dataclass
class BackupResult:
    """Where a directory's pre-migration contents were moved to."""
    original: Path
    backup: Path


def backup_dir(target: Path, today: Optional[date] = None) -> Optional[BackupResult]:
    """Move `target` to `target.parent/<name>.bak.YYYY-MM-DD/` and recreate empty target.

    Returns None if `target` does not exist or is empty. Raises if a backup with the same
    date already exists (operator must clean up before re-running).
    """
    if not target.exists() or not any(target.iterdir()):
        return None
    today = today or date.today()
    backup_path = target.parent / f"{target.name}.bak.{today.isoformat()}"
    if backup_path.exists():
        raise FileExistsError(f"backup already exists: {backup_path} — remove it before retrying")
    shutil.move(str(target), str(backup_path))
    target.mkdir(parents=True)
    return BackupResult(original=target, backup=backup_path)
```

- [ ] **Step 6: Run — expect all 11 pass**

```bash
cd ~/skill-repo
uv run pytest tests/test_migrate.py -v
```

Expected: 11 passed.

- [ ] **Step 7: Commit**

```bash
cd ~/skill-repo
git add src/skillsync/migrate.py tests/test_migrate.py
git commit -m "feat(migrate): discover, resolve conflicts, apply to repo skills/"
```

---

## Task 5: Symlink wiring — tests then implementation

**Files:**
- Create: `~/skill-repo/tests/test_init_cmd.py`
- Create: `~/skill-repo/src/skillsync/init_cmd.py`

- [ ] **Step 1: Write failing tests for `init_cmd.wire_symlinks`**

```python
"""Tests for skillsync.init_cmd."""
from __future__ import annotations
from pathlib import Path

import pytest

from skillsync import init_cmd


@pytest.fixture
def repo_with_two_skills(tmp_path):
    repo_skills = tmp_path / "repo_skills"
    repo_skills.mkdir()
    for name in ("alpha", "beta"):
        d = repo_skills / name
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n")
    return repo_skills


def test_wire_symlinks_creates_per_skill_symlinks(repo_with_two_skills, tmp_path):
    target = tmp_path / "claude_skills"
    target.mkdir()
    created = init_cmd.wire_symlinks(repo_skills_dir=repo_with_two_skills, target_dir=target)
    assert sorted(created) == ["alpha", "beta"]
    assert (target / "alpha").is_symlink()
    assert (target / "alpha").resolve() == (repo_with_two_skills / "alpha").resolve()
    assert (target / "beta").is_symlink()


def test_wire_symlinks_creates_target_dir_if_missing(repo_with_two_skills, tmp_path):
    target = tmp_path / "missing_dir" / "skills"
    init_cmd.wire_symlinks(repo_skills_dir=repo_with_two_skills, target_dir=target)
    assert target.is_dir()
    assert (target / "alpha").is_symlink()


def test_wire_symlinks_preserves_unrelated_dirs(repo_with_two_skills, tmp_path):
    """E.g. ~/.codex/skills/.system/ must not be touched."""
    target = tmp_path / "codex_skills"
    target.mkdir()
    system = target / ".system"
    system.mkdir()
    (system / "marker").write_text("bundled")
    init_cmd.wire_symlinks(repo_skills_dir=repo_with_two_skills, target_dir=target)
    assert (system / "marker").read_text() == "bundled"
    assert not (target / ".system").is_symlink()


def test_wire_symlinks_refuses_to_clobber_real_dir(repo_with_two_skills, tmp_path):
    target = tmp_path / "claude_skills"
    target.mkdir()
    real = target / "alpha"
    real.mkdir()
    (real / "SKILL.md").write_text("local\n")
    with pytest.raises(FileExistsError):
        init_cmd.wire_symlinks(repo_skills_dir=repo_with_two_skills, target_dir=target)


def test_wire_symlinks_replaces_existing_symlink_pointing_elsewhere(repo_with_two_skills, tmp_path):
    target = tmp_path / "claude_skills"
    target.mkdir()
    bogus = tmp_path / "bogus"
    bogus.mkdir()
    (target / "alpha").symlink_to(bogus, target_is_directory=True)
    init_cmd.wire_symlinks(repo_skills_dir=repo_with_two_skills, target_dir=target)
    assert (target / "alpha").is_symlink()
    assert (target / "alpha").resolve() == (repo_with_two_skills / "alpha").resolve()


def test_wire_symlinks_idempotent(repo_with_two_skills, tmp_path):
    target = tmp_path / "claude_skills"
    target.mkdir()
    init_cmd.wire_symlinks(repo_skills_dir=repo_with_two_skills, target_dir=target)
    # Second call should be a no-op (no errors, same final state).
    init_cmd.wire_symlinks(repo_skills_dir=repo_with_two_skills, target_dir=target)
    assert (target / "alpha").is_symlink()
    assert (target / "beta").is_symlink()
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd ~/skill-repo
uv run pytest tests/test_init_cmd.py -v
```

Expected: ImportError on `from skillsync import init_cmd`.

- [ ] **Step 3: Implement `init_cmd.py`**

```python
"""skill-sync init: backup existing user-level skill dirs and symlink each repo skill."""
from __future__ import annotations

from pathlib import Path

from skillsync.paths import (
    CLAUDE_USER_SKILLS_DIR,
    CODEX_USER_SKILLS_DIR,
    SKILLS_DIR,
)


def wire_symlinks(
    repo_skills_dir: Path = SKILLS_DIR,
    target_dir: Path = CLAUDE_USER_SKILLS_DIR,
) -> list[str]:
    """For each subdir in repo_skills_dir, ensure target_dir/<name> is a symlink to it.

    - Creates target_dir if missing.
    - If target_dir/<name> is already a symlink, replaces it (silently).
    - If target_dir/<name> is a real file or dir, raises FileExistsError. The operator
      must back it up first via `init --migrate` (which calls `migrate.backup_dir`).
    - Items in target_dir not present in repo_skills_dir (e.g. `.system/`) are left alone.

    Returns the list of names symlinked.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    linked: list[str] = []
    for entry in sorted(repo_skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        link = target_dir / entry.name
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            raise FileExistsError(
                f"{link} already exists and is not a symlink. "
                f"Run `skill-sync init --migrate` first to back up and import."
            )
        link.symlink_to(entry.resolve(), target_is_directory=True)
        linked.append(entry.name)
    return linked
```

- [ ] **Step 4: Run — expect all 6 pass**

```bash
cd ~/skill-repo
uv run pytest tests/test_init_cmd.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/skill-repo
git add src/skillsync/init_cmd.py tests/test_init_cmd.py
git commit -m "feat(init): per-skill symlink wiring (preserves .system/ and other content)"
```

---

## Task 6: Wire `init` and `init --migrate` into the CLI

**Files:**
- Modify: `~/skill-repo/src/skillsync/cli.py`
- Modify: `~/skill-repo/src/skillsync/init_cmd.py` (add `run` orchestrator)
- Modify: `~/skill-repo/tests/test_cli_smoke.py` (assert `init` listed)

- [ ] **Step 1: Add `run()` orchestrator to `init_cmd.py`**

First, expand the import block at the top of `src/skillsync/init_cmd.py` so it reads:

```python
"""skill-sync init: backup existing user-level skill dirs and symlink each repo skill."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from skillsync import migrate
from skillsync.paths import (
    CLAUDE_USER_SKILLS_DIR,
    CODEX_USER_SKILLS_DIR,
    SKILLS_DIR,
)
```

Then **append** (after the existing `wire_symlinks` function) the orchestrator and prompt helpers:

```python
DEFAULT_PROMPT_TEMPLATE = """\
Conflict on skill '{name}':
  --- claude version ---
{claude_body}
  --- codex version ---
{codex_body}
Choose [claude / codex / skip]: """


def _interactive_prompt(name: str, claude_body: str, codex_body: str) -> str:
    msg = DEFAULT_PROMPT_TEMPLATE.format(
        name=name,
        claude_body=claude_body.strip()[:400] + ("…" if len(claude_body) > 400 else ""),
        codex_body=codex_body.strip()[:400] + ("…" if len(codex_body) > 400 else ""),
    )
    answer = input(msg).strip().lower()
    if answer not in ("claude", "codex", "skip"):
        return "codex"  # default canonical
    return answer


def _autopilot_prompt(default: str) -> Callable[[str, str, str], str]:
    def _fn(name: str, _c: str, _x: str) -> str:
        print(f"  conflict on '{name}' — auto-resolving as '{default}'", file=sys.stderr)
        return default
    return _fn


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
        print("Discovering existing user-level skills…", flush=True)
        found = migrate.discover(claude_dir=claude_dir, codex_dir=codex_dir)
        if not found:
            print("  (none found — proceeding with symlink wiring only)", flush=True)
        else:
            print(f"  found {len(found)} skill name(s): {', '.join(sorted(found))}", flush=True)

            if yes:
                prompt_fn = _autopilot_prompt(keep or "codex")
            else:
                prompt_fn = _interactive_prompt

            decisions = migrate.resolve(found, prompt_fn=prompt_fn)

            print("Backing up existing user-level skill dirs…", flush=True)
            for d in (claude_dir, codex_dir):
                result = migrate.backup_dir(d)
                if result:
                    print(f"  {d} → {result.backup}", flush=True)

            print("Importing into ~/skill-repo/skills/…", flush=True)
            written = migrate.apply(decisions, repo_skills_dir=repo_skills_dir)
            print(f"  wrote {len(written)} skill(s): {', '.join(written)}", flush=True)

            print("Committing imported skills…", flush=True)
            try:
                subprocess.run(
                    ["git", "-C", str(repo_skills_dir.parent), "add", "skills/"],
                    check=True,
                )
                subprocess.run(
                    ["git", "-C", str(repo_skills_dir.parent), "commit", "-m",
                     f"feat(skills): import {len(written)} user-level skills via init --migrate"],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                print(f"  (git commit skipped: {e})", file=sys.stderr)

    print("Wiring per-skill symlinks…", flush=True)
    for d in (claude_dir, codex_dir):
        linked = wire_symlinks(repo_skills_dir=repo_skills_dir, target_dir=d)
        print(f"  {d}: {len(linked)} link(s)", flush=True)

    print("Done.", flush=True)
    return 0
```

- [ ] **Step 2: Add `init` subcommand to `cli.py`**

Open `src/skillsync/cli.py`. After the `p_knowledge` subparser block, add:

```python
    p_init = sub.add_parser("init", help="Wire user-level symlinks; optionally migrate existing skills")
    p_init.add_argument("--migrate", action="store_true",
                        help="Import existing skills from ~/.claude/skills/ and ~/.codex/skills/ first")
    p_init.add_argument("--yes", action="store_true",
                        help="Non-interactive; resolve conflicts via --keep (default: codex)")
    p_init.add_argument("--keep", choices=["claude", "codex"], default=None,
                        help="With --yes: which side wins on conflict")
```

In the dispatch block (currently `if args.cmd == "knowledge":`), add:

```python
    if args.cmd == "init":
        from skillsync.init_cmd import run as init_run
        return init_run(migrate_flag=args.migrate, yes=args.yes, keep=args.keep)
```

- [ ] **Step 3: Update CLI smoke test to check both subcommands listed**

Open `tests/test_cli_smoke.py` and replace the assertion line:

```python
    assert "knowledge" in out
    assert "init" in out
```

- [ ] **Step 4: Run all tests**

```bash
cd ~/skill-repo
uv run pytest -v
```

Expected: every test passes (knowledge, migrate, init_cmd, cli smoke).

- [ ] **Step 5: Verify CLI from PATH**

```bash
cd /tmp
skill-sync --help
skill-sync init --help
```

Expected: `init` listed in main help; `init --help` shows `--migrate`, `--yes`, `--keep` flags.

- [ ] **Step 6: Commit**

```bash
cd ~/skill-repo
git add src/skillsync/init_cmd.py src/skillsync/cli.py tests/test_cli_smoke.py
git commit -m "feat(cli): add `skill-sync init` and `init --migrate`"
```

---

## Task 7: Live migration on this machine (one-time, irreversible without backup)

**This task touches the operator's actual `~/.claude/skills/` and `~/.codex/skills/`. Do not auto-run; perform with the operator watching. Backups are written first.**

**Files:** none new — exercising the existing CLI.

- [ ] **Step 1: Snapshot current state**

```bash
ls -la ~/.claude/skills/ ~/.codex/skills/
```

Expected (today, 2026-05-12):
- `~/.claude/skills/` — 4 flat `.md` files (`checkpoint-commit.md`, `generate-image.md`, `generate-video.md`, `workflow-scout.md`)
- `~/.codex/skills/` — 5 dirs (above 4 + `video-intent-authoring`) plus `.system/` plus `.codex-system-skills.marker`

If state has drifted from this snapshot, pause and reconcile before proceeding.

- [ ] **Step 2: Confirm no name collides with content-creation plugin skills**

```bash
ls /home/tim-huang/content-creation/skills/
```

Note any names that overlap with the ~/.claude or ~/.codex names. They will continue to be served from the project plugin marketplace and are not affected by this migration. Just record any overlaps for the wrap-up note.

- [ ] **Step 3: Dry-run discovery**

```bash
cd ~/skill-repo
uv run python -c "from skillsync import migrate; import json; print(json.dumps({k: {'has_claude': v['claude'] is not None, 'has_codex': v['codex'] is not None} for k, v in migrate.discover().items()}, indent=2))"
```

Expected output: 5 unique names, four with `has_claude=True` and `has_codex=True`, one (`video-intent-authoring`) with only `has_codex=True`.

- [ ] **Step 4: Run interactive migration**

```bash
skill-sync init --migrate
```

Expected interaction:
- Prints discovered skill list (5 names).
- For each name where claude+codex bodies differ after normalization, shows a diff snippet and prompts `[claude / codex / skip]`. Operator chooses; default canonical is `codex`.
- Backs up `~/.claude/skills/` → `~/.claude/skills.bak.2026-05-12/`.
- Backs up `~/.codex/skills/` → `~/.codex/skills.bak.2026-05-12/` (this preserves `.system/` inside the backup, which is fine — Codex re-creates `.system/` on next launch).
- Writes 5 SKILL.md files into `~/skill-repo/skills/`.
- Auto-commits the import.
- Wires 5 symlinks in `~/.claude/skills/` and 5 in `~/.codex/skills/`.

If `.system/` ends up inside the backup (not the new live dir), Step 5 below will recreate it; if Codex is unhappy, manually move it back: `mv ~/.codex/skills.bak.2026-05-12/.system ~/.codex/skills/.system`.

- [ ] **Step 5: Restore Codex `.system/` if needed**

```bash
ls ~/.codex/skills/.system/ 2>/dev/null || mv ~/.codex/skills.bak.2026-05-12/.system ~/.codex/skills/.system
ls ~/.codex/skills/.system/
```

Expected: `.system/` exists in the live dir with the same contents as before migration (or empty — Codex CLI will repopulate on next launch).

- [ ] **Step 6: Verify symlinks resolve**

```bash
ls -la ~/.claude/skills/ | grep -E "checkpoint|generate|workflow|video-intent"
ls -la ~/.codex/skills/ | grep -E "checkpoint|generate|workflow|video-intent"
readlink ~/.claude/skills/checkpoint-commit
readlink ~/.codex/skills/checkpoint-commit
```

Expected: each entry shows as a symlink (`l...`) pointing into `~/skill-repo/skills/<name>`.

- [ ] **Step 7: Verify Claude Code picks up the symlinked skill**

In a fresh Claude Code session (not this one, since live-change-detection only watches dirs that existed at session start for top-level), open the `/skills` listing or invoke `/checkpoint-commit` and confirm it loads.

If it does not, there is a Claude Code bug or symlink-resolution issue; report and roll back via Step 11 below.

- [ ] **Step 8: Verify Codex CLI picks up the symlinked skill**

```bash
codex --print-skills 2>&1 | grep -i checkpoint || echo "skill not visible to codex"
```

(If `codex` does not have a `--print-skills` flag in 0.130.0, fall back to launching `codex`, asking it "list your skills" or "do you have a checkpoint-commit skill?", and observing the response. The official spec page says Codex prints the skill list on startup at debug level — `RUST_LOG=debug codex 2>&1 | head -100` may help.)

If the symlinked skill is not visible to Codex, this confirms the spec's open question that Codex 0.130.0 may require `~/.agents/skills/` instead. Treat as a Plan B blocker:
- Halt and ask the operator for direction.
- Possible follow-up: extend `init_cmd.wire_symlinks` to also write into `~/.agents/skills/` and re-run.

- [ ] **Step 9: Run skill-repo tests one more time**

```bash
cd ~/skill-repo
uv run pytest -v
```

Expected: all green.

- [ ] **Step 10: Push the imported-skills commit**

```bash
cd ~/skill-repo
git log --oneline | head -10
```

(No push yet; remote setup is Task 8.)

- [ ] **Step 11: Rollback procedure (only if Step 7 or 8 failed)**

```bash
# Remove the broken symlinks, restore the backups, leave the repo skills/ in place for re-attempt later.
rm -rf ~/.claude/skills
mv ~/.claude/skills.bak.2026-05-12 ~/.claude/skills
rm -rf ~/.codex/skills
mv ~/.codex/skills.bak.2026-05-12 ~/.codex/skills
```

Then halt Plan B and report the failure mode for redesign.

---

## Task 8: Wrap-up — remote push, spec update, summary

**Files:**
- Modify: `~/skill-repo/docs/design-spec.md` (resolve Open Question #3)
- Modify: `/home/tim-huang/content-creation/docs/superpowers/specs/2026-05-12-skill-management-design.md` (mirror the resolution)

- [ ] **Step 1: Update the spec's Open Questions section**

Open both copies of the spec (`~/skill-repo/docs/design-spec.md` and the canonical copy in `content-creation/docs/superpowers/specs/`). Replace the bullet:

```markdown
- **Path verification.** Doc-fetcher reported Codex user-level path as `~/.agents/skills/`, but installed Codex on this machine uses `~/.codex/skills/`. Confirm during implementation; spec assumes `~/.codex/skills/` until disproven.
```

with:

```markdown
- **Path verification (resolved 2026-05-12).** Codex CLI 0.130.0 on Tim's machine reads from `~/.codex/skills/` (the official OpenAI doc cites `$HOME/.agents/skills` but `~/.agents/` does not exist on disk). Plan B verified that symlinks at `~/.codex/skills/<name>` are picked up by Codex. Implementation targets `~/.codex/skills/`. If a future Codex version drops support for that path, extend `init_cmd.wire_symlinks` to also write into `~/.agents/skills/`.
```

Also update the **Architecture** section's symlink diagram:

```markdown
~/.claude/skills/<name>  →  symlink to  ~/skill-repo/skills/<name>   # per-skill, not parent-dir
~/.codex/skills/<name>   →  symlink to  ~/skill-repo/skills/<name>   # per-skill; preserves .system/
```

Add a one-line note after the diagram:

```markdown
> Per-skill (not parent-dir) symlinks — preserves Codex's `.system/` bundled-skills dir.
```

- [ ] **Step 2: Optionally add GitHub remote (deferred from Plan A Task 7 step 4)**

If a private GitHub repo `tim-huang/skill-repo` exists:

```bash
cd ~/skill-repo
git remote add origin git@github.com:tim-huang/skill-repo.git
git push -u origin main
```

If no remote yet, document this as still-deferred and skip.

- [ ] **Step 3: Commit the spec update**

```bash
cd /home/tim-huang/content-creation
git add docs/superpowers/specs/2026-05-12-skill-management-design.md
git commit -m "docs(spec): resolve Open Question #3 (codex path) + per-skill symlinks"
```

```bash
cd ~/skill-repo
git add docs/design-spec.md
git commit -m "docs: mirror spec update — codex path resolved, per-skill symlinks"
```

- [ ] **Step 4: Final summary report**

Report to operator (one paragraph + numbers):
- Number of skills imported into `~/skill-repo/skills/` (expected: 5).
- Number of conflicts resolved interactively + which side won for each.
- Whether Step 7 (Claude Code) and Step 8 (Codex CLI) verifications succeeded.
- Whether GitHub remote was added.
- Open follow-ups for Plan C (sync, doctor, search, list).

---

## Self-review checklist

**Spec coverage (Plan B scope only):**
- ✅ `skill-sync init` (per-skill symlinks; preserves `.system/`)
- ✅ `skill-sync init --migrate` (discover → resolve → backup → apply → wire)
- ✅ Interactive conflict resolution + `--yes` / `--keep` flags
- ✅ Backup directories with date suffix (rollback path documented)
- ✅ Codex path open-question resolved with smoke test
- ✅ Plan A followups #1–5 folded into Task 1
- ⏭️ `sync` / `doctor` / `search` / `list` — Plan C
- ⏭️ `push` / `install` / `move` / `.skills.toml` flow — Plan D
- ⏭️ SessionStart hook + project onboarding — Plan E
- ⏭️ Plan A followups #6 (knowledge.py preprocessing) and #7 (split fetch_one) — deferred (low value until knowledge re-fetches start producing real noise)
- ⏭️ Project-skill migration from `content-creation/skills/` — deferred until Plan D's `install --scope project` exists

**Placeholders:** none. Every step has concrete commands and code.

**Type consistency:**
- `migrate.discover` → `Discovered` (`dict[str, dict[str, Optional[Source]]]`)
- `migrate.resolve(discovered, prompt_fn, default_keep)` → `dict[str, dict]` with keys `chosen` (`'claude' | 'codex' | 'skip'`) and `source` (`Source | None`)
- `migrate.apply(decisions, repo_skills_dir)` → `list[str]` (names written)
- `migrate.backup_dir(target, today)` → `Optional[BackupResult]`
- `init_cmd.wire_symlinks(repo_skills_dir, target_dir)` → `list[str]` (names linked)
- `init_cmd.run(migrate_flag, yes, keep, ...)` → `int` (exit code)

Names used identically in `migrate.py`, `init_cmd.py`, `cli.py`, and the test suite.

**Known risks:**
1. **Codex symlink resolution unproven on 0.130.0.** Mitigated by Step 7/8 smoke tests + Step 11 rollback. If it fails, Plan B halts cleanly with backups intact.
2. **Backup-dir name collision.** `migrate.backup_dir` raises if `<dir>.bak.<today>` already exists. Operator must clean up before re-running on the same day.
3. **`~/.codex/skills/.system/` lands in the backup.** Step 5 explicitly handles this — Codex CLI re-creates `.system/` on next launch in any case.
4. **Frontmatter normalization is conservative.** Only `version` and `user-invocable` keys are stripped for equality comparison. Any other Claude-only key (`when_to_use`, `allowed-tools`, `context: fork`, `agent`) will count as a conflict and trigger a prompt — which is the correct behaviour (operator should look at it).

---

## Execution next steps

After Plan B completes:
- Plan C: `skill-sync sync` + `doctor` + `search` + `list` (generates `index.json`).
- Plan D: `skill-sync push` + `install` + `move`; introduces project-scope `.skills.toml` flow.
- Plan E: SessionStart hook + project onboarding via `CLAUDE.md`/`AGENTS.md` `skill-repo:` declaration.

Reconsider Plan A followups #6 and #7 once `skill-sync sync` lands and we observe whether the knowledge.md noise is actually a problem in practice.
