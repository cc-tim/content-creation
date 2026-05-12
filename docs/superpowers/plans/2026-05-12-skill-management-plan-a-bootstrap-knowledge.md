# Skill Management — Plan A: Repo Bootstrap + Knowledge Sync

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up `~/skill-repo/` with Python `skill-sync` CLI scaffolding and a working `skill-sync knowledge` command that fetches the 7 official skill/subagent docs into local markdown.

**Architecture:** New local git repo at `~/skill-repo/` containing a Python package `skillsync` and a `skill-sync` CLI entry point. First implemented subcommand is `knowledge`: reads URL list from `KNOWLEDGE/_urls.txt`, fetches each URL, converts HTML to markdown, sha256-pins, skips unchanged on re-runs.

**Tech Stack:**
- Python 3.11+ (system has `tomllib` in stdlib)
- `uv` for venv + package install (already on system; project uses it elsewhere)
- `markdownify` for HTML→markdown
- `requests` for HTTP (simpler than urllib for our needs)
- `pytest` for tests

**Reference spec:** `content-creation/docs/superpowers/specs/2026-05-12-skill-management-design.md`

---

## File Structure (after Plan A completes)

```
~/skill-repo/
├── .git/
├── .gitignore
├── README.md
├── pyproject.toml
├── KNOWLEDGE/
│   ├── _urls.txt                       # 7 default URLs, one per line
│   └── _last-sync.json                 # generated after first run
├── skills/                             # empty for now
│   └── .gitkeep
├── docs/
│   └── design-spec.md                  # copy of the design spec
├── bin/
│   └── skill-sync                      # shebang dispatcher → uv run
└── src/
│   └── skillsync/
│       ├── __init__.py
│       ├── __main__.py                 # python -m skillsync entry
│       ├── cli.py                      # argparse dispatch
│       ├── paths.py                    # repo root, KNOWLEDGE dir
│       └── knowledge.py                # fetch + convert + write
└── tests/
    ├── __init__.py
    └── test_knowledge.py

~/.local/bin/skill-sync → ~/skill-repo/bin/skill-sync   # PATH symlink
```

---

## Task 1: Initialize repo skeleton

**Files:**
- Create: `~/skill-repo/.gitignore`
- Create: `~/skill-repo/README.md`
- Create: `~/skill-repo/pyproject.toml`
- Create: `~/skill-repo/KNOWLEDGE/_urls.txt`
- Create: `~/skill-repo/skills/.gitkeep`
- Create: `~/skill-repo/docs/design-spec.md` (copied from content-creation)

- [ ] **Step 1: Make the repo directory and `git init`**

```bash
mkdir -p ~/skill-repo/{KNOWLEDGE,skills,docs,bin,src/skillsync,tests}
cd ~/skill-repo && git init -b main
```

Expected: "Initialized empty Git repository in /home/tim-huang/skill-repo/.git/"

- [ ] **Step 2: Write `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
*.egg-info/
.coverage
```

- [ ] **Step 3: Write `README.md`**

```markdown
# skill-repo

Cross-agent (Claude Code + Codex CLI) skill management. Flat catalog of user-authored skills; symlinked into both agents' user-level skill dirs; project-level installs via `.skills.toml` manifest.

See `docs/design-spec.md` for full architecture.

## Quickstart

```bash
~/skill-repo/bin/skill-sync knowledge       # fetch official skill docs
~/skill-repo/bin/skill-sync --help
```

## Layout

- `skills/` — flat catalog, one dir per skill, each with `SKILL.md`
- `KNOWLEDGE/` — synced official docs (re-runnable)
- `src/skillsync/` — Python package
- `bin/skill-sync` — CLI entry
```

- [ ] **Step 4: Write `pyproject.toml`**

```toml
[project]
name = "skillsync"
version = "0.1.0"
description = "Cross-agent skill management CLI"
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31",
    "markdownify>=0.11",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
skill-sync = "skillsync.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/skillsync"]
```

- [ ] **Step 5: Write `KNOWLEDGE/_urls.txt`**

