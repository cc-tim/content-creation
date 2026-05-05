"""Agent subprocess runner for dashboard edit jobs."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path

import structlog

from pipeline.dashboard.job_queue import EditJob, SubActionResult
from pipeline.notify.telegram import TelegramNotifier

logger = structlog.get_logger()

SubprocessFactory = Callable[[list[str]], Awaitable["asyncio.subprocess.Process"]]


def summarize_storyboard(storyboard_path: Path, *, max_per_line: int = 60) -> str:
    """Build a compact human-readable storyboard summary for the prompt."""
    if not storyboard_path.exists():
        return "(no storyboard found)"
    try:
        data = json.loads(storyboard_path.read_text(encoding="utf-8"))
    except Exception:
        return "(storyboard unreadable)"
    lines: list[str] = []
    for scene in data.get("scenes", []):
        narration = (scene.get("narration") or "")[:max_per_line]
        lines.append(f"  {scene.get('id')} [{scene.get('section')}]: {narration}")
    return "\n".join(lines) if lines else "(no scenes)"


def build_agent_prompt(*, template: str, job: EditJob, storyboard_summary: str) -> str:
    tokens_lines = "\n".join(f"  - {token}" for token in job.tokens) or "  (none)"
    return template.format(
        project_id=job.project_id,
        tokens=tokens_lines,
        instruction=job.instruction,
        storyboard_summary=storyboard_summary,
    )


async def _default_subprocess_factory(argv: list[str]) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


class ClaudeAgentRunner:
    """AgentRunner that spawns `claude -p` and streams stdout to Telegram."""

    def __init__(
        self,
        *,
        prompt_template: str,
        notifier: TelegramNotifier | None,
        subprocess_factory: SubprocessFactory | None = None,
        edit_interval_sec: float = 2.0,
    ) -> None:
        self._template = prompt_template
        self._notifier = notifier
        self._factory = subprocess_factory or _default_subprocess_factory
        self._edit_interval_sec = edit_interval_sec

    async def run(self, job: EditJob, project_root: Path) -> list[SubActionResult]:
        prompt = build_agent_prompt(
            template=self._template,
            job=job,
            storyboard_summary=summarize_storyboard(project_root / "storyboard.json"),
        )
        proc = await self._factory(["claude", "-p", prompt])
        accumulated: list[bytes] = []
        last_edit_time = 0.0

        async def pump_stdout() -> None:
            nonlocal last_edit_time
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    return
                accumulated.append(line)
                now = asyncio.get_event_loop().time()
                if (
                    self._notifier is not None
                    and job.telegram_opener_id is not None
                    and now - last_edit_time >= self._edit_interval_sec
                ):
                    last_edit_time = now
                    text = b"".join(accumulated).decode(errors="replace")[-3500:]
                    await asyncio.to_thread(
                        self._notifier.edit_message_text,
                        message_id=job.telegram_opener_id,
                        text=text,
                        parse_mode="",
                    )

        try:
            pump_task = asyncio.create_task(pump_stdout())
            try:
                returncode = await proc.wait()
            finally:
                try:
                    await asyncio.wait_for(pump_task, timeout=1.0)
                except TimeoutError:
                    pump_task.cancel()
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError):
                proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except TimeoutError:
                proc.kill()
                await proc.wait()
            raise

        stdout_text = b"".join(accumulated).decode(errors="replace")
        stderr_text = ""
        if proc.stderr is not None:
            stderr_text = (await proc.stderr.read()).decode(errors="replace")
        ok = returncode == 0
        message = stdout_text.strip() or stderr_text.strip() or (
            "no output" if ok else f"agent exited with code {returncode}"
        )
        if not ok and "exit" not in message.lower():
            message = f"agent exited with code {returncode}: {message}"
        return [SubActionResult(verb="agent", scene=None, ok=ok, message=message)]
