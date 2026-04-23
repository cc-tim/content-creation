from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger()

_MDV2_ESCAPE = str.maketrans({
    "_": r"\_", "*": r"\*", "[": r"\[", "]": r"\]",
    "(": r"\(", ")": r"\)", "~": r"\~", "`": r"\`",
    ">": r"\>", "#": r"\#", "+": r"\+", "-": r"\-",
    "=": r"\=", "|": r"\|", "{": r"\{", "}": r"\}",
    ".": r"\.", "!": r"\!",
})


def _escape_mdv2(text: str) -> str:
    return text.translate(_MDV2_ESCAPE)


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

    def send(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            response = httpx.post(
                url,
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "MarkdownV2"},
                timeout=10.0,
            )
            if response.status_code >= 400:
                logger.warning(
                    "telegram.send.http_error",
                    status=response.status_code,
                    body=response.text[:200],
                )
        except Exception as exc:
            logger.warning("telegram.send.exception", error=str(exc))


def notify_failure(
    *,
    project_id: int,
    profile: str,
    phase: str,
    error: str,
    fix_command: str | None,
) -> None:
    """Send a Telegram failure notification. No-op if env vars not set.

    Swallows all exceptions — must never mask the real pipeline error.
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
