# Skill Management — Plan C: sync, doctor, search, list

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the four "read + reconcile" subcommands of `skill-sync` — `list`, `search`, `doctor`, `sync` — together with the generated `index.json` that powers search and dashboard-style queries. After Plan C, the operator can ask the agent in natural language ("find a skill for FishAudio", "is my setup healthy?", "what's installed where?") and get terse answers without burning main-session tokens.

**Architecture:**
- **`index.json` is the search/listing substrate.** Generated at `~/skill-repo/index.json`. Regenerated on `sync` and (lazily) on `search` if missing or older than any `skills/<name>/SKILL.md`. One entry per skill: `name`, `description`, `when_to_use`, `body_excerpt`, `body_lines`, `platforms`, `frontmatter_keys`.
- **`list` is dumb and read-only.** Scans `~/.claude/skills/`, `~/.codex/skills/`, `~/skill-repo/skills/` and prints a one-row-per-skill summary with status (symlinked-to-repo / real-file / broken-link / missing). Doesn't touch index.
- **`search` is a tiny scorer.** Loads index, ranks skills by token overlap across name/description/body_excerpt with weights 3/2/1, prints top-N (default 5) terse. `--full` greps raw `SKILL.md` bodies for an extra confirmation pass.
- **`doctor` runs the spec's check table.** Two severity levels (fail / warn). Returns exit 1 if any fail. `--quiet` suppresses success output and reduces failures to a single line — the SessionStart hook (Plan E) will swallow this with `|| true`.
- **`sync` is the reconciliation surface.** For Plan C its job is user-level only: (a) ensure every repo skill has both symlinks, healing missing/broken ones; (b) detect local-only skills (real file/dir at user level not in repo) and warn (push is Plan D); (c) regenerate `index.json`. Project-scope `.skills.toml` drift is **explicitly deferred to Plan D**, since Plan D is what introduces project snapshots.
- **YAML frontmatter parsing gets its own module.** `frontmatter.py` wraps `pyyaml` so doctor/index/list/sync all share one parser. New dependency: `pyyaml>=6.0`. Hand-parsing was OK for Plan B's narrow normalize-and-compare use; Plan C needs char-count and key-existence checks on arbitrary frontmatter shapes, so a real parser is mandatory.

**Tech Stack:** Python 3.11+, `uv`, `pytest`, `requests` (already there), `markdownify` (already there), **new: `pyyaml>=6.0`**.

**Reference spec:** `content-creation/docs/superpowers/specs/2026-05-12-skill-management-design.md` — see "CLI surface", "Sync semantics", "Testing & verification".
**Reference plan (predecessor, completed):** `2026-05-12-skill-management-plan-b-init-symlinks-migration.md`

---

## Design decisions locked in this plan

1. **`pyyaml` added as a runtime dependency.** Spec's offhand "(already on system)" note doesn't match `pyproject.toml`. It's tiny (~200 KB wheel, no transitive deps) and the alternative (hand-parsing multi-line/`|` block scalars in `description`) is fragile. Decision: add it.

2. **`platforms` is derived from `subagents/` presence only — not from frontmatter keys.** Spec's portability rule: SKILL.md frontmatter may contain Claude-only keys (`context: fork`, `allowed-tools`, `agent`, etc.) and that's fine — Codex tolerates them. The `platforms` field in `index.json` only narrows to claude-only / codex-only when the skill carries a **subagent sidecar** that exists for one platform but not the other. With none of the current 5 skills using subagents, every entry will be `["claude", "codex"]` after Plan C; the detection logic is in place for Plan D's `install`.

3. **`search` is greedy-substring + token-bag, not ranking-quality.** Token weight 3/2/1 (name/description/body_excerpt). No fuzzy match, no stemming. Good enough for "find skill for fishaudio" type queries. If the operator later complains about recall, we revisit — but for the natural-language UX the spec describes, this is overkill-as-is.

4. **`sync` is interactive only for local-only detections, and only when reachable.** If `sys.stdin.isatty()` is False (CI, hook), local-only skills become a warning, never a prompt. `--yes` short-circuits prompts in all cases. Defaults: skip (no push, no delete). Push lands in Plan D.

5. **Doctor's "Description in first person" warning is implemented but lenient.** Per spec it's a style warning. We flag if `description` starts with a first-person pronoun (`I `, `I'm`, `I can`, `me`, `my `) at sentence start, case-insensitive. False positives possible; that's why it's a warning not a fail.

6. **Doctor does not check project `.skills.toml` shas.** Spec lists this under "Warn"; defer to Plan D where `.skills.toml` actually exists.

7. **Doctor exits 1 on warns as well as fails, matching spec.** Spec line 231 reads "exit 0 if all pass, exit 1 if any warn/fail". The SessionStart hook (Plan E) swallows exit codes via `|| true`, so warns are still non-blocking in practice — but the exit-code contract matches the spec literally. Quiet mode surfaces a single line for the first finding regardless of severity.

8. **`skill-sync list` ignores `--scope`.** Spec's CLI surface shows `list [--scope user|project|all]`. Plan C does not implement the flag because there is no project scope yet — `.skills.toml` snapshots land in Plan D. Listing without the flag covers everything that exists today. The flag is added when project scope is real.

9. **`agents/openai.yaml` sidecar is not consulted for platforms detection.** Spec architecture (lines 47–50) shows it as the Codex-side sidecar. None of the current 5 skills carry one, so Plan C's platforms detection looks only at `subagents/claude/` and `subagents/codex/`. If a future skill ships `agents/openai.yaml` with `disable: true` or similar, extend `_platforms` then.

---

## File Structure

```
~/skill-repo/
├── pyproject.toml                       # MODIFY: add pyyaml dep
├── src/skillsync/
│   ├── cli.py                           # MODIFY: add 4 subparsers, dispatch
│   ├── frontmatter.py                   # CREATE: parse YAML frontmatter
│   ├── index_cmd.py                     # CREATE: build index.json
│   ├── list_cmd.py                      # CREATE: scan + print rows
│   ├── search_cmd.py                    # CREATE: load index + score
│   ├── doctor.py                        # CREATE: run check table
│   └── sync_cmd.py                      # CREATE: reconcile + regen index
└── tests/
    ├── test_frontmatter.py              # CREATE
    ├── test_index_cmd.py                # CREATE
    ├── test_list_cmd.py                 # CREATE
    ├── test_search_cmd.py               # CREATE
    ├── test_doctor.py                   # CREATE
    └── test_sync_cmd.py                 # CREATE
```

No live filesystem effects outside the repo (Plan C is read + index-write only). The existing user-level symlinks placed by Plan B continue working unchanged.

---

## Task 1: Add `pyyaml` dependency

**Files:**
- Modify: `~/skill-repo/pyproject.toml`

- [ ] **Step 1: Add `pyyaml` to dependencies**

Open `pyproject.toml`. Change the `dependencies` block to:

```toml
dependencies = [
    "requests>=2.31",
    "markdownify>=0.11",
    "pyyaml>=6.0",
]
```

- [ ] **Step 2: Sync the lockfile**

```bash
cd ~/skill-repo
uv sync
```

Expected: lockfile updates; `pyyaml` resolves to ~6.0.x.

- [ ] **Step 3: Verify import**

```bash
cd ~/skill-repo
uv run python -c "import yaml; print(yaml.__version__)"
```

Expected: prints a version ≥ 6.0.

- [ ] **Step 4: Commit**

```bash
cd ~/skill-repo
git add pyproject.toml uv.lock
git commit -m "build: add pyyaml dependency for frontmatter parsing"
```

---

## Task 2: Frontmatter parser — failing tests