```
https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
https://code.claude.com/docs/en/skills
https://code.claude.com/docs/en/agents
https://code.claude.com/docs/en/agent-teams
https://developers.openai.com/codex/skills
https://developers.openai.com/codex/subagents
```

- [ ] **Step 6: Touch `skills/.gitkeep`**

```bash
touch ~/skill-repo/skills/.gitkeep
```

- [ ] **Step 7: Copy the design spec into the repo**

```bash
cp /home/tim-huang/content-creation/docs/superpowers/specs/2026-05-12-skill-management-design.md ~/skill-repo/docs/design-spec.md
```

- [ ] **Step 8: Initial commit**

```bash
cd ~/skill-repo
git add .gitignore README.md pyproject.toml KNOWLEDGE/_urls.txt skills/.gitkeep docs/design-spec.md
git commit -m "chore: scaffold skill-repo with design spec and URL list"
```

Expected: commit with 6 files.

---

## Task 2: Python package skeleton + CLI scaffold

**Files:**
- Create: `~/skill-repo/src/skillsync/__init__.py`
- Create: `~/skill-repo/src/skillsync/__main__.py`
- Create: `~/skill-repo/src/skillsync/paths.py`
- Create: `~/skill-repo/src/skillsync/cli.py`
- Create: `~/skill-repo/bin/skill-sync`
- Create: `~/skill-repo/tests/__init__.py`

- [ ] **Step 1: Empty `src/skillsync/__init__.py`**

```python
"""skillsync — cross-agent skill management."""
__version__ = "0.1.0"
```

- [ ] **Step 2: Write `src/skillsync/paths.py`**

```python
"""Filesystem path constants for skill-repo."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = REPO_ROOT / "KNOWLEDGE"
SKILLS_DIR = REPO_ROOT / "skills"
URLS_FILE = KNOWLEDGE_DIR / "_urls.txt"
LAST_SYNC_FILE = KNOWLEDGE_DIR / "_last-sync.json"
```

- [ ] **Step 3: Write `src/skillsync/cli.py` (stub for `knowledge` subcommand)**

```python
"""skill-sync CLI dispatch."""
import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skill-sync", description="Cross-agent skill management")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_knowledge = sub.add_parser("knowledge", help="Sync official skill/subagent docs")
    p_knowledge.add_argument("--force", action="store_true", help="Re-fetch even if sha matches")

    args = parser.parse_args(argv)

    if args.cmd == "knowledge":
        from skillsync.knowledge import run
        return run(force=args.force)

    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Write `src/skillsync/__main__.py`**

```python
"""Enable `python -m skillsync`."""
from skillsync.cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Write `bin/skill-sync` shebang dispatcher**

```bash
#!/usr/bin/env bash
# bin/skill-sync — entry point for skill-sync CLI
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
exec uv run python -m skillsync "$@"
```

- [ ] **Step 6: Make it executable**

```bash
chmod +x ~/skill-repo/bin/skill-sync
```

- [ ] **Step 7: Empty `tests/__init__.py`**

```bash
touch ~/skill-repo/tests/__init__.py
```

- [ ] **Step 8: Bootstrap venv and verify CLI runs**

```bash
cd ~/skill-repo
uv sync --extra dev
~/skill-repo/bin/skill-sync --help
```

Expected: argparse usage message listing the `knowledge` subcommand. (`knowledge.py` doesn't exist yet, so a real `knowledge` invocation will ImportError — that's fine for this task.)

- [ ] **Step 9: Commit**

```bash
cd ~/skill-repo
git add src/ bin/skill-sync tests/__init__.py uv.lock
git commit -m "feat(cli): scaffold skill-sync CLI with knowledge subcommand stub"
```

---

## Task 3: Knowledge fetcher — failing test first

**Files:**
- Create: `~/skill-repo/tests/test_knowledge.py`

- [ ] **Step 1: Write failing test for `fetch_one`**

