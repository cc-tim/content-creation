"""pipeline proofread — proofreads narration and overlay text in a storyboard."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from pipeline.config import PipelineConfig

proofread_app = typer.Typer(help="Proofread storyboard narration and overlay text.")
_console = Console()

_PROOFREADING_GUIDE_PATH = Path("data/proofreading-notice-zh-tw.txt")

_SYSTEM_PROMPT = """\
你是一個專業的繁體中文校稿專家，專門審閱 YouTube 影片腳本。

你的任務是審閱影片腳本中的兩種文字：
- NARRATION（旁白）：會被 TTS 語音合成讀出的文字
- OVERLAY（畫面標題）：會顯示在影片畫面上的文字

每個場景會標註 SECTION（段落角色），例如：
- hook / context：開場與背景，應該以平實的事實陳述為主
- rising / climax / aftermath：張力與高潮，可使用較有力的修辭
- analysis / content / punchline：結尾分析或收束

校稿重點：
1. 如有 OVERLAY，審閱標題語法：
   - 語法是否正確、結構是否完整
   - 是否簡潔有力、易於快速閱讀
   - 是否符合台灣繁體中文用法
   - 必須是獨立完整的陳述句，不可是懸掛子句
   - 常見問題：以「，是...」、「，而是...」、「，但...」開頭的片段（缺乏主語或前提）
   - 常見問題：以否定詞「不是...，是...」作為標題開頭（像是句子的後半段）
   - 建議改法：改成正向陳述或加上主語，例如「關鍵：...」、「真相：...」
2. NARRATION 旁白語法：
   - 語句是否流暢自然
   - 有沒有明顯語法錯誤或用詞不當
3. NARRATION 語氣與「AI 寫作味」檢查（重要）：
   - 在 hook 或 context 段落出現的「重音收尾句」：例如「X 年沒換過」、「從未改變」、
     「永遠不變」、「完全相同」、「徹底顛覆」、「再也回不去了」——這些屬於高潮句型，
     不應該出現在開場/背景段。請建議改為事實陳述。
   - 不必要的最高級或誇飾：「最」、「絕對」、「唯一」、「永遠」、「徹底」——若沒有
     扎實事實支撐，建議改為帶有對冲詞的版本（「幾乎」、「大致」、「將近」、「在...範圍內」）。
   - 排比句的浮誇收尾：「同一個 X、同一個 Y、同一個 Z」這類三連排比，若事實上 X/Y/Z
     並非真的相同，要求列出哪一項與圖像/事實不符。
   - 對於 climax / punchline 段落，這些修辭是允許的，不要誤報。
4. 事實內部一致性：narration 中具體名詞（座椅、輪子、年代、人名）若與其他場景互相矛盾，
   或描述了畫面顯然不存在的物件（純文字無法 100% 驗證，但若有跨場景矛盾請指出），標記出來。

格式要求（嚴格遵守）：
每個問題一個條目，使用以下格式：
ISSUE|scene_id|OVERLAY or NARRATION or TONE|原文|建議|原因

- TONE 類型用於語氣與 AI 味問題（不一定是文法錯）
- NARRATION 類型用於語法/用詞錯誤
- 原因要簡短說明屬於哪一類（例如「hook 段落出現高潮句型」、「無事實支撐的最高級」）

如果完全沒有問題，只輸出：OK

