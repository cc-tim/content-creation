from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pipeline.dashboard.sse_emitter import SSEEmitter


def _sse_endpoint(app: Any):
    for route in app.routes:
        if getattr(route, "path", None) == "/api/sse/{project_id}":
            return route.endpoint
    raise AssertionError("SSE endpoint not registered")


async def _next_text(iterator: Any) -> str:
    chunk = await anext(iterator)
    if isinstance(chunk, bytes):
        return chunk.decode("utf-8")
    return str(chunk)


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("pipeline.notify.telegram.TelegramNotifier.from_env", lambda: None)

    from pipeline.dashboard.server import create_app

    app = create_app(output_dir=tmp_path)
    app.state.sse_emitter = SSEEmitter()
    return app


@pytest.mark.asyncio
async def test_sse_endpoint_streams_published_event(app) -> None:
    response = await _sse_endpoint(app)("42", keepalive_sec=0.2)
    iterator = response.body_iterator

    assert await _next_text(iterator) == ": connected\n\n"
    app.state.sse_emitter.publish_files_changed("42", ["storyboard.json"])
    event = await _next_text(iterator)

    assert event == 'event: files_changed\ndata: {"paths":["storyboard.json"]}\n\n'


@pytest.mark.asyncio
async def test_sse_endpoint_emits_keepalive_ping(app) -> None:
    response = await _sse_endpoint(app)("42", keepalive_sec=0.01)
    iterator = response.body_iterator

    assert await _next_text(iterator) == ": connected\n\n"
    assert await _next_text(iterator) == "event: ping\ndata: {}\n\n"
