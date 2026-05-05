from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.dashboard.job_queue import (
    EditJob,
    JobQueue,
    SubActionResult,
    job_sidecar_path,
    list_jobs,
    load_job,
    save_job,
)
from pipeline.session_log import SessionEntry, append_session


def _sample_job(project_id: str = "42", job_id: str = "job-001") -> EditJob:
    return EditJob(
        job_id=job_id,
        project_id=project_id,
        tokens=["@s9/visual", "@s11/subtitle"],
        instruction="make these darker and tighten the subtitle",
    )


def test_edit_job_defaults_status_to_queued() -> None:
    job = _sample_job()
    assert job.status == "queued"
    assert job.telegram_opener_id is None
    assert job.sub_action_results == []
    assert job.started_at is None
    assert job.finished_at is None
    assert job.created_at is not None


def test_edit_job_status_must_be_in_allowed_set() -> None:
    with pytest.raises(ValueError):
        EditJob(job_id="x", project_id="y", tokens=[], instruction="z", status="bogus")


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    job = _sample_job()
    save_job(tmp_path, job)
    sidecar = job_sidecar_path(tmp_path, job.job_id)
    assert sidecar.exists()
    assert sidecar.parent.name == "edit_jobs"
    assert load_job(tmp_path, job.job_id) == job


def test_save_overwrites_existing_sidecar(tmp_path: Path) -> None:
    job = _sample_job()
    save_job(tmp_path, job)
    job.status = "running"
    save_job(tmp_path, job)
    assert load_job(tmp_path, job.job_id).status == "running"


def test_sub_action_result_round_trips_through_job_sidecar(tmp_path: Path) -> None:
    job = _sample_job()
    job.sub_action_results.append(
        SubActionResult(verb="subtitle set", scene="s9", ok=True, message="updated")
    )
    save_job(tmp_path, job)
    loaded = load_job(tmp_path, job.job_id)
    assert len(loaded.sub_action_results) == 1
    assert loaded.sub_action_results[0].verb == "subtitle set"
    assert loaded.sub_action_results[0].ok is True


def test_list_jobs_returns_all_sidecars_sorted_by_created_at(tmp_path: Path) -> None:
    save_job(tmp_path, _sample_job(job_id="job-001"))
    save_job(tmp_path, _sample_job(job_id="job-002"))
    save_job(tmp_path, _sample_job(job_id="job-003"))
    assert [job.job_id for job in list_jobs(tmp_path)] == ["job-001", "job-002", "job-003"]


def test_list_jobs_returns_empty_when_directory_absent(tmp_path: Path) -> None:
    assert list_jobs(tmp_path) == []


class FakeRunner:
    def __init__(self, *, sleep_sec: float = 0.0, succeed: bool = True) -> None:
        self.sleep_sec = sleep_sec
        self.succeed = succeed
        self.calls: list[EditJob] = []

    async def run(self, job: EditJob, project_root: Path) -> list[SubActionResult]:
        self.calls.append(job)
        if self.sleep_sec:
            await asyncio.sleep(self.sleep_sec)
        if not self.succeed:
            raise RuntimeError("simulated failure")
        return [SubActionResult(verb="subtitle set", scene="s9", ok=True, message="ok")]


@pytest.fixture
def project_tree(tmp_path: Path) -> Path:
    proj = tmp_path / "projects" / "42"
    proj.mkdir(parents=True)
    return tmp_path / "projects"


@pytest.mark.asyncio
async def test_submit_runs_one_job_to_completion(project_tree: Path) -> None:
    runner = FakeRunner()
    queue = JobQueue(projects_root=project_tree, runner=runner)
    await queue.start()
    await queue.submit(EditJob(job_id="j1", project_id="42", tokens=["@s9"], instruction="x"))
    await queue.wait_idle("42", timeout=2.0)
    loaded = load_job(project_tree / "42", "j1")
    assert loaded.status == "done"
    assert loaded.started_at is not None
    assert loaded.finished_at is not None
    assert len(loaded.sub_action_results) == 1
    assert runner.calls[0].job_id == "j1"
    await queue.shutdown()


@pytest.mark.asyncio
async def test_per_project_fifo_serialization(project_tree: Path) -> None:
    runner = FakeRunner(sleep_sec=0.05)
    queue = JobQueue(projects_root=project_tree, runner=runner)
    await queue.start()
    await queue.submit(EditJob(job_id="j1", project_id="42", tokens=[], instruction="a"))
    await queue.submit(EditJob(job_id="j2", project_id="42", tokens=[], instruction="b"))
    await queue.wait_idle("42", timeout=2.0)
    assert [call.job_id for call in runner.calls] == ["j1", "j2"]
    await queue.shutdown()


