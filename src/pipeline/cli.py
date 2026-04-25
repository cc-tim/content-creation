from __future__ import annotations

import asyncio
from pathlib import Path

import structlog
import typer

from pipeline.cli_compose import compose_app
from pipeline.cli_metadata import metadata_app
from pipeline.cli_proofread import proofread_app
from pipeline.cli_storyboard import storyboard_app
from pipeline.cli_storyteller import storytell_app
from pipeline.cli_voice import voice_app
from pipeline.config import PipelineConfig
from pipeline.gallery_cli import gallery_app
from pipeline.orchestrator import Orchestrator
from pipeline.publish.channels import auto_detect_niche, load_channel_config
from pipeline.publish.cli import publish_app
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
app.add_typer(publish_app, name="publish")
app.add_typer(metadata_app, name="metadata")
app.add_typer(gallery_app, name="gallery")
app.add_typer(proofread_app, name="proofread")
app.add_typer(storytell_app, name="storytell")
app.add_typer(compose_app, name="compose")


def _channel_config_path() -> Path:
    """Path to the channels TOML. Overridable in tests."""
    return Path("configs/youtube_channels.toml")


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
    niche: str | None = typer.Option(
        None,
        "--niche",
        help="Niche (parenting/tech/drama/...). Auto-detected from routing when omitted. "
        "Use --niche none to opt out.",
    ),
) -> None:
    """Run the full production pipeline for a video or web article."""
    config = PipelineConfig()

    if project_id == 0:
        import time

        project_id = int(time.time())

    # Resolve niche (explicit | auto-detected | "none" opt-out)
    if niche is None:
        cfg_path = _channel_config_path()
        if cfg_path.exists():
            try:
                niche = auto_detect_niche(load_channel_config(cfg_path), locale=locale)
                typer.echo(f"niche auto-detected from routing: {niche}")
            except ValueError as exc:
                raise typer.BadParameter(str(exc)) from exc
        else:
            typer.echo(
                f"warning: {cfg_path} not found — --niche omitted and no routing available",
                err=True,
            )

    work_dir = config.OUTPUT_DIR / "projects" / str(project_id)
    work_dir.mkdir(parents=True, exist_ok=True)

    context_file = work_dir / "context.json"
    if start_from and context_file.exists():
        ctx = PipelineContext.load(context_file)
        if voice:
            ctx.voice_id = voice
        ctx.burn_subtitles = subtitles
    else:
        ctx = PipelineContext(
            project_id=project_id,
            source_url=url,
            locale=locale,
            work_dir=work_dir,
            voice_id=voice,
            burn_subtitles=subtitles,
            niche=niche,
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

            # Auto-proofread storyboard at the review gate (before TTS)
            if result.ctx.storyboard_path and result.ctx.storyboard_path.exists():
                typer.echo("\nProofreading storyboard text (Claude Haiku)...")
                try:
                    from pipeline.cli_proofread import print_issues_table, proofread_storyboard

                    issues = proofread_storyboard(result.ctx.storyboard_path)
                    if issues:
                        print_issues_table(issues)
                        typer.echo(
                            f"\nFound {len(issues)} issue(s). Apply before resuming:\n"
                            f"  uv run pipeline proofread run --project-id {project_id} --apply"
                        )
                    else:
                        typer.echo("  ✓ No text issues found.")
                except Exception as exc:
                    typer.echo(f"  (proofread skipped: {exc})")

            # Auto-storytell: narrative flow review at the review gate
            if result.ctx.storyboard_path and result.ctx.storyboard_path.exists():
                typer.echo("\nReviewing narrative flow (Claude Haiku)...")
                try:
                    from pipeline.cli_storyteller import (
                        print_storytell_table,
                        storytell_storyboard,
                    )

                    st_issues = storytell_storyboard(result.ctx.storyboard_path)
                    if st_issues:
                        print_storytell_table(st_issues)
                        typer.echo(
                            f"\nFound {len(st_issues)} narrative issue(s). Apply before resuming:\n"
                            f"  uv run pipeline storytell run --project-id {project_id} --apply"
                        )
                    else:
                        typer.echo("  ✓ No narrative issues found.")
                except Exception as exc:
                    typer.echo(f"  (storytell skipped: {exc})")

            typer.echo("\nReview the files above, then resume with:")
            typer.echo(
                f'  uv run pipeline produce --url "{url}" --locale {locale} '
                f"--project-id {project_id} --start-from tts"
            )
            typer.echo(
                f"  # compose-only re-render (skips TTS):\n"
                f'  uv run pipeline produce --url "{url}" --locale {locale} '
                f"--project-id {project_id} --start-from compose"
            )
            return

        if result.success and skip_review:
            # Auto-apply proofread fixes before TTS in fully automated runs
            if result.ctx.storyboard_path and result.ctx.storyboard_path.exists():
                try:
                    from pipeline.cli_proofread import apply_issues, proofread_storyboard

                    issues = proofread_storyboard(result.ctx.storyboard_path)
                    if issues:
                        n = apply_issues(result.ctx.storyboard_path, issues)
                        typer.echo(f"  proofread: auto-applied {n}/{len(issues)} fix(es)")
                except Exception as exc:
                    typer.echo(f"  (proofread skipped: {exc})")

            # Auto-apply storytell MINOR fixes in --skip-review. MAJOR issues are skipped
            # because they may require scene reordering or hook rewrites — changes that need
            # human review even in automated mode (mirrors the interactive path in cli_storyteller).
            if result.ctx.storyboard_path and result.ctx.storyboard_path.exists():
                try:
                    from pipeline.cli_storyteller import (
                        apply_storytell_issues,
                        storytell_storyboard,
                    )

                    st_issues = storytell_storyboard(result.ctx.storyboard_path)
                    minor = [i for i in st_issues if i["severity"] == "MINOR"]
                    major = [i for i in st_issues if i["severity"] == "MAJOR"]
                    if minor:
                        n = apply_storytell_issues(result.ctx.storyboard_path, minor)
                        typer.echo(f"  storytell: auto-applied {n}/{len(minor)} MINOR fix(es)")
                    if major:
                        typer.echo(
                            f"  storytell: skipped {len(major)} MAJOR issue(s) — run "
                            f"  uv run pipeline storytell run --project-id {project_id} --apply"
                            "  to review"
                        )
                except Exception as exc:
                    typer.echo(f"  (storytell skipped: {exc})")

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


@app.command()
def dashboard(
    port: int = typer.Option(8765, "--port", help="Port to serve on"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Skip auto-opening browser"),
    dev: bool = typer.Option(False, "--dev", help="Enable hot-reload for static/ files"),
) -> None:
    """Start the read-only project monitoring dashboard."""
    import webbrowser

    import uvicorn

    from pipeline.dashboard.server import create_app

    config = PipelineConfig()
    server_app = create_app(config.OUTPUT_DIR, dev_mode=dev)

    url = f"http://localhost:{port}"
    typer.echo(f"Dashboard → {url}  (Ctrl+C to stop)")

    if not no_browser:
        webbrowser.open(url)

    uvicorn.run(server_app, host="localhost", port=port, log_level="warning")


if __name__ == "__main__":
    app()