**Files:**
- Create: `~/skill-repo/tests/test_frontmatter.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for skillsync.frontmatter."""
from __future__ import annotations

import pytest

from skillsync import frontmatter


def test_parse_returns_empty_when_no_frontmatter():
    body = "# Just a heading\n\nNo frontmatter here.\n"
    fm, rest = frontmatter.parse(body)
    assert fm == {}
    assert rest == body


def test_parse_extracts_simple_keys():
    body = "---\nname: foo\ndescription: A short skill.\n---\n# Body\n"
    fm, rest = frontmatter.parse(body)
    assert fm == {"name": "foo", "description": "A short skill."}
    assert rest == "# Body\n"


def test_parse_handles_quoted_string_with_backticks():
    body = (
        "---\n"
        "name: video\n"
        'description: "Use when editing `intent: video` pages."\n'
        "---\n"
        "Body."
    )
    fm, _ = frontmatter.parse(body)
    assert fm["description"] == "Use when editing `intent: video` pages."


def test_parse_handles_block_scalar_description():
    body = (
        "---\n"
        "name: x\n"
        "description: |\n"
        "  Line one.\n"
        "  Line two.\n"
        "---\n"
        "Body."
    )
    fm, _ = frontmatter.parse(body)
    assert fm["description"] == "Line one.\nLine two.\n"


def test_parse_tolerates_bom():
    body = "﻿---\nname: bom\ndescription: B\n---\nbody\n"
    fm, rest = frontmatter.parse(body)
    assert fm["name"] == "bom"
    assert rest == "body\n"


def test_parse_returns_empty_on_malformed_yaml():
    """Malformed YAML between fences -> empty dict, full body returned. Doctor will flag it."""
    body = "---\nname: x\ndescription: : :\n---\nbody\n"
    fm, rest = frontmatter.parse(body)
    assert fm == {}
    assert rest == body  # caller can see something went wrong


def test_parse_preserves_unknown_keys():
    body = (
        "---\n"
        "name: foo\n"
        "description: d\n"
        "context: fork\n"
        "allowed-tools: [Read, Bash]\n"
        "---\n"
    )
    fm, _ = frontmatter.parse(body)
    assert fm["context"] == "fork"
    assert fm["allowed-tools"] == ["Read", "Bash"]
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd ~/skill-repo
uv run pytest tests/test_frontmatter.py -v
```

Expected: `ImportError: cannot import name 'frontmatter'`.

---

## Task 3: Frontmatter parser — implementation

**Files:**
- Create: `~/skill-repo/src/skillsync/frontmatter.py`

- [ ] **Step 1: Implement parser**

```python
"""Parse YAML frontmatter from SKILL.md files.

Returns (frontmatter_dict, body_string). Frontmatter is the block delimited by
`---` fences at the top of the file. On any parse failure (no fences, malformed
YAML), returns ({}, original_body) so callers can decide how to surface the
problem — `doctor` will flag empty frontmatter as a fail.
"""
from __future__ import annotations

from typing import Any

import yaml


def parse(body: str) -> tuple[dict[str, Any], str]:
    """Split `body` into (frontmatter_dict, remainder)."""
    if body.startswith("﻿"):
        body = body[1:]

    if not body.startswith("---"):
        return {}, body

    lines = body.splitlines(keepends=True)
    if not lines or lines[0].rstrip() != "---":
        return {}, body

    end = None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            end = i
            break
    if end is None:
        return {}, body

    fm_text = "".join(lines[1:end])
    rest = "".join(lines[end + 1 :])
    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return {}, body

    if not isinstance(data, dict):
        return {}, body
    return data, rest
```

- [ ] **Step 2: Run — expect all 7 pass**

```bash
cd ~/skill-repo
uv run pytest tests/test_frontmatter.py -v
```

Expected: 7 passed.

- [ ] **Step 3: Commit**

```bash
cd ~/skill-repo
git add src/skillsync/frontmatter.py tests/test_frontmatter.py
git commit -m "feat(frontmatter): YAML parser shared by index/doctor/list/sync"
```

---

## Task 4: Index builder — failing tests

**Files:**
- Create: `~/skill-repo/tests/test_index_cmd.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for skillsync.index_cmd."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillsync import index_cmd


def _write_skill(repo_skills: Path, name: str, frontmatter: str, body: str = "") -> None:
    d = repo_skills / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\n{frontmatter}---\n{body}")


@pytest.fixture
def repo_with_skills(tmp_path):
    repo_skills = tmp_path / "skills"
    repo_skills.mkdir()
    _write_skill(
        repo_skills, "alpha",
        "name: alpha\ndescription: First skill.\n",
        "Alpha body line one.\nAlpha body line two.\n",
    )
    _write_skill(
        repo_skills, "beta",
        "name: beta\ndescription: Second skill.\nwhen_to_use: When testing.\n",
        "Beta body.\n",
    )
    return repo_skills


def test_build_index_writes_entry_per_skill(repo_with_skills, tmp_path):
    index_path = tmp_path / "index.json"
    written = index_cmd.build(repo_skills_dir=repo_with_skills, index_path=index_path)
    assert sorted(written) == ["alpha", "beta"]
    data = json.loads(index_path.read_text())
    assert "generated_at" in data
    names = [e["name"] for e in data["skills"]]
    assert names == ["alpha", "beta"]


def test_build_index_extracts_description_and_when_to_use(repo_with_skills, tmp_path):
    index_path = tmp_path / "index.json"
    index_cmd.build(repo_skills_dir=repo_with_skills, index_path=index_path)
    data = json.loads(index_path.read_text())
    by_name = {e["name"]: e for e in data["skills"]}
    assert by_name["alpha"]["description"] == "First skill."
    assert by_name["alpha"]["when_to_use"] is None
    assert by_name["beta"]["when_to_use"] == "When testing."


def test_build_index_captures_body_metadata(repo_with_skills, tmp_path):
    index_path = tmp_path / "index.json"
    index_cmd.build(repo_skills_dir=repo_with_skills, index_path=index_path)
    data = json.loads(index_path.read_text())
    by_name = {e["name"]: e for e in data["skills"]}
    assert by_name["alpha"]["body_lines"] == 2
    assert "Alpha body line one" in by_name["alpha"]["body_excerpt"]


def test_build_index_records_platforms_both_when_no_sidecars(repo_with_skills, tmp_path):
    index_path = tmp_path / "index.json"
    index_cmd.build(repo_skills_dir=repo_with_skills, index_path=index_path)
    data = json.loads(index_path.read_text())
    assert all(set(e["platforms"]) == {"claude", "codex"} for e in data["skills"])


def test_build_index_records_claude_only_when_codex_sidecar_missing(repo_with_skills, tmp_path):
    """A skill with subagents/claude/x.md but no subagents/codex/x.toml is claude-only."""
    sub_dir = repo_with_skills / "alpha" / "subagents" / "claude"
    sub_dir.mkdir(parents=True)
    (sub_dir / "alpha.md").write_text("---\nname: alpha\n---\nclaude subagent\n")

    index_path = tmp_path / "index.json"
    index_cmd.build(repo_skills_dir=repo_with_skills, index_path=index_path)
    data = json.loads(index_path.read_text())
    by_name = {e["name"]: e for e in data["skills"]}
    assert by_name["alpha"]["platforms"] == ["claude"]


def test_build_index_skips_dotted_dirs(tmp_path):
    repo_skills = tmp_path / "skills"
    repo_skills.mkdir()
    _write_skill(repo_skills, "real", "name: real\ndescription: R\n", "")
    (repo_skills / ".hidden").mkdir()
    (repo_skills / ".hidden" / "SKILL.md").write_text("---\nname: hidden\n---\n")
    index_path = tmp_path / "index.json"
    index_cmd.build(repo_skills_dir=repo_skills, index_path=index_path)
    data = json.loads(index_path.read_text())
    assert [e["name"] for e in data["skills"]] == ["real"]


def test_build_index_skips_dirs_without_skill_md(tmp_path):
    repo_skills = tmp_path / "skills"
    repo_skills.mkdir()
    (repo_skills / "empty").mkdir()  # no SKILL.md
    _write_skill(repo_skills, "real", "name: real\ndescription: R\n", "")
    index_path = tmp_path / "index.json"
    index_cmd.build(repo_skills_dir=repo_skills, index_path=index_path)
    data = json.loads(index_path.read_text())
    assert [e["name"] for e in data["skills"]] == ["real"]


def test_build_index_writes_atomically(tmp_path):
    """Index file is written via tempfile + rename — no partial writes on crash."""
    repo_skills = tmp_path / "skills"
    repo_skills.mkdir()
    _write_skill(repo_skills, "alpha", "name: alpha\ndescription: A\n", "")
    index_path = tmp_path / "index.json"
    index_path.write_text("{ stale }")  # pre-existing junk
    index_cmd.build(repo_skills_dir=repo_skills, index_path=index_path)
    # Should now be valid JSON.
    json.loads(index_path.read_text())
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd ~/skill-repo
uv run pytest tests/test_index_cmd.py -v
```

