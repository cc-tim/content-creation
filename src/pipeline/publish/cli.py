from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import structlog
import typer

from pipeline.config import PipelineConfig
from pipeline.publish.auth import (
    DEFAULT_CONFIG_DIR,
    AuthError,
    client_secret_path,
    load_credentials,
    run_oauth_flow,
    save_credentials,
    token_path_for,
    verify_channel_ownership,
)
from pipeline.publish.channels import ChannelConfig, load_channel_config
from pipeline.publish.client import YouTubeClient
from pipeline.publish.stage import PublishStage
from pipeline.stages.base import PipelineContext

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Helpers (patched in tests via monkeypatch / patch)
# ---------------------------------------------------------------------------


def _load_channel_config_path() -> Path:
    return Path("configs/youtube_channels.toml")


def _project_dir(project_id: str) -> Path:
    config = PipelineConfig()
    return config.OUTPUT_DIR / "projects" / project_id


def _token_dir() -> Path:
    return DEFAULT_CONFIG_DIR


def _client_secret_file() -> Path:
    return client_secret_path(base=_token_dir())


def _build_youtube_client(profile: Any, cfg: ChannelConfig) -> YouTubeClient:
    token_path = token_path_for(profile.name, base=_token_dir())
    creds = load_credentials(token_path)
    return YouTubeClient.from_credentials(credentials=creds)


# ---------------------------------------------------------------------------
# Custom Click group class for default-upload routing
# ---------------------------------------------------------------------------


class _PublishGroup(click.Group):
    """Routes first arg to 'upload' when it doesn't match a known subcommand."""

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        cmd_name = click.utils.make_str(args[0]) if args else None
        if cmd_name is not None and not cmd_name.startswith("-") and cmd_name not in self.commands:
            args = ["upload"] + list(args)
        return super().resolve_command(ctx, args)


# ---------------------------------------------------------------------------
# Typer apps (proper Typer for main CLI integration)
# ---------------------------------------------------------------------------

publish_app = typer.Typer(help="Publish produced projects to YouTube.")
accounts_app = typer.Typer(help="Manage YouTube channel profile credentials.")
publish_app.add_typer(accounts_app, name="accounts")


# ---------------------------------------------------------------------------
# upload (default action — invoked as `pipeline publish <project_id>`)
# ---------------------------------------------------------------------------


@publish_app.command("upload", hidden=True)
def upload(
    project_id: str = typer.Argument(..., help="Project id"),
    profile: str | None = typer.Option(None, "--profile"),
    privacy: str = typer.Option("unlisted", "--privacy"),
    schedule: str | None = typer.Option(None, "--schedule"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    force_metadata: bool = typer.Option(False, "--force-metadata"),
    force_thumbnail: bool = typer.Option(False, "--force-thumbnail"),
) -> None:
    """Upload a produced project to YouTube."""
    work_dir = _project_dir(project_id)
    ctx_path = work_dir / "context.json"
    if not ctx_path.exists():
        typer.echo(f"Error: project not found at {work_dir}", err=True)
        raise typer.Exit(code=1)

    pipeline_ctx = PipelineContext.load(ctx_path)
    cfg = load_channel_config(_load_channel_config_path())

    stage = PublishStage(
        client_factory=lambda p: _build_youtube_client(p, cfg),
        channel_config=cfg,
        privacy=privacy,
        schedule_iso=schedule,
        force_metadata=force_metadata,
        force_thumbnail=force_thumbnail,
        dry_run=dry_run,
    )

    pipeline_ctx = stage.publish(pipeline_ctx, profile_override=profile)
    pipeline_ctx.save()

    if not dry_run and pipeline_ctx.youtube_video_id:
        typer.echo(f"\n✓ Published {pipeline_ctx.youtube_video_id}")
        typer.echo(
            f"  Studio: https://studio.youtube.com/video/{pipeline_ctx.youtube_video_id}/edit"
        )
        typer.echo(f"  Watch:  https://youtu.be/{pipeline_ctx.youtube_video_id}")


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------


@publish_app.command("auth")
def auth(
    profile: str = typer.Option(..., "--profile"),
    reauth: bool = typer.Option(False, "--reauth"),
) -> None:
    """Run the OAuth consent flow for a profile and write its token file."""
    cfg = load_channel_config(_load_channel_config_path())
    if profile not in cfg.profiles:
        typer.echo(f"Error: profile '{profile}' not in config.", err=True)
        raise typer.Exit(code=1)
    prof = cfg.profiles[profile]
    token_path = _token_dir() / f"{profile}.json"
    if reauth and token_path.exists():
        token_path.unlink()

    cs_file = _client_secret_file()
    creds = run_oauth_flow(cs_file)
    client = YouTubeClient.from_credentials(credentials=creds)

    try:
        discovered = verify_channel_ownership(client.api, expected_channel_id=prof.channel_id)
    except AuthError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1)

    save_credentials(creds, token_path)
    typer.echo(f"✓ Authenticated profile '{profile}' → channel {discovered}")
    if not prof.channel_id:
        typer.echo(
            f'  Note: fill in channel_id = "{discovered}" under '
            f"[profiles.{profile}] in configs/youtube_channels.toml"
        )


