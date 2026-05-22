from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class StyleLogEntry:
    timestamp: str
    action: str        # "add" | "remove" | "add_per_scene" | "remove_per_scene"
    element_id: str
    rationale: str = ""


def append_log(
    project_dir: Path,
    action: str,
    element_id: str,
    rationale: str = "",
) -> None:
    """Append a mutation entry to style_log.json (append-only audit trail)."""
    log_path = project_dir / "style_log.json"
    entry = StyleLogEntry(
        timestamp=datetime.now(tz=UTC).isoformat(),
        action=action,
        element_id=element_id,
        rationale=rationale,
    )
    entries: list[dict] = []
    if log_path.exists():
        entries = json.loads(log_path.read_text(encoding="utf-8"))
    entries.append(asdict(entry))
    log_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
