# Shared Agent Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `memory-sync` CLI that gives Claude and Codex a shared `.agent-memory/` per-project memory store, with session-end hooks and weekly maintenance cron.

**Architecture:** `~/.claude/bin/memory_sync.py` is a standalone Python library + CLI. A one-time `memory-sync init` migrates Claude's existing memory and creates a symlink so Claude writes natively. Codex reads the shared index via an AGENTS.md Session Startup instruction; a Stop hook runs `extract-codex` to distil Codex rollout summaries into normalized topic files via Claude Haiku. A weekly cron script enforces the 35-entry cap and runs an intelligent audit.

**Tech Stack:** Python 3.12 stdlib + `yaml` (pyyaml, system-available), `subprocess` for `claude` CLI calls, `json` for timestamp state; cron for scheduling.

**Spec:** `docs/superpowers/specs/2026-05-13-shared-agent-memory-design.md`

---

## File Map

| Action | Path | Purpose |
|---|---|---|
| Create | `~/.claude/bin/memory_sync.py` | Core library + CLI (importable for tests) |
| Create (symlink) | `~/.claude/bin/memory-sync` | Executable entry point → `memory_sync.py` |
| Create | `~/.claude/hooks/memory-sync-session-end.py` | Claude SessionEnd hook (background spawn) |
| Create | `~/.local/bin/memory-weekly-maintenance.sh` | Weekly cron wrapper |
| Create | `tests/unit/test_memory_sync.py` | Pytest tests (uses project venv) |
| Modify | `~/.claude/settings.json` | Add SessionEnd hook entry |
| Modify | `~/.codex/hooks.json` | Add Stop hook entry |
| Modify | `AGENTS.md` | Add Session Startup read instruction |
| Created at runtime | `<project>/.agent-memory/` | Shared memory directory tree |
| Created at runtime | `~/.claude/projects/-home-tim-huang-content-creation/memory` | Replaced with symlink → `.agent-memory/` |

---

## Task 1: Core library skeleton + `doctor` (read-only)

**Files:**
- Create: `~/.claude/bin/memory_sync.py`
- Create (symlink): `~/.claude/bin/memory-sync`
- Test: `tests/unit/test_memory_sync.py`

- [ ] **Step 1: Write failing tests for `load_index` and `check_doctor`**

```python
# tests/unit/test_memory_sync.py
import sys, os
sys.path.insert(0, os.path.expanduser("~/.claude/bin"))
import memory_sync as ms

import pytest
from pathlib import Path


def make_agent_memory(tmp_path: Path, index_lines: list[str], topic_files: dict[str, str] = None) -> Path:
    am = tmp_path / ".agent-memory"
    am.mkdir()
    (am / "MEMORY.md").write_text("\n".join(index_lines) + "\n")
    if topic_files:
        for rel_path, content in topic_files.items():
            p = am / rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
    return am


VALID_FRONTMATTER = """\
---
id: test-entry
name: Test entry
description: A test memory entry
type: feedback
source_agents: [claude]
updated: 2026-01-01
---

Rule text.

**Why:** reason

**How to apply:** when applicable
"""


def test_load_index_counts_live_entries(tmp_path):
    lines = [
        "# Memory Index",
        "- [feedback/a.md](feedback/a.md) — entry one",
        "- [feedback/b.md](feedback/b.md) — entry two",
    ]
    am = make_agent_memory(tmp_path, lines)
    idx = ms.load_index(am)
    assert len(idx.entries) == 2
    assert idx.entries[0].path == "feedback/a.md"
    assert idx.entries[0].description == "entry one"


def test_load_index_ignores_archive_pointers(tmp_path):
    lines = [
        "# Memory Index",
        "- [feedback/a.md](feedback/a.md) — entry one",
        "- (archive) [archive/2025/](archive/2025/) — 3 entries archived 2025",
    ]
    am = make_agent_memory(tmp_path, lines)
    idx = ms.load_index(am)
    assert len(idx.live_entries) == 1


def test_parse_frontmatter_extracts_fields():
    fm = ms.parse_frontmatter(VALID_FRONTMATTER)
    assert fm["id"] == "test-entry"
    assert fm["type"] == "feedback"
    assert fm["updated"] == "2026-01-01"


def test_check_doctor_passes_clean_index(tmp_path):
    lines = ["# Memory Index"] + [
        f"- [feedback/e{i}.md](feedback/e{i}.md) — entry {i}"
        for i in range(10)
    ]
    topic = {f"feedback/e{i}.md": VALID_FRONTMATTER for i in range(10)}
    am = make_agent_memory(tmp_path, lines, topic)
    violations = ms.check_doctor(am, ms.Config())
    assert violations == []


def test_check_doctor_flags_line_count(tmp_path):
    lines = ["# Memory Index"] + [
        f"- [feedback/e{i}.md](feedback/e{i}.md) — entry {i}"
        for i in range(36)
    ]
    topic = {f"feedback/e{i}.md": VALID_FRONTMATTER for i in range(36)}
    am = make_agent_memory(tmp_path, lines, topic)
    violations = ms.check_doctor(am, ms.Config())
    assert any("live entries" in v for v in violations)


def test_check_doctor_flags_missing_frontmatter(tmp_path):
    lines = [
        "# Memory Index",
        "- [feedback/a.md](feedback/a.md) — entry one",
    ]
    am = make_agent_memory(tmp_path, lines, {"feedback/a.md": "# No frontmatter\n\nsome text\n"})
    violations = ms.check_doctor(am, ms.Config())
    assert any("frontmatter" in v for v in violations)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_memory_sync.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'memory_sync'`

- [ ] **Step 3: Create `~/.claude/bin/memory_sync.py`**

