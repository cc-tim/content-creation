from __future__ import annotations

from pathlib import Path

import typer

outro_app = typer.Typer(help="Manage per-channel outro clips.")

_CHANNELS_DIR = Path("configs/channels")
_CHANNELS_TOML = Path("configs/youtube_channels.toml")


def _load_config():
    from pipeline.publish.channels import load_channel_config

    return load_channel_config(_CHANNELS_TOML)


@outro_app.command("build")
def build(
    profile: str = typer.Option(..., "--profile", help="Profile name from youtube_channels.toml"),
    aspect_ratio: str = typer.Option("16:9", "--aspect-ratio", help="16:9 or 9:16"),
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
        typer.echo(f"profile.png not found at {profile_png} — fetching from YouTube API...")
        from pipeline.outro.builder import fetch_profile_png

        try:
            fetch_profile_png(channel_id=prof.channel_id, dest=profile_png)
            typer.echo("✓ Downloaded profile.png")
        except (ValueError, EnvironmentError) as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1)

    typer.echo(f"Building outro for '{profile}' ({aspect_ratio})...")
    from pipeline.outro.builder import build_outro

    build_outro(
        profile=prof,
        profile_png_path=profile_png,
        output_path=output,
        aspect_ratio=aspect_ratio,
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