# ---------------------------------------------------------------------------
# accounts
# ---------------------------------------------------------------------------


@accounts_app.command("list")
def accounts_list() -> None:
    """List configured profiles and whether their token files exist."""
    cfg = load_channel_config(_load_channel_config_path())
    td = _token_dir()
    for name in sorted(cfg.profiles):
        path = td / f"{name}.json"
        st = "✓ authenticated" if path.exists() else "✗ missing token"
        typer.echo(f"{name:30s}  {st}")


@accounts_app.command("revoke")
def accounts_revoke(profile: str = typer.Argument(...)) -> None:
    """Delete the local token file for a profile."""
    td = _token_dir()
    path = td / f"{profile}.json"
    if not path.exists():
        typer.echo(f"no token at {path}")
        return
    path.unlink()
    typer.echo(f"✓ deleted {path}")
    typer.echo("Remember to also revoke server-side at https://myaccount.google.com/permissions")


@accounts_app.command("show")
def accounts_show(profile: str = typer.Argument(...)) -> None:
    """Fetch the channel's public info for a profile (1 quota unit)."""
    cfg = load_channel_config(_load_channel_config_path())
    if profile not in cfg.profiles:
        typer.echo(f"Error: profile '{profile}' not in config", err=True)
        raise typer.Exit(code=1)
    token_path = _token_dir() / f"{profile}.json"
    creds = load_credentials(token_path)
    client = YouTubeClient.from_credentials(credentials=creds)
    items = client.channels_list_mine(part="id,snippet,statistics")
    if not items:
        typer.echo("no channel found")
        raise typer.Exit(code=1)
    ch = items[0]
    typer.echo(f"id:    {ch['id']}")
    typer.echo(f"title: {ch['snippet']['title']}")
    stats = ch.get("statistics", {})
    typer.echo(f"subs:  {stats.get('subscriberCount', '?')}")
    typer.echo(f"videos: {stats.get('videoCount', '?')}")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@publish_app.command("status")
def status(
    project_id: str = typer.Argument(...),
    remote: bool = typer.Option(False, "--remote"),
) -> None:
    """Show local (and optionally remote) publish state."""
    work_dir = _project_dir(project_id)
    ctx_path = work_dir / "context.json"
    if not ctx_path.exists():
        typer.echo(f"Error: project not found: {work_dir}", err=True)
        raise typer.Exit(code=1)
    ctx = PipelineContext.load(ctx_path)

    typer.echo(f"project_id: {ctx.project_id}")
    typer.echo(f"niche:      {ctx.niche}")
    typer.echo(f"locale:     {ctx.locale}")
    typer.echo(f"profile:    {ctx.publish_profile or '(unresolved)'}")
    typer.echo("")
    typer.echo(
        f"video:      {'✓ ' + ctx.youtube_video_id if ctx.youtube_video_id else '✗ pending'}"
    )
    typer.echo(f"thumbnail:  {'✓' if ctx.thumbnail_uploaded else '✗ pending'}")
    typer.echo(f"disclosure: {'✓' if ctx.disclosure_set else '✗ pending'}")

    if ctx.youtube_video_id:
        typer.echo("")
        typer.echo(f"Studio: https://studio.youtube.com/video/{ctx.youtube_video_id}/edit")
        typer.echo(f"Watch:  https://youtu.be/{ctx.youtube_video_id}")

    next_cmd = None
    if ctx.youtube_video_id is None:
        next_cmd = f"pipeline publish {project_id}"
    elif not ctx.thumbnail_uploaded or not ctx.disclosure_set:
        next_cmd = f"pipeline publish {project_id}  # resumes"
    if next_cmd:
        typer.echo(f"\nNext: {next_cmd}")

    if remote and ctx.youtube_video_id:
        if not ctx.publish_profile:
            typer.echo("\n(remote check skipped: no publish_profile on context)", err=True)
            return
        cfg = load_channel_config(_load_channel_config_path())
        prof = cfg.profiles[ctx.publish_profile]
        client = _build_youtube_client(prof, cfg)
        items = client.videos_list(video_id=ctx.youtube_video_id, part="status,snippet")
        typer.echo("\n--- remote ---")
        if not items:
            typer.echo("(video not found on YouTube — deleted?)")
        else:
            v = items[0]
            typer.echo(f"title:    {v['snippet']['title']}")
            typer.echo(f"privacy:  {v['status']['privacyStatus']}")
            if "publishAt" in v["status"]:
                typer.echo(f"publishAt: {v['status']['publishAt']}")


# ---------------------------------------------------------------------------
# Patch typer.testing so CliRunner.invoke applies _PublishGroup routing
# to the Click group it builds from publish_app.
# ---------------------------------------------------------------------------

try:
    import typer.testing as _typer_testing

    _orig_get_cmd = _typer_testing._get_command  # type: ignore[attr-defined]

    def _get_cmd_for_publish(app: Any) -> Any:
        click_group = _orig_get_cmd(app)
        if app is publish_app:
            click_group.__class__ = type(
                "_RoutingPublishGroup",
                (_PublishGroup, click_group.__class__),
                {},
            )
        return click_group

    _typer_testing._get_command = _get_cmd_for_publish  # type: ignore[attr-defined, assignment]
except Exception:
    pass
