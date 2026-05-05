"""Per-project SSE pub/sub and allowlisted file-change polling."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import structlog

logger = structlog.get_logger()

EventKind = Literal["files_changed", "job_status", "ping"]

_ALLOWLIST_GLOBS: tuple[str, ...] = (
    "storyboard.json",
    "compose/*.mp4",
    "compose/scene_finals/*.mp4",
    "narration_overrides/*.wav",
    "images/scenes/*.png",
)


@dataclass(frozen=True)
class SSEEvent:
    kind: EventKind
    payload: dict[str, Any]

    def to_sse_line(self) -> str:
        data = json.dumps(self.payload, ensure_ascii=False, separators=(",", ":"))
        return f"event: {self.kind}\ndata: {data}\n\n"


class _Subscription:
    """Async iterator for a single subscriber."""

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue()
        self.closed = False

    def __aiter__(self) -> _Subscription:
        return self

    async def __anext__(self) -> SSEEvent:
        event = await self.queue.get()
        if event is None:
            raise StopAsyncIteration
        return event

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.queue.put_nowait(None)


class SSEEmitter:
    """Small in-memory per-project pub/sub for dashboard SSE events."""

    def __init__(self) -> None:
        self._subs: dict[str, list[_Subscription]] = {}

    def subscribe(self, project_id: str) -> _Subscription:
        sub = _Subscription(project_id)
        self._subs.setdefault(project_id, []).append(sub)
        return sub

    def unsubscribe(self, sub: _Subscription) -> None:
        subs = self._subs.get(sub.project_id)
        if subs is not None and sub in subs:
            subs.remove(sub)
            if not subs:
                self._subs.pop(sub.project_id, None)
        sub.close()

    def publish_files_changed(self, project_id: str, paths: Iterable[str]) -> None:
        self._publish(
            project_id,
            SSEEvent(kind="files_changed", payload={"paths": list(paths)}),
        )

    def publish_job_status(
        self,
        job: Any,
        *,
        job_status: dict[str, Any] | None = None,
    ) -> None:
        if job_status is not None:
            self._publish(str(job), SSEEvent(kind="job_status", payload=dict(job_status)))
            return

        project_id = _read_field(job, "project_id")
        if project_id is None:
            raise ValueError("job_status event requires a project_id")
        payload = _job_status_payload(job)
        self._publish(str(project_id), SSEEvent(kind="job_status", payload=payload))

    def _publish(self, project_id: str, event: SSEEvent) -> None:
        for sub in list(self._subs.get(project_id, [])):
            if sub.closed:
                self.unsubscribe(sub)
                continue
            sub.queue.put_nowait(event)


class FileWatcher:
    """Poll allowlisted project files and emit files_changed on mtime changes."""

    def __init__(
        self,
        emitter: SSEEmitter,
        *,
        projects_root: Path,
        tick_sec: float = 1.0,
    ) -> None:
        self._emitter = emitter
        self._projects_root = projects_root
        self._tick_sec = tick_sec
        self._task: asyncio.Task[None] | None = None
        self._stopped: asyncio.Event | None = None
        self._mtimes: dict[tuple[str, str], float] = {}

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stopped = asyncio.Event()
        self._scan(seed=True)
        self._task = asyncio.create_task(self._run(), name="dashboard-sse-file-watcher")

    async def stop(self) -> None:
        if self._stopped is not None:
            self._stopped.set()
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _run(self) -> None:
        assert self._stopped is not None
        while not self._stopped.is_set():
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._tick_sec)
                return
            except TimeoutError:
                pass

            try:
                self._scan(seed=False)
            except Exception:
                logger.exception("file_watcher.scan_error")

    def _scan(self, *, seed: bool) -> None:
        if not self._projects_root.exists():
            return

        seen: set[tuple[str, str]] = set()
        for project_dir in self._projects_root.iterdir():
            if not project_dir.is_dir():
                continue
            project_id = project_dir.name
            changed: list[str] = []
            for relpath, path in self._iter_allowlisted(project_dir):
                key = (project_id, relpath)
                seen.add(key)
                try:
                    mtime = path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if self._mtimes.get(key) == mtime:
                    continue
                self._mtimes[key] = mtime
                if not seed:
                    changed.append(relpath)
            if changed:
                self._emitter.publish_files_changed(project_id, changed)

        for key in set(self._mtimes) - seen:
            del self._mtimes[key]

    @staticmethod
    def _iter_allowlisted(project_dir: Path) -> list[tuple[str, Path]]:
        results: list[tuple[str, Path]] = []
        for pattern in _ALLOWLIST_GLOBS:
            for path in sorted(project_dir.glob(pattern)):
                if not path.is_file():
                    continue
                relpath = path.relative_to(project_dir).as_posix()
                results.append((relpath, path))
        return results


def _read_field(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _job_status_payload(job: Any) -> dict[str, Any]:
    if isinstance(job, dict):
        payload = dict(job)
    elif hasattr(job, "model_dump"):
        payload = job.model_dump()
    else:
        fields = (
            "job_id",
            "project_id",
            "status",
            "tokens",
            "instruction",
            "created_at",
            "started_at",
            "finished_at",
        )
        payload = {field: _read_field(job, field) for field in fields if _read_field(job, field) is not None}
    return payload
