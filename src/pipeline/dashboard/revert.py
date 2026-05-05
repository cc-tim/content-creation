"""Revert orchestration for dashboard edit jobs."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from pipeline.dashboard.job_queue import EditJob


def synthesise_revert_job(*, project_root: Path, mutation_id: str) -> EditJob:
    """Build an edit job that replays the inverse of a prior mutation."""
    sessions_path = project_root / "sessions.json"
    if not sessions_path.exists():
        raise KeyError(f"no sessions.json under {project_root}")

    rows = json.loads(sessions_path.read_text(encoding="utf-8"))
    target = next((row for row in rows if row.get("mutation_id") == mutation_id), None)
    if target is None:
        raise KeyError(f"mutation_id {mutation_id!r} not found in sessions.json")
    if not target.get("revert_payload"):
        raise ValueError(f"mutation {mutation_id!r} is not revertable (no revert_payload)")

    return EditJob(
        job_id=uuid.uuid4().hex[:12],
        project_id=project_root.name,
        tokens=[],
        instruction=f"revert mutation {mutation_id}",
        revert_target={"mutation_id": mutation_id},
    )