Expected: `ImportError: cannot import name 'index_cmd'`.

---

## Task 5: Index builder — implementation

**Files:**
- Create: `~/skill-repo/src/skillsync/index_cmd.py`

- [ ] **Step 1: Implement builder**

```python
"""Build ~/skill-repo/index.json from skills/.

Each entry: {name, description, when_to_use, body_excerpt, body_lines,
platforms, frontmatter_keys}. Written atomically (tempfile + os.replace).
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from skillsync.frontmatter import parse as parse_frontmatter
from skillsync.paths import REPO_ROOT, SKILLS_DIR

INDEX_PATH = REPO_ROOT / "index.json"
EXCERPT_CHARS = 400


def _platforms(skill_dir: Path) -> list[str]:
    """Return ['claude', 'codex'], ['claude'], or ['codex'] based on subagent sidecars."""
    has_claude_subs = (skill_dir / "subagents" / "claude").is_dir() and any(
        (skill_dir / "subagents" / "claude").iterdir()
    )
    has_codex_subs = (skill_dir / "subagents" / "codex").is_dir() and any(
        (skill_dir / "subagents" / "codex").iterdir()
    )
    if has_claude_subs and not has_codex_subs:
        return ["claude"]
    if has_codex_subs and not has_claude_subs:
        return ["codex"]
    return ["claude", "codex"]


def _entry(skill_dir: Path) -> dict | None:
    """Build a single index entry; return None if no SKILL.md."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return None
    body = skill_md.read_text()
    fm, rest = parse_frontmatter(body)
    return {
        "name": skill_dir.name,
        "description": fm.get("description"),
        "when_to_use": fm.get("when_to_use"),
        "body_excerpt": rest.strip()[:EXCERPT_CHARS],
        "body_lines": len([ln for ln in rest.splitlines() if ln.strip()]),
        "platforms": _platforms(skill_dir),
        "frontmatter_keys": sorted(fm.keys()),
    }


def build(
    repo_skills_dir: Path = SKILLS_DIR,
    index_path: Path = INDEX_PATH,
) -> list[str]:
    """Build index.json. Returns names written, in sort order."""
    entries: list[dict] = []
    for child in sorted(repo_skills_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            continue
        entry = _entry(child)
        if entry is not None:
            entries.append(entry)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "skills": entries,
    }
    text = json.dumps(payload, indent=2, sort_keys=False)

    index_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".index.", suffix=".tmp", dir=str(index_path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, index_path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise

    return [e["name"] for e in entries]


def is_stale(repo_skills_dir: Path = SKILLS_DIR, index_path: Path = INDEX_PATH) -> bool:
    """True if index.json is missing or older than any SKILL.md."""
    if not index_path.exists():
        return True
    idx_mtime = index_path.stat().st_mtime
    for child in repo_skills_dir.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        skill_md = child / "SKILL.md"
        if skill_md.exists() and skill_md.stat().st_mtime > idx_mtime:
            return True
    return False
```

- [ ] **Step 2: Run — expect all 8 pass**

```bash
cd ~/skill-repo
uv run pytest tests/test_index_cmd.py -v
```

Expected: 8 passed.

- [ ] **Step 3: Commit**

```bash
cd ~/skill-repo
git add src/skillsync/index_cmd.py tests/test_index_cmd.py
git commit -m "feat(index): build index.json with descriptions + platforms"
```

---

## Task 6: `list` command — failing tests

**Files:**
- Create: `~/skill-repo/tests/test_list_cmd.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for skillsync.list_cmd."""
from __future__ import annotations

from pathlib import Path

import pytest

from skillsync import list_cmd


def _make_skill(repo: Path, name: str) -> Path:
    d = repo / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n")
    return d


@pytest.fixture
def world(tmp_path):
    """Build a repo + claude + codex + an extra local-only skill in claude."""
    repo = tmp_path / "repo_skills"
    claude = tmp_path / "claude_skills"
    codex = tmp_path / "codex_skills"
    repo.mkdir()
    claude.mkdir()
    codex.mkdir()

    alpha = _make_skill(repo, "alpha")
    beta = _make_skill(repo, "beta")
    (claude / "alpha").symlink_to(alpha, target_is_directory=True)
    (codex / "alpha").symlink_to(alpha, target_is_directory=True)
    (claude / "beta").symlink_to(beta, target_is_directory=True)
    # beta has no codex symlink (drift case).

    # Local-only skill at claude scope, not in repo.
    local = claude / "gamma"
    local.mkdir()
    (local / "SKILL.md").write_text("---\nname: gamma\ndescription: local\n---\n")

    return repo, claude, codex


def test_collect_lists_every_known_name(world):
    repo, claude, codex = world
    rows = list_cmd.collect(repo_skills_dir=repo, claude_dir=claude, codex_dir=codex)
    names = sorted(r["name"] for r in rows)
    assert names == ["alpha", "beta", "gamma"]


def test_collect_marks_synced_when_both_symlinks_point_at_repo(world):
    repo, claude, codex = world
    rows = {r["name"]: r for r in list_cmd.collect(
        repo_skills_dir=repo, claude_dir=claude, codex_dir=codex
    )}
    assert rows["alpha"]["claude"] == "symlink"
    assert rows["alpha"]["codex"] == "symlink"
    assert rows["alpha"]["in_repo"] is True


def test_collect_flags_missing_codex_symlink(world):
    repo, claude, codex = world
    rows = {r["name"]: r for r in list_cmd.collect(
        repo_skills_dir=repo, claude_dir=claude, codex_dir=codex
    )}
    assert rows["beta"]["claude"] == "symlink"
    assert rows["beta"]["codex"] == "missing"
    assert rows["beta"]["in_repo"] is True


def test_collect_flags_local_only(world):
    repo, claude, codex = world
    rows = {r["name"]: r for r in list_cmd.collect(
        repo_skills_dir=repo, claude_dir=claude, codex_dir=codex
    )}
    assert rows["gamma"]["in_repo"] is False
    assert rows["gamma"]["claude"] == "real"
    assert rows["gamma"]["codex"] == "missing"


def test_collect_flags_broken_symlink(tmp_path):
    repo = tmp_path / "repo_skills"
    claude = tmp_path / "claude_skills"
    codex = tmp_path / "codex_skills"
    repo.mkdir()
    claude.mkdir()
    codex.mkdir()
    alpha = _make_skill(repo, "alpha")
    (claude / "alpha").symlink_to(alpha, target_is_directory=True)
    # Break the link by removing the target.
    import shutil
    shutil.rmtree(alpha)

    rows = {r["name"]: r for r in list_cmd.collect(
        repo_skills_dir=repo, claude_dir=claude, codex_dir=codex
    )}
    # Repo entry now gone, but the dangling symlink should still surface.
    assert rows["alpha"]["claude"] == "broken"
    assert rows["alpha"]["in_repo"] is False


def test_run_prints_table_and_exits_zero(world, capsys):
    repo, claude, codex = world
    code = list_cmd.run(repo_skills_dir=repo, claude_dir=claude, codex_dir=codex)
    out = capsys.readouterr().out
    assert "alpha" in out
    assert "beta" in out
    assert "gamma" in out
    assert code == 0
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd ~/skill-repo
uv run pytest tests/test_list_cmd.py -v
```

---

## Task 7: `list` command — implementation

**Files:**
- Create: `~/skill-repo/src/skillsync/list_cmd.py`

- [ ] **Step 1: Implement**

