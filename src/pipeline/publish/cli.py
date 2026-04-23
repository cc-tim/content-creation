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
# Custom Click group: routes unknown first args to 'upload'
# ---------------------------------------------------------------------------

class _PublishGroup(click.Group):
    """Routes first arg to 'upload' when it doesn't match a known subcommand."""

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        cmd_name = click.utils.make_str(args[0]) if args else None
        if (
            cmd_name is not None
            and not cmd_name.startswith("-")
            and cmd_name not in self.commands
        ):
            args = ["upload"] + list(args)
        return super().resolve_command(ctx, args)


@click.group(
    cls=_PublishGroup,
    name="publish",
    invoke_without_command=True,
    help="Publish produced projects to YouTube.",
)
@click.pass_context
def publish_app(ctx: click.Context) -> None:
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ---------------------------------------------------------------------------
# upload (default action when no subcommand matched)
# ---------------------------------------------------------------------------

@publish_app.command("upload", hidden=True)
@click.argument("project_id")
@click.option("--profile", default=None)
@click.option("--privacy", default="unlisted")
@click.option("--schedule", default=None)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--force-metadata", is_flag=True, default=False)
@click.option("--force-thumbnail", is_flag=True, default=False)
def upload(
    project_id: str,
    profile: str | None,
    privacy: str,
    schedule: str | None,
    dry_run: bool,
    force_metadata: bool,
    force_thumbnail: bool,
) -> None:
    """Upload a produced project to YouTube."""
    work_dir = _project_dir(project_id)
    ctx_path = work_dir / "context.json"
    if not ctx_path.exists():
        click.echo(f"Error: project not found at {work_dir}", err=True)
        raise SystemExit(1)

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
        click.echo(f"\n✓ Published {pipeline_ctx.youtube_video_id}")
        click.echo(
            f"  Studio: https://studio.youtube.com/video/{pipeline_ctx.youtube_video_id}/edit"
        )
        click.echo(f"  Watch:  https://youtu.be/{pipeline_ctx.youtube_video_id}")


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------

@publish_app.command("auth")
@click.option("--profile", required=True)
@click.option("--reauth", is_flag=True, default=False)
def auth(profile: str, reauth: bool) -> None:
    """Run the OAuth consent flow for a profile and write its token file."""
    cfg = load_channel_config(_load_channel_config_path())
    if profile not in cfg.profiles:
        click.echo(f"Error: profile '{profile}' not in config.", err=True)
        raise SystemExit(1)
    prof = cfg.profiles[profile]
    token_path = _token_dir() / f"{profile}.json"
    if reauth and token_path.exists():
        token_path.unlink()

    cs_file = _client_secret_file()
    creds = run_oauth_flow(cs_file)
    client = YouTubeClient.from_credentials(credentials=creds)

    try:
        discovered = verify_channel_ownership(
            client.api, expected_channel_id=prof.channel_id
        )
    except AuthError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1)

    save_credentials(creds, token_path)
    click.echo(f"✓ Authenticated profile '{profile}' → channel {discovered}")
    if not prof.channel_id:
        click.echo(
            f"  Note: fill in channel_id = \"{discovered}\" under "
            f"[profiles.{profile}] in configs/youtube_channels.toml"
        )


# ---------------------------------------------------------------------------
# accounts
# ---------------------------------------------------------------------------

@publish_app.group("accounts")
def accounts_app() -> None:
    """Manage YouTube channel profile credentials."""
    pass


@accounts_app.command("list")
def accounts_list() -> None:
    """List configured profiles and whether their token files exist."""
    cfg = load_channel_config(_load_channel_config_path())
    td = _token_dir()
    for name in sorted(cfg.profiles):
        path = td / f"{name}.json"
        st = "✓ authenticated" if path.exists() else "✗ missing token"
        click.echo(f"{name:30s}  {st}")


@accounts_app.command("revoke")
@click.argument("profile")
def accounts_revoke(profile: str) -> None:
    """Delete the local token file for a profile."""
    td = _token_dir()
    path = td / f"{profile}.json"
    if not path.exists():
        click.echo(f"no token at {path}")
        return
    path.unlink()
    click.echo(f"✓ deleted {path}")
    click.echo(
        "Remember to also revoke server-side at https://myaccount.google.com/permissions"
    )


