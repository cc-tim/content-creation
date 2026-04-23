from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pipeline.notify.telegram import TelegramNotifier, notify_failure


def test_notifier_silent_when_token_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    notifier = TelegramNotifier.from_env()
    assert notifier is None


def test_notifier_silent_when_chat_id_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert TelegramNotifier.from_env() is None


def test_notifier_constructed_when_both_env_vars_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    notifier = TelegramNotifier.from_env()
    assert notifier is not None
    assert notifier.token == "abc"
    assert notifier.chat_id == "123"


def test_send_posts_to_telegram_api() -> None:
    notifier = TelegramNotifier(token="tok", chat_id="42")
    with patch("pipeline.notify.telegram.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        notifier.send("hello")
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0].endswith("/bot tok/sendMessage".replace(" ", ""))
    assert kwargs["json"]["chat_id"] == "42"
    assert kwargs["json"]["text"] == "hello"
    assert kwargs["json"]["parse_mode"] == "MarkdownV2"


def test_send_logs_but_does_not_raise_on_failure() -> None:
    notifier = TelegramNotifier(token="tok", chat_id="42")
    with patch("pipeline.notify.telegram.httpx.post", side_effect=RuntimeError("boom")):
        # Must not raise
        notifier.send("hello")


def test_notify_failure_composes_expected_message() -> None:
    with patch("pipeline.notify.telegram.TelegramNotifier.from_env") as from_env:
        sent: list[str] = []
        notifier = MagicMock()
        notifier.send = lambda msg: sent.append(msg)
        from_env.return_value = notifier

        notify_failure(
            project_id=1234,
            profile="ideal-parents-tw",
            phase="thumbnail",
            error="File too large (3.2MB > 2MB limit)",
            fix_command="pipeline publish 1234",
        )
    assert len(sent) == 1
    msg = sent[0]
    assert "1234" in msg
    assert "ideal\\-parents\\-tw" in msg or "ideal-parents-tw" in msg
    assert "thumbnail" in msg
    assert "File too large" in msg


def test_notify_failure_noop_when_no_notifier_env() -> None:
    with patch("pipeline.notify.telegram.TelegramNotifier.from_env", return_value=None):
        notify_failure(
            project_id=1,
            profile="x",
            phase="y",
            error="z",
            fix_command=None,
        )  # Must not raise