```python
"""skill-sync list: scan user-level dirs + repo, print a status row per skill."""
from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict

from skillsync.paths import (
    CLAUDE_USER_SKILLS_DIR,
    CODEX_USER_SKILLS_DIR,
    SKILLS_DIR,
)

LinkStatus = Literal["symlink", "real", "missing", "broken"]


class Row(TypedDict):
    name: str
    in_repo: bool
    claude: LinkStatus
    codex: LinkStatus


def _status_at(target_dir: Path, name: str, repo_skills_dir: Path) -> LinkStatus:
    entry = target_dir / name
    if not entry.exists() and not entry.is_symlink():
        return "missing"
    if entry.is_symlink():
        try:
            resolved = entry.resolve(strict=True)
        except (OSError, RuntimeError):
            return "broken"
        try:
            resolved.relative_to(repo_skills_dir.resolve())
            return "symlink"
        except ValueError:
            return "real"  # symlink points outside repo
    return "real"


def collect(
    repo_skills_dir: Path = SKILLS_DIR,
    claude_dir: Path = CLAUDE_USER_SKILLS_DIR,
    codex_dir: Path = CODEX_USER_SKILLS_DIR,
) -> list[Row]:
    """Build one row per known skill name across all three dirs."""
    names: set[str] = set()

    if repo_skills_dir.is_dir():
        for c in repo_skills_dir.iterdir():
            if c.is_dir() and not c.name.startswith("."):
                names.add(c.name)

    for d in (claude_dir, codex_dir):
        if not d.is_dir():
            continue
        for c in d.iterdir():
            if c.name.startswith("."):
                continue
            # Include dangling symlinks (is_symlink True, exists False).
            if c.exists() or c.is_symlink():
                names.add(c.name)

    rows: list[Row] = []
    for name in sorted(names):
        in_repo = (repo_skills_dir / name).is_dir()
        rows.append(Row(
            name=name,
            in_repo=in_repo,
            claude=_status_at(claude_dir, name, repo_skills_dir),
            codex=_status_at(codex_dir, name, repo_skills_dir),
        ))
    return rows


def _fmt_row(row: Row) -> str:
    repo_mark = "✓" if row["in_repo"] else " "
    return f"  [{repo_mark}] {row['name']:<30} claude={row['claude']:<8} codex={row['codex']}"


def run(
    repo_skills_dir: Path = SKILLS_DIR,
    claude_dir: Path = CLAUDE_USER_SKILLS_DIR,
    codex_dir: Path = CODEX_USER_SKILLS_DIR,
) -> int:
    rows = collect(repo_skills_dir=repo_skills_dir, claude_dir=claude_dir, codex_dir=codex_dir)
    if not rows:
        print("(no skills found)")
        return 0
    print(f"  {'in-repo':<5} {'name':<30} {'claude':<14} {'codex'}")
    for row in rows:
        print(_fmt_row(row))
    return 0
```

- [ ] **Step 2: Run — expect 6 pass**

```bash
cd ~/skill-repo
uv run pytest tests/test_list_cmd.py -v
```

- [ ] **Step 3: Commit**

```bash
cd ~/skill-repo
git add src/skillsync/list_cmd.py tests/test_list_cmd.py
git commit -m "feat(list): one-row-per-skill status across repo/claude/codex"
```

---

## Task 8: `search` command — failing tests

**Files:**
- Create: `~/skill-repo/tests/test_search_cmd.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for skillsync.search_cmd."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillsync import index_cmd, search_cmd


@pytest.fixture
def indexed_repo(tmp_path):
    repo = tmp_path / "skills"
    repo.mkdir()
    for name, desc, body in [
        ("render-video", "Render a video using ffmpeg.", "Build a video timeline."),
        ("fish-audio", "Use FishAudio TTS to synthesize narration.", "Calls fish.audio."),
        ("commit-stuff", "Make git commits.", "Stage and commit changes."),
    ]:
        d = repo / name
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n{body}\n")
    index_path = tmp_path / "index.json"
    index_cmd.build(repo_skills_dir=repo, index_path=index_path)
    return repo, index_path


def test_score_weights_name_higher_than_description(indexed_repo):
    _repo, index_path = indexed_repo
    results = search_cmd.score(query="fish", index_path=index_path)
    assert results[0]["name"] == "fish-audio"


def test_score_falls_back_to_description_match(indexed_repo):
    _repo, index_path = indexed_repo
    results = search_cmd.score(query="ffmpeg", index_path=index_path)
    assert results[0]["name"] == "render-video"


def test_score_returns_empty_when_no_match(indexed_repo):
    _repo, index_path = indexed_repo
    results = search_cmd.score(query="kubernetes", index_path=index_path)
    assert results == []


def test_score_is_case_insensitive(indexed_repo):
    _repo, index_path = indexed_repo
    results = search_cmd.score(query="FISH", index_path=index_path)
    assert results[0]["name"] == "fish-audio"


def test_score_respects_top_n(indexed_repo):
    """Multi-token query that matches all 3 entries — top_n caps output."""
    _repo, index_path = indexed_repo
    results = search_cmd.score(query="video audio commit", index_path=index_path, top_n=2)
    assert len(results) == 2


def test_run_prints_and_returns_zero(indexed_repo, capsys):
    repo, index_path = indexed_repo
    code = search_cmd.run(query="fish", repo_skills_dir=repo, index_path=index_path)
    out = capsys.readouterr().out
    assert "fish-audio" in out
    assert code == 0


def test_run_returns_one_when_no_results(indexed_repo, capsys):
    repo, index_path = indexed_repo
    code = search_cmd.run(query="kubernetes", repo_skills_dir=repo, index_path=index_path)
    out = capsys.readouterr().out
    assert "no match" in out.lower() or "no result" in out.lower()
    assert code == 1


def test_run_rebuilds_stale_index(tmp_path, capsys):
    """If index is missing, search should rebuild it before scoring."""
    repo = tmp_path / "skills"
    repo.mkdir()
    d = repo / "alpha"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: alpha\ndescription: Alpha skill.\n---\n")
    index_path = tmp_path / "index.json"
    # index_path does not exist yet.
    code = search_cmd.run(query="alpha", repo_skills_dir=repo, index_path=index_path)
    assert code == 0
    assert index_path.exists()
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd ~/skill-repo
uv run pytest tests/test_search_cmd.py -v
```

---

## Task 9: `search` command — implementation

**Files:**
- Create: `~/skill-repo/src/skillsync/search_cmd.py`

- [ ] **Step 1: Implement**

```python
"""skill-sync search: score index entries against a query, print top matches."""
from __future__ import annotations

import json
import re
from pathlib import Path

from skillsync import index_cmd
from skillsync.index_cmd import INDEX_PATH
from skillsync.paths import SKILLS_DIR

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _entry_score(entry: dict, q_tokens: list[str]) -> int:
    """Weighted token-overlap. 3x name, 2x description+when_to_use, 1x body_excerpt."""
    name_tokens = _tokens(entry["name"])
    desc_tokens = _tokens((entry.get("description") or "") + " " + (entry.get("when_to_use") or ""))
    body_tokens = _tokens(entry.get("body_excerpt") or "")
    score = 0
    for tok in q_tokens:
        for n in name_tokens:
            if tok in n:
                score += 3
        for d in desc_tokens:
            if tok in d:
                score += 2
        for b in body_tokens:
            if tok in b:
                score += 1
    return score


def score(query: str, index_path: Path = INDEX_PATH, top_n: int = 5) -> list[dict]:
    """Rank index entries against `query`. Returns top_n entries (with `_score` added) or []."""
    if not index_path.exists():
        return []
    q_tokens = _tokens(query)
    if not q_tokens:
        return []
    data = json.loads(index_path.read_text())
    scored = []
    for entry in data.get("skills", []):
        s = _entry_score(entry, q_tokens)
        if s > 0:
            e = dict(entry)
            e["_score"] = s
            scored.append(e)
    scored.sort(key=lambda e: (-e["_score"], e["name"]))
    return scored[:top_n]


def _fmt(entry: dict) -> str:
    desc = (entry.get("description") or "").strip().replace("\n", " ")
    if len(desc) > 120:
        desc = desc[:117] + "..."
    return f"  [{entry['_score']:>3}] {entry['name']:<28} {desc}"


def run(
    query: str,
    repo_skills_dir: Path = SKILLS_DIR,
    index_path: Path = INDEX_PATH,
    top_n: int = 5,
) -> int:
    if index_cmd.is_stale(repo_skills_dir=repo_skills_dir, index_path=index_path):
        index_cmd.build(repo_skills_dir=repo_skills_dir, index_path=index_path)
    results = score(query=query, index_path=index_path, top_n=top_n)
    if not results:
        print(f"  no match for: {query}")
        return 1
    for r in results:
        print(_fmt(r))
    return 0
```

- [ ] **Step 2: Run — expect 8 pass**

```bash
cd ~/skill-repo
uv run pytest tests/test_search_cmd.py -v
```

- [ ] **Step 3: Commit**

```bash
cd ~/skill-repo
git add src/skillsync/search_cmd.py tests/test_search_cmd.py
git commit -m "feat(search): weighted token-overlap over index.json"
```