@accounts_app.command("show")
@click.argument("profile")
def accounts_show(profile: str) -> None:
    """Fetch the channel's public info for a profile (1 quota unit)."""
    cfg = load_channel_config(_load_channel_config_path())
    if profile not in cfg.profiles:
        click.echo(f"Error: profile '{profile}' not in config", err=True)
        raise SystemExit(1)
    token_path = _token_dir() / f"{profile}.json"
    creds = load_credentials(token_path)
    client = YouTubeClient.from_credentials(credentials=creds)
    items = client.channels_list_mine(part="id,snippet,statistics")
    if not items:
        click.echo("no channel found")
        raise SystemExit(1)
    ch = items[0]
    click.echo(f"id:    {ch['id']}")
    click.echo(f"title: {ch['snippet']['title']}")
    stats = ch.get("statistics", {})
    click.echo(f"subs:  {stats.get('subscriberCount', '?')}")
    click.echo(f"videos: {stats.get('videoCount', '?')}")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@publish_app.command("status")
@click.argument("project_id")
@click.option("--remote", is_flag=True, default=False)
def status(project_id: str, remote: bool) -> None:
    """Show local (and optionally remote) publish state."""
    work_dir = _project_dir(project_id)
    ctx_path = work_dir / "context.json"
    if not ctx_path.exists():
        click.echo(f"Error: project not found: {work_dir}", err=True)
        raise SystemExit(1)
    ctx = PipelineContext.load(ctx_path)

    click.echo(f"project_id: {ctx.project_id}")
    click.echo(f"niche:      {ctx.niche}")
    click.echo(f"locale:     {ctx.locale}")
    click.echo(f"profile:    {ctx.publish_profile or '(unresolved)'}")
    click.echo("")
    click.echo(
        f"video:      {'✓ ' + ctx.youtube_video_id if ctx.youtube_video_id else '✗ pending'}"
    )
    click.echo(f"thumbnail:  {'✓' if ctx.thumbnail_uploaded else '✗ pending'}")
    click.echo(f"disclosure: {'✓' if ctx.disclosure_set else '✗ pending'}")

    if ctx.youtube_video_id:
        click.echo("")
        click.echo(f"Studio: https://studio.youtube.com/video/{ctx.youtube_video_id}/edit")
        click.echo(f"Watch:  https://youtu.be/{ctx.youtube_video_id}")

    next_cmd = None
    if ctx.youtube_video_id is None:
        next_cmd = f"pipeline publish {project_id}"
    elif not ctx.thumbnail_uploaded or not ctx.disclosure_set:
        next_cmd = f"pipeline publish {project_id}  # resumes"
    if next_cmd:
        click.echo(f"\nNext: {next_cmd}")

    if remote and ctx.youtube_video_id:
        if not ctx.publish_profile:
            click.echo("\n(remote check skipped: no publish_profile on context)", err=True)
            return
        cfg = load_channel_config(_load_channel_config_path())
        prof = cfg.profiles[ctx.publish_profile]
        client = _build_youtube_client(prof, cfg)
        items = client.videos_list(video_id=ctx.youtube_video_id, part="status,snippet")
        click.echo("\n--- remote ---")
        if not items:
            click.echo("(video not found on YouTube — deleted?)")
        else:
            v = items[0]
            click.echo(f"title:    {v['snippet']['title']}")
            click.echo(f"privacy:  {v['status']['privacyStatus']}")
            if "publishAt" in v["status"]:
                click.echo(f"publishAt: {v['status']['publishAt']}")


# ---------------------------------------------------------------------------
# Make typer.testing.CliRunner accept publish_app (a Click group, not a Typer)
# ---------------------------------------------------------------------------

try:
    import typer.testing as _typer_testing

    _orig_get_cmd = _typer_testing._get_command

    def _get_cmd_for_publish(app: Any) -> click.BaseCommand:
        if app is publish_app:
            return app  # already a Click group
        return _orig_get_cmd(app)

    _typer_testing._get_command = _get_cmd_for_publish
except Exception:
    pass  # not a test environment