```python
#!/usr/bin/env python3
"""memory-sync: shared Claude+Codex agent memory CLI."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None  # config.yml optional; defaults used


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MemoryEntry:
    path: str          # relative to .agent-memory/
    description: str   # ≤12 words from index line
    is_archive: bool = False


@dataclass
class MemoryIndex:
    entries: list[MemoryEntry] = field(default_factory=list)
    raw_lines: list[str] = field(default_factory=list)

    @property
    def live_entries(self) -> list[MemoryEntry]:
        return [e for e in self.entries if not e.is_archive]


@dataclass
class Config:
    max_lines: int = 80
    max_live_entries: int = 35
    archive_destination: str = "archive/{YYYY}"
    normalization_model: str = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

_ENTRY_RE = re.compile(r"^- \[([^\]]+)\]\([^\)]+\)\s+[—–-]\s+(.+)$")
_ARCHIVE_RE = re.compile(r"^- \(archive\)")


def load_config(agent_memory: Path) -> Config:
    cfg_path = agent_memory / "config.yml"
    if not cfg_path.exists() or yaml is None:
        return Config()
    with cfg_path.open() as f:
        raw = yaml.safe_load(f) or {}
    si = raw.get("startup_index", {})
    nm = raw.get("normalization", {})
    return Config(
        max_lines=si.get("max_lines", 80),
        max_live_entries=si.get("max_live_entries", 35),
        normalization_model=nm.get("model", "claude-haiku-4-5-20251001"),
    )


def load_index(agent_memory: Path) -> MemoryIndex:
    idx = MemoryIndex()
    memory_md = agent_memory / "MEMORY.md"
    if not memory_md.exists():
        return idx
    lines = memory_md.read_text().splitlines()
    idx.raw_lines = lines
    for line in lines:
        if _ARCHIVE_RE.match(line):
            idx.entries.append(MemoryEntry(path="", description="", is_archive=True))
            continue
        m = _ENTRY_RE.match(line)
        if m:
            idx.entries.append(MemoryEntry(path=m.group(1), description=m.group(2).strip()))
    return idx


def save_index(agent_memory: Path, lines: list[str]) -> None:
    (agent_memory / "MEMORY.md").write_text("\n".join(lines) + "\n")


def parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from a topic file. Returns {} if missing."""
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    block = content[3:end].strip()
    if yaml is None:
        # Minimal key:value parser fallback
        result = {}
        for line in block.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                result[k.strip()] = v.strip()
        return result
    return yaml.safe_load(block) or {}


REQUIRED_FRONTMATTER = {"id", "name", "description", "type", "updated"}


def check_doctor(agent_memory: Path, config: Config) -> list[str]:
    """Return list of violation strings. Empty list = healthy."""
    violations = []
    idx = load_index(agent_memory)

    # Line count
    line_count = len(idx.raw_lines)
    if line_count > config.max_lines:
        violations.append(f"MEMORY.md has {line_count} lines (max {config.max_lines})")

    # Live entry count
    live = len(idx.live_entries)
    if live > config.max_live_entries:
        violations.append(f"{live} live entries (max {config.max_live_entries}) — run --fix to archive")

    # Frontmatter validation
    for entry in idx.live_entries:
        if not entry.path:
            continue
        topic_path = agent_memory / entry.path
        if not topic_path.exists():
            violations.append(f"Missing topic file: {entry.path}")
            continue
        fm = parse_frontmatter(topic_path.read_text())
        missing = REQUIRED_FRONTMATTER - set(fm.keys())
        if missing:
            violations.append(f"Missing frontmatter keys in {entry.path}: {', '.join(sorted(missing))}")

    return violations


# ---------------------------------------------------------------------------
# CLI entry point (commands added in later tasks)
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(prog="memory-sync", description="Shared Claude+Codex agent memory")
    parser.add_argument("--project", default=os.getcwd(), help="Project root (default: cwd)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="Report violations").add_argument("--fix", action="store_true")
    sub.add_parser("init", help="One-time migration + symlink setup")
    sub.add_parser("extract-codex", help="Pull + normalize Codex rollout learnings")
    sub.add_parser("migrate", help="Re-run migration (idempotent)")

    args = parser.parse_args()
    project = Path(args.project).resolve()
    agent_memory = project / ".agent-memory"

    if args.cmd == "doctor":
        cmd_doctor(agent_memory, fix=getattr(args, "fix", False))
    elif args.cmd == "init":
        cmd_init(project)
    elif args.cmd == "extract-codex":
        cmd_extract_codex(project)
    elif args.cmd == "migrate":
        cmd_migrate(project)


if __name__ == "__main__":
    main()
```

Stub out the four command functions (will be filled in later tasks):

```python
def cmd_doctor(agent_memory: Path, fix: bool = False) -> None:
    config = load_config(agent_memory)
    violations = check_doctor(agent_memory, config)
    if not violations:
        print("✓ Memory index healthy")
        return
    for v in violations:
        print(f"  ✗ {v}")
    if fix:
        archive_oldest(agent_memory, config)


def cmd_init(project: Path) -> None:
    print(f"[init] Not yet implemented — project: {project}")


def cmd_extract_codex(project: Path) -> None:
    print(f"[extract-codex] Not yet implemented — project: {project}")


def cmd_migrate(project: Path) -> None:
    print(f"[migrate] Not yet implemented — project: {project}")


def archive_oldest(agent_memory: Path, config: Config) -> None:
    print("[doctor --fix] Not yet implemented")
```

- [ ] **Step 4: Create executable symlink**

```bash
chmod +x ~/.claude/bin/memory_sync.py
ln -sf ~/.claude/bin/memory_sync.py ~/.claude/bin/memory-sync
memory-sync --help
```

Expected: prints usage with `doctor`, `init`, `extract-codex`, `migrate` subcommands.

- [ ] **Step 5: Run tests — should pass**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_memory_sync.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_memory_sync.py
git commit -m "feat(memory-sync): core library skeleton + doctor command"
```

---

## Task 2: `init` command — migrate + symlink

**Files:**
- Modify: `~/.claude/bin/memory_sync.py` — implement `cmd_init`, `cmd_migrate`
- Test: `tests/unit/test_memory_sync.py` — add init tests

- [ ] **Step 1: Write failing tests for `cmd_init`**

Add to `tests/unit/test_memory_sync.py`:

```python
def test_init_creates_typed_subdirs(tmp_path):
    project = tmp_path / "myproject"
    project.mkdir()
    # Simulate existing Claude native memory
    native_slug = str(project).replace("/", "-")
    native_mem = tmp_path / ".claude" / "projects" / native_slug / "memory"
    native_mem.mkdir(parents=True)
    (native_mem / "feedback_test.md").write_text(
        "---\nname: test\ndescription: test\nmetadata:\n  type: feedback\n---\n\nContent.\n"
    )
    (native_mem / "MEMORY.md").write_text(
        "# Memory Index\n- [feedback_test.md](feedback_test.md) — a test entry\n"
    )

    ms.cmd_init(project, claude_home=tmp_path / ".claude")

    agent_memory = project / ".agent-memory"
    assert agent_memory.is_dir()
    assert (agent_memory / "feedback").is_dir()
    assert (agent_memory / "project").is_dir()
    assert (agent_memory / "reference").is_dir()
    assert (agent_memory / "user").is_dir()
    assert (agent_memory / "codex").is_dir()
    assert (agent_memory / "archive").is_dir()
    assert (agent_memory / "MEMORY.md").exists()
    assert (agent_memory / "config.yml").exists()


