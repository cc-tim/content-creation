# Click-to-Edit Plan 3 — JobQueue + Telegram + Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend plumbing for chat-driven edits — an in-process per-project asyncio JobQueue that spawns a `claude -p` subprocess per submitted job, a Telegram long-poll listener that routes inline-button taps back into the queue, and four project-scoped CLI verbs (`narration regen`, `subtitle set`, `overlay set`, `image regen`) the agent calls to mutate storyboard state. No frontend, no SSE, no trust-gate UI yet — those land in Plans 4-5.

**Architecture:** A single `JobQueue` instance owned by the FastAPI app. Per-project `asyncio.Queue[EditJob]` plus a per-project consumer coroutine that pulls one job at a time and runs it through an injectable `AgentRunner` (production: spawns `claude -p`; tests: a fake that returns canned stdout). Job state lives on disk at `output/projects/<id>/edit_jobs/<job_id>.json`; on startup, any job left in `running` state is marked `interrupted`. The four CLI verbs are deliberately mutate-only — they update the storyboard (or a per-scene override field) and stop. The agent chains `compose rescene` / `compose reburn` afterwards. This matches the existing `transition set` (Plan 1) and `narration set-source` (Plan 2) idiom: a single source of truth for state mutations, with the heavyweight render step invoked separately.

**Tech Stack:** Python 3.12, FastAPI, asyncio, pydantic v2, Typer, httpx, pytest + pytest-asyncio. No new third-party dependencies.

**Spec reference:** `docs/superpowers/specs/2026-05-04-dashboard-click-to-edit-design.md` — §"Architecture", §"Backend — JobQueue", §"Backend — Telegram listener", §"CLI verb surface" (the four agent-only verbs), §"Failure handling & policies" (concurrency, crash recovery), and the `POST /api/jobs/...` rows in §"Backend — direct-action endpoints".

**Worktree:** Work happens in `.worktrees/feat/click-to-edit-3-jobqueue-telegram/` (already created on branch `feat/click-to-edit-3-jobqueue-telegram` off `master`).

---

## File Structure

**Create:**

| File | Responsibility |
|---|---|
| `src/pipeline/dashboard/job_queue.py` | `EditJob`, `SubActionResult` pydantic models; `JobQueue` class (per-project asyncio queues, single-consumer coroutine per project, submit/cancel/crash-recovery). Agent invocation delegated to an injected `AgentRunner`. |
| `src/pipeline/dashboard/agent_runner.py` | `ClaudeAgentRunner` implementation of the `AgentRunner` Protocol — `asyncio.create_subprocess_exec("claude", "-p", ...)`, streams stdout, edits a Telegram message every ~2s. The `AgentRunner` Protocol itself lives in `job_queue.py` to avoid a circular import. |
| `src/pipeline/dashboard/agent_prompt.md` | System-prompt template for the edit agent. Loaded once at JobQueue startup and supplemented per-job with project id + storyboard summary + resolved tokens. |
| `src/pipeline/cli_subtitle.py` | Typer subapp exposing `pipeline subtitle set` (adds `subtitle_override` field on Scene). |
| `src/pipeline/cli_overlay.py` | Typer subapp exposing `pipeline overlay set` (mutates `scene.overlay["text"]`). |
| `src/pipeline/cli_image.py` | Typer subapp exposing `pipeline image regen` (mutates `scene.visual["prompt"]`, `visual["tier"]`; deletes the cached scene image). |
| `tests/unit/test_job_queue.py` | EditJob model + JobQueue submit/cancel/parallel-projects/crash-recovery via FakeAgentRunner. |
| `tests/unit/test_agent_runner.py` | ClaudeAgentRunner — prompt assembly, streaming-edit cadence, exit-code mapping. Real subprocess swapped for `python -c`. |
| `tests/unit/test_telegram_extended_send.py` | reply_to/inline_keyboard params, send_photo, send_video, edit_message_text — httpx mocked. |
| `tests/unit/test_telegram_long_poll.py` | get_updates loop, offset tracking, callback_query dispatch, retry on transient failure. |
| `tests/unit/test_cli_subtitle.py` | `subtitle set` mutation, scene-not-found, project-id refusal, idempotent replace. |
| `tests/unit/test_cli_overlay.py` | `overlay set` mutation, preserves other overlay keys, scene-not-found. |
| `tests/unit/test_cli_narration_regen.py` | `narration regen` mutation, scene-not-found. |
| `tests/unit/test_cli_image.py` | `image regen` mutation + image-cache deletion + tier validation. |
| `tests/integration/test_jobs_endpoints.py` | POST /api/jobs submit + cancel — FastAPI TestClient hitting a JobQueue with FakeAgentRunner. |

**Modify:**

| File | Change |
|---|---|
| `src/pipeline/storyboard.py` | Add `subtitle_override: str \| None = None` field to `Scene` (sparse to_dict). |
| `src/pipeline/notify/telegram.py` | Add `reply_to_message_id` + `reply_markup` params to existing send paths; add `send_photo`, `send_video`, `edit_message_text` helpers; add `get_updates` long-poll method + `LongPollListener` async runner. |
| `src/pipeline/cli_narration.py` | Add `narration regen --scene --text` command to existing `narration_app`. |
| `src/pipeline/cli.py` | Register `subtitle_app`, `overlay_app`, `image_app` typer subapps. |
| `src/pipeline/dashboard/server.py` | Register `POST /api/jobs/{project_id}/submit` and `POST /api/jobs/{project_id}/{job_id}/cancel`; wire `JobQueue` and Telegram long-poll listener into FastAPI `lifespan`. |

**Out of scope** (later plans):

- Edit-mode UI / floating composer / click-to-mint frontend (Plan 4)
- Trust gate (auto-apply vs propose-then-apply tiers) (Plan 5)
- `↩ Revert` button + `revert_payload` on session_log entries (Plan 5)
- SSE `files_changed` channel and dashboard auto-refresh (Plan 5)
- Direct-action HTTP endpoints for transitions / narration sources / recorder (already shipped in Plans 1-2)

---

## Task 1: Add `EditJob` + `SubActionResult` pydantic models with sidecar I/O

**Files:**
- Create: `src/pipeline/dashboard/job_queue.py` (initial — model definitions only)
- Test: `tests/unit/test_job_queue.py` (new)

The job sidecar lives at `output/projects/<id>/edit_jobs/<job_id>.json`. The model is the on-disk shape and the in-memory contract for the queue.

- [ ] **Step 1.1: Write the model + sidecar tests**

Create `tests/unit/test_job_queue.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.dashboard.job_queue import (
    EditJob,
    SubActionResult,
    job_sidecar_path,
    list_jobs,
    load_job,
    save_job,
)


def _sample_job(project_id: str = "42", job_id: str = "job-001") -> EditJob:
    return EditJob(
        job_id=job_id,
        project_id=project_id,
        tokens=["@s9/visual", "@s11/subtitle"],
        instruction="make these darker and tighten the subtitle",
    )


def test_edit_job_defaults_status_to_queued():
    job = _sample_job()
    assert job.status == "queued"
    assert job.telegram_opener_id is None
    assert job.sub_action_results == []
    assert job.started_at is None
    assert job.finished_at is None
    assert job.created_at is not None  # auto-stamped


def test_edit_job_status_must_be_in_allowed_set():
    with pytest.raises(ValueError):
        EditJob(
            job_id="x", project_id="y", tokens=[], instruction="z",
            status="bogus",
        )


def test_save_and_load_round_trip(tmp_path: Path):
    job = _sample_job()
    save_job(tmp_path, job)
    sidecar = job_sidecar_path(tmp_path, job.job_id)
    assert sidecar.exists()
    assert sidecar.parent.name == "edit_jobs"

    loaded = load_job(tmp_path, job.job_id)
    assert loaded == job


def test_save_overwrites_existing_sidecar(tmp_path: Path):
    job = _sample_job()
    save_job(tmp_path, job)
    job.status = "running"
    save_job(tmp_path, job)
    loaded = load_job(tmp_path, job.job_id)
    assert loaded.status == "running"


def test_sub_action_result_round_trips_through_job_sidecar(tmp_path: Path):
    job = _sample_job()
    job.sub_action_results.append(
        SubActionResult(verb="subtitle set", scene="s9", ok=True, message="updated")
    )
    save_job(tmp_path, job)
    loaded = load_job(tmp_path, job.job_id)
    assert len(loaded.sub_action_results) == 1
    assert loaded.sub_action_results[0].verb == "subtitle set"
    assert loaded.sub_action_results[0].ok is True


def test_list_jobs_returns_all_sidecars_sorted_by_created_at(tmp_path: Path):
    save_job(tmp_path, _sample_job(job_id="job-001"))
    save_job(tmp_path, _sample_job(job_id="job-002"))
    save_job(tmp_path, _sample_job(job_id="job-003"))
    jobs = list_jobs(tmp_path)
    assert [j.job_id for j in jobs] == ["job-001", "job-002", "job-003"]


def test_list_jobs_returns_empty_when_directory_absent(tmp_path: Path):
    assert list_jobs(tmp_path) == []
```

- [ ] **Step 1.2: Run the tests — expect ImportError**

Run: `uv run pytest tests/unit/test_job_queue.py -v`
Expected: ImportError on `pipeline.dashboard.job_queue`.

- [ ] **Step 1.3: Create `job_queue.py` with the model + sidecar I/O**

Create `src/pipeline/dashboard/job_queue.py`:

```python
"""Per-project asyncio JobQueue + sidecar persistence for edit jobs.

Job sidecars live at:
    output/projects/<id>/edit_jobs/<job_id>.json

Status lifecycle:
    queued → running → done | failed | interrupted | cancelled
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "done", "failed", "interrupted", "cancelled"]


class SubActionResult(BaseModel):
    """One CLI verb invocation by the agent inside a single job."""

    verb: str
    scene: str | None = None
    ok: bool
    message: str = ""


class EditJob(BaseModel):
    """One submitted edit, queued for a project's consumer coroutine."""

    job_id: str
    project_id: str
    tokens: list[str]
    instruction: str
    status: JobStatus = "queued"
    telegram_opener_id: int | None = None
    sub_action_results: list[SubActionResult] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    started_at: str | None = None
    finished_at: str | None = None


def job_sidecar_path(project_root: Path, job_id: str) -> Path:
    return project_root / "edit_jobs" / f"{job_id}.json"


def save_job(project_root: Path, job: EditJob) -> None:
    """Atomically persist a job sidecar. Overwrites on re-save."""
    path = job_sidecar_path(project_root, job.job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(job.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)


def load_job(project_root: Path, job_id: str) -> EditJob:
    path = job_sidecar_path(project_root, job_id)
    return EditJob.model_validate_json(path.read_text(encoding="utf-8"))


def list_jobs(project_root: Path) -> list[EditJob]:
    """Return all jobs in this project's edit_jobs/ dir, sorted by created_at."""
    edit_dir = project_root / "edit_jobs"
    if not edit_dir.exists():
        return []
    jobs: list[EditJob] = []
    for p in edit_dir.glob("*.json"):
        if p.name.endswith(".json.tmp"):
            continue
        try:
            jobs.append(EditJob.model_validate_json(p.read_text(encoding="utf-8")))
        except Exception:
            # Corrupt sidecar — skip rather than crash the listing.
            continue
    jobs.sort(key=lambda j: j.created_at)
    return jobs
```

- [ ] **Step 1.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_job_queue.py -v`
Expected: 7 passed.

- [ ] **Step 1.5: Commit**

```bash
git add src/pipeline/dashboard/job_queue.py tests/unit/test_job_queue.py
git commit -m "feat(dashboard): EditJob/SubActionResult models + sidecar I/O"
```

---

## Task 2: `JobQueue` core — submit + per-project consumer loop

**Files:**
- Modify: `src/pipeline/dashboard/job_queue.py`
- Test: `tests/unit/test_job_queue.py` (extend)

The queue serializes jobs *within* one project (FIFO, single consumer coroutine) and runs them in *parallel* across projects. The actual agent invocation is delegated to an `AgentRunner` callable injected at construction time so tests can pass a fake.

- [ ] **Step 2.1: Add the runner-protocol + JobQueue tests**

Append to `tests/unit/test_job_queue.py`:

```python
import asyncio

from pipeline.dashboard.job_queue import JobQueue


class FakeRunner:
    """Records run() calls and produces a deterministic, configurable result."""

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
    """A fake projects root with one project subdir."""
    proj = tmp_path / "projects" / "42"
    proj.mkdir(parents=True)
    return tmp_path / "projects"


@pytest.mark.asyncio
async def test_submit_runs_one_job_to_completion(project_tree: Path):
    runner = FakeRunner()
    queue = JobQueue(projects_root=project_tree, runner=runner)
    await queue.start()
    job = EditJob(job_id="j1", project_id="42", tokens=["@s9"], instruction="x")

    await queue.submit(job)
    await queue.wait_idle("42", timeout=2.0)

    loaded = load_job(project_tree / "42", "j1")
    assert loaded.status == "done"
    assert loaded.started_at is not None
    assert loaded.finished_at is not None
    assert len(loaded.sub_action_results) == 1
    assert runner.calls[0].job_id == "j1"

    await queue.shutdown()