```python
"""Tests for skillsync.knowledge."""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from skillsync import knowledge


@pytest.fixture
def tmp_knowledge_dir(tmp_path, monkeypatch):
    """Redirect knowledge module to a tmp dir."""
    urls_file = tmp_path / "_urls.txt"
    urls_file.write_text("https://example.com/docs/skills\n")
    last_sync = tmp_path / "_last-sync.json"
    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", tmp_path)
    monkeypatch.setattr(knowledge, "URLS_FILE", urls_file)
    monkeypatch.setattr(knowledge, "LAST_SYNC_FILE", last_sync)
    return tmp_path


def test_fetch_one_writes_markdown(tmp_knowledge_dir):
    html = "<html><body><h1>Hello</h1><p>World</p></body></html>"
    with patch("skillsync.knowledge.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, text=html, raise_for_status=lambda: None)
        sha = knowledge.fetch_one("https://example.com/docs/skills")

    out = tmp_knowledge_dir / "example-com-docs-skills.md"
    assert out.exists()
    content = out.read_text()
    assert "# Hello" in content
    assert "World" in content
    assert isinstance(sha, str) and len(sha) == 64  # sha256 hex


def test_fetch_one_deterministic_sha(tmp_knowledge_dir):
    """fetch_one returns the same sha for identical content across calls."""
    html = "<html><body><h1>Same</h1></body></html>"
    url = "https://example.com/docs/skills"
    with patch("skillsync.knowledge.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, text=html, raise_for_status=lambda: None)
        sha1 = knowledge.fetch_one(url)
        sha2 = knowledge.fetch_one(url)
    assert sha2 == sha1


def test_run_skips_unchanged_urls(tmp_knowledge_dir):
    """Second invocation of run() with matching sha records the same fetched_at as the first."""
    urls = tmp_knowledge_dir / "_urls.txt"
    urls.write_text("https://a.example/x\n")
    html = "<h1>Stable</h1>"
    with patch("skillsync.knowledge.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, text=html, raise_for_status=lambda: None)
        rc1 = knowledge.run(force=False)
        first = json.loads((tmp_knowledge_dir / "_last-sync.json").read_text())
        first_fetched_at = first["https://a.example/x"]["fetched_at"]

        rc2 = knowledge.run(force=False)
        second = json.loads((tmp_knowledge_dir / "_last-sync.json").read_text())

    assert rc1 == 0 and rc2 == 0
    # sha unchanged across runs (same content)
    assert second["https://a.example/x"]["sha"] == first["https://a.example/x"]["sha"]
    # fetched_at unchanged on second run because sha matched — that's the skip signature
    assert second["https://a.example/x"]["fetched_at"] == first_fetched_at


def test_run_writes_files_for_each_url(tmp_knowledge_dir):
    urls = tmp_knowledge_dir / "_urls.txt"
    urls.write_text("https://a.example/x\nhttps://b.example/y\n")
    html_for = {"https://a.example/x": "<h1>A</h1>", "https://b.example/y": "<h1>B</h1>"}

    def fake_get(url, timeout=None):
        return MagicMock(status_code=200, text=html_for[url], raise_for_status=lambda: None)

    with patch("skillsync.knowledge.requests.get", side_effect=fake_get):
        rc = knowledge.run(force=False)

    assert rc == 0
    assert (tmp_knowledge_dir / "a-example-x.md").exists()
    assert (tmp_knowledge_dir / "b-example-y.md").exists()
    last = json.loads((tmp_knowledge_dir / "_last-sync.json").read_text())
    assert set(last.keys()) == {"https://a.example/x", "https://b.example/y"}
    for v in last.values():
        assert "sha" in v and "fetched_at" in v
```

- [ ] **Step 2: Run the test — expect ImportError or AttributeError**

```bash
cd ~/skill-repo
uv run pytest tests/test_knowledge.py -v
```