---

## Task 10: `doctor` — failing tests

**Files:**
- Create: `~/skill-repo/tests/test_doctor.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for skillsync.doctor."""
from __future__ import annotations

from pathlib import Path

import pytest

from skillsync import doctor


def _make_skill(repo: Path, name: str, frontmatter: str, body: str = "") -> Path:
    d = repo / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\n{frontmatter}---\n{body}")
    return d


@pytest.fixture
def healthy_repo(tmp_path):
    repo = tmp_path / "skills"
    repo.mkdir()
    _make_skill(repo, "alpha", "name: alpha\ndescription: A short description.\n", "body\n")
    claude = tmp_path / "claude"
    codex = tmp_path / "codex"
    claude.mkdir()
    codex.mkdir()
    target = repo / "alpha"
    (claude / "alpha").symlink_to(target, target_is_directory=True)
    (codex / "alpha").symlink_to(target, target_is_directory=True)
    return repo, claude, codex


def test_check_all_green_on_healthy_repo(healthy_repo):
    repo, claude, codex = healthy_repo
    findings = doctor.check(repo_skills_dir=repo, claude_dir=claude, codex_dir=codex)
    fails = [f for f in findings if f["severity"] == "fail"]
    assert fails == []


def test_check_fails_on_broken_symlink(healthy_repo, tmp_path):
    repo, claude, codex = healthy_repo
    import shutil
    shutil.rmtree(repo / "alpha")
    findings = doctor.check(repo_skills_dir=repo, claude_dir=claude, codex_dir=codex)
    # The pre-existing symlinks now dangle.
    assert any(f["severity"] == "fail" and "broken" in f["message"].lower() for f in findings)


def test_check_fails_on_empty_frontmatter(tmp_path):
    repo = tmp_path / "skills"
    repo.mkdir()
    d = repo / "bad"
    d.mkdir()
    (d / "SKILL.md").write_text("no frontmatter at all\n")
    findings = doctor.check(
        repo_skills_dir=repo, claude_dir=tmp_path / "c", codex_dir=tmp_path / "x",
    )
    assert any(
        f["severity"] == "fail" and "frontmatter" in f["message"].lower() and f["name"] == "bad"
        for f in findings
    )


def test_check_fails_on_name_with_claude_substring(tmp_path):
    repo = tmp_path / "skills"
    repo.mkdir()
    _make_skill(repo, "my-claude-helper", "name: my-claude-helper\ndescription: x\n")
    findings = doctor.check(
        repo_skills_dir=repo, claude_dir=tmp_path / "c", codex_dir=tmp_path / "x",
    )
    assert any(f["severity"] == "fail" and "claude" in f["message"].lower() for f in findings)


def test_check_fails_on_description_over_1024_chars(tmp_path):
    repo = tmp_path / "skills"
    repo.mkdir()
    huge = "x" * 1100
    _make_skill(repo, "fat", f"name: fat\ndescription: {huge}\n")
    findings = doctor.check(
        repo_skills_dir=repo, claude_dir=tmp_path / "c", codex_dir=tmp_path / "x",
    )
    assert any(f["severity"] == "fail" and "1024" in f["message"] for f in findings)


def test_check_fails_on_description_plus_when_to_use_over_1536(tmp_path):
    repo = tmp_path / "skills"
    repo.mkdir()
    desc = "x" * 1000
    wtu = "y" * 600
    _make_skill(repo, "combo", f"name: combo\ndescription: {desc}\nwhen_to_use: {wtu}\n")
    findings = doctor.check(
        repo_skills_dir=repo, claude_dir=tmp_path / "c", codex_dir=tmp_path / "x",
    )
    assert any(f["severity"] == "fail" and "1536" in f["message"] for f in findings)


def test_check_warns_on_long_body(tmp_path):
    repo = tmp_path / "skills"
    repo.mkdir()
    body = "\n".join(f"line {i}" for i in range(600))
    _make_skill(repo, "long", "name: long\ndescription: d\n", body + "\n")
    findings = doctor.check(
        repo_skills_dir=repo, claude_dir=tmp_path / "c", codex_dir=tmp_path / "x",
    )
    assert any(f["severity"] == "warn" and "500" in f["message"] for f in findings)


def test_check_warns_on_missing_subagent_for_agent_key(tmp_path):
    repo = tmp_path / "skills"
    repo.mkdir()
    _make_skill(
        repo, "orchestrate",
        "name: orchestrate\ndescription: d\nagent: research-bot\n",
    )
    findings = doctor.check(
        repo_skills_dir=repo, claude_dir=tmp_path / "c", codex_dir=tmp_path / "x",
    )
    assert any(
        f["severity"] == "warn" and "subagent" in f["message"].lower()
        for f in findings
    )


def test_check_warns_on_first_person_description(tmp_path):
    repo = tmp_path / "skills"
    repo.mkdir()
    _make_skill(repo, "i-skill", "name: i-skill\ndescription: I help you commit code.\n")
    findings = doctor.check(
        repo_skills_dir=repo, claude_dir=tmp_path / "c", codex_dir=tmp_path / "x",
    )
    assert any(
        f["severity"] == "warn" and "first person" in f["message"].lower()
        for f in findings
    )


def test_run_quiet_silent_on_success(healthy_repo, capsys):
    repo, claude, codex = healthy_repo
    code = doctor.run(quiet=True, repo_skills_dir=repo, claude_dir=claude, codex_dir=codex)
    out = capsys.readouterr().out
    assert out == ""
    assert code == 0


def test_run_returns_one_on_warns_only(tmp_path, capsys):
    """Per spec: exit 1 if any warn/fail. Warn-only repos must still exit 1."""
    repo = tmp_path / "skills"
    repo.mkdir()
    body = "\n".join(f"line {i}" for i in range(600))
    _make_skill(repo, "long", "name: long\ndescription: d\n", body + "\n")
    code = doctor.run(
        quiet=False, repo_skills_dir=repo, claude_dir=tmp_path / "c", codex_dir=tmp_path / "x",
    )
    out = capsys.readouterr().out
    assert "WARN" in out
    assert code == 1


def test_run_quiet_one_line_on_warns_only(tmp_path, capsys):
    repo = tmp_path / "skills"
    repo.mkdir()
    body = "\n".join(f"line {i}" for i in range(600))
    _make_skill(repo, "long", "name: long\ndescription: d\n", body + "\n")
    code = doctor.run(
        quiet=True, repo_skills_dir=repo, claude_dir=tmp_path / "c", codex_dir=tmp_path / "x",
    )
    out = capsys.readouterr().out
    assert out.count("\n") <= 1
    assert "warn" in out.lower()
    assert code == 1


def test_run_quiet_one_line_on_failure(tmp_path, capsys):
    repo = tmp_path / "skills"
    repo.mkdir()
    d = repo / "bad"
    d.mkdir()
    (d / "SKILL.md").write_text("no frontmatter\n")
    code = doctor.run(
        quiet=True, repo_skills_dir=repo, claude_dir=tmp_path / "c", codex_dir=tmp_path / "x",
    )
    out = capsys.readouterr().out
    # Quiet mode: one short line only.
    assert out.count("\n") <= 1
    assert code == 1


def test_run_verbose_prints_all_findings(tmp_path, capsys):
    repo = tmp_path / "skills"
    repo.mkdir()
    d = repo / "bad"
    d.mkdir()
    (d / "SKILL.md").write_text("no frontmatter\n")
    code = doctor.run(
        quiet=False, repo_skills_dir=repo, claude_dir=tmp_path / "c", codex_dir=tmp_path / "x",
    )
    out = capsys.readouterr().out
    assert "bad" in out
    assert "frontmatter" in out
    assert code == 1
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd ~/skill-repo
uv run pytest tests/test_doctor.py -v
```

---

## Task 11: `doctor` — implementation

**Files:**
- Create: `~/skill-repo/src/skillsync/doctor.py`

- [ ] **Step 1: Implement**

