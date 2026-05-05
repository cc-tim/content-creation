"""Per-project asyncio JobQueue + sidecar persistence for edit jobs."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()

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
    revert_target: dict | None = None


class AgentRunner(Protocol):
    """Strategy for running one job's edit agent."""

    async def run(self, job: EditJob, project_root: Path) -> list[SubActionResult]:
        ...


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
    for path in edit_dir.glob("*.json"):
        if path.name.endswith(".json.tmp"):
            continue
        try:
            jobs.append(EditJob.model_validate_json(path.read_text(encoding="utf-8")))
        except Exception:
            logger.warning("jobqueue.sidecar.unreadable", path=str(path))
            continue
    jobs.sort(key=lambda job: (job.created_at, job.job_id))
    return jobs


class JobQueue:
    """Per-project asyncio queue with one consumer coroutine per project."""

    def __init__(
        self,
        *,
        projects_root: Path,
        runner: AgentRunner,
        notifier: Any | None = None,
        sse_emitter: Any | None = None,
    ) -> None:
        self._projects_root = projects_root
        self._runner = runner
        self._notifier = notifier
        self._sse = sse_emitter
        self._queues: dict[str, asyncio.Queue[EditJob]] = {}
        self._consumers: dict[str, asyncio.Task[None]] = {}
        self._idle_events: dict[str, asyncio.Event] = {}
        self._running_jobs: dict[str, EditJob] = {}
        self._cancel_targets: dict[str, tuple[str, asyncio.Task[None]]] = {}
        self._coord: Any | None = None
        self._lock = asyncio.Lock()
        self._started = False

    def set_coordinator(self, coord: Any) -> None:
        """Wire the mutation coordinator for proposal callback routing."""
        self._coord = coord

    async def start(self) -> None:
        """Marker for explicit lifecycle. Consumers are lazy-spawned on first submit."""
        self._started = True

    async def shutdown(self) -> None:
        """Cancel all consumer tasks and clear state."""
        for task in self._consumers.values():
            task.cancel()
        for task in self._consumers.values():
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._queues.clear()
        self._consumers.clear()
        self._idle_events.clear()
        self._running_jobs.clear()
        self._cancel_targets.clear()
        self._started = False

    def reload_on_startup(self) -> None:
        """Mark sidecars left in running state as interrupted."""
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

    async def submit(self, job: EditJob) -> None:
        """Persist the job sidecar and enqueue for that project's consumer."""
        project_root = self._projects_root / job.project_id
        save_job(project_root, job)
        async with self._lock:
            self._ensure_consumer(job.project_id)
            self._idle_events[job.project_id].clear()
            await self._queues[job.project_id].put(job)
        self._publish_status(job)
        logger.info("jobqueue.submit", job_id=job.job_id, project_id=job.project_id)

    async def cancel(self, project_id: str, job_id: str) -> bool:
        """Cancel the in-flight job for this project if its id matches."""
        target = self._cancel_targets.get(project_id)
        if target is None or target[0] != job_id:
            return False
        _, task = target
        task.cancel()
        return True

    async def handle_callback_query(self, callback: dict[str, Any]) -> bool:
        """Route a Telegram callback_query update."""
        data = callback.get("data", "")
        verb, _, rest = data.partition(":")
        if verb == "cancel":
            project_id, _, job_id = rest.partition(":")
            return await self.cancel(project_id, job_id)
        if verb == "revert":
            project_id, _, mutation_id = rest.partition(":")
            return await self.enqueue_revert(project_id, mutation_id)
        if verb == "apply":
            _project_id, _, mutation_id = rest.partition(":")
            return self._resolve_proposal(mutation_id, decision="apply")
        if verb == "cancel_proposal":
            _project_id, _, mutation_id = rest.partition(":")
            return self._resolve_proposal(mutation_id, decision="cancel")
        if verb == "edit_proposal":
            project_id, _, tail = rest.partition(":")
            mutation_id, _, job_id = tail.partition(":")
            return self._handle_edit_proposal(project_id, mutation_id, job_id)
        if verb == "reburn":
            project_id, _, _job_id = rest.partition(":")
            if self._notifier is not None:
                await asyncio.to_thread(
                    self._notifier.send_message,
                    (
                        f"reburn requested for {project_id}; run "
                        f"`pipeline compose reburn --project-id {project_id}`"
                    ),
                    parse_mode="",
                )
            return True
        return False

    async def enqueue_revert(self, project_id: str, mutation_id: str) -> bool:
        """Public hook for server endpoints to submit a revert job."""
        from pipeline.dashboard.revert import synthesise_revert_job

        proj_root = self._projects_root / project_id
        if not proj_root.exists():
            return False
        try:
            job = synthesise_revert_job(project_root=proj_root, mutation_id=mutation_id)
        except (KeyError, ValueError) as exc:
            logger.warning("jobqueue.revert.refused", reason=str(exc), mutation_id=mutation_id)
            return False
        await self.submit(job)
        return True

    def _resolve_proposal(self, mutation_id: str, *, decision: str) -> bool:
        if self._coord is None:
            return False
        return bool(self._coord.resolve(mutation_id, decision=decision))

    def _handle_edit_proposal(self, project_id: str, mutation_id: str, job_id: str) -> bool:
        if self._coord is None:
            return False
        proposal = self._proposal_for(mutation_id)
        if proposal is None:
            return False
        proj_root = self._projects_root / project_id
        try:
            self._write_edit_draft(proj_root, proposal)
        except Exception as exc:
            logger.warning(
                "jobqueue.edit_proposal.write_draft_failed",
                error=str(exc),
                job_id=job_id,
                mutation_id=mutation_id,
            )
        return self._resolve_proposal(mutation_id, decision="cancel")

    def _proposal_for(self, mutation_id: str) -> Any | None:
        if self._coord is None:
            return None
        proposal_for = getattr(self._coord, "proposal_for", None)
        if callable(proposal_for):
            return proposal_for(mutation_id)
        pending_for = getattr(self._coord, "pending_for", None)
        if callable(pending_for):
            pending = pending_for(mutation_id)
            return getattr(pending, "proposal", None)
        return None

    def _write_edit_draft(self, proj_root: Path, proposal: Any) -> None:
        import json as _json

        args = getattr(proposal, "args", {})
        verb = getattr(proposal, "verb", "")
        scene_id = args.get("scene", "unknown") if isinstance(args, dict) else "unknown"
        draft = {
            "tokens": [f"@{scene_id}"],
            "text": f"refine: {verb} {args!r}",
        }
        proj_root.mkdir(parents=True, exist_ok=True)
        (proj_root / "edit_draft.json").write_text(
            _json.dumps(draft, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def wait_idle(self, project_id: str, *, timeout: float) -> None:
        """Wait until the project's queue is drained and between jobs."""
        event = self._idle_events.get(project_id)
        if event is None:
            return
        await asyncio.wait_for(event.wait(), timeout=timeout)

    def _ensure_consumer(self, project_id: str) -> None:
        if project_id in self._consumers:
            return
        self._queues[project_id] = asyncio.Queue()
        self._idle_events[project_id] = asyncio.Event()
        self._idle_events[project_id].set()
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

    def _opener_text(self, job: EditJob) -> str:
        token_line = " + ".join(job.tokens) if job.tokens else "(no tokens)"
        return f"[{job.project_id}] editing {token_line}: {job.instruction!r}"

    def _opener_keyboard(self, job: EditJob) -> dict[str, Any]:
        return {
            "inline_keyboard": [[
                {"text": "Cancel", "callback_data": f"cancel:{job.project_id}:{job.job_id}"}
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

    async def _run_job(self, job: EditJob) -> None:
        project_root = self._projects_root / job.project_id
        job.status = "running"
        job.started_at = datetime.now().isoformat(timespec="seconds")
        await self._post_opener(job)
        save_job(project_root, job)
        self._running_jobs[job.project_id] = job
        self._publish_status(job)

        run_task = asyncio.current_task()
        if run_task is not None:
            self._cancel_targets[job.project_id] = (job.job_id, run_task)

        try:
            if job.revert_target is not None:
                results = await asyncio.to_thread(_run_revert, job, project_root)
            else:
                results = await self._runner.run(job, project_root)
            job.sub_action_results = results
            job.status = "done"
            await self._maybe_post_compose_pending(job)
        except asyncio.CancelledError:
            job.status = "cancelled"
            logger.info("jobqueue.run.cancelled", job_id=job.job_id)
        except Exception as exc:
            logger.warning("jobqueue.run.failed", job_id=job.job_id, error=str(exc))
            job.status = "failed"
        finally:
            job.finished_at = datetime.now().isoformat(timespec="seconds")
            save_job(project_root, job)
            self._running_jobs.pop(job.project_id, None)
            self._cancel_targets.pop(job.project_id, None)
            self._publish_status(job)

    def _publish_status(self, job: EditJob) -> None:
        if self._sse is None:
            return
        self._sse.publish_job_status(
            job.project_id,
            job_status={
                "job_id": job.job_id,
                "status": job.status,
                "tokens": job.tokens,
                "instruction": job.instruction,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "is_revert": job.revert_target is not None,
            },
        )

    async def _maybe_post_compose_pending(self, job: EditJob) -> None:
        if self._notifier is None:
            return
        results = job.sub_action_results
        if not results:
            return
        has_successful_mutation = any(
            result.ok
            and result.verb.startswith(
                ("subtitle ", "overlay ", "narration ", "image ", "transition ")
            )
            for result in results
        )
        compose_failed = any(
            (not result.ok) and result.verb.startswith("compose ")
            for result in results
        )
        if not (has_successful_mutation and compose_failed):
            return
        keyboard = {
            "inline_keyboard": [[
                {"text": "Reburn", "callback_data": f"reburn:{job.project_id}:{job.job_id}"}
            ]]
        }
        kwargs: dict[str, Any] = {"parse_mode": "", "reply_markup": keyboard}
        if job.telegram_opener_id is not None:
            kwargs["reply_to_message_id"] = job.telegram_opener_id
        await asyncio.to_thread(
            self._notifier.send_message,
            "compose pending - render the new state with reburn?",
            **kwargs,
        )


def _run_revert(job: EditJob, project_root: Path) -> list[SubActionResult]:
    """Apply the inverse mutation for a revert job without invoking the agent."""
    import json as _json

    from pipeline.dashboard.mutation_runtime import MutationProposal, apply_mutation

    target = job.revert_target or {}
    mutation_id = target.get("mutation_id")
    if not mutation_id:
        return [SubActionResult(verb="revert", ok=False, message="no mutation_id in revert_target")]

    sessions_path = project_root / "sessions.json"
    if not sessions_path.exists():
        return [SubActionResult(verb="revert", ok=False, message="no sessions.json")]

    try:
        rows = _json.loads(sessions_path.read_text(encoding="utf-8"))
    except (_json.JSONDecodeError, OSError) as exc:
        return [SubActionResult(verb="revert", ok=False, message=f"unreadable sessions.json: {exc}")]

    source = next((row for row in rows if row.get("mutation_id") == mutation_id), None)
    if source is None or not source.get("revert_payload"):
        return [
            SubActionResult(
                verb="revert",
                ok=False,
                message=f"mutation {mutation_id} not revertable",
            )
        ]

    payload = source["revert_payload"]
    proposal = MutationProposal(
        job_id=job.job_id,
        verb=payload["verb"],
        args=payload["args"],
    )
    result = apply_mutation(proposal, project_root=project_root)
    return [
        SubActionResult(
            verb=f"revert {payload['verb']}",
            scene=payload["args"].get("scene"),
            ok=result.status == "applied",
            message=result.message,
        )
    ]
