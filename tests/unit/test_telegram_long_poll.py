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
                return httpx.Response(200, json={"ok": True, "result": []})
            return httpx.Response(200, json=self._responses.pop(0))

        super().__init__(handler)


def _patch_async_client(
    monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport
) -> None:
    monkeypatch.setattr(
        "pipeline.notify.telegram._http_async_client",
        lambda: httpx.AsyncClient(transport=transport, timeout=10.0),
    )


@pytest.mark.asyncio
async def test_get_updates_returns_result(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _ScriptedTransport(
        [{"ok": True, "result": [{"update_id": 100, "callback_query": {"id": "a"}}]}]
    )
    _patch_async_client(monkeypatch, transport)
    notifier = TelegramNotifier(token="t", chat_id="c")
    updates = await notifier.get_updates(
        offset=99, timeout=1, allowed_updates=["callback_query"]
    )
    assert updates == [{"update_id": 100, "callback_query": {"id": "a"}}]
    body = transport.requests[0].read().decode()
    assert "offset" in body
    assert "99" in body
    assert "callback_query" in body


@pytest.mark.asyncio
async def test_long_poll_dispatches_callback_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _ScriptedTransport(
        [
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
        ]
    )
    _patch_async_client(monkeypatch, transport)
    notifier = TelegramNotifier(token="t", chat_id="c")
    received: list[dict[str, Any]] = []

    async def handler(callback: dict[str, Any]) -> None:
        received.append(callback)

    listener = LongPollListener(notifier, on_callback_query=handler, poll_timeout=0)
    task = asyncio.create_task(listener.run())
    for _ in range(50):
        if received:
            break
        await asyncio.sleep(0.01)
    listener.stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert len(received) == 1
    assert received[0]["data"] == "cancel:42:job-1"


@pytest.mark.asyncio
async def test_long_poll_advances_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _ScriptedTransport(
        [
            {
                "ok": True,
                "result": [
                    {"update_id": 100, "callback_query": {"id": "a", "data": "x"}}
                ],
            },
            {"ok": True, "result": []},
            {"ok": True, "result": []},
        ]
    )
    _patch_async_client(monkeypatch, transport)
    notifier = TelegramNotifier(token="t", chat_id="c")

    async def handler(callback: dict[str, Any]) -> None:
        pass

    listener = LongPollListener(notifier, on_callback_query=handler, poll_timeout=0)
    task = asyncio.create_task(listener.run())
    for _ in range(50):
        if len(transport.requests) >= 2:
            break
        await asyncio.sleep(0.01)
    listener.stop()
    await asyncio.wait_for(task, timeout=1.0)

    second_body = transport.requests[1].read().decode()
    assert "offset" in second_body
    assert "101" in second_body


@pytest.mark.asyncio
async def test_long_poll_retries_on_transient_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(502, json={"ok": False})
        return httpx.Response(200, json={"ok": True, "result": []})

    monkeypatch.setattr(
        "pipeline.notify.telegram._http_async_client",
        lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=10.0
        ),
    )
    notifier = TelegramNotifier(token="t", chat_id="c")

    async def callback(_: dict[str, Any]) -> None:
        pass

    listener = LongPollListener(
        notifier, on_callback_query=callback, poll_timeout=0, retry_delay_sec=0.01
    )
    task = asyncio.create_task(listener.run())
    for _ in range(100):
        if call_count["n"] >= 2:
            break
        await asyncio.sleep(0.01)
    listener.stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert call_count["n"] >= 2


@pytest.mark.asyncio
async def test_long_poll_continues_after_callback_handler_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = _ScriptedTransport(
        [
            {"ok": True, "result": [{"update_id": 100, "callback_query": {"id": "a"}}]},
            {"ok": True, "result": [{"update_id": 101, "callback_query": {"id": "b"}}]},
        ]
    )
    _patch_async_client(monkeypatch, transport)
    notifier = TelegramNotifier(token="t", chat_id="c")
    seen: list[str] = []

    async def callback(query: dict[str, Any]) -> None:
        seen.append(query["id"])
        if query["id"] == "a":
            raise RuntimeError("boom")

    listener = LongPollListener(notifier, on_callback_query=callback, poll_timeout=0)
    task = asyncio.create_task(listener.run())
    for _ in range(50):
        if seen == ["a", "b"]:
            break
        await asyncio.sleep(0.01)
    listener.stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert seen == ["a", "b"]


@pytest.mark.asyncio
async def test_long_poll_stops_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _ScriptedTransport([])
    _patch_async_client(monkeypatch, transport)
    notifier = TelegramNotifier(token="t", chat_id="c")

    async def callback(_: dict[str, Any]) -> None:
        pass

    listener = LongPollListener(notifier, on_callback_query=callback, poll_timeout=0)
    task = asyncio.create_task(listener.run())
    await asyncio.sleep(0.05)
    listener.stop()
    await asyncio.wait_for(task, timeout=1.0)
    assert task.done()