```python
"""skill-sync doctor: validate symlinks, frontmatter shapes, body sizes.

Returns exit 0 if no fail-severity findings; 1 otherwise. `--quiet` suppresses
success output and reduces failures to a single line, suitable for SessionStart
hook use (`skill-sync doctor --quiet || true`).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, TypedDict

from skillsync.frontmatter import parse as parse_frontmatter
from skillsync.paths import (
    CLAUDE_USER_SKILLS_DIR,
    CODEX_USER_SKILLS_DIR,
    SKILLS_DIR,
)


Severity = Literal["fail", "warn"]


class Finding(TypedDict):
    severity: Severity
    name: str
    message: str


_NAME_RE = re.compile(r"^[a-z0-9-]{1,64}$")
_FIRST_PERSON_RE = re.compile(r"^(i|i'm|i'll|i can|me|my)\b", re.IGNORECASE)
_BAD_NAME_SUBSTRINGS = ("anthropic", "claude")


def _check_skill(skill_dir: Path) -> list[Finding]:
    name = skill_dir.name
    findings: list[Finding] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        findings.append(Finding(
            severity="fail", name=name, message=f"missing SKILL.md in {skill_dir}",
        ))
        return findings

    body = skill_md.read_text()
    fm, rest = parse_frontmatter(body)
    if not fm:
        findings.append(Finding(
            severity="fail", name=name,
            message="invalid or empty frontmatter (could not parse YAML between --- fences)",
        ))
        return findings

    fm_name = fm.get("name")
    if not isinstance(fm_name, str) or not _NAME_RE.match(fm_name):
        findings.append(Finding(
            severity="fail", name=name,
            message=f"frontmatter `name` invalid: {fm_name!r} (must match [a-z0-9-]{{1,64}})",
        ))
    else:
        for sub in _BAD_NAME_SUBSTRINGS:
            if sub in fm_name.lower():
                findings.append(Finding(
                    severity="fail", name=name,
                    message=f"`name` contains forbidden substring '{sub}'",
                ))

    desc = fm.get("description")
    if not isinstance(desc, str) or not desc.strip():
        findings.append(Finding(
            severity="fail", name=name, message="frontmatter `description` is missing or empty",
        ))
        desc_len = 0
    else:
        desc_len = len(desc)
        if desc_len > 1024:
            findings.append(Finding(
                severity="fail", name=name,
                message=f"`description` exceeds 1024 chars ({desc_len})",
            ))
        if _FIRST_PERSON_RE.match(desc.strip()):
            findings.append(Finding(
                severity="warn", name=name,
                message="`description` starts in first person — prefer third-person ('Use when...')",
            ))

    wtu = fm.get("when_to_use") or ""
    if isinstance(wtu, str) and (desc_len + len(wtu)) > 1536:
        findings.append(Finding(
            severity="fail", name=name,
            message=f"`description` + `when_to_use` combined exceeds 1536 chars "
                    f"({desc_len + len(wtu)})",
        ))

    body_lines = sum(1 for _ in rest.splitlines())
    if body_lines > 500:
        findings.append(Finding(
            severity="warn", name=name, message=f"body exceeds 500 lines ({body_lines})",
        ))

    if "agent" in fm:
        agent_name = fm["agent"]
        sub_path = skill_dir / "subagents" / "claude" / f"{agent_name}.md"
        if not sub_path.is_file():
            findings.append(Finding(
                severity="warn", name=name,
                message=f"frontmatter `agent: {agent_name}` but no subagent file at {sub_path}",
            ))

    return findings


def _check_symlinks(
    target_dir: Path,
    target_label: str,
    repo_skills_dir: Path,
) -> list[Finding]:
    findings: list[Finding] = []
    if not target_dir.is_dir():
        return findings
    repo_resolved = repo_skills_dir.resolve()
    for entry in sorted(target_dir.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_symlink():
            try:
                resolved = entry.resolve(strict=True)
            except (OSError, RuntimeError):
                findings.append(Finding(
                    severity="fail", name=entry.name,
                    message=f"broken symlink at {target_label}/{entry.name}",
                ))
                continue
            try:
                resolved.relative_to(repo_resolved)
            except ValueError:
                findings.append(Finding(
                    severity="warn", name=entry.name,
                    message=f"{target_label}/{entry.name} symlinks outside the repo ({resolved})",
                ))
    return findings


def _check_duplicate_names(repo_skills_dir: Path) -> list[Finding]:
    """Names from frontmatter that disagree with the directory name → potential duplicate."""
    findings: list[Finding] = []
    seen: dict[str, str] = {}
    for child in sorted(repo_skills_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            continue
        fm, _ = parse_frontmatter(skill_md.read_text())
        fm_name = fm.get("name") if isinstance(fm.get("name"), str) else None
        if fm_name and fm_name in seen and seen[fm_name] != child.name:
            findings.append(Finding(
                severity="fail", name=fm_name,
                message=f"duplicate `name: {fm_name}` in {child.name} (also in {seen[fm_name]})",
            ))
        elif fm_name:
            seen[fm_name] = child.name
    return findings


def check(
    repo_skills_dir: Path = SKILLS_DIR,
    claude_dir: Path = CLAUDE_USER_SKILLS_DIR,
    codex_dir: Path = CODEX_USER_SKILLS_DIR,
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
    return findings


def _fmt(finding: Finding) -> str:
    badge = "FAIL" if finding["severity"] == "fail" else "WARN"
    return f"  [{badge}] {finding['name']:<25} {finding['message']}"


def run(
    quiet: bool = False,
    repo_skills_dir: Path = SKILLS_DIR,
    claude_dir: Path = CLAUDE_USER_SKILLS_DIR,
    codex_dir: Path = CODEX_USER_SKILLS_DIR,
) -> int:
    findings = check(
        repo_skills_dir=repo_skills_dir, claude_dir=claude_dir, codex_dir=codex_dir,
    )
    fails = [f for f in findings if f["severity"] == "fail"]
    warns = [f for f in findings if f["severity"] == "warn"]

    if quiet:
        if fails:
            first = fails[0]
            print(f"skill-sync doctor: {len(fails)} fail(s); first: {first['name']} — {first['message']}")
            return 1
        if warns:
            first = warns[0]
            print(f"skill-sync doctor: {len(warns)} warn(s); first: {first['name']} — {first['message']}")
            return 1
        return 0

    if not findings:
        print("skill-sync doctor: all checks passed.")
        return 0
    for f in findings:
        print(_fmt(f))
    print(f"\n{len(fails)} fail, {len(warns)} warn")
    return 1
```

- [ ] **Step 2: Run — expect 14 pass**

```bash
cd ~/skill-repo
uv run pytest tests/test_doctor.py -v
```

- [ ] **Step 3: Commit**

```bash
cd ~/skill-repo
git add src/skillsync/doctor.py tests/test_doctor.py
git commit -m "feat(doctor): symlink + frontmatter + body-size checks with quiet mode"
```

---

## Task 12: `sync` command — failing tests