只列出真正需要修改的地方。不要列出「沒有問題」的條目。
"""


def _load_guide() -> str:
    if _PROOFREADING_GUIDE_PATH.exists():
        return _PROOFREADING_GUIDE_PATH.read_text(encoding="utf-8")
    return ""


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


def _format_for_review(storyboard_path: Path) -> str:
    from pipeline.storyboard import Storyboard

    sb = Storyboard.load(storyboard_path)
    lines = []
    has_overlay = False
    for s in sb.scenes:
        lines.append(f"[{s.id}] SECTION: {s.section}")
        lines.append(f"[{s.id}] NARRATION: {s.narration}")
        if s.overlay:
            text = s.overlay.get("text", "")
            if text:
                has_overlay = True
                lines.append(f"[{s.id}] OVERLAY: {text}")
    if not has_overlay:
        lines.append("（本腳本無 OVERLAY 文字，請只審閱 NARRATION）")
    return "\n".join(lines)


def _parse_issues(raw: str) -> list[dict]:
    issues = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("ISSUE|"):
            continue
        parts = line.split("|", 5)
        if len(parts) == 6:
            _, scene_id, field_type, original, suggested, reason = parts
            issues.append(
                {
                    "scene_id": scene_id.strip(),
                    "type": field_type.strip(),
                    "original": original.strip(),
                    "suggested": suggested.strip(),
                    "reason": reason.strip(),
                }
            )
    return issues


# ── Public API (importable by cli.py and other modules) ──────────────────────


def proofread_storyboard(storyboard_path: Path) -> list[dict]:
    """Run Claude Haiku on storyboard text. Returns list of issue dicts (empty = clean)."""
    import anthropic

    guide = _load_guide()
    system = _SYSTEM_PROMPT + (f"\n\n校稿參考資料：\n{guide}" if guide else "")
    review_text = _format_for_review(storyboard_path)
    client = anthropic.Anthropic(api_key=_get_api_key())
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": review_text}],
    )
    raw = msg.content[0].text.strip()
    if raw == "OK":
        return []
    issues = _parse_issues(raw)
    if not issues:
        # Claude returned something but not structured — surface it as a single note
        issues = [
            {"scene_id": "?", "type": "NOTE", "original": "", "suggested": "", "reason": raw[:200]}
        ]
    return issues


def apply_issues(storyboard_path: Path, issues: list[dict]) -> int:
    """Apply a list of issues to storyboard.json. Returns count of applied fixes."""
    import json

    data = json.loads(storyboard_path.read_text(encoding="utf-8"))
    applied = 0
    for iss in issues:
        if iss["type"] not in ("NARRATION", "OVERLAY", "TONE"):
            continue
        for s in data["scenes"]:
            if s["id"] != iss["scene_id"]:
                continue
            if iss["type"] in ("NARRATION", "TONE"):
                if iss["original"] in s.get("narration", ""):
                    s["narration"] = s["narration"].replace(iss["original"], iss["suggested"])
                    applied += 1
            elif iss["type"] == "OVERLAY":
                overlay = s.get("overlay") or {}
                if overlay.get("text") == iss["original"]:
                    overlay["text"] = iss["suggested"]
                    s["overlay"] = overlay
                    applied += 1
    storyboard_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return applied


def print_issues_table(issues: list[dict], console: Console | None = None) -> None:
    c = console or _console
    table = Table(box=box.ROUNDED, show_lines=True)
    table.add_column("Scene", style="cyan", width=6)
    table.add_column("Type", style="yellow", width=9)
    table.add_column("Original", style="red", max_width=35)
    table.add_column("Suggested", style="green", max_width=35)
    table.add_column("Reason", max_width=30)
    for iss in issues:
        table.add_row(
            iss["scene_id"], iss["type"], iss["original"], iss["suggested"], iss["reason"]
        )
    c.print(table)


# ── CLI command ───────────────────────────────────────────────────────────────


@proofread_app.command()
def run(
    work_dir: Annotated[Path | None, typer.Option("--work-dir", help="Project directory")] = None,
    project_id: Annotated[int, typer.Option("--project-id", help="Project ID")] = 0,
    apply: Annotated[bool, typer.Option("--apply/--no-apply", help="Auto-apply all fixes")] = False,
) -> None:
    """Proofread storyboard narration and overlay text using Claude Haiku."""
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

    _console.print(f"[cyan]Proofreading[/cyan] {storyboard_path}")
    with _console.status("Calling Claude Haiku..."):
        issues = proofread_storyboard(storyboard_path)

    if not issues:
        _console.print("[green]✓ No issues found.[/green]")
        return

    print_issues_table(issues)

    if apply:
        n = apply_issues(storyboard_path, issues)
        _console.print(f"\n[green]Applied {n}/{len(issues)} fixes.[/green]")
        from pipeline.session_log import SessionEntry, append_session, new_session_id

        append_session(
            work_dir,
            SessionEntry(
                session_id=new_session_id(),
                timestamp=datetime.now().isoformat(timespec="seconds"),
                command="proofread run --apply",
                summary=f"proofread: applied {n}/{len(issues)} fixes",
            ),
        )
    else:
        _console.print(
            f"\n[dim]Found {len(issues)} issue(s). "
            f"Re-run with [cyan]--apply[/cyan] to apply all fixes.[/dim]"
        )
