from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import typer

from pipeline.publish.auth import DEFAULT_CONFIG_DIR, load_credentials, token_path_for
from pipeline.publish.client import YouTubeClient

if TYPE_CHECKING:
    from pipeline.publish.channels import ChannelConfig

outro_app = typer.Typer(help="Manage per-channel outro clips.")

_CHANNELS_DIR = Path("configs/channels")
_CHANNELS_TOML = Path("configs/youtube_channels.toml")


def _load_config() -> ChannelConfig:
    from pipeline.publish.channels import load_channel_config

    return load_channel_config(_CHANNELS_TOML)


def _fetch_profile_png_via_oauth(channel_id: str, dest: Path, profile_name: str) -> None:
    """Fetch channel avatar using stored OAuth token for the profile."""
    token_path = token_path_for(profile_name, base=DEFAULT_CONFIG_DIR)
    creds = load_credentials(token_path)
    client = YouTubeClient.from_credentials(credentials=creds)
    items = client.channels_list_mine(part="snippet")
    if not items:
        raise RuntimeError("No channel returned from YouTube API")
    thumb_url = items[0]["snippet"]["thumbnails"]["high"]["url"]
    resp = httpx.get(thumb_url, timeout=30)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)


@outro_app.command("build")
def build(
    profile: str = typer.Option(..., "--profile", help="Profile name from youtube_channels.toml"),
    aspect_ratio: str = typer.Option("16:9", "--aspect-ratio", help="16:9 or 9:16"),
    fps: int = typer.Option(30, "--fps", help="Frame rate — must match main video"),
    sample_rate: int = typer.Option(48000, "--sample-rate", help="Audio sample rate Hz"),
    force: bool = typer.Option(False, "--force", help="Rebuild even if outro.mp4 already exists"),
) -> None:
    """Build (or rebuild) the outro clip for a channel profile."""
    cfg = _load_config()
    if profile not in cfg.profiles:
        typer.echo(f"Error: profile '{profile}' not in config.", err=True)
        raise typer.Exit(code=1)

    prof = cfg.profiles[profile]
    channel_dir = _CHANNELS_DIR / profile
    channel_dir.mkdir(parents=True, exist_ok=True)
    profile_png = channel_dir / "profile.png"
    output = channel_dir / "outro.mp4"

    if output.exists() and not force:
        typer.echo(f"outro.mp4 already exists at {output}. Pass --force to rebuild.")
        raise typer.Exit()

    if not profile_png.exists():
        typer.echo(f"profile.png not found at {profile_png} — fetching via OAuth credentials...")
        try:
            _fetch_profile_png_via_oauth(prof.channel_id, profile_png, profile)
            typer.echo("✓ Downloaded profile.png")
        except Exception as exc:
            typer.echo(f"Error fetching profile.png: {exc}", err=True)
            typer.echo(f"Drop it manually at: {profile_png}", err=True)
            raise typer.Exit(code=1) from None

    typer.echo(f"Building outro for '{profile}' ({aspect_ratio})...")
    from pipeline.outro.builder import build_outro

    build_outro(
        profile=prof,
        profile_png_path=profile_png,
        output_path=output,
        aspect_ratio=aspect_ratio,
        fps=fps,
        sample_rate=sample_rate,
    )
    typer.echo(f"✓ outro.mp4 written to {output}")


@outro_app.command("status")
def status() -> None:
    """Show outro build status across all configured profiles."""
    cfg = _load_config()
    for name, prof in sorted(cfg.profiles.items()):
        outro_path = _CHANNELS_DIR / name / "outro.mp4"
        enabled_label = "outro_enabled" if prof.outro_enabled else "disabled   "
        built_label = "✓ built  " if outro_path.exists() else "✗ missing"
        size_label = f"{outro_path.stat().st_size // 1024}KB" if outro_path.exists() else ""
        typer.echo(f"{name:30s}  [{enabled_label}]  [{built_label}]  {size_label}")
