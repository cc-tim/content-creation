from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from pipeline.orchestrator import Orchestrator, StageResult
from pipeline.stages.base import PipelineContext, PipelineStage


class FakePassStage(PipelineStage):
    @property
    def name(self) -> str:
        return "fake_pass"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        ctx.transcript_text = "processed"
        return ctx


class FakeFailStage(PipelineStage):
    @property
    def name(self) -> str:
        return "fake_fail"

    async def run(self, ctx: PipelineContext) -> PipelineContext:
        raise RuntimeError("Stage exploded")


async def test_orchestrator_runs_stages_in_order(sample_context):
    orch = Orchestrator(stages=[FakePassStage()])
    result = await orch.run(sample_context)
    assert result.success
    assert result.ctx.transcript_text == "processed"


async def test_orchestrator_stops_on_failure(sample_context):
    orch = Orchestrator(stages=[FakeFailStage(), FakePassStage()])
    result = await orch.run(sample_context)
    assert not result.success
    assert result.failed_stage == "fake_fail"
    assert "exploded" in result.error


async def test_orchestrator_saves_context_after_each_stage(sample_context):
    orch = Orchestrator(stages=[FakePassStage()])
    result = await orch.run(sample_context)
    context_file = sample_context.work_dir / "context.json"
    assert context_file.exists()
