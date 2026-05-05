from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from pipeline.dashboard.sse_emitter import FileWatcher, SSEEmitter, SSEEvent


@pytest.mark.asyncio
async def test_subscribe_receives_published_event() -> None:
    emitter = SSEEmitter()
    sub = emitter.subscribe("42")
    emitter.publish_files_changed("42", paths=["storyboard.json"])

    event = await asyncio.wait_for(sub.__anext__(), timeout=1.0)
    assert event.kind == "files_changed"
    assert event.payload == {"paths": ["storyboard.json"]}


@pytest.mark.asyncio
async def test_multiple_subscribers_each_receive_event() -> None:
    emitter = SSEEmitter()
    sub_a = emitter.subscribe("42")
    sub_b = emitter.subscribe("42")
    emitter.publish_files_changed("42", paths=["x"])
    e_a = await asyncio.wait_for(sub_a.__anext__(), timeout=1.0)
    e_b = await asyncio.wait_for(sub_b.__anext__(), timeout=1.0)
    assert e_a.payload == e_b.payload == {"paths": ["x"]}


@pytest.mark.asyncio
async def test_isolation_across_projects() -> None:
    emitter = SSEEmitter()
    sub_42 = emitter.subscribe("42")
    sub_99 = emitter.subscribe("99")
    emitter.publish_files_changed("42", paths=["x"])
    e = await asyncio.wait_for(sub_42.__anext__(), timeout=1.0)
    assert e.payload == {"paths": ["x"]}
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(sub_99.__anext__(), timeout=0.1)


@pytest.mark.asyncio
async def test_publish_job_status_emits_job_status_event() -> None:
    emitter = SSEEmitter()
    sub = emitter.subscribe("42")
    emitter.publish_job_status({"project_id": "42", "job_id": "j1", "status": "running"})
    event = await asyncio.wait_for(sub.__anext__(), timeout=1.0)
    assert event.kind == "job_status"
    assert event.payload["status"] == "running"


@pytest.mark.asyncio
async def test_publish_job_status_accepts_explicit_payload_for_future_queue_wiring() -> None:
    emitter = SSEEmitter()
    sub = emitter.subscribe("42")
    emitter.publish_job_status("42", job_status={"job_id": "j1", "status": "done"})
    event = await asyncio.wait_for(sub.__anext__(), timeout=1.0)
    assert event.kind == "job_status"
    assert event.payload == {"job_id": "j1", "status": "done"}


@pytest.mark.asyncio
async def test_unsubscribe_stops_iteration() -> None:
    emitter = SSEEmitter()
    sub = emitter.subscribe("42")
    emitter.unsubscribe(sub)
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(sub.__anext__(), timeout=0.5)


def test_sse_event_serializes_wire_format() -> None:
    event = SSEEvent(kind="files_changed", payload={"paths": ["storyboard.json"]})
    assert event.to_sse_line() == 'event: files_changed\ndata: {"paths":["storyboard.json"]}\n\n'


@pytest.mark.asyncio
async def test_file_watcher_emits_when_storyboard_mtime_changes(tmp_path: Path) -> None:
    proj = tmp_path / "projects" / "42"
    proj.mkdir(parents=True)
    sb = proj / "storyboard.json"
    sb.write_text("{}", encoding="utf-8")

    emitter = SSEEmitter()
    watcher = FileWatcher(emitter, projects_root=tmp_path / "projects", tick_sec=0.05)
    await watcher.start()
    try:
        sub = emitter.subscribe("42")
        time.sleep(0.1)
        sb.write_text('{"x": 1}', encoding="utf-8")

        event = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
        assert event.kind == "files_changed"
        assert "storyboard.json" in event.payload["paths"]
    finally:
        await watcher.stop()


@pytest.mark.asyncio
async def test_file_watcher_emits_for_compose_outputs(tmp_path: Path) -> None:
    proj = tmp_path / "projects" / "42"
    (proj / "compose").mkdir(parents=True)

    emitter = SSEEmitter()
    watcher = FileWatcher(emitter, projects_root=tmp_path / "projects", tick_sec=0.05)
    await watcher.start()
    try:
        sub = emitter.subscribe("42")
        (proj / "compose" / "final.mp4").write_bytes(b"\x00\x00")

        event = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
        assert event.kind == "files_changed"
        assert "compose/final.mp4" in event.payload["paths"]
    finally:
        await watcher.stop()


@pytest.mark.asyncio
async def test_file_watcher_emits_for_nested_scene_finals(tmp_path: Path) -> None:
    proj = tmp_path / "projects" / "42"
    (proj / "compose" / "scene_finals").mkdir(parents=True)

    emitter = SSEEmitter()
    watcher = FileWatcher(emitter, projects_root=tmp_path / "projects", tick_sec=0.05)
    await watcher.start()
    try:
        sub = emitter.subscribe("42")
        (proj / "compose" / "scene_finals" / "s1.mp4").write_bytes(b"\x00")

        event = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
        assert event.kind == "files_changed"
        assert "compose/scene_finals/s1.mp4" in event.payload["paths"]
    finally:
        await watcher.stop()


@pytest.mark.asyncio
async def test_file_watcher_ignores_paths_outside_allowlist(tmp_path: Path) -> None:
    proj = tmp_path / "projects" / "42"
    proj.mkdir(parents=True)
    (proj / "storyboard.json").write_text("{}", encoding="utf-8")

    emitter = SSEEmitter()
    watcher = FileWatcher(emitter, projects_root=tmp_path / "projects", tick_sec=0.05)
    await watcher.start()
    try:
        sub = emitter.subscribe("42")
        (proj / "random.txt").write_text("ignore", encoding="utf-8")

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(sub.__anext__(), timeout=0.3)
    finally:
        await watcher.stop()