@pytest.mark.asyncio
async def test_per_project_fifo_serialization(project_tree: Path):
    """Two jobs for the same project run sequentially, not concurrently."""
    runner = FakeRunner(sleep_sec=0.05)
    queue = JobQueue(projects_root=project_tree, runner=runner)
    await queue.start()

    j1 = EditJob(job_id="j1", project_id="42", tokens=[], instruction="a")
    j2 = EditJob(job_id="j2", project_id="42", tokens=[], instruction="b")
    await queue.submit(j1)
    await queue.submit(j2)
    await queue.wait_idle("42", timeout=2.0)

    # Verify FIFO order via the runner's call log.
    assert [c.job_id for c in runner.calls] == ["j1", "j2"]
    await queue.shutdown()


@pytest.mark.asyncio
async def test_parallel_across_projects(project_tree: Path):
    """Jobs for different projects run concurrently — total wall time ≈ one job, not two."""
    (project_tree / "43").mkdir()
    runner = FakeRunner(sleep_sec=0.2)
    queue = JobQueue(projects_root=project_tree, runner=runner)
    await queue.start()

    j1 = EditJob(job_id="ja", project_id="42", tokens=[], instruction="x")
    j2 = EditJob(job_id="jb", project_id="43", tokens=[], instruction="y")

    t0 = asyncio.get_event_loop().time()
    await queue.submit(j1)
    await queue.submit(j2)
    await asyncio.gather(
        queue.wait_idle("42", timeout=2.0),
        queue.wait_idle("43", timeout=2.0),
    )
    elapsed = asyncio.get_event_loop().time() - t0
    # Two 0.2s jobs in parallel → ~0.2s wall; serial would be ~0.4s.
    assert elapsed < 0.35, f"expected parallel execution, got {elapsed:.2f}s"
    await queue.shutdown()


@pytest.mark.asyncio
async def test_failed_job_marked_failed_and_queue_recovers(project_tree: Path):
    runner = FakeRunner(succeed=False)
    queue = JobQueue(projects_root=project_tree, runner=runner)
    await queue.start()

    j1 = EditJob(job_id="bad", project_id="42", tokens=[], instruction="x")
    await queue.submit(j1)
    await queue.wait_idle("42", timeout=2.0)

    loaded = load_job(project_tree / "42", "bad")
    assert loaded.status == "failed"
    # Submitting a second job should still work — queue not stuck.
    runner.succeed = True
    j2 = EditJob(job_id="good", project_id="42", tokens=[], instruction="y")
    await queue.submit(j2)
    await queue.wait_idle("42", timeout=2.0)
    assert load_job(project_tree / "42", "good").status == "done"
    await queue.shutdown()
```

- [ ] **Step 2.2: Run the new tests — expect ImportError**

Run: `uv run pytest tests/unit/test_job_queue.py -v -k "submit or fifo or parallel or failed"`
Expected: ImportError on `JobQueue`.

- [ ] **Step 2.3: Add the `AgentRunner` Protocol + `JobQueue` to `job_queue.py`**

Append to `src/pipeline/dashboard/job_queue.py`:

```python
import asyncio
from typing import Protocol

import structlog

logger = structlog.get_logger()


class AgentRunner(Protocol):
    """Strategy for running one job's agent. Production: claude -p subprocess.
    Tests: a fake that records calls and produces canned results."""

    async def run(self, job: EditJob, project_root: Path) -> list[SubActionResult]:
        ...


class JobQueue:
    """Per-project asyncio queue with one consumer coroutine per project.

    Lifecycle:
      queue = JobQueue(projects_root=..., runner=...)
      await queue.start()
      ...
      await queue.shutdown()
    """

    def __init__(self, *, projects_root: Path, runner: AgentRunner) -> None:
        self._projects_root = projects_root
        self._runner = runner
        self._queues: dict[str, asyncio.Queue[EditJob]] = {}
        self._consumers: dict[str, asyncio.Task[None]] = {}
        self._idle_events: dict[str, asyncio.Event] = {}
        self._running_jobs: dict[str, EditJob] = {}  # one in-flight job per project
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self) -> None:
        """Marker for explicit lifecycle. Consumers are lazy-spawned on first submit."""
        self._started = True

    async def shutdown(self) -> None:
        """Cancel all consumer tasks and clear state."""
        for task in self._consumers.values():
            task.cancel()
        for task in self._consumers.values():
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._queues.clear()
        self._consumers.clear()
        self._idle_events.clear()
        self._running_jobs.clear()
        self._started = False

    async def submit(self, job: EditJob) -> None:
        """Persist the job sidecar and enqueue for that project's consumer."""
        project_root = self._projects_root / job.project_id
        save_job(project_root, job)
        async with self._lock:
            self._ensure_consumer(job.project_id)
            self._idle_events[job.project_id].clear()
            await self._queues[job.project_id].put(job)
        logger.info("jobqueue.submit", job_id=job.job_id, project_id=job.project_id)

    async def wait_idle(self, project_id: str, *, timeout: float) -> None:
        """Wait until the given project's queue is drained AND the consumer is between jobs."""
        ev = self._idle_events.get(project_id)
        if ev is None:
            return
        await asyncio.wait_for(ev.wait(), timeout=timeout)

    def _ensure_consumer(self, project_id: str) -> None:
        if project_id in self._consumers:
            return
        self._queues[project_id] = asyncio.Queue()
        self._idle_events[project_id] = asyncio.Event()
        self._idle_events[project_id].set()  # idle until first job lands
        self._consumers[project_id] = asyncio.create_task(
            self._consume_loop(project_id),
            name=f"jobqueue-{project_id}",
        )

    async def _consume_loop(self, project_id: str) -> None:
        queue = self._queues[project_id]
        idle = self._idle_events[project_id]
        try:
            while True:
                job = await queue.get()
                idle.clear()
                try:
                    await self._run_job(job)
                finally:
                    queue.task_done()
                    if queue.empty():
                        idle.set()
        except asyncio.CancelledError:
            raise

    async def _run_job(self, job: EditJob) -> None:
        project_root = self._projects_root / job.project_id
        job.status = "running"
        job.started_at = datetime.now().isoformat(timespec="seconds")
        save_job(project_root, job)
        self._running_jobs[job.project_id] = job
        try:
            results = await self._runner.run(job, project_root)
            job.sub_action_results = results
            job.status = "done"
        except Exception as exc:
            logger.warning("jobqueue.run.failed", job_id=job.job_id, error=str(exc))
            job.status = "failed"
        finally:
            job.finished_at = datetime.now().isoformat(timespec="seconds")
            save_job(project_root, job)
            self._running_jobs.pop(job.project_id, None)
```

- [ ] **Step 2.4: Add `pytest-asyncio` config if not already present**

Open `pyproject.toml` and verify `[tool.pytest.ini_options]` enables `asyncio_mode = "auto"`. If not, add:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

If it's already set, skip this step. Then run `uv sync` to ensure pytest-asyncio is installed:

```bash
uv add --dev pytest-asyncio
```

Skip the install step if `pytest-asyncio` already appears in `pyproject.toml`'s dev dependencies.

- [ ] **Step 2.5: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_job_queue.py -v`
Expected: 11 passed (7 from Task 1 + 4 new).

- [ ] **Step 2.6: Commit**

```bash
git add src/pipeline/dashboard/job_queue.py tests/unit/test_job_queue.py pyproject.toml
git commit -m "feat(dashboard): JobQueue with per-project asyncio consumer loops"
```

---

## Task 3: `JobQueue.cancel` + crash-recovery on startup

**Files:**
- Modify: `src/pipeline/dashboard/job_queue.py`
- Test: `tests/unit/test_job_queue.py` (extend)

Cancel: signal the in-flight runner via an `asyncio.CancelledError` raised inside `_run_job`. The runner is responsible for terminating any subprocess it spawned. Crash recovery: on startup scan, mark any sidecar with `status == "running"` as `interrupted` (these are leftover from a previous process that died mid-job).

- [ ] **Step 3.1: Add cancel + recovery tests**

Append to `tests/unit/test_job_queue.py`:

```python
class CancellableRunner:
    """Runner that sleeps until cancelled. Records whether cancellation was observed."""

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
async def test_cancel_marks_job_cancelled_and_runner_observes_cancellation(project_tree: Path):
    runner = CancellableRunner()
    queue = JobQueue(projects_root=project_tree, runner=runner)
    await queue.start()

    job = EditJob(job_id="long", project_id="42", tokens=[], instruction="x")
    await queue.submit(job)
    await asyncio.wait_for(runner.entered.wait(), timeout=1.0)

    cancelled = await queue.cancel("42", "long")
    assert cancelled is True
    # Wait for the consumer to finish processing the cancellation.
    await queue.wait_idle("42", timeout=2.0)

    loaded = load_job(project_tree / "42", "long")
    assert loaded.status == "cancelled"
    assert runner.cancelled is True
    await queue.shutdown()


@pytest.mark.asyncio
async def test_cancel_returns_false_when_job_not_running(project_tree: Path):
    runner = FakeRunner()
    queue = JobQueue(projects_root=project_tree, runner=runner)
    await queue.start()
    cancelled = await queue.cancel("42", "nonexistent")
    assert cancelled is False
    await queue.shutdown()


def test_reload_on_startup_marks_running_as_interrupted(project_tree: Path):
    """Sidecars left in 'running' state from a prior process get marked interrupted."""
    proj = project_tree / "42"
    save_job(proj, EditJob(
        job_id="orphan", project_id="42", tokens=[], instruction="x", status="running"
    ))
    save_job(proj, EditJob(
        job_id="finished", project_id="42", tokens=[], instruction="y", status="done"
    ))

    runner = FakeRunner()
    queue = JobQueue(projects_root=project_tree, runner=runner)
    queue.reload_on_startup()

    assert load_job(proj, "orphan").status == "interrupted"
    assert load_job(proj, "finished").status == "done"


def test_reload_on_startup_handles_missing_projects_dir(tmp_path: Path):
    """If projects/ doesn't exist yet, reload is a no-op."""
    runner = FakeRunner()
    queue = JobQueue(projects_root=tmp_path / "nonexistent", runner=runner)
    queue.reload_on_startup()  # must not raise
```

- [ ] **Step 3.2: Run the new tests — expect AttributeError**

Run: `uv run pytest tests/unit/test_job_queue.py -v -k "cancel or reload"`
Expected: failures because `JobQueue.cancel` and `JobQueue.reload_on_startup` don't exist yet.

- [ ] **Step 3.3: Add `cancel` and `reload_on_startup` to `JobQueue`**

Open `src/pipeline/dashboard/job_queue.py`. The `_run_job` method already saves status changes; we just need to convert `CancelledError` into a `cancelled` status. Replace the existing `_run_job` method body with:

```python
    async def _run_job(self, job: EditJob) -> None:
        project_root = self._projects_root / job.project_id
        job.status = "running"
        job.started_at = datetime.now().isoformat(timespec="seconds")
        save_job(project_root, job)
        self._running_jobs[job.project_id] = job

        run_task = asyncio.current_task()
        # Track this task so cancel() can target it specifically.
        self._cancel_targets[job.project_id] = (job.job_id, run_task)

        try:
            results = await self._runner.run(job, project_root)
            job.sub_action_results = results
            job.status = "done"
        except asyncio.CancelledError:
            job.status = "cancelled"
            logger.info("jobqueue.run.cancelled", job_id=job.job_id)
            # Don't re-raise — we want the consumer loop to keep running.
        except Exception as exc:
            logger.warning("jobqueue.run.failed", job_id=job.job_id, error=str(exc))
            job.status = "failed"
        finally:
            job.finished_at = datetime.now().isoformat(timespec="seconds")
            save_job(project_root, job)
            self._running_jobs.pop(job.project_id, None)
            self._cancel_targets.pop(job.project_id, None)
```

In `JobQueue.__init__`, add the cancel-targets map (insert next to `self._running_jobs`):

```python
        self._cancel_targets: dict[str, tuple[str, asyncio.Task[None]]] = {}
```

Add the `cancel` method (after `wait_idle`):

```python
    async def cancel(self, project_id: str, job_id: str) -> bool:
        """Cancel the in-flight job for this project if its id matches.

        Returns True if a cancellation was issued, False if no matching
        in-flight job was found (already finished, never queued, or wrong id).
        """
        target = self._cancel_targets.get(project_id)
        if target is None or target[0] != job_id:
            return False
        _, task = target
        task.cancel()
        return True
```

Add `reload_on_startup` (synchronous; called once before consumers start):

```python
    def reload_on_startup(self) -> None:
        """Mark any sidecar left in 'running' state as 'interrupted'.

        Called once at FastAPI startup before any consumers begin pulling
        jobs. These leftovers are from a prior dashboard process that died
        mid-job; per spec, we do not auto-resume.
        """
        if not self._projects_root.exists():
            return
        for project_dir in self._projects_root.iterdir():
            if not project_dir.is_dir():
                continue
            for job in list_jobs(project_dir):
                if job.status == "running":
                    job.status = "interrupted"
                    job.finished_at = datetime.now().isoformat(timespec="seconds")
                    save_job(project_dir, job)
                    logger.info(
                        "jobqueue.reload.interrupted",
                        project_id=project_dir.name,
                        job_id=job.job_id,
                    )
```

