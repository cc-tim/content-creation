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