def test_init_creates_symlink(tmp_path):
    project = tmp_path / "myproject"
    project.mkdir()
    native_slug = str(project).replace("/", "-")
    native_mem = tmp_path / ".claude" / "projects" / native_slug / "memory"
    native_mem.mkdir(parents=True)
    (native_mem / "MEMORY.md").write_text("# Memory Index\n")

    ms.cmd_init(project, claude_home=tmp_path / ".claude")

    link = tmp_path / ".claude" / "projects" / native_slug / "memory"
    assert link.is_symlink()
    assert link.resolve() == (project / ".agent-memory").resolve()


def test_init_migrates_files_to_typed_subdirs(tmp_path):
    project = tmp_path / "myproject"
    project.mkdir()
    native_slug = str(project).replace("/", "-")
    native_mem = tmp_path / ".claude" / "projects" / native_slug / "memory"
    native_mem.mkdir(parents=True)
    (native_mem / "feedback_wording.md").write_text(
        "---\nname: wording\ndescription: wording rule\nmetadata:\n  type: feedback\n---\n\nDo X.\n\n**Why:** reason\n\n**How to apply:** always\n"
    )
    (native_mem / "project_pipeline.md").write_text(
        "---\nname: pipeline\ndescription: pipeline facts\nmetadata:\n  type: project\n---\n\nFact.\n"
    )
    (native_mem / "MEMORY.md").write_text(
        "# Memory Index\n"
        "- [feedback_wording.md](feedback_wording.md) — wording rule\n"
        "- [project_pipeline.md](project_pipeline.md) — pipeline facts\n"
    )

    ms.cmd_init(project, claude_home=tmp_path / ".claude")
    am = project / ".agent-memory"

    assert (am / "feedback" / "feedback_wording.md").exists()
    assert (am / "project" / "project_pipeline.md").exists()
    idx = ms.load_index(am)
    paths = [e.path for e in idx.live_entries]
    assert "feedback/feedback_wording.md" in paths
    assert "project/project_pipeline.md" in paths


def test_init_is_idempotent(tmp_path):
    project = tmp_path / "myproject"
    project.mkdir()
    native_slug = str(project).replace("/", "-")
    native_mem = tmp_path / ".claude" / "projects" / native_slug / "memory"
    native_mem.mkdir(parents=True)
    (native_mem / "MEMORY.md").write_text("# Memory Index\n")

    ms.cmd_init(project, claude_home=tmp_path / ".claude")
    ms.cmd_init(project, claude_home=tmp_path / ".claude")  # second call — must not raise
    assert (project / ".agent-memory").is_dir()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_memory_sync.py::test_init_creates_typed_subdirs -v
```

Expected: FAIL — `cmd_init` is a stub.

- [ ] **Step 3: Implement `cmd_init` and helpers in `memory_sync.py`**

Replace the `cmd_init` stub and add helpers:

```python
# Type detection from existing filename prefix
_TYPE_PREFIXES = {
    "feedback_": "feedback",
    "project_": "project",
    "reference_": "reference",
    "user_": "user",
}

def _detect_type(filename: str) -> str:
    for prefix, t in _TYPE_PREFIXES.items():
        if filename.startswith(prefix):
            return t
    return "project"  # default


def _project_to_claude_slug(project: Path) -> str:
    return str(project).replace("/", "-")


def _ensure_dirs(agent_memory: Path) -> None:
    for subdir in ("feedback", "project", "reference", "user", "codex", "archive"):
        (agent_memory / subdir).mkdir(parents=True, exist_ok=True)


CONFIG_YML = """\
startup_index:
  max_lines: 80
  max_live_entries: 35
topics:
  required_frontmatter: [id, name, description, type, updated]
archive:
  when_live_entries_over: 35
  destination: archive/YYYY/
  keep_archive_pointer: true
normalization:
  model: claude-haiku-4-5-20251001
"""


def _upgrade_frontmatter(content: str, slug: str, file_type: str) -> str:
    """Add missing required frontmatter fields (id, source_agents, updated)."""
    fm = parse_frontmatter(content)
    if not fm:
        return content
    today = date.today().isoformat()
    changed = False
    if "id" not in fm:
        fm["id"] = slug.replace("_", "-")
        changed = True
    if "source_agents" not in fm:
        fm["source_agents"] = ["claude"]
        changed = True
    if "updated" not in fm:
        fm["updated"] = today
        changed = True
    # Normalize metadata.type → type
    if "type" not in fm and "metadata" in fm and isinstance(fm["metadata"], dict):
        fm["type"] = fm["metadata"].get("type", file_type)
        del fm["metadata"]
        changed = True
    if not changed:
        return content
    # Rebuild: strip old frontmatter, prepend new
    body_start = content.find("\n---", 3)
    body = content[body_start + 4:] if body_start != -1 else content
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(str(x) for x in v)}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body.lstrip("\n")


def cmd_init(project: Path, claude_home: Path = None) -> None:
    if claude_home is None:
        claude_home = Path.home() / ".claude"
    agent_memory = project / ".agent-memory"
    native_slug = _project_to_claude_slug(project)
    native_mem = claude_home / "projects" / native_slug / "memory"

    # Already initialised
    if agent_memory.exists() and native_mem.is_symlink():
        print(f"[init] Already initialised — {agent_memory}")
        return

    _ensure_dirs(agent_memory)

    # Write config.yml if missing
    cfg_path = agent_memory / "config.yml"
    if not cfg_path.exists():
        cfg_path.write_text(CONFIG_YML)

    # Migrate existing memory files
    if native_mem.exists() and native_mem.is_dir() and not native_mem.is_symlink():
        _migrate_files(native_mem, agent_memory)
        shutil.rmtree(native_mem)

    # Create symlink
    if not native_mem.is_symlink():
        native_mem.symlink_to(agent_memory.resolve())
        print(f"[init] Symlink created: {native_mem} → {agent_memory}")

    print(f"[init] Done — {agent_memory}")