**Files:**
- Create: `~/skill-repo/tests/test_sync_cmd.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for skillsync.sync_cmd."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillsync import sync_cmd


def _make_skill(repo: Path, name: str) -> Path:
    d = repo / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n")
    return d


@pytest.fixture
def world(tmp_path):
    repo = tmp_path / "repo_skills"
    claude = tmp_path / "claude_skills"
    codex = tmp_path / "codex_skills"
    repo.mkdir()
    claude.mkdir()
    codex.mkdir()
    alpha = _make_skill(repo, "alpha")
    _make_skill(repo, "beta")  # in repo but unlinked anywhere
    (claude / "alpha").symlink_to(alpha, target_is_directory=True)
    (codex / "alpha").symlink_to(alpha, target_is_directory=True)
    index_path = tmp_path / "index.json"
    return repo, claude, codex, index_path


def test_run_heals_missing_repo_symlinks(world, capsys):
    repo, claude, codex, index_path = world
    code = sync_cmd.run(
        repo_skills_dir=repo, claude_dir=claude, codex_dir=codex, index_path=index_path,
        yes=True,
    )
    assert (claude / "beta").is_symlink()
    assert (codex / "beta").is_symlink()
    assert code == 0


def test_run_regenerates_index(world):
    repo, claude, codex, index_path = world
    sync_cmd.run(
        repo_skills_dir=repo, claude_dir=claude, codex_dir=codex, index_path=index_path,
        yes=True,
    )
    assert index_path.exists()
    data = json.loads(index_path.read_text())
    names = sorted(e["name"] for e in data["skills"])
    assert names == ["alpha", "beta"]


def test_run_reports_local_only_skills(world, capsys):
    repo, claude, codex, index_path = world
    # Create a local-only skill in claude (real dir, not in repo).
    local = claude / "gamma"
    local.mkdir()
    (local / "SKILL.md").write_text("---\nname: gamma\ndescription: local\n---\n")

    code = sync_cmd.run(
        repo_skills_dir=repo, claude_dir=claude, codex_dir=codex, index_path=index_path,
        yes=True,
    )
    out = capsys.readouterr().out
    assert "gamma" in out
    assert "local-only" in out.lower() or "not in repo" in out.lower()
    assert code == 0  # local-only is informational, not failure


def test_run_does_not_prompt_when_yes(world, capsys, monkeypatch):
    """With --yes, never call input()."""
    repo, claude, codex, index_path = world
    local = claude / "gamma"
    local.mkdir()
    (local / "SKILL.md").write_text("---\nname: gamma\ndescription: local\n---\n")

    def _no_input(*_a, **_kw):
        raise AssertionError("input() should not be called when yes=True")
    monkeypatch.setattr("builtins.input", _no_input)

    code = sync_cmd.run(
        repo_skills_dir=repo, claude_dir=claude, codex_dir=codex, index_path=index_path,
        yes=True,
    )
    assert code == 0


def test_run_does_not_prompt_when_stdin_not_tty(world, monkeypatch):
    repo, claude, codex, index_path = world
    local = claude / "gamma"
    local.mkdir()
    (local / "SKILL.md").write_text("---\nname: gamma\ndescription: local\n---\n")

    def _no_input(*_a, **_kw):
        raise AssertionError("input() should not be called when stdin is not a tty")
    monkeypatch.setattr("builtins.input", _no_input)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    code = sync_cmd.run(
        repo_skills_dir=repo, claude_dir=claude, codex_dir=codex, index_path=index_path,
        yes=False,
    )
    assert code == 0
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd ~/skill-repo
uv run pytest tests/test_sync_cmd.py -v
```

---

## Task 13: `sync` command — implementation

**Files:**
- Create: `~/skill-repo/src/skillsync/sync_cmd.py`

- [ ] **Step 1: Implement**

```python
"""skill-sync sync: heal symlinks, regen index, report local-only skills.

Plan C scope is user-level only. Project `.skills.toml` reconciliation lives
in Plan D, where snapshots actually exist.
"""
from __future__ import annotations

import sys
from pathlib import Path

from skillsync import index_cmd, init_cmd, list_cmd
from skillsync.index_cmd import INDEX_PATH
from skillsync.paths import (
    CLAUDE_USER_SKILLS_DIR,
    CODEX_USER_SKILLS_DIR,
    SKILLS_DIR,
)


def _heal_symlinks(
    repo_skills_dir: Path, claude_dir: Path, codex_dir: Path,
) -> tuple[list[str], list[str]]:
    """Add any missing per-skill symlinks. Returns (claude_added, codex_added)."""
    claude_before = {p.name for p in claude_dir.iterdir() if p.is_symlink() or p.exists()} if claude_dir.is_dir() else set()
    codex_before = {p.name for p in codex_dir.iterdir() if p.is_symlink() or p.exists()} if codex_dir.is_dir() else set()
    init_cmd.wire_symlinks(repo_skills_dir=repo_skills_dir, target_dir=claude_dir)
    init_cmd.wire_symlinks(repo_skills_dir=repo_skills_dir, target_dir=codex_dir)
    claude_after = {p.name for p in claude_dir.iterdir() if p.is_symlink()} if claude_dir.is_dir() else set()
    codex_after = {p.name for p in codex_dir.iterdir() if p.is_symlink()} if codex_dir.is_dir() else set()
    return sorted(claude_after - claude_before), sorted(codex_after - codex_before)


def run(
    yes: bool = False,
    repo_skills_dir: Path = SKILLS_DIR,
    claude_dir: Path = CLAUDE_USER_SKILLS_DIR,
    codex_dir: Path = CODEX_USER_SKILLS_DIR,
    index_path: Path = INDEX_PATH,
) -> int:
    print("Healing per-skill symlinks…", flush=True)
    claude_added, codex_added = _heal_symlinks(repo_skills_dir, claude_dir, codex_dir)
    if claude_added:
        print(f"  added {len(claude_added)} symlink(s) in {claude_dir}: {', '.join(claude_added)}")
    if codex_added:
        print(f"  added {len(codex_added)} symlink(s) in {codex_dir}: {', '.join(codex_added)}")
    if not claude_added and not codex_added:
        print("  (none needed)")

    print("Regenerating index.json…", flush=True)
    names = index_cmd.build(repo_skills_dir=repo_skills_dir, index_path=index_path)
    print(f"  {len(names)} skill(s) indexed.")

    print("Scanning for local-only skills…", flush=True)
    rows = list_cmd.collect(
        repo_skills_dir=repo_skills_dir, claude_dir=claude_dir, codex_dir=codex_dir,
    )
    local_only = [r for r in rows if not r["in_repo"] and (r["claude"] == "real" or r["codex"] == "real")]
    if not local_only:
        print("  (none)")
        return 0

    interactive = (not yes) and sys.stdin.isatty()
    for row in local_only:
        msg = (
            f"  local-only: {row['name']} "
            f"(claude={row['claude']}, codex={row['codex']}) — not in repo. "
            f"Push support lands in Plan D."
        )
        print(msg)
        if interactive:
            try:
                input("    press enter to continue (push not yet implemented)… ")
            except EOFError:
                pass
    return 0
```

- [ ] **Step 2: Run — expect 5 pass**

```bash
cd ~/skill-repo
uv run pytest tests/test_sync_cmd.py -v
```

- [ ] **Step 3: Commit**

```bash
cd ~/skill-repo
git add src/skillsync/sync_cmd.py tests/test_sync_cmd.py
git commit -m "feat(sync): heal symlinks + regen index + report local-only"
```

---

## Task 14: CLI wiring + smoke tests

**Files:**
- Modify: `~/skill-repo/src/skillsync/cli.py`
- Modify: `~/skill-repo/tests/test_cli_smoke.py`

- [ ] **Step 1: Replace `cli.py` so all six subcommands are wired**

Open `src/skillsync/cli.py` and replace the entire file with:

