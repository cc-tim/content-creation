from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pipeline.dashboard.agent_runner import (
    ClaudeAgentRunner,
    build_agent_prompt,
    summarize_storyboard,
)
from pipeline.dashboard.job_queue import EditJob
from pipeline.storyboard import Scene, Storyboard


def test_summarize_storyboard_lists_scene_ids_and_narration_prefix(tmp_path: Path) -> None:
    sb = Storyboard(scenes=[
        Scene(
            id="s1",
            section="hook",
            narration="Once upon a time there was a kingdom",
            narration_est_sec=3.0,
        ),
        Scene(id="s2", section="content", narration="Short.", narration_est_sec=1.0),
    ])
    sb_path = tmp_path / "storyboard.json"
    sb.save(sb_path)
    summary = summarize_storyboard(sb_path)
    assert "s1" in summary
    assert "s2" in summary
    assert "Once upon a time" in summary
    assert "Short." in summary


def test_summarize_storyboard_returns_placeholder_when_missing(tmp_path: Path) -> None:
    assert "no storyboard" in summarize_storyboard(tmp_path / "nope.json").lower()


def test_build_agent_prompt_substitutes_placeholders() -> None:
    template = (
        "Project: {project_id}\n"
        "Tokens: {tokens}\n"
        "Instruction: {instruction}\n"
        "Storyboard:\n{storyboard_summary}\n"
    )
    job = EditJob(
        job_id="j1",
        project_id="42",
        tokens=["@s9/visual", "@s11/subtitle"],
        instruction="darken these",
    )
    out = build_agent_prompt(template=template, job=job, storyboard_summary="(scenes...)")
    assert "Project: 42" in out
    assert "@s9/visual" in out
    assert "@s11/subtitle" in out
    assert "darken these" in out
    assert "(scenes...)" in out


@pytest.mark.asyncio
async def test_runner_invokes_subprocess_and_returns_result(tmp_path: Path) -> None:
    project = tmp_path / "42"
    project.mkdir()
    (project / "storyboard.json").write_text("{}", encoding="utf-8")
    captured_argv: list[list[str]] = []
    captured_env: list[dict[str, str] | None] = []

    async def fake_factory(
        argv: list[str], *, env: dict[str, str] | None = None
    ) -> asyncio.subprocess.Process:
        captured_argv.append(argv)
        captured_env.append(env)
        return await asyncio.create_subprocess_exec(
            "python",
            "-c",
            "import sys; sys.stdout.write('subtitle set s9 ok\\n')",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    runner = ClaudeAgentRunner(
        prompt_template="P: {project_id}\nI: {instruction}\nT: {tokens}\nS: {storyboard_summary}",
        notifier=None,
        subprocess_factory=fake_factory,
        dashboard_base_url="http://dashboard.test",
    )
    job = EditJob(job_id="j1", project_id="42", tokens=["@s9"], instruction="x")
    job.telegram_opener_id = 999
    results = await runner.run(job, project_root=project)
    assert captured_argv[0][0] == "claude"
    assert "-p" in captured_argv[0]
    assert captured_env[0] is not None
    assert captured_env[0]["PIPELINE_JOB_ID"] == "j1"
    assert captured_env[0]["PIPELINE_DASHBOARD_BASE_URL"] == "http://dashboard.test"
    assert results[0].ok is True
    assert "subtitle set s9 ok" in results[0].message


@pytest.mark.asyncio
async def test_runner_marks_failure_on_nonzero_exit(tmp_path: Path) -> None:
    project = tmp_path / "42"
    project.mkdir()
    (project / "storyboard.json").write_text("{}", encoding="utf-8")

    async def fake_factory(
        argv: list[str], *, env: dict[str, str] | None = None
    ) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            "python",
            "-c",
            "import sys; sys.stderr.write('boom\\n'); sys.exit(2)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    runner = ClaudeAgentRunner(prompt_template="x", notifier=None, subprocess_factory=fake_factory)
    results = await runner.run(
        EditJob(job_id="j1", project_id="42", tokens=[], instruction="x"),
        project_root=project,
    )
    assert results[0].ok is False
    assert "exit" in results[0].message.lower()


@pytest.mark.asyncio
async def test_runner_terminates_subprocess_on_cancel(tmp_path: Path) -> None:
    project = tmp_path / "42"
    project.mkdir()
    (project / "storyboard.json").write_text("{}", encoding="utf-8")

    async def fake_factory(
        argv: list[str], *, env: dict[str, str] | None = None
    ) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            "python",
            "-c",
            "import time; time.sleep(10)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    runner = ClaudeAgentRunner(prompt_template="x", notifier=None, subprocess_factory=fake_factory)

    async def run_and_cancel() -> None:
        task = asyncio.create_task(
            runner.run(
                EditJob(job_id="j1", project_id="42", tokens=[], instruction="x"),
                project_root=project,
            )
        )
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    await asyncio.wait_for(run_and_cancel(), timeout=3.0)
