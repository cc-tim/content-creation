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


def test_init_creates_typed_subdirs(tmp_path):
    project = tmp_path / "myproject"
    project.mkdir()
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
    for subdir in ("feedback", "project", "reference", "user", "codex", "archive"):
        assert (agent_memory / subdir).is_dir()
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
    ms.cmd_init(project, claude_home=tmp_path / ".claude")  # second call must not raise
    assert (project / ".agent-memory").is_dir()