```python
"""skill-sync CLI dispatch."""
import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skill-sync", description="Cross-agent skill management")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_knowledge = sub.add_parser("knowledge", help="Sync official skill/subagent docs")
    p_knowledge.add_argument("--force", action="store_true", help="Re-fetch even if sha matches")

    p_init = sub.add_parser("init", help="Wire user-level symlinks; optionally migrate existing skills")
    p_init.add_argument("--migrate", action="store_true",
                        help="Import existing skills from ~/.claude/skills/ and ~/.codex/skills/ first")
    p_init.add_argument("--yes", action="store_true",
                        help="Non-interactive; resolve conflicts via --keep (default: codex)")
    p_init.add_argument("--keep", choices=["claude", "codex"], default=None,
                        help="With --yes: which side wins on conflict")

    p_sync = sub.add_parser("sync", help="Heal symlinks, regenerate index, report local-only")
    p_sync.add_argument("--yes", action="store_true", help="Non-interactive")

    p_doctor = sub.add_parser("doctor", help="Run health checks on the skill catalog")
    p_doctor.add_argument("--quiet", action="store_true",
                          help="Silent on success; one line on first failure (for hooks)")

    p_search = sub.add_parser("search", help="Search skills by query")
    p_search.add_argument("query", help="Search terms (case-insensitive)")
    p_search.add_argument("--top-n", type=int, default=5, help="Max results (default 5)")

    sub.add_parser("list", help="List skills across repo / ~/.claude / ~/.codex")

    args = parser.parse_args(argv)

    if args.cmd == "knowledge":
        from skillsync.knowledge import run
        return run(force=args.force)

    if args.cmd == "init":
        from skillsync.init_cmd import run as init_run
        return init_run(migrate_flag=args.migrate, yes=args.yes, keep=args.keep)

    if args.cmd == "sync":
        from skillsync.sync_cmd import run as sync_run
        return sync_run(yes=args.yes)

    if args.cmd == "doctor":
        from skillsync.doctor import run as doctor_run
        return doctor_run(quiet=args.quiet)

    if args.cmd == "search":
        from skillsync.search_cmd import run as search_run
        return search_run(query=args.query, top_n=args.top_n)

    if args.cmd == "list":
        from skillsync.list_cmd import run as list_run
        return list_run()

    raise AssertionError(f"unreachable: argparse should have rejected {args.cmd!r}")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Extend the CLI smoke test**

Open `tests/test_cli_smoke.py` and replace the assertions section with:

```python
def test_cli_help_lists_subcommands():
    """`python -m skillsync --help` exits 0 and mentions every registered subcommand."""
    result = subprocess.run(
        [sys.executable, "-m", "skillsync", "--help"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout + result.stderr
    for name in ("knowledge", "init", "sync", "doctor", "search", "list"):
        assert name in out, f"missing subcommand in help: {name}"


def test_cli_doctor_quiet_runs_on_real_repo():
    """`skill-sync doctor --quiet` exits 0 or 1 (never crashes) against the real repo."""
    result = subprocess.run(
        [sys.executable, "-m", "skillsync", "doctor", "--quiet"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode in (0, 1), result.stderr


def test_cli_list_runs_on_real_repo():
    result = subprocess.run(
        [sys.executable, "-m", "skillsync", "list"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 3: Run the full test suite**

```bash
cd ~/skill-repo
uv run pytest -v
```

Expected: every test green (Plan A's 24 + Plan B's tests + the new Plan C tests).

- [ ] **Step 4: Verify CLI from PATH**

```bash
cd /tmp
skill-sync --help
skill-sync list
skill-sync doctor
skill-sync search video
```

Expected:
- `--help` lists all 6 subcommands.
- `list` shows the 5 skills currently in `~/skill-repo/skills/`, each marked `[✓]` with `claude=symlink codex=symlink`.
- `doctor` prints either "all checks passed" (exit 0) or per-finding rows ending with "N fail, M warn" (exit 1). Per spec, warns also produce exit 1.
- `search video` returns at least `generate-video` and `video-intent-authoring`.

If `doctor` returns any FAIL severity, halt and reconcile before proceeding to Task 15 — the existing skills should be free of fails. Warns (e.g. body > 500 lines) are acceptable and just need to be noted.

- [ ] **Step 5: Commit**

```bash
cd ~/skill-repo
git add src/skillsync/cli.py tests/test_cli_smoke.py
git commit -m "feat(cli): wire sync/doctor/search/list subcommands"
```

---

## Task 15: Final integration check + push

**Files:** none new.

- [ ] **Step 1: Run doctor on the live repo, confirm no fails**

```bash
cd ~/skill-repo
skill-sync doctor; echo "exit=$?"
```

Expected: zero fails. Exit code is 0 if also no warns, or 1 if any warns (the spec exits 1 on warn|fail). If FAIL severity appears in the output, halt and reconcile.

- [ ] **Step 2: Run sync, confirm idempotency**

```bash
cd ~/skill-repo
skill-sync sync
skill-sync sync
```

Expected: both runs say "(none needed)" for symlinks and produce identical index.json output.

- [ ] **Step 3: Spot-check search**

```bash
skill-sync search "check git status before new task"
skill-sync search video
skill-sync search fishaudio
```

Expected:
- First query returns `checkpoint-commit` near the top.
- Second returns the two video-related skills.
- Third returns "no match" (no fish-audio skill yet — confirms negative case).

- [ ] **Step 4: Push to GitHub**

```bash
cd ~/skill-repo
git log --oneline | head -10
git push origin master
```

Expected: all Plan C commits visible on remote.

- [ ] **Step 5: Final summary to operator**

Report:
- Total commits landed by Plan C (expected ~7: one per task that touched code).
- Doctor output on live repo (any persistent warns).
- Index.json entry count and the two highest-scoring search results for representative queries.
- Whether `pyyaml` made it into `uv.lock`.
- Open follow-ups for Plan D (push / install / move / .skills.toml) and Plan E (SessionStart hook + project onboarding).

---

## Self-review checklist

**Spec coverage (Plan C scope only):**
- ✅ `skill-sync sync` — heal symlinks, regen index, report local-only (Plan C scope)
- ✅ `skill-sync doctor` + `--quiet` — full check table from spec, minus project `.skills.toml` drift
- ✅ `skill-sync search` — weighted token-overlap on index.json
- ✅ `skill-sync list` — one-row-per-skill across repo/claude/codex
- ✅ `index.json` generation — description + when_to_use + body_excerpt + platforms
- ✅ Atomic writes (tempfile + os.replace) for `index.json`
- ✅ `pyyaml` dependency added (Task 1) with lockfile updated
- ⏭️ Project `.skills.toml` reconciliation in `sync` — Plan D
- ⏭️ Project `.skills.toml` sha-drift check in `doctor` — Plan D
- ⏭️ `push` / `install` / `move` — Plan D
- ⏭️ SessionStart hook + project onboarding via CLAUDE.md — Plan E

**Placeholders:** none. Every step has concrete commands and code blocks.

**Type consistency (used identically across modules and tests):**
- `frontmatter.parse(body)` → `tuple[dict[str, Any], str]`
- `index_cmd.build(repo_skills_dir, index_path)` → `list[str]` (names written)
- `index_cmd.is_stale(repo_skills_dir, index_path)` → `bool`
- `index_cmd.INDEX_PATH` — module-level `Path` constant
- `list_cmd.Row` TypedDict (`name`, `in_repo`, `claude`, `codex`)
- `list_cmd.collect(...)` → `list[Row]`
- `list_cmd.run(...)` → `int`
- `search_cmd.score(query, index_path, top_n)` → `list[dict]` (entries with `_score` key)
- `search_cmd.run(query, repo_skills_dir, index_path, top_n)` → `int`
- `doctor.Finding` TypedDict (`severity`, `name`, `message`)
- `doctor.check(repo_skills_dir, claude_dir, codex_dir)` → `list[Finding]`
- `doctor.run(quiet, repo_skills_dir, claude_dir, codex_dir)` → `int`
- `sync_cmd.run(yes, repo_skills_dir, claude_dir, codex_dir, index_path)` → `int`

**Known risks:**
1. **`pyyaml` install can fail offline.** `uv sync` needs network access on first run. If the implementer is offline, halt; do not hand-roll YAML.
2. **First-person regex is approximate.** "Initialize the storyboard…" starts with "Init" which doesn't match — good. But "I/O bound tasks…" would match (`I` boundary). Acceptable warn-only false-positive rate; revisit if it fires on real skills.
3. **`platforms` detection is structural-only.** It does not parse `agents/openai.yaml` content or check `context: fork` keys. Deliberate — see Design decision #2.
4. **`is_stale` uses mtime, which can be unstable across filesystems.** On the operator's local ext4 disk this is fine. If `~/skill-repo/` ever lives on a network mount, swap to sha comparison.
5. **`sync` heals symlinks unconditionally.** If a `~/.claude/skills/<name>` is a real file/dir (not a symlink), `wire_symlinks` already raises `FileExistsError` — the operator must run `init --migrate` first. `sync` does not auto-import. That's intentional: surface the conflict, don't auto-resolve it.
6. **`is_stale` does not detect deletions.** If a skill is removed from `~/skill-repo/skills/`, the stale entry stays in `index.json` until `sync` runs again. `sync` rebuilds wholesale so this only affects `search` between `sync` invocations. Acceptable for the natural-language UX; if it ever bites, swap `is_stale` to compare the index's name set against the repo's.

---

## Execution next steps

After Plan C completes:
- **Plan D** — `push` / `install` / `move` + project-scope `.skills.toml` flow. Adds:
  - Local-only skills now have a one-command upload (`skill-sync push <name>`).
  - Doctor grows the project `.skills.toml` sha-drift check.
  - Sync grows project-scope reconciliation.
  - Optionally migrates `content-creation/skills/` (16 plugin-marketplace skills) into the repo.
- **Plan E** — SessionStart hook (`skill-sync doctor --quiet || true`) + `CLAUDE.md` / `AGENTS.md` `skill-repo:` declaration that triggers per-project onboarding. Smallest of the three remaining phases.

Plan A followups #6 (knowledge.py per-site preprocessing) and #7 (split `fetch_one` to avoid mtime churn) remain deferred. Re-evaluate after Plan C lands and the operator starts running `skill-sync knowledge` regularly — if the markdown noise is real, fold them into Plan D as small chores.