Important: `_run_job` no longer re-raises `CancelledError`, but `_consume_loop` may itself be cancelled at shutdown. The existing `try/except asyncio.CancelledError: raise` block in `_consume_loop` already handles that. Verify visually that `_consume_loop` still raises on its own cancellation.

- [ ] **Step 3.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_job_queue.py -v`
Expected: 15 passed.

- [ ] **Step 3.5: Commit**

```bash
git add src/pipeline/dashboard/job_queue.py tests/unit/test_job_queue.py
git commit -m "feat(dashboard): JobQueue cancel + crash-recovery on startup"
```

---

## Task 4: CLI — `pipeline subtitle set`

**Files:**
- Modify: `src/pipeline/storyboard.py` (add `subtitle_override` field to `Scene`)
- Create: `src/pipeline/cli_subtitle.py`
- Modify: `src/pipeline/cli.py` (register subapp)
- Test: `tests/unit/test_cli_subtitle.py` (new)

`pipeline subtitle set --project-id X --scene sN --text "..."` writes a per-scene `subtitle_override` field. The compose stage already burns subtitles from a generated SRT; respecting the override is a Plan 5 polish task. For Plan 3 we ship the data-mutation path; the agent calls `compose reburn` afterwards (which is documented in `agent_prompt.md`).

- [ ] **Step 4.1: Write the CLI tests**

Create `tests/unit/test_cli_subtitle.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_subtitle import subtitle_app
from pipeline.storyboard import Scene, Storyboard


def _write_minimal_storyboard(work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
        Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
    ])
    sb_path = work_dir / "storyboard.json"
    sb.save(sb_path)
    (work_dir / "context.json").write_text(
        json.dumps({"project_id": 42, "source_url": "x", "locale": "zh-TW",
                    "work_dir": str(work_dir)}),
        encoding="utf-8",
    )
    return sb_path


@pytest.fixture
def project_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out_root = tmp_path / "output"
    proj = out_root / "projects" / "42"
    _write_minimal_storyboard(proj)
    monkeypatch.setattr(
        "pipeline.cli_subtitle.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    return proj


def test_set_writes_subtitle_override(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(subtitle_app, [
        "set", "--project-id", "42", "--scene", "s1", "--text", "hello world",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.get_scene("s1").subtitle_override == "hello world"
    assert sb.get_scene("s2").subtitle_override is None


def test_set_replaces_existing_override(project_tree: Path):
    runner = CliRunner()
    runner.invoke(subtitle_app, ["set", "--project-id", "42", "--scene", "s1", "--text", "v1"])
    runner.invoke(subtitle_app, ["set", "--project-id", "42", "--scene", "s1", "--text", "v2"])
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.get_scene("s1").subtitle_override == "v2"


def test_set_rejects_unknown_scene(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(subtitle_app, [
        "set", "--project-id", "42", "--scene", "s99", "--text", "x",
    ])
    assert result.exit_code != 0
    assert "s99" in result.output


def test_set_rejects_missing_storyboard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "pipeline.cli_subtitle.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": tmp_path / "output"})(),
    )
    runner = CliRunner()
    result = runner.invoke(subtitle_app, [
        "set", "--project-id", "999", "--scene", "s1", "--text", "x",
    ])
    assert result.exit_code != 0
    assert "storyboard" in result.output.lower()
```

- [ ] **Step 4.2: Run the tests — expect ImportError**

Run: `uv run pytest tests/unit/test_cli_subtitle.py -v`
Expected: ImportError on `pipeline.cli_subtitle`.

- [ ] **Step 4.3: Add `subtitle_override` field to `Scene`**

In `src/pipeline/storyboard.py`, modify the `Scene` dataclass (around line 104-117). Find:

```python
    pause_after_sec: float = 0
    compartment: dict[str, Any] | None = None
    narration_source: NarrationSource | None = None
```

Replace with:

```python
    pause_after_sec: float = 0
    compartment: dict[str, Any] | None = None
    narration_source: NarrationSource | None = None
    subtitle_override: str | None = None
```

In `Scene.from_dict` (around line 119-134), find:

```python
            narration_source=narration_source,
        )
```

Replace with:

```python
            narration_source=narration_source,
            subtitle_override=data.get("subtitle_override"),
        )
```

In `Scene.to_dict` (around line 136-153), find:

```python
        if self.narration_source is not None:
            out["narration_source"] = self.narration_source.to_dict()
        return out
```

Replace with:

```python
        if self.narration_source is not None:
            out["narration_source"] = self.narration_source.to_dict()
        if self.subtitle_override is not None:
            out["subtitle_override"] = self.subtitle_override
        return out
```

- [ ] **Step 4.4: Create `cli_subtitle.py`**

Create `src/pipeline/cli_subtitle.py`:

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from pipeline.config import PipelineConfig
from pipeline.session_log import SessionEntry, append_session, new_session_id
from pipeline.storyboard import Storyboard

subtitle_app = typer.Typer(name="subtitle", help="Per-scene subtitle override commands")


@subtitle_app.callback()
def _main() -> None:
    """Per-scene subtitle override commands."""


def _resolve_work_dir(project_id: int) -> Path:
    return PipelineConfig().OUTPUT_DIR / "projects" / str(project_id)


def _load_storyboard(project_id: int) -> tuple[Path, Storyboard]:
    work = _resolve_work_dir(project_id)
    sb_path = work / "storyboard.json"
    if not sb_path.exists():
        typer.echo(f"storyboard.json not found at {sb_path}", err=True)
        raise typer.Exit(code=1)
    return sb_path, Storyboard.load(sb_path)


@subtitle_app.command("set")
def set_subtitle(
    project_id: int = typer.Option(..., "--project-id"),
    scene: str = typer.Option(..., "--scene", help="Scene id (e.g. s9)"),
    text: str = typer.Option(..., "--text", help="Subtitle text override"),
) -> None:
    """Write a subtitle_override on the named scene. Idempotent.

    The override mutates storyboard state only. Run `pipeline compose reburn`
    afterwards to re-burn subtitles into the final video.
    """
    sb_path, sb = _load_storyboard(project_id)
    target = sb.get_scene(scene)
    if target is None:
        typer.echo(f"Scene {scene!r} not found in storyboard", err=True)
        raise typer.Exit(code=1)
    target.subtitle_override = text
    sb.save(sb_path)

    summary = f"subtitle set {scene}: {text[:40]}"
    typer.echo(summary)
    work = _resolve_work_dir(project_id)
    append_session(work, SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"subtitle set --scene {scene} --text {text!r}",
        summary=summary,
    ))
```

- [ ] **Step 4.5: Register `subtitle_app` in `cli.py`**

Open `src/pipeline/cli.py`. Find the existing import line:

```python
from pipeline.cli_storyteller import storytell_app
```

Add immediately below it:

```python
from pipeline.cli_subtitle import subtitle_app
```

Find the `app.add_typer` block (around line 35-47). Add after the `transition_app` registration:

```python
app.add_typer(subtitle_app, name="subtitle")
```

- [ ] **Step 4.6: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_cli_subtitle.py -v`
Expected: 4 passed.

- [ ] **Step 4.7: Verify CLI registration**

Run: `uv run pipeline subtitle --help`
Expected: typer help output listing the `set` subcommand.

- [ ] **Step 4.8: Commit**

```bash
git add src/pipeline/storyboard.py src/pipeline/cli_subtitle.py src/pipeline/cli.py tests/unit/test_cli_subtitle.py
git commit -m "feat(cli): pipeline subtitle set command + Scene.subtitle_override"
```

---

## Task 5: CLI — `pipeline overlay set`

**Files:**
- Create: `src/pipeline/cli_overlay.py`
- Modify: `src/pipeline/cli.py`
- Test: `tests/unit/test_cli_overlay.py` (new)

`Scene.overlay` is `dict[str, Any] | None`. The verb writes `text` while preserving other keys (e.g. `position`, `style`).

- [ ] **Step 5.1: Write the CLI tests**

Create `tests/unit/test_cli_overlay.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_overlay import overlay_app
from pipeline.storyboard import Scene, Storyboard