def _migrate_files(src: Path, agent_memory: Path) -> None:
    """Move files from native memory dir into typed subdirs of agent_memory."""
    index_entries = []
    old_index = load_index(src)
    old_desc = {e.path: e.description for e in old_index.live_entries}

    for f in src.iterdir():
        if f.name == "MEMORY.md" or f.name.startswith(".") or f.is_dir():
            continue
        file_type = _detect_type(f.name)
        slug = f.stem
        content = f.read_text()
        content = _upgrade_frontmatter(content, slug, file_type)
        dest = agent_memory / file_type / f.name
        dest.write_text(content)
        rel_path = f"{file_type}/{f.name}"
        desc = old_desc.get(f.name, slug.replace("_", " "))
        index_entries.append(f"- [{rel_path}]({rel_path}) — {desc}")
        print(f"[migrate] {f.name} → {rel_path}")

    # Rebuild MEMORY.md
    header = (src / "MEMORY.md").read_text().splitlines()[0] if (src / "MEMORY.md").exists() else "# Memory Index"
    lines = [header, ""] + sorted(index_entries) + [""]
    save_index(agent_memory, lines)


def cmd_migrate(project: Path) -> None:
    agent_memory = project / ".agent-memory"
    claude_home = Path.home() / ".claude"
    native_slug = _project_to_claude_slug(project)
    native_mem = claude_home / "projects" / native_slug / "memory"
    if native_mem.is_symlink():
        print("[migrate] Already symlinked — nothing to do")
        return
    cmd_init(project, claude_home)
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_memory_sync.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_memory_sync.py
git commit -m "feat(memory-sync): init command — migrate existing memory + create symlink"
```

---

## Task 3: `doctor --fix` — archive enforcement

**Files:**
- Modify: `~/.claude/bin/memory_sync.py` — implement `archive_oldest`
- Test: `tests/unit/test_memory_sync.py` — add archive tests

- [ ] **Step 1: Write failing tests for `archive_oldest`**

Add to `tests/unit/test_memory_sync.py`:

```python
def make_topic_file(updated: str, type_: str = "feedback") -> str:
    return (
        f"---\nid: entry\nname: entry\ndescription: an entry\n"
        f"type: {type_}\nsource_agents: [claude]\nupdated: {updated}\n---\n\nRule.\n"
    )


def test_archive_oldest_moves_files_when_over_cap(tmp_path):
    am = tmp_path / ".agent-memory"
    am.mkdir()
    (am / "feedback").mkdir()
    (am / "archive").mkdir()

    # Create 36 entries (1 over cap of 35)
    index_lines = ["# Memory Index"]
    for i in range(36):
        fname = f"feedback/e{i:02d}.md"
        (am / "feedback" / f"e{i:02d}.md").write_text(make_topic_file(f"2025-01-{i+1:02d}"))
        index_lines.append(f"- [{fname}]({fname}) — entry {i}")
    save_index(am, index_lines)

    ms.archive_oldest(am, ms.Config())

    idx = ms.load_index(am)
    assert len(idx.live_entries) == 35
    # Oldest (e00, updated 2025-01-01) should be archived
    live_paths = [e.path for e in idx.live_entries]
    assert "feedback/e00.md" not in live_paths
    # Archive dir should have the file
    archived = list((am / "archive").rglob("e00.md"))
    assert len(archived) == 1


def test_archive_oldest_adds_archive_pointer_to_index(tmp_path):
    am = tmp_path / ".agent-memory"
    am.mkdir()
    (am / "feedback").mkdir()
    (am / "archive").mkdir()

    index_lines = ["# Memory Index"]
    for i in range(36):
        fname = f"feedback/e{i:02d}.md"
        (am / "feedback" / f"e{i:02d}.md").write_text(make_topic_file(f"2025-0{(i//9)+1}-{(i%9)+1:02d}"))
        index_lines.append(f"- [{fname}]({fname}) — entry {i}")
    save_index(am, index_lines)

    ms.archive_oldest(am, ms.Config())
    index_text = (am / "MEMORY.md").read_text()
    assert "(archive)" in index_text


def test_archive_oldest_noop_when_under_cap(tmp_path):
    am = tmp_path / ".agent-memory"
    am.mkdir()
    (am / "feedback").mkdir()
    (am / "archive").mkdir()
    index_lines = ["# Memory Index",
                   "- [feedback/a.md](feedback/a.md) — entry a"]
    (am / "feedback" / "a.md").write_text(make_topic_file("2026-01-01"))
    save_index(am, index_lines)
    original = (am / "MEMORY.md").read_text()

    ms.archive_oldest(am, ms.Config())
    assert (am / "MEMORY.md").read_text() == original
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_memory_sync.py::test_archive_oldest_moves_files_when_over_cap -v
```

Expected: FAIL — `archive_oldest` is a stub.

- [ ] **Step 3: Implement `archive_oldest` in `memory_sync.py`**

Replace the `archive_oldest` stub:

```python
def archive_oldest(agent_memory: Path, config: Config) -> None:
    idx = load_index(agent_memory)
    live = idx.live_entries
    if len(live) <= config.max_live_entries:
        return

    # Sort live entries by frontmatter 'updated' date (oldest first)
    def entry_date(e: MemoryEntry) -> str:
        p = agent_memory / e.path
        if not p.exists():
            return "0000-00-00"
        fm = parse_frontmatter(p.read_text())
        return str(fm.get("updated", "0000-00-00"))

    live_sorted = sorted(live, key=entry_date)
    to_archive = live_sorted[:len(live) - config.max_live_entries]

    year = datetime.now().strftime("%Y")
    archive_dir = agent_memory / "archive" / year
    archive_dir.mkdir(parents=True, exist_ok=True)

    archived_paths = set()
    for entry in to_archive:
        src = agent_memory / entry.path
        if src.exists():
            dest = archive_dir / src.name
            shutil.move(str(src), dest)
            archived_paths.add(entry.path)
            print(f"[archive] {entry.path} → archive/{year}/{src.name}")

    # Rebuild MEMORY.md: remove archived entries, add one archive pointer
    new_lines = []
    archive_mentioned = False
    for line in idx.raw_lines:
        m = _ENTRY_RE.match(line)
        if m and m.group(1) in archived_paths:
            if not archive_mentioned:
                rel = f"archive/{year}/"
                new_lines.append(
                    f"- (archive) [{rel}]({rel}) — {len(archived_paths)} entries archived {year}"
                )
                archive_mentioned = True
            continue
        new_lines.append(line)
    save_index(agent_memory, new_lines)
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_memory_sync.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_memory_sync.py
git commit -m "feat(memory-sync): doctor --fix archives oldest entries when over cap"
```

---

## Task 4: `extract-codex` — parse rollout summaries

**Files:**
- Modify: `~/.claude/bin/memory_sync.py` — implement rollout parser
- Test: `tests/unit/test_memory_sync.py` — add rollout parsing tests

- [ ] **Step 1: Write failing tests for `parse_rollout_bullets`**

Add to `tests/unit/test_memory_sync.py`:

```python
SAMPLE_ROLLOUT = """\
# Task Group: content-creation / dashboard fix
scope: Dashboard SSE fix; use when working on dashboard streaming.
applies_to: cwd=/home/tim-huang/content-creation; reuse_rule=safe to reuse

## Task 1: Fix SSE streaming, success

### rollout_summary_files

- rollout_summaries/2026-05-11T07-30-14-D8NP-dashboard_fix.md

## User preferences

- when user said "fix it now" -> fix immediately and rerun a live test [Task 1]
- when user challenged "did you test?" -> separate interactive proof from cron proof [Task 1]

## Reusable knowledge

- SSE endpoints must flush after each event or client hangs [Task 1]
- dashboard uses port 8080; firewall must allow it [Task 1]

## Failures and how to do differently
"""

