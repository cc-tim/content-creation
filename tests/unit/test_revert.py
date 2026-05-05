from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from pipeline.dashboard.job_queue import JobQueue
from pipeline.dashboard.mutation_runtime import MutationProposal, apply_mutation
from pipeline.dashboard.revert import synthesise_revert_job
from pipeline.session_log import SessionEntry, append_session
from pipeline.storyboard import Scene, Storyboard


def _seed_mutation_log(
    work_dir: Path,
    *,
    mutation_id: str,
    revert_payload: dict[str, Any] | None,
) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    append_session(
        work_dir,
        SessionEntry(
            session_id="sess-1",
            timestamp=datetime.now().isoformat(timespec="seconds"),
            command="subtitle set --scene s1 --text 'new'",
            summary="subtitle s1 set",
            mutation_id=mutation_id,
            revert_payload=revert_payload,
        ),
    )


def test_synthesise_revert_job_loads_payload_and_marks_revert_target(tmp_path: Path) -> None:
    proj = tmp_path / "projects" / "42"
    _seed_mutation_log(
        proj,
        mutation_id="m1",
        revert_payload={"verb": "subtitle set", "args": {"scene": "s1", "text": "old"}},
    )

    job = synthesise_revert_job(project_root=proj, mutation_id="m1")

    assert job.project_id == "42"
    assert job.revert_target == {"mutation_id": "m1"}
    assert job.tokens == []
    assert "revert" in job.instruction.lower()


def test_synthesise_revert_job_unknown_mutation_id_raises(tmp_path: Path) -> None:
    proj = tmp_path / "projects" / "42"
    proj.mkdir(parents=True)

    with pytest.raises(KeyError):
        synthesise_revert_job(project_root=proj, mutation_id="nonexistent")


def test_synthesise_revert_job_skipped_when_payload_is_none(tmp_path: Path) -> None:
    proj = tmp_path / "projects" / "42"
    _seed_mutation_log(proj, mutation_id="m1", revert_payload=None)

    with pytest.raises(ValueError, match="not revertable"):
        synthesise_revert_job(project_root=proj, mutation_id="m1")


class _NeverRunner:
    async def run(self, job, project_root):
        raise AssertionError("agent runner should not be called for revert jobs")


@pytest.mark.asyncio
async def test_revert_round_trip_restores_old_value_and_skips_agent(tmp_path: Path) -> None:
    proj_root = tmp_path / "projects" / "42"
    proj_root.mkdir(parents=True)
    Storyboard(
        scenes=[
            Scene(
                id="s1",
                section="content",
                narration="ORIGINAL",
                narration_est_sec=1.0,
            )
        ]
    ).save(proj_root / "storyboard.json")

    apply_result = apply_mutation(
        MutationProposal(
            job_id="seed",
            verb="subtitle set",
            args={"scene": "s1", "text": "EDITED"},
        ),
        project_root=proj_root,
    )
    assert apply_result.status == "applied"
    assert apply_result.mutation_id is not None

    queue = JobQueue(projects_root=tmp_path / "projects", runner=_NeverRunner())
    await queue.start()
    revert_job = synthesise_revert_job(
        project_root=proj_root,
        mutation_id=apply_result.mutation_id,
    )
    await queue.submit(revert_job)
    await queue.wait_idle("42", timeout=2.0)

    scene = Storyboard.load(proj_root / "storyboard.json").get_scene("s1")
    assert scene is not None
    assert scene.subtitle_override == "ORIGINAL"
    rows = json.loads((proj_root / "sessions.json").read_text(encoding="utf-8"))
    assert rows[-1]["command"].startswith("subtitle set")
    assert "ORIGINAL" in rows[-1]["summary"]

    await queue.shutdown()
