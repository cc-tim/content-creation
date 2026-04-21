from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
import typer

from pipeline.cli_storyboard import storyboard_app
from pipeline.cli_voice import voice_app
from pipeline.config import PipelineConfig
from pipeline.orchestrator import Orchestrator
from pipeline.research.cli import app as research_app
from pipeline.stages.acquire import AcquireStage
from pipeline.stages.analyze import AnalyzeStage
from pipeline.stages.base import PipelineContext
from pipeline.stages.compose import ComposeStage
from pipeline.stages.direct import DirectStage
from pipeline.stages.tts import TtsStage

logger = structlog.get_logger()
app = typer.Typer(name="pipeline", help="YouTube content porting pipeline")
app.add_typer(voice_app, name="voice")
app.add_typer(storyboard_app, name="storyboard")
app.add_typer(research_app, name="research")


@app.command()
def produce(
    url: str = typer.Option(..., "--url", help="YouTube or web article URL"),
    locale: str = typer.Option("zh-TW", "--locale", help="Target locale (zh-TW, ja, es-MX)"),
    start_from: str | None = typer.Option(None, "--start-from", help="Resume from stage"),
    project_id: int = typer.Option(0, "--project-id", help="Project ID (0 = auto)"),
    skip_review: bool = typer.Option(False, "--skip-review", help="Skip human review gate"),
    source_type: str = typer.Option("youtube", "--source-type", help="Source: youtube or web"),
    voice: str | None = typer.Option(
        None, "--voice", help="Voice profile id (see `pipeline voice list`)."
    ),
    subtitles: bool = typer.Option(
        False,
        "--subtitles/--no-subtitles",
        help="Burn subtitles into the final video (default: off).",
    ),
    source_locale: str | None = typer.Option(
        None, "--source-locale", help="Origin of source material (e.g. US, CA, en, ja)"
    ),
    reference_storyboard: str | None = typer.Option(
        None,
        "--reference-storyboard",
        help="Path to an existing storyboard JSON used as parallel-locale reference",
    ),
) -> None:
    """Run the full production pipeline for a video or web article."""
    config = PipelineConfig()

    if project_id == 0:
        import time

        project_id = int(time.time())

    work_dir = config.OUTPUT_DIR / "projects" / str(project_id)
    work_dir.mkdir(parents=True, exist_ok=True)

    context_file = work_dir / "context.json"
    if start_from and context_file.exists():
        ctx = PipelineContext.load(context_file)
        if voice:
            ctx.voice_id = voice
        ctx.burn_subtitles = subtitles
        if source_locale is not None:
            ctx.source_locale = source_locale
        if reference_storyboard is not None:
            ctx.reference_storyboard_path = Path(reference_storyboard)
    else:
        ctx = PipelineContext(
            project_id=project_id,
            source_url=url,
            locale=locale,
            work_dir=work_dir,
            voice_id=voice,
            burn_subtitles=subtitles,
            source_locale=source_locale,
            reference_storyboard_path=(
                Path(reference_storyboard) if reference_storyboard else None
            ),
        )

    # Select acquire stage based on source type
    if source_type == "web":
        from pipeline.stages.acquire_web import AcquireWebStage

        acquire = AcquireWebStage()
    else:
        acquire = AcquireStage()

    all_stages = [
        acquire,
        AnalyzeStage(),
        DirectStage(),
        TtsStage(),
        ComposeStage(),
    ]

    pre_review = {"acquire", "analyze", "direct"}
    post_review = {"tts", "compose"}

    if start_from and start_from in post_review:
        stages = [s for s in all_stages if s.name in post_review]
        orch = Orchestrator(stages=stages)
        result = asyncio.run(orch.run(ctx, start_from=start_from))
    else:
        stages = [s for s in all_stages if s.name in pre_review]
        orch = Orchestrator(stages=stages)
        result = asyncio.run(orch.run(ctx, start_from=start_from))

        if result.success and not skip_review:
            typer.echo("\n--- HUMAN REVIEW GATE ---")
            typer.echo(f"Knowledge: {result.ctx.knowledge_path}")
            typer.echo(f"Storyboard: {result.ctx.storyboard_path}")
            typer.echo(f"Script: {result.ctx.script_path}")
            typer.echo("Review these files, then resume with:")
            typer.echo(
                f'  uv run pipeline produce --url "{url}" --locale {locale} '
                f"--project-id {project_id} --start-from tts"
            )
            return

        if result.success and skip_review:
            phase2 = [s for s in all_stages if s.name in post_review]
            orch = Orchestrator(stages=phase2)
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


@app.command()
def shorts(
    project_id: int = typer.Option(
        ..., "--project-id", help="Project with existing knowledge.json"
    ),
    count: int = typer.Option(3, "--count", help="Number of Shorts to generate"),
    locale: str = typer.Option("zh-TW", "--locale", help="Target locale"),
    tone: str = typer.Option("educational", "--tone", help="Tone: dramatic, educational, humorous"),
) -> None:
    """Generate Short storyboards from existing knowledge base."""
    config = PipelineConfig()
    work_dir = config.OUTPUT_DIR / "projects" / str(project_id)
    knowledge_path = work_dir / "knowledge.json"

    if not knowledge_path.exists():
        typer.echo(f"No knowledge.json found at {knowledge_path}")
        typer.echo("Run 'pipeline produce' first to create the knowledge base.")
        raise typer.Exit(code=1)

    from pipeline.knowledge import Knowledge
    from pipeline.stages.direct import generate_shorts_storyboards

    knowledge = Knowledge.load(knowledge_path)
    typer.echo(f"Loaded {len(knowledge.facts)} facts from knowledge base")

    storyboards = asyncio.run(generate_shorts_storyboards(knowledge, locale, count, tone))

    for i, sb in enumerate(storyboards, 1):
        path = work_dir / f"storyboard_short_{i:02d}.json"
        sb.save(path)
        est = sb.estimated_duration_sec()
        typer.echo(f"Short #{i}: {path} ({len(sb.scenes)} scenes, ~{est:.0f}s)")

    typer.echo(f"\nGenerated {len(storyboards)} Short storyboards.")


if __name__ == "__main__":
    app()