WRONG_PROJECT_ROLLOUT = """\
# Task Group: know-fountains / wiki update
applies_to: cwd=/home/tim-huang/know-fountains; reuse_rule=safe
## User preferences
- some preference [Task 1]
"""


def test_parse_rollout_bullets_extracts_both_sections():
    bullets = ms.parse_rollout_bullets(SAMPLE_ROLLOUT, project_cwd="/home/tim-huang/content-creation")
    assert len(bullets) == 4
    prefs = [b for b in bullets if b.section == "preferences"]
    knowledge = [b for b in bullets if b.section == "knowledge"]
    assert len(prefs) == 2
    assert len(knowledge) == 2


def test_parse_rollout_bullets_filters_by_cwd():
    bullets = ms.parse_rollout_bullets(WRONG_PROJECT_ROLLOUT, project_cwd="/home/tim-huang/content-creation")
    assert bullets == []


def test_parse_rollout_bullets_strips_task_ref():
    bullets = ms.parse_rollout_bullets(SAMPLE_ROLLOUT, project_cwd="/home/tim-huang/content-creation")
    for b in bullets:
        assert "[Task" not in b.text


def test_scan_new_rollouts_returns_only_newer(tmp_path):
    rollout_dir = tmp_path / "rollout_summaries"
    rollout_dir.mkdir()
    old_file = rollout_dir / "2026-05-01T00-00-00-AAAA-old.md"
    new_file = rollout_dir / "2026-05-13T00-00-00-BBBB-new.md"
    old_file.write_text(SAMPLE_ROLLOUT)
    new_file.write_text(SAMPLE_ROLLOUT)

    # Timestamp set to between the two files
    since = datetime(2026, 5, 5)
    results = ms.scan_new_rollouts(rollout_dir, since=since, project_cwd="/home/tim-huang/content-creation")
    assert len(results) == 1
    assert results[0][0].name == new_file.name
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_memory_sync.py::test_parse_rollout_bullets_extracts_both_sections -v
```

Expected: FAIL — `parse_rollout_bullets` not yet defined.

- [ ] **Step 3: Implement rollout parser in `memory_sync.py`**

```python
@dataclass
class RolloutBullet:
    text: str       # cleaned bullet text (task ref stripped)
    section: str    # "preferences" or "knowledge"


_TASK_REF_RE = re.compile(r"\s*\[Task \d+\]\s*$")
_CWD_RE = re.compile(r"applies_to:.*?cwd=([^;]+)")

ROLLOUT_DIR = Path.home() / ".codex/memories/rollout_summaries"
SYNC_STATE_FILE_NAME = ".last-codex-sync"


def parse_rollout_bullets(content: str, project_cwd: str) -> list[RolloutBullet]:
    """Extract preference + knowledge bullets from a Codex rollout summary."""
    # Check project cwd matches
    cwd_match = _CWD_RE.search(content)
    if not cwd_match or cwd_match.group(1).strip() != project_cwd:
        return []

    bullets = []
    current_section = None
    for line in content.splitlines():
        if line.strip() == "## User preferences":
            current_section = "preferences"
            continue
        if line.strip() == "## Reusable knowledge":
            current_section = "knowledge"
            continue
        if line.startswith("## ") and current_section:
            current_section = None  # next section
            continue
        if current_section and re.match(r"^\s*-\s+", line):
            text = re.sub(r"^\s*-\s+", "", line)
            text = _TASK_REF_RE.sub("", text).strip()
            if text:
                bullets.append(RolloutBullet(text=text, section=current_section))

    return bullets


def _rollout_file_datetime(path: Path) -> Optional[datetime]:
    """Parse datetime from filename like 2026-05-13T07-30-14-XXXX-name.md"""
    m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})", path.name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%dT%H-%M-%S")
    except ValueError:
        return None


def scan_new_rollouts(
    rollout_dir: Path,
    since: datetime,
    project_cwd: str,
) -> list[tuple[Path, list[RolloutBullet]]]:
    """Return (file, bullets) pairs for rollout files newer than `since`."""
    results = []
    if not rollout_dir.exists():
        return results
    for f in sorted(rollout_dir.iterdir()):
        if not f.suffix == ".md":
            continue
        dt = _rollout_file_datetime(f)
        if dt is None or dt <= since:
            continue
        bullets = parse_rollout_bullets(f.read_text(), project_cwd=project_cwd)
        if bullets:
            results.append((f, bullets))
    return results
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_memory_sync.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_memory_sync.py
git commit -m "feat(memory-sync): extract-codex rollout parser"
```

---

## Task 5: `extract-codex` — Haiku normalization + write

**Files:**
- Modify: `~/.claude/bin/memory_sync.py` — implement `normalize_bullet`, `append_codex_learnings`, `cmd_extract_codex`
- Test: `tests/unit/test_memory_sync.py` — add normalization + write tests

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_memory_sync.py`:

