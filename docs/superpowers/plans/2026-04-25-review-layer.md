# Review Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the proofreader's overlay hallucination bug and add a storyteller agent that reviews narrative transitions with auto-apply for MINOR issues and interactive confirmation for MAJOR ones.

**Architecture:** Two independent changes sharing the same module pattern: `cli_proofread.py` gets a targeted fix to its input formatting and system prompt; `cli_storyteller.py` is a new module mirroring the proofreader structure with an added interactive confirmation path for MAJOR issues. Both are wired into the review gate in `cli.py`.

**Tech Stack:** Python, Typer, anthropic SDK (`claude-haiku-4-5-20251001`), pytest, Rich tables.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/pipeline/cli_proofread.py` | Modify | Fix overlay-detection in `_format_for_review` + soften system prompt |
| `src/pipeline/cli_storyteller.py` | Create | Full storyteller agent: format input, call Haiku, parse MINOR/MAJOR, apply/confirm |
| `src/pipeline/cli.py` | Modify | Register `storytell_app`; wire storyteller into both review gate paths |
| `tests/unit/test_cli_proofread.py` | Modify | Add no-overlay regression test |
| `tests/unit/test_cli_storyteller.py` | Create | Unit tests for parse, format, apply logic |

---

## Task 1: Proofreader — fix overlay hallucination

**Files:**
- Modify: `src/pipeline/cli_proofread.py`
- Test: `tests/unit/test_cli_proofread.py`

- [ ] **Step 1: Write the failing regression test**

Open `tests/unit/test_cli_proofread.py`. Find the existing test class or add at the end:

```python
def test_format_for_review_no_overlay_adds_notice(tmp_path):
    """When no scene has overlay text, the formatted string must contain the no-overlay notice."""
    import json
    from pipeline.cli_proofread import _format_for_review

    sb = {
        "version": 1,
        "format": "storyboard_v1",
        "target_duration_sec": 300,
        "aspect_ratio": "9:16",
        "theme": {},
        "scenes": [
            {"id": "s1", "section": "hook", "narration": "第一句旁白。",
             "narration_est_sec": 5, "facts_ref": [], "visual": {}, "overlay": {}, "pause_after_sec": 0.5},
            {"id": "s2", "section": "body", "narration": "第二句旁白。",
             "narration_est_sec": 5, "facts_ref": [], "visual": {}, "overlay": None, "pause_after_sec": 0.5},
        ],
    }
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(sb), encoding="utf-8")

    result = _format_for_review(p)
    assert "本腳本無 OVERLAY 文字" in result


def test_format_for_review_with_overlay_no_notice(tmp_path):
    """When at least one overlay exists, the no-overlay notice must NOT appear."""
    import json
    from pipeline.cli_proofread import _format_for_review

    sb = {
        "version": 1,
        "format": "storyboard_v1",
        "target_duration_sec": 300,
        "aspect_ratio": "9:16",
        "theme": {},
        "scenes": [
            {"id": "s1", "section": "hook", "narration": "旁白。",
             "narration_est_sec": 5, "facts_ref": [], "visual": {},
             "overlay": {"text": "標題文字"}, "pause_after_sec": 0.5},
        ],
    }
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(sb), encoding="utf-8")

    result = _format_for_review(p)
    assert "本腳本無 OVERLAY 文字" not in result
```

- [ ] **Step 2: Run to confirm both tests fail**

```bash
uv run pytest tests/unit/test_cli_proofread.py::test_format_for_review_no_overlay_adds_notice tests/unit/test_cli_proofread.py::test_format_for_review_with_overlay_no_notice -v
```

Expected: both FAIL (wrong return type or missing notice logic).

- [ ] **Step 3: Fix `_format_for_review` in `cli_proofread.py`**

Replace the existing `_format_for_review` function:

```python
def _format_for_review(storyboard_path: Path) -> str:
    from pipeline.storyboard import Storyboard
    sb = Storyboard.load(storyboard_path)
    lines = []
    has_overlay = False
    for s in sb.scenes:
        lines.append(f"[{s.id}] NARRATION: {s.narration}")
        if s.overlay:
            text = s.overlay.get("text", "")
            if text:
                has_overlay = True
                lines.append(f"[{s.id}] OVERLAY: {text}")
    if not has_overlay:
        lines.append("（本腳本無 OVERLAY 文字，請只審閱 NARRATION）")
    return "\n".join(lines)
```

- [ ] **Step 4: Soften the system prompt's OVERLAY priority line**

In `_SYSTEM_PROMPT`, change:

```python
# old
"""1. OVERLAY 標題（最重要）："""