@pytest.mark.asyncio
async def test_parallel_across_projects(project_tree: Path) -> None:
    (project_tree / "43").mkdir()
    runner = FakeRunner(sleep_sec=0.2)
    queue = JobQueue(projects_root=project_tree, runner=runner)
    await queue.start()
    t0 = asyncio.get_event_loop().time()
    await queue.submit(EditJob(job_id="ja", project_id="42", tokens=[], instruction="x"))
    await queue.submit(EditJob(job_id="jb", project_id="43", tokens=[], instruction="y"))
    await asyncio.gather(
        queue.wait_idle("42", timeout=2.0),
        queue.wait_idle("43", timeout=2.0),
    )
    elapsed = asyncio.get_event_loop().time() - t0
    assert elapsed < 0.35
    await queue.shutdown()


@pytest.mark.asyncio
async def test_failed_job_marked_failed_and_queue_recovers(project_tree: Path) -> None:
    runner = FakeRunner(succeed=False)
    queue = JobQueue(projects_root=project_tree, runner=runner)
    await queue.start()
    await queue.submit(EditJob(job_id="bad", project_id="42", tokens=[], instruction="x"))
    await queue.wait_idle("42", timeout=2.0)
    assert load_job(project_tree / "42", "bad").status == "failed"
    runner.succeed = True
    await queue.submit(EditJob(job_id="good", project_id="42", tokens=[], instruction="y"))
    await queue.wait_idle("42", timeout=2.0)
    assert load_job(project_tree / "42", "good").status == "done"
    await queue.shutdown()


class CancellableRunner:
    def __init__(self) -> None:
        self.cancelled = False
        self.entered = asyncio.Event()

    async def run(self, job: EditJob, project_root: Path) -> list[SubActionResult]:
        self.entered.set()
        try:
            await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return []


@pytest.mark.asyncio
async def test_cancel_marks_job_cancelled_and_runner_observes_cancellation(
    project_tree: Path,
) -> None:
    runner = CancellableRunner()
    queue = JobQueue(projects_root=project_tree, runner=runner)
    await queue.start()
    await queue.submit(EditJob(job_id="long", project_id="42", tokens=[], instruction="x"))
    await asyncio.wait_for(runner.entered.wait(), timeout=1.0)
    assert await queue.cancel("42", "long") is True
    await queue.wait_idle("42", timeout=2.0)
    assert load_job(project_tree / "42", "long").status == "cancelled"
    assert runner.cancelled is True
    await queue.shutdown()


@pytest.mark.asyncio
async def test_cancel_returns_false_when_job_not_running(project_tree: Path) -> None:
    queue = JobQueue(projects_root=project_tree, runner=FakeRunner())
    await queue.start()
    assert await queue.cancel("42", "nonexistent") is False
    await queue.shutdown()


def test_reload_on_startup_marks_running_as_interrupted(project_tree: Path) -> None:
    proj = project_tree / "42"
    save_job(
        proj,
        EditJob(
            job_id="orphan",
            project_id="42",
            tokens=[],
            instruction="x",
            status="running",
        ),
    )
    save_job(
        proj,
        EditJob(
            job_id="finished",
            project_id="42",
            tokens=[],
            instruction="y",
            status="done",
        ),
    )
    queue = JobQueue(projects_root=project_tree, runner=FakeRunner())
    queue.reload_on_startup()
    assert load_job(proj, "orphan").status == "interrupted"
    assert load_job(proj, "finished").status == "done"


def test_reload_on_startup_handles_missing_projects_dir(tmp_path: Path) -> None:
    queue = JobQueue(projects_root=tmp_path / "nonexistent", runner=FakeRunner())
    queue.reload_on_startup()


class _RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.next_id = 1000

    def send_message(self, text: str, **kwargs):
        self.sent.append({"method": "send_message", "text": text, **kwargs})
        msg_id = self.next_id
        self.next_id += 1
        return {"message_id": msg_id}

    def edit_message_text(self, **kwargs):
        self.sent.append({"method": "edit_message_text", **kwargs})
        return {}