```python
def test_build_normalization_prompt_contains_bullet():
    bullet = RolloutBullet(text="fix immediately and rerun live test", section="preferences")
    prompt = ms.build_normalization_prompt(bullet, today="2026-05-13")
    assert "fix immediately and rerun live test" in prompt
    assert "---" in prompt  # expects frontmatter in output


def test_append_codex_learnings_creates_file(tmp_path):
    am = tmp_path / ".agent-memory"
    am.mkdir()
    (am / "codex").mkdir()
    (am / "MEMORY.md").write_text("# Memory Index\n")

    topic_content = (
        "---\nid: fix-live-test\nname: Fix and retest\n"
        "description: Fix immediately and rerun live test\n"
        "type: feedback\nsource_agents: [codex]\nupdated: 2026-05-13\n---\n\n"
        "Fix immediately and rerun a live test.\n\n**Why:** proof matters\n\n**How to apply:** always\n"
    )
    ms.append_codex_learnings(am, [topic_content])

    learnings = am / "codex" / "codex-learnings.md"
    assert learnings.exists()
    assert "fix-live-test" in learnings.read_text()

    # Should add to MEMORY.md index if not present
    index = (am / "MEMORY.md").read_text()
    assert "codex/codex-learnings.md" in index


def test_append_codex_learnings_deduplicates_by_id(tmp_path):
    am = tmp_path / ".agent-memory"
    am.mkdir()
    (am / "codex").mkdir()
    (am / "MEMORY.md").write_text("# Memory Index\n")

    topic = (
        "---\nid: fix-live-test\nname: Fix\ndescription: fix\n"
        "type: feedback\nsource_agents: [codex]\nupdated: 2026-05-13\n---\n\nRule.\n"
    )
    ms.append_codex_learnings(am, [topic])
    ms.append_codex_learnings(am, [topic])  # second call — same id

    content = (am / "codex" / "codex-learnings.md").read_text()
    assert content.count("id: fix-live-test") == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_memory_sync.py::test_build_normalization_prompt_contains_bullet -v
```

Expected: FAIL.

- [ ] **Step 3: Implement normalization + write in `memory_sync.py`**

```python
NORMALIZATION_PROMPT_TEMPLATE = """\
Convert this Codex memory bullet into a concise shared-memory topic file.

Bullet type: {section}
Bullet text: {text}

Output ONLY the topic file in this exact format (no explanation, no extra text):

---
id: <kebab-slug-3-to-5-words>
name: <3-5 word name>
description: <one sentence: what this memory is for>
type: {fm_type}
source_agents: [codex]
updated: {today}
---

<Rule in one sentence.>

**Why:** <reason this matters>

**How to apply:** <when this kicks in>
"""


def build_normalization_prompt(bullet: RolloutBullet, today: str) -> str:
    fm_type = "feedback" if bullet.section == "preferences" else "project"
    return NORMALIZATION_PROMPT_TEMPLATE.format(
        section=bullet.section,
        text=bullet.text,
        fm_type=fm_type,
        today=today,
    )


def normalize_bullet_via_claude(bullet: RolloutBullet, model: str) -> Optional[str]:
    """Call Claude CLI to normalize a bullet. Returns topic file content or None."""
    today = date.today().isoformat()
    prompt = build_normalization_prompt(bullet, today=today)
    try:
        result = subprocess.run(
            [
                str(Path.home() / ".local/bin/claude"),
                "-p", prompt,
                "--model", model,
                "--no-session-persistence",
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"[extract-codex] Haiku call failed: {result.stderr[:200]}", file=sys.stderr)
            return None
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[extract-codex] Claude CLI error: {e}", file=sys.stderr)
        return None


def _existing_ids(learnings_path: Path) -> set[str]:
    if not learnings_path.exists():
        return set()
    content = learnings_path.read_text()
    return set(re.findall(r"^id:\s*(.+)$", content, re.MULTILINE))


def append_codex_learnings(agent_memory: Path, topic_contents: list[str]) -> int:
    """Append new topic file contents to codex-learnings.md. Returns count added."""
    learnings_path = agent_memory / "codex" / "codex-learnings.md"
    existing = _existing_ids(learnings_path)
    added = 0
    new_blocks = []
    for content in topic_contents:
        fm = parse_frontmatter(content)
        entry_id = fm.get("id", "")
        if entry_id in existing:
            continue
        new_blocks.append(content.strip())
        existing.add(entry_id)
        added += 1

    if not new_blocks:
        return 0

    separator = "\n\n---\n\n"
    if learnings_path.exists() and learnings_path.stat().st_size > 0:
        with learnings_path.open("a") as f:
            f.write(separator + separator.join(new_blocks))
    else:
        learnings_path.write_text("\n\n".join(new_blocks) + "\n")

    # Add to MEMORY.md if not present
    rel = "codex/codex-learnings.md"
    idx_path = agent_memory / "MEMORY.md"
    idx_text = idx_path.read_text() if idx_path.exists() else "# Memory Index\n"
    if rel not in idx_text:
        entry = f"- [{rel}]({rel}) — Codex-extracted preferences and reusable knowledge"
        idx_path.write_text(idx_text.rstrip() + "\n" + entry + "\n")

    return added


def _read_sync_timestamp(agent_memory: Path) -> datetime:
    state = agent_memory / SYNC_STATE_FILE_NAME
    if not state.exists():
        return datetime(2000, 1, 1)
    try:
        return datetime.fromisoformat(state.read_text().strip())
    except ValueError:
        return datetime(2000, 1, 1)


def _write_sync_timestamp(agent_memory: Path) -> None:
    (agent_memory / SYNC_STATE_FILE_NAME).write_text(datetime.utcnow().isoformat())


def cmd_extract_codex(project: Path) -> None:
    agent_memory = project / ".agent-memory"
    if not agent_memory.exists():
        print("[extract-codex] .agent-memory not found — run memory-sync init first", file=sys.stderr)
        return

    config = load_config(agent_memory)
    since = _read_sync_timestamp(agent_memory)
    project_cwd = str(project)

    rollouts = scan_new_rollouts(ROLLOUT_DIR, since=since, project_cwd=project_cwd)
    if not rollouts:
        print(f"[extract-codex] No new rollout entries since {since.date()}")
        _write_sync_timestamp(agent_memory)
        return

    all_bullets = [b for _, bullets in rollouts for b in bullets]
    print(f"[extract-codex] Found {len(all_bullets)} bullets in {len(rollouts)} rollout file(s)")

    normalized = []
    for bullet in all_bullets:
        content = normalize_bullet_via_claude(bullet, model=config.normalization_model)
        if content:
            normalized.append(content)

    added = append_codex_learnings(agent_memory, normalized)
    print(f"[extract-codex] Added {added} new entries to codex/codex-learnings.md")
    _write_sync_timestamp(agent_memory)
```

