# tests/unit/test_memory_sync.py
import sys, os
sys.path.insert(0, os.path.expanduser("~/.claude/bin"))
import memory_sync as ms

import datetime
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


# ---------------------------------------------------------------------------
# Task 3: archive_oldest
# ---------------------------------------------------------------------------

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

    index_lines = ["# Memory Index"]
    for i in range(36):
        fname = f"feedback/e{i:02d}.md"
        (am / "feedback" / f"e{i:02d}.md").write_text(make_topic_file(f"2025-01-{i+1:02d}"))
        index_lines.append(f"- [{fname}]({fname}) — entry {i}")
    ms.save_index(am, index_lines)

    ms.archive_oldest(am, ms.Config())

    idx = ms.load_index(am)
    assert len(idx.live_entries) == 35
    live_paths = [e.path for e in idx.live_entries]
    assert "feedback/e00.md" not in live_paths
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
    ms.save_index(am, index_lines)

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
    ms.save_index(am, index_lines)
    original = (am / "MEMORY.md").read_text()

    ms.archive_oldest(am, ms.Config())
    assert (am / "MEMORY.md").read_text() == original


# ---------------------------------------------------------------------------
# Task 4: parse_rollout_bullets / scan_new_rollouts
# ---------------------------------------------------------------------------

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

    since = datetime.datetime(2026, 5, 5)
    results = ms.scan_new_rollouts(rollout_dir, since=since, project_cwd="/home/tim-huang/content-creation")
    assert len(results) == 1
    assert results[0][0].name == new_file.name


# ---------------------------------------------------------------------------
# Task 5: build_normalization_prompt / append_codex_learnings
# ---------------------------------------------------------------------------

def test_build_normalization_prompt_contains_bullet():
    bullet = ms.RolloutBullet(text="fix immediately and rerun live test", section="preferences")
    prompt = ms.build_normalization_prompt(bullet, today="2026-05-13")
    assert "fix immediately and rerun live test" in prompt
    assert "---" in prompt


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
    ms.append_codex_learnings(am, [topic])

    content = (am / "codex" / "codex-learnings.md").read_text()
    assert content.count("id: fix-live-test") == 1
