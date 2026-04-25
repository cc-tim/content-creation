"""pipeline storytell — narrative flow review for storyboard scenes."""
from __future__ import annotations

import json
from pathlib import Path

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
            issues.append(
                {
                    "scene_id": scene_id.strip(),
                    "severity": severity.strip(),
                    "original": original.strip(),
                    "suggested": suggested.strip(),
                    "reason": reason.strip(),
                }
            )
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
                s["narration"] = narration.replace(iss["original"], iss["suggested"], 1)  # first match only
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
            iss["scene_id"],
            iss["severity"],
            iss["original"],
            iss["suggested"],
            iss["reason"],
        )
    c.print(table)