- [ ] **Step 4: Run tests — should pass**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_memory_sync.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Smoke test `extract-codex` against real Codex data**

```bash
cd /home/tim-huang/content-creation
memory-sync extract-codex --project /home/tim-huang/content-creation
```

Expected: reports N bullets from rollout files, adds entries to `.agent-memory/codex/codex-learnings.md`.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_memory_sync.py
git commit -m "feat(memory-sync): extract-codex with Haiku normalization and deduplication"
```

---

## Task 6: Claude SessionEnd hook + settings.json

**Files:**
- Create: `~/.claude/hooks/memory-sync-session-end.py`
- Modify: `~/.claude/settings.json`

- [ ] **Step 1: Create the hook script**

```python
# ~/.claude/hooks/memory-sync-session-end.py
#!/usr/bin/env python3
"""Spawn memory-sync extract-codex in background after Claude session ends."""
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT = "/home/tim-huang/content-creation"
LOG = Path.home() / ".local/state/memory-sync.log"
LOG.parent.mkdir(parents=True, exist_ok=True)

try:
    event = json.loads(sys.stdin.read())
    cwd = event.get("cwd", "")
    # Only run for the content-creation project
    if not cwd.startswith(PROJECT):
        sys.exit(0)
except Exception:
    sys.exit(0)

subprocess.Popen(
    ["memory-sync", "extract-codex", "--project", PROJECT],
    start_new_session=True,
    stdin=subprocess.DEVNULL,
    stdout=open(LOG, "a"),
    stderr=subprocess.STDOUT,
)
```

```bash
chmod +x ~/.claude/hooks/memory-sync-session-end.py
```

- [ ] **Step 2: Add to `~/.claude/settings.json` SessionEnd array**

Read current `SessionEnd` hooks array in `~/.claude/settings.json`. Append the new entry:

```json
{
  "type": "command",
  "command": "python3 /home/tim-huang/.claude/hooks/memory-sync-session-end.py"
}
```

The final `SessionEnd` section should look like:

```json
"SessionEnd": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "/home/tim-huang/.claude/hooks/session-end.py"
      }
    ]
  },
  {
    "hooks": [
      {
        "type": "command",
        "command": "python3 /home/tim-huang/.claude/hooks/memory-sync-session-end.py"
      }
    ]
  }
]
```

- [ ] **Step 3: Verify hook fires**

```bash
# Test the hook manually (simulates SessionEnd event)
echo '{"session_id": "test-123", "cwd": "/home/tim-huang/content-creation"}' \
  | python3 ~/.claude/hooks/memory-sync-session-end.py
sleep 3
tail ~/.local/state/memory-sync.log
```

Expected: log shows `[extract-codex]` output.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(memory-sync): Claude SessionEnd hook"
# Note: settings.json is in ~/.claude/ (not the project), no git add needed
```

---

## Task 7: Codex Stop hook

**Files:**
- Modify: `~/.codex/hooks.json`

- [ ] **Step 1: Add entry to `~/.codex/hooks.json`**

Current `Stop` array has one entry. Append:

```json
{
  "type": "command",
  "command": "memory-sync extract-codex --project /home/tim-huang/content-creation",
  "timeout": 30
}
```

Final `~/.codex/hooks.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "/home/tim-huang/content-creation/scripts/restart-dashboard-if-changed.sh",
            "timeout": 10
          }
        ]
      },
      {
        "hooks": [
          {
            "type": "command",
            "command": "memory-sync extract-codex --project /home/tim-huang/content-creation",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 2: Verify hook syntax is valid JSON**

```bash
python3 -m json.tool ~/.codex/hooks.json > /dev/null && echo "valid JSON"
```

Expected: `valid JSON`

- [ ] **Step 3: Commit (note: hooks.json not in project git)**

No git commit needed — `~/.codex/hooks.json` is machine config.

---

## Task 8: AGENTS.md Session Startup

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Add line to `## Session Startup` section**

Current `## Session Startup` section:
```
## Session Startup

Before anything else:
1. Read `~/.openclaw/workspace/SOUL.md` — who you are
2. Read `~/.openclaw/workspace/USER.md` — who you're helping
3. Read `CLAUDE.md` — full project architecture, commands, and design decisions
4. Read `~/.openclaw/workspace/memory/` recent files for conversation continuity
```

Add line 5:
```
5. Read `.agent-memory/MEMORY.md` — shared agent memories (feedback, project facts, preferences)
```

- [ ] **Step 2: Verify AGENTS.md parses cleanly**

```bash
grep -n "agent-memory" AGENTS.md
```

Expected: shows line 5 in Session Startup.

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "feat(memory-sync): add .agent-memory/MEMORY.md to Codex Session Startup"
```

---

## Task 9: Weekly maintenance cron

**Files:**
- Create: `~/.local/bin/memory-weekly-maintenance.sh`

- [ ] **Step 1: Create the wrapper script**

```bash
#!/usr/bin/env bash
# ~/.local/bin/memory-weekly-maintenance.sh
# Weekly memory maintenance: enforce cap, audit, extract missed Codex learnings.

HOME="/home/tim-huang"
PATH="/home/tim-huang/.local/bin:/home/tim-huang/.nvm/versions/node/v24.14.0/bin:/usr/bin:/bin"
LOG="$HOME/.local/state/memory-maintenance.log"
PROJECT="$HOME/content-creation"
CODEX="$HOME/.nvm/versions/node/v24.14.0/bin/codex"
CLAUDE="$HOME/.local/bin/claude"

mkdir -p "$(dirname "$LOG")"
echo "=== START $(date) ===" >> "$LOG"

# Phase 1: mechanical — enforce live entry cap, validate frontmatter
memory-sync doctor --fix --project "$PROJECT" >> "$LOG" 2>&1
echo "Phase 1 done" >> "$LOG"