Expected: ImportError on `from skillsync import knowledge` (file doesn't exist yet).

---

## Task 4: Knowledge fetcher — implementation

**Files:**
- Create: `~/skill-repo/src/skillsync/knowledge.py`

- [ ] **Step 1: Implement `knowledge.py`**

```python
"""Sync official skill/subagent docs into KNOWLEDGE/."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from markdownify import markdownify as md_convert

from skillsync.paths import KNOWLEDGE_DIR, URLS_FILE, LAST_SYNC_FILE


def url_to_filename(url: str) -> str:
    """Convert a URL to a stable filename: example.com/docs/skills -> example-com-docs-skills.md"""
    parsed = urlparse(url)
    raw = parsed.netloc + parsed.path
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", raw).strip("-").lower()
    return f"{slug}.md"


def fetch_one(url: str, timeout: int = 30) -> str:
    """Fetch URL, convert to markdown, write to KNOWLEDGE_DIR. Returns sha256 of markdown."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    md_text = md_convert(resp.text, heading_style="ATX")
    out_path = KNOWLEDGE_DIR / url_to_filename(url)
    out_path.write_text(md_text)
    sha = hashlib.sha256(md_text.encode("utf-8")).hexdigest()
    return sha


def read_last_sync() -> dict[str, dict[str, str]]:
    if not LAST_SYNC_FILE.exists():
        return {}
    return json.loads(LAST_SYNC_FILE.read_text())


def write_last_sync(data: dict[str, dict[str, str]]) -> None:
    LAST_SYNC_FILE.write_text(json.dumps(data, indent=2, sort_keys=True))


def read_urls() -> list[str]:
    if not URLS_FILE.exists():
        return []
    return [line.strip() for line in URLS_FILE.read_text().splitlines() if line.strip() and not line.startswith("#")]


def run(force: bool = False) -> int:
    """Sync all URLs in KNOWLEDGE/_urls.txt. Returns exit code."""
    urls = read_urls()
    if not urls:
        print(f"No URLs in {URLS_FILE}", flush=True)
        return 1

    last = read_last_sync()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_state: dict[str, dict[str, str]] = {}
    changed = 0
    skipped = 0
    failed = 0

    for url in urls:
        try:
            sha = fetch_one(url)
        except Exception as e:
            print(f"FAIL {url}: {e}", flush=True)
            failed += 1
            if url in last:
                new_state[url] = last[url]
            continue

        prev_sha = last.get(url, {}).get("sha")
        if prev_sha == sha and not force:
            skipped += 1
            new_state[url] = last[url]
        else:
            changed += 1
            new_state[url] = {"sha": sha, "fetched_at": now}
            print(f"OK   {url}", flush=True)

    write_last_sync(new_state)
    print(f"\nDone. changed={changed} skipped={skipped} failed={failed}", flush=True)
    return 0 if failed == 0 else 1
```

- [ ] **Step 2: Run tests — expect pass**

```bash
cd ~/skill-repo
uv run pytest tests/test_knowledge.py -v
```

Expected: 3 tests pass.

- [ ] **Step 3: Commit**

```bash
cd ~/skill-repo
git add src/skillsync/knowledge.py tests/test_knowledge.py
git commit -m "feat(knowledge): fetch official skill docs into KNOWLEDGE/"
```

---

## Task 5: End-to-end run against real URLs

**Files:** none new — exercising the existing code.

- [ ] **Step 1: Run knowledge sync against the real 7 URLs**

```bash
cd ~/skill-repo
~/skill-repo/bin/skill-sync knowledge
```

Expected: 7 "OK" lines, then summary "Done. changed=7 skipped=0 failed=0".

- [ ] **Step 2: Verify output**

```bash
ls -la ~/skill-repo/KNOWLEDGE/
```

Expected: 7 `.md` files plus `_urls.txt` and `_last-sync.json`.

- [ ] **Step 3: Spot-check one markdown file**

```bash
head -40 ~/skill-repo/KNOWLEDGE/code-claude-com-docs-en-skills.md
```

Expected: readable markdown with headings like `# Skills`, sections about skill format, etc.

If markdownify output is severely garbled (e.g., nav menus dominate, code blocks broken), capture a specific URL that fails and report — we may need to add a preprocessing step to strip nav/footer elements (out of scope for Plan A; record as a Plan A followup).

- [ ] **Step 4: Re-run to verify skip behavior**

```bash
~/skill-repo/bin/skill-sync knowledge
```

Expected: "Done. changed=0 skipped=7 failed=0".

- [ ] **Step 5: Commit the fetched knowledge**

```bash
cd ~/skill-repo
git add KNOWLEDGE/
git commit -m "docs: seed KNOWLEDGE/ with official skill+subagent docs"
```

---

## Task 6: PATH symlink + final smoke test

**Files:**
- Create: `~/.local/bin/skill-sync` (symlink)

- [ ] **Step 1: Ensure `~/.local/bin` is on PATH**

```bash
echo "$PATH" | tr ':' '\n' | grep -F "$HOME/.local/bin" || echo "NOT ON PATH"
```

If "NOT ON PATH", add to shell profile (e.g., `~/.bashrc`): `export PATH="$HOME/.local/bin:$PATH"`. Source it: `source ~/.bashrc`.

- [ ] **Step 2: Create the symlink**

```bash
mkdir -p ~/.local/bin
ln -sf ~/skill-repo/bin/skill-sync ~/.local/bin/skill-sync
```

- [ ] **Step 3: Verify from any directory**

```bash
cd /tmp
skill-sync --help
```

Expected: argparse usage with `knowledge` subcommand listed.

- [ ] **Step 4: Verify knowledge subcommand runs**

```bash
cd /tmp
skill-sync knowledge
```

Expected: "Done. changed=0 skipped=7 failed=0".

- [ ] **Step 5: Verify pytest from anywhere**

```bash
cd ~/skill-repo
uv run pytest -v
```

Expected: 3 tests pass.

---

## Task 7: Plan A wrap-up

**Files:** none new.

- [ ] **Step 1: Verify git log shows clean progression**

```bash
cd ~/skill-repo
git log --oneline
```

Expected: 4 commits — scaffold, CLI scaffold, knowledge fetcher, knowledge seed.

- [ ] **Step 2: Check repo for stray files**

```bash
cd ~/skill-repo
git status
```

Expected: clean working tree (after committing uv.lock if it was generated and not yet committed).

- [ ] **Step 3: Report results to operator**

Write a 3-line summary to stdout:
- Number of fetched docs (should be 7).
- Total bytes in KNOWLEDGE/ (`du -sh ~/skill-repo/KNOWLEDGE/`).
- Any URLs that failed or produced poor markdown (for Plan A followups list).

- [ ] **Step 4: Optional — add GitHub remote**

If Tim has created a private GitHub repo:
```bash
cd ~/skill-repo
git remote add origin git@github.com:tim-huang/skill-repo.git
git push -u origin main
```

If no remote yet, skip this step. Plan B's init command will assume the remote exists; Tim must create it before Plan B execution.

---

## Self-review checklist (filled in by plan author)

**Spec coverage (Plan A scope only):**
- ✅ Repo skeleton (`Architecture` section)
- ✅ `KNOWLEDGE/` dir with `_urls.txt`, `_last-sync.json`, 7 markdown files
- ✅ `skill-sync` CLI entrypoint, registered on PATH via `~/.local/bin/`
- ✅ `skill-sync knowledge` command per `Knowledge sync` spec section
- ✅ Sha256-based skip-when-unchanged (per spec: "skips unchanged")
- ⏭️ Symlinks, migration, doctor, search, sync, push, install, move, hook, project onboarding — Plan B+

**Placeholders:** none. All steps have concrete commands/code.

**Type consistency:** `fetch_one`, `read_last_sync`, `write_last_sync`, `read_urls`, `run` — names used consistently between knowledge.py, tests, and cli.py.

**Known risks:**
- HTML→markdown quality varies by site. If `code.claude.com` or `developers.openai.com` ship heavy SPA scaffolding, raw HTML fetch may produce noise. If markdown is unusable, Plan A followup = swap to pandoc CLI or add per-site preprocessing.
- `uv run` adds ~200ms overhead per invocation. Acceptable for CLI tool; revisit if it becomes annoying.

---

## Execution next steps

After Plan A completes:
- Review fetched markdown quality. Decide whether to keep markdownify or upgrade.
- Re-read `KNOWLEDGE/code-claude-com-docs-en-skills.md` to confirm Codex skill paths (`~/.codex/skills/` vs `~/.agents/skills/`) — spec open question #3.
- Author Plan B: `skill-sync init` + user-level symlinks + `init --migrate` for existing skills.