# new
"""1. 如有 OVERLAY，審閱標題語法："""
```

Find the exact line (around line 28 of `cli_proofread.py`) and apply that one-word change.

- [ ] **Step 5: Run the two new tests — expect PASS**

```bash
uv run pytest tests/unit/test_cli_proofread.py::test_format_for_review_no_overlay_adds_notice tests/unit/test_cli_proofread.py::test_format_for_review_with_overlay_no_notice -v
```

Expected: both PASS.

- [ ] **Step 6: Run the full unit suite — no regressions**

```bash
uv run pytest tests/unit/ -q
```

Expected: all existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add src/pipeline/cli_proofread.py tests/unit/test_cli_proofread.py
git commit -m "fix(proofread): suppress overlay hallucination when no overlays exist"
```

---

## Task 2: Storyteller — parsing and formatting utilities

**Files:**
- Create: `src/pipeline/cli_storyteller.py` (scaffold only — no API call yet)
- Create: `tests/unit/test_cli_storyteller.py`

- [ ] **Step 1: Write failing tests for `_parse_storytell_issues` and `_format_for_storytell`**

Create `tests/unit/test_cli_storyteller.py`:

```python
"""Unit tests for cli_storyteller — no API calls."""
import json
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# _parse_storytell_issues
# ---------------------------------------------------------------------------

def test_parse_minor_issue():
    from pipeline.cli_storyteller import _parse_storytell_issues
    raw = "ISSUE|s3|MINOR|原本的句子。|建議的句子。|缺少過渡語"
    issues = _parse_storytell_issues(raw)
    assert len(issues) == 1
    assert issues[0]["scene_id"] == "s3"
    assert issues[0]["severity"] == "MINOR"
    assert issues[0]["original"] == "原本的句子。"
    assert issues[0]["suggested"] == "建議的句子。"
    assert issues[0]["reason"] == "缺少過渡語"


def test_parse_major_issue():
    from pipeline.cli_storyteller import _parse_storytell_issues
    raw = "ISSUE|s7|MAJOR|原文。|改寫建議。|敘事角度改變"
    issues = _parse_storytell_issues(raw)
    assert issues[0]["severity"] == "MAJOR"


def test_parse_ok_returns_empty():
    from pipeline.cli_storyteller import _parse_storytell_issues
    assert _parse_storytell_issues("OK") == []


def test_parse_ignores_non_issue_lines():
    from pipeline.cli_storyteller import _parse_storytell_issues
    raw = "這是一些說明文字\nISSUE|s1|MINOR|原文|建議|原因\n另一行"
    issues = _parse_storytell_issues(raw)
    assert len(issues) == 1


def test_parse_multiple_issues():
    from pipeline.cli_storyteller import _parse_storytell_issues
    raw = (
        "ISSUE|s2|MINOR|原文A|建議A|原因A\n"
        "ISSUE|s5|MAJOR|原文B|建議B|原因B\n"
        "ISSUE|s9|MINOR|原文C|建議C|原因C"
    )
    issues = _parse_storytell_issues(raw)
    assert len(issues) == 3
    assert issues[1]["severity"] == "MAJOR"


# ---------------------------------------------------------------------------
# _format_for_storytell
# ---------------------------------------------------------------------------

def test_format_for_storytell_includes_all_scenes(tmp_path):
    from pipeline.cli_storyteller import _format_for_storytell

    sb = {
        "version": 1, "format": "storyboard_v1",
        "target_duration_sec": 300, "aspect_ratio": "9:16", "theme": {},
        "scenes": [
            {"id": "s1", "section": "hook", "narration": "第一段旁白。",
             "narration_est_sec": 5, "facts_ref": [], "visual": {}, "overlay": {}, "pause_after_sec": 0.5},
            {"id": "s2", "section": "body", "narration": "第二段旁白。",
             "narration_est_sec": 5, "facts_ref": [], "visual": {}, "overlay": {}, "pause_after_sec": 0.5},
        ],
    }
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(sb), encoding="utf-8")

    result = _format_for_storytell(p)
    assert "[s1]" in result
    assert "第一段旁白。" in result
    assert "[s2]" in result
    assert "第二段旁白。" in result


# ---------------------------------------------------------------------------
# apply_storytell_issues
# ---------------------------------------------------------------------------

def test_apply_minor_replaces_narration(tmp_path):
    from pipeline.cli_storyteller import apply_storytell_issues

    sb = {
        "version": 1, "format": "storyboard_v1",
        "target_duration_sec": 300, "aspect_ratio": "9:16", "theme": {},
        "scenes": [
            {"id": "s3", "section": "body", "narration": "原本的句子。後面的文字。",
             "narration_est_sec": 5, "facts_ref": [], "visual": {}, "overlay": {}, "pause_after_sec": 0.5},
        ],
    }
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(sb), encoding="utf-8")

    issues = [{"scene_id": "s3", "severity": "MINOR",
               "original": "原本的句子。", "suggested": "改寫後的句子。", "reason": "過渡"}]
    applied = apply_storytell_issues(p, issues)

    data = json.loads(p.read_text(encoding="utf-8"))
    assert applied == 1
    assert "改寫後的句子。" in data["scenes"][0]["narration"]
    assert "原本的句子。" not in data["scenes"][0]["narration"]


def test_apply_skips_when_original_not_found(tmp_path):
    from pipeline.cli_storyteller import apply_storytell_issues

    sb = {
        "version": 1, "format": "storyboard_v1",
        "target_duration_sec": 300, "aspect_ratio": "9:16", "theme": {},
        "scenes": [
            {"id": "s1", "section": "hook", "narration": "完全不同的文字。",
             "narration_est_sec": 5, "facts_ref": [], "visual": {}, "overlay": {}, "pause_after_sec": 0.5},
        ],
    }
    p = tmp_path / "storyboard.json"
    p.write_text(json.dumps(sb), encoding="utf-8")

    issues = [{"scene_id": "s1", "severity": "MINOR",
               "original": "不存在的原文。", "suggested": "新文字。", "reason": "test"}]
    applied = apply_storytell_issues(p, issues)
    assert applied == 0
```

