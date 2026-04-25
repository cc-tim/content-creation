from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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
        from pipeline.session_log import SessionEntry, append_session, new_session_id

        stage_names = [s.name for s in self.stages]
        session = SessionEntry(
            session_id=new_session_id(),
            timestamp=datetime.now().isoformat(timespec="seconds"),
            command=f"produce: {' → '.join(stage_names)}",
        )

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
                session.stages.append(stage.name)
                logger.info("orchestrator.stage.complete", stage=stage.name)
            except Exception as e:
                logger.error("orchestrator.stage.failed", stage=stage.name, error=str(e))
                session.outcome = "failed"
                session.error = str(e)[:200]
                session.summary = f"failed at {stage.name}"
                append_session(ctx.work_dir, session)
                return StageResult(
                    success=False,
                    ctx=ctx,
                    failed_stage=stage.name,
                    error=str(e),
                )

        session.summary = " → ".join(session.stages) if session.stages else " → ".join(stage_names)
        append_session(ctx.work_dir, session)
        return StageResult(success=True, ctx=ctx)