@pytest.mark.asyncio
async def test_submit_posts_opener_message_with_cancel_button(project_tree: Path) -> None:
    notifier = _RecordingNotifier()
    queue = JobQueue(projects_root=project_tree, runner=FakeRunner(), notifier=notifier)
    await queue.start()
    await queue.submit(
        EditJob(job_id="j1", project_id="42", tokens=["@s9/visual"], instruction="darken this")
    )
    await queue.wait_idle("42", timeout=2.0)
    opener = notifier.sent[0]
    assert opener["method"] == "send_message"
    keyboard = opener.get("reply_markup", {}).get("inline_keyboard", [])
    assert any(
        btn.get("callback_data") == "cancel:42:j1"
        for row in keyboard
        for btn in row
    )
    assert load_job(project_tree / "42", "j1").telegram_opener_id == 1000
    await queue.shutdown()


@pytest.mark.asyncio
async def test_handle_callback_query_routes_cancel(project_tree: Path) -> None:
    runner = CancellableRunner()
    queue = JobQueue(projects_root=project_tree, runner=runner, notifier=_RecordingNotifier())
    await queue.start()
    await queue.submit(EditJob(job_id="long", project_id="42", tokens=[], instruction="x"))
    await asyncio.wait_for(runner.entered.wait(), timeout=1.0)
    assert await queue.handle_callback_query({"id": "cb1", "data": "cancel:42:long"}) is True
    await queue.wait_idle("42", timeout=2.0)
    assert load_job(project_tree / "42", "long").status == "cancelled"
    await queue.shutdown()


@pytest.mark.asyncio
async def test_handle_callback_query_ignores_unknown_verb(project_tree: Path) -> None:
    queue = JobQueue(projects_root=project_tree, runner=FakeRunner(), notifier=None)
    await queue.start()
    assert await queue.handle_callback_query({"id": "cb1", "data": "doitnow:42:j1"}) is False
    await queue.shutdown()


@pytest.mark.asyncio
async def test_handle_callback_query_routes_revert(project_tree: Path) -> None:
    append_session(
        project_tree / "42",
        SessionEntry(
            session_id="sess-1",
            timestamp=datetime.now().isoformat(timespec="seconds"),
            command="subtitle set",
            mutation_id="m1",
            revert_payload={"verb": "subtitle set", "args": {"scene": "s1", "text": "old"}},
        ),
    )
    queue = JobQueue(projects_root=project_tree, runner=FakeRunner(), notifier=None)
    await queue.start()

    assert await queue.handle_callback_query({"data": "revert:42:m1"}) is True
    await queue.wait_idle("42", timeout=2.0)

    jobs = list_jobs(project_tree / "42")
    assert any(job.revert_target == {"mutation_id": "m1"} for job in jobs)
    await queue.shutdown()


class _FakeCoordinator:
    def __init__(self) -> None:
        self.resolutions: list[tuple[str, str]] = []
        self.proposals: dict[str, object] = {}

    def resolve(self, mutation_id: str, *, decision: str) -> bool:
        self.resolutions.append((mutation_id, decision))
        return True

    def proposal_for(self, mutation_id: str):
        return self.proposals.get(mutation_id)


class _Proposal:
    verb = "subtitle set"
    args = {"scene": "s9", "text": "candidate"}


@pytest.mark.asyncio
async def test_handle_callback_query_routes_proposal_apply_and_cancel(
    project_tree: Path,
) -> None:
    coord = _FakeCoordinator()
    queue = JobQueue(projects_root=project_tree, runner=FakeRunner(), notifier=None)
    queue.set_coordinator(coord)
    await queue.start()

    assert await queue.handle_callback_query({"data": "apply:42:m1"}) is True
    assert await queue.handle_callback_query({"data": "cancel_proposal:42:m2"}) is True

    assert coord.resolutions == [("m1", "apply"), ("m2", "cancel")]
    await queue.shutdown()


@pytest.mark.asyncio
async def test_handle_callback_query_edit_proposal_writes_draft_and_cancels(
    project_tree: Path,
) -> None:
    coord = _FakeCoordinator()
    coord.proposals["m1"] = _Proposal()
    queue = JobQueue(projects_root=project_tree, runner=FakeRunner(), notifier=None)
    queue.set_coordinator(coord)
    await queue.start()

    assert await queue.handle_callback_query({"data": "edit_proposal:42:m1:j1"}) is True

    draft = (project_tree / "42" / "edit_draft.json").read_text(encoding="utf-8")
    assert "@s9" in draft
    assert "subtitle set" in draft
    assert coord.resolutions == [("m1", "cancel")]
    await queue.shutdown()
