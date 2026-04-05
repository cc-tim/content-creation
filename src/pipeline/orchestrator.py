from __future__ import annotations

from dataclasses import dataclass

import structlog

from pipeline.stages.base import PipelineContext, PipelineStage

logger = structlog.get_logger()


@dataclass
class StageResult:
    success: bool
    ctx: PipelineContext
    failed_stage: str = ""
    error: str = ""


class Orchestrator:
    """Chains pipeline stages, handles state persistence and resume."""

    def __init__(self, stages: list[PipelineStage]) -> None:
        self.stages = stages

    async def run(
        self,
        ctx: PipelineContext,
        start_from: str | None = None,
    ) -> StageResult:
        """Run all stages sequentially. Saves context after each stage."""
        skip = start_from is not None

        for stage in self.stages:
            if skip:
                if stage.name == start_from:
                    skip = False
                else:
                    logger.info("orchestrator.skip", stage=stage.name)
                    continue

            logger.info("orchestrator.stage.start", stage=stage.name)
            try:
                ctx = await stage.run(ctx)
                ctx.save()
                logger.info("orchestrator.stage.complete", stage=stage.name)
            except Exception as e:
                logger.error("orchestrator.stage.failed", stage=stage.name, error=str(e))
                return StageResult(
                    success=False,
                    ctx=ctx,
                    failed_stage=stage.name,
                    error=str(e),
                )

        return StageResult(success=True, ctx=ctx)
