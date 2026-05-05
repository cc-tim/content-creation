from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class SessionEntry:
    session_id: str
    timestamp: str
    command: str
    outcome: str = "success"   # "success" | "failed"
    stages: list[str] = field(default_factory=list)
    summary: str = ""
    error: str = ""
    mutation_id: str | None = None
    revert_payload: dict | None = None


def detect_claude_session() -> str | None:
    """Return the active Claude Code session UUID by finding the most recently
    modified .jsonl in ~/.claude/projects/<cwd-slug>/.

    Returns None when not running inside Claude Code.
    """
    cwd = os.getcwd()
    # /home/tim-huang/content-creation → -home-tim-huang-content-creation
    project_key = cwd.replace("/", "-")
    sessions_dir = Path.home() / ".claude" / "projects" / project_key
    if not sessions_dir.exists():
        return None
    jsonl_files = sorted(
        sessions_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return jsonl_files[0].stem if jsonl_files else None


def new_session_id() -> str:
    """Return the active Claude Code session UUID when running inside Claude Code,
    otherwise a millisecond-precision timestamp ID for manual CLI runs.
    """
    return detect_claude_session() or datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]


def append_session(work_dir: Path, entry: SessionEntry) -> None:
    """Atomically append a session entry to work_dir/sessions.json."""
    path = work_dir / "sessions.json"
    tmp = path.with_suffix(".json.tmp")
    try:
        existing: list[dict] = json.loads(path.read_text()) if path.exists() else []
    except (json.JSONDecodeError, OSError):
        existing = []
    existing.append(asdict(entry))
    tmp.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


def recent_mutations(work_dir: Path, *, n: int = 10) -> list[SessionEntry]:
    """Return the last n session entries that carry a revert_payload."""
    path = work_dir / "sessions.json"
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(rows, list):
        return []

    entries: list[SessionEntry] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not row.get("revert_payload"):
            continue
        entries.append(SessionEntry(
            session_id=row.get("session_id", ""),
            timestamp=row.get("timestamp", ""),
            command=row.get("command", ""),
            outcome=row.get("outcome", "success"),
            stages=list(row.get("stages", [])),
            summary=row.get("summary", ""),
            error=row.get("error", ""),
            mutation_id=row.get("mutation_id"),
            revert_payload=row.get("revert_payload"),
        ))
    return entries[-n:]