@pytest.fixture
def project_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out_root = tmp_path / "output"
    proj = out_root / "projects" / "42"
    proj.mkdir(parents=True)
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="a", narration_est_sec=1.0),
        Scene(id="s2", section="content", narration="b", narration_est_sec=1.0,
              overlay={"text": "old", "position": "lower-third", "style": "bold"}),
    ])
    sb.save(proj / "storyboard.json")
    (proj / "context.json").write_text(
        json.dumps({"project_id": 42, "source_url": "x", "locale": "zh-TW",
                    "work_dir": str(proj)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "pipeline.cli_overlay.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    return proj


def test_set_creates_overlay_when_absent(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(overlay_app, [
        "set", "--project-id", "42", "--scene", "s1", "--text", "hello",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.get_scene("s1").overlay == {"text": "hello"}


def test_set_preserves_existing_overlay_keys(project_tree: Path):
    """When overlay already has position/style, only `text` changes."""
    runner = CliRunner()
    result = runner.invoke(overlay_app, [
        "set", "--project-id", "42", "--scene", "s2", "--text", "new text",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    overlay = sb.get_scene("s2").overlay
    assert overlay == {"text": "new text", "position": "lower-third", "style": "bold"}


def test_set_rejects_unknown_scene(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(overlay_app, [
        "set", "--project-id", "42", "--scene", "s99", "--text", "x",
    ])
    assert result.exit_code != 0
    assert "s99" in result.output
```

- [ ] **Step 5.2: Run the tests — expect ImportError**

Run: `uv run pytest tests/unit/test_cli_overlay.py -v`
Expected: ImportError on `pipeline.cli_overlay`.

- [ ] **Step 5.3: Create `cli_overlay.py`**

Create `src/pipeline/cli_overlay.py`:

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from pipeline.config import PipelineConfig
from pipeline.session_log import SessionEntry, append_session, new_session_id
from pipeline.storyboard import Storyboard

overlay_app = typer.Typer(name="overlay", help="Per-scene overlay text commands")


@overlay_app.callback()
def _main() -> None:
    """Per-scene overlay text commands."""


def _resolve_work_dir(project_id: int) -> Path:
    return PipelineConfig().OUTPUT_DIR / "projects" / str(project_id)


def _load_storyboard(project_id: int) -> tuple[Path, Storyboard]:
    work = _resolve_work_dir(project_id)
    sb_path = work / "storyboard.json"
    if not sb_path.exists():
        typer.echo(f"storyboard.json not found at {sb_path}", err=True)
        raise typer.Exit(code=1)
    return sb_path, Storyboard.load(sb_path)


@overlay_app.command("set")
def set_overlay(
    project_id: int = typer.Option(..., "--project-id"),
    scene: str = typer.Option(..., "--scene", help="Scene id (e.g. s9)"),
    text: str = typer.Option(..., "--text", help="Overlay text"),
) -> None:
    """Set the overlay text on the named scene. Preserves other overlay keys.

    Mutates storyboard state only. Run `pipeline compose rescene --scene <id>`
    afterwards to re-render the scene clip with the new overlay.
    """
    sb_path, sb = _load_storyboard(project_id)
    target = sb.get_scene(scene)
    if target is None:
        typer.echo(f"Scene {scene!r} not found in storyboard", err=True)
        raise typer.Exit(code=1)
    existing = dict(target.overlay) if target.overlay else {}
    existing["text"] = text
    target.overlay = existing
    sb.save(sb_path)

    summary = f"overlay set {scene}: {text[:40]}"
    typer.echo(summary)
    work = _resolve_work_dir(project_id)
    append_session(work, SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"overlay set --scene {scene} --text {text!r}",
        summary=summary,
    ))
```

- [ ] **Step 5.4: Register `overlay_app` in `cli.py`**

Open `src/pipeline/cli.py`. Below the `from pipeline.cli_subtitle import subtitle_app` line, add:

```python
from pipeline.cli_overlay import overlay_app
```

Below the `app.add_typer(subtitle_app, name="subtitle")` line, add:

```python
app.add_typer(overlay_app, name="overlay")
```

- [ ] **Step 5.5: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_cli_overlay.py -v`
Expected: 3 passed.

- [ ] **Step 5.6: Commit**

```bash
git add src/pipeline/cli_overlay.py src/pipeline/cli.py tests/unit/test_cli_overlay.py
git commit -m "feat(cli): pipeline overlay set command"
```

---

## Task 6: CLI — `pipeline narration regen`

**Files:**
- Modify: `src/pipeline/cli_narration.py` (add new command to existing `narration_app`)
- Test: `tests/unit/test_cli_narration_regen.py` (new)

`Scene.narration` is a string; `regen` overwrites it. Re-running TTS for the scene happens via `compose rescene` invoked by the agent.

- [ ] **Step 6.1: Write the CLI tests**

Create `tests/unit/test_cli_narration_regen.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_narration import narration_app
from pipeline.storyboard import Scene, Storyboard


@pytest.fixture
def project_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out_root = tmp_path / "output"
    proj = out_root / "projects" / "42"
    proj.mkdir(parents=True)
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="original text", narration_est_sec=1.0),
        Scene(id="s2", section="content", narration="another", narration_est_sec=1.0),
    ])
    sb.save(proj / "storyboard.json")
    (proj / "context.json").write_text(
        json.dumps({"project_id": 42, "source_url": "x", "locale": "zh-TW",
                    "work_dir": str(proj)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "pipeline.cli_narration.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    return proj


def test_regen_overwrites_narration_text(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "regen", "--project-id", "42", "--scene", "s1", "--text", "rewritten",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.get_scene("s1").narration == "rewritten"
    # Other scenes untouched.
    assert sb.get_scene("s2").narration == "another"


def test_regen_rejects_unknown_scene(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "regen", "--project-id", "42", "--scene", "s99", "--text", "x",
    ])
    assert result.exit_code != 0
    assert "s99" in result.output


def test_regen_preserves_narration_source(project_tree: Path):
    """If the scene has a narration_source override, regen still writes new
    narration text — leaving the source override intact."""
    sb = Storyboard.load(project_tree / "storyboard.json")
    from pipeline.storyboard import NarrationSource
    sb.get_scene("s1").narration_source = NarrationSource(engine="edge", voice="zh-TW-HsiaoChenNeural")
    sb.save(project_tree / "storyboard.json")

    runner = CliRunner()
    result = runner.invoke(narration_app, [
        "regen", "--project-id", "42", "--scene", "s1", "--text", "fresh",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.get_scene("s1").narration == "fresh"
    assert sb.get_scene("s1").narration_source is not None
    assert sb.get_scene("s1").narration_source.engine == "edge"
```

- [ ] **Step 6.2: Run the tests — expect failure (no `regen` subcommand yet)**

Run: `uv run pytest tests/unit/test_cli_narration_regen.py -v`
Expected: failures with exit codes ≠ 0 because `narration regen` is not registered.

- [ ] **Step 6.3: Add the `regen` command to `cli_narration.py`**

Open `src/pipeline/cli_narration.py`. After the existing `set_source` command (around line 121, end of file), append:

```python
@narration_app.command("regen")
def regen(
    project_id: int = typer.Option(..., "--project-id"),
    scene: str = typer.Option(..., "--scene", help="Scene id (e.g. s9)"),
    text: str = typer.Option(..., "--text", help="New narration text"),
) -> None:
    """Overwrite the narration text on the named scene.

    Mutates storyboard state only. Run `pipeline compose rescene --scene <id>`
    afterwards to re-run TTS and re-render the scene clip.
    """
    sb_path, sb = _load_storyboard(project_id)
    target = sb.get_scene(scene)
    if target is None:
        typer.echo(f"Scene {scene!r} not found in storyboard", err=True)
        raise typer.Exit(code=1)
    target.narration = text
    sb.save(sb_path)

    summary = f"narration regen {scene}: {text[:40]}"
    typer.echo(summary)
    work = _resolve_work_dir(project_id)
    append_session(work, SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"narration regen --scene {scene} --text {text!r}",
        summary=summary,
    ))
```

- [ ] **Step 6.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_cli_narration_regen.py -v`
Expected: 3 passed.

- [ ] **Step 6.5: Commit**

```bash
git add src/pipeline/cli_narration.py tests/unit/test_cli_narration_regen.py
git commit -m "feat(cli): pipeline narration regen command"
```

---

## Task 7: CLI — `pipeline image regen`

**Files:**
- Create: `src/pipeline/cli_image.py`
- Modify: `src/pipeline/cli.py`
- Test: `tests/unit/test_cli_image.py` (new)

`pipeline image regen --project-id X --scene sN --prompt "..." --tier draft|production` updates `scene.visual["prompt"]` and `visual["tier"]`, then deletes the cached scene image and the cached scene clip(s) so the next `compose rescene` re-runs image generation. Mutate-only; the agent calls `compose rescene` to actually regenerate.

- [ ] **Step 7.1: Write the CLI tests**

Create `tests/unit/test_cli_image.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pipeline.cli_image import image_app
from pipeline.storyboard import Scene, Storyboard


@pytest.fixture
def project_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out_root = tmp_path / "output"
    proj = out_root / "projects" / "42"
    proj.mkdir(parents=True)

    # Storyboard with one scene that already has a visual prompt.
    sb = Storyboard(scenes=[
        Scene(id="s1", section="content", narration="a", narration_est_sec=1.0,
              visual={"type": "ai_image", "prompt": "old prompt", "tier": "draft"}),
        Scene(id="s2", section="content", narration="b", narration_est_sec=1.0),
    ])
    sb.save(proj / "storyboard.json")
    (proj / "context.json").write_text(
        json.dumps({"project_id": 42, "source_url": "x", "locale": "zh-TW",
                    "work_dir": str(proj)}),
        encoding="utf-8",
    )

    # Pre-create cached image + scene clip files we expect to be deleted.
    (proj / "images").mkdir()
    (proj / "images" / "s1.png").write_bytes(b"fake png")
    (proj / "compose" / "scenes").mkdir(parents=True)
    (proj / "compose" / "scenes" / "s1_final.mp4").write_bytes(b"x")
    (proj / "compose" / "scenes" / "s1_final_no_overlay.mp4").write_bytes(b"y")

    monkeypatch.setattr(
        "pipeline.cli_image.PipelineConfig",
        lambda: type("C", (), {"OUTPUT_DIR": out_root})(),
    )
    return proj


def test_regen_updates_visual_prompt_and_tier(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(image_app, [
        "regen", "--project-id", "42", "--scene", "s1",
        "--prompt", "a man on a rainy street",
        "--tier", "production",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    visual = sb.get_scene("s1").visual
    assert visual["prompt"] == "a man on a rainy street"
    assert visual["tier"] == "production"
    # Existing keys preserved.
    assert visual["type"] == "ai_image"


def test_regen_deletes_cached_image_and_scene_clips(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(image_app, [
        "regen", "--project-id", "42", "--scene", "s1",
        "--prompt", "x", "--tier", "draft",
    ])
    assert result.exit_code == 0, result.output
    assert not (project_tree / "images" / "s1.png").exists()
    assert not (project_tree / "compose" / "scenes" / "s1_final.mp4").exists()
    assert not (project_tree / "compose" / "scenes" / "s1_final_no_overlay.mp4").exists()


def test_regen_creates_visual_dict_when_scene_has_none(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(image_app, [
        "regen", "--project-id", "42", "--scene", "s2",
        "--prompt", "fresh prompt", "--tier", "draft",
    ])
    assert result.exit_code == 0, result.output
    sb = Storyboard.load(project_tree / "storyboard.json")
    assert sb.get_scene("s2").visual["prompt"] == "fresh prompt"
    assert sb.get_scene("s2").visual["tier"] == "draft"


def test_regen_rejects_unknown_tier(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(image_app, [
        "regen", "--project-id", "42", "--scene", "s1",
        "--prompt", "x", "--tier", "platinum",
    ])
    assert result.exit_code != 0
    assert "platinum" in result.output or "tier" in result.output.lower()


def test_regen_rejects_unknown_scene(project_tree: Path):
    runner = CliRunner()
    result = runner.invoke(image_app, [
        "regen", "--project-id", "42", "--scene", "s99",
        "--prompt", "x", "--tier", "draft",
    ])
    assert result.exit_code != 0
    assert "s99" in result.output


def test_regen_handles_missing_image_cache_gracefully(project_tree: Path):
    """First-time regen: no cached image yet — must not error."""
    (project_tree / "images" / "s1.png").unlink()
    runner = CliRunner()
    result = runner.invoke(image_app, [
        "regen", "--project-id", "42", "--scene", "s1",
        "--prompt", "x", "--tier", "draft",
    ])
    assert result.exit_code == 0, result.output
```

- [ ] **Step 7.2: Run the tests — expect ImportError**

Run: `uv run pytest tests/unit/test_cli_image.py -v`
Expected: ImportError on `pipeline.cli_image`.

- [ ] **Step 7.3: Create `cli_image.py`**

Create `src/pipeline/cli_image.py`:

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from pipeline.config import PipelineConfig
from pipeline.session_log import SessionEntry, append_session, new_session_id
from pipeline.storyboard import Storyboard

image_app = typer.Typer(name="image", help="Per-scene image regen commands")


@image_app.callback()
def _main() -> None:
    """Per-scene image regen commands."""


_VALID_TIERS = {"draft", "production"}


def _resolve_work_dir(project_id: int) -> Path:
    return PipelineConfig().OUTPUT_DIR / "projects" / str(project_id)


def _load_storyboard(project_id: int) -> tuple[Path, Storyboard]:
    work = _resolve_work_dir(project_id)
    sb_path = work / "storyboard.json"
    if not sb_path.exists():
        typer.echo(f"storyboard.json not found at {sb_path}", err=True)
        raise typer.Exit(code=1)
    return sb_path, Storyboard.load(sb_path)


def _delete_image_cache_for_scene(work_dir: Path, scene_id: str) -> None:
    """Delete the cached scene image and any cached scene clips so a
    subsequent `compose rescene` regenerates them from the new prompt."""
    images_dir = work_dir / "images"
    if images_dir.exists():
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            p = images_dir / f"{scene_id}{ext}"
            if p.exists():
                p.unlink()
    scenes_dir = work_dir / "compose" / "scenes"
    if scenes_dir.exists():
        for suffix in ("_final.mp4", "_final_no_overlay.mp4"):
            p = scenes_dir / f"{scene_id}{suffix}"
            if p.exists():
                p.unlink()


@image_app.command("regen")
def regen(
    project_id: int = typer.Option(..., "--project-id"),
    scene: str = typer.Option(..., "--scene", help="Scene id (e.g. s9)"),
    prompt: str = typer.Option(..., "--prompt", help="New image generation prompt"),
    tier: str = typer.Option(..., "--tier", help=f"One of: {', '.join(sorted(_VALID_TIERS))}"),
) -> None:
    """Update a scene's image prompt + tier and clear its image cache.

    Mutates storyboard + cache only. Run `pipeline compose rescene --scene <id>`
    afterwards to actually regenerate the image and recompose the scene.
    """
    if tier not in _VALID_TIERS:
        typer.echo(
            f"Unknown tier {tier!r}. Choose from: {', '.join(sorted(_VALID_TIERS))}",
            err=True,
        )
        raise typer.Exit(code=1)
    sb_path, sb = _load_storyboard(project_id)
    target = sb.get_scene(scene)
    if target is None:
        typer.echo(f"Scene {scene!r} not found in storyboard", err=True)
        raise typer.Exit(code=1)
    visual = dict(target.visual) if target.visual else {}
    visual["prompt"] = prompt
    visual["tier"] = tier
    target.visual = visual
    sb.save(sb_path)

    work = _resolve_work_dir(project_id)
    _delete_image_cache_for_scene(work, scene)

    summary = f"image regen {scene}: tier={tier} prompt={prompt[:40]}"
    typer.echo(summary)
    append_session(work, SessionEntry(
        session_id=new_session_id(),
        timestamp=datetime.now().isoformat(timespec="seconds"),
        command=f"image regen --scene {scene} --prompt {prompt!r} --tier {tier}",
        summary=summary,
    ))
```

- [ ] **Step 7.4: Register `image_app` in `cli.py`**

Open `src/pipeline/cli.py`. Below the `from pipeline.cli_overlay import overlay_app` line, add:

```python
from pipeline.cli_image import image_app
```

Below the `app.add_typer(overlay_app, name="overlay")` line, add:

```python
app.add_typer(image_app, name="image")
```

- [ ] **Step 7.5: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_cli_image.py -v`
Expected: 6 passed.

- [ ] **Step 7.6: Commit**

```bash
git add src/pipeline/cli_image.py src/pipeline/cli.py tests/unit/test_cli_image.py
git commit -m "feat(cli): pipeline image regen command"
```

---

## Task 8: Telegram — extended send helpers (`reply_to`, `reply_markup`, `send_photo`, `send_video`, `edit_message_text`)

**Files:**
- Modify: `src/pipeline/notify/telegram.py`
- Test: `tests/unit/test_telegram_extended_send.py` (new)

`TelegramNotifier.send` currently only takes `text`. We expand it without breaking the existing call sites. New helpers all return the API response dict (which includes `message_id`) so callers can hand the id back to `edit_message_text` later.

- [ ] **Step 8.1: Write the extended-send tests**

Create `tests/unit/test_telegram_extended_send.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from pipeline.notify.telegram import TelegramNotifier


class _MockTransport(httpx.MockTransport):
    """Records every request and returns canned 200 responses."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(
                200,
                json={"ok": True, "result": {"message_id": 12345}},
            )
        super().__init__(handler)


def _notifier_with_mock(monkeypatch: pytest.MonkeyPatch) -> tuple[TelegramNotifier, _MockTransport]:
    transport = _MockTransport()
    monkeypatch.setattr(
        "pipeline.notify.telegram._http_client",
        lambda: httpx.Client(transport=transport, timeout=10.0),
    )
    return TelegramNotifier(token="t", chat_id="c"), transport


def test_send_message_returns_message_id(monkeypatch: pytest.MonkeyPatch):
    notifier, transport = _notifier_with_mock(monkeypatch)
    result = notifier.send_message("hello")
    assert result == {"message_id": 12345}
    assert transport.requests[0].url.path.endswith("/sendMessage")


def test_send_message_with_reply_to_passes_param(monkeypatch: pytest.MonkeyPatch):
    notifier, transport = _notifier_with_mock(monkeypatch)
    notifier.send_message("hello", reply_to_message_id=999)
    body = transport.requests[0].read().decode()
    assert "reply_to_message_id" in body
    assert "999" in body


def test_send_message_with_reply_markup_serializes_inline_keyboard(monkeypatch: pytest.MonkeyPatch):
    notifier, transport = _notifier_with_mock(monkeypatch)
    keyboard = {"inline_keyboard": [[{"text": "Cancel", "callback_data": "cancel:job-1"}]]}
    notifier.send_message("queued", reply_markup=keyboard)
    body = transport.requests[0].read().decode()
    assert "callback_data" in body
    assert "cancel:job-1" in body


def test_edit_message_text_calls_correct_endpoint(monkeypatch: pytest.MonkeyPatch):
    notifier, transport = _notifier_with_mock(monkeypatch)
    notifier.edit_message_text(message_id=12345, text="updated")
    assert transport.requests[0].url.path.endswith("/editMessageText")
    body = transport.requests[0].read().decode()
    assert "12345" in body
    assert "updated" in body


def test_send_photo_uploads_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    notifier, transport = _notifier_with_mock(monkeypatch)
    photo = tmp_path / "test.png"
    photo.write_bytes(b"fake png bytes")
    result = notifier.send_photo(photo, caption="here it is")
    assert result == {"message_id": 12345}
    assert transport.requests[0].url.path.endswith("/sendPhoto")


def test_send_video_uploads_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    notifier, transport = _notifier_with_mock(monkeypatch)
    video = tmp_path / "test.mp4"
    video.write_bytes(b"fake mp4 bytes")
    result = notifier.send_video(video, caption="rendered")
    assert result == {"message_id": 12345}
    assert transport.requests[0].url.path.endswith("/sendVideo")


def test_legacy_send_method_still_works(monkeypatch: pytest.MonkeyPatch):
    """Existing `notifier.send(text)` callers must keep working unchanged."""
    notifier, transport = _notifier_with_mock(monkeypatch)
    notifier.send("legacy text")
    assert transport.requests[0].url.path.endswith("/sendMessage")


def test_http_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch):
    """All notifier methods swallow exceptions to avoid breaking callers."""
    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"ok": False, "description": "down"})

    monkeypatch.setattr(
        "pipeline.notify.telegram._http_client",
        lambda: httpx.Client(transport=httpx.MockTransport(failing_handler), timeout=10.0),
    )
    notifier = TelegramNotifier(token="t", chat_id="c")
    # Each of these must return None (or {}) and NOT raise.
    assert notifier.send_message("x") is None
    assert notifier.edit_message_text(message_id=1, text="y") is None
```

- [ ] **Step 8.2: Run the tests — expect failures**

Run: `uv run pytest tests/unit/test_telegram_extended_send.py -v`
Expected: failures because `send_message`, `edit_message_text`, `send_photo`, `send_video`, and `_http_client` don't exist yet.

- [ ] **Step 8.3: Refactor `telegram.py` — add `_http_client` factory, extend `send` paths, add new helpers**

Open `src/pipeline/notify/telegram.py`. Replace the entire file contents with:

```python
from __future__ import annotations

import json as _json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

_MDV2_ESCAPE = str.maketrans(
    {
        "_": r"\_",
        "*": r"\*",
        "[": r"\[",
        "]": r"\]",
        "(": r"\(",
        ")": r"\)",
        "~": r"\~",
        "`": r"\`",
        ">": r"\>",
        "#": r"\#",
        "+": r"\+",
        "-": r"\-",
        "=": r"\=",
        "|": r"\|",
        "{": r"\{",
        "}": r"\}",
        ".": r"\.",
        "!": r"\!",
    }
)


def _escape_mdv2(text: str) -> str:
    return text.translate(_MDV2_ESCAPE)


def _http_client() -> httpx.Client:
    """Factory that tests monkeypatch to inject a MockTransport."""
    return httpx.Client(timeout=10.0)


@dataclass(frozen=True)
class TelegramNotifier:
    token: str
    chat_id: str

    @classmethod
    def from_env(cls) -> "TelegramNotifier | None":
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return None
        return cls(token=token, chat_id=chat_id)

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.token}/{method}"

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        try:
            with _http_client() as client:
                response = client.post(self._api_url(method), json=payload)
        except Exception as exc:
            logger.warning("telegram.post.exception", method=method, error=str(exc))
            return None
        if response.status_code >= 400:
            logger.warning(
                "telegram.post.http_error",
                method=method,
                status=response.status_code,
                body=response.text[:200],
            )
            return None
        try:
            data = response.json()
        except Exception:
            return None
        if not data.get("ok"):
            return None
        return data.get("result", {})

    def _post_multipart(
        self,
        method: str,
        files: dict[str, tuple[str, bytes]],
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        try:
            with _http_client() as client:
                response = client.post(self._api_url(method), files=files, data=data)
        except Exception as exc:
            logger.warning("telegram.post.exception", method=method, error=str(exc))
            return None
        if response.status_code >= 400:
            logger.warning(
                "telegram.post.http_error",
                method=method,
                status=response.status_code,
                body=response.text[:200],
            )
            return None
        try:
            payload = response.json()
        except Exception:
            return None
        if not payload.get("ok"):
            return None
        return payload.get("result", {})

    def send_message(
        self,
        text: str,
        *,
        parse_mode: str = "MarkdownV2",
        reply_to_message_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Send a message. Returns {message_id, ...} on success, None on failure.

        `reply_markup` accepts an inline keyboard dict, e.g.:
            {"inline_keyboard": [[{"text": "Cancel", "callback_data": "cancel:42"}]]}
        """
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        if reply_markup is not None:
            payload["reply_markup"] = _json.dumps(reply_markup)
        return self._post("sendMessage", payload)

    def edit_message_text(
        self,
        *,
        message_id: int,
        text: str,
        parse_mode: str = "MarkdownV2",
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            payload["reply_markup"] = _json.dumps(reply_markup)
        return self._post("editMessageText", payload)

    def send_photo(
        self,
        photo_path: Path,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> dict[str, Any] | None:
        files = {"photo": (photo_path.name, photo_path.read_bytes())}
        data: dict[str, Any] = {"chat_id": self.chat_id}
        if caption is not None:
            data["caption"] = caption
        if reply_to_message_id is not None:
            data["reply_to_message_id"] = str(reply_to_message_id)
        return self._post_multipart("sendPhoto", files, data)

    def send_video(
        self,
        video_path: Path,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> dict[str, Any] | None:
        files = {"video": (video_path.name, video_path.read_bytes())}
        data: dict[str, Any] = {"chat_id": self.chat_id}
        if caption is not None:
            data["caption"] = caption
        if reply_to_message_id is not None:
            data["reply_to_message_id"] = str(reply_to_message_id)
        return self._post_multipart("sendVideo", files, data)

    def send(self, text: str) -> None:
        """Backwards-compatible: existing callers (e.g. notify_failure) keep working."""
        self.send_message(text)


def notify_failure(
    *,
    project_id: int,
    profile: str,
    phase: str,
    error: str,
    fix_command: str | None,
) -> None:
    """Send a Telegram failure notification. No-op if env vars not set."""
    notifier = TelegramNotifier.from_env()
    if notifier is None:
        return
    lines = [
        "🚨 *Publish failed*",
        "",
        f"Project: `{_escape_mdv2(str(project_id))}`",
        f"Profile: `{_escape_mdv2(profile)}`",
        f"Phase: `{_escape_mdv2(phase)}`",
        f"Error: {_escape_mdv2(error)}",
    ]
    if fix_command:
        lines.append("")
        lines.append(f"Fix: `{_escape_mdv2(fix_command)}`")
    notifier.send("\n".join(lines))
```

- [ ] **Step 8.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_telegram_extended_send.py -v`
Expected: 8 passed.

- [ ] **Step 8.5: Verify the existing publish-failure tests still pass**

Run: `uv run pytest tests/unit/notify/ tests/unit/publish/ -v`
Expected: all pass — the legacy `send` method still routes to `sendMessage` so `notify_failure` is unchanged.

- [ ] **Step 8.6: Commit**

```bash
git add src/pipeline/notify/telegram.py tests/unit/test_telegram_extended_send.py
git commit -m "feat(telegram): reply_to/inline_keyboard params + send_photo/send_video/edit_message_text"
```

---

## Task 9: Telegram — long-poll listener for callback_query

**Files:**
- Modify: `src/pipeline/notify/telegram.py` (add `get_updates` + `LongPollListener`)
- Test: `tests/unit/test_telegram_long_poll.py` (new)

The listener is a long-running asyncio task. It calls `getUpdates` with the next offset, dispatches each `callback_query` to a registered handler (the JobQueue's button-callback router we'll wire up in Task 12), and repeats. Transient HTTP failures are retried with backoff; cancellation exits the loop.

- [ ] **Step 9.1: Write the long-poll tests**

Create `tests/unit/test_telegram_long_poll.py`:

```python
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from pipeline.notify.telegram import LongPollListener, TelegramNotifier


class _ScriptedTransport(httpx.MockTransport):
    """Returns a scripted sequence of responses to /getUpdates calls."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if not self._responses:
                # Keep returning empty so the loop just polls.
                return httpx.Response(200, json={"ok": True, "result": []})
            return httpx.Response(200, json=self._responses.pop(0))
        super().__init__(handler)


def _patch_async_client(monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport) -> None:
    monkeypatch.setattr(
        "pipeline.notify.telegram._http_async_client",
        lambda: httpx.AsyncClient(transport=transport, timeout=10.0),
    )


@pytest.mark.asyncio
async def test_long_poll_dispatches_callback_query(monkeypatch: pytest.MonkeyPatch):
    transport = _ScriptedTransport([
        {
            "ok": True,
            "result": [
                {
                    "update_id": 100,
                    "callback_query": {
                        "id": "cb-1",
                        "data": "cancel:42:job-1",
                        "from": {"id": 7, "username": "tim"},
                        "message": {"message_id": 999, "chat": {"id": 1}},
                    },
                }
            ],
        }
    ])
    _patch_async_client(monkeypatch, transport)
    notifier = TelegramNotifier(token="t", chat_id="c")
    received: list[dict] = []

    async def handler(callback: dict) -> None:
        received.append(callback)

    listener = LongPollListener(notifier, on_callback_query=handler, poll_timeout=0)
    task = asyncio.create_task(listener.run())
    # Wait briefly for the dispatch.
    for _ in range(50):
        if received:
            break
        await asyncio.sleep(0.01)
    listener.stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert len(received) == 1
    assert received[0]["data"] == "cancel:42:job-1"


@pytest.mark.asyncio
async def test_long_poll_advances_offset(monkeypatch: pytest.MonkeyPatch):
    """After processing update_id=100, next getUpdates request includes offset=101."""
    transport = _ScriptedTransport([
        {"ok": True, "result": [
            {"update_id": 100, "callback_query": {"id": "a", "data": "x"}}
        ]},
        {"ok": True, "result": []},
        {"ok": True, "result": []},
    ])
    _patch_async_client(monkeypatch, transport)
    notifier = TelegramNotifier(token="t", chat_id="c")

    async def handler(callback: dict) -> None: pass

    listener = LongPollListener(notifier, on_callback_query=handler, poll_timeout=0)
    task = asyncio.create_task(listener.run())
    for _ in range(50):
        if len(transport.requests) >= 2:
            break
        await asyncio.sleep(0.01)
    listener.stop()
    await asyncio.wait_for(task, timeout=1.0)

    # Second request must carry offset=101 in its body.
    second_body = transport.requests[1].read().decode()
    assert "offset" in second_body
    assert "101" in second_body


@pytest.mark.asyncio
async def test_long_poll_retries_on_transient_failure(monkeypatch: pytest.MonkeyPatch):
    """A 502 response must not kill the loop — listener retries."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(502, json={"ok": False})
        return httpx.Response(200, json={"ok": True, "result": []})

    monkeypatch.setattr(
        "pipeline.notify.telegram._http_async_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=10.0),
    )
    notifier = TelegramNotifier(token="t", chat_id="c")

    async def cb(_: dict) -> None: pass

    listener = LongPollListener(
        notifier, on_callback_query=cb, poll_timeout=0, retry_delay_sec=0.01
    )
    task = asyncio.create_task(listener.run())
    for _ in range(100):
        if call_count["n"] >= 2:
            break
        await asyncio.sleep(0.01)
    listener.stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert call_count["n"] >= 2  # the 502 was retried


@pytest.mark.asyncio
async def test_long_poll_stops_cleanly(monkeypatch: pytest.MonkeyPatch):
    transport = _ScriptedTransport([])
    _patch_async_client(monkeypatch, transport)
    notifier = TelegramNotifier(token="t", chat_id="c")

    async def cb(_: dict) -> None: pass

    listener = LongPollListener(notifier, on_callback_query=cb, poll_timeout=0)
    task = asyncio.create_task(listener.run())
    await asyncio.sleep(0.05)
    listener.stop()
    await asyncio.wait_for(task, timeout=1.0)
    assert task.done()
```

- [ ] **Step 9.2: Run the tests — expect ImportError**

Run: `uv run pytest tests/unit/test_telegram_long_poll.py -v`
Expected: ImportError on `LongPollListener` and `_http_async_client`.

- [ ] **Step 9.3: Add `_http_async_client` + `LongPollListener` to `telegram.py`**

Append to `src/pipeline/notify/telegram.py`:

```python
import asyncio
from collections.abc import Awaitable, Callable


def _http_async_client() -> httpx.AsyncClient:
    """Async factory that tests monkeypatch to inject a MockTransport."""
    return httpx.AsyncClient(timeout=30.0)


class LongPollListener:
    """Background asyncio task that polls Telegram getUpdates and dispatches
    callback_query updates to a registered handler.

    Started by the FastAPI lifespan; stopped on shutdown.
    """

    def __init__(
        self,
        notifier: TelegramNotifier,
        *,
        on_callback_query: Callable[[dict[str, Any]], Awaitable[None]],
        poll_timeout: int = 25,
        retry_delay_sec: float = 1.0,
    ) -> None:
        self._notifier = notifier
        self._on_callback = on_callback_query
        self._poll_timeout = poll_timeout
        self._retry_delay_sec = retry_delay_sec
        self._offset: int | None = None
        self._stopped = asyncio.Event()

    def stop(self) -> None:
        self._stopped.set()

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                updates = await self._fetch_updates()
            except Exception as exc:
                logger.warning("telegram.long_poll.exception", error=str(exc))
                await self._sleep_or_stop(self._retry_delay_sec)
                continue
            if updates is None:
                await self._sleep_or_stop(self._retry_delay_sec)
                continue
            for update in updates:
                self._offset = update["update_id"] + 1
                cb = update.get("callback_query")
                if cb is not None:
                    try:
                        await self._on_callback(cb)
                    except Exception as exc:
                        logger.warning(
                            "telegram.long_poll.handler_exception",
                            error=str(exc),
                        )

    async def _fetch_updates(self) -> list[dict[str, Any]] | None:
        payload: dict[str, Any] = {
            "timeout": self._poll_timeout,
            "allowed_updates": ["callback_query"],
        }
        if self._offset is not None:
            payload["offset"] = self._offset
        async with _http_async_client() as client:
            response = await client.post(
                self._notifier._api_url("getUpdates"), json=payload
            )
        if response.status_code >= 400:
            logger.warning(
                "telegram.long_poll.http_error",
                status=response.status_code,
                body=response.text[:200],
            )
            return None
        data = response.json()
        if not data.get("ok"):
            return None
        return list(data.get("result", []))

    async def _sleep_or_stop(self, sec: float) -> None:
        try:
            await asyncio.wait_for(self._stopped.wait(), timeout=sec)
        except asyncio.TimeoutError:
            pass
```

- [ ] **Step 9.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_telegram_long_poll.py -v`
Expected: 4 passed.

- [ ] **Step 9.5: Commit**

```bash
git add src/pipeline/notify/telegram.py tests/unit/test_telegram_long_poll.py
git commit -m "feat(telegram): LongPollListener for callback_query dispatch"
```

---

## Task 10: Agent system-prompt template at `agent_prompt.md`

**Files:**
- Create: `src/pipeline/dashboard/agent_prompt.md`

This is the static template loaded once at JobQueue startup. The runner fills in the placeholder header (`{project_id}`, `{storyboard_summary}`, `{tokens}`, `{instruction}`) at job-spawn time and pipes the assembled string to `claude -p`.

- [ ] **Step 10.1: Create `agent_prompt.md`**

Create `src/pipeline/dashboard/agent_prompt.md`:

```markdown
You are an editing agent for a YouTube content-porting pipeline. The user
clicked elements in their dashboard, picked some addressable tokens, and gave
you an instruction. Your job is to translate that instruction into a small
sequence of CLI verb calls that mutate the project's storyboard, then chain
the appropriate `compose` recompose commands so the new state actually
renders.

## Job context (filled in per invocation)

Project ID: {project_id}

Resolved tokens:
{tokens}

Instruction:
{instruction}

Current storyboard summary:
{storyboard_summary}

## CLI verbs you MAY call

Each verb is project-scoped via `--project-id`. Always pass `--project-id {project_id}`.

Mutating verbs (data only — they update storyboard state and stop):

- `pipeline narration regen --project-id {project_id} --scene <id> --text "..."`
  → overwrites the scene's narration text
- `pipeline subtitle set --project-id {project_id} --scene <id> --text "..."`
  → adds a per-scene subtitle override
- `pipeline overlay set --project-id {project_id} --scene <id> --text "..."`
  → updates the overlay text on the scene
- `pipeline image regen --project-id {project_id} --scene <id> --prompt "..." --tier draft|production`
  → updates the image generation prompt + tier and clears the cached image

Recompose verbs (after mutations, run the right rebuild):

- `pipeline compose rescene --project-id {project_id} --scene <id>` (repeatable)
  → re-renders one or more scenes from cache (image, TTS, scene clip)
  → use after `narration regen`, `overlay set`, `image regen`
- `pipeline compose reburn --project-id {project_id}`
  → re-burns subtitles into the existing raw video
  → use after `subtitle set`

You MAY also read storyboard state to check what you're working with:

- `pipeline storyboard show --project-id {project_id}` — full storyboard JSON

## Rules

1. Use the verbs exactly as specified — do not invent new flags.
2. Make the smallest set of changes that satisfies the instruction.
3. After data-mutation verbs, ALWAYS chain the appropriate `compose rescene`
   or `compose reburn` so the user sees the change in the rendered video.
4. If a token is `@sN` without a sub-element, infer which element the
   instruction is about (text → narration/subtitle, "look"/"image"/"darker" →
   visual, "caption"/"overlay" → overlay).
5. If the instruction is ambiguous (e.g. "make this better"), pick the most
   plausible interpretation and proceed — do not stall.
6. If a verb fails, do NOT retry blindly. Report the failure and stop. The
   user can retry from Telegram.
7. Default `image regen` to `--tier draft` unless the instruction explicitly
   says "high quality" / "production".
8. Print one short status line per CLI invocation to stdout — these are
   streamed back to the user.
```

- [ ] **Step 10.2: Verify the file is checked in**

Run: `ls -la src/pipeline/dashboard/agent_prompt.md`
Expected: file exists, ~2 KB.

- [ ] **Step 10.3: Commit**

```bash
git add src/pipeline/dashboard/agent_prompt.md
git commit -m "feat(dashboard): edit-agent system prompt template"
```

---

## Task 11: Agent subprocess runner — `ClaudeAgentRunner`

**Files:**
- Create: `src/pipeline/dashboard/agent_runner.py`
- Test: `tests/unit/test_agent_runner.py` (new)

`ClaudeAgentRunner` implements the `AgentRunner` Protocol from Task 2. It assembles the per-job prompt (template + placeholders), spawns `claude -p <full-prompt>` as a subprocess, and accumulates stdout. Every `~2 seconds` (or on prompt completion), it edits the Telegram opener message with the latest stdout chunk so the user sees streaming progress. On exit it returns a `[SubActionResult]` list (a single result for now — a v2 enhancement could parse stdout for multiple verb invocations and split them).

For tests we don't actually invoke `claude` — we inject a `subprocess_factory` that swaps the binary for a controllable shim (`["python", "-c", "..."]`).

- [ ] **Step 11.1: Write the runner tests**

Create `tests/unit/test_agent_runner.py`:

```python
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pipeline.dashboard.agent_runner import (
    ClaudeAgentRunner,
    build_agent_prompt,
    summarize_storyboard,
)
from pipeline.dashboard.job_queue import EditJob
from pipeline.storyboard import Scene, Storyboard


def test_summarize_storyboard_lists_scene_ids_and_narration_prefix(tmp_path: Path):
    sb = Storyboard(scenes=[
        Scene(id="s1", section="hook", narration="Once upon a time there was a kingdom",
              narration_est_sec=3.0),
        Scene(id="s2", section="content", narration="Short.", narration_est_sec=1.0),
    ])
    sb_path = tmp_path / "storyboard.json"
    sb.save(sb_path)
    summary = summarize_storyboard(sb_path)
    assert "s1" in summary
    assert "s2" in summary
    assert "Once upon a time" in summary
    assert "Short." in summary


def test_summarize_storyboard_returns_placeholder_when_missing(tmp_path: Path):
    summary = summarize_storyboard(tmp_path / "nope.json")
    assert "no storyboard" in summary.lower() or summary == ""


def test_build_agent_prompt_substitutes_placeholders(tmp_path: Path):
    template = (
        "Project: {project_id}\n"
        "Tokens: {tokens}\n"
        "Instruction: {instruction}\n"
        "Storyboard:\n{storyboard_summary}\n"
    )
    job = EditJob(
        job_id="j1", project_id="42",
        tokens=["@s9/visual", "@s11/subtitle"],
        instruction="darken these",
    )
    out = build_agent_prompt(template=template, job=job, storyboard_summary="(scenes...)")
    assert "Project: 42" in out
    assert "@s9/visual" in out
    assert "@s11/subtitle" in out
    assert "darken these" in out
    assert "(scenes...)" in out


@pytest.mark.asyncio
async def test_runner_invokes_subprocess_and_returns_result(tmp_path: Path):
    """Inject a fake subprocess factory that pretends to be `claude -p`."""
    project = tmp_path / "42"
    project.mkdir()
    (project / "storyboard.json").write_text("{}", encoding="utf-8")

    captured_argv: list[list[str]] = []

    async def fake_factory(argv: list[str]) -> "asyncio.subprocess.Process":
        captured_argv.append(argv)
        # Use a real subprocess that just echoes a known string then exits 0.
        return await asyncio.create_subprocess_exec(
            "python", "-c", "import sys; sys.stdout.write('subtitle set s9 ok\\n')",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )

    runner = ClaudeAgentRunner(
        prompt_template="P: {project_id}\nI: {instruction}\nT: {tokens}\nS: {storyboard_summary}",
        notifier=None,
        subprocess_factory=fake_factory,
    )
    job = EditJob(job_id="j1", project_id="42", tokens=["@s9"], instruction="x")
    job.telegram_opener_id = 999

    results = await runner.run(job, project_root=project)

    assert len(captured_argv) == 1
    assert captured_argv[0][0] == "claude"
    assert "-p" in captured_argv[0]
    assert len(results) == 1
    assert results[0].ok is True
    assert "subtitle set s9 ok" in results[0].message


@pytest.mark.asyncio
async def test_runner_marks_failure_on_nonzero_exit(tmp_path: Path):
    project = tmp_path / "42"
    project.mkdir()
    (project / "storyboard.json").write_text("{}", encoding="utf-8")

    async def fake_factory(argv: list[str]) -> "asyncio.subprocess.Process":
        return await asyncio.create_subprocess_exec(
            "python", "-c", "import sys; sys.stderr.write('boom\\n'); sys.exit(2)",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )

    runner = ClaudeAgentRunner(
        prompt_template="x",
        notifier=None,
        subprocess_factory=fake_factory,
    )
    job = EditJob(job_id="j1", project_id="42", tokens=[], instruction="x")
    results = await runner.run(job, project_root=project)
    assert len(results) == 1
    assert results[0].ok is False
    assert "exit" in results[0].message.lower()


@pytest.mark.asyncio
async def test_runner_terminates_subprocess_on_cancel(tmp_path: Path):
    project = tmp_path / "42"
    project.mkdir()
    (project / "storyboard.json").write_text("{}", encoding="utf-8")

    async def fake_factory(argv: list[str]) -> "asyncio.subprocess.Process":
        # A long-running subprocess to test cancellation.
        return await asyncio.create_subprocess_exec(
            "python", "-c", "import time; time.sleep(10)",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )

    runner = ClaudeAgentRunner(
        prompt_template="x",
        notifier=None,
        subprocess_factory=fake_factory,
    )
    job = EditJob(job_id="j1", project_id="42", tokens=[], instruction="x")

    async def run_and_cancel() -> None:
        task = asyncio.create_task(runner.run(job, project_root=project))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    await asyncio.wait_for(run_and_cancel(), timeout=3.0)
```

- [ ] **Step 11.2: Run the tests — expect ImportError**

Run: `uv run pytest tests/unit/test_agent_runner.py -v`
Expected: ImportError on `pipeline.dashboard.agent_runner`.

- [ ] **Step 11.3: Create `agent_runner.py`**

Create `src/pipeline/dashboard/agent_runner.py`:

```python
"""Agent subprocess runner.

Spawns `claude -p <full-prompt>` per job, accumulates stdout, optionally
edits a Telegram message with streaming progress, and returns the parsed
result(s) for the JobQueue to persist to the job sidecar.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import structlog

from pipeline.dashboard.job_queue import EditJob, SubActionResult
from pipeline.notify.telegram import TelegramNotifier

logger = structlog.get_logger()

# Subprocess factory signature — tests inject a fake that swaps the binary.
SubprocessFactory = Callable[[list[str]], Awaitable["asyncio.subprocess.Process"]]


def summarize_storyboard(storyboard_path: Path, *, max_per_line: int = 60) -> str:
    """Build a compact human-readable summary of the storyboard for the prompt."""
    if not storyboard_path.exists():
        return "(no storyboard found)"
    try:
        data = json.loads(storyboard_path.read_text(encoding="utf-8"))
    except Exception:
        return "(storyboard unreadable)"
    lines: list[str] = []
    for scene in data.get("scenes", []):
        narration = (scene.get("narration") or "")[:max_per_line]
        lines.append(f"  {scene.get('id')} [{scene.get('section')}]: {narration}")
    return "\n".join(lines) if lines else "(no scenes)"


def build_agent_prompt(*, template: str, job: EditJob, storyboard_summary: str) -> str:
    tokens_lines = "\n".join(f"  - {tok}" for tok in job.tokens) or "  (none)"
    return template.format(
        project_id=job.project_id,
        tokens=tokens_lines,
        instruction=job.instruction,
        storyboard_summary=storyboard_summary,
    )


async def _default_subprocess_factory(argv: list[str]) -> "asyncio.subprocess.Process":
    return await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


class ClaudeAgentRunner:
    """`AgentRunner` that spawns `claude -p` and streams stdout to Telegram."""

    def __init__(
        self,
        *,
        prompt_template: str,
        notifier: TelegramNotifier | None,
        subprocess_factory: SubprocessFactory | None = None,
        edit_interval_sec: float = 2.0,
    ) -> None:
        self._template = prompt_template
        self._notifier = notifier
        self._factory = subprocess_factory or _default_subprocess_factory
        self._edit_interval_sec = edit_interval_sec

    async def run(self, job: EditJob, project_root: Path) -> list[SubActionResult]:
        sb_summary = summarize_storyboard(project_root / "storyboard.json")
        prompt = build_agent_prompt(
            template=self._template, job=job, storyboard_summary=sb_summary
        )
        argv = ["claude", "-p", prompt]
        proc = await self._factory(argv)

        accumulated: list[bytes] = []
        last_edit_time = 0.0

        async def _pump_stdout() -> None:
            nonlocal last_edit_time
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    return
                accumulated.append(line)
                now = asyncio.get_event_loop().time()
                if (
                    self._notifier is not None
                    and job.telegram_opener_id is not None
                    and now - last_edit_time >= self._edit_interval_sec
                ):
                    last_edit_time = now
                    text = b"".join(accumulated).decode(errors="replace")[-3500:]
                    await asyncio.to_thread(
                        self._notifier.edit_message_text,
                        message_id=job.telegram_opener_id,
                        text=text,
                        parse_mode="",
                    )

        try:
            pump_task = asyncio.create_task(_pump_stdout())
            try:
                returncode = await proc.wait()
            finally:
                # Ensure the pump task drains any remaining output.
                try:
                    await asyncio.wait_for(pump_task, timeout=1.0)
                except asyncio.TimeoutError:
                    pump_task.cancel()
        except asyncio.CancelledError:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
            raise

        stdout_text = b"".join(accumulated).decode(errors="replace")
        ok = returncode == 0
        message = stdout_text.strip() or (
            f"agent exited with code {returncode}" if not ok else "no output"
        )
        return [SubActionResult(verb="agent", scene=None, ok=ok, message=message)]
```

- [ ] **Step 11.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_agent_runner.py -v`
Expected: 6 passed.

- [ ] **Step 11.5: Commit**

```bash
git add src/pipeline/dashboard/agent_runner.py tests/unit/test_agent_runner.py
git commit -m "feat(dashboard): ClaudeAgentRunner subprocess + streaming Telegram edit"
```

---

## Task 12: JobQueue ⇄ Telegram integration — opener message + callback router

**Files:**
- Modify: `src/pipeline/dashboard/job_queue.py` (post opener message before run; expose `handle_callback_query`)
- Test: `tests/unit/test_job_queue.py` (extend)

When a job starts running, the queue posts an opener message to Telegram (`[42] editing @s9/visual: "make these darker"`) with a `Cancel` inline button (`callback_data: "cancel:42:job-1"`), saves the returned `message_id` on the job sidecar, then hands the job to the runner. The Telegram long-poll listener feeds incoming `callback_query` updates back via a single dispatcher method `handle_callback_query` which currently understands one verb: `cancel:<project_id>:<job_id>`.

- [ ] **Step 12.1: Add the integration tests**

Append to `tests/unit/test_job_queue.py`:

```python
class _RecordingNotifier:
    """Stand-in for TelegramNotifier that records calls and returns canned ids."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.next_id = 1000

    def send_message(self, text, **kwargs):
        self.sent.append({"method": "send_message", "text": text, **kwargs})
        msg_id = self.next_id
        self.next_id += 1
        return {"message_id": msg_id}

    def edit_message_text(self, **kwargs):
        self.sent.append({"method": "edit_message_text", **kwargs})
        return {}


@pytest.mark.asyncio
async def test_submit_posts_opener_message_with_cancel_button(project_tree: Path):
    notifier = _RecordingNotifier()
    runner = FakeRunner()
    queue = JobQueue(projects_root=project_tree, runner=runner, notifier=notifier)
    await queue.start()

    job = EditJob(
        job_id="j1", project_id="42",
        tokens=["@s9/visual"], instruction="darken this",
    )
    await queue.submit(job)
    await queue.wait_idle("42", timeout=2.0)

    # Opener was posted with cancel keyboard before run.
    opener = notifier.sent[0]
    assert opener["method"] == "send_message"
    assert "j1" in opener["text"] or "@s9/visual" in opener["text"]
    keyboard = opener.get("reply_markup", {}).get("inline_keyboard", [])
    assert any(
        btn.get("callback_data") == "cancel:42:j1"
        for row in keyboard
        for btn in row
    )
    # message_id was persisted to the job sidecar.
    loaded = load_job(project_tree / "42", "j1")
    assert loaded.telegram_opener_id == 1000

    await queue.shutdown()


@pytest.mark.asyncio
async def test_handle_callback_query_routes_cancel(project_tree: Path):
    notifier = _RecordingNotifier()
    runner = CancellableRunner()
    queue = JobQueue(projects_root=project_tree, runner=runner, notifier=notifier)
    await queue.start()

    job = EditJob(job_id="long", project_id="42", tokens=[], instruction="x")
    await queue.submit(job)
    await asyncio.wait_for(runner.entered.wait(), timeout=1.0)

    callback = {
        "id": "cb1",
        "data": "cancel:42:long",
        "from": {"id": 7, "username": "tim"},
    }
    routed = await queue.handle_callback_query(callback)
    assert routed is True
    await queue.wait_idle("42", timeout=2.0)
    assert load_job(project_tree / "42", "long").status == "cancelled"
    await queue.shutdown()


@pytest.mark.asyncio
async def test_handle_callback_query_ignores_unknown_verb(project_tree: Path):
    queue = JobQueue(projects_root=project_tree, runner=FakeRunner(), notifier=None)
    await queue.start()
    callback = {"id": "cb1", "data": "doitnow:42:j1", "from": {"id": 1}}
    routed = await queue.handle_callback_query(callback)
    assert routed is False
    await queue.shutdown()
```

- [ ] **Step 12.2: Run the new tests — expect failure**

Run: `uv run pytest tests/unit/test_job_queue.py -v -k "opener or callback"`
Expected: failures because `JobQueue` doesn't accept a `notifier` kwarg or expose `handle_callback_query`.

- [ ] **Step 12.3: Add `notifier` param + opener flow + `handle_callback_query`**

Open `src/pipeline/dashboard/job_queue.py`. Replace the `__init__` signature with:

```python
    def __init__(
        self,
        *,
        projects_root: Path,
        runner: AgentRunner,
        notifier: Any | None = None,
    ) -> None:
        self._projects_root = projects_root
        self._runner = runner
        self._notifier = notifier
        self._queues: dict[str, asyncio.Queue[EditJob]] = {}
        self._consumers: dict[str, asyncio.Task[None]] = {}
        self._idle_events: dict[str, asyncio.Event] = {}
        self._running_jobs: dict[str, EditJob] = {}
        self._cancel_targets: dict[str, tuple[str, asyncio.Task[None]]] = {}
        self._lock = asyncio.Lock()
        self._started = False
```

Add this helper method on `JobQueue` (near `_run_job`):

```python
    def _opener_text(self, job: EditJob) -> str:
        token_line = " + ".join(job.tokens) if job.tokens else "(no tokens)"
        return f"[{job.project_id}] editing {token_line}: {job.instruction!r}"

    def _opener_keyboard(self, job: EditJob) -> dict[str, Any]:
        return {
            "inline_keyboard": [[
                {"text": "✕ Cancel", "callback_data": f"cancel:{job.project_id}:{job.job_id}"}
            ]]
        }

    async def _post_opener(self, job: EditJob) -> None:
        if self._notifier is None:
            return
        result = await asyncio.to_thread(
            self._notifier.send_message,
            self._opener_text(job),
            reply_markup=self._opener_keyboard(job),
            parse_mode="",
        )
        if result and "message_id" in result:
            job.telegram_opener_id = int(result["message_id"])
```

Modify `_run_job` to post the opener BEFORE running the agent. Replace the head of `_run_job` (the part before `try:`) with:

```python
    async def _run_job(self, job: EditJob) -> None:
        project_root = self._projects_root / job.project_id
        job.status = "running"
        job.started_at = datetime.now().isoformat(timespec="seconds")
        await self._post_opener(job)
        save_job(project_root, job)
        self._running_jobs[job.project_id] = job

        run_task = asyncio.current_task()
        self._cancel_targets[job.project_id] = (job.job_id, run_task)
```

(The remaining body of `_run_job` — the `try/except/finally` block — stays as it was after Task 3.)

Add the callback router (place after `cancel`):

```python
    async def handle_callback_query(self, callback: dict[str, Any]) -> bool:
        """Route a Telegram callback_query update.

        Returns True if the verb was recognized and dispatched; False otherwise.
        """
        data = callback.get("data", "")
        verb, _, rest = data.partition(":")
        if verb == "cancel":
            project_id, _, job_id = rest.partition(":")
            return await self.cancel(project_id, job_id)
        return False
```

Also add `from typing import Any` to the imports at the top of the file if not already present.

- [ ] **Step 12.4: Run the tests — expect pass**

Run: `uv run pytest tests/unit/test_job_queue.py -v`
Expected: 18 passed.

- [ ] **Step 12.5: Commit**

```bash
git add src/pipeline/dashboard/job_queue.py tests/unit/test_job_queue.py
git commit -m "feat(dashboard): JobQueue Telegram opener + callback_query router"
```

---

## Task 13: HTTP endpoints — `POST /api/jobs/{project_id}/submit` + `/cancel`

**Files:**
- Modify: `src/pipeline/dashboard/server.py` (add the two endpoints)
- Test: `tests/integration/test_jobs_endpoints.py` (new)

Endpoints expect a `JobQueue` instance attached to `app.state.job_queue`. We expose a `register_job_endpoints(app, output_dir)` helper so tests can build a minimal app without bringing up the full lifespan; the production wiring is in Task 14.

- [ ] **Step 13.1: Write the endpoint tests**

Create `tests/integration/test_jobs_endpoints.py`:

```python
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pipeline.dashboard.job_queue import (
    EditJob,
    JobQueue,
    SubActionResult,
    load_job,
)
from pipeline.dashboard.server import register_job_endpoints


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[EditJob] = []
        self._block = asyncio.Event()
        self.entered = asyncio.Event()

    async def run(self, job: EditJob, project_root: Path) -> list[SubActionResult]:
        self.calls.append(job)
        self.entered.set()
        await self._block.wait()
        return [SubActionResult(verb="subtitle set", scene="s9", ok=True, message="ok")]

    def release(self) -> None:
        self._block.set()


@pytest.fixture
def app_with_queue(tmp_path: Path):
    output = tmp_path / "output"
    (output / "projects" / "42").mkdir(parents=True)
    runner = _FakeRunner()

    # The TestClient runs the request in the same loop as the JobQueue.
    queue = JobQueue(projects_root=output / "projects", runner=runner, notifier=None)

    app = FastAPI()
    register_job_endpoints(app, output_dir=output)
    app.state.job_queue = queue

    @app.on_event("startup")
    async def _start():
        await queue.start()

    @app.on_event("shutdown")
    async def _stop():
        runner.release()
        await queue.shutdown()

    yield app, queue, runner


def test_submit_endpoint_returns_job_id_and_persists_sidecar(app_with_queue, tmp_path: Path):
    app, queue, runner = app_with_queue
    with TestClient(app) as client:
        response = client.post(
            "/api/jobs/42/submit",
            json={"tokens": ["@s9/visual"], "instruction": "darken"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "job_id" in body
        sidecar = tmp_path / "output" / "projects" / "42" / "edit_jobs" / f"{body['job_id']}.json"
        assert sidecar.exists()
        runner.release()


def test_submit_rejects_unknown_project(app_with_queue):
    app, queue, runner = app_with_queue
    with TestClient(app) as client:
        response = client.post(
            "/api/jobs/9999/submit",
            json={"tokens": [], "instruction": "x"},
        )
        assert response.status_code == 404


def test_submit_rejects_empty_instruction(app_with_queue):
    app, queue, runner = app_with_queue
    with TestClient(app) as client:
        response = client.post(
            "/api/jobs/42/submit",
            json={"tokens": ["@s9"], "instruction": ""},
        )
        assert response.status_code == 400


def test_cancel_endpoint_terminates_in_flight_job(app_with_queue, tmp_path: Path):
    app, queue, runner = app_with_queue
    with TestClient(app) as client:
        submit = client.post(
            "/api/jobs/42/submit",
            json={"tokens": [], "instruction": "x"},
        )
        job_id = submit.json()["job_id"]
        # Wait for the runner to actually pick up the job.
        for _ in range(50):
            if runner.entered.is_set():
                break
            import time; time.sleep(0.02)

        cancel = client.post(f"/api/jobs/42/{job_id}/cancel")
        assert cancel.status_code == 200
        assert cancel.json()["cancelled"] is True

    # After the test client closed (shutdown ran), sidecar should reflect cancellation.
    sidecar = tmp_path / "output" / "projects" / "42" / "edit_jobs" / f"{job_id}.json"
    job = json.loads(sidecar.read_text())
    assert job["status"] in ("cancelled", "interrupted")


def test_cancel_returns_false_for_unknown_job(app_with_queue):
    app, queue, runner = app_with_queue
    with TestClient(app) as client:
        runner.release()
        response = client.post("/api/jobs/42/nonexistent/cancel")
        assert response.status_code == 200
        assert response.json()["cancelled"] is False
```

- [ ] **Step 13.2: Run the tests — expect ImportError**

Run: `uv run pytest tests/integration/test_jobs_endpoints.py -v`
Expected: ImportError on `pipeline.dashboard.server.register_job_endpoints`.

- [ ] **Step 13.3: Add the endpoint registration helper to `server.py`**

Open `src/pipeline/dashboard/server.py`. Add this import block near the top, alongside the existing imports:

```python
import uuid

from pipeline.dashboard.job_queue import EditJob, JobQueue
```

Below the existing `_TranscribeBody` pydantic model class (around line 47-49), add:

```python
class _JobSubmitBody(BaseModel):
    tokens: list[str] = []
    instruction: str
```

After the `create_app` function definition (around line 297), add:

```python
def register_job_endpoints(app: FastAPI, *, output_dir: Path) -> None:
    """Register POST /api/jobs/{project_id}/submit and /cancel endpoints.

    Expects `app.state.job_queue: JobQueue` to be set before requests arrive
    (typically in the FastAPI lifespan startup handler).
    """

    def _project_root(project_id: str) -> Path:
        proj = output_dir / "projects" / project_id
        if not proj.exists():
            raise HTTPException(status_code=404, detail=f"project {project_id} not found")
        return proj

    @app.post("/api/jobs/{project_id}/submit")
    async def post_submit(project_id: str, body: _JobSubmitBody) -> JSONResponse:
        _project_root(project_id)  # 404 guard
        if not body.instruction.strip():
            raise HTTPException(status_code=400, detail="instruction must not be empty")
        queue: JobQueue = app.state.job_queue
        job = EditJob(
            job_id=uuid.uuid4().hex[:12],
            project_id=project_id,
            tokens=list(body.tokens),
            instruction=body.instruction,
        )
        await queue.submit(job)
        return JSONResponse({"ok": True, "job_id": job.job_id, "status": job.status})

    @app.post("/api/jobs/{project_id}/{job_id}/cancel")
    async def post_cancel(project_id: str, job_id: str) -> JSONResponse:
        queue: JobQueue = app.state.job_queue
        cancelled = await queue.cancel(project_id, job_id)
        return JSONResponse({"ok": True, "cancelled": cancelled})
```

Note: keep `register_job_endpoints` separate from `create_app` so the production app can call both, and tests can call `register_job_endpoints` against a minimal `FastAPI()`.

- [ ] **Step 13.4: Run the tests — expect pass**

Run: `uv run pytest tests/integration/test_jobs_endpoints.py -v`
Expected: 5 passed.

- [ ] **Step 13.5: Commit**

```bash
git add src/pipeline/dashboard/server.py tests/integration/test_jobs_endpoints.py
git commit -m "feat(dashboard): POST /api/jobs/<project>/submit and /cancel endpoints"
```

---

## Task 14: FastAPI lifespan wiring + final verification

**Files:**
- Modify: `src/pipeline/dashboard/server.py` (add `lifespan` that builds JobQueue + Telegram listener; call `register_job_endpoints`)

The production `create_app` now:
1. Loads `agent_prompt.md` from disk.
2. Constructs `ClaudeAgentRunner(prompt_template=..., notifier=...)`.
3. Constructs `JobQueue(projects_root=..., runner=..., notifier=...)`, calls `reload_on_startup()`, and stores it on `app.state.job_queue`.
4. Starts a `LongPollListener(notifier, on_callback_query=queue.handle_callback_query)` task on startup; cancels it on shutdown.
5. Calls `register_job_endpoints(app, output_dir=output_dir)`.

When `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` are unset, the listener is skipped — but the queue and HTTP endpoints still work.

- [ ] **Step 14.1: Add a smoke test that exercises `create_app` startup**

Create `tests/integration/test_dashboard_jobs_lifespan.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.dashboard.server import create_app


@pytest.fixture(autouse=True)
def _no_telegram_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)


def test_dashboard_starts_and_jobs_endpoints_are_registered(tmp_path: Path):
    output = tmp_path / "output"
    (output / "projects" / "42").mkdir(parents=True)
    app = create_app(output)
    with TestClient(app) as client:
        # Hitting the submit endpoint requires JobQueue on app.state — confirms
        # lifespan ran. We expect a 400 (empty instruction), not a 500/AttributeError.
        response = client.post(
            "/api/jobs/42/submit", json={"tokens": [], "instruction": ""}
        )
        assert response.status_code == 400


def test_reload_on_startup_marks_orphan_running_as_interrupted(tmp_path: Path):
    """A sidecar left in 'running' from a 'prior' process gets reset at startup."""
    import json as _json
    output = tmp_path / "output"
    proj = output / "projects" / "42"
    edit_dir = proj / "edit_jobs"
    edit_dir.mkdir(parents=True)
    sidecar = edit_dir / "orphan.json"
    sidecar.write_text(_json.dumps({
        "job_id": "orphan", "project_id": "42",
        "tokens": [], "instruction": "x", "status": "running",
        "telegram_opener_id": None, "sub_action_results": [],
        "created_at": "2026-05-04T00:00:00", "started_at": "2026-05-04T00:00:01",
        "finished_at": None,
    }), encoding="utf-8")

    app = create_app(output)
    with TestClient(app):
        pass  # lifespan startup ran reload_on_startup()

    after = _json.loads(sidecar.read_text(encoding="utf-8"))
    assert after["status"] == "interrupted"
```

- [ ] **Step 14.2: Run the test — expect failure**

Run: `uv run pytest tests/integration/test_dashboard_jobs_lifespan.py -v`
Expected: failure — current `create_app` doesn't wire up the queue.

- [ ] **Step 14.3: Add lifespan wiring to `create_app`**

Open `src/pipeline/dashboard/server.py`. Add to the imports near the top:

```python
from contextlib import asynccontextmanager

from pipeline.dashboard.agent_runner import ClaudeAgentRunner
from pipeline.notify.telegram import LongPollListener, TelegramNotifier
```

Then modify the `create_app` function. Find the current signature:

```python
def create_app(output_dir: Path, dev_mode: bool = False) -> FastAPI:
    output_dir.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Content Dashboard")
```

Replace with:

```python
def create_app(output_dir: Path, dev_mode: bool = False) -> FastAPI:
    output_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        notifier = TelegramNotifier.from_env()
        prompt_template = (
            Path(__file__).parent / "agent_prompt.md"
        ).read_text(encoding="utf-8")
        runner = ClaudeAgentRunner(
            prompt_template=prompt_template,
            notifier=notifier,
        )
        queue = JobQueue(
            projects_root=output_dir / "projects",
            runner=runner,
            notifier=notifier,
        )
        queue.reload_on_startup()
        await queue.start()
        app.state.job_queue = queue

        listener_task: asyncio.Task[None] | None = None
        if notifier is not None:
            listener = LongPollListener(
                notifier,
                on_callback_query=queue.handle_callback_query,
            )
            listener_task = asyncio.create_task(
                listener.run(), name="telegram-long-poll"
            )
            app.state.telegram_listener = listener

        try:
            yield
        finally:
            if listener_task is not None:
                app.state.telegram_listener.stop()
                listener_task.cancel()
                try:
                    await listener_task
                except (asyncio.CancelledError, Exception):
                    pass
            await queue.shutdown()

    app = FastAPI(title="Content Dashboard", lifespan=lifespan)
```

At the end of `create_app` (just before the existing `return app`), add:

```python
    register_job_endpoints(app, output_dir=output_dir)
```

- [ ] **Step 14.4: Run the lifespan smoke test — expect pass**

Run: `uv run pytest tests/integration/test_dashboard_jobs_lifespan.py -v`
Expected: 2 passed.

- [ ] **Step 14.5: Run the full test suite (excluding the known pre-existing failure)**

Run: `uv run pytest --deselect tests/unit/test_compose_v2.py::test_compose_burn_subtitles_false_returns_plain_variant -q`
Expected: all pass.

- [ ] **Step 14.6: Final lint + type check**

Run:
```bash
uv run ruff check src/pipeline/dashboard/job_queue.py \
                  src/pipeline/dashboard/agent_runner.py \
                  src/pipeline/dashboard/server.py \
                  src/pipeline/notify/telegram.py \
                  src/pipeline/cli_subtitle.py \
                  src/pipeline/cli_overlay.py \
                  src/pipeline/cli_image.py \
                  src/pipeline/cli_narration.py \
                  src/pipeline/storyboard.py
```
Expected: no errors.

Run:
```bash
uv run mypy src/pipeline/dashboard/job_queue.py \
            src/pipeline/dashboard/agent_runner.py \
            src/pipeline/cli_subtitle.py \
            src/pipeline/cli_overlay.py \
            src/pipeline/cli_image.py
```
Expected: no errors. Pre-existing mypy issues elsewhere in `src/` may persist; ignore those.

- [ ] **Step 14.7: Manual smoke — start the dashboard and submit a no-op job**

Pick any existing project under `output/projects/`. Then:

```bash
PROJ=$(ls output/projects/ | head -1)

# Start the dashboard in one terminal:
./scripts/start-dashboard.sh --local-only &
sleep 3

# Submit a job (curl).
curl -s -X POST "http://localhost:8765/api/jobs/$PROJ/submit" \
  -H 'Content-Type: application/json' \
  -d '{"tokens": ["@s1/subtitle"], "instruction": "tighten this"}'
```

Expected: JSON response `{"ok": true, "job_id": "<hex>", "status": "queued"}`. The
sidecar file appears at `output/projects/$PROJ/edit_jobs/<hex>.json`. If `claude`
is not on PATH, the agent will fail and the job sidecar will end up in
`failed` state — that's expected; what we're verifying is the endpoint plumbing.

Tear down: `kill %1`.

- [ ] **Step 14.8: Commit**

```bash
git add src/pipeline/dashboard/server.py tests/integration/test_dashboard_jobs_lifespan.py
git commit -m "feat(dashboard): wire JobQueue + long-poll into FastAPI lifespan"
```

---

## Plan complete

After all tasks above are checked off:

- New module `src/pipeline/dashboard/job_queue.py` provides per-project FIFO queues with parallel-across-projects execution, cancel, and crash-recovery.
- New module `src/pipeline/dashboard/agent_runner.py` spawns `claude -p` per job and streams stdout to a Telegram message.
- `src/pipeline/notify/telegram.py` extends with `reply_to_message_id`, `reply_markup`, `send_photo`, `send_video`, `edit_message_text`, and a long-poll `LongPollListener` for `callback_query` updates.
- Four new project-scoped CLI verbs (`subtitle set`, `overlay set`, `narration regen`, `image regen`) mutate storyboard state; the agent chains the appropriate `compose rescene` / `compose reburn` afterwards.
- New HTTP endpoints `POST /api/jobs/{project_id}/submit` and `POST /api/jobs/{project_id}/{job_id}/cancel` route through `app.state.job_queue`.
- The dashboard FastAPI lifespan starts the JobQueue and the Telegram long-poll listener (the latter is no-op when env vars are unset, so dev usage stays unchanged).
- `agent_prompt.md` is loaded once at startup and supplemented per-job with project id, storyboard summary, and resolved tokens.

**Hand-off note for follow-on plans:**

- Plan 4 (frontend edit-mode + composer + click-to-mint) calls `POST /api/jobs/<id>/submit` from the floating composer's submit handler. The API response shape (`{job_id, status}`) and cancel route are stable.
- Plan 5 (trust gate, revert, SSE) layers on top: extend `EditJob.status` to gate auto-apply vs propose-then-apply (the schema already accepts new states cleanly), add `revert_payload` to session_log entries, and add an SSE channel emitting `job_status` events whenever `save_job` runs.
