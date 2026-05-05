from __future__ import annotations

import asyncio
import contextlib
import json as _json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

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


def _http_async_client() -> httpx.AsyncClient:
    """Async factory that tests monkeypatch to inject a MockTransport."""
    return httpx.AsyncClient(timeout=30.0)


@dataclass(frozen=True)
class TelegramNotifier:
    token: str
    chat_id: str

    @classmethod
    def from_env(cls) -> TelegramNotifier | None:
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
        return cast(dict[str, Any], data.get("result", {}))

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
        return cast(dict[str, Any], payload.get("result", {}))

    def send_message(
        self,
        text: str,
        *,
        parse_mode: str = "MarkdownV2",
        reply_to_message_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Send a message and return Telegram's result payload on success."""
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
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        try:
            files = {"photo": (photo_path.name, photo_path.read_bytes())}
        except Exception as exc:
            logger.warning(
                "telegram.media_read.exception",
                path=str(photo_path),
                error=str(exc),
            )
            return None
        data = self._media_payload(caption, reply_to_message_id, reply_markup)
        return self._post_multipart("sendPhoto", files, data)

    def send_video(
        self,
        video_path: Path,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        try:
            files = {"video": (video_path.name, video_path.read_bytes())}
        except Exception as exc:
            logger.warning(
                "telegram.media_read.exception",
                path=str(video_path),
                error=str(exc),
            )
            return None
        data = self._media_payload(caption, reply_to_message_id, reply_markup)
        return self._post_multipart("sendVideo", files, data)

    def _media_payload(
        self,
        caption: str | None,
        reply_to_message_id: int | None,
        reply_markup: dict[str, Any] | None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"chat_id": self.chat_id}
        if caption is not None:
            data["caption"] = caption
        if reply_to_message_id is not None:
            data["reply_to_message_id"] = str(reply_to_message_id)
        if reply_markup is not None:
            data["reply_markup"] = _json.dumps(reply_markup)
        return data

    async def get_updates(
        self,
        *,
        offset: int | None = None,
        timeout: int = 25,
        allowed_updates: list[str] | None = None,
    ) -> list[dict[str, Any]] | None:
        payload: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        if allowed_updates is not None:
            payload["allowed_updates"] = allowed_updates
        try:
            async with _http_async_client() as client:
                response = await client.post(self._api_url("getUpdates"), json=payload)
        except Exception as exc:
            logger.warning("telegram.get_updates.exception", error=str(exc))
            return None
        if response.status_code >= 400:
            logger.warning(
                "telegram.get_updates.http_error",
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
        return list(data.get("result", []))

    def send(self, text: str) -> None:
        """Backwards-compatible fire-and-forget message send."""
        self.send_message(text)


class LongPollListener:
    """Poll Telegram getUpdates and dispatch callback_query updates."""

    def __init__(
        self,
        notifier: TelegramNotifier,
        *,
        on_callback_query: Callable[[dict[str, Any]], Awaitable[Any]],
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
            updates = await self._fetch_updates()
            if updates is None:
                await self._sleep_or_stop(self._retry_delay_sec)
                continue
            if not updates:
                await self._sleep_or_stop(0.01)
                continue
            for update in updates:
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    self._offset = update_id + 1
                callback = update.get("callback_query")
                if callback is not None:
                    try:
                        await self._on_callback(callback)
                    except Exception as exc:
                        logger.warning(
                            "telegram.long_poll.handler_exception",
                            error=str(exc),
                        )
            await asyncio.sleep(0)

    async def _fetch_updates(self) -> list[dict[str, Any]] | None:
        try:
            return await self._notifier.get_updates(
                offset=self._offset,
                timeout=self._poll_timeout,
                allowed_updates=["callback_query"],
            )
        except Exception as exc:
            logger.warning("telegram.long_poll.exception", error=str(exc))
            return None

    async def _sleep_or_stop(self, sec: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stopped.wait(), timeout=sec)


def notify_failure(
    *,
    project_id: int,
    profile: str,
    phase: str,
    error: str,
    fix_command: str | None,
) -> None:
    """Send a Telegram failure notification. No-op if env vars not set.

    Swallows all exceptions -- must never mask the real pipeline error.
    """
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