# Phase 2: intelligent audit via Claude Haiku — stale + duplicate detection
"$CLAUDE" -p \
  "You are reviewing the shared agent memory at $PROJECT/.agent-memory/. \
Read MEMORY.md and all topic files in feedback/, project/, reference/, user/, and codex/. \
Identify and list: \
(1) entries with 'updated' date older than 3 months from today that appear unlikely to be referenced in recent work, \
(2) pairs of entries that appear semantically duplicate (same rule expressed differently). \
Output a markdown checklist of recommended actions. Do NOT modify any files." \
  --model claude-haiku-4-5-20251001 \
  --no-session-persistence \
  --cwd "$PROJECT" >> "$LOG" 2>&1
echo "Phase 2 done" >> "$LOG"

# Phase 3: Codex extract — catch any missed session-end extractions
"$CODEX" exec \
  --skip-git-repo-check --ignore-rules --ephemeral \
  --cd "$PROJECT" \
  "Run the command: memory-sync extract-codex --project /home/tim-huang/content-creation and report how many new entries were added to .agent-memory/codex/codex-learnings.md. Output only the result." \
  >> "$LOG" 2>&1
echo "Phase 3 done" >> "$LOG"

echo "=== EXIT=$? $(date) ===" >> "$LOG"
```

```bash
chmod +x ~/.local/bin/memory-weekly-maintenance.sh
```

- [ ] **Step 2: Test wrapper in cron-like environment**

```bash
env -i HOME="/home/tim-huang" \
  SHELL=/bin/bash \
  PATH="/home/tim-huang/.local/bin:/home/tim-huang/.nvm/versions/node/v24.14.0/bin:/usr/bin:/bin" \
  /home/tim-huang/.local/bin/memory-weekly-maintenance.sh
```

```bash
tail -30 ~/.local/state/memory-maintenance.log
```

Expected: all three phases complete, no `command not found` errors.

- [ ] **Step 3: Add cron entry (weekly, Sunday 9am)**

```bash
(crontab -l; echo "0 9 * * 0 /home/tim-huang/.local/bin/memory-weekly-maintenance.sh") | crontab -
crontab -l | grep memory
```

Expected: entry appears in crontab.

- [ ] **Step 4: Schedule and verify smoke test (+2 min)**

```bash
# Add smoke test entry running 2 min from now
SMOKE_TIME=$(date -d "+2 minutes" "+%M %H")
SMOKE_TAG="memory-smoke-$(date +%s)"
(crontab -l; echo "$SMOKE_TIME * * * * /home/tim-huang/.local/bin/memory-weekly-maintenance.sh # $SMOKE_TAG") | crontab -
echo "Smoke test scheduled at $(date -d '+2 minutes' '+%H:%M')"
```

After 2 minutes:
```bash
journalctl -u cron --since "5 minutes ago" | grep memory
tail -20 ~/.local/state/memory-maintenance.log
```

Expected: cron shows launch, log shows all three phases, no `EXIT=1`.

Remove smoke test entry after verification:
```bash
crontab -l | grep -v "$SMOKE_TAG" | crontab -
```

---

## Task 10: Execute `memory-sync init` — actual migration

**Files:**
- Created: `<project>/.agent-memory/` (all subdirs + migrated files)
- Created (symlink): `~/.claude/projects/-home-tim-huang-content-creation/memory`

- [ ] **Step 1: Dry-run check**

```bash
ls ~/.claude/projects/-home-tim-huang-content-creation/memory/
```

Expected: existing memory files listed (not yet a symlink).

- [ ] **Step 2: Run init**

```bash
cd /home/tim-huang/content-creation
memory-sync init
```

Expected output:
```
[migrate] feedback_description_content.md → feedback/feedback_description_content.md
[migrate] feedback_e2e_lessons.md → feedback/feedback_e2e_lessons.md
...
[init] Symlink created: ~/.claude/projects/-home-tim-huang-content-creation/memory → /home/tim-huang/content-creation/.agent-memory
[init] Done — /home/tim-huang/content-creation/.agent-memory
```

- [ ] **Step 3: Verify symlink**

```bash
ls -la ~/.claude/projects/-home-tim-huang-content-creation/memory
```

Expected: `memory -> /home/tim-huang/content-creation/.agent-memory`

- [ ] **Step 4: Verify MEMORY.md index**

```bash
cat /home/tim-huang/content-creation/.agent-memory/MEMORY.md
```

Expected: 14+ entries with typed paths (`feedback/`, `project/`, `reference/`, `user/`).

- [ ] **Step 5: Verify doctor passes**

```bash
memory-sync doctor --project /home/tim-huang/content-creation
```

Expected: `✓ Memory index healthy`

- [ ] **Step 6: Run full test suite**

```bash
cd /home/tim-huang/content-creation
uv run pytest tests/unit/test_memory_sync.py -v
uv run ruff check ~/.claude/bin/memory_sync.py 2>/dev/null || echo "ruff not in scope for ~/.claude/bin"
```

Expected: all memory_sync tests PASS.

- [ ] **Step 7: Gitignore `.agent-memory/`**

```bash
echo ".agent-memory/" >> .gitignore
git add .gitignore
git commit -m "chore: gitignore .agent-memory/ (machine-local, like .codex/memories/)"
```

- [ ] **Step 8: Final commit**

```bash
git add tests/unit/test_memory_sync.py AGENTS.md .gitignore
git status  # confirm only expected changes
git commit -m "feat: shared Claude+Codex agent memory (.agent-memory/) — init complete"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| `.agent-memory/` typed subdirs | Task 2 |
| `MEMORY.md` 80-line / 35-entry cap | Tasks 1, 3 |
| `config.yml` | Task 2 |
| Topic file format with required frontmatter | Tasks 1, 2, 5 |
| Claude symlink (autoMemoryDirectory workaround) | Task 2 |
| Codex reads via AGENTS.md Session Startup | Task 8 |
| `extract-codex` rollout parser | Task 4 |
| Haiku normalization | Task 5 |
| Deduplication by id | Task 5 |
| Claude SessionEnd hook | Task 6 |
| Codex Stop hook | Task 7 |
| Weekly cron maintenance | Task 9 |
| `memory-sync doctor --fix` archive | Task 3 |
| Actual migration of existing 14 files | Task 10 |
| `.last-codex-sync` timestamp | Task 5 |

No gaps found.
