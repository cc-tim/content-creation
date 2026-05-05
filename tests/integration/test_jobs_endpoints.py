from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pipeline.dashboard.job_queue import EditJob, JobQueue, SubActionResult
from pipeline.dashboard.server import register_job_endpoints


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[EditJob] = []
        self._block: asyncio.Event | None = None
        self.entered: asyncio.Event | None = None

    def bind_loop(self) -> None:
        self._block = asyncio.Event()
        self.entered = asyncio.Event()

    async def run(self, job: EditJob, project_root: Path) -> list[SubActionResult]:
        assert self._block is not None
        assert self.entered is not None
        self.calls.append(job)
        self.entered.set()
        await self._block.wait()
        return [SubActionResult(verb="subtitle set", scene="s9", ok=True, message="ok")]

    def release(self) -> None:
        if self._block is not None:
            self._block.set()


@pytest.fixture
def app_with_queue(tmp_path: Path):
    output = tmp_path / "output"
    (output / "projects" / "42").mkdir(parents=True)
    runner = _FakeRunner()
    queue = JobQueue(projects_root=output / "projects", runner=runner, notifier=None)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runner.bind_loop()
        await queue.start()
        try:
            yield
        finally:
            runner.release()
            await queue.shutdown()

    app = FastAPI(lifespan=lifespan)
    register_job_endpoints(app, output_dir=output)
    app.state.job_queue = queue

    yield app, runner


def test_submit_endpoint_returns_job_id_and_persists_sidecar(
    app_with_queue,
    tmp_path: Path,
) -> None:
    app, runner = app_with_queue
    with TestClient(app) as client:
        response = client.post(
            "/api/jobs/42/submit",
            json={"tokens": ["@s9/visual"], "instruction": "darken"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "job_id" in body
        sidecar = (
            tmp_path / "output" / "projects" / "42" / "edit_jobs" / f"{body['job_id']}.json"
        )
        assert sidecar.exists()
        runner.release()


def test_submit_rejects_unknown_project(app_with_queue) -> None:
    app, runner = app_with_queue
    with TestClient(app) as client:
        response = client.post(
            "/api/jobs/9999/submit",
            json={"tokens": [], "instruction": "x"},
        )
        assert response.status_code == 404
        runner.release()


def test_submit_rejects_empty_instruction(app_with_queue) -> None:
    app, runner = app_with_queue
    with TestClient(app) as client:
        response = client.post(
            "/api/jobs/42/submit",
            json={"tokens": ["@s9"], "instruction": ""},
        )
        assert response.status_code == 400
        runner.release()


def test_cancel_endpoint_terminates_in_flight_job(app_with_queue, tmp_path: Path) -> None:
    app, runner = app_with_queue
    with TestClient(app) as client:
        submit = client.post(
            "/api/jobs/42/submit",
            json={"tokens": [], "instruction": "x"},
        )
        job_id = submit.json()["job_id"]
        assert runner.entered is not None
        for _ in range(50):
            if runner.entered.is_set():
                break
            time.sleep(0.02)
        cancel = client.post(f"/api/jobs/42/{job_id}/cancel")
        assert cancel.status_code == 200
        assert cancel.json()["cancelled"] is True

    sidecar = tmp_path / "output" / "projects" / "42" / "edit_jobs" / f"{job_id}.json"
    job = json.loads(sidecar.read_text(encoding="utf-8"))
    assert job["status"] in ("cancelled", "interrupted")


def test_cancel_returns_false_for_unknown_job(app_with_queue) -> None:
    app, runner = app_with_queue
    with TestClient(app) as client:
        runner.release()
        response = client.post("/api/jobs/42/nonexistent/cancel")
        assert response.status_code == 200
        assert response.json()["cancelled"] is False
