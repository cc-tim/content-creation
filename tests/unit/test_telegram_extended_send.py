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


def _notifier_with_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TelegramNotifier, _MockTransport]:
    transport = _MockTransport()
    monkeypatch.setattr(
        "pipeline.notify.telegram._http_client",
        lambda: httpx.Client(transport=transport, timeout=10.0),
    )
    return TelegramNotifier(token="t", chat_id="c"), transport


def test_send_message_returns_message_id(monkeypatch: pytest.MonkeyPatch) -> None:
    notifier, transport = _notifier_with_mock(monkeypatch)
    result = notifier.send_message("hello")
    assert result == {"message_id": 12345}
    assert transport.requests[0].url.path.endswith("/sendMessage")


def test_send_message_with_reply_to_passes_param(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notifier, transport = _notifier_with_mock(monkeypatch)
    notifier.send_message("hello", reply_to_message_id=999)
    body = transport.requests[0].read().decode()
    assert "reply_to_message_id" in body
    assert "999" in body


def test_send_message_with_reply_markup_serializes_inline_keyboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notifier, transport = _notifier_with_mock(monkeypatch)
    keyboard = {
        "inline_keyboard": [[{"text": "Cancel", "callback_data": "cancel:job-1"}]]
    }
    notifier.send_message("queued", reply_markup=keyboard)
    body = transport.requests[0].read().decode()
    assert "callback_data" in body
    assert "cancel:job-1" in body


def test_edit_message_text_calls_correct_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notifier, transport = _notifier_with_mock(monkeypatch)
    notifier.edit_message_text(message_id=12345, text="updated")
    assert transport.requests[0].url.path.endswith("/editMessageText")
    body = transport.requests[0].read().decode()
    assert "12345" in body
    assert "updated" in body


def test_send_photo_uploads_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    notifier, transport = _notifier_with_mock(monkeypatch)
    photo = tmp_path / "test.png"
    photo.write_bytes(b"fake png bytes")
    result = notifier.send_photo(photo, caption="here it is")
    assert result == {"message_id": 12345}
    assert transport.requests[0].url.path.endswith("/sendPhoto")


def test_send_video_uploads_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    notifier, transport = _notifier_with_mock(monkeypatch)
    video = tmp_path / "test.mp4"
    video.write_bytes(b"fake mp4 bytes")
    result = notifier.send_video(video, caption="rendered")
    assert result == {"message_id": 12345}
    assert transport.requests[0].url.path.endswith("/sendVideo")


def test_legacy_send_method_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    notifier, transport = _notifier_with_mock(monkeypatch)
    notifier.send("legacy text")
    assert transport.requests[0].url.path.endswith("/sendMessage")


def test_http_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"ok": False, "description": "down"})

    monkeypatch.setattr(
        "pipeline.notify.telegram._http_client",
        lambda: httpx.Client(
            transport=httpx.MockTransport(failing_handler), timeout=10.0
        ),
    )
    notifier = TelegramNotifier(token="t", chat_id="c")
    assert notifier.send_message("x") is None
    assert notifier.edit_message_text(message_id=1, text="y") is None
    assert notifier.send_photo(Path("/missing/photo.png")) is None


def test_media_reply_markup_and_reply_to(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    notifier, transport = _notifier_with_mock(monkeypatch)
    video = tmp_path / "test.mp4"
    video.write_bytes(b"fake mp4 bytes")
    keyboard: dict[str, Any] = {
        "inline_keyboard": [[{"text": "Cancel", "callback_data": "cancel:job-1"}]]
    }
    notifier.send_video(video, reply_to_message_id=999, reply_markup=keyboard)
    body = transport.requests[0].read().decode()
    assert "reply_to_message_id" in body
    assert "999" in body
    assert "callback_data" in body
