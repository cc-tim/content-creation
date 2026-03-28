from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
import typer

from pipeline.config import PipelineConfig
from pipeline.models import Locale
from pipeline.orchestrator import Orchestrator
from pipeline.stages.acquire import AcquireStage
from pipeline.stages.analyze import AnalyzeStage
from pipeline.stages.base import PipelineContext
from pipeline.stages.compose import ComposeStage
from pipeline.stages.scriptwrite import ScriptwriteStage
from pipeline.stages.tts import TtsStage

logger = structlog.get_logger()
app = typer.Typer(name="pipeline", help="YouTube content porting pipeline")


@app.command()
def produce(
    url: str = typer.Option(..., "--url", help="YouTube video URL"),
    locale: str = typer.Option("zh-TW", "--locale", help="Target locale (zh-TW, ja, es-MX)"),
    start_from: str | None = typer.Option(None, "--start-from", help="Resume from stage"),
    project_id: int = typer.Option(0, "--project-id", help="Project ID (0 = auto)"),
    skip_review: bool = typer.Option(False, "--skip-review", help="Skip human script review gate"),
) -> None:
    """Run the full production pipeline for a single video."""
    config = PipelineConfig()

    # Create project directory
    if project_id == 0:
        import time
        project_id = int(time.time())

    work_dir = config.OUTPUT_DIR / "projects" / str(project_id)
    work_dir.mkdir(parents=True, exist_ok=True)

    ctx = PipelineContext(
        project_id=project_id,
        source_url=url,
        locale=locale,
        work_dir=work_dir,
    )

    # Phase 1: acquire → analyze → scriptwrite
    pre_review_stages = [
        AcquireStage(),
        AnalyzeStage(),
        ScriptwriteStage(),
    ]

    # Phase 2: tts → compose (after human review)
    post_review_stages = [
        TtsStage(),
        ComposeStage(),
    ]

    # Run phase 1 (or resume from a specific stage)
    if start_from and start_from in ("tts", "compose"):
        # Resuming after review — load existing context
        ctx = PipelineContext.load(work_dir / "context.json")
        orch = Orchestrator(stages=post_review_stages)
        result = asyncio.run(orch.run(ctx, start_from=start_from))
    else:
        orch = Orchestrator(stages=pre_review_stages)
        result = asyncio.run(orch.run(ctx, start_from=start_from))

        if result.success and not skip_review:
            typer.echo(f"\n--- HUMAN REVIEW GATE ---")
            typer.echo(f"Script ready for review: {result.ctx.script_path}")
            typer.echo(f"Edit the script, then resume with:")
            typer.echo(f"  uv run pipeline produce --url \"{url}\" --locale {locale} "
                       f"--project-id {project_id} --start-from tts")
            return

        if result.success and skip_review:
            # Continue directly to phase 2
            orch = Orchestrator(stages=post_review_stages)
            result = asyncio.run(orch.run(result.ctx))

    if result.success:
        typer.echo(f"\nPipeline complete! Output: {result.ctx.final_video_path}")
    else:
        typer.echo(f"\nPipeline failed at stage '{result.failed_stage}': {result.error}")
        raise typer.Exit(code=1)


@app.command()
def acquire(
    url: str = typer.Option(..., "--url", help="YouTube video URL"),
) -> None:
    """Download video and extract transcript only."""
    config = PipelineConfig()
    import time
    project_id = int(time.time())
    work_dir = config.OUTPUT_DIR / "projects" / str(project_id)
    work_dir.mkdir(parents=True, exist_ok=True)

    ctx = PipelineContext(
        project_id=project_id,
        source_url=url,
        locale="zh-TW",
        work_dir=work_dir,
    )

    result = asyncio.run(Orchestrator(stages=[AcquireStage()]).run(ctx))
    if result.success:
        typer.echo(f"Acquired: {result.ctx.video_path}")
        typer.echo(f"Transcript: {result.ctx.transcript_path}")
    else:
        typer.echo(f"Failed: {result.error}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