- [ ] **Step 2: Run to confirm all tests fail**

```bash
uv run pytest tests/unit/test_cli_storyteller.py -v
```

Expected: all FAIL with `ModuleNotFoundError` (file doesn't exist yet).

- [ ] **Step 3: Create `src/pipeline/cli_storyteller.py` with the scaffold**

```python
"""pipeline storytell — narrative flow review for storyboard scenes."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.console import Console
from rich.table import Table

storytell_app = typer.Typer(help="Review narrative flow and scene transitions.")
_console = Console()

_SYSTEM_PROMPT = """\
你是一位專業的繁體中文影片敘事顧問，專門審閱 YouTube 影片腳本的敘事結構。

你的任務是審閱影片腳本的「場景旁白（NARRATION）」序列，找出影響觀看流暢度的敘事結構問題。

審閱重點（只關注敘事結構，不檢查語法或用字）：
1. 場景間的過渡是否突兀——前一場景說完 A 主題，下一場景突然切到 B 主題，中間沒有銜接
2. 前提與結論順序是否錯誤——結論或情緒高潮在前提建立之前就出現
3. 連續場景是否重複陳述相同概念而未深化

嚴重程度分類（你來判斷）：
- MINOR：只需在場景開頭或結尾加入一句銜接語，不改變原本的意思與角度
- MAJOR：建議涉及重新排列場景順序、改寫鉤子（hook）、或改變觀眾對某場景的解讀角度

輸出格式（每個問題一行，嚴格遵守）：
ISSUE|場景ID|MINOR 或 MAJOR|原始句子（或該場景開頭句）|建議修改內容|原因說明

如果沒有問題，只輸出：OK

只列出真正影響敘事流暢度的問題，不要列雞毛蒜皮的細節。
"""


def _format_for_storytell(storyboard_path: Path) -> str:
    from pipeline.storyboard import Storyboard
    sb = Storyboard.load(storyboard_path)
    lines = []
    for s in sb.scenes:
        lines.append(f"[{s.id}] NARRATION: {s.narration}")
    return "\n".join(lines)


def _parse_storytell_issues(raw: str) -> list[dict]:
    issues = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("ISSUE|"):
            continue
        parts = line.split("|", 5)
        if len(parts) == 6:
            _, scene_id, severity, original, suggested, reason = parts
            issues.append({
                "scene_id": scene_id.strip(),
                "severity": severity.strip(),
                "original": original.strip(),
                "suggested": suggested.strip(),
                "reason": reason.strip(),
            })
    return issues


def apply_storytell_issues(storyboard_path: Path, issues: list[dict]) -> int:
    """Apply a list of storytell issues to storyboard.json. Returns count applied."""
    data = json.loads(storyboard_path.read_text(encoding="utf-8"))
    applied = 0
    for iss in issues:
        for s in data["scenes"]:
            if s["id"] != iss["scene_id"]:
                continue
            narration = s.get("narration", "")
            if iss["original"] in narration:
                s["narration"] = narration.replace(iss["original"], iss["suggested"], 1)
                applied += 1
    storyboard_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return applied


def print_storytell_table(issues: list[dict], console: Console | None = None) -> None:
    c = console or _console
    table = Table(box=box.ROUNDED, show_lines=True)
    table.add_column("Scene", style="cyan", width=6)
    table.add_column("Severity", style="yellow", width=7)
    table.add_column("Original", style="red", max_width=35)
    table.add_column("Suggested", style="green", max_width=35)
    table.add_column("Reason", max_width=30)
    for iss in issues:
        table.add_row(
            iss["scene_id"], iss["severity"],
            iss["original"], iss["suggested"], iss["reason"],
        )
    c.print(table)
```

- [ ] **Step 4: Run the tests — expect PASS**

```bash
uv run pytest tests/unit/test_cli_storyteller.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/cli_storyteller.py tests/unit/test_cli_storyteller.py
git commit -m "feat(storyteller): add parse/format/apply utilities with tests"
```

---

## Task 3: Storyteller — API call + CLI command

**Files:**
- Modify: `src/pipeline/cli_storyteller.py` (add `storytell_storyboard` + `run` command)

- [ ] **Step 1: Add `storytell_storyboard` function and `run` CLI command to `cli_storyteller.py`**

Append to the bottom of `src/pipeline/cli_storyteller.py` (after `print_storytell_table`):

```python
def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("PIPELINE_ANTHROPIC_API_KEY")
    if not key:
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("PIPELINE_ANTHROPIC_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        raise RuntimeError("No ANTHROPIC_API_KEY. Set PIPELINE_ANTHROPIC_API_KEY in .env.")
    return key


def storytell_storyboard(storyboard_path: Path) -> list[dict]:
    """Run Claude Haiku on storyboard narrations. Returns list of issue dicts."""
    import anthropic
    review_text = _format_for_storytell(storyboard_path)
    client = anthropic.Anthropic(api_key=_get_api_key())
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": review_text}],
    )
    raw = msg.content[0].text.strip()
    if raw == "OK":
        return []
    issues = _parse_storytell_issues(raw)
    if not issues:
        issues = [{"scene_id": "?", "severity": "NOTE", "original": "",
                   "suggested": "", "reason": raw[:200]}]
    return issues


@storytell_app.command()
def run(
    work_dir: Annotated[Path | None, typer.Option("--work-dir")] = None,
    project_id: Annotated[int, typer.Option("--project-id")] = 0,
    apply: Annotated[bool, typer.Option("--apply/--no-apply")] = False,
) -> None:
    """Review narrative flow and scene transitions using Claude Haiku."""
    from pipeline.config import PipelineConfig
    config = PipelineConfig()

    if work_dir is None:
        if project_id == 0:
            _console.print("[red]Provide --work-dir or --project-id[/red]")
            raise typer.Exit(1)
        work_dir = config.OUTPUT_DIR / "projects" / str(project_id)

    storyboard_path = work_dir / "storyboard.json"
    if not storyboard_path.exists():
        _console.print(f"[red]No storyboard.json in {work_dir}[/red]")
        raise typer.Exit(1)

    _console.print(f"[cyan]Reviewing narrative flow[/cyan] {storyboard_path}")
    with _console.status("Calling Claude Haiku..."):
        issues = storytell_storyboard(storyboard_path)

    if not issues:
        _console.print("[green]✓ No narrative issues found.[/green]")
        return

    print_storytell_table(issues)

    if not apply:
        _console.print(
            f"\n[dim]Found {len(issues)} issue(s). "
            f"Re-run with [cyan]--apply[/cyan] to apply fixes.[/dim]"
        )
        return

    minor = [i for i in issues if i["severity"] == "MINOR"]
    major = [i for i in issues if i["severity"] == "MAJOR"]

    # Auto-apply MINOR issues
    if minor:
        n = apply_storytell_issues(storyboard_path, minor)
        _console.print(f"\n[green]Auto-applied {n}/{len(minor)} MINOR fix(es).[/green]")

    # Confirm each MAJOR issue
    confirmed = []
    for iss in major:
        _console.print(f"\n[yellow]MAJOR[/yellow] [{iss['scene_id']}] {iss['reason']}")
        _console.print(f"  Original:  {iss['original']}")
        _console.print(f"  Suggested: {iss['suggested']}")
        answer = typer.prompt("Apply? [y/N]", default="N")
        if answer.strip().lower() == "y":
            confirmed.append(iss)

    if confirmed:
        n = apply_storytell_issues(storyboard_path, confirmed)
        _console.print(f"[green]Applied {n}/{len(confirmed)} confirmed MAJOR fix(es).[/green]")
```

- [ ] **Step 2: Smoke-test the CLI (display-only, no API call needed for structure)**

```bash
uv run pipeline storytell --help
```

Expected: error — `storytell` not registered yet (that's Task 4). If `pipeline storytell run --help` can't resolve, that's expected.

Actually run against the module directly to verify it loads:

```bash
uv run python -c "from pipeline.cli_storyteller import storytell_app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run full unit suite — no regressions**

```bash
uv run pytest tests/unit/ -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/cli_storyteller.py
git commit -m "feat(storyteller): add API call and CLI run command"
```

---

## Task 4: Register storyteller + wire into review gate

**Files:**
- Modify: `src/pipeline/cli.py`

- [ ] **Step 1: Register `storytell_app` in `cli.py`**

In `src/pipeline/cli.py`, add the import alongside the other cli imports (around line 11):

```python
from pipeline.cli_storyteller import storytell_app
```

Add the registration alongside `proofread_app` (around line 35):

```python
app.add_typer(storytell_app, name="storytell")
```

- [ ] **Step 2: Verify CLI is reachable**

```bash
uv run pipeline storytell --help
```

Expected output includes: `run  Review narrative flow and scene transitions using Claude Haiku.`

- [ ] **Step 3: Wire into the interactive review gate**

In `src/pipeline/cli.py`, find the proofread block inside the review gate (around line 144–159). After the `except` block that ends the proofread section, add the storyteller block:

```python
            # Auto-storytell: narrative flow review at the review gate
            if result.ctx.storyboard_path and result.ctx.storyboard_path.exists():
                typer.echo("\nReviewing narrative flow (Claude Haiku)...")
                try:
                    from pipeline.cli_storyteller import (
                        print_storytell_table,
                        storytell_storyboard,
                    )
                    st_issues = storytell_storyboard(result.ctx.storyboard_path)
                    if st_issues:
                        print_storytell_table(st_issues)
                        typer.echo(
                            f"\nFound {len(st_issues)} narrative issue(s). Apply before resuming:\n"
                            f"  uv run pipeline storytell run --project-id {project_id} --apply"
                        )
                    else:
                        typer.echo("  ✓ No narrative issues found.")
                except Exception as exc:
                    typer.echo(f"  (storytell skipped: {exc})")
```

Place this block immediately after the closing `except Exception as exc:` of the proofread block, before the `typer.echo("\nReview the files above...")` line.

- [ ] **Step 4: Wire into the `--skip-review` path**

Find the skip-review proofread block (around line 174–183). After its `except` block, add:

```python
            # Auto-apply storytell MINOR fixes in fully automated runs
            if result.ctx.storyboard_path and result.ctx.storyboard_path.exists():
                try:
                    from pipeline.cli_storyteller import (
                        apply_storytell_issues,
                        storytell_storyboard,
                    )
                    st_issues = storytell_storyboard(result.ctx.storyboard_path)
                    minor = [i for i in st_issues if i["severity"] == "MINOR"]
                    if minor:
                        n = apply_storytell_issues(result.ctx.storyboard_path, minor)
                        typer.echo(f"  storytell: auto-applied {n}/{len(minor)} MINOR fix(es)")
                except Exception as exc:
                    typer.echo(f"  (storytell skipped: {exc})")
```

- [ ] **Step 5: Run full unit suite**

```bash
uv run pytest tests/unit/ -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/cli.py
git commit -m "feat(cli): register storytell subapp and wire into review gate"
```

---

## Task 5: End-to-end smoke test

- [ ] **Step 1: Run storytell display-only on the existing project**

```bash
uv run pipeline storytell run --project-id 1776997800
```

Expected: either `✓ No narrative issues found.` or a table of MINOR/MAJOR issues — no crash, no hallucinated overlay errors.

- [ ] **Step 2: Verify proofreader fix on the same project**

```bash
uv run pipeline proofread run --project-id 1776997800
```

Expected: no "缺少 OVERLAY" findings. Either `✓ No issues found.` or only genuine narration text issues.

- [ ] **Step 3: Run ruff and mypy**

```bash
uv run ruff check src/pipeline/cli_storyteller.py src/pipeline/cli_proofread.py src/pipeline/cli.py
uv run ruff format src/pipeline/cli_storyteller.py src/pipeline/cli_proofread.py src/pipeline/cli.py
```

Fix any lint errors, then:

```bash
uv run mypy src/pipeline/cli_storyteller.py
```

Expected: no errors (or only missing stubs for `anthropic`, which is acceptable).

- [ ] **Step 4: Final commit**

```bash
git add -u
git commit -m "chore: lint and type-check review layer"
```
